from aiogram.fsm.state import State, StatesGroup


class StopTaskStates(StatesGroup):
    """7.5-band: "Stop" bosilganda sabab yozish majburiy."""

    waiting_for_reason = State()


class CreateTaskStates(StatesGroup):
    """7.1-band: rahbar/nazoratchi yangi vazifa yaratish oqimi."""

    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_deadline = State()
    waiting_for_department = State()
    waiting_for_employees = State()
    confirming = State()
