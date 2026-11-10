"""Configuration management using Pydantic Settings."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Bot
    BOT_TOKEN: str = Field(
        default="123456789:ABCDefGhIJklMNopQRstUVwxyz_SAMPLE_TOKEN",
        description="Telegram Bot API Token from @BotFather",
    )
    ALLOWED_TELEGRAM_USER_IDS: list[int] = Field(
        default_factory=list,
        description="Comma-separated list of allowed Telegram user IDs",
    )
    TELEGRAM_PROXY_URL: Optional[str] = Field(
        default=None,
        description="Optional HTTP or SOCKS5 proxy URL for Telegram API (e.g. http://127.0.0.1:2080 or socks5://127.0.0.1:10808)",
    )

    # Storage paths
    DATA_DIR: Path = Field(
        default=Path("data"),
        description="Base directory for runtime data and databases",
    )
    DB_PATH: Path = Field(
        default=Path("data/dormitory_bot.db"),
        description="Path to SQLite database file",
    )
    SESSIONS_DIR: Path = Field(
        default=Path("data/sessions"),
        description="Directory for temporary raw data entry session files",
    )

    # Excel and Image Settings
    MAX_IMAGE_DIMENSION_PX: int = Field(
        default=320,
        description="Maximum width or height in pixels for embedded cell images",
    )
    CLEANUP_TEMP_FILES_ON_FINISH: bool = Field(
        default=False,
        description="Whether to delete raw photo files after generating the raw Excel spreadsheet",
    )

    # Spreadsheet SFTP / Drop-zone Destination (For Antigravity CLI manual processing)
    SPREADSHEET_UPLOAD_DIR: Path = Field(
        default=Path("incoming_spreadsheets"),
        description="Target server/project directory where uploaded Excel files are placed for manual Antigravity CLI processing",
    )
    OVERWRITE_EXISTING_FILES: bool = Field(
        default=True,
        description="Whether to overwrite existing files with the same name in SPREADSHEET_UPLOAD_DIR",
    )

    # Dormitory System Ingestion Settings
    INGESTION_MODE: Literal["file_dropzone", "agent_webhook", "openai_compatible_agent", "mock_dry_run"] = Field(
        default="file_dropzone",
        description="Mode for handling uploaded spreadsheets: 'file_dropzone' (default, places file in folder for Antigravity CLI)",
    )
    DORMITORY_AGENT_API_URL: str = Field(
        default="",
        description="Endpoint URL for Dormitory AI Agent webhook/REST API",
    )
    DORMITORY_AGENT_API_KEY: str = Field(
        default="",
        description="Bearer token or API key for Dormitory AI Agent",
    )
    DORMITORY_BACKEND_API_URL: str = Field(
        default="",
        description="Backend REST API URL for Dormitory Management System",
    )

    # OpenAI-Compatible Agent Settings
    OPENAI_BASE_URL: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI-compatible LLM agent",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for OpenAI-compatible LLM agent",
    )
    AGENT_MODEL: str = Field(
        default="gpt-4o-mini",
        description="Model name for OpenAI-compatible LLM agent",
    )

    # Custom Agent Prompt / Instructions
    DEFAULT_AGENT_INSTRUCTIONS: str = Field(
        default="",
        description="Default instructions provided to the agent for transaction parsing",
    )

    @field_validator("ALLOWED_TELEGRAM_USER_IDS", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v: object) -> list[int]:
        """Parse comma-separated string or list into a list of integers."""
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            ids: list[int] = []
            for item in v.split(","):
                clean = item.strip().strip("'\"[]")
                if clean:
                    try:
                        ids.append(int(clean))
                    except ValueError:
                        logger.warning("Invalid Telegram user ID in configuration: %s", clean)
            return ids
        if isinstance(v, (list, tuple, set)):
            return [int(item) for item in v if item is not None and str(item).strip()]
        return []

    def ensure_directories(self) -> None:
        """Create runtime directories if they do not exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.SPREADSHEET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if self.DB_PATH.parent:
            self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    def get_effective_default_instructions(self) -> str:
        """Retrieve default instructions from config or file on disk."""
        if self.DEFAULT_AGENT_INSTRUCTIONS.strip():
            return self.DEFAULT_AGENT_INSTRUCTIONS.strip()

        file_path = Path("config/default_agent_instructions.md")
        if file_path.exists():
            try:
                return file_path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning("Failed to read instructions from %s: %s", file_path, e)

        return (
            "Process the provided dormitory transactions and categorize into Rent, "
            "Deposit, Utilities, or Fees. Apply idempotency checks on reference numbers."
        )


settings = Settings()

