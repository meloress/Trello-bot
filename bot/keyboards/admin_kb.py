from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models.brigade import Brigade
from db.models.department import Department
from db.models.employee import Employee
from utils.enums import Role

EMPLOYEES_DONE = "employees_done"
CONFIRM_TASK = "confirm_task"
CANCEL_TASK = "cancel_task"

# 5.1-band: xodim boshqaruvi uchun umumiy (state-orqali izolyatsiya qilingan,
# shuning uchun bir nechta oqimda xavfsiz qayta ishlatiladigan) literal qiymatlar.
SKIP = "skip"
CONFIRM = "confirm"
CANCEL = "cancel"
EMP_ADD = "emp_add"
EMP_LIST = "emp_list"
EMP_EDIT = "emp_edit"
EMP_DELETE = "emp_delete"
EMP_BACK_TO_DETAIL = "emp_back_to_detail"
EMP_TOGGLE_ACTIVE = "emp_toggle_active"


class DepartmentSelect(CallbackData, prefix="dept"):
    department_id: int


class EmployeeToggle(CallbackData, prefix="emp"):
    """Vazifa yaratishda ko'p-tanlovli xodim ro'yxati uchun (task_create.py)."""

    employee_id: int


class SettingField(CallbackData, prefix="setfield"):
    field: str


class RoleSelect(CallbackData, prefix="rolesel"):
    role: str


class BrigadeSelect(CallbackData, prefix="brigsel"):
    brigade_id: int


class EmployeeSelect(CallbackData, prefix="empsel"):
    """Xodimlar ro'yxatidan bittasini tanlash uchun (employee_management.py)."""

    employee_id: int


class EmployeeFieldSelect(CallbackData, prefix="empfield"):
    field: str


class AdvanceTaskSetup(CallbackData, prefix="advtask"):
    """6.1/7.4-band: "Sozlash" tugmasi — PENDING_SETUP bosqichga muddat/xodim
    kiritish oqimini boshlaydi (handlers/admin/advance_task.py)."""

    task_id: int


class ReassignReview(CallbackData, prefix="reassign"):
    """8.3-band: "Ko'rib chiqish" tugmasi — avtomatik-aniqlangan uzoq
    kechikkan buyurtmani boshqa brigadaga o'tkazish oqimini boshlaydi
    (handlers/admin/reassign_task.py)."""

    task_id: int


class ReminderEntrySelect(CallbackData, prefix="remidx"):
    """7.3-band: eslatma jadvalidagi bitta yozuvni tanlash (tahrirlash/o'chirish)."""

    index: int


class ReminderEntryEdit(CallbackData, prefix="remedit"):
    index: int


class ReminderEntryDelete(CallbackData, prefix="remdel"):
    index: int


class ReminderUrgencySelect(CallbackData, prefix="remurg"):
    urgency: str


class DepartmentAutoReassignToggle(CallbackData, prefix="deptauto"):
    """8.3-band: `/autoreassign` — bo'lim darajasida 48-soatlik avtomatik
    brigadaga-o'tkazish signalini yoqish/o'chirish."""

    department_id: int


REMINDER_BACK = "reminder_back"


ROLE_LABELS: dict[Role, str] = {
    Role.WORKER: "👷 Ishchi",
    Role.BRIGADIER: "👨‍💼 Brigadir",
    Role.SUPERVISOR: "🕵️ Nazoratchi",
    Role.ADMIN: "👔 Rahbar/Admin",
    Role.OBSERVER: "👀 Kuzatuvchi",
    Role.SELLER: "💼 Sotuvchi",
}

EMPLOYEE_FIELD_LABELS: dict[str, str] = {
    "full_name": "👤 Ism",
    "phone_number": "📞 Telefon",
    "trello_username": "🔗 Trello username",
    "role": "🏷 Rol",
    "department_id": "🏢 Bo'lim",
    "brigade_id": "👥 Brigada",
}


def build_department_keyboard(
    departments: list[Department], *, include_skip: bool = False
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=d.name, callback_data=DepartmentSelect(department_id=d.id).pack())]
        for d in departments
    ]
    if include_skip:
        rows.append([InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=SKIP)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_brigade_keyboard(brigades: list[Brigade], *, include_skip: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=b.name, callback_data=BrigadeSelect(brigade_id=b.id).pack())]
        for b in brigades
    ]
    if include_skip:
        rows.append([InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=SKIP)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_role_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=RoleSelect(role=role.value).pack())]
        for role, label in ROLE_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_yes_no_keyboard(yes_data: str = CONFIRM, no_data: str = CANCEL) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=yes_data),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=no_data),
            ]
        ]
    )


def build_employee_list_keyboard(employees: list[Employee]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if e.is_active else '🚫'} {e.full_name} "
                f"({ROLE_LABELS.get(e.role, e.role.value)})",
                callback_data=EmployeeSelect(employee_id=e.id).pack(),
            )
        ]
        for e in employees
    ]
    rows.append([InlineKeyboardButton(text="➕ Yangi xodim qo'shish", callback_data=EMP_ADD)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_employee_detail_keyboard(employee: Employee) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Faolsizlantirish" if employee.is_active else "✅ Faollashtirish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=EMP_EDIT)],
            [InlineKeyboardButton(text=toggle_text, callback_data=EMP_TOGGLE_ACTIVE)],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=EMP_DELETE)],
            [InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data=EMP_LIST)],
        ]
    )


def build_employee_edit_fields_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=EmployeeFieldSelect(field=field).pack())]
        for field, label in EMPLOYEE_FIELD_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=EMP_BACK_TO_DETAIL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_employee_multiselect_keyboard(
    employees: list[Employee], selected_ids: set[int]
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅ ' if e.id in selected_ids else ''}{e.full_name}",
                callback_data=EmployeeToggle(employee_id=e.id).pack(),
            )
        ]
        for e in employees
    ]
    rows.append([InlineKeyboardButton(text="✅ Tayyor", callback_data=EMPLOYEES_DONE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=CONFIRM_TASK),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CANCEL_TASK),
            ]
        ]
    )


SETTING_FIELD_LABELS: dict[str, str] = {
    "default_penalty_multiplier": "📊 Jarima ko'paytiruvchisi",
    "brigade_share_ratio": "👥 Brigadir ulushi",
    "balls_per_day_shift": "📅 Kun-siljish uchun ball",
}

URGENCY_LABELS: dict[str, str] = {
    "info": "ℹ️ Oddiy (info)",
    "warning": "⚠️ Ogohlantirish (warning)",
    "urgent": "🚨 Shoshilinch (urgent)",
}

REMINDER_ADD = "reminder_add"


def build_advance_setup_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛠 Sozlash", callback_data=AdvanceTaskSetup(task_id=task_id).pack())]
        ]
    )


def build_settings_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"✏️ {label}", callback_data=SettingField(field=field).pack())]
        for field, label in SETTING_FIELD_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reminder_schedule_keyboard(schedule: list[dict]) -> InlineKeyboardMarkup:
    """7.3-band: `/reminders` — joriy eslatma jadvali, har biri tahrirlash
    uchun bosiladigan, + yangi qo'shish tugmasi."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"🕗 {entry['time']} — {URGENCY_LABELS.get(entry['urgency'], entry['urgency'])}",
                callback_data=ReminderEntrySelect(index=i).pack(),
            )
        ]
        for i, entry in enumerate(schedule)
    ]
    rows.append([InlineKeyboardButton(text="➕ Yangi vaqt qo'shish", callback_data=REMINDER_ADD)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reminder_entry_action_keyboard(index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Vaqtni o'zgartirish", callback_data=ReminderEntryEdit(index=index).pack()
                ),
                InlineKeyboardButton(
                    text="🗑 O'chirish", callback_data=ReminderEntryDelete(index=index).pack()
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=REMINDER_BACK)],
        ]
    )


def build_urgency_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=ReminderUrgencySelect(urgency=value).pack())]
        for value, label in URGENCY_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_autoreassign_keyboard(departments: list[Department]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if d.auto_reassign_after_48h else '🚫'} {d.name}",
                callback_data=DepartmentAutoReassignToggle(department_id=d.id).pack(),
            )
        ]
        for d in departments
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reassign_review_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔁 Ko'rib chiqish", callback_data=ReassignReview(task_id=task_id).pack())]
        ]
    )
