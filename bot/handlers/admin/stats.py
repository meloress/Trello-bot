"""Statistika va Dashboard (10-band): joriy oy bo'yicha xodimlar statistikasi.

Ruxsat: faqat Role.ADMIN/Role.SUPERVISOR — RoleAccessMiddleware orqali,
modul darajasida routerga ulangan.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from middlewares.auth import RoleAccessMiddleware
from services import stats_service
from utils.enums import Role

logger = logging.getLogger(__name__)

router = Router(name="admin_stats")
router.message.middleware(RoleAccessMiddleware({Role.ADMIN, Role.SUPERVISOR}))


def _format_stats_table(stats: list[stats_service.EmployeeStats]) -> str:
    """Butun xabar bitta kod-blok ichida qaytariladi — xodim ismidagi maxsus
    belgilar (_, *, `) Markdown parserini buzmasligi uchun (kod blok ichida
    Telegram hech narsani formatlab o'qimaydi, hammasi literal matn)."""
    if not stats:
        return "Faol xodimlar topilmadi."

    stats = sorted(stats, key=lambda s: s.total_score, reverse=True)

    name_width = max(len("Xodim"), max(len(s.full_name) for s in stats))
    header = f"{'Xodim'.ljust(name_width)} | Bajar. | Ball | Jarima"
    separator = "-" * len(header)

    lines = [f"Joriy oy statistikasi ({len(stats)} xodim)", "", header, separator]
    for s in stats:
        lines.append(
            f"{s.full_name.ljust(name_width)} | {str(s.completed_tasks).rjust(6)} | "
            f"{str(s.total_score).rjust(4)} | {str(s.penalty_count).rjust(6)}"
        )

    best = max(stats, key=lambda s: s.total_score)
    worst = max(stats, key=lambda s: s.penalty_count)

    lines.append("")
    if best.total_score > 0:
        lines.append(f"Eng yuqori ball: {best.full_name} ({best.total_score:+d})")
    if worst.penalty_count > 0:
        lines.append(f"Eng ko'p jarima (past unumdorlik): {worst.full_name} ({worst.penalty_count} marta)")

    return "```\n" + "\n".join(lines) + "\n```"


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    try:
        stats = await stats_service.get_monthly_stats()
        text = _format_stats_table(stats)
        await message.answer(text, parse_mode="Markdown")
    except Exception:
        logger.exception("cmd_stats xatosi")
        await message.answer("Kutilmagan xatolik yuz berdi.")
