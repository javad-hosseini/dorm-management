"""Media group (album) aggregation middleware with debounce."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)


class AlbumMiddleware(BaseMiddleware):
    """Aggregates multiple messages belonging to the same media group (album) into a single event.

    Uses an asynchronous debounce delay (default: 0.6 seconds) so that all images sent
    in an album are captured together, preventing race conditions and multiple replies.
    """

    def __init__(self, latency: float = 0.6) -> None:
        super().__init__()
        self.latency = latency
        self.albums: Dict[str, List[Message]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        media_group_id = event.media_group_id
        if not media_group_id:
            # Single message, normal processing
            return await handler(event, data)

        if media_group_id in self.albums:
            # Subsequent message in the same media group; append and drop execution for this update
            self.albums[media_group_id].append(event)
            return None

        # First message for this media group; register and sleep for debounce duration
        self.albums[media_group_id] = [event]
        await asyncio.sleep(self.latency)

        # Retrieve all collected messages for this media group
        album_messages = self.albums.pop(media_group_id, [])
        data["album"] = album_messages

        return await handler(event, data)

