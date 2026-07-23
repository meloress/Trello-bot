from __future__ import annotations

from datetime import date as date_, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee


class DailyReportSubmission(TimestampedBase):
    """Fasad sex TZ, Phase 8: kunlik rasm/video hisobot muvofiqligi — FAQAT
    kuzatuv (hech qanday jarima/ball bilan bog'liq emas, TZning o'zi ham bu
    masalada ochiq savol qoldirgan — `.claude/plans/09z-...`). Bitta xodim
    uchun bitta kunga bitta yozuv (`UNIQUE(employee_id, report_date)`) —
    qayta yuborilsa yangi qator yaratilmaydi, mavjudi yangilanadi (upsert,
    `services/daily_report_service.submit_daily_report`). `file_id` —
    Telegram'ning o'zi beradigan `photo`/`video` fayl identifikatori;
    tizimda fayl saqlash qatlami yo'q va bu uchun ham qurilmaydi — faqat
    shu satr saqlanadi, kerak bo'lganda Telegram API orqali qayta olinadi."""

    __tablename__ = "daily_report_submissions"
    __table_args__ = (
        UniqueConstraint("employee_id", "report_date", name="uq_daily_report_submissions_employee_date"),
    )

    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    # Hisobot QAYSI kalendar kun UCHUN (Toshkent vaqti) — jo'natilgan payt emas.
    report_date: Mapped[date_] = mapped_column(Date, nullable=False)
    file_id: Mapped[str] = mapped_column(String(200), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    employee: Mapped["Employee"] = relationship()
