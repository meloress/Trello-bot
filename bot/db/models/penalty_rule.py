from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.department import Department


class PenaltyRule(TimestampedBase):
    """8.2-band: kechikish (soat) -> JAMI (kumulyativ) jarima balli.

    Har qator "[min_hours_late, max_hours_late) oralig'idagi kechikishda jami ball =
    score" ma'nosini beradi. max_hours_late=NULL — ochiq yuqori chegara ("va undan
    keyin ham"). Bu oraliqni qamrab olmagan kechikish (masalan, hali sozlanmagan
    96+ soat) uchun atayin HECH QANDAY qoida topilmaydi (oxirgi ma'lum qiymatga
    "yopishib qolmaydi") — shunday holatda tizim aniq xato ko'taradi, shu orqali
    yangi bosqich kodga tegmasdan, faqat yangi qator qo'shish orqali qo'shiladi.

    department_id=NULL -> barcha yo'nalishlarga tatbiq etiladigan global qoida;
    kerak bo'lsa muayyan yo'nalish uchun ustunlik beruvchi qator qo'shish mumkin
    (8.3-band: ba'zi yo'nalishlarda qoidalar boshqacha bo'lishi mumkin).
    """

    __tablename__ = "penalty_rules"

    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    min_hours_late: Mapped[int] = mapped_column(Integer, nullable=False)
    max_hours_late: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

    department: Mapped[Optional["Department"]] = relationship()
