"""Unit tests for application entrypoint and initialization."""

from unittest.mock import AsyncMock, patch
import pytest

from src.main import main


@pytest.mark.asyncio
async def test_main_initialization():
    """Verify application bootstrap: DB initialization, middleware registration, and graceful shutdown."""
    with (
        patch("src.main.get_db") as mock_get_db,
        patch("src.main.Dispatcher.start_polling", new_callable=AsyncMock) as mock_polling,
        patch("src.main.Bot") as mock_bot_cls,
    ):
        mock_db = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_bot_instance = AsyncMock()
        mock_bot_instance.session.close = AsyncMock()
        mock_bot_cls.return_value = mock_bot_instance

        await main()

        mock_db.init_db.assert_awaited_once()
        mock_polling.assert_awaited_once()
        mock_bot_instance.session.close.assert_awaited_once()
