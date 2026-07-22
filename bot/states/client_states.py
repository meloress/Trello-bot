from aiogram.fsm.state import State, StatesGroup


class ClientLinkStates(StatesGroup):
    """12-band: mijoz `/mijoz` orqali Telegram'ning o'z kontakt-ulashish
    tugmasi bilan telefon raqamini yuborib, Telegram akkauntini bog'laydi
    (admin oldindan kiritgan yozuvga)."""

    waiting_for_contact = State()
