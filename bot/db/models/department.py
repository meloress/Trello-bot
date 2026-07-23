from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import TimestampedBase

if TYPE_CHECKING:
    from db.models.brigade import Brigade
    from db.models.employee import Employee
    from db.models.task import Task


class Department(TimestampedBase):
    """Yo'nalish/sex (Fasad sexi, Stolyar, Shkurka, Kraska va h.k.)."""

    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 7.1/7.2-band: shu yo'nalishga tegishli vazifalar qaysi Trello ro'yxatiga
    # (list) yoziladi. NULL = hali sozlanmagan — bunday yo'nalish uchun
    # task_service.create_task() aniq xato ko'taradi (raqamni o'zi taxmin qilmaydi).
    trello_list_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 6.1/7.4-band: standart ishlab chiqarish ketma-ketligidagi KEYINGI bo'lim
    # (masalan Stolyar.next -> Shkurka). NULL = zanjirning so'nggi bosqichi —
    # shu bo'limda vazifa yakunlansa, buyurtma to'liq COMPLETED bo'ladi
    # (task_service.advance_task_stage() shu ustunga qaraydi).
    next_department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", name="fk_departments_next_department_id"), nullable=True
    )
    # 8.3-band: "ba'zi yo'nalishlarda 2 kundan ortiq kechiksa, buyurtma
    # avtomatik boshqa brigadaga o'tkaziladi" — bu qoida barcha yo'nalishda
    # majburiy emas, shu sabab bo'lim darajasida yoqiladi/o'chiriladi
    # (admin panel, /autoreassign).
    auto_reassign_after_48h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Fasad sex TZ: ba'zi bo'limlarda buyurtma darhol ACTIVE emas, STOPPED
    # holatda ochiladi (joy tayyor bo'lishini kutish) — task_service.create_task()
    # shu bayroqqa qarab boshlang'ich holatni tanlaydi.
    starts_stopped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Fasad sex TZ (Phase 3): konvergensiya (join) bo'limi — bir nechta parallel
    # tarmoq shu bo'limga qaytib qo'shiladi. True bo'lsa,
    # task_service.advance_task_stage() bu bo'limga o'tishdan oldin BARCHA
    # qardosh tarmoqlar tugashini kutadi (fork nuqtasi esa
    # department_fork_targets jadvalida belgilanadi).
    requires_join: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Fasad sex TZ (Phase 0): shu bo'lim qaysi ishlab chiqarish moduliga
    # tegishli — "mebel" (asosiy, standart) yoki "fasad_sex" (yangi, parallel
    # zanjir). Oddiy VARCHAR, CHECK/enum emas (CLAUDE.md konvensiyasi) — 3-modul
    # keyinchalik qo'shilsa, migratsiya kod o'zgarishisiz kengayadi.
    module: Mapped[str] = mapped_column(String(20), nullable=False, default="mebel")
    # Fasad sex TZ, §9 "ikkinchi zavod": shu bo'lim qaysi FIZIK zavod/filialga
    # tegishli — `module`dan MUSTAQIL (module = qaysi ishlab chiqarish
    # tizimi, factory_name = qaysi jismoniy joylashuv). NULL = hali
    # belgilanmagan (bitta zavod bo'lgan davrdagi bo'limlar). Faqat statistikani
    # zavod bo'yicha ajratish uchun (stats_service.py), UI/CRUD'dan tashqari
    # boshqa hech qanday mantiqqa ta'sir qilmaydi.
    factory_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Fasad sex TZ (Phase 5): "Stop" bosilganda karta shu Trello ro'yxatiga
    # ko'chirilishi kerak bo'lgan bo'limlar uchun maqsad list (masalan
    # "stopda"). NULL = standart xatti-harakat — Stop faqat DB status/label
    # o'zgartiradi, karta joyidan qo'zg'almaydi (timer_service.stop_task()).
    # `trello_list_id`dan MUSTAQIL — Resume bosilganda karta ANIQ shu
    # ustunga emas, bo'limning ODATIY `trello_list_id`siga qaytariladi.
    stop_target_list_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    brigades: Mapped[list["Brigade"]] = relationship(back_populates="department")
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
    tasks: Mapped[list["Task"]] = relationship(back_populates="current_department")
    next_department: Mapped[Optional["Department"]] = relationship(
        remote_side="Department.id", foreign_keys=[next_department_id]
    )
