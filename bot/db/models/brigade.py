from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.department import Department
    from db.models.employee import Employee


class Brigade(TimestampedBase):
    __tablename__ = "brigades"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    brigadier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)

    department: Mapped["Department"] = relationship(back_populates="brigades")
    brigadier: Mapped[Optional["Employee"]] = relationship(
        back_populates="led_brigades", foreign_keys=[brigadier_id]
    )
    members: Mapped[list["Employee"]] = relationship(
        back_populates="brigade", foreign_keys="Employee.brigade_id"
    )
