"""Shared pytest fixtures for the Dormitory Telegram Bot test suite."""

from __future__ import annotations

import io
from pathlib import Path
from typing import AsyncGenerator, Callable, Optional
from unittest.mock import AsyncMock, MagicMock

import openpyxl
import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Chat, Document, Message, PhotoSize, User
from PIL import Image as PILImage, ImageDraw

from src.config import Settings
from src.database.repository import DatabaseRepository


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Provide isolated application settings using temporary directories."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = data_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "test_dormitory.db"

    return Settings(
        BOT_TOKEN="123456789:TEST_MOCK_TOKEN_ABC1234def",
        ALLOWED_TELEGRAM_USER_IDS=[111111, 222222],
        DATA_DIR=data_dir,
        DB_PATH=db_path,
        SESSIONS_DIR=sessions_dir,
        SPREADSHEET_UPLOAD_DIR=tmp_path / "incoming_spreadsheets",
        MAX_IMAGE_DIMENSION_PX=320,
        CLEANUP_TEMP_FILES_ON_FINISH=False,
        INGESTION_MODE="file_dropzone",
    )


@pytest.fixture
async def db_repo(test_settings: Settings) -> AsyncGenerator[DatabaseRepository, None]:
    """Initialize an isolated async SQLite repository in tmp_path."""
    repo = DatabaseRepository(test_settings.DB_PATH)
    await repo.init_db()
    yield repo


@pytest.fixture
def synthetic_receipt_image(tmp_path: Path) -> Path:
    """Generate a realistic 1200x1600 RGB JPEG receipt image on disk."""
    image_path = tmp_path / "synthetic_receipt_1200x1600.jpg"
    img = PILImage.new("RGB", (1200, 1600), color=(250, 250, 248))
    draw = ImageDraw.Draw(img)

    # Draw header lines resembling a POS receipt
    draw.rectangle([100, 80, 1100, 180], fill=(220, 220, 220))
    draw.rectangle([150, 300, 1050, 340], fill=(50, 50, 50))
    draw.rectangle([150, 400, 850, 430], fill=(80, 80, 80))
    draw.rectangle([150, 500, 950, 530], fill=(80, 80, 80))
    draw.rectangle([150, 650, 1050, 700], fill=(20, 20, 20))

    img.save(image_path, format="JPEG", quality=95)
    return image_path


@pytest.fixture
def mock_bot(synthetic_receipt_image: Path) -> AsyncMock:
    """Create a fully-mocked aiogram.Bot capable of downloading test images."""
    bot = AsyncMock(spec=Bot)
    bot.id = 123456789

    receipt_bytes = synthetic_receipt_image.read_bytes()

    async def mock_download(file, destination=None, timeout=None, chunk_size=None):
        if destination is not None:
            if isinstance(destination, (str, Path)):
                dest_path = Path(destination)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(receipt_bytes)
                return dest_path
            elif hasattr(destination, "write"):
                destination.write(receipt_bytes)
                return destination
        buf = io.BytesIO(receipt_bytes)
        return buf

    bot.download = AsyncMock(side_effect=mock_download)
    bot.download_file = AsyncMock(side_effect=mock_download)
    bot.send_document = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def fsm_context() -> FSMContext:
    """Provide a real FSMContext backed by MemoryStorage."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=123456789, chat_id=111111, user_id=111111)
    return FSMContext(storage=storage, key=key)


@pytest.fixture
def make_message() -> Callable[..., Message]:
    """Factory fixture creating realistic aiogram.types.Message mocks."""

    def _factory(
        text: Optional[str] = None,
        photo: Optional[list[PhotoSize]] = None,
        document: Optional[Document] = None,
        caption: Optional[str] = None,
        user_id: int = 111111,
        chat_id: int = 111111,
        media_group_id: Optional[str] = None,
    ) -> Message:
        msg = AsyncMock(spec=Message)
        user = User(
            id=user_id,
            is_bot=False,
            first_name="TestManager",
            username="manager_test",
        )
        chat = Chat(id=chat_id, type="private")

        msg.message_id = 101
        msg.from_user = user
        msg.chat = chat
        msg.text = text
        msg.photo = photo
        msg.document = document
        msg.caption = caption
        msg.media_group_id = media_group_id

        # Async response mocks
        response_msg = AsyncMock(spec=Message)
        response_msg.message_id = 102
        response_msg.edit_text = AsyncMock(return_value=response_msg)
        response_msg.delete = AsyncMock()

        msg.answer = AsyncMock(return_value=response_msg)
        msg.edit_text = AsyncMock(return_value=response_msg)
        msg.reply = AsyncMock(return_value=response_msg)
        msg.answer_document = AsyncMock(return_value=response_msg)
        return msg

    return _factory


@pytest.fixture
def make_callback_query() -> Callable[..., CallbackQuery]:
    """Factory fixture creating realistic aiogram.types.CallbackQuery mocks."""

    def _factory(
        data: str,
        user_id: int = 111111,
        chat_id: int = 111111,
    ) -> CallbackQuery:
        cb = AsyncMock(spec=CallbackQuery)
        user = User(
            id=user_id,
            is_bot=False,
            first_name="TestManager",
            username="manager_test",
        )
        chat = Chat(id=chat_id, type="private")

        msg = AsyncMock(spec=Message)
        msg.message_id = 201
        msg.chat = chat
        msg.from_user = user
        msg.edit_text = AsyncMock(return_value=msg)
        msg.answer = AsyncMock(return_value=msg)

        cb.id = "cb_query_999"
        cb.from_user = user
        cb.data = data
        cb.message = msg
        cb.answer = AsyncMock()
        return cb

    return _factory


@pytest.fixture
def sample_cleaned_xlsx(tmp_path: Path) -> Path:
    """Create a sample cleaned transactions workbook."""
    file_path = tmp_path / "cleaned_dormitory_transactions.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cleaned_Transactions"

    ws.append(["Room", "Resident_Name", "Amount_IRR", "Transaction_Date", "Reference_Code", "Type"])
    ws.append([101, "Ali Hosseini", 4500000, "2026-11-04", "POS-987654", "RENT_PAYMENT"])
    ws.append([102, "Sara Karimi", 7500000, "2026-11-04", "CARD-123456", "SECURITY_DEPOSIT"])
    ws.append([205, "Reza Rad", 3000000, "2026-11-04", "CARD-554433", "RENT_PAYMENT"])

    wb.save(file_path)
    return file_path
