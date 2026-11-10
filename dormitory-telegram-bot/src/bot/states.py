"""Finite State Machine (FSM) state groups for raw data collection and spreadsheet ingestion."""

from aiogram.fsm.state import State, StatesGroup


class RawDataStates(StatesGroup):
    """FSM states for collecting photos, notes, and building cell-anchored raw spreadsheets."""

    collecting_row = State()


class IngestStates(StatesGroup):
    """FSM states for uploading, previewing, and syncing cleaned Excel spreadsheets."""

    waiting_for_file = State()
    preview_and_confirm = State()
    editing_instructions = State()
    handling_duplicates = State()

