from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.employee import Employee
    from db.models.lead import Lead


class CallLog(TimestampedBase):
    """13.2-band: qo'ng'iroqlar bazasi. Qo'lda kiritish (matn yoki Telegram
    ovozli xabar) — IP-telefoniya integratsiyasi KEYINGI, alohida loyihalash
    talab qiladigan ish (provayder hali tanlanmagan, foydalanuvchi bilan
    tasdiqlangan)."""

    __tablename__ = "call_logs"

    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", name="fk_call_logs_lead_id"), nullable=False)
    recorded_by_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", name="fk_call_logs_recorded_by_id"), nullable=False
    )
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    lead: Mapped["Lead"] = relationship()
    recorded_by: Mapped["Employee"] = relationship()
