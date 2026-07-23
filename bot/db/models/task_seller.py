from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import TimestampedBase


class TaskSeller(TimestampedBase):
    """Fasad sex TZ: buyurtmaga biriktirilgan sotuvchi ("sotuvchi") — Stop
    bosilganda ham xabar olishi kerak bo'lgan qo'shimcha odam(lar). Shakli
    `task_assignments`ga o'xshash (task_id/employee_id, UNIQUE juftlik), lekin
    ma'nosi boshqa: bu KPI tayinlash emas, faqat bildirishnoma ro'yxati uchun
    (task_service.create_task()'da bittaga 3 tagacha cheklanadi)."""

    __tablename__ = "task_sellers"
    __table_args__ = (UniqueConstraint("task_id", "employee_id", name="uq_task_seller"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
