from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from utils.enums import TaskStatus

if TYPE_CHECKING:
    from db.models.task import Task

# Toshkent doim UTC+5 (yozgi vaqtga o'tmaydi) — xabarlarda mahalliy vaqt ko'rsatiladi.
TASHKENT_TZ = timezone(timedelta(hours=5))

TASK_STATUS_LABELS = {
    TaskStatus.ACTIVE: "🟢 Faol",
    TaskStatus.STOPPED: "🛑 To'xtatilgan",
    TaskStatus.COMPLETED: "✅ Yakunlangan",
    TaskStatus.OVERDUE: "🔴 Muddati o'tgan",
    TaskStatus.PENDING_SETUP: "⏳ Navbatda (sozlanmoqda)",
}


def format_dt(value: datetime) -> str:
    return value.astimezone(TASHKENT_TZ).strftime("%d.%m.%Y %H:%M")


def format_task_card(task: "Task") -> str:
    """Bitta vazifani ishchi ekranlarida (`/tasks`, `/misctasks`, bildirishnoma)
    bir xilda ko'rsatish uchun umumiy karta matni."""
    label = TASK_STATUS_LABELS.get(task.status, str(task.status))
    lines = [task.title, f"Holat: {label}"]

    if task.deadline is None:
        # PENDING_SETUP holatida deadline hali yo'q (6.1/7.4-band: nazoratchi
        # hali muddat kiritmagan).
        lines.append("Muddat: hali belgilanmagan")
    else:
        lines.append(f"Muddat: {format_dt(task.deadline)}")
        delta = task.deadline - datetime.now(timezone.utc)
        days = int(delta.total_seconds() // 86400)
        if delta.total_seconds() >= 0:
            lines.append(f"Muddatgacha: {days} kun" if days > 0 else "Muddatgacha: bugun")
        else:
            lines.append(f"Muddati o'tgan: {abs(days)} kun oldin" if days < 0 else "Muddati bugun o'tdi")

    return "\n".join(lines)
