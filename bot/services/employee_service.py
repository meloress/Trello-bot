"""Xodimlar bazasi moduli — CRUD (5.1-band). Admin/nazoratchi bot orqali
xodim qo'shadi, tahrirlaydi, ishdan bo'shatadi. Yangi xodim yozuvi FAQAT shu
yerda yaratiladi — `registration_service.py` esa faqat MAVJUD yozuvni
Telegramga bog'laydi, hech qachon yangi yozuv yaratmaydi.

O'CHIRISH — faqat SOFT DELETE (`is_active=False`). Hard delete taklif
qilinmadi: xodimning `kpi_logs`/`task_assignments`/`stop_logs` tarixi FK
orqali unga bog'liq (ON DELETE CASCADE yo'q), shuning uchun hard delete yo
tarixiy ma'lumotni yo'qotardi, yo FK xatosi bilan butunlay muvaffaqiyatsiz
tugardi. Soft-delete esa audit tarixini saqlab, xodimni "faol xodim"
so'rovlaridan (`list_by_department(active_only=True)` kabi) chiqarib
qo'yadi va istalgan vaqt `reactivate_employee()` bilan qaytarish mumkin.
"""

from core.database import async_session
from db.models.brigade import Brigade
from db.models.employee import Employee
from db.repositories import BrigadeRepository, DepartmentRepository, EmployeeRepository
from utils.enums import Role


class DuplicateNameError(Exception):
    """Shu to'liq ism bilan xodim allaqachon mavjud."""


class DuplicatePhoneError(Exception):
    """Shu telefon raqami bilan xodim allaqachon mavjud."""


class EmployeeNotFoundError(Exception):
    """Berilgan employee_id bo'yicha xodim topilmadi."""


async def _ensure_brigade(session, employee: Employee, department_id: int) -> Brigade:
    """Shu bo'limda `employee` boshqaradigan brigadani topadi, bo'lmasa yaratadi.
    Brigadirsiz qolgan brigada bo'lsa — yangisini yaratmasdan o'shani oladi,
    aks holda o'sha bo'limda ikkita brigada paydo bo'lib, eski a'zolar
    brigadirsiz brigadada osilib qolardi."""
    brigade_repo = BrigadeRepository(session)
    brigades = await brigade_repo.list_by_department(department_id)

    for brigade in brigades:
        if brigade.brigadier_id == employee.id:
            return brigade

    orphan = next((b for b in brigades if b.brigadier_id is None), None)
    if orphan is not None:
        await brigade_repo.update(orphan, brigadier_id=employee.id)
        return orphan

    department = await DepartmentRepository(session).get_by_id(department_id)
    department_name = department.name if department is not None else str(department_id)
    # Nom xabarlarda ham ko'rinadi ("Kraska — Yoldoshov Elyor"), shuning uchun
    # bo'lim nomi doim ichida: ikkita brigadaga rahbarlik qiladigan odam
    # xabarning qaysi brigadaga tegishli ekanini shundan biladi.
    return await brigade_repo.create(
        name=f"{department_name} — {employee.full_name}",
        department_id=department_id,
        brigadier_id=employee.id,
    )


async def _link_unassigned_workers(session, department_id: int, brigade_id: int) -> None:
    """Shu bo'limdagi brigadasiz ishchilarni brigadaga bog'laydi — xodim
    qo'shishda brigada qo'lda tanlanmaydi, bo'limi bo'yicha o'zi topiladi."""
    employee_repo = EmployeeRepository(session)
    for member in await employee_repo.list_by_department(department_id):
        if member.role == Role.WORKER and member.brigade_id is None:
            await employee_repo.update(member, brigade_id=brigade_id)


async def sync_brigade_links(
    session, employee: Employee, led_department_ids: list[int] | None = None
) -> None:
    """Brigada = brigadirning o'zi. Alohida "Brigada yaratish" ekrani yo'q —
    xodim BRIGADIR deb belgilanishi bilan unga bo'limi bo'yicha brigada
    yaratiladi, ishchilar esa BO'LIMI bo'yicha o'sha brigadaga bog'lanadi.

    - BRIGADIER: o'z bo'limi + har bir qo'shimcha bo'lim (`led_department_ids`,
      masalan Kraska rahbari Shkurkaga ham qarasa) uchun brigada get-or-create;
      brigadirning o'zi ham a'zo bo'ladi (statistika `employees.brigade_id`
      bo'yicha yig'iladi), bo'limdagi brigadasiz ishchilar bog'lanadi.
    - Boshqa rol: shu odam boshqarayotgan brigadalar brigadirsiz qoladi
      (brigadir ishchilikka tushirilganda ro'yxatlarda qolib ketmasligi uchun).
    - WORKER: bo'limida bitta brigada bo'lsa — o'shanga bog'lanadi. Bir nechta
      bo'lsa qaysi biri ekani noaniq, tegilmaydi (qo'lda tanlanadi).

    Rahbarlikdan olingan bo'lim brigadasi O'CHIRILMAYDI — faqat
    `brigadier_id=None` bo'ladi, a'zolari va KPI tarixi joyida qoladi.
    """
    brigade_repo = BrigadeRepository(session)
    employee_repo = EmployeeRepository(session)

    if employee.role != Role.BRIGADIER:
        for brigade in await brigade_repo.list_by_brigadier_id(employee.id):
            await brigade_repo.update(brigade, brigadier_id=None)
        if (
            employee.role == Role.WORKER
            and employee.department_id is not None
            and employee.brigade_id is None
        ):
            brigades = await brigade_repo.list_by_department(employee.department_id)
            if len(brigades) == 1:
                await employee_repo.update(employee, brigade_id=brigades[0].id)
        return

    department_ids: list[int] = []
    for department_id in [employee.department_id, *(led_department_ids or [])]:
        if department_id is not None and department_id not in department_ids:
            department_ids.append(department_id)

    own_brigades = []
    for department_id in department_ids:
        brigade = await _ensure_brigade(session, employee, department_id)
        own_brigades.append(brigade)
        await _link_unassigned_workers(session, department_id, brigade.id)

    if led_department_ids is not None:
        kept = {b.id for b in own_brigades}
        for brigade in await brigade_repo.list_by_brigadier_id(employee.id):
            if brigade.id not in kept:
                await brigade_repo.update(brigade, brigadier_id=None)

    if own_brigades and employee.brigade_id not in {b.id for b in own_brigades}:
        await employee_repo.update(employee, brigade_id=own_brigades[0].id)


async def create_employee(
    *,
    full_name: str,
    phone_number: str,
    role: Role,
    department_id: int | None = None,
    brigade_id: int | None = None,
    trello_username: str | None = None,
    trello_member_id: str | None = None,
) -> Employee:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)

        if await employee_repo.list_by_full_name(full_name):
            raise DuplicateNameError(f"'{full_name}' ismli xodim allaqachon mavjud")
        if await employee_repo.get_by_phone_number(phone_number):
            raise DuplicatePhoneError(f"'{phone_number}' raqamli xodim allaqachon mavjud")

        employee = await employee_repo.create(
            full_name=full_name,
            phone_number=phone_number,
            role=role,
            department_id=department_id,
            brigade_id=brigade_id,
            trello_username=trello_username,
            trello_member_id=trello_member_id,
        )
        await sync_brigade_links(session, employee)
        await session.commit()
        return employee


async def update_employee(
    employee_id: int, *, led_department_ids: list[int] | None = None, **fields: object
) -> Employee:
    """Bitta yoki bir nechta maydonni yangilaydi. `full_name`/`phone_number`
    o'zgartirilsa, dublikat tekshiruvi shu xodimning o'zini hisobga olmaydi.
    `led_department_ids` — ustun emas, brigadalar orqali ifodalanadi
    (`sync_brigade_links`), shuning uchun `fields`dan alohida olinadi."""
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)

        employee = await employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(f"Employee {employee_id} topilmadi")

        if "full_name" in fields:
            duplicates = await employee_repo.list_by_full_name(fields["full_name"])
            if any(e.id != employee_id for e in duplicates):
                raise DuplicateNameError(f"'{fields['full_name']}' ismli boshqa xodim allaqachon mavjud")

        if fields.get("phone_number"):
            existing_phone = await employee_repo.get_by_phone_number(fields["phone_number"])
            if existing_phone is not None and existing_phone.id != employee_id:
                raise DuplicatePhoneError(
                    f"'{fields['phone_number']}' raqamli boshqa xodim allaqachon mavjud"
                )

        await employee_repo.update(employee, **fields)
        await sync_brigade_links(session, employee, led_department_ids)
        await session.commit()
        return employee


async def deactivate_employee(employee_id: int) -> Employee:
    """Soft-delete: `is_active=False`. Xodim tarixi to'liq saqlanib qoladi."""
    return await update_employee(employee_id, is_active=False)


async def reactivate_employee(employee_id: int) -> Employee:
    return await update_employee(employee_id, is_active=True)
