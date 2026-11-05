from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import TimestampedBase


class OrderTopic(TimestampedBase):
    """Nazorat Trello zakaz kartasi -> guruhdagi topic (`jobs/order_topics_job.py`).
    Bir topicda bir nechta karta bo'lishi mumkin: bir raqamli FASAD+korpus
    kartalari yoki polniy uyning hamma zakazlari (`house_key`)."""

    __tablename__ = "order_topics"

    card_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    order_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    house_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # topicni shu karta nomi bilan ochgan bo'lsa — nom o'zgarsa topic ham qayta nomlanadi
    topic_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # oxirgi yuborilgan holat
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
