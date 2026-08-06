"""Yangi vazifa yaratish va Trello bilan integratsiya (7.1-band).

`timer_service.py` mavjud vazifaning holatini boshqaradi; bu servis esa YANGI
vazifani Trello'da va bazada yaratadi. Tartib ataylab shunday: AVVAL Trello'da
karta ochiladi, FAQAT muvaffaqiyatli bo'lsagina bazaga yoziladi — aks holda
bazada Trello'siz "osilib qolgan" vazifa paydo bo'lardi. Aksincha tartib
(avval baza, keyin Trello) bazada Trello kartasiz vazifa qoldirib ketishi
mumkin edi, buni ataylab oldini oldik.

6.2-band (karta a'zo + checklist): bular ASOSIY vazifa yaratish/o'tkazish
oqimidan KEYIN, ikkinchi-darajali effekt sifatida bajariladi — xato bo'lsa
faqat log qilinadi, asosiy oqim (karta/baza yozuvi) allaqachon muvaffaqiyatli
bo'lgani uchun foydalanuvchiga soxta xatolik ko'rsatilmaydi.
"""

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from config import settings
from core.database import async_session
from db.models.task import Task
from db.repositories import (
    DepartmentForkTargetRepository,
    DepartmentRepository,
    EmployeeRepository,
    StopLogRepository,
    TaskAssignmentRepository,
    TaskRepository,
    TaskSellerRepository,
)
from services import penalty_service
from trello.client import TrelloClient
from utils.enums import MiscCategory, Role, TaskStatus, TaskType
from utils.formatters import TASHKENT_TZ
from utils.modules import MEBEL

logger = logging.getLogger(__name__)

# Trello kartasidagi a'zolardan KIM ijrochi bo'la oladi. Admin/nazoratchi/
# sotuvchi kartada bo'lishi mumkin (kuzatish uchun, yoki tasodifan) — bu ish
# tayinlash EMAS. Filtrsiz holatda haqiqiy ishlab chiqarish bazasida ADMIN
# hisobi vazifa ijrochisi bo'lib qolgan edi (task #129), va u hech qachon
# ball ololmasdi (`penalty_service` faqat ishchi/brigadirni hisoblaydi) —
# ya'ni vazifa butunlay KPI'dan tashqarida qolardi.
ASSIGNABLE_ROLES = (Role.WORKER, Role.BRIGADIER)


async def _trello_writes_disabled(department_id: int | None) -> bool:
    """Mebel moduli endi bir tomonlama (faqat Trello -> bot): shu bo'limlar
    uchun karta mutatsiyasi funksiyalari (a'zo qo'shish/olib tashlash,
    checklist yaratish) hech narsa qilmasligi kerak. `fasad_sex` uchun
    doim False qaytadi — xatti-harakat o'zgarishsiz qoladi."""
    if department_id is None:
        return False
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
    return department is not None and department.module == MEBEL


class DepartmentNotFoundError(Exception):
    """Berilgan department_id topilmadi."""


class DepartmentNotConfiguredError(Exception):
    """Department uchun Trello ro'yxati (trello_list_id) sozlanmagan."""


class TaskNotFoundError(Exception):
    """Berilgan task_id bo'yicha vazifa topilmadi."""


class InvalidTaskStateError(Exception):
    """So'ralgan amal vazifaning joriy holatiga mos kelmaydi."""


async def _collect_department_chain_names(
    department_repo: DepartmentRepository,
    fork_repo: DepartmentForkTargetRepository,
    start_department_id: int,
) -> list[str]:
    """6.2-band + Fasad sex Phase 3: checklist punktlari uchun bo'lim nomlari.

    Zanjir endi chiziqli emas, DAG bo'lishi mumkin (fork = fan-out, join =
    fan-in), shu sabab kenglik bo'yicha (BFS) + `visited` to'plami bilan
    yuriladi: fork nuqtasi barcha target'larni navbatga qo'yadi, join bo'limi
    esa bir nechta tarmoqdan yetib kelsa ham FAQAT BIR MARTA qo'shiladi.
    Fork YO'Q chiziqli zanjir uchun bu eski `while` sikli bilan AYNAN bir xil
    tartibdagi natijani beradi (regressiya kafolati)."""
    names: list[str] = []
    visited: set[int] = set()
    queue: deque[int | None] = deque([start_department_id])
    while queue:
        current_id = queue.popleft()
        if current_id is None or current_id in visited:
            continue
        department = await department_repo.get_by_id(current_id)
        if department is None:
            continue
        visited.add(current_id)
        names.append(department.name)
        fork_targets = await fork_repo.list_by_department(current_id)
        if fork_targets:
            for ft in fork_targets:
                queue.append(ft.target_department_id)
        elif department.next_department_id is not None:
            queue.append(department.next_department_id)
    return names


async def _add_members_to_card(card_id: str, employee_ids: list[int], department_id: int | None = None) -> None:
    """6.2-band: karta a'zolari. `trello_member_id` yo'q xodim — faqat
    log (ikkinchi-darajali, asosiy oqimni to'xtatmaydi)."""
    if await _trello_writes_disabled(department_id):
        return
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        employees = [await employee_repo.get_by_id(eid) for eid in employee_ids]

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for employee in employees:
            if employee is None:
                continue
            if not employee.trello_member_id:
                logger.warning(
                    "Xodim '%s' (id=%s) uchun trello_member_id yo'q — kartaga a'zo sifatida qo'shilmadi",
                    employee.full_name, employee.id,
                )
                continue
            try:
                await trello.add_member_to_card(card_id, employee.trello_member_id)
            except Exception:
                logger.exception(
                    "Xodim '%s' (id=%s) kartaga (%s) a'zo sifatida qo'shilmadi", employee.full_name, employee.id, card_id
                )


async def _remove_members_from_card(card_id: str, employee_ids: list[int], department_id: int | None = None) -> None:
    if await _trello_writes_disabled(department_id):
        return
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        employees = [await employee_repo.get_by_id(eid) for eid in employee_ids]

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        for employee in employees:
            if employee is None or not employee.trello_member_id:
                continue
            try:
                await trello.remove_member_from_card(card_id, employee.trello_member_id)
            except Exception:
                logger.exception(
                    "Xodim '%s' (id=%s) kartadan (%s) a'zolikdan chiqarilmadi", employee.full_name, employee.id, card_id
                )


async def _create_stage_checklist(task_id: int, card_id: str, department_id: int) -> None:
    """6.2-band: bo'lim zanjiri bo'yicha checklist — har bosqich (departament)
    uchun bitta punkt. `task.trello_checklist_id`ga yoziladi."""
    if await _trello_writes_disabled(department_id):
        return
    async with async_session() as session:
        chain_names = await _collect_department_chain_names(
            DepartmentRepository(session), DepartmentForkTargetRepository(session), department_id
        )

    try:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            checklist = await trello.create_checklist(card_id, "Bosqichlar")
            for name in chain_names:
                await trello.add_checklist_item(checklist["id"], name)
    except Exception:
        logger.exception("Task %s uchun checklist yaratilmadi (karta %s)", task_id, card_id)
        return

    async with async_session() as session:
        task_repo = TaskRepository(session)
        task = await task_repo.get_by_id(task_id)
        if task is not None:
            await task_repo.update(task, trello_checklist_id=checklist["id"])
            await session.commit()


async def create_task(
    title: str,
    description: str | None,
    deadline: datetime,
    department_id: int,
    employee_ids: list[int],
    client_id: int | None = None,
    created_by_employee_id: int | None = None,
    seller_ids: list[int] | None = None,
    is_urgent: bool = False,
) -> Task:
    seller_ids = list(dict.fromkeys(seller_ids or []))
    if len(seller_ids) > 3:
        raise ValueError("Bitta buyurtmaga ko'pi bilan 3 ta sotuvchi biriktirish mumkin")

    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
        if department is None:
            raise DepartmentNotFoundError(f"Department {department_id} topilmadi")
        if not department.trello_list_id:
            raise DepartmentNotConfiguredError(
                f"'{department.name}' yo'nalishi uchun Trello ro'yxati (list) sozlanmagan"
            )
        list_id = department.trello_list_id
        starts_stopped = department.starts_stopped

    if starts_stopped and created_by_employee_id is None:
        raise ValueError("starts_stopped bo'limlar uchun created_by_employee_id majburiy")

    async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
        card = await trello.create_card(list_id=list_id, name=title, desc=description or "", due=deadline)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.create(
            trello_card_id=card["id"],
            task_type=TaskType.ORDER,
            title=title,
            description=description,
            deadline=deadline,
            status=TaskStatus.STOPPED if starts_stopped else TaskStatus.ACTIVE,
            current_department_id=department_id,
            started_at=datetime.now(timezone.utc),
            client_id=client_id,
            # SPEC.md §5.2: srochnost butun buyurtmaga tegishli — keyingi
            # bosqichlarga `_spawn_pending_stage()` orqali ko'chib boradi va
            # o'sha bo'limlarning `sla_urgent_hours`ini faollashtiradi.
            is_urgent=is_urgent,
        )

        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        if seller_ids:
            seller_repo = TaskSellerRepository(session)
            for seller_id in seller_ids:
                await seller_repo.create(task_id=task.id, employee_id=seller_id)

        if starts_stopped:
            # Fasad sex TZ: "joy tayyor bo'lishini kutish" — STOPPED holatda
            # ochilgan vazifa ham resume_task() orqali davom ettirilishi
            # kerak, u esa faol stop_log talab qiladi (get_active_stop()).
            await StopLogRepository(session).create(
                task_id=task.id,
                employee_id=created_by_employee_id,
                reason="Buyurtma qabul qilindi — joy tayyor bo'lishini kutmoqda",
                stopped_at=datetime.now(timezone.utc),
                resumed_at=None,
            )

        await session.commit()

    try:
        await _add_members_to_card(card["id"], employee_ids, department_id=department_id)
    except Exception:
        logger.exception("Task %s uchun karta a'zolari qo'shilmadi", task.id)

    await _create_stage_checklist(task.id, card["id"], department_id)

    return task


async def sync_trello_card_stage(
    *,
    department_id: int,
    card_id: str,
    title: str,
    description: str | None,
    deadline: datetime,
    member_trello_ids: list[str],
    previous_task_id: int | None = None,
    client_id: int | None = None,
    trello_list_id: str | None = None,
) -> Task | None:
    """Mebel moduli: Trello-birinchi kirish nuqtasi (`jobs/trello_ingest_job.py`
    chaqiradi, keyingi vazifada qo'shiladi). Trello endi yagona manba — bu
    funksiya HECH QANDAY Trello yozuvi qilmaydi, faqat allaqachon Trello'da
    mavjud karta holatini bazaga aks ettiradi. Ham yangi buyurtma
    (`previous_task_id=None`), ham bosqich o'tishi (`previous_task_id`=eski
    qator) uchun ishlatiladi — ikkalasi ham bir xil "karta + a'zo(lar) +
    muddat allaqachon ma'lum" holatidan boshlanadi, shuning uchun
    `PENDING_SETUP` oraliq bosqichi endi kerak emas (solishtiring:
    `activate_pending_stage()` — u yerda muddat/xodim hali botda qo'lda
    kiritilishi kerak edi, bu yerda ikkalasi ham Trello kartadan allaqachon
    ma'lum)."""
    async with async_session() as session:
        department = await DepartmentRepository(session).get_by_id(department_id)
        if department is None:
            logger.warning("sync_trello_card_stage: bo'lim %s topilmadi (karta %s)", department_id, card_id)
            return None

        employee_repo = EmployeeRepository(session)
        resolved = []
        for trello_member_id in member_trello_ids:
            employee = await employee_repo.get_by_trello_member_id(trello_member_id)
            if employee is not None and employee.is_active and employee.role in ASSIGNABLE_ROLES:
                resolved.append(employee)

        if not resolved:
            logger.warning(
                "sync_trello_card_stage: karta %s uchun hech qanday tanish IJROCHI topilmadi (a'zolar: %s)",
                card_id, member_trello_ids,
            )
            return None

        # Kartadagi BARCHA tanish ishchi vazifaga biriktiriladi — brigadir
        # Trello'da ishni bir nechta ishchiga bo'lib beradi, va ularning
        # HAMMASIGA xabar borishi kerak. Avval faqat bittasi (yoki brigadir)
        # tayinlanardi, ya'ni brigadir 3 ta ishchi qo'shsa 2 tasi ishdan
        # butunlay bexabar qolardi. Ishchi umuman bo'lmasa (brigadir kartani
        # o'ziga olgan, hali bo'lib bermagan) — brigadir(lar) tayinlanadi,
        # javobgarlik o'shanda qoladi (penalty_service ham shunga mos: ishchi
        # bo'lmasa ball brigadirning o'ziga yoziladi).
        workers = [e for e in resolved if e.role == Role.WORKER]
        assignees = workers or [e for e in resolved if e.role == Role.BRIGADIER]
        if not assignees:
            logger.warning(
                "sync_trello_card_stage: karta %s a'zolari orasida ishchi/brigadir yo'q", card_id
            )
            return None

        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.create(
            trello_card_id=card_id,
            task_type=TaskType.ORDER,
            title=title,
            description=description,
            deadline=deadline,
            status=TaskStatus.ACTIVE,
            current_department_id=department_id,
            started_at=datetime.now(timezone.utc),
            previous_task_id=previous_task_id,
            client_id=client_id,
            trello_last_seen_list_id=trello_list_id or department.trello_list_id,
            trello_last_seen_member_ids=list(member_trello_ids),
            trello_last_polled_at=datetime.now(timezone.utc),
        )
        for assignee in assignees:
            await assignment_repo.create(task_id=task.id, employee_id=assignee.id)

        await session.commit()
        return task


async def set_assignees_from_trello(task_id: int, new_employee_ids: list[int]) -> Task:
    """Mebel moduli: karta a'zolari Trello'da o'zgarganda chaqiriladi
    (`jobs/trello_ingest_job.py`) — jarima yo'q, Trello yozuvi yo'q, faqat
    `task_assignments`ni to'liq almashtiradi (`delegate_task()`/
    `reassign_task_brigade()`dagi bilan bir xil "to'liq almashtirish"
    qoidasi — qisman birgalikda egalik qilish yo'q).

    Ro'yxat qabul qiladi, chunki brigadir bitta ishni bir nechta ishchiga
    bo'lib berishi mumkin va ularning hammasi biriktirilishi kerak."""
    if not new_employee_ids:
        raise ValueError("new_employee_ids bo'sh bo'lishi mumkin emas")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")

        for assignment in await assignment_repo.list_by_task(task_id):
            await assignment_repo.delete(assignment)
        for employee_id in new_employee_ids:
            await assignment_repo.create(task_id=task_id, employee_id=employee_id)

        await session.commit()
        return task


async def _is_same_sla_block(session, department, previous_task) -> bool:
    """SPEC.md §5.3: yangi bosqich OLDINGISI bilan bir xil SLA blokidami?
    Shunday bo'lsa muddat qayta hisoblanmaydi — blokka kirganda qo'yilgani
    ko'chib boraveradi (blok ichida erkin harakat, chiqish esa umumiy
    muddat ichida)."""
    if department.sla_block_id is None or previous_task is None:
        return False
    if previous_task.current_department_id is None:
        return False
    previous_department = await DepartmentRepository(session).get_by_id(previous_task.current_department_id)
    return previous_department is not None and previous_department.sla_block_id == department.sla_block_id


async def _sla_hours_for_stage(session, department, previous_task) -> int | None:
    """SPEC.md §5.1 + §5.2: shu bosqich uchun necha soat muddat berilishi.
    `None` = SLA sozlanmagan, muddat qo'lda kiritiladi.

    §5.2 navbat qoidasi faqat `daily_quota_orders` VA `sla_over_quota_hours`
    ikkalasi ham sozlangan bo'limlarda ishlaydi (chizish bosqichi); qolgan
    hamma bo'limda oddiy `default_sla_hours` qaytadi."""
    if previous_task is not None and previous_task.is_urgent and department.sla_urgent_hours:
        return department.sla_urgent_hours

    if department.daily_quota_orders and department.sla_over_quota_hours:
        # Kun chegarasi Toshkent bo'yicha: "bir kunda tushgan zakazlar"
        # rahbar uchun mahalliy kalendar kun, UTC sutkasi emas.
        now_local = datetime.now(TASHKENT_TZ)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        created_today = await TaskRepository(session).count_created_in_department_since(
            department_id=department.id, since=day_start
        )
        # `created_today` — bu bosqich YARATILISHIDAN oldingi son, ya'ni
        # hozirgi buyurtmaning kun ichidagi tartibi `created_today + 1`.
        if created_today + 1 > department.daily_quota_orders:
            return department.sla_over_quota_hours

    return department.default_sla_hours


async def resolve_stage_deadline(session, department, previous_task) -> datetime | None:
    """SPEC.md §5.1/§5.2/§5.3: yangi bosqich muddatini aniqlaydi.

    `None` = muddat qo'yilmaydi (nazoratchi qo'lda kiritadi) — SLA
    sozlanmagan bo'lim, yoki mebel moduli (u yerda muddat Trello
    kartadan/list nomidan keladi, bu ustunlar umuman o'qilmaydi)."""
    if department is None or department.module == MEBEL:
        return None

    if await _is_same_sla_block(session, department, previous_task):
        return previous_task.deadline

    hours = await _sla_hours_for_stage(session, department, previous_task)
    return datetime.now(timezone.utc) + timedelta(hours=hours) if hours else None


async def _spawn_pending_stage(
    session,
    *,
    department_id: int,
    previous_task_id: int,
    card_id: str | None,
    checklist_id: str | None,
    title: str,
    description: str | None,
    client_id: int | None,
) -> Task:
    """Yangi `PENDING_SETUP` bosqich-qatorini yaratadi (xodim hali YO'Q).
    Chiziqli (bitta bola) va fork (N bola) yo'llari BIR XIL qatorni yaratadi,
    faqat `department_id`da farq qiladi — shu sabab bitta joyda.

    SPEC.md §5.1: bo'lim `default_sla_hours` sozlagan bo'lsa (faqat
    `fasad_sex`), muddat SHU YERDA — buyurtma bosqichga kirgan aniq paytda —
    oldindan hisoblanadi: `deadline = now + SLA`. Bosqich baribir
    `PENDING_SETUP` bo'lib qoladi, chunki u IKKI narsani kutadi (muddat VA
    xodim) — SLA faqat birinchisini yechadi. Muhim yutuq shunda: taymer
    nazoratchi tugmani bosgan paytdan emas, buyurtma haqiqatda bosqichga
    o'tgan paytdan ketadi (TZ aynan shuni talab qiladi). SLA sozlanmagan
    bo'lsa `None` — muddat butunlay qo'lda kiritiladi (eski xatti-harakat).
    Aniq qoidalar (navbat, blok) `resolve_stage_deadline()`da."""
    department = await DepartmentRepository(session).get_by_id(department_id)
    previous_task = await TaskRepository(session).get_by_id(previous_task_id) if previous_task_id else None
    deadline = await resolve_stage_deadline(session, department, previous_task)

    new_task = await TaskRepository(session).create(
        trello_card_id=card_id,
        task_type=TaskType.ORDER,
        title=title,
        description=description,
        deadline=deadline,
        status=TaskStatus.PENDING_SETUP,
        current_department_id=department_id,
        started_at=datetime.now(timezone.utc),
        previous_task_id=previous_task_id,
        trello_checklist_id=checklist_id,
        client_id=client_id,
        # SPEC.md §5.2: "srochniy" butun buyurtmaga tegishli, bitta bosqichga
        # emas — `client_id`/`trello_checklist_id` kabi zanjir bo'ylab ko'chadi.
        is_urgent=bool(previous_task is not None and previous_task.is_urgent),
    )

    # TZ 3.4/5.3-band: sotuvchi ham SHU BUYURTMAGA biriktirilgan, bitta
    # bosqichiga emas — shuning uchun `client_id` kabi zanjir bo'ylab ko'chadi.
    # Avval `task_sellers` FAQAT `create_task()`da yozilardi, ya'ni
    # `notify_task_stopped()` (u joriy bosqich-qatorining sotuvchilarini
    # o'qiydi) sotuvchini faqat BIRINCHI bosqichda topardi — keyingi 15+
    # bosqichda "Stop" bosilsa sotuvchiga umuman xabar bormasdi.
    seller_repo = TaskSellerRepository(session)
    for seller in await seller_repo.list_by_task(previous_task_id):
        await seller_repo.create(task_id=new_task.id, employee_id=seller.employee_id)

    return new_task


async def advance_task_stage(completed_task_id: int) -> Task | list[Task] | None:
    """6.1/7.4-band + Fasad sex Phase 3 (fork/join): ko'p bosqichli buyurtma
    progressiyasi. Bosqich yakunlanganda (ishchining "Yakunlash" tugmasi
    orqali) chaqiriladi.

    Qaytish qiymati uch xil:
    - `list[Task]` — joriy bo'lim FORK NUQTASI (`department_fork_targets`da
      qatori bor): har bir target uchun bitta `PENDING_SETUP` bosqich-qatori
      yaratiladi, hammasi bir xil `previous_task_id`ni ulashadi. Trello karta
      KO'CHIRILMAYDI (bitta karta 3 list'da tura olmaydi — u fork nuqtasi
      list'ida qoladi, parallel jarayon checklist orqali ko'rinadi).
    - `Task` — oddiy chiziqli o'tish (yoki join bo'limiga o'tishning OXIRGI
      tarmog'i): karta keyingi bo'lim list'iga ko'chiriladi, bitta yangi
      bosqich yaratiladi (eskicha xatti-harakat, o'zgarishsiz).
    - `None` — IKKI ma'no: (a) buyurtma to'liq tugadi (`next_department_id`
      yo'q), YOKI (b) join bo'limiga o'tish, lekin bu tarmoq faqat bittasi
      tugadi — qardosh tarmoqlar hali tugamagan, shu sabab yangi bosqich
      HALI yaratilmaydi (bu tarmoqning checklist punkti belgilanadi va
      xodimlari kartadan olinadi, ammo karta ko'chmaydi).

    Yangi bosqich `PENDING_SETUP` holatida (muddat/xodim hali YO'Q — buni
    nazoratchi/admin `activate_pending_stage()` orqali kiritadi, C.2-band).

    MUHIM: bu funksiya `timer_service.finish_task()` ICHIDAN chaqirilMAYDI —
    faqat ishchining "Yakunlash" handler'i orqali. `daily_sync_job`ning Trello
    karta arxivlanganda avtomatik yopish yo'li buni chaqirmaydi."""
    async with async_session() as session:
        task_repo = TaskRepository(session)
        department_repo = DepartmentRepository(session)
        assignment_repo = TaskAssignmentRepository(session)
        fork_repo = DepartmentForkTargetRepository(session)

        completed_task = await task_repo.get_by_id(completed_task_id)
        if completed_task is None:
            raise TaskNotFoundError(f"Task {completed_task_id} topilmadi")
        if completed_task.current_department_id is None:
            return None

        current_department = await department_repo.get_by_id(completed_task.current_department_id)
        if current_department is None:
            return None

        # Umumiy (har uch yo'l uchun kerak) — detach bo'lgan obyektlarga
        # keyin murojaat qilmaslik uchun shu yerda snapshot olinadi.
        card_id = completed_task.trello_card_id
        checklist_id = completed_task.trello_checklist_id
        current_department_name = current_department.name
        current_department_id = current_department.id
        title = completed_task.title
        description = completed_task.description
        client_id = completed_task.client_id
        old_employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(completed_task_id)]

        fork_targets = await fork_repo.list_by_department(current_department.id)

        # Yo'nalishni aniqlash: "fork" | "advance" | "wait" | "terminal".
        target_department_ids: list[int] = []
        next_department_id: int | None = None
        next_list_id: str | None = None
        is_join = False
        if fork_targets:
            mode = "fork"
            target_department_ids = [ft.target_department_id for ft in fork_targets]
        elif current_department.next_department_id is None:
            mode = "terminal"
        else:
            next_department = await department_repo.get_by_id(current_department.next_department_id)
            if next_department is None:
                return None
            if not next_department.trello_list_id:
                raise DepartmentNotConfiguredError(
                    f"'{next_department.name}' yo'nalishi uchun Trello ro'yxati (list) sozlanmagan"
                )
            next_department_id = next_department.id
            next_list_id = next_department.trello_list_id
            if next_department.requires_join and completed_task.previous_task_id is not None:
                # ponytail: sibling lookup assumes a fork branch is exactly one
                # department deep; if a future branch needs its own multi-stage
                # sub-chain before rejoining, propagate a fork_root_task_id
                # forward through each branch's own advance_task_stage() calls
                # (same way client_id/trello_checklist_id are already copied
                # forward today) and query that instead of previous_task_id.
                siblings = await task_repo.list_by_previous_task_id(completed_task.previous_task_id)
                if all(s.status == TaskStatus.COMPLETED for s in siblings):
                    mode = "advance"  # oxirgi tarmoq — join bosqichini yaratamiz
                    is_join = True
                else:
                    mode = "wait"  # boshqa tarmoqlar hali tugamagan
            else:
                mode = "advance"

    if mode == "terminal":
        return None

    # Trello ikkinchi-darajali effektlari: fork/advance/wait — hammasi joriy
    # bosqich checklist punktini belgilaydi va xodimlarini kartadan oladi;
    # FAQAT "advance" kartani keyingi list'ga ko'chiradi.
    if card_id:
        async with TrelloClient(settings.trello_api_key, settings.trello_token) as trello:
            if mode == "advance":
                await trello.move_card_to_list(card_id, next_list_id)

            if checklist_id:
                try:
                    await trello.check_checklist_item_by_name(card_id, checklist_id, current_department_name)
                except Exception:
                    logger.exception(
                        "Task %s: checklist punkti '%s' belgilanmadi", completed_task_id, current_department_name
                    )

        if old_employee_ids:
            try:
                await _remove_members_from_card(card_id, old_employee_ids, department_id=current_department_id)
            except Exception:
                logger.exception("Task %s: eski bosqich xodimlari kartadan olib tashlanmadi", completed_task_id)

    if mode == "wait":
        return None

    async with async_session() as session:
        if mode == "fork":
            # Note: a fork-branch department stays at the fork-point's Trello
            # list until join fires (card never moves on fork). If that branch's
            # department also has stop_target_list_id set (Phase 5), stopping
            # and resuming it will move the shared card to the branch's own
            # list instead — cosmetic Trello-position confusion only, the join
            # itself is DB-status-based and unaffected. Worth knowing before
            # enabling both features on the same chain.
            new_tasks = [
                await _spawn_pending_stage(
                    session,
                    department_id=dept_id,
                    previous_task_id=completed_task_id,
                    card_id=card_id,
                    checklist_id=checklist_id,
                    title=title,
                    description=description,
                    client_id=client_id,
                )
                for dept_id in target_department_ids
            ]
            await session.commit()
            return new_tasks

        if is_join and card_id:
            # Race guard: two branches finishing near-simultaneously can both
            # pass the "all siblings COMPLETED" check above before either has
            # created the join task. A plain check-then-insert here isn't
            # enough — both concurrent calls can pass the check before either
            # commits. pg_advisory_xact_lock serializes them: the second call
            # blocks here until the first commits (and releases the lock at
            # commit/rollback), so its re-check below correctly sees the
            # first call's already-created join task.
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:card_id))"), {"card_id": card_id})
            # `get_by_trello_card_id` returns the card's current (non-COMPLETED)
            # row, which is exactly the join task if a racing call beat us to it.
            current_for_card = await task_repo.get_by_trello_card_id(card_id)
            if current_for_card is not None and current_for_card.current_department_id == next_department_id:
                return current_for_card

        next_task = await _spawn_pending_stage(
            session,
            department_id=next_department_id,
            previous_task_id=completed_task_id,
            card_id=card_id,
            checklist_id=checklist_id,
            title=title,
            description=description,
            client_id=client_id,
        )
        await session.commit()
        return next_task


async def activate_pending_stage(
    task_id: int, *, deadline: datetime | None = None, employee_ids: list[int]
) -> Task:
    """6.1/7.4-band: nazoratchi/admin `PENDING_SETUP` bosqichga muddat va
    xodim(lar)ni belgilagach chaqiriladi. Karta joyi allaqachon
    `advance_task_stage()`da ko'chirilgan — bu yerda faqat muddat/xodim
    yozilib, taymer (`status=ACTIVE`) boshlanadi. 6.2-band: yangi bosqich
    xodimlari kartaga a'zo sifatida qo'shiladi (bu funksiyaga birinchi
    Trello a'zo chaqiruvi — eski bosqichda bu ish `advance_task_stage()`da
    bajarilgan).

    SPEC.md §5.1: `deadline=None` bo'lsa mavjud muddat SAQLANADI — bo'limning
    `default_sla_hours`i uni `_spawn_pending_stage()`da allaqachon
    hisoblagan bo'lishi mumkin, va o'sha qiymat to'g'ri (buyurtma bosqichga
    kirgan paytdan hisoblangan). Nazoratchi aniq qiymat bersa — bekor
    qiladi. Ikkalasi ham bo'lmasa vazifa muddatsiz ACTIVE bo'ladi (SLA
    sozlanmagan bo'lim), bu eski xatti-harakat bilan bir xil."""
    if not employee_ids:
        raise ValueError("Kamida bitta xodim tanlanishi kerak")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.PENDING_SETUP:
            raise InvalidTaskStateError(
                f"Task {task_id} sozlashni kutmayapti (joriy holat: {task.status})"
            )

        # ponytail: mirrors create_task()'s starts_stopped block above — a
        # mid-chain department (e.g. Sklad) can ALSO open its stage STOPPED,
        # unlike the "only honored at creation" note that used to apply here.
        department = (
            await DepartmentRepository(session).get_by_id(task.current_department_id)
            if task.current_department_id
            else None
        )
        starts_stopped = department is not None and department.starts_stopped

        await task_repo.update(
            task,
            deadline=deadline if deadline is not None else task.deadline,
            status=TaskStatus.STOPPED if starts_stopped else TaskStatus.ACTIVE,
        )
        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        if starts_stopped:
            await StopLogRepository(session).create(
                task_id=task.id,
                employee_id=employee_ids[0],
                reason="Bosqich boshlandi — joy tayyor bo'lishini kutmoqda",
                stopped_at=datetime.now(timezone.utc),
            )

        await session.commit()
        card_id = task.trello_card_id
        department_id = task.current_department_id

    if card_id:
        try:
            await _add_members_to_card(card_id, employee_ids, department_id=department_id)
        except Exception:
            logger.exception("Task %s: yangi bosqich xodimlari kartaga qo'shilmadi", task_id)

    return task


async def delegate_task(task_id: int, *, brigadier_id: int, worker_ids: list[int]) -> Task:
    """Ikki bosqichli tayinlash oqimi: `create_task()`/`activate_pending_stage()`
    endi vazifani to'g'ridan-to'g'ri ishchiga emas, BRIGADIRga beradi (Mini App
    yangi vazifa/bosqich yaratishda endi xodim emas, brigadir tanlatadi) —
    brigadir Mini App'da o'ziga tushgan vazifani ko'radi va shu yerda o'z
    brigadasidagi xodim(lar)ga topshiradi. Eski `task_assignments' (brigadir)
    to'liq o'chiriladi, tanlangan xodim(lar) qo'shiladi — `reassign_task_
    brigade()`dagi bilan bir xil "to'liq almashtirish" qoidasi (qisman
    birgalikda egalik qilish yo'q). Brigadirning o'zi hech qachon
    `task_assignments`da qolmaydi, lekin bu KPI ulushini yo'qotmaydi —
    `penalty_service`dagi brigadir ulushi `brigades.brigadier_id` orqali
    avtomatik hisoblanadi, `task_assignments`da qatnashishga bog'liq emas."""
    if not worker_ids:
        raise ValueError("Kamida bitta xodim tanlanishi kerak")

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")

        current_assignments = await assignment_repo.list_by_task(task_id)
        if brigadier_id not in {a.employee_id for a in current_assignments}:
            raise InvalidTaskStateError("Bu vazifa sizga tayinlanmagan")

        for assignment in current_assignments:
            await assignment_repo.delete(assignment)
        for worker_id in worker_ids:
            await assignment_repo.create(task_id=task_id, employee_id=worker_id)

        await session.commit()
        card_id = task.trello_card_id
        department_id = task.current_department_id

    if card_id:
        try:
            await _remove_members_from_card(card_id, [brigadier_id], department_id=department_id)
        except Exception:
            logger.exception("Task %s: brigadir kartadan olib tashlanmadi", task_id)
        try:
            await _add_members_to_card(card_id, worker_ids, department_id=department_id)
        except Exception:
            logger.exception("Task %s: xodim(lar) kartaga qo'shilmadi", task_id)

    return task


async def reassign_task_brigade(task_id: int, new_brigade_id: int, bot=None) -> Task:
    """8.3-band: uzoq kechikkan (OVERDUE, avtomatik aniqlangan —
    `overdue_watch_job._process_reassignment_signals`) buyurtmani boshqa
    brigadaga QO'LDA o'tkazish (yakuniy tasdiq rahbarda,
    `handlers/admin/reassign_task.py`). Ikkiga bo'lingan jarima mantig'i
    (foydalanuvchi tasdiqlagan qaror): eski brigadaga DARHOL to'liq jarima
    (hozirgi vaqtga nisbatan kechikish), yangi brigada uchun hisoblash
    bazasi shu o'tkazish vaqtidan boshlanadi (`task.reassigned_at` —
    `calculate_and_apply_task_penalty()` shunga qarab `deadline` o'rniga
    shu vaqtdan hisoblaydi). Task `COMPLETED` qilinmaydi — taymer davom etadi."""
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)
        employee_repo = EmployeeRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} topilmadi")
        if task.status != TaskStatus.OVERDUE:
            raise InvalidTaskStateError(
                f"Task {task_id} OVERDUE emas, brigadaga o'tkazib bo'lmaydi (joriy holat: {task.status})"
            )

        new_employees = await employee_repo.list_by_brigade(new_brigade_id)
        new_employee_ids = [e.id for e in new_employees]
        if not new_employee_ids:
            raise ValueError(f"Brigada {new_brigade_id}da faol xodim yo'q")

        old_employee_ids = [a.employee_id for a in await assignment_repo.list_by_task(task_id)]
        department_id = task.current_department_id
        deadline = task.deadline
        card_id = task.trello_card_id

    hours_late = int((now - deadline).total_seconds() // 3600)
    kpi_logs = await penalty_service.apply_penalty_for_employees(
        task_id=task_id,
        department_id=department_id,
        employee_ids=old_employee_ids,
        hours_late=hours_late,
        reason_label="Brigadaga o'tkazish (eski brigada, darhol jarima)",
    )
    # Yozilgan ball haqida eski brigada xodimlariga xabar — avval bu yozuvlar
    # jim tashlab yuborilardi (jarima yozilardi, lekin hech kim bilmasdi).
    await penalty_service.notify_kpi_logs(bot, kpi_logs)

    async with async_session() as session:
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        task = await task_repo.get_by_id(task_id)
        for assignment in await assignment_repo.list_by_task(task_id):
            await assignment_repo.delete(assignment)
        for employee_id in new_employee_ids:
            await assignment_repo.create(task_id=task_id, employee_id=employee_id)

        await task_repo.update(task, reassigned_at=now)
        await session.commit()

    if card_id:
        try:
            await _remove_members_from_card(card_id, old_employee_ids, department_id=department_id)
        except Exception:
            logger.exception("Task %s: eski brigada a'zolari kartadan olib tashlanmadi", task_id)
        try:
            await _add_members_to_card(card_id, new_employee_ids, department_id=department_id)
        except Exception:
            logger.exception("Task %s: yangi brigada a'zolari kartaga qo'shilmadi", task_id)

    return task


async def create_misc_task(
    *, text: str, deadline: datetime, employee_ids: list[int], category: MiscCategory | None = None
) -> Task:
    """9-band: "Vazifalar" moduli — Trello'siz, faqat tizim ichida
    boshqariladigan alohida topshiriq (masalan "Ofisni tozalash"). Trello'ga
    HECH QANDAY murojaat qilinmaydi — faqat bazaga yoziladi. Bildirishnoma
    bu funksiya ichida YUBORILMAYDI (chaqiruvchi handler
    `notification_service.notify_task_started()` orqali o'zi yuboradi —
    `create_task()` bilan bir xil naqsh).

    `category`: Fasad sex TZ, Phase 9 — ixtiyoriy MISC kategoriya belgisi
    (`None` bo'lsa avvalgidek, kategoriyasiz vazifa).

    TZ 9-band: "Bitta vazifaga 3 tagacha odam belgilanishi mumkin" — bu
    cheklov shu yerda tekshiriladi (UI validatsiyasiga tayanmaydi)."""
    if not employee_ids:
        raise ValueError("Kamida bitta xodim tanlanishi kerak")
    if len(employee_ids) > 3:
        raise ValueError("Bitta vazifaga ko'pi bilan 3 ta xodim biriktirish mumkin")

    async with async_session() as session:
        employee_repo = EmployeeRepository(session)
        task_repo = TaskRepository(session)
        assignment_repo = TaskAssignmentRepository(session)

        # Tashkiliy kontekst uchun (statistika/jarima qoidalari bo'lim
        # bo'yicha bo'lishi mumkin) — birinchi tanlangan xodimning bo'limidan
        # olinadi, aniq so'ralmaydi (TZning o'zida MISC yaratishda bo'lim
        # tanlash talab qilinmagan).
        first_employee = await employee_repo.get_by_id(employee_ids[0])
        department_id = first_employee.department_id if first_employee else None

        task = await task_repo.create(
            trello_card_id=None,
            task_type=TaskType.MISC,
            title=text[:255],
            description=text,
            deadline=deadline,
            status=TaskStatus.ACTIVE,
            current_department_id=department_id,
            started_at=datetime.now(timezone.utc),
            misc_category=category,
        )

        for employee_id in employee_ids:
            await assignment_repo.create(task_id=task.id, employee_id=employee_id)

        await session.commit()
        return task
