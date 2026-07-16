from aiogram.fsm.state import State, StatesGroup


class MiscTaskStates(StatesGroup):
    """9-band: "Vazifalar" moduli — Trello'siz alohida topshiriq yaratish oqimi."""

    waiting_for_text = State()
    waiting_for_deadline = State()
    waiting_for_employees = State()
    confirming = State()
