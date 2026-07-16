from aiogram.fsm.state import State, StatesGroup


class EmployeeManageStates(StatesGroup):
    """5.1-band: admin/nazoratchi botdan xodim qo'shish/tahrirlash/o'chirish oqimi."""

    # Qo'shish
    add_waiting_full_name = State()
    add_waiting_phone = State()
    add_waiting_role = State()
    add_waiting_department = State()
    add_waiting_brigade = State()
    add_confirming = State()

    # Tahrirlash (FSM data: employee_id, field)
    edit_waiting_text_value = State()
    edit_waiting_role = State()
    edit_waiting_department = State()
    edit_waiting_brigade = State()

    # O'chirish (soft-delete) tasdig'i
    delete_confirming = State()
