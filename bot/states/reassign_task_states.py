from aiogram.fsm.state import State, StatesGroup


class ReassignTaskStates(StatesGroup):
    """8.3-band: "Ko'rib chiqish" tugmasi -> boshqa brigadani tanlash ->
    tasdiqlash oqimi (handlers/admin/reassign_task.py)."""

    waiting_for_brigade = State()
    confirming = State()
