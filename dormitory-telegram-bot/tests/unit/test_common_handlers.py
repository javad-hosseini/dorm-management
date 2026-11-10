"""Unit tests for common handlers (/start, /help, /cancel)."""

from typing import Callable
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.bot.handlers.common import handle_cancel, handle_help, handle_start
from src.bot.states import RawDataStates


@pytest.mark.asyncio
async def test_handle_start(fsm_context: FSMContext, make_message: Callable[..., Message]):
    """Verify /start clears FSM state and sends welcome message with main menu."""
    await fsm_context.set_state(RawDataStates.collecting_row)
    msg = make_message(text="/start")

    await handle_start(msg, fsm_context)

    assert await fsm_context.get_state() is None
    msg.answer.assert_awaited_once()
    args, kwargs = msg.answer.call_args
    assert "Welcome to the Dormitory Financial Assistant Bot" in args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_handle_help(make_message: Callable[..., Message]):
    """Verify /help returns detailed operational guide."""
    msg = make_message(text="/help")
    await handle_help(msg)

    msg.answer.assert_awaited_once()
    args, _ = msg.answer.call_args
    assert "Dormitory Bot Guide & Instructions" in args[0]


@pytest.mark.asyncio
async def test_handle_cancel_with_active_state(
    fsm_context: FSMContext, make_message: Callable[..., Message]
):
    """Verify /cancel clears active state and notifies user."""
    await fsm_context.set_state(RawDataStates.collecting_row)
    msg = make_message(text="/cancel")

    await handle_cancel(msg, fsm_context)

    assert await fsm_context.get_state() is None
    msg.answer.assert_awaited_once()
    args, _ = msg.answer.call_args
    assert "Current operation cancelled" in args[0]


@pytest.mark.asyncio
async def test_handle_cancel_without_active_state(
    fsm_context: FSMContext, make_message: Callable[..., Message]
):
    """Verify /cancel when no state is running."""
    await fsm_context.clear()
    msg = make_message(text="/cancel")

    await handle_cancel(msg, fsm_context)

    msg.answer.assert_awaited_once()
    args, _ = msg.answer.call_args
    assert "No active operation was running" in args[0]

