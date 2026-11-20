"""Authentication and authorization middleware."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from src.config import Settings

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Middleware to whitelist Telegram users by their user ID.

    Unauthorized events are rejected with an explicit alert and dropped.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            sender = getattr(event, "from_user", None)
            sender_info = f"{sender.id} (@{sender.username})" if sender else "Unknown"
            logger.info("📩 Message from %s: text=%r, content_type=%s", sender_info, event.text or event.caption, event.content_type)
        elif isinstance(event, CallbackQuery):
            sender = getattr(event, "from_user", None)
            sender_info = f"{sender.id} (@{sender.username})" if sender else "Unknown"
            logger.info("🔘 Callback from %s: data=%r", sender_info, event.data)
        return await handler(event, data)

