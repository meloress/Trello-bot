from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.stats_service import EmployeeStats

WEEKLY_REPORT = "weekly"
CURRENT_TASKS = "tasks"


class BrigadeMemberAction(CallbackData, prefix="bmember"):
    action: str
    employee_id: int


def build_brigade_member_keyboard(stats: list[EmployeeStats]) -> InlineKeyboardMarkup:
    """Har bir xodim uchun bitta qatorda ikkita tugma: haftalik hisobot va
    joriy vazifalar (11.1-band)."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"📅 {s.full_name}",
                callback_data=BrigadeMemberAction(action=WEEKLY_REPORT, employee_id=s.employee_id).pack(),
            ),
            InlineKeyboardButton(
                text=f"📋 {s.full_name}",
                callback_data=BrigadeMemberAction(action=CURRENT_TASKS, employee_id=s.employee_id).pack(),
            ),
        ]
        for s in stats
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
