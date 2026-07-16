from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    """16-band: admin sozlamalarni bitta-bitta tahrirlash oqimi."""

    editing_value = State()


class DepartmentChainStates(StatesGroup):
    """6.1/7.4-band: bo'limlarning standart ishlab chiqarish ketma-ketligini
    (`departments.next_department_id`) sozlash oqimi."""

    waiting_for_department = State()
    waiting_for_next_department = State()
