from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models.task import Task
from utils.enums import TaskStatus


class TaskAction(CallbackData, prefix="task"):
    action: str  # "start" | "stop" | "resume" | "finish"
    task_id: int


def build_task_keyboard(task: Task) -> InlineKeyboardMarkup | None:
    """Vazifa holatiga mos tugmalar. Sxemada alohida "hali boshlanmagan" statusi
    yo'q (faqat active/stopped/completed/overdue) — shu sababli active/overdue
    holatida uchala amal (qayta boshlash, to'xtatish, yakunlash) birga ko'rsatiladi;
    "Boshlash" bosilishi start_task()ni idempotent tarzda qayta chaqiradi va
    started_at'ni yangilaydi."""
    buttons: list[InlineKeyboardButton] = []

    if task.status in (TaskStatus.ACTIVE, TaskStatus.OVERDUE):
        buttons = [
            InlineKeyboardButton(
                text="▶️ Boshlash", callback_data=TaskAction(action="start", task_id=task.id).pack()
            ),
            InlineKeyboardButton(
                text="🛑 To'xtatish", callback_data=TaskAction(action="stop", task_id=task.id).pack()
            ),
            InlineKeyboardButton(
                text="✅ Yakunlash", callback_data=TaskAction(action="finish", task_id=task.id).pack()
            ),
        ]
    elif task.status == TaskStatus.STOPPED:
        buttons = [
            InlineKeyboardButton(
                text="▶️ Davom ettirish",
                callback_data=TaskAction(action="resume", task_id=task.id).pack(),
            )
        ]
    # COMPLETED -- amal tugmasi yo'q

    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
