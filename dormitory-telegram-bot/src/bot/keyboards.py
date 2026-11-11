"""Telegram keyboards (Reply and Inline) for navigation, row controls, and confirmation."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Text labels for Reply Keyboard commands
BTN_START_RAW = "📸 Start Raw Data Entry"
BTN_UPLOAD_CLEANED = "📥 Upload Cleaned .xlsx to System"
BTN_HELP = "ℹ️ Help & Instructions"


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Create the persistent bottom reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_START_RAW)],
            [KeyboardButton(text=BTN_UPLOAD_CLEANED)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def get_session_resume_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard shown when an unfinished raw session is detected."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Resume Existing Session",
                    callback_data="raw:resume",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Discard & Start Fresh",
                    callback_data="raw:discard",
                ),
            ],
        ]
    )


def get_raw_row_control_keyboard(current_row_index: int) -> InlineKeyboardMarkup:
    """Inline control keyboard attached to live row summaries in raw data entry."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"➕ Next Resident (Go to Row #{current_row_index + 1})",
                    callback_data="raw:next_row",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Undo Last Block",
                    callback_data="raw:undo_last",
                ),
                InlineKeyboardButton(
                    text=f"🗑️ Clear Row #{current_row_index}",
                    callback_data="raw:clear_row",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Finish & Export .xlsx",
                    callback_data="raw:finish",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel Session",
                    callback_data="raw:cancel",
                ),
            ],
        ]
    )


def get_ingest_preview_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for cleaned .xlsx ingestion dry-run preview."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Confirm & Place File for CLI",
                    callback_data="ingest:confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Edit/Add Custom Instructions",
                    callback_data="ingest:edit_instructions",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="ingest:cancel",
                ),
            ],
        ]
    )


def get_ingest_duplicate_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard when duplicates are detected during ingestion."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏩ Skip Duplicates",
                    callback_data="ingest:skip_duplicates",
                ),
                InlineKeyboardButton(
                    text="⚠️ Force Re-insert",
                    callback_data="ingest:force_duplicates",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="ingest:cancel",
                ),
            ],
        ]
    )


def get_cancel_keyboard(callback_data: str = "ingest:cancel") -> InlineKeyboardMarkup:
    """Single cancel button inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data=callback_data)]
        ]
    )

