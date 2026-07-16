from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """5.2-band: /start bosgan yangi (hali bog'lanmagan) foydalanuvchidan
    bazada mavjud to'liq ismini so'rash."""

    waiting_for_full_name = State()
