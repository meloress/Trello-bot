from aiogram.fsm.state import State, StatesGroup


class ClientLinkStates(StatesGroup):
    """12-band: mijoz `/mijoz` orqali o'z telefon raqamini kiritib
    Telegram akkauntini bog'laydi (admin oldindan kiritgan yozuvga)."""

    waiting_for_phone = State()
