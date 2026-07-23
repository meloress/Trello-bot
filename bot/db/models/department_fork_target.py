from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import TimestampedBase


class DepartmentForkTarget(TimestampedBase):
    """Fasad sex TZ (Phase 3): fork nuqtasi <-> parallel tarmoq bog'lanishi.

    `department_id` — bo'linish (fork) NUQTASI (masalan "Fayl yig'ish"),
    `target_department_id` — undan chiqadigan N parallel tarmoqdan biri
    (masalan "Korpus qismi"). Bir fork nuqtasi bir nechta target'ga ega
    bo'ladi — shu ko'p-qatorlik `next_department_id` (bitta bola) modeli
    ifodalay olmagan holatni beradi. Fork/join FAQAT shu jadvalga qator
    kiritilgan bo'limlar uchun ishlaydi; qolgan hamma bo'lim
    `next_department_id` bo'yicha o'zgarishsiz ishlaydi (task_service.
    advance_task_stage() shu jadvalni birinchi tekshiradi)."""

    __tablename__ = "department_fork_targets"
    __table_args__ = (
        UniqueConstraint("department_id", "target_department_id", name="uq_department_fork_target"),
    )

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", name="fk_department_fork_targets_department_id"), nullable=False
    )
    target_department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", name="fk_department_fork_targets_target_department_id"),
        nullable=False,
    )
