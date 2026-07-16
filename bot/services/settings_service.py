"""Tizim sozlamalari: bazada saqlanadigan, admin/nazoratchi tomonidan bot
orqali o'zgartiriladigan qiymatlar (16-band). `config.py`dagi .env-asosli
STATIK sozlamalardan farqli o'laroq, bular DINAMIK — shu sabab alohida
modulda, xotirada keshlangan holda saqlanadi: har o'qishda bazaga
murojaat qilinmaydi, faqat qiymat o'zgarganda (`update_setting`) kesh
yangilanadi.
"""

from dataclasses import dataclass
from datetime import time

from core.database import async_session
from db.repositories import AppSettingRepository


@dataclass(frozen=True)
class AppSettingsSnapshot:
    remind_time: time
    default_penalty_multiplier: float
    brigade_share_ratio: float
    balls_per_day_shift: int


_cache: AppSettingsSnapshot | None = None


async def _load_from_db() -> AppSettingsSnapshot:
    async with async_session() as session:
        row = await AppSettingRepository(session).get_singleton()
    return AppSettingsSnapshot(
        remind_time=row.remind_time,
        default_penalty_multiplier=row.default_penalty_multiplier,
        brigade_share_ratio=row.brigade_share_ratio,
        balls_per_day_shift=row.balls_per_day_shift,
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
    async with async_session() as session:
        repo = AppSettingRepository(session)
        row = await repo.get_singleton()
        await repo.update(row, **fields)
        await session.commit()

    return await refresh()
