from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import ClaimActionType, ClaimStatus

if TYPE_CHECKING:
    from db.models.task import Task
    from db.models.employee import Employee


class TaskClaim(TimestampedBase):
    """Mebel moduli: ishchi Mini App'da "Pauza"/"Yakunlash" bosganda haqiqiy
    holat DARHOL o'zgarmaydi — shu yozuv yaratiladi va faqat bo'lim rahbari
    (SUPERVISOR/ADMIN) tasdiqlagandan keyingina `timer_service.stop_task`/
    `finish_task` chaqiriladi, `claimed_at`ni asl vaqt sifatida ishlatib
    (tasdiqlash necha soat/kun kechiksa ham, ball hisob-kitobiga ta'sir
    qilmasligi uchun). Rad etilsa — hech qanday task/StopLog mutatsiyasi
    bo'lmaydi, vazifa xuddi so'rov bo'lmagandek ACTIVE holatida qoladi.

    `financial_suggestions`ning xuddi shu "taklif qil, keyin odam hal
    qilsin" naqshi (`status=PENDING_MANAGER_REVIEW` -> inson qaror qiladi)."""

    __tablename__ = "task_claims"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", name="fk_task_claims_task_id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", name="fk_task_claims_employee_id"), nullable=False
    )
    action_type: Mapped[ClaimActionType] = mapped_column(
        Enum(ClaimActionType, name="claim_action_type", native_enum=False,
             values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status", native_enum=False,
             values_callable=lambda e: [m.value for m in e]),
        default=ClaimStatus.PENDING,
        nullable=False,
    )
    # Ishchi tugmani bosgan ANIQ vaqt — tasdiqlansa shu vaqt finished_at/
    # stopped_at'ga o'tadi, rahbar TASDIQLAGAN vaqt emas.
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # PAUSE uchun majburiy (servis darajasida tekshiriladi), FINISH uchun ixtiyoriy.
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", name="fk_task_claims_reviewed_by_employee_id"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Eskalatsiya eslatmalari uchun (overdue_watch_job): 0 = hali yuborilmagan,
    # 1/2/3 = +2/+6/+24 soatlik bosqichlardan qaysi biri oxirgi marta yuborilgan
    # (bir xil bosqich uchun qayta yubormaslik).
    last_reminder_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(foreign_keys=[task_id])
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])
    reviewed_by: Mapped[Optional["Employee"]] = relationship(foreign_keys=[reviewed_by_employee_id])
