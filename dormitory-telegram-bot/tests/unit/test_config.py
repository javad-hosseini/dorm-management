"""Unit tests for Pydantic settings loading and validation."""

from pathlib import Path
from src.config import Settings


def test_settings_allowed_user_ids_parsing():
    """Verify parsing comma-separated strings, integer sequences, and empty values."""
    s1 = Settings(ALLOWED_TELEGRAM_USER_IDS="111111, 222222, 333333")  # type: ignore
    assert s1.ALLOWED_TELEGRAM_USER_IDS == [111111, 222222, 333333]

    s2 = Settings(ALLOWED_TELEGRAM_USER_IDS=[111111, 222222])
    assert s2.ALLOWED_TELEGRAM_USER_IDS == [111111, 222222]

    s3 = Settings(ALLOWED_TELEGRAM_USER_IDS="")  # type: ignore
    assert s3.ALLOWED_TELEGRAM_USER_IDS == []

    s4 = Settings(ALLOWED_TELEGRAM_USER_IDS="['444444', '555555']")  # type: ignore
    assert s4.ALLOWED_TELEGRAM_USER_IDS == [444444, 555555]


def test_settings_default_instructions():
    """Verify loading default instructions from disk when not overridden."""
    s_default = Settings(DEFAULT_AGENT_INSTRUCTIONS="")
    instructions = s_default.get_effective_default_instructions()
    assert len(instructions) > 0
    assert "Dormitory" in instructions or "transaction" in instructions.lower()

    s_custom = Settings(DEFAULT_AGENT_INSTRUCTIONS="Custom rule: rent only.")
    assert s_custom.get_effective_default_instructions() == "Custom rule: rent only."


def test_settings_ensure_directories(tmp_path: Path):
    """Verify runtime directory creation."""
    data_dir = tmp_path / "custom_data"
    sessions_dir = data_dir / "custom_sessions"
    db_path = data_dir / "custom.db"

    s = Settings(DATA_DIR=data_dir, SESSIONS_DIR=sessions_dir, DB_PATH=db_path)
    s.ensure_directories()

    assert data_dir.exists()
    assert sessions_dir.exists()

