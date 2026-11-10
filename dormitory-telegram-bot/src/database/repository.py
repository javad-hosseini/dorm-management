"""SQLite persistence layer using aiosqlite for session recovery and idempotency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionRecord:
    """Represents a raw data entry session."""

    session_id: str
    user_id: int
    current_row_index: int
    status: str  # ACTIVE, COMPLETED, CANCELLED
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class BlockRecord:
    """Represents an individual block (cell item) within a row."""

    id: int
    session_id: str
    row_index: int
    col_index: int
    block_type: str  # TEXT or IMAGE
    text_content: Optional[str]
    file_path: Optional[str]
    created_at: str


@dataclass(frozen=True)
class IngestedTransactionRecord:
    """Represents an ingested row record for idempotency and audit."""

    row_hash: str
    file_name: str
    row_index: int
    data_json: str
    status: str  # SUCCESS, FAILED, DUPLICATE
    error_message: Optional[str]
    ingested_at: str
    user_id: int


class DatabaseRepository:
    """Asynchronous SQLite repository for managing bot sessions and transaction history."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = str(db_path)

    async def init_db(self) -> None:
        """Initialize database schema, tables, and indexes."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA foreign_keys=ON;")

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    current_row_index INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_user_status 
                ON sessions(user_id, status);
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    row_index INTEGER NOT NULL,
                    col_index INTEGER NOT NULL,
                    block_type TEXT NOT NULL,
                    text_content TEXT,
                    file_path TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_blocks_session_row 
                ON session_blocks(session_id, row_index, col_index);
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS ingested_transactions (
                    row_hash TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    row_index INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    ingested_at TEXT NOT NULL,
                    user_id INTEGER NOT NULL
                );
                """
            )
            await db.commit()
            logger.info("Database schema verified at %s", self.db_path)

    async def get_active_session(self, user_id: int) -> Optional[SessionRecord]:
        """Fetch the current active session for a user, if any."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id, user_id, current_row_index, status, created_at, updated_at
                FROM sessions
                WHERE user_id = ? AND status = 'ACTIVE'
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return SessionRecord(
                session_id=row["session_id"],
                user_id=row["user_id"],
                current_row_index=row["current_row_index"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Fetch a session by its session_id."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id, user_id, current_row_index, status, created_at, updated_at
                FROM sessions
                WHERE session_id = ?;
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return SessionRecord(
                session_id=row["session_id"],
                user_id=row["user_id"],
                current_row_index=row["current_row_index"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def create_session(self, user_id: int, session_id: str) -> SessionRecord:
        """Create a new session, deactivating any existing active sessions for this user."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            # Mark previous active sessions as CANCELLED
            await db.execute(
                """
                UPDATE sessions 
                SET status = 'CANCELLED', updated_at = ?
                WHERE user_id = ? AND status = 'ACTIVE';
                """,
                (now, user_id),
            )

            await db.execute(
                """
                INSERT INTO sessions (session_id, user_id, current_row_index, status, created_at, updated_at)
                VALUES (?, ?, 1, 'ACTIVE', ?, ?);
                """,
                (session_id, user_id, now, now),
            )
            await db.commit()

        return SessionRecord(
            session_id=session_id,
            user_id=user_id,
            current_row_index=1,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )

    async def update_session_row(self, session_id: str, new_row_index: int) -> None:
        """Update current row index for a session."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET current_row_index = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (new_row_index, now, session_id),
            )
            await db.commit()

    async def set_session_status(self, session_id: str, status: str) -> None:
        """Update status of a session ('ACTIVE', 'COMPLETED', 'CANCELLED')."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET status = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (status, now, session_id),
            )
            await db.commit()

    async def add_block(
        self,
        session_id: str,
        row_index: int,
        block_type: str,
        text_content: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> BlockRecord:
        """Append a block to the next available column in the specified row."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Determine next col_index for this row
            cursor = await db.execute(
                """
                SELECT COALESCE(MAX(col_index), 0) + 1 AS next_col
                FROM session_blocks
                WHERE session_id = ? AND row_index = ?;
                """,
                (session_id, row_index),
            )
            row = await cursor.fetchone()
            next_col = row["next_col"] if row else 1

            insert_cursor = await db.execute(
                """
                INSERT INTO session_blocks (
                    session_id, row_index, col_index, block_type, text_content, file_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (session_id, row_index, next_col, block_type, text_content, file_path, now),
            )
            block_id = insert_cursor.lastrowid or 0

            # Update session updated_at
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                (now, session_id),
            )
            await db.commit()

            return BlockRecord(
                id=block_id,
                session_id=session_id,
                row_index=row_index,
                col_index=next_col,
                block_type=block_type,
                text_content=text_content,
                file_path=file_path,
                created_at=now,
            )

    async def get_blocks_for_row(self, session_id: str, row_index: int) -> list[BlockRecord]:
        """Fetch all blocks for a given row in ascending column order."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, session_id, row_index, col_index, block_type, text_content, file_path, created_at
                FROM session_blocks
                WHERE session_id = ? AND row_index = ?
                ORDER BY col_index ASC;
                """,
                (session_id, row_index),
            )
            rows = await cursor.fetchall()
            return [
                BlockRecord(
                    id=r["id"],
                    session_id=r["session_id"],
                    row_index=r["row_index"],
                    col_index=r["col_index"],
                    block_type=r["block_type"],
                    text_content=r["text_content"],
                    file_path=r["file_path"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    async def get_blocks_for_session(self, session_id: str) -> list[BlockRecord]:
        """Fetch all blocks in a session, ordered by row then column."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, session_id, row_index, col_index, block_type, text_content, file_path, created_at
                FROM session_blocks
                WHERE session_id = ?
                ORDER BY row_index ASC, col_index ASC;
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [
                BlockRecord(
                    id=r["id"],
                    session_id=r["session_id"],
                    row_index=r["row_index"],
                    col_index=r["col_index"],
                    block_type=r["block_type"],
                    text_content=r["text_content"],
                    file_path=r["file_path"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    async def undo_last_block(
        self, session_id: str, current_row_index: int
    ) -> tuple[Optional[BlockRecord], int]:
        """Undo the last block in current row.

        If current row is empty and current_row_index > 1, step back to previous row.
        Returns (removed_block_or_none, resulting_row_index).
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Check if current row has blocks
            cursor = await db.execute(
                """
                SELECT id, session_id, row_index, col_index, block_type, text_content, file_path, created_at
                FROM session_blocks
                WHERE session_id = ? AND row_index = ?
                ORDER BY col_index DESC
                LIMIT 1;
                """,
                (session_id, current_row_index),
            )
            last_block_row = await cursor.fetchone()

            if last_block_row:
                # Delete this block
                block = BlockRecord(
                    id=last_block_row["id"],
                    session_id=last_block_row["session_id"],
                    row_index=last_block_row["row_index"],
                    col_index=last_block_row["col_index"],
                    block_type=last_block_row["block_type"],
                    text_content=last_block_row["text_content"],
                    file_path=last_block_row["file_path"],
                    created_at=last_block_row["created_at"],
                )
                await db.execute("DELETE FROM session_blocks WHERE id = ?;", (block.id,))
                await db.commit()
                return block, current_row_index

            # Current row is empty. If row > 1, step back to previous row
            if current_row_index > 1:
                prev_row = current_row_index - 1
                now = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "UPDATE sessions SET current_row_index = ?, updated_at = ? WHERE session_id = ?;",
                    (prev_row, now, session_id),
                )
                await db.commit()
                return None, prev_row

            return None, current_row_index

    async def clear_row(self, session_id: str, row_index: int) -> list[BlockRecord]:
        """Delete all blocks in the given row and return them."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, session_id, row_index, col_index, block_type, text_content, file_path, created_at
                FROM session_blocks
                WHERE session_id = ? AND row_index = ?;
                """,
                (session_id, row_index),
            )
            rows = await cursor.fetchall()
            blocks = [
                BlockRecord(
                    id=r["id"],
                    session_id=r["session_id"],
                    row_index=r["row_index"],
                    col_index=r["col_index"],
                    block_type=r["block_type"],
                    text_content=r["text_content"],
                    file_path=r["file_path"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
            if blocks:
                await db.execute(
                    "DELETE FROM session_blocks WHERE session_id = ? AND row_index = ?;",
                    (session_id, row_index),
                )
                now = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?;",
                    (now, session_id),
                )
                await db.commit()
            return blocks

    async def check_row_hashes(self, hashes: list[str]) -> set[str]:
        """Return the subset of row_hashes that already exist in the database."""
        if not hashes:
            return set()

        existing: set[str] = set()
        # Query in chunks if hashes list is large
        chunk_size = 500
        async with aiosqlite.connect(self.db_path) as db:
            for i in range(0, len(hashes), chunk_size):
                chunk = hashes[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor = await db.execute(
                    f"SELECT row_hash FROM ingested_transactions WHERE row_hash IN ({placeholders});",
                    chunk,
                )
                rows = await cursor.fetchall()
                for r in rows:
                    existing.add(r[0])
        return existing

    async def record_ingested_transaction(
        self,
        row_hash: str,
        file_name: str,
        row_index: int,
        data_json: str,
        status: str,
        user_id: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Insert or update transaction record for idempotency tracking."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO ingested_transactions (
                    row_hash, file_name, row_index, data_json, status, error_message, ingested_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (row_hash, file_name, row_index, data_json, status, error_message, now, user_id),
            )
            await db.commit()


_db_instance: Optional[DatabaseRepository] = None


def get_db(db_path: Path | str | None = None) -> DatabaseRepository:
    """Singleton getter for the DatabaseRepository."""
    global _db_instance
    if _db_instance is None:
        from src.config import settings

        path = db_path or settings.DB_PATH
        _db_instance = DatabaseRepository(path)
    return _db_instance

