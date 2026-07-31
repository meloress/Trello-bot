from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import Role

if TYPE_CHECKING:
    from db.models.brigade import Brigade
    from db.models.department import Department
    from db.models.kpi_log import KpiLog
    from db.models.stop_log import StopLog
    from db.models.task_assignment import TaskAssignment


def _default_payment_date() -> date:
    """8.5-band: oylik/avans kuni odatda har oyning 15-sanasi."""
    return date.today().replace(day=15)


class Employee(TimestampedBase):
    __tablename__ = "employees"

    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    trello_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 6.2-band: kartaga real a'zo qilib biriktirish uchun Trello'ning o'zi
    # beradigan a'zo ID'si (24 xonali hex) — `trello_username`dan farqli,
    # bu Trello API chaqiruvlarida (`idMembers`) ishlatiladigan qiymat.
    # `trello_username` kiritilganda `trello.get_member_id()` orqali
    # avtomatik olinadi (handlers/admin/employee_management.py).
    trello_member_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gmail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="employee_role", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    brigade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("brigades.id"), nullable=True)
    next_payment_date: Mapped[Optional[date]] = mapped_column(Date, default=_default_payment_date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Mini App profil ekrani: xodim tanlagan interfeys tili ("uz"/"ru").
    language: Mapped[str] = mapped_column(String(2), default="uz", server_default="uz", nullable=False)
    # SPEC.md §7/§8: bevosita rahbar. Bo'ysunuvchiga jarima ball yozilganda va
    # uning vazifasi muddatidan kechikkanda rahbar ham xabar oladi
    # (`notification_service._add_managers` / `notify_penalty_applied`).
    # `department_id`dan MUSTAQIL: bo'lim — qayerda ishlaydi, `manager_id` —
    # kimga hisobot beradi (ikkovi ko'pincha mos keladi, lekin har doim emas).
    # NULL = rahbar belgilanmagan, hech qanday qo'shimcha xabar ketmaydi.
    manager_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", name="fk_employees_manager_id"), nullable=True
    )
    # Eslatma: `daily_report_required` ustuni DB'da hali bor, lekin kunlik
    # rasm/video hisobot funksiyasi 2026-07-31'da rahbar talabiga ko'ra
    # butunlay olib tashlangan (faqat kod — ustun tegilmagan).
    # `server_default='false'` bo'lgani uchun modelda bo'lmasligi xavfsiz.

    department: Mapped[Optional["Department"]] = relationship(back_populates="employees")
    # employees<->brigades orasida ikkita mustaqil FK bor (brigades.brigadier_id va
    # employees.brigade_id), shuning uchun har ikkala tomonda ham foreign_keys aniq
    # ko'rsatiladi — aks holda SQLAlchemy qaysi ustunni ishlatishni bilolmaydi.
    led_brigades: Mapped[list["Brigade"]] = relationship(
        back_populates="brigadier", foreign_keys="Brigade.brigadier_id"
    )
    brigade: Mapped[Optional["Brigade"]] = relationship(
        back_populates="members", foreign_keys=[brigade_id]
    )
    manager: Mapped[Optional["Employee"]] = relationship(
        remote_side="Employee.id", foreign_keys=[manager_id]
    )
    task_assignments: Mapped[list["TaskAssignment"]] = relationship(back_populates="employee")
    kpi_logs: Mapped[list["KpiLog"]] = relationship(back_populates="employee")
    stop_logs: Mapped[list["StopLog"]] = relationship(back_populates="employee")
