from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.brigade import Brigade
    from db.models.employee import Employee
    from db.models.task import Task


class Department(TimestampedBase):
    """Yo'nalish/sex (Fasad sexi, Stolyar, Shkurka, Kraska va h.k.)."""

    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 7.1/7.2-band: shu yo'nalishga tegishli vazifalar qaysi Trello ro'yxatiga
    # (list) yoziladi. NULL = hali sozlanmagan — bunday yo'nalish uchun
    # task_service.create_task() aniq xato ko'taradi (raqamni o'zi taxmin qilmaydi).
    trello_list_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 6.1/7.4-band: standart ishlab chiqarish ketma-ketligidagi KEYINGI bo'lim
    # (masalan Stolyar.next -> Shkurka). NULL = zanjirning so'nggi bosqichi —
    # shu bo'limda vazifa yakunlansa, buyurtma to'liq COMPLETED bo'ladi
    # (task_service.advance_task_stage() shu ustunga qaraydi).
    next_department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", name="fk_departments_next_department_id"), nullable=True
    )
    # 8.3-band: "ba'zi yo'nalishlarda 2 kundan ortiq kechiksa, buyurtma
    # avtomatik boshqa brigadaga o'tkaziladi" — bu qoida barcha yo'nalishda
    # majburiy emas, shu sabab bo'lim darajasida yoqiladi/o'chiriladi
    # (admin panel, /autoreassign).
    auto_reassign_after_48h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    brigades: Mapped[list["Brigade"]] = relationship(back_populates="department")
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
    tasks: Mapped[list["Task"]] = relationship(back_populates="current_department")
    next_department: Mapped[Optional["Department"]] = relationship(
        remote_side="Department.id", foreign_keys=[next_department_id]
    )
