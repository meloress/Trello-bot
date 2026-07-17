from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import TimestampedBase


class Client(TimestampedBase):
    """Mijoz (12-band: bosqich o'tganda/"Stop" bosilganda avtomatik xabarnoma
    uchun). Admin `task_service.create_task()` oqimida telefon raqami bo'yicha
    topadi yoki yaratadi (`client_service.find_or_create_client`); mijozning
    o'zi keyin `/mijoz` orqali telefon raqamini kiritib `telegram_id`sini
    bog'laydi (`registration_service.link_employee_to_telegram` bilan bir xil
    naqsh — client_service.link_client_to_telegram). `telegram_id=NULL` bo'lsa
    xabarnoma jim o'tkazib yuboriladi (SMS kanal ochiq savol #11 sabab hali yo'q).

    5-bosqich (Sotuv CRM) shu jadvalni qayta ishlatishi mumkin — shu sabab
    minimal va CRM-spetsifik bo'lmagan maydonlar bilan cheklangan."""

    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
