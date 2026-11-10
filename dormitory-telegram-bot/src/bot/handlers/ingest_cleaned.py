"""Feature 2: Cleaned .xlsx ingestion, dry-run preview, instruction editing, and backend/agent sync."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, FSInputFile, Message

from src.bot.keyboards import (
    BTN_UPLOAD_CLEANED,
    get_cancel_keyboard,
    get_ingest_duplicate_keyboard,
    get_ingest_preview_keyboard,
    get_main_menu_keyboard,
)
from src.bot.states import IngestStates, RawDataStates
from src.config import settings
from src.database.repository import get_db
from src.services.dormitory_client import get_dormitory_client
from src.services.excel_parser import ExcelParser, ParsedSheetData

logger = logging.getLogger(__name__)

router = Router(name="ingest_cleaned_router")


def format_preview_message(
    sheet_data: ParsedSheetData,
    instructions: str,
    target_path: Path,
    duplicate_count: int = 0,
) -> str:
    """Format dry-run preview details for the cleaned spreadsheet."""
    cols_display = ", ".join(f"<code>{c}</code>" for c in sheet_data.headers[:6])
    if len(sheet_data.headers) > 6:
        cols_display += f" ... (+{len(sheet_data.headers) - 6} more)"

    # Format sample of row 1 & row 2
    sample_rows = sheet_data.rows[:2]
    sample_text = ""
    for idx, r in enumerate(sample_rows, start=1):
        sample_json = json.dumps(r, indent=2, ensure_ascii=False)
        sample_text += f"<b>Row {idx}:</b>\n<pre>{sample_json}</pre>\n"

    instr_preview = instructions.strip()
    if len(instr_preview) > 300:
        instr_preview = instr_preview[:295] + "..."

    dup_alert = ""
    if duplicate_count > 0:
        dup_alert = (
            f"\n⚠️ <b>Duplicate Warning:</b> Found <b>{duplicate_count}</b> previously "
            "ingested row(s) in this file based on row signatures.\n"
        )

    mode_info = ""
    if settings.INGESTION_MODE == "file_dropzone":
        mode_info = (
            f"📂 <b>Target Server Path:</b> <code>{target_path}</code>\n"
            "⚡ <b>Mode:</b> Local Drop-Zone (No external API calls; ready for Antigravity CLI)\n"
        )
    else:
        mode_info = f"🚀 <b>Mode:</b> {settings.INGESTION_MODE}\n"

    return (
        "📋 <b>Spreadsheet Received & Analyzed</b>\n\n"
        f"📁 <b>File:</b> <code>{sheet_data.file_name}</code>\n"
        f"📑 <b>Sheet:</b> <code>{sheet_data.sheet_name}</code>\n"
        f"📊 <b>Total Rows:</b> <b>{len(sheet_data.rows)}</b>\n"
        f"🏷️ <b>Columns:</b> {cols_display}\n"
        f"{mode_info}"
        f"{dup_alert}\n"
        "🔍 <b>Sample Data:</b>\n"
        f"{sample_text}\n"
        "📝 <b>Instructions for Antigravity CLI:</b>\n"
        f"<i>\"{instr_preview}\"</i>\n\n"
        "Choose an action to proceed:"
    )


@router.message(Command("ingest_cleaned"))
@router.message(F.text == BTN_UPLOAD_CLEANED)
async def prompt_upload_cleaned_file(message: Message, state: FSMContext) -> None:
    """Prompt user to upload the cleaned Excel file."""
    await state.set_state(IngestStates.waiting_for_file)
    upload_dir = settings.SPREADSHEET_UPLOAD_DIR
    text = (
        "📥 <b>Upload Cleaned Spreadsheet (Drop-Zone)</b>\n\n"
        f"Please send the cleaned <code>.xlsx</code> file as a document.\n"
        f"The bot will place it into: <code>{upload_dir}</code>.\n\n"
        "<i>Tip: You can include custom instructions in the document caption! "
        "They will be saved alongside the spreadsheet for Antigravity CLI.</i>"
    )
    await message.answer(text, reply_markup=get_cancel_keyboard("ingest:cancel"))


@router.message(F.document)
async def handle_uploaded_document(message: Message, state: FSMContext, bot: Bot) -> None:
    """Handle uploaded documents; automatically detect .xlsx files outside raw sessions."""
    current_state = await state.get_state()
    # If the user is currently entering raw photo/text data in Row #X, let raw_data handler take care of it
    if current_state == RawDataStates.collecting_row.state:
        return

    doc: Optional[Document] = message.document
    if not doc:
        return

    file_name = doc.file_name or "cleaned_transactions.xlsx"
    if not file_name.lower().endswith(".xlsx"):
        # If explicitly waiting for file, alert user
        if current_state == IngestStates.waiting_for_file.state:
            await message.answer(
                "⚠️ Invalid file format. Please upload an Excel file ending with <code>.xlsx</code>."
            )
        return

    progress_msg = await message.answer("⏳ <b>Receiving and placing .xlsx file into drop-zone...</b>")

    target_dir = settings.SPREADSHEET_UPLOAD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / file_name

    try:
        await bot.download(doc, destination=target_file)
        parser = ExcelParser()
        sheet_data = parser.parse_cleaned_workbook(target_file, original_file_name=file_name)

        if not sheet_data.rows:
            await progress_msg.edit_text(
                "❌ The uploaded spreadsheet contains no data rows or only empty cells."
            )
            return

        # Check for instructions in caption, fallback to default instructions
        instructions = ""
        if message.caption and message.caption.strip():
            instructions = message.caption.strip()
        else:
            instructions = settings.get_effective_default_instructions()

        # Save companion instructions file for Antigravity CLI
        stem_name = Path(file_name).stem
        instr_file = target_dir / f"{stem_name}_instructions.md"
        instr_file.write_text(instructions, encoding="utf-8")

        # Check duplicates in DB
        db = get_db()
        existing_hashes = await db.check_row_hashes(sheet_data.row_hashes)
        duplicate_count = len(existing_hashes)

        # Store in FSM
        await state.set_state(
            IngestStates.handling_duplicates
            if duplicate_count > 0
            else IngestStates.preview_and_confirm
        )
        await state.update_data(
            file_path=str(target_file),
            file_name=sheet_data.file_name,
            file_hash=sheet_data.file_hash,
            sheet_name=sheet_data.sheet_name,
            headers=sheet_data.headers,
            rows=sheet_data.rows,
            row_hashes=sheet_data.row_hashes,
            instructions=instructions,
            duplicate_hashes=list(existing_hashes),
        )

        preview_msg = format_preview_message(
            sheet_data, instructions, target_file, duplicate_count
        )
        keyboard = (
            get_ingest_duplicate_keyboard()
            if duplicate_count > 0
            else get_ingest_preview_keyboard()
        )

        await progress_msg.edit_text(preview_msg, reply_markup=keyboard)

    except Exception as e:
        logger.exception("Error processing uploaded .xlsx: %s", e)
        await progress_msg.edit_text(f"❌ Failed to process spreadsheet: {e}")


@router.callback_query(F.data == "ingest:edit_instructions")
async def handle_edit_instructions(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to submit replacement instructions for the agent."""
    await state.set_state(IngestStates.editing_instructions)
    await callback.answer()
    if callback.message and isinstance(callback.message, Message):
        await callback.message.answer(
            "✏️ <b>Enter Custom Instructions</b>\n\n"
            "Please type your custom instructions for the Dormitory AI Agent in your next message:",
            reply_markup=get_cancel_keyboard("ingest:cancel"),
        )


@router.message(IngestStates.editing_instructions)
async def handle_new_instructions_text(message: Message, state: FSMContext) -> None:
    """Save new custom instructions, update companion file, and re-render the preview."""
    if not message.text:
        await message.answer("Please send instructions as text.")
        return

    new_instructions = message.text.strip()
    data = await state.get_data()
    file_path = Path(data.get("file_path", ""))
    if file_path.exists():
        # Update companion instructions file for Antigravity CLI
        instr_file = file_path.parent / f"{file_path.stem}_instructions.md"
        instr_file.write_text(new_instructions, encoding="utf-8")

    await state.update_data(instructions=new_instructions)
    await state.set_state(IngestStates.preview_and_confirm)

    # Reconstruct sheet data from FSM
    sheet_data = ParsedSheetData(
        file_name=data.get("file_name", "cleaned.xlsx"),
        file_hash=data.get("file_hash", ""),
        sheet_name=data.get("sheet_name", "Sheet1"),
        headers=data.get("headers", []),
        rows=data.get("rows", []),
        row_hashes=data.get("row_hashes", []),
    )
    dup_hashes = data.get("duplicate_hashes", [])

    preview_msg = format_preview_message(
        sheet_data, new_instructions, file_path, len(dup_hashes)
    )
    keyboard = (
        get_ingest_duplicate_keyboard() if dup_hashes else get_ingest_preview_keyboard()
    )
    await message.answer(preview_msg, reply_markup=keyboard)


@router.callback_query(F.data.in_(["ingest:confirm", "ingest:skip_duplicates", "ingest:force_duplicates"]))
async def handle_confirm_ingestion(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    """Execute ingestion into the Dormitory System or place into drop-zone for Antigravity CLI."""
    action = callback.data
    data = await state.get_data()

    rows: List[Dict[str, Any]] = data.get("rows", [])
    row_hashes: List[str] = data.get("row_hashes", [])
    headers: List[str] = data.get("headers", [])
    instructions: str = data.get("instructions", "")
    dup_hashes_set = set(data.get("duplicate_hashes", []))
    file_name: str = data.get("file_name", "cleaned.xlsx")
    file_path = data.get("file_path", str(settings.SPREADSHEET_UPLOAD_DIR / file_name))
    user_id = callback.from_user.id

    if not rows:
        await callback.answer("No transaction rows found to ingest.", show_alert=True)
        return

    # Filter out duplicates if requested
    rows_to_process: List[Dict[str, Any]] = []
    hashes_to_process: List[str] = []

    if action == "ingest:skip_duplicates":
        for r, h in zip(rows, row_hashes):
            if h not in dup_hashes_set:
                rows_to_process.append(r)
                hashes_to_process.append(h)
    else:
        rows_to_process = rows
        hashes_to_process = row_hashes

    if not rows_to_process:
        await callback.answer("All rows were duplicates and have been skipped.", show_alert=True)
        if callback.message and isinstance(callback.message, Message):
            await callback.message.edit_text(
                "⏩ All rows in this file are existing duplicates and were skipped.\nNo new records were posted.",
                reply_markup=get_main_menu_keyboard(),
            )
        await state.clear()
        return

    await callback.answer("Processing file...")
    status_msg = None
    if callback.message and isinstance(callback.message, Message):
        status_msg = await callback.message.edit_text(
            f"🚀 <b>Placing spreadsheet into drop-zone ({settings.INGESTION_MODE})...</b>\n"
            f"Processing <b>{len(rows_to_process)}</b> transactions..."
        )

    # Invoke client
    client = get_dormitory_client(settings)
    results = await client.process_rows(rows_to_process, hashes_to_process, instructions)

    # Persist in SQLite
    db = get_db()
    failed_rows: List[Tuple[Dict[str, Any], str]] = []
    succeeded_count = 0

    for res, row_data in zip(results, rows_to_process):
        status_str = "SUCCESS" if res.success else "FAILED"
        if res.success:
            succeeded_count += 1
        else:
            failed_rows.append((row_data, res.error_message or "Unknown error"))

        await db.record_ingested_transaction(
            row_hash=res.row_hash,
            file_name=file_name,
            row_index=res.row_index,
            data_json=json.dumps(row_data, ensure_ascii=False),
            status=status_str,
            error_message=res.error_message,
            user_id=user_id,
        )

    failed_count = len(failed_rows)

    summary_text = (
        "🏁 <b>Spreadsheet Ready on Server!</b>\n\n"
        f"📊 <b>Summary:</b>\n"
        f"• ✅ <b>Tracked:</b> {succeeded_count} rows\n"
        f"• ❌ <b>Failed:</b> {failed_count} rows\n\n"
    )

    if settings.INGESTION_MODE == "file_dropzone":
        summary_text += (
            f"📁 <b>Saved File:</b> <code>{file_path}</code>\n"
            f"📝 <b>Instructions File:</b> <code>{Path(file_path).stem}_instructions.md</code>\n\n"
            "💻 <b>Ready for Antigravity CLI!</b>\n"
            "You can now run in the project terminal:\n"
            f"<code>agy \"Check {file_name} in {settings.SPREADSHEET_UPLOAD_DIR} and insert clean transactions into SQLite\"</code>"
        )
        if status_msg:
            await status_msg.edit_text(summary_text, reply_markup=get_main_menu_keyboard())
    elif failed_count == 0:
        summary_text += "🎉 All transactions were verified and posted successfully!"
        if status_msg:
            await status_msg.edit_text(summary_text, reply_markup=get_main_menu_keyboard())
    else:
        summary_text += (
            "⚠️ Some rows could not be posted. An error report spreadsheet is attached below "
            "with exact failure reasons so you can correct and re-upload them."
        )
        if status_msg:
            await status_msg.edit_text(summary_text)

        # Generate failed rows report
        parser = ExcelParser()
        report_dir = settings.DATA_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"failed_rows_{uuid.uuid4().hex[:8]}.xlsx"

        parser.generate_failed_rows_report(
            headers=headers,
            failed_items=failed_rows,
            output_path=report_path,
        )

        doc = FSInputFile(str(report_path), filename="failed_rows_report.xlsx")
        chat_id = callback.message.chat.id if callback.message else callback.from_user.id
        await bot.send_document(
            chat_id=chat_id,
            document=doc,
            caption="📄 <b>Failed Transactions Report:</b> Contains only failed rows and error reasons.",
            reply_markup=get_main_menu_keyboard(),
        )

    await state.clear()


@router.callback_query(F.data == "ingest:cancel")
async def handle_cancel_ingestion(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel cleaned Excel ingestion flow."""
    await state.clear()
    await callback.answer("Ingestion cancelled.")
    if callback.message and isinstance(callback.message, Message):
        await callback.message.edit_text(
            "❌ Ingestion cancelled. Returned to main menu.",
            reply_markup=get_main_menu_keyboard(),
        )
