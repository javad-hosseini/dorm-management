"""Feature 1: Raw data collection, live row summarization, and cell-anchored Excel builder."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from openpyxl.utils import get_column_letter

from src.bot.keyboards import (
    BTN_START_RAW,
    get_main_menu_keyboard,
    get_raw_row_control_keyboard,
    get_session_resume_keyboard,
)
from src.bot.states import RawDataStates
from src.config import settings
from src.database.repository import BlockRecord, SessionRecord, get_db
from src.services.excel_builder import ExcelBuilder

logger = logging.getLogger(__name__)

router = Router(name="raw_data_router")


def format_row_summary(row_index: int, blocks: List[BlockRecord]) -> str:
    """Format live summary of blocks currently in the row."""
    if not blocks:
        return (
            f"📌 <b>Row #{row_index} (Resident {row_index})</b> currently has <b>0 blocks</b>.\n\n"
            f"Send photos or text notes to add to Row #{row_index}, or choose an action:"
        )

    items: List[str] = []
    for b in blocks:
        # Col A is Resident_Row_ID, so block 1 (col_index 1) is Col B
        excel_col = b.col_index + 1
        letter = get_column_letter(excel_col)
        if b.block_type == "IMAGE":
            items.append(f"Col {letter}: 🖼️ Photo")
        else:
            txt_preview = (b.text_content or "").replace("\n", " ")
            if len(txt_preview) > 28:
                txt_preview = txt_preview[:25] + "..."
            items.append(f'Col {letter}: 📝 "{txt_preview}"')

    preview_str = " | ".join(items)
    return (
        f"📌 <b>Row #{row_index} (Resident {row_index})</b> currently has <b>{len(blocks)} block(s)</b>:\n"
        f"<code>{preview_str}</code>\n\n"
        f"Send more photos/text to add to Row #{row_index}, or choose an action:"
    )


async def _start_fresh_session(user_id: int, state: FSMContext, message: Message) -> None:
    """Initialize a brand-new raw data entry session."""
    session_id = uuid.uuid4().hex[:10]
    session_dir = settings.SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    db = get_db()
    session = await db.create_session(user_id=user_id, session_id=session_id)

    await state.set_state(RawDataStates.collecting_row)
    await state.update_data(session_id=session.session_id)

    text = (
        "🟢 <b>Raw Data Session Started!</b>\n\n"
        "You are currently entering data for <b>Row #1 (Resident 1)</b>.\n"
        "Send photos (single or album), photos with captions, or text notes.\n"
        "Each item will be placed in a new column of Row #1."
    )
    await message.answer(text, reply_markup=get_raw_row_control_keyboard(1))


@router.message(Command("raw_data"))
@router.message(F.text == BTN_START_RAW)
async def handle_start_raw_data(message: Message, state: FSMContext) -> None:
    """Initiate raw data collection, checking for existing active sessions to resume."""
    user_id = message.from_user.id if message.from_user else 0
    db = get_db()
    active_session = await db.get_active_session(user_id)

    if active_session:
        # Prompt user to resume or discard
        blocks = await db.get_blocks_for_row(
            active_session.session_id, active_session.current_row_index
        )
        prompt_text = (
            f"⚠️ <b>Unfinished Session Found!</b>\n\n"
            f"You have an ongoing session (<code>{active_session.session_id}</code>) "
            f"at <b>Row #{active_session.current_row_index}</b> ({len(blocks)} block(s) in this row).\n\n"
            f"Would you like to resume where you left off or discard it and start fresh?"
        )
        await message.answer(prompt_text, reply_markup=get_session_resume_keyboard())
    else:
        await _start_fresh_session(user_id, state, message)


@router.callback_query(F.data == "raw:resume")
async def handle_resume_session(callback: CallbackQuery, state: FSMContext) -> None:
    """Resume an existing active session."""
    user_id = callback.from_user.id
    db = get_db()
    session = await db.get_active_session(user_id)

    if not session:
        await callback.answer("No active session found. Starting fresh...", show_alert=True)
        if callback.message and isinstance(callback.message, Message):
            await _start_fresh_session(user_id, state, callback.message)
        return

    await state.set_state(RawDataStates.collecting_row)
    await state.update_data(session_id=session.session_id)

    blocks = await db.get_blocks_for_row(session.session_id, session.current_row_index)
    summary_text = (
        f"▶️ <b>Session Resumed!</b>\n\n"
        f"{format_row_summary(session.current_row_index, blocks)}"
    )

    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            summary_text,
            reply_markup=get_raw_row_control_keyboard(session.current_row_index),
        )


@router.callback_query(F.data == "raw:discard")
async def handle_discard_session(callback: CallbackQuery, state: FSMContext) -> None:
    """Discard previous session and start a new fresh one."""
    user_id = callback.from_user.id
    db = get_db()
    active_session = await db.get_active_session(user_id)
    if active_session:
        await db.set_session_status(active_session.session_id, "CANCELLED")

    await callback.answer("Previous session discarded.")
    if callback.message and isinstance(callback.message, Message):
        await _start_fresh_session(user_id, state, callback.message)


@router.callback_query(F.data == "raw:next_row")
async def handle_next_row(callback: CallbackQuery, state: FSMContext) -> None:
    """Move to next resident row."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    session: Optional[SessionRecord] = None
    if session_id:
        session = await db.get_session(session_id)
    if not session:
        session = await db.get_active_session(callback.from_user.id)
        if session:
            await state.update_data(session_id=session.session_id)

    if not session:
        await callback.answer("No active session found. Please start a session.", show_alert=True)
        return

    blocks = await db.get_blocks_for_row(session.session_id, session.current_row_index)
    if not blocks:
        await callback.answer(
            "Current row is empty! Add at least one photo or text before moving to the next row.",
            show_alert=True,
        )
        return

    new_row = session.current_row_index + 1
    await db.update_session_row(session.session_id, new_row)
    await callback.answer(f"Moved to Row #{new_row}")

    new_row_msg = (
        f"➡️ <b>Advanced to Row #{new_row} (Resident {new_row})</b>\n\n"
        f"Send photos (single/album) or text notes for Resident {new_row}:"
    )
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            new_row_msg,
            reply_markup=get_raw_row_control_keyboard(new_row),
        )


@router.callback_query(F.data == "raw:undo_last")
async def handle_undo_last(callback: CallbackQuery, state: FSMContext) -> None:
    """Undo the last added block or step back to the previous row if current row is empty."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    session = await db.get_session(session_id) if session_id else None
    if not session:
        session = await db.get_active_session(callback.from_user.id)

    if not session:
        await callback.answer("No active session found.", show_alert=True)
        return

    removed_block, resulting_row = await db.undo_last_block(
        session.session_id, session.current_row_index
    )

    if removed_block:
        # Delete file from disk if it was an image
        if removed_block.file_path:
            try:
                Path(removed_block.file_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to delete undone image %s: %s", removed_block.file_path, e)
        alert_msg = f"↩️ Removed last block ({removed_block.block_type}) from Row #{resulting_row}."
    elif resulting_row < session.current_row_index:
        alert_msg = f"↩️ Current row was empty. Stepped back to Row #{resulting_row}."
    else:
        alert_msg = f"Row #{resulting_row} is already empty."

    await callback.answer(alert_msg)

    # Refresh row status
    blocks = await db.get_blocks_for_row(session.session_id, resulting_row)
    summary_text = format_row_summary(resulting_row, blocks)

    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                summary_text,
                reply_markup=get_raw_row_control_keyboard(resulting_row),
            )
        except Exception:
            await callback.message.answer(
                summary_text,
                reply_markup=get_raw_row_control_keyboard(resulting_row),
            )


@router.callback_query(F.data == "raw:clear_row")
async def handle_clear_row(callback: CallbackQuery, state: FSMContext) -> None:
    """Clear all blocks in the current row."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    session = await db.get_session(session_id) if session_id else None
    if not session:
        session = await db.get_active_session(callback.from_user.id)

    if not session:
        await callback.answer("No active session found.", show_alert=True)
        return

    cleared_blocks = await db.clear_row(session.session_id, session.current_row_index)
    for b in cleared_blocks:
        if b.file_path:
            try:
                Path(b.file_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to remove cleared file %s: %s", b.file_path, e)

    await callback.answer(f"🗑️ Cleared {len(cleared_blocks)} block(s) from Row #{session.current_row_index}.")

    summary_text = format_row_summary(session.current_row_index, [])
    if callback.message and isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                summary_text,
                reply_markup=get_raw_row_control_keyboard(session.current_row_index),
            )
        except Exception:
            await callback.message.answer(
                summary_text,
                reply_markup=get_raw_row_control_keyboard(session.current_row_index),
            )


@router.callback_query(F.data == "raw:cancel")
async def handle_cancel_session(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel the active raw data entry session."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    if session_id:
        await db.set_session_status(session_id, "CANCELLED")

    await state.clear()
    await callback.answer("Session cancelled.")

    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "❌ Raw data entry session has been cancelled. Back to main menu.",
            reply_markup=get_main_menu_keyboard(),
        )


@router.callback_query(F.data == "raw:finish")
async def handle_finish_export(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Compile the session into a cell-anchored .xlsx spreadsheet and send to user."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    session = await db.get_session(session_id) if session_id else None
    if not session:
        session = await db.get_active_session(callback.from_user.id)

    if not session:
        await callback.answer("No active session found.", show_alert=True)
        return

    all_blocks = await db.get_blocks_for_session(session.session_id)
    if not all_blocks:
        await callback.answer(
            "Cannot export an empty session! Add at least one photo or text block first.",
            show_alert=True,
        )
        return

    await callback.answer("Preparing your Excel spreadsheet...")
    if callback.message and isinstance(callback.message, Message):
        progress_msg = await callback.message.answer(
            "⏳ <b>Generating cell-anchored raw Excel spreadsheet...</b>\n"
            "Resizing photos and embedding strictly into worksheet cells..."
        )
    else:
        progress_msg = None

    # Build workbook
    session_dir = settings.SESSIONS_DIR / session.session_id
    output_xlsx = session_dir / f"raw_transactions_{session.session_id}.xlsx"

    builder = ExcelBuilder(max_dimension_px=settings.MAX_IMAGE_DIMENSION_PX)
    try:
        builder.build_raw_workbook(
            session_id=session.session_id,
            blocks=all_blocks,
            output_path=output_xlsx,
        )
    except Exception as e:
        logger.exception("Failed to build raw Excel workbook: %s", e)
        if progress_msg:
            await progress_msg.edit_text(f"❌ Failed to generate spreadsheet: {e}")
        return

    # Count statistics
    total_images = sum(1 for b in all_blocks if b.block_type == "IMAGE")
    total_texts = sum(1 for b in all_blocks if b.block_type == "TEXT")
    unique_rows = len(set(b.row_index for b in all_blocks))

    caption = (
        "✅ <b>Raw Data Export Complete!</b>\n\n"
        f"📊 <b>Summary:</b>\n"
        f"• Total Resident Rows: <b>{unique_rows}</b>\n"
        f"• Total Embedded Images: <b>{total_images}</b>\n"
        f"• Total Text Notes: <b>{total_texts}</b>\n\n"
        "📎 Sheet 1 (<code>Raw_Transactions</code>): Each resident is in their own row, "
        "with receipt images strictly anchored inside cell boundaries.\n"
        "📎 Sheet 2 (<code>_AI_EXTRACTION_GUIDE</code>): Instructions and 15-line Python snippet "
        "for AI Code Interpreters to inspect <code>ws._images</code> and extract receipts.\n\n"
        "You can now process this file in your AI chatbot, then upload the cleaned result here!"
    )

    doc_file = FSInputFile(str(output_xlsx), filename=f"raw_dormitory_log_{session.session_id}.xlsx")
    await bot.send_document(
        chat_id=callback.message.chat.id if callback.message else callback.from_user.id,
        document=doc_file,
        caption=caption,
        reply_markup=get_main_menu_keyboard(),
    )

    # Mark completed in DB
    await db.set_session_status(session.session_id, "COMPLETED")
    await state.clear()

    if progress_msg:
        try:
            await progress_msg.delete()
        except Exception:
            pass


@router.message(RawDataStates.collecting_row)
async def handle_collecting_row_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    album: Optional[List[Message]] = None,
) -> None:
    """Accept photos (single or album), captions, and text notes for the current row."""
    data = await state.get_data()
    session_id = data.get("session_id")
    db = get_db()

    session: Optional[SessionRecord] = None
    if session_id:
        session = await db.get_session(session_id)
    if not session:
        session = await db.get_active_session(message.from_user.id if message.from_user else 0)
        if session:
            await state.update_data(session_id=session.session_id)

    if not session:
        await message.answer(
            "⚠️ No active raw entry session found. Please tap '📸 Start Raw Data Entry'.",
            reply_markup=get_main_menu_keyboard(),
        )
        await state.clear()
        return

    session_dir = settings.SESSIONS_DIR / session.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    r_idx = session.current_row_index

    # 1. Handle Album (Media Group)
    if album:
        logger.info("Processing album of %d items for Row #%d", len(album), r_idx)
        for msg in album:
            if msg.photo:
                photo_obj = msg.photo[-1]
                file_uuid = uuid.uuid4().hex[:6]
                dest_path = session_dir / f"row_{r_idx}_{file_uuid}.jpg"
                await bot.download(photo_obj, destination=dest_path)
                await db.add_block(
                    session_id=session.session_id,
                    row_index=r_idx,
                    block_type="IMAGE",
                    file_path=str(dest_path),
                )
            if msg.caption and msg.caption.strip():
                await db.add_block(
                    session_id=session.session_id,
                    row_index=r_idx,
                    block_type="TEXT",
                    text_content=msg.caption.strip(),
                )

    # 2. Handle Single Photo
    elif message.photo:
        photo_obj = message.photo[-1]
        file_uuid = uuid.uuid4().hex[:6]
        dest_path = session_dir / f"row_{r_idx}_{file_uuid}.jpg"
        await bot.download(photo_obj, destination=dest_path)
        await db.add_block(
            session_id=session.session_id,
            row_index=r_idx,
            block_type="IMAGE",
            file_path=str(dest_path),
        )
        # If photo WITH caption, automatically append caption as TEXT block in next column
        if message.caption and message.caption.strip():
            await db.add_block(
                session_id=session.session_id,
                row_index=r_idx,
                block_type="TEXT",
                text_content=message.caption.strip(),
            )

    # 3. Handle Document (Image fallback)
    elif message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        file_name = (doc.file_name or "").lower()
        is_image = mime.startswith("image/") or file_name.endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        )

        if is_image:
            file_uuid = uuid.uuid4().hex[:6]
            ext = Path(doc.file_name or "img.jpg").suffix or ".jpg"
            dest_path = session_dir / f"row_{r_idx}_{file_uuid}{ext}"
            await bot.download(doc, destination=dest_path)
            await db.add_block(
                session_id=session.session_id,
                row_index=r_idx,
                block_type="IMAGE",
                file_path=str(dest_path),
            )
            if message.caption and message.caption.strip():
                await db.add_block(
                    session_id=session.session_id,
                    row_index=r_idx,
                    block_type="TEXT",
                    text_content=message.caption.strip(),
                )
        else:
            await message.answer(
                "⚠️ Document is not a supported image. Please send JPG/PNG receipts or text notes."
            )
            return

    # 4. Handle Text Message
    elif message.text:
        await db.add_block(
            session_id=session.session_id,
            row_index=r_idx,
            block_type="TEXT",
            text_content=message.text.strip(),
        )

    # 5. Unsupported media
    else:
        await message.answer(
            "⚠️ Unsupported input format. Please send photos, photos with captions, or text notes."
        )
        return

    # Render updated live summary
    blocks = await db.get_blocks_for_row(session.session_id, r_idx)
    summary_text = format_row_summary(r_idx, blocks)
    await message.answer(summary_text, reply_markup=get_raw_row_control_keyboard(r_idx))

