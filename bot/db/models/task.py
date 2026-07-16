from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase
from utils.enums import TaskStatus, TaskType

if TYPE_CHECKING:
    from db.models.department import Department
    from db.models.stop_log import StopLog
    from db.models.task_assignment import TaskAssignment


class Task(TimestampedBase):
    """Ishlab chiqarish buyurtmasi (ORDER, Trello kartasiga mos) yoki alohida
    topshiriq (MISC, Trello'siz — 9-band)."""

    __tablename__ = "tasks"

    # ORDER uchun majburiy, MISC uchun har doim NULL (Trello'ga umuman
    # murojaat qilinmaydi) — shu sabab ustun DB darajasida nullable, "ORDER
    # bo'lsa albatta bo'lishi kerak" qoidasi task_service.py'da ta'minlanadi.
    # UNIQUE emas: ko'p bosqichli buyurtmada (6.1/7.4-band) bir nechta
    # bosqich-qatori BIR XIL kartani bo'lishadi (faqat bittasi COMPLETED
    # bo'lmagan holatda "joriy" hisoblanadi — bu ilova darajasidagi invariant,
    # task_repo.get_by_trello_card_id() shu qoidaga mos qaytaradi).
    trello_card_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=TaskType.ORDER,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # PENDING_SETUP holatida NULL — bo'limga endi kelgan bosqich uchun
    # nazoratchi/admin muddatni hali kiritmagan (task_service.advance_task_stage()).
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=TaskStatus.ACTIVE,
        nullable=False,
    )
    # MISC vazifa uchun bo'lim tanlash majburiy emas (TZ 9-band); belgilansa
    # birinchi tanlangan xodimning bo'limidan avtomatik olinadi (task_service.py).
    current_department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 6.1/7.4-band: bir xil buyurtmaning OLDINGI bosqichiga ishora (zanjir).
    # Ildiz bosqich (buyurtmaning birinchi qatori) uchun NULL.
    previous_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", name="fk_tasks_previous_task_id"), nullable=True
    )
    # 7.2-band: "1 kun qoldi" signali faqat bir marta yuborilishi uchun
    # (overdue_watch_job har soat qayta tekshiradi).
    day_left_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 8.3-band: brigadaga o'tkazish signali yuborilgan payt — qayta signal
    # yubormaslik uchun (overdue_watch_job).
    reassignment_signaled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 8.3-band: brigada QO'LDA almashtirilgan payt. Bo'lsa, yakuniy jarima
    # (penalty_service) `deadline` o'rniga shu vaqtdan hisoblanadi — eski
    # brigada allaqachon jarimalangan davrni yangi brigadaga qayta
    # hisoblamaslik uchun.
    reassigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 6.2-band: kartadagi "bosqichlar" checklist'i — bir xil trello_card_id'ni
    # bo'lishuvchi barcha bosqich-qatorlariga bir xil qiymat ko'chiriladi.
    trello_checklist_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    current_department: Mapped[Optional["Department"]] = relationship(back_populates="tasks")
    assignments: Mapped[list["TaskAssignment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    stop_logs: Mapped[list["StopLog"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    previous_task: Mapped[Optional["Task"]] = relationship(
        remote_side="Task.id", foreign_keys=[previous_task_id]
    )
