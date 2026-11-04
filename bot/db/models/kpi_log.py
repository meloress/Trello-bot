from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee


class KpiLog(TimestampedBase):
    """Minus/plus ball tarixi (8-band)."""

    __tablename__ = "kpi_logs"

    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    # Kasr (2026-11-04): Nazorat Trello jarimasi soatbay hisoblanadi (-1.5).
    score: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    employee: Mapped["Employee"] = relationship(back_populates="kpi_logs")
