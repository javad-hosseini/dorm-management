"""End-to-end integration test for Feature 1 (Raw Data Collection and Cell-Anchored Excel Export)."""

from pathlib import Path
from typing import Callable
from unittest.mock import AsyncMock
import openpyxl
import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message, PhotoSize

from src.bot.handlers.raw_data import (
    handle_cancel_session,
    handle_clear_row,
    handle_collecting_row_input,
    handle_discard_session,
    handle_finish_export,
    handle_next_row,
    handle_resume_session,
    handle_start_raw_data,
    handle_undo_last,
)
from src.bot.states import RawDataStates
from src.database.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_full_raw_data_fsm_workflow(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    mock_bot: AsyncMock,
    make_message: Callable[..., Message],
    make_callback_query: Callable[..., CallbackQuery],
    synthetic_receipt_image: Path,
    monkeypatch,
):
    """Simulate complete manager raw entry journey:

    1. Start raw session (/raw_data).
    2. Attempt advance with empty row (rejected).
    3. Send Photo WITH Caption -> 2 blocks added (IMAGE + TEXT).
    4. Send 2-photo Album -> 2 more IMAGE blocks added (4 blocks total).
    5. Undo last block -> 3 blocks remaining.
    6. Advance to Row #2.
    7. Send plain text note for Resident 2.
    8. Finish & Export -> .xlsx generated, sent via bot, session marked completed in SQLite.
    """
    monkeypatch.setattr("src.bot.handlers.raw_data.get_db", lambda: db_repo)

    # 1. User sends /raw_data
    msg_start = make_message(text="/raw_data", user_id=111111)
    await handle_start_raw_data(msg_start, fsm_context)

    state = await fsm_context.get_state()
    assert state == RawDataStates.collecting_row.state

    session = await db_repo.get_active_session(111111)
    assert session is not None
    assert session.current_row_index == 1
    session_id = session.session_id

    # 2. Click raw:next_row immediately while Row #1 is empty
    cb_next_empty = make_callback_query(data="raw:next_row", user_id=111111)
    await handle_next_row(cb_next_empty, fsm_context)
    cb_next_empty.answer.assert_awaited_once()
    _, kwargs = cb_next_empty.answer.call_args
    assert kwargs.get("show_alert") is True
    assert (await db_repo.get_session(session_id)).current_row_index == 1

    # 3. Send Photo WITH Caption ("Room 204 - Ali Rezaei - 5,000,000")
    photo_obj = PhotoSize(file_id="p_single", file_unique_id="pu_1", width=600, height=800)
    msg_photo_caption = make_message(
        photo=[photo_obj],
        caption="Room 204 - Ali Rezaei - 5,000,000",
        user_id=111111,
    )
    await handle_collecting_row_input(msg_photo_caption, fsm_context, mock_bot)

    blocks_r1 = await db_repo.get_blocks_for_row(session_id, row_index=1)
    assert len(blocks_r1) == 2
    assert blocks_r1[0].block_type == "IMAGE"
    assert blocks_r1[1].block_type == "TEXT"
    assert blocks_r1[1].text_content == "Room 204 - Ali Rezaei - 5,000,000"

    # 4. Send 2-photo Album
    m_alb1 = make_message(
        photo=[PhotoSize(file_id="p_alb1", file_unique_id="pu_a1", width=500, height=700)],
        media_group_id="mg_test",
        user_id=111111,
    )
    m_alb2 = make_message(
        photo=[PhotoSize(file_id="p_alb2", file_unique_id="pu_a2", width=500, height=700)],
        media_group_id="mg_test",
        user_id=111111,
    )
    await handle_collecting_row_input(
        m_alb1,
        fsm_context,
        mock_bot,
        album=[m_alb1, m_alb2],
    )

    blocks_r1 = await db_repo.get_blocks_for_row(session_id, row_index=1)
    assert len(blocks_r1) == 4
    assert blocks_r1[2].block_type == "IMAGE"
    assert blocks_r1[3].block_type == "IMAGE"

    # 5. Undo last block
    cb_undo = make_callback_query(data="raw:undo_last", user_id=111111)
    await handle_undo_last(cb_undo, fsm_context)

    blocks_r1 = await db_repo.get_blocks_for_row(session_id, row_index=1)
    assert len(blocks_r1) == 3

    # 6. Click raw:next_row -> Advance to Row #2
    cb_next_valid = make_callback_query(data="raw:next_row", user_id=111111)
    await handle_next_row(cb_next_valid, fsm_context)
    session_r2 = await db_repo.get_session(session_id)
    assert session_r2.current_row_index == 2

    # 7. Send plain text note for Resident 2
    msg_note_r2 = make_message(text="Room 305 - Reza Mohammadi - Rent paid cash", user_id=111111)
    await handle_collecting_row_input(msg_note_r2, fsm_context, mock_bot)

    blocks_r2 = await db_repo.get_blocks_for_row(session_id, row_index=2)
    assert len(blocks_r2) == 1
    assert blocks_r2[0].block_type == "TEXT"

    # 8. Finish & Export
    cb_finish = make_callback_query(data="raw:finish", user_id=111111)
    await handle_finish_export(cb_finish, fsm_context, mock_bot)

    # Session in DB marked COMPLETED
    session_done = await db_repo.get_session(session_id)
    assert session_done.status == "COMPLETED"
    assert await db_repo.get_active_session(111111) is None

    # State cleared
    assert await fsm_context.get_state() is None

    # Document sent via bot.send_document
    mock_bot.send_document.assert_awaited_once()
    _, kwargs = mock_bot.send_document.call_args
    doc_arg = kwargs.get("document")
    assert doc_arg is not None
    assert Path(doc_arg.path).exists()

    # Load and verify exported workbook
    wb = openpyxl.load_workbook(doc_arg.path)
    assert "Raw_Transactions" in wb.sheetnames
    assert "_AI_EXTRACTION_GUIDE" in wb.sheetnames
    ws = wb["Raw_Transactions"]
    assert ws.cell(row=2, column=1).value == "Resident_1"
    assert ws.cell(row=3, column=1).value == "Resident_2"
    wb.close()


@pytest.mark.asyncio
async def test_raw_data_resume_and_discard_flow(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    make_message: Callable[..., Message],
    make_callback_query: Callable[..., CallbackQuery],
    monkeypatch,
):
    """Test resuming an active session and discarding an active session."""
    monkeypatch.setattr("src.bot.handlers.raw_data.get_db", lambda: db_repo)

    # Pre-create an active session in SQLite
    session = await db_repo.create_session(111111, "existing_sess_001")
    await db_repo.add_block("existing_sess_001", row_index=1, block_type="TEXT", text_content="Old Note")

    # User sends /raw_data -> bot prompts with resume keyboard
    msg = make_message(text="/raw_data", user_id=111111)
    await handle_start_raw_data(msg, fsm_context)
    msg.answer.assert_awaited_once()
    args, _ = msg.answer.call_args
    assert "Unfinished Session Found" in args[0]

    # Click resume
    cb_resume = make_callback_query(data="raw:resume", user_id=111111)
    await handle_resume_session(cb_resume, fsm_context)
    assert await fsm_context.get_state() == RawDataStates.collecting_row.state
    data = await fsm_context.get_data()
    assert data["session_id"] == "existing_sess_001"

    # Click discard
    cb_discard = make_callback_query(data="raw:discard", user_id=111111)
    await handle_discard_session(cb_discard, fsm_context)
    new_active = await db_repo.get_active_session(111111)
    assert new_active is not None
    assert new_active.session_id != "existing_sess_001"


@pytest.mark.asyncio
async def test_raw_data_clear_row_and_cancel_session(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    make_callback_query: Callable[..., CallbackQuery],
    monkeypatch,
):
    """Test clear_row and cancel_session callbacks."""
    monkeypatch.setattr("src.bot.handlers.raw_data.get_db", lambda: db_repo)

    session = await db_repo.create_session(111111, "sess_actions")
    await db_repo.add_block("sess_actions", 1, "TEXT", "Note A")
    await fsm_context.set_state(RawDataStates.collecting_row)
    await fsm_context.update_data(session_id="sess_actions")

    # Clear Row
    cb_clear = make_callback_query(data="raw:clear_row", user_id=111111)
    await handle_clear_row(cb_clear, fsm_context)
    assert len(await db_repo.get_blocks_for_row("sess_actions", 1)) == 0

    # Cancel Session
    cb_cancel = make_callback_query(data="raw:cancel", user_id=111111)
    await handle_cancel_session(cb_cancel, fsm_context)
    assert (await db_repo.get_session("sess_actions")).status == "CANCELLED"
    assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_raw_data_document_and_unsupported_media(
    db_repo: DatabaseRepository,
    fsm_context: FSMContext,
    mock_bot: AsyncMock,
    make_message: Callable[..., Message],
    monkeypatch,
):
    """Test document image upload fallback and gentle rejection of unsupported media."""
    monkeypatch.setattr("src.bot.handlers.raw_data.get_db", lambda: db_repo)
    session = await db_repo.create_session(111111, "sess_media")
    await fsm_context.set_state(RawDataStates.collecting_row)
    await fsm_context.update_data(session_id="sess_media")

    # Document that is an image
    doc_img = Document(
        file_id="doc_img_1",
        file_unique_id="doc_uid_img",
        file_name="receipt.jpg",
        mime_type="image/jpeg",
    )
    msg_doc = make_message(document=doc_img, caption="Room 105", user_id=111111)
    await handle_collecting_row_input(msg_doc, fsm_context, mock_bot)

    blocks = await db_repo.get_blocks_for_row("sess_media", 1)
    assert len(blocks) == 2
    assert blocks[0].block_type == "IMAGE"
    assert blocks[1].block_type == "TEXT"

    # Document that is NOT an image (e.g. PDF)
    doc_pdf = Document(
        file_id="doc_pdf_1",
        file_unique_id="doc_uid_pdf",
        file_name="contract.pdf",
        mime_type="application/pdf",
    )
    msg_pdf = make_message(document=doc_pdf, user_id=111111)
    await handle_collecting_row_input(msg_pdf, fsm_context, mock_bot)
    msg_pdf.answer.assert_awaited()
    assert "not a supported image" in msg_pdf.answer.call_args[0][0]

    # Unsupported media (no text, photo, or document)
    msg_unsupported = make_message(user_id=111111)
    msg_unsupported.text = None
    await handle_collecting_row_input(msg_unsupported, fsm_context, mock_bot)
    assert "Unsupported input format" in msg_unsupported.answer.call_args[0][0]
