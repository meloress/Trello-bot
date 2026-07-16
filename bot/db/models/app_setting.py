from __future__ import annotations

from sqlalchemy import Float, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.base import TimestampedBase

# 7.3-band standart jadvali: 09:00/13:00 oddiy eslatma, 15:00 ogohlantirish,
# 17:00 shoshilinch. 18:00 ("DEDLAYN") shu ro'yxatga kiritilmagan — haqiqiy
# muddat har vazifada turlicha bo'lgani uchun soatlik overdue_watch_job
# (7.2-band "muddat o'tdi" hodisasi) bilan alohida ishlanadi.
DEFAULT_REMINDER_SCHEDULE = [
    {"time": "09:00", "urgency": "info"},
    {"time": "13:00", "urgency": "info"},
    {"time": "15:00", "urgency": "warning"},
    {"time": "17:00", "urgency": "urgent"},
]


class AppSetting(TimestampedBase):
    """Tizim sozlamalari — SINGLETON jadval (doim faqat bitta qator bo'ladi,
    migratsiya orqali seed qilingan). 16-band: "eslatma vaqtlari, jarima
    boshlanish vaqti, ball qiymatlari, brigadir ulushi — hammasi admin
    paneldan o'zgartiriladi (kodga tikilmaydi)". Qiymatlar xotirada
    keshlanadi (`services/settings_service.py`) — bu jadvalga har so'rovda
    to'g'ridan-to'g'ri murojaat qilinmaydi."""

    __tablename__ = "app_settings"

    # 7.3-band: kunlik eslatma vaqtlari ro'yxati, har biri eskalatsiya
    # darajasi bilan — [{"time": "HH:MM", "urgency": "info|warning|urgent"}, ...].
    reminder_schedule: Mapped[list] = mapped_column(JSON, nullable=False)
    default_penalty_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    brigade_share_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    balls_per_day_shift: Mapped[int] = mapped_column(Integer, nullable=False)
