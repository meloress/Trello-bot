from datetime import datetime, timedelta

from sqlalchemy import func, or_, select

from db.models.department import Department
from db.models.task import Task
from db.repositories.base import BaseRepository
from utils.enums import MiscCategory, TaskStatus, TaskType

_OPEN_STATUSES = [TaskStatus.ACTIVE, TaskStatus.STOPPED]


def _timer_running():
    """SPEC.md §6.1: `fasad_sex`da "Stop" taymerni MUZLATADI, ya'ni to'xtatilgan
    vazifa muddat o'tgani uchun OVERDUE bo'lmasligi ham, "1 kun qoldi"
    ogohlantirishini olishi ham kerak emas — to'xtab turgan vaqt
    `timer_service.resume_task()`da muddatga qo'shib beriladi.

    Mebelda esa "Stop" muddatga umuman ta'sir qilmaydi (u yerda muddat Trello
    kartadan keladi), shuning uchun STOPPED vazifalar avvalgidek hisobga
    olinaveradi. `coalesce(..., "mebel")` — bo'limi yo'q vazifalar (MISC)
    uchun ham eski xatti-harakat saqlanadi.

    LEFT JOIN bilan ishlatiladi, shuning uchun chaqiruvchi `outerjoin` qilishi
    shart."""
    return or_(
        Task.status == TaskStatus.ACTIVE,
        func.coalesce(Department.module, "mebel") == "mebel",
    )


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def get_by_trello_card_id(self, trello_card_id: str) -> Task | None:
        """Trello webhook/sinxronizatsiya kartani karta ID orqali topadi (6.3, 7.1-band).

        Ko'p bosqichli buyurtmada (6.1/7.4-band) bir nechta bosqich-qatori BIR
        XIL kartaga ishora qilishi mumkin (`task.py`dagi izohga qarang) — shu
        sabab faqat hali YAKUNLANMAGAN (joriy) qatorni qaytaramiz. Bir nechta
        mos qator bo'lsa ham (masalan ikkalasi ham COMPLETED emas holati
        bo'lishi mumkin emas, lekin himoya sifatida) eng oxirgisini olamiz."""
        result = await self.session.execute(
            select(Task)
            .where(Task.trello_card_id == trello_card_id, Task.status != TaskStatus.COMPLETED)
            .order_by(Task.id.desc())
        )
        return result.scalars().first()

    async def get_latest_by_trello_card_id(self, trello_card_id: str) -> Task | None:
        """Mebel moduli: `trello_ingest_job` uchun — `get_by_trello_card_id()`dan
        farqli, COMPLETED qatorlarni HAM qamraydi (eng oxirgi qator, status
        qanday bo'lishidan qat'iy nazar). Ingest job shu orqali "karta uchun
        umuman birorta qator bormi, va u qaysi holatda/bo'limda tugagan"
        ekanini aniqlaydi — yangi buyurtma / normal bosqich o'tishi /
        shubhali qayta paydo bo'lish holatlarini ajratish uchun."""
        result = await self.session.execute(
            select(Task).where(Task.trello_card_id == trello_card_id).order_by(Task.id.desc())
        )
        return result.scalars().first()

    async def list_by_previous_task_id(self, previous_task_id: int) -> list[Task]:
        """Fasad sex TZ (Phase 3, fork/join): bitta fork nuqtasidan chiqqan
        qardosh tarmoq-qatorlarini topish — hammasi bir xil
        `previous_task_id`ni (fork nuqtasining task id'si) ulashadi."""
        result = await self.session.execute(
            select(Task).where(Task.previous_task_id == previous_task_id)
        )
        return list(result.scalars().all())

    async def list_by_status(self, status: TaskStatus) -> list[Task]:
        """Kunlik label sinxronizatsiyasi va taymer job'lari uchun (6.3, 7.4-band)."""
        result = await self.session.execute(select(Task).where(Task.status == status))
        return list(result.scalars().all())

    async def list_by_type(
        self, task_type: TaskType, *, misc_category: MiscCategory | None = None
    ) -> list[Task]:
        """Fasad sex TZ, Phase 9 tuzatish: admin-tomonlama MISC vazifalar
        ro'yxati (`GET /admin/misctasks`) — bitta xodimning `task_assignments`
        yozuviga bog'liq emas, `list_by_employee`dagidan farqli, HAMMA MISC
        vazifalarni ko'radi. Ixtiyoriy `misc_category` filtri."""
        query = select(Task).where(Task.task_type == task_type)
        if misc_category is not None:
            query = query.where(Task.misc_category == misc_category)
        result = await self.session.execute(query.order_by(Task.id.desc()))
        return list(result.scalars().all())

    async def list_due_between(
        self, since: datetime, until: datetime, statuses: list[TaskStatus]
    ) -> list[Task]:
        """[since, until) oralig'ida muddati tugaydigan, berilgan status(lar)dagi
        vazifalar — kunlik eslatma job'i uchun (7.3-band)."""
        result = await self.session.execute(
            select(Task).where(
                Task.deadline >= since,
                Task.deadline < until,
                Task.status.in_(statuses),
            )
        )
        return list(result.scalars().all())

    async def list_deadline_approaching(self, *, now: datetime, within_hours: int = 24) -> list[Task]:
        """7.2-band: muddat tugashiga oz qoldi — hali signal yuborilmagan
        (`day_left_notified_at IS NULL`), muddati [now, now+within_hours)
        oralig'ida bo'lgan faol vazifalar (`overdue_watch_job`, soatiga bir
        marta). `within_hours` SPEC.md §5.4 bo'yicha sozlanadi
        (`app_settings.deadline_warning_hours`) — chaqiruvchi uzatadi."""
        threshold = now + timedelta(hours=within_hours)
        result = await self.session.execute(
            select(Task)
            .outerjoin(Department, Task.current_department_id == Department.id)
            .where(
                Task.status.in_(_OPEN_STATUSES),
                _timer_running(),
                Task.deadline.isnot(None),
                Task.deadline > now,
                Task.deadline <= threshold,
                Task.day_left_notified_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_newly_overdue(self, *, now: datetime) -> list[Task]:
        """7.2-band: muddati o'tib ketgan, lekin hali `OVERDUE` deb
        belgilanmagan vazifalar. To'xtatilgan `fasad_sex` vazifalari bu yerga
        TUSHMAYDI — `_timer_running()` izohiga qarang."""
        result = await self.session.execute(
            select(Task)
            .outerjoin(Department, Task.current_department_id == Department.id)
            .where(
                Task.status.in_(_OPEN_STATUSES),
                _timer_running(),
                Task.deadline.isnot(None),
                Task.deadline < now,
            )
        )
        return list(result.scalars().all())

    async def list_overdue_for_repeat_reminder(self, *, now: datetime, repeat_hours: int) -> list[Task]:
        """SPEC.md §5.4: "kechikish davom etsa, har M soatda takroriy eslatma".
        OVERDUE holatda turgan `fasad_sex` vazifalari — oxirgi takroriy
        eslatmadan (bo'lmasa: muddatning o'zidan) `repeat_hours` o'tgan
        bo'lsa qaytariladi.

        Mebel chetda: u yerda kechikish eslatmasi Trello oqimi va claim
        eslatmalari orqali boradi, ikkinchi kanal shovqin bo'lardi."""
        threshold = now - timedelta(hours=repeat_hours)
        result = await self.session.execute(
            select(Task)
            .join(Department, Task.current_department_id == Department.id)
            .where(
                Task.status == TaskStatus.OVERDUE,
                Department.module != "mebel",
                Task.deadline.isnot(None),
                func.coalesce(Task.last_overdue_reminder_at, Task.deadline) < threshold,
            )
        )
        return list(result.scalars().all())

    async def list_overdue_for_reassignment_check(
        self, *, now: datetime, hours_overdue: int = 48
    ) -> list[Task]:
        """8.3-band: bo'limi `auto_reassign_after_48h=True` bo'lgan, muddatidan
        `hours_overdue` soatdan ortiq o'tgan, hali signal berilmagan OVERDUE
        vazifalar."""
        threshold = now - timedelta(hours=hours_overdue)
        result = await self.session.execute(
            select(Task)
            .join(Department, Task.current_department_id == Department.id)
            .where(
                Task.status == TaskStatus.OVERDUE,
                Department.auto_reassign_after_48h.is_(True),
                Task.deadline < threshold,
                Task.reassignment_signaled_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_awaiting_reassignment_review(self) -> list[Task]:
        """8.3-band admin UI (Mini App): signal allaqachon berilgan
        (`reassignment_signaled_at`), hali OVERDUE va hali qo'lda ko'rib
        chiqilmagan (`reassigned_at IS NULL`) buyurtmalar ro'yxati."""
        result = await self.session.execute(
            select(Task).where(
                Task.status == TaskStatus.OVERDUE,
                Task.reassignment_signaled_at.isnot(None),
                Task.reassigned_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_stopped_for_auto_resume(self) -> list[Task]:
        """Fasad sex TZ (Sklad): STOPPED bosqichlar, bo'limida
        `stopped_auto_resume_after_hours` sozlangan bo'lsa — aniq necha soat
        o'tganini `overdue_watch_job` o'zi `StopLogRepository.get_active_stop()`
        orqali tekshiradi (bu yerda faqat nomzodlar ro'yxati)."""
        result = await self.session.execute(
            select(Task)
            .join(Department, Task.current_department_id == Department.id)
            .where(
                Task.status == TaskStatus.STOPPED,
                Department.stopped_auto_resume_after_hours.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def list_open_orders_excluding_module(self, excluded_module: str) -> list[Task]:
        """`daily_sync_job` uchun: ochiq (COMPLETED/PENDING_SETUP emas) ORDER
        vazifalar, lekin berilgan modulga (masalan "mebel") tegishli bo'lim
        chiqarib tashlanadi — bu modul endi Trello'ni bevosita, yuqori
        chastotali `jobs/trello_ingest_job.py` orqali kuzatadi. `current_
        department_id IS NULL` bo'lgan qatorlar (nazariy jihatdan bo'lmasligi
        kerak ORDER uchun, lekin himoya sifatida) chiqarib tashlanmaydi —
        modul tekshiruvi faqat bo'lim aniq bo'lganda qo'llaniladi."""
        result = await self.session.execute(
            select(Task)
            .join(Department, Task.current_department_id == Department.id, isouter=True)
            .where(
                Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.PENDING_SETUP]),
                Task.task_type == TaskType.ORDER,
                (Department.module != excluded_module) | (Task.current_department_id.is_(None)),
            )
        )
        return list(result.scalars().all())

