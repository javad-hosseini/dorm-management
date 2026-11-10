"""End-to-end integration test for Feature 2 (Cleaned .xlsx Ingestion, Preview, Instruction Edit, and Sync)."""

from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock
import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message

from src.bot.handlers.ingest_cleaned import (
    handle_cancel_ingestion,
    handle_confirm_ingestion,
    handle_edit_instructions,
    handle_new_instructions_text,
    handle_uploaded_document,
    prompt_upload_cleaned_file,
)
from src.bot.states import IngestStates
from src.database.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_full_cleaned_ingest_fsm_workflow(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    mock_bot: AsyncMock,
    make_message: Callable[..., Message],
    make_callback_query: Callable[..., CallbackQuery],
    sample_cleaned_xlsx: Path,
    monkeypatch,
):
    """Simulate complete manager cleaned Excel ingestion workflow:

    1. User initiates via /ingest_cleaned.
    2. Manager uploads cleaned_transactions.xlsx with caption "Insert into Q4 ledger".
    3. Bot replies with Dry-Run Preview showing 3 rows and custom caption instructions.
    4. Manager clicks ingest:edit_instructions and sends "Use strict room number matching".
    5. Bot updates FSM and refreshes preview with new instructions.
    6. Manager clicks ingest:confirm -> Bot executes ingestion, persists idempotency hashes.
    7. Manager re-uploads the same file -> Bot detects duplicate SHA-256 hashes and warns user.
    """
    monkeypatch.setattr("src.bot.handlers.ingest_cleaned.get_db", lambda: db_repo)

    # 1. User prompts upload via /ingest_cleaned
    msg_prompt = make_message(text="/ingest_cleaned", user_id=111111)
    await prompt_upload_cleaned_file(msg_prompt, fsm_context)
    assert await fsm_context.get_state() == IngestStates.waiting_for_file.state

    # 2. User uploads cleaned_transactions.xlsx with caption "Insert into Q4 ledger"
    xlsx_bytes = sample_cleaned_xlsx.read_bytes()

    async def mock_download_xlsx(doc, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(xlsx_bytes)

    mock_bot.download = AsyncMock(side_effect=mock_download_xlsx)

    doc_obj = Document(
        file_id="doc_clean_1",
        file_unique_id="doc_uid_1",
        file_name="cleaned_dormitory_transactions.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    msg_upload = make_message(
        document=doc_obj,
        caption="Insert into Q4 ledger",
        user_id=111111,
    )

    await handle_uploaded_document(msg_upload, fsm_context, mock_bot)

    # Assert state is preview_and_confirm and preview contains metadata
    assert await fsm_context.get_state() == IngestStates.preview_and_confirm.state
    fsm_data = await fsm_context.get_data()
    assert fsm_data["file_name"] == "cleaned_dormitory_transactions.xlsx"
    assert len(fsm_data["rows"]) == 3
    assert fsm_data["instructions"] == "Insert into Q4 ledger"
    assert len(fsm_data["duplicate_hashes"]) == 0

    # 3. Manager clicks ingest:edit_instructions
    cb_edit = make_callback_query(data="ingest:edit_instructions", user_id=111111)
    await handle_edit_instructions(cb_edit, fsm_context)
    assert await fsm_context.get_state() == IngestStates.editing_instructions.state

    # 4. Manager sends new instructions text
    msg_new_instr = make_message(text="Use strict room number matching", user_id=111111)
    await handle_new_instructions_text(msg_new_instr, fsm_context)

    assert await fsm_context.get_state() == IngestStates.preview_and_confirm.state
    fsm_data = await fsm_context.get_data()
    assert fsm_data["instructions"] == "Use strict room number matching"

    # 5. Manager clicks ingest:confirm
    cb_confirm = make_callback_query(data="ingest:confirm", user_id=111111)
    await handle_confirm_ingestion(cb_confirm, fsm_context, mock_bot)

    # Verify FSM cleared and transactions stored in SQLite
    assert await fsm_context.get_state() is None
    stored_hashes = await db_repo.check_row_hashes(fsm_data["row_hashes"])
    assert len(stored_hashes) == 3

    # 6. Manager re-uploads the exact same file -> Duplicate detection triggers
    msg_reupload = make_message(
        document=doc_obj,
        caption="Second upload attempt",
        user_id=111111,
    )
    await handle_uploaded_document(msg_reupload, fsm_context, mock_bot)

    # State transitions to handling_duplicates
    assert await fsm_context.get_state() == IngestStates.handling_duplicates.state
    fsm_reupload_data = await fsm_context.get_data()
    assert len(fsm_reupload_data["duplicate_hashes"]) == 3

    # 7. User clicks ingest:skip_duplicates when all rows are duplicates
    cb_skip = make_callback_query(data="ingest:skip_duplicates", user_id=111111)
    await handle_confirm_ingestion(cb_skip, fsm_context, mock_bot)
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_ingest_cancel_and_error_report(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    mock_bot: AsyncMock,
    make_callback_query: Callable[..., CallbackQuery],
    monkeypatch,
):
    """Test cancellation and failed row error report generation during confirmation."""
    monkeypatch.setattr("src.bot.handlers.ingest_cleaned.get_db", lambda: db_repo)

    # Cancel callback
    cb_cancel = make_callback_query(data="ingest:cancel", user_id=111111)
    await handle_cancel_ingestion(cb_cancel, fsm_context)
    assert await fsm_context.get_state() is None

    # Test confirmation with simulated failed row
    from src.config import settings
    monkeypatch.setattr(settings, "INGESTION_MODE", "mock_dry_run")

    await fsm_context.set_state(IngestStates.preview_and_confirm)
    await fsm_context.update_data(
        file_name="mixed_data.xlsx",
        headers=["Room", "Amount", "simulate_error"],
        rows=[
            {"Room": 101, "Amount": 5000000, "simulate_error": False},
            {"Room": 102, "Amount": 3000000, "simulate_error": True},
        ],
        row_hashes=["h_succ", "h_fail"],
        instructions="Post mixed",
        duplicate_hashes=[],
    )

    cb_confirm = make_callback_query(data="ingest:confirm", user_id=111111)
    await handle_confirm_ingestion(cb_confirm, fsm_context, mock_bot)

    # Verify bot.send_document was called with the failed_rows_report.xlsx
    mock_bot.send_document.assert_awaited()
    _, kwargs = mock_bot.send_document.call_args
    doc = kwargs.get("document")
    assert doc is not None
    assert "failed_rows_report.xlsx" == kwargs.get("caption", "") or "Failed Transactions Report" in kwargs.get("caption", "")
