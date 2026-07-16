from aiogram.fsm.state import State, StatesGroup


class AdvanceTaskStates(StatesGroup):
    """6.1/7.4-band: ko'p bosqichli buyurtma — PENDING_SETUP bosqichga
    muddat/xodim belgilash oqimi ("Sozlash" tugmasi)."""

    waiting_for_deadline = State()
    waiting_for_employees = State()
    confirming = State()
