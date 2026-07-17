from aiogram.fsm.state import State, StatesGroup


class CreateLeadStates(StatesGroup):
    """13.1-band: sotuvchi yangi lid kiritish oqimi (/yangilid)."""

    waiting_for_brand = State()
    waiting_for_phone = State()
    waiting_for_name = State()


class CallLogStates(StatesGroup):
    """13.2-band: lidga qo'ng'iroq yozuvi qo'shish — matn yoki ovozli xabar."""

    waiting_for_content = State()
