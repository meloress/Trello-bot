from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import LeadBrand, LeadStage

if TYPE_CHECKING:
    from db.models.client import Client
    from db.models.employee import Employee


class Lead(TimestampedBase):
    """13.1-band: sotuv varonkasi lidi. Ishlab chiqarish `tasks` jadvalidan
    TO'LIQ mustaqil — muddat/KPI jarima tizimiga umuman kirmaydi (5-bosqich
    hujjatidagi arxitektura qarori)."""

    __tablename__ = "leads"

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", name="fk_leads_client_id"), nullable=False)
    brand: Mapped[LeadBrand] = mapped_column(
        Enum(LeadBrand, name="lead_brand", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    stage: Mapped[LeadStage] = mapped_column(
        Enum(LeadStage, name="lead_stage", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=LeadStage.NEW_LEAD,
        nullable=False,
    )
    assigned_seller_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", name="fk_leads_assigned_seller_id"), nullable=False
    )
    trello_card_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 13.3-band: eng oxirgi qo'ng'iroq vaqti (yoki lid yaratilgan vaqt, hali
    # qo'ng'iroq bo'lmagan bo'lsa) — `jobs/lead_follow_up_job.py` shu ustunga
    # qarab "uzoq aloqasiz" lidlarni topadi (har safar join/aggregate qilish
    # o'rniga, `sales_service.add_call_log()` yozganda yangilanadi).
    last_contacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    client: Mapped["Client"] = relationship()
    assigned_seller: Mapped["Employee"] = relationship()
