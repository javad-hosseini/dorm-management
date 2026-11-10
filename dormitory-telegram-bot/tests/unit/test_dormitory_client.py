"""Unit tests for Dormitory System API and Agent clients with respx HTTP mocking."""

import httpx
import pytest
import respx

from src.config import Settings
from src.database.repository import DatabaseRepository
from src.services.dormitory_client import (
    AgentWebhookClient,
    FileDropzoneClient,
    MockDryRunClient,
    OpenAICompatibleAgentClient,
    get_dormitory_client,
)


@pytest.mark.asyncio
async def test_mock_dry_run_mode():
    """Verify mock dry run processes rows without network calls, returning 100% success."""
    client = MockDryRunClient()
    rows = [
        {"Room": 101, "Amount": 5000000},
        {"Room": 102, "Amount": 7000000},
        {"Room": 103, "Amount": 4500000},
    ]
    hashes = ["h101", "h102", "h103"]

    results = await client.process_rows(rows, hashes, "Standard ledger rules")

    assert len(results) == 3
    assert all(r.success for r in results)
    assert sum(1 for r in results if r.success) == 3
    assert sum(1 for r in results if not r.success) == 0


@pytest.mark.asyncio
@respx.mock
async def test_agent_webhook_all_success():
    """Verify agent webhook batch POST payload, Bearer authorization, and success parsing."""
    api_url = "https://agent.dormitory.test/api/v1/ingest"
    api_key = "secret_agent_token_xyz"

    mock_route = respx.post(api_url).respond(
        status_code=200,
        json={"status": "BATCH_OK", "processed": 2},
    )

    client = AgentWebhookClient(api_url=api_url, api_key=api_key)
    rows = [{"Room": 101, "Amount": 5000000}, {"Room": 102, "Amount": 6000000}]
    hashes = ["hash_1", "hash_2"]

    results = await client.process_rows(rows, hashes, instructions="Categorize strictly as rent.")

    assert len(results) == 2
    assert all(r.success for r in results)
    assert mock_route.called

    request = mock_route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {api_key}"
    payload = request.read().decode("utf-8")
    assert "instructions" in payload
    assert "transactions" in payload
    assert "Categorize strictly as rent." in payload


@pytest.mark.asyncio
@respx.mock
async def test_agent_webhook_partial_failure_and_idempotency(db_repo: DatabaseRepository):
    """Simulate 5 rows where Row #3 fails; verify 4 succeed, 1 fails, and idempotency is recorded."""
    api_url = "https://agent.dormitory.test/api/v1/ingest"

    # Mock endpoint returning itemized per-row statuses where row 3 fails
    respx.post(api_url).respond(
        status_code=200,
        json={
            "results": [
                {"success": True, "ledger_id": "L1"},
                {"success": True, "ledger_id": "L2"},
                {"success": False, "error": "Invalid tenant identifier: Room 999"},
                {"success": True, "ledger_id": "L4"},
                {"success": True, "ledger_id": "L5"},
            ]
        },
    )

    client = AgentWebhookClient(api_url=api_url, api_key="test-key")
    rows = [
        {"Room": 101, "Amount": 1000},
        {"Room": 102, "Amount": 2000},
        {"Room": 999, "Amount": 3000},
        {"Room": 104, "Amount": 4000},
        {"Room": 105, "Amount": 5000},
    ]
    hashes = [f"h_{i}" for i in range(1, 6)]

    results = await client.process_rows(rows, hashes, instructions="Ledger sync")

    assert len(results) == 5
    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    assert len(succeeded) == 4
    assert len(failed) == 1
    assert failed[0].row_index == 4
    assert "Invalid tenant identifier" in (failed[0].error_message or "")

    # Record in SQLite repository
    for res in results:
        status_str = "SUCCESS" if res.success else "FAILED"
        await db_repo.record_ingested_transaction(
            row_hash=res.row_hash,
            file_name="clean.xlsx",
            row_index=res.row_index,
            data_json="{}",
            status=status_str,
            user_id=111111,
            error_message=res.error_message,
        )

    # Verify idempotency table contains records
    existing_hashes = await db_repo.check_row_hashes(hashes)
    assert len(existing_hashes) == 5


@pytest.mark.asyncio
@respx.mock
async def test_agent_webhook_network_timeout_and_error_capture():
    """Verify that network timeout or 503 error is handled gracefully without crashing."""
    api_url = "https://agent.dormitory.test/api/v1/ingest"

    # First batch POST fails with ConnectTimeout
    respx.post(api_url).mock(side_effect=httpx.ConnectTimeout("Connection timed out"))

    client = AgentWebhookClient(api_url=api_url, api_key="test-key", timeout=1.0)
    rows = [{"Room": 101, "Amount": 1000}]
    hashes = ["h_timeout"]

    results = await client.process_rows(rows, hashes, instructions="Ledger sync")

    assert len(results) == 1
    assert results[0].success is False
    assert "Network error" in (results[0].error_message or "") or "ConnectTimeout" in (
        results[0].error_message or ""
    )


@pytest.mark.asyncio
async def test_agent_webhook_missing_url_fallback():
    """Verify fallback to mock dry run when api_url is empty."""
    client = AgentWebhookClient(api_url="", api_key="")
    results = await client.process_rows([{"Room": 1}], ["h_empty"], "Instructions")
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.asyncio
@respx.mock
async def test_openai_compatible_agent_client():
    """Verify OpenAI-compatible LLM agent mode payload, backend forwarding, and response parsing."""
    base_url = "https://api.openai.com/v1"
    backend_url = "https://backend.dormitory.test/api/v1/ledger"

    respx.post(f"{base_url}/chat/completions").respond(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Transaction verified. Type: RENT_PAYMENT, Room: 101."
                    }
                }
            ]
        },
    )
    respx.post(backend_url).respond(status_code=201)

    client = OpenAICompatibleAgentClient(
        base_url=base_url,
        api_key="sk-test-mock-key",
        model="gpt-4o-mini",
        backend_url=backend_url,
    )
    rows = [{"Room": 101, "Amount": 5000000}]
    hashes = ["h_llm_1"]

    results = await client.process_rows(rows, hashes, "Validate rent")
    assert len(results) == 1
    assert results[0].success is True
    assert "Transaction verified" in results[0].response_data["llm_response"]
    assert results[0].response_data["backend"]["backend_status"] == 201


@pytest.mark.asyncio
async def test_openai_compatible_agent_missing_key_fallback():
    """Verify fallback to mock dry run when openai key is missing."""
    client = OpenAICompatibleAgentClient(
        base_url="https://api.openai.com/v1",
        api_key="",
        model="gpt-4o",
    )
    results = await client.process_rows([{"Room": 1}], ["h_nokey"], "Instructions")
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.asyncio
async def test_file_dropzone_client(tmp_path):
    """Verify file dropzone client places rows on disk for Antigravity CLI without network calls."""
    from src.services.dormitory_client import FileDropzoneClient

    target_dir = tmp_path / "dropzone"
    client = FileDropzoneClient(target_dir=target_dir)

    rows = [{"Room": 101, "Amount": 4500000}, {"Room": 102, "Amount": 6000000}]
    hashes = ["h1", "h2"]

    results = await client.process_rows(rows, hashes, "Antigravity CLI instructions")
    assert len(results) == 2
    assert all(r.success for r in results)
    assert target_dir.exists()
    assert results[0].response_data["mode"] == "file_dropzone"


def test_get_dormitory_client_factory():
    """Verify client factory returns correct class for each configuration mode."""
    s_dropzone = Settings(INGESTION_MODE="file_dropzone")
    assert isinstance(get_dormitory_client(s_dropzone), FileDropzoneClient)

    s_mock = Settings(INGESTION_MODE="mock_dry_run")
    assert isinstance(get_dormitory_client(s_mock), MockDryRunClient)

    s_webhook = Settings(
        INGESTION_MODE="agent_webhook",
        DORMITORY_AGENT_API_URL="https://agent.example.com/api",
    )
    assert isinstance(get_dormitory_client(s_webhook), AgentWebhookClient)

    s_openai = Settings(
        INGESTION_MODE="openai_compatible_agent",
        OPENAI_API_KEY="sk-key",
    )
    assert isinstance(get_dormitory_client(s_openai), OpenAICompatibleAgentClient)
