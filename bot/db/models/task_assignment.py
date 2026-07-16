from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee
    from db.models.task import Task


class TaskAssignment(TimestampedBase):
    """Vazifa <-> Xodim ko'p-ko'pga bog'lanishi (mas'ul xodim/brigadir/nachalnik)."""

    __tablename__ = "task_assignments"
    __table_args__ = (UniqueConstraint("task_id", "employee_id", name="uq_task_assignment"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="assignments")
    employee: Mapped["Employee"] = relationship(back_populates="task_assignments")
