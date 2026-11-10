"""Middlewares package."""

from src.middlewares.album import AlbumMiddleware
from src.middlewares.auth import AuthMiddleware

__all__ = ["AlbumMiddleware", "AuthMiddleware"]

