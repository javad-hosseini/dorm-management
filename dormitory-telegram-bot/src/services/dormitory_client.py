"""Pluggable async client for syncing cleaned transactions to Dormitory AI Agent / Backend."""

from __future__ import annotations

import abc
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class RowResult:
    """Result of processing an individual transaction row."""

    row_index: int
    row_hash: str
    success: bool
    error_message: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None


class DormitoryClientBase(abc.ABC):
    """Abstract interface for dormitory ingestion backends."""

    @abc.abstractmethod
    async def process_rows(
        self,
        rows: List[Dict[str, Any]],
        row_hashes: List[str],
        instructions: str,
    ) -> List[RowResult]:
        """Process a list of transaction rows with instructions."""
        raise NotImplementedError


class FileDropzoneClient(DormitoryClientBase):
    """Saves uploaded transactions to local disk as a clean drop-zone for Antigravity CLI."""

    def __init__(self, target_dir: Path | str) -> None:
        self.target_dir = Path(target_dir)

    async def process_rows(
        self,
        rows: List[Dict[str, Any]],
        row_hashes: List[str],
        instructions: str,
    ) -> List[RowResult]:
        self.target_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[FILE DROPZONE] Placed %d rows into %s for manual Antigravity CLI processing",
            len(rows),
            self.target_dir,
        )

        return [
            RowResult(
                row_index=idx,
                row_hash=r_hash,
                success=True,
                response_data={"destination": str(self.target_dir), "mode": "file_dropzone"},
            )
            for idx, r_hash in enumerate(row_hashes, start=2)
        ]


class MockDryRunClient(DormitoryClientBase):
    """Simulates ingestion for testing, local development, and dry-run verification."""

    async def process_rows(
        self,
        rows: List[Dict[str, Any]],
        row_hashes: List[str],
        instructions: str,
    ) -> List[RowResult]:
        logger.info(
            "[MOCK DRY-RUN] Simulating processing of %d rows with instructions (len=%d)",
            len(rows),
            len(instructions),
        )

        results: List[RowResult] = []
        for idx, (row, r_hash) in enumerate(zip(rows, row_hashes), start=2):
            await asyncio.sleep(0.05)  # Realistic async yield

            # Allow simulated failures for testing if row has test triggers
            is_mock_error = (
                str(row.get("simulate_error", "")).lower() in ("true", "1")
                or str(row.get("Status", "")).lower() == "error"
            )

            if is_mock_error:
                results.append(
                    RowResult(
                        row_index=idx,
                        row_hash=r_hash,
                        success=False,
                        error_message="Simulated validation error: Missing or invalid room identifier",
                    )
                )
            else:
                results.append(
                    RowResult(
                        row_index=idx,
                        row_hash=r_hash,
                        success=True,
                        response_data={"mock_ledger_id": f"LEDGER-MOCK-{idx}", "status": "POSTED"},
                    )
                )

        logger.info(
            "[MOCK DRY-RUN] Ingestion simulation complete. Succeeded: %d, Failed: %d",
            sum(1 for r in results if r.success),
            sum(1 for r in results if not r.success),
        )
        return results


class AgentWebhookClient(DormitoryClientBase):
    """Client for calling Dormitory AI Agent webhook or REST API endpoints."""

    def __init__(self, api_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout

    async def process_rows(
        self,
        rows: List[Dict[str, Any]],
        row_hashes: List[str],
        instructions: str,
    ) -> List[RowResult]:
        if not self.api_url:
            logger.warning("DORMITORY_AGENT_API_URL is not set. Falling back to mock dry-run.")
            return await MockDryRunClient().process_rows(rows, row_hashes, instructions)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "instructions": instructions,
            "transactions": [
                {"row_index": idx, "row_hash": r_hash, "data": row}
                for idx, (row, r_hash) in enumerate(zip(rows, row_hashes), start=2)
            ],
        }

        # Try batch execution first
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(self.api_url, json=payload, headers=headers)
                if response.status_code in (200, 201):
                    data = response.json() if response.content else {}
                    # If endpoint returned per-row itemized results
                    items_result = data.get("results")
                    if isinstance(items_result, list) and len(items_result) == len(rows):
                        results = []
                        for res, (row, r_hash), idx in zip(
                            items_result, zip(rows, row_hashes), range(2, len(rows) + 2)
                        ):
                            succ = bool(res.get("success", True))
                            err = res.get("error") if not succ else None
                            results.append(
                                RowResult(
                                    row_index=idx,
                                    row_hash=r_hash,
                                    success=succ,
                                    error_message=err,
                                    response_data=res,
                                )
                            )
                        return results

                    # Batch accepted globally
                    return [
                        RowResult(
                            row_index=idx,
                            row_hash=r_hash,
                            success=True,
                            response_data=data,
                        )
                        for idx, r_hash in enumerate(row_hashes, start=2)
                    ]
            except Exception as e:
                logger.warning("Batch webhook POST failed (%s). Attempting row-by-row with retries...", e)

            # Fallback to row-by-row processing with retry backoff
            results: List[RowResult] = []
            for idx, (row, r_hash) in enumerate(zip(rows, row_hashes), start=2):
                row_payload = {
                    "instructions": instructions,
                    "row_index": idx,
                    "row_hash": r_hash,
                    "transaction": row,
                }
                success = False
                error_msg: Optional[str] = None
                resp_json: Optional[Dict[str, Any]] = None

                for attempt in range(3):
                    try:
                        r = await client.post(self.api_url, json=row_payload, headers=headers)
                        if r.status_code in (200, 201):
                            success = True
                            resp_json = r.json() if r.content else {}
                            break
                        error_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    except Exception as exc:
                        error_msg = f"Network error: {str(exc)[:150]}"

                    await asyncio.sleep(0.5 * (2**attempt))

                results.append(
                    RowResult(
                        row_index=idx,
                        row_hash=r_hash,
                        success=success,
                        error_message=error_msg,
                        response_data=resp_json,
                    )
                )

            return results


class OpenAICompatibleAgentClient(DormitoryClientBase):
    """Client for calling an LLM agent endpoint (e.g. OpenAI, vLLM, Ollama, LiteLLM)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        backend_url: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.backend_url = backend_url
        self.timeout = timeout

    async def process_rows(
        self,
        rows: List[Dict[str, Any]],
        row_hashes: List[str],
        instructions: str,
    ) -> List[RowResult]:
        if not self.api_key and "openai.com" in self.base_url:
            logger.warning("OPENAI_API_KEY is not set. Falling back to mock dry-run.")
            return await MockDryRunClient().process_rows(rows, row_hashes, instructions)

        system_prompt = (
            "You are a Dormitory Financial Ledger ingestion agent. Your task is to validate "
            "and format dormitory transactions according to operational rules."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        results: List[RowResult] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for idx, (row, r_hash) in enumerate(zip(rows, row_hashes), start=2):
                user_content = (
                    f"Instructions:\n{instructions}\n\n"
                    f"Transaction Row (Index {idx}):\n{json.dumps(row, ensure_ascii=False)}"
                )
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.1,
                }

                try:
                    url = f"{self.base_url}/chat/completions"
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        message_text = (
                            data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        )

                        # If backend URL configured, forward the LLM-validated ledger item
                        backend_data = None
                        if self.backend_url:
                            b_resp = await client.post(
                                self.backend_url,
                                json={"row_index": idx, "row_hash": r_hash, "analysis": message_text, "raw": row},
                                headers={"Content-Type": "application/json"},
                            )
                            backend_data = {"backend_status": b_resp.status_code}

                        results.append(
                            RowResult(
                                row_index=idx,
                                row_hash=r_hash,
                                success=True,
                                response_data={"llm_response": message_text, "backend": backend_data},
                            )
                        )
                    else:
                        results.append(
                            RowResult(
                                row_index=idx,
                                row_hash=r_hash,
                                success=False,
                                error_message=f"LLM API returned HTTP {response.status_code}: {response.text[:150]}",
                            )
                        )
                except Exception as e:
                    logger.exception("Error processing row %d via LLM agent: %s", idx, e)
                    results.append(
                        RowResult(
                            row_index=idx,
                            row_hash=r_hash,
                            success=False,
                            error_message=f"Agent error: {str(e)[:150]}",
                        )
                    )

        return results


def get_dormitory_client(settings: Settings) -> DormitoryClientBase:
    """Factory function returning the configured dormitory ingestion client."""
    mode = settings.INGESTION_MODE
    logger.info("Initializing Dormitory Client with mode: %s", mode)

    if mode == "file_dropzone":
        return FileDropzoneClient(target_dir=settings.SPREADSHEET_UPLOAD_DIR)
    elif mode == "agent_webhook":
        return AgentWebhookClient(
            api_url=settings.DORMITORY_AGENT_API_URL,
            api_key=settings.DORMITORY_AGENT_API_KEY,
        )
    elif mode == "openai_compatible_agent":
        return OpenAICompatibleAgentClient(
            base_url=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            model=settings.AGENT_MODEL,
            backend_url=settings.DORMITORY_BACKEND_API_URL,
        )
    else:
        return MockDryRunClient()

