from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import FinancialSuggestionKind, FinancialSuggestionStatus

if TYPE_CHECKING:
    from db.models.task import Task


class FinancialSuggestion(TimestampedBase):
    """8.6-band: moliyaviy javobgarlik TAKLIFI (bayroqlash + summa hisob-kitobi).
    Tizim hech qachon pul ko'chirmaydi/maoshni o'zgartirmaydi — faqat shu
    yozuvni yaratadi, `status` doim `PENDING_MANAGER_REVIEW` bilan boshlanadi.
    Tasdiqlash/rad etish (approve/reject) BOSHQA modul zimmasida — bu yerda
    faqat interfeys (status maydoni) tayyor.

    Ikkita mustaqil qoida bitta jadvalda `kind` orqali ajratiladi (WAGE_DEDUCTION
    uchun stage_duration_days/amount_withheld_by_customer/suggested_deduction_amount,
    ADVANCE_WAIVER uchun advance_percent_paid/order_total_value/waived_amount —
    boshqa kind'ning maydonlari shunchaki NULL qoladi)."""

    __tablename__ = "financial_suggestions"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    kind: Mapped[FinancialSuggestionKind] = mapped_column(
        Enum(FinancialSuggestionKind, name="financial_suggestion_kind", native_enum=False,
             values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[FinancialSuggestionStatus] = mapped_column(
        Enum(FinancialSuggestionStatus, name="financial_suggestion_status", native_enum=False,
             values_callable=lambda e: [m.value for m in e]),
        default=FinancialSuggestionStatus.PENDING_MANAGER_REVIEW,
        nullable=False,
    )
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # WAGE_DEDUCTION (1-qoida: bo'lim aybi bilan mijozdan to'lov olinmasa)
    stage_duration_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amount_withheld_by_customer: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_deduction_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ADVANCE_WAIVER (2-qoida: 80% avans olingandan keyin kechikish)
    advance_percent_paid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_total_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    waived_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # SPEED_TIER_BONUS (Fasad sex TZ, Phase 7: bosqich tezligiga qarab to'lov
    # taklifi — bo'sh jadval bo'lsa yoki hech qaysi tier mos kelmasa yozuv
    # umuman yaratilmaydi, `financial_service.suggest_speed_tier_bonus`ga q.)
    speed_tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    suggested_pay_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    task: Mapped["Task"] = relationship()
