from aiogram.fsm.state import State, StatesGroup


class SettingsStates(StatesGroup):
    """16-band: admin sozlamalarni bitta-bitta tahrirlash oqimi."""

    editing_value = State()


class DepartmentChainStates(StatesGroup):
    """6.1/7.4-band: bo'limlarning standart ishlab chiqarish ketma-ketligini
    (`departments.next_department_id`) sozlash oqimi."""

    waiting_for_department = State()
    waiting_for_next_department = State()


class ReminderScheduleStates(StatesGroup):
    """7.3-band: `/reminders` — eslatma jadvalini qo'shish/tahrirlash oqimi.
    FSM data: `index` (tahrirlashda — mavjud yozuvning o'rni, qo'shishda yo'q),
    `time` (vaqt tanlangach)."""

    waiting_for_time = State()
    waiting_for_urgency = State()
