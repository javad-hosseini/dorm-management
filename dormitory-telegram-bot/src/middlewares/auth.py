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
        user: User | None = data.get("event_from_user")
        if user is None and hasattr(event, "from_user"):
            user = getattr(event, "from_user", None)

        if user is None:
            # System event or internal update without user context
            return await handler(event, data)

        allowed_ids = self.settings.ALLOWED_TELEGRAM_USER_IDS

        # If whitelist is empty, we permit access or enforce strictness?
        # Specification requires: "checks event.from_user.id against settings.ALLOWED_TELEGRAM_USER_IDS
        # If an unauthorized user interacts with the bot, reply with '⛔ Unauthorized access...'"
        if allowed_ids and user.id not in allowed_ids:
            logger.warning(
                "Access denied for unauthorized user ID: %s (@%s)",
                user.id,
                user.username,
            )
            rejection_text = (
                f"⛔ Unauthorized access. Your User ID ({user.id}) is not whitelisted."
            )

            if isinstance(event, Message):
                await event.answer(rejection_text)
            elif isinstance(event, CallbackQuery):
                await event.answer(rejection_text, show_alert=True)
            return None

        return await handler(event, data)

