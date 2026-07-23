from __future__ import annotations

from sqlalchemy import Float, Integer, JSON, String
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

# Fasad sex TZ, Phase 7: bosqich necha kunda tugatilganiga qarab tavsiya
# etiladigan to'lov "tezlik darajasi" jadvali — [{"max_days": N, "tier":
# "<nom>", "pay_multiplier": X}, ...]. Aniq foiz/nom TZda berilmagan (ochiq
# savol #7), shu sabab standart qiymat BO'SH — admin to'ldirmaguncha butun
# xususiyat harakatsiz (`financial_service.calculate_speed_tier_bonus`).
DEFAULT_SPEED_TIER_SCHEDULE: list = []

# 5-bosqich (Sotuv CRM), 6.1-band: har (brand, bosqich) juftligi uchun
# Trello list ID. `departments.trello_list_id` bilan bir xil naqsh: bot UI
# orqali EMAS, to'g'ridan-to'g'ri bazada sozlanadi.
DEFAULT_SALES_BOARD_LISTS = {
    "ezza": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
    "melores": {"new_lead": None, "contacted": None, "offer_sent": None, "agreed": None, "closed": None},
}


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
    # 8.4-band: plus ball — muddatdan necha KUN oldin tugatilsa (dayIndex =
    # hours_early // 24), shuncha * plus_ball_per_day beriladi,
    # plus_ball_max_days'dan ortig'iga qo'shimcha ball berilmaydi (cap).
    plus_ball_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    plus_ball_max_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # 8.6-band: bosqich shuncha kundan ORTIQ (qat'iy >) davom etsa, moliyaviy
    # taklif avtomatik bayroqlanadi (summa hali noma'lum holatda).
    financial_flag_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # 8.6-band 2-qoida: avans shu foizdan KO'P/TENG olingan bo'lsa va buyurtma
    # kechiksa, qolgan advance_waiver_percent mijozdan talab qilinmasligi taklif qilinadi.
    advance_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    advance_waiver_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    # 10.2-band: kunlik/haftalik/oylik Telegram hisobotlari shu vaqtda
    # (HH:MM, Toshkent) ADMIN/SUPERVISOR'larga yuboriladi (jobs/report_job.py).
    # Haftalik — yakshanba, oylik — har oyning 1-sanasi, ikkalasi ham shu
    # bitta soatda (kun tanlovi TZda so'ralmagan, sozlanuvchan qilinmagan).
    report_time: Mapped[str] = mapped_column(String(5), nullable=False)
    # 13.3-band: "uzoq vaqt aloqaga chiqilmagan" mijoz uchun necha kun
    # (foydalanuvchi bilan tasdiqlangan standart: 7). /settings orqali o'zgartiriladi.
    lead_follow_up_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # 6.1-band: {"ezza": {"new_lead": list_id, ...}, "melores": {...}} — har
    # (brand, bosqich) juftligi uchun Trello list ID. `departments.trello_list_id`
    # bilan bir xil naqsh: bot UI orqali EMAS, to'g'ridan-to'g'ri bazada
    # sozlanadi (5-bosqich hujjatiga qarang).
    sales_board_lists: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Fasad sex TZ, Phase 6: kunlik norma — har ishchi kuniga shuncha "punkt"
    # ishlab chiqarishi kutiladi ("5 punkt ≈ 100 kv.m"). Bu qiymat FAQAT
    # stats/dashboard'da ko'rsatish uchun — timer/jarima sifatida MAJBURIY
    # QILINMAYDI (stats_service.get_capacity_vs_actual()).
    daily_quota_points_per_worker: Mapped[int] = mapped_column(Integer, nullable=False)
    # Fasad sex TZ, Phase 7: tezlik-darajali to'lov taklifi jadvali (yuqoridagi
    # DEFAULT_SPEED_TIER_SCHEDULE izohiga q.) — standart bo'sh ro'yxat.
    speed_tier_schedule: Mapped[list] = mapped_column(JSON, nullable=False)
