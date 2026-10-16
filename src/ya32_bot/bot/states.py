"""FSM states for multi-step input."""

from aiogram.fsm.state import State, StatesGroup


class HwAdd(StatesGroup):
    collect = State()


class HwEdit(StatesGroup):
    text = State()


class EditField(StatesGroup):
    """Admin types a value for a lesson field (date override or template row)."""

    value = State()


class SubjectEdit(StatesGroup):
    value = State()


class HolidayTitle(StatesGroup):
    title = State()


class Broadcast(StatesGroup):
    text = State()
