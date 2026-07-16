from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee
    from db.models.task import Task


class StopLog(TimestampedBase):
    """"Stop" tugmasi hodisalari (7.5-band)."""

    __tablename__ = "stop_logs"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    stopped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="stop_logs")
    employee: Mapped["Employee"] = relationship(back_populates="stop_logs")
