"""Unit tests for SQLite repository persistence, crash recovery, and idempotency."""

import pytest
from src.database.repository import DatabaseRepository


@pytest.mark.asyncio
async def test_session_lifecycle_and_crash_recovery(db_repo: DatabaseRepository):
    """Test session creation, persistence, and recovery simulating container restarts."""
    user_id = 111111

    # Ensure no active session initially
    assert await db_repo.get_active_session(user_id) is None

    # 1. Create a new active session
    session = await db_repo.create_session(user_id, "session_restart_test")
    assert session.session_id == "session_restart_test"
    assert session.current_row_index == 1
    assert session.status == "ACTIVE"

    # 2. Simulate container restart by fetching active session again from DB
    recovered = await db_repo.get_active_session(user_id)
    assert recovered is not None
    assert recovered.session_id == "session_restart_test"
    assert recovered.current_row_index == 1

    # 3. Status transition to COMPLETED
    await db_repo.set_session_status("session_restart_test", "COMPLETED")
    assert await db_repo.get_active_session(user_id) is None


@pytest.mark.asyncio
async def test_add_blocks_and_col_index_increment(db_repo: DatabaseRepository):
    """Verify adding blocks increments col_index sequentially within the row."""
    session = await db_repo.create_session(111111, "sess_col_test")
    s_id = session.session_id

    b1 = await db_repo.add_block(s_id, row_index=1, block_type="TEXT", text_content="Room 101 - 5,000,000")
    b2 = await db_repo.add_block(s_id, row_index=1, block_type="IMAGE", file_path="/app/data/photo1.jpg")
    b3 = await db_repo.add_block(s_id, row_index=1, block_type="TEXT", text_content="Peigiri 987654")

    assert b1.col_index == 1
    assert b2.col_index == 2
    assert b3.col_index == 3

    blocks = await db_repo.get_blocks_for_row(s_id, 1)
    assert len(blocks) == 3
    assert [b.col_index for b in blocks] == [1, 2, 3]


@pytest.mark.asyncio
async def test_row_progression(db_repo: DatabaseRepository):
    """Verify row advancement updates current_row_index and resets col_index for new row."""
    session = await db_repo.create_session(111111, "sess_progression")
    s_id = session.session_id

    # Add block to Row 1
    await db_repo.add_block(s_id, row_index=1, block_type="TEXT", text_content="Row 1 note")

    # Advance to Row 2
    await db_repo.update_session_row(s_id, new_row_index=2)
    updated_session = await db_repo.get_session(s_id)
    assert updated_session is not None
    assert updated_session.current_row_index == 2

    # Add first block to Row 2 -> must start at col_index = 1
    b_row2 = await db_repo.add_block(s_id, row_index=2, block_type="IMAGE", file_path="/app/data/photo2.jpg")
    assert b_row2.col_index == 1


@pytest.mark.asyncio
async def test_undo_last_block_edge_cases(db_repo: DatabaseRepository):
    """Verify undo behavior when row has blocks, when row is empty (stepback), and at Row 1 boundary."""
    session = await db_repo.create_session(111111, "sess_undo")
    s_id = session.session_id

    # Case A: Current row has 2 blocks -> undo removes block #2, leaves block #1
    b1 = await db_repo.add_block(s_id, row_index=1, block_type="TEXT", text_content="Block 1")
    b2 = await db_repo.add_block(s_id, row_index=1, block_type="IMAGE", file_path="/app/data/b2.jpg")

    removed, res_row = await db_repo.undo_last_block(s_id, current_row_index=1)
    assert removed is not None
    assert removed.id == b2.id
    assert res_row == 1

    remaining = await db_repo.get_blocks_for_row(s_id, 1)
    assert len(remaining) == 1
    assert remaining[0].id == b1.id

    # Case B: Current row (Row 2) has 0 blocks and row > 1 -> steps back to Row 1
    await db_repo.update_session_row(s_id, new_row_index=2)
    stepback_removed, stepback_row = await db_repo.undo_last_block(s_id, current_row_index=2)
    assert stepback_removed is None
    assert stepback_row == 1

    # Verify session current_row_index in DB was updated to 1
    session_after_stepback = await db_repo.get_session(s_id)
    assert session_after_stepback is not None
    assert session_after_stepback.current_row_index == 1

    # Clear remaining block on Row 1
    await db_repo.undo_last_block(s_id, current_row_index=1)

    # Case C: Current row is Row 1 and empty -> returns cleanly without exception
    empty_removed, empty_row = await db_repo.undo_last_block(s_id, current_row_index=1)
    assert empty_removed is None
    assert empty_row == 1


@pytest.mark.asyncio
async def test_clear_current_row(db_repo: DatabaseRepository):
    """Verify clear_row deletes all blocks in specified row without affecting other rows."""
    session = await db_repo.create_session(111111, "sess_clear_isolated")
    s_id = session.session_id

    # Populate Row 1
    await db_repo.add_block(s_id, row_index=1, block_type="TEXT", text_content="Row 1 text")

    # Populate Row 2
    await db_repo.add_block(s_id, row_index=2, block_type="IMAGE", file_path="/app/img2a.jpg")
    await db_repo.add_block(s_id, row_index=2, block_type="TEXT", text_content="Row 2 text")

    # Clear Row 2
    cleared = await db_repo.clear_row(s_id, row_index=2)
    assert len(cleared) == 2

    # Row 2 must be empty
    assert len(await db_repo.get_blocks_for_row(s_id, 2)) == 0

    # Row 1 must remain intact
    row1_blocks = await db_repo.get_blocks_for_row(s_id, 1)
    assert len(row1_blocks) == 1
    assert row1_blocks[0].text_content == "Row 1 text"


@pytest.mark.asyncio
async def test_transaction_idempotency(db_repo: DatabaseRepository):
    """Verify SHA-256 hash tracking and duplicate detection."""
    row_hashes = ["hash_tx_001", "hash_tx_002"]

    # Initially empty
    assert await db_repo.check_row_hashes(row_hashes) == set()

    # Record first transaction
    await db_repo.record_ingested_transaction(
        row_hash="hash_tx_001",
        file_name="cleaned_dormitory.xlsx",
        row_index=2,
        data_json='{"Room": 101, "Amount": 5000000}',
        status="SUCCESS",
        user_id=111111,
    )

    # Check hashes again
    existing = await db_repo.check_row_hashes(row_hashes)
    assert existing == {"hash_tx_001"}

