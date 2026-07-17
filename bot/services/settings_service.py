"""Tizim sozlamalari: bazada saqlanadigan, admin/nazoratchi tomonidan bot
orqali o'zgartiriladigan qiymatlar (16-band). `config.py`dagi .env-asosli
STATIK sozlamalardan farqli o'laroq, bular DINAMIK — shu sabab alohida
modulda, xotirada keshlangan holda saqlanadi: har o'qishda bazaga
murojaat qilinmaydi, faqat qiymat o'zgarganda (`update_setting`) kesh
yangilanadi.
"""

from dataclasses import dataclass

from core.database import async_session
from db.repositories import AppSettingRepository
from utils.enums import ReminderUrgency

_URGENCY_VALUES = {u.value for u in ReminderUrgency}


class InvalidReminderScheduleError(Exception):
    """`reminder_schedule` ro'yxati noto'g'ri formatda (7.3-band validatsiyasi)."""


@dataclass(frozen=True)
class AppSettingsSnapshot:
    reminder_schedule: list[dict]
    default_penalty_multiplier: float
    brigade_share_ratio: float
    balls_per_day_shift: int
    plus_ball_per_day: int
    plus_ball_max_days: int
    financial_flag_threshold_days: int
    advance_threshold_percent: int
    advance_waiver_percent: int
    report_time: str
    lead_follow_up_threshold_days: int
    sales_board_lists: dict


_cache: AppSettingsSnapshot | None = None


def validate_reminder_schedule(schedule: list[dict]) -> None:
    """7.3/16-band: har vaqt HH:MM formatida, takrorlanmasin, urgency uchta
    qiymatdan biri bo'lsin. Bo'sh ro'yxatga ruxsat bor (barcha eslatmalarni
    o'chirib qo'yish — admin qarori)."""
    seen_times: set[str] = set()
    for entry in schedule:
        time_str = entry.get("time")
        urgency = entry.get("urgency")
        try:
            hour, minute = time_str.split(":")
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError
        except (AttributeError, ValueError):
            raise InvalidReminderScheduleError(f"Noto'g'ri vaqt formati: {time_str!r} (HH:MM kerak)")
        if time_str in seen_times:
            raise InvalidReminderScheduleError(f"Vaqt takrorlanmoqda: {time_str}")
        seen_times.add(time_str)
        if urgency not in _URGENCY_VALUES:
            raise InvalidReminderScheduleError(
                f"Noto'g'ri urgency: {urgency!r} ({', '.join(sorted(_URGENCY_VALUES))} bo'lishi kerak)"
            )


def validate_time_str(value: str) -> None:
    """10.2-band: `report_time` HH:MM formatida bo'lishi kerak (reminder
    vaqtlari bilan bir xil qoida)."""
    try:
        hour, minute = value.split(":")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError
    except (AttributeError, ValueError):
        raise InvalidReminderScheduleError(f"Noto'g'ri vaqt formati: {value!r} (HH:MM kerak)")


async def _load_from_db() -> AppSettingsSnapshot:
    async with async_session() as session:
        row = await AppSettingRepository(session).get_singleton()
    return AppSettingsSnapshot(
        reminder_schedule=row.reminder_schedule,
        default_penalty_multiplier=row.default_penalty_multiplier,
        brigade_share_ratio=row.brigade_share_ratio,
        balls_per_day_shift=row.balls_per_day_shift,
        plus_ball_per_day=row.plus_ball_per_day,
        plus_ball_max_days=row.plus_ball_max_days,
        financial_flag_threshold_days=row.financial_flag_threshold_days,
        advance_threshold_percent=row.advance_threshold_percent,
        advance_waiver_percent=row.advance_waiver_percent,
        report_time=row.report_time,
        lead_follow_up_threshold_days=row.lead_follow_up_threshold_days,
        sales_board_lists=row.sales_board_lists,
    )


async def get_settings() -> AppSettingsSnapshot:
    """Keshlangan qiymatlarni qaytaradi; birinchi chaqiruvda bazadan yuklaydi."""
    global _cache
    if _cache is None:
        _cache = await _load_from_db()
    return _cache


async def refresh() -> AppSettingsSnapshot:
    """Bazadan majburan qayta yuklaydi va keshni yangilaydi."""
    global _cache
    _cache = await _load_from_db()
    return _cache


async def update_setting(**fields: object) -> AppSettingsSnapshot:
    """Bitta yoki bir nechta maydonni bazada yangilaydi va keshni yangilab qaytaradi.
    Masalan: `await update_setting(brigade_share_ratio=0.4)`."""
    if "reminder_schedule" in fields:
        validate_reminder_schedule(fields["reminder_schedule"])
    if "report_time" in fields:
        validate_time_str(fields["report_time"])

    async with async_session() as session:
        repo = AppSettingRepository(session)
        row = await repo.get_singleton()
        await repo.update(row, **fields)
        await session.commit()

    return await refresh()
