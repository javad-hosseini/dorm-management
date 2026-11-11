"""Unit tests for AuthMiddleware whitelist and AlbumMiddleware media group debouncing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import CallbackQuery, Message, User

from src.config import Settings
from src.middlewares.album import AlbumMiddleware
from src.middlewares.auth import AuthMiddleware


@pytest.mark.asyncio
async def test_auth_middleware_whitelisted_user():
    """Verify whitelisted user (111111) is allowed through to the downstream handler."""
    settings = Settings(ALLOWED_TELEGRAM_USER_IDS=[111111, 222222])
    middleware = AuthMiddleware(settings)

    handler = AsyncMock(return_value="DOWNSTREAM_OK")
    user = User(id=111111, is_bot=False, first_name="WhitelistedManager")
    message = MagicMock(spec=Message)
    message.from_user = user

    result = await middleware(handler, message, {"event_from_user": user})
    assert result == "DOWNSTREAM_OK"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_middleware_unauthorized_user():
    """Verify unauthorized user (999999) is blocked, replied with rejection alert, and event dropped."""
    settings = Settings(ALLOWED_TELEGRAM_USER_IDS=[111111, 222222])
    middleware = AuthMiddleware(settings)

    handler = AsyncMock(return_value="DOWNSTREAM_OK")
    user = User(id=999999, is_bot=False, first_name="Stranger")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.answer = AsyncMock()

    result = await middleware(handler, message, {"event_from_user": user})
    assert result is None
    handler.assert_not_awaited()

    message.answer.assert_awaited_once()
    args, _ = message.answer.call_args
    assert "⛔ Unauthorized access" in args[0]
    assert "999999" in args[0]


@pytest.mark.asyncio
async def test_auth_middleware_unauthorized_callback():
    """Verify unauthorized callback query is blocked with show_alert=True."""
    settings = Settings(ALLOWED_TELEGRAM_USER_IDS=[111111, 222222])
    middleware = AuthMiddleware(settings)

    handler = AsyncMock(return_value="DOWNSTREAM_OK")
    user = User(id=999999, is_bot=False, first_name="Stranger")
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = user
    cb.answer = AsyncMock()

    result = await middleware(handler, cb, {"event_from_user": user})
    assert result is None
    handler.assert_not_awaited()

    cb.answer.assert_awaited_once()
    _, kwargs = cb.answer.call_args
    assert kwargs.get("show_alert") is True


@pytest.mark.asyncio
async def test_album_middleware_three_photos_aggregated():
    """Simulate 3 messages in media_group arriving within 50ms; assert handler called ONCE with all 3."""
    # Use small test latency (0.05s) for high performance
    middleware = AlbumMiddleware(latency=0.05)
    handler = AsyncMock(return_value="ALBUM_HANDLED")

    m1 = MagicMock(spec=Message)
    m1.message_id = 1
    m1.media_group_id = "album_123"

    m2 = MagicMock(spec=Message)
    m2.message_id = 2
    m2.media_group_id = "album_123"

    m3 = MagicMock(spec=Message)
    m3.message_id = 3
    m3.media_group_id = "album_123"

    data = {}

    # Launch concurrent arrivals spaced by 10ms
    async def send_burst():
        t1 = asyncio.create_task(middleware(handler, m1, data))
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(middleware(handler, m2, data))
        await asyncio.sleep(0.01)
        t3 = asyncio.create_task(middleware(handler, m3, data))
        return await asyncio.gather(t1, t2, t3)

    results = await send_burst()

    # m2 and m3 must return None (suppressed)
    assert results[1] is None
    assert results[2] is None
    # m1 must return handler output
    assert results[0] == "ALBUM_HANDLED"

    handler.assert_awaited_once()
    assert "album" in data
    assert len(data["album"]) == 3
    assert [m.message_id for m in data["album"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_album_middleware_single_message_passthrough():
    """Verify single photo message (no media_group_id) passes through immediately."""
    middleware = AlbumMiddleware(latency=0.05)
    handler = AsyncMock(return_value="SINGLE_OK")

    msg = MagicMock(spec=Message)
    msg.media_group_id = None

    data = {}
    result = await middleware(handler, msg, data)

    assert result == "SINGLE_OK"
    handler.assert_awaited_once()
    assert "album" not in data

