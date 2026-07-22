from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """5.2-band: /start bosgan yangi (hali bog'lanmagan) foydalanuvchidan
    Telegram'ning o'z kontakt-ulashish tugmasi orqali telefon raqamini
    so'rash (ism o'rniga — ism osongina taqlid qilinishi mumkin, kontakt esa
    Telegram'ning o'zi tomonidan tasdiqlangan raqam)."""

    waiting_for_contact = State()
