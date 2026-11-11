"""Common bot commands and entrypoint handlers (/start, /help, /cancel, main menu)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.keyboards import (
    BTN_HELP,
    BTN_START_RAW,
    BTN_UPLOAD_CLEANED,
    get_main_menu_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="common_router")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    """Handle /start command with system introduction and persistent main menu."""
    await state.clear()
    welcome_text = (
        "👋 <b>Welcome to the Dormitory Financial Assistant Bot!</b>\n\n"
        "This bot streamlines digitizing daily dormitory transactions from paper notebooks "
        "and POS receipts into cell-anchored Excel spreadsheets and syncing them with your "
        "Dormitory Management System.\n\n"
        "<b>Core Operations:</b>\n"
        "1️⃣ <b>📸 Start Raw Data Entry:</b> Group photos and notes row-by-row for each resident. "
        "Exports a cell-anchored <code>.xlsx</code> ready for AI Code Interpreter.\n"
        "2️⃣ <b>📥 Upload Cleaned .xlsx to System:</b> Upload the cleaned spreadsheet, review "
        "a dry-run preview, customize agent instructions, and post transactions.\n\n"
        "Choose an option below to begin:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def handle_help(message: Message) -> None:
    """Handle /help command or Help button."""
    help_text = (
        "📖 <b>Dormitory Bot Guide & Instructions</b>\n\n"
        "<b>📸 1. Raw Data Collection Workflow:</b>\n"
        "• Tap <b>'Start Raw Data Entry'</b> or use <code>/raw_data</code>.\n"
        "• Send receipts, transfer screenshots, or text notes for <b>Row #1 (Resident 1)</b>.\n"
        "• You can send single photos, albums of multiple photos, or photos with captions.\n"
        "• If a photo has a caption, the photo is placed in Column C and the caption automatically "
        "in Column C+1!\n"
        "• Use <b>➕ Next Resident</b> to proceed to the next row (Resident 2, 3, etc.).\n"
        "• Use <b>↩️ Undo</b> to remove the last block, or <b>🗑️ Clear Row</b> to reset the row.\n"
        "• Tap <b>✅ Finish & Export .xlsx</b> to receive the generated workbook with cell-anchored "
        "photos and an AI Code Interpreter extraction script.\n\n"
        "<b>📥 2. Cleaned .xlsx Ingestion Workflow:</b>\n"
        "• Tap <b>'Upload Cleaned .xlsx to System'</b> or send any <code>.xlsx</code> file.\n"
        "• Review the dry-run preview showing column names, row counts, and sample entries.\n"
        "• Tap <b>✏️ Edit/Add Custom Instructions</b> to tailor how the AI Agent categorizes rent vs deposits.\n"
        "• Tap <b>🚀 Confirm & Send</b> to execute the ingestion with idempotency and duplicate checking.\n"
        "• If any rows fail validation, an error report spreadsheet will be generated automatically.\n\n"
        "<i>Use /cancel at any time to return to the main menu.</i>"
    )
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    """Handle /cancel command to clear active FSM state."""
    current_state = await state.get_state()
    await state.clear()
    if current_state:
        await message.answer(
            "🛑 Current operation cancelled. You are back at the main menu.",
            reply_markup=get_main_menu_keyboard(),
        )
    else:
        await message.answer(
            "ℹ️ No active operation was running. Main menu is ready.",
            reply_markup=get_main_menu_keyboard(),
        )

