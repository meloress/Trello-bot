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
from db.models.employee import Employee
from db.repositories import EmployeeRepository
from utils.enums import Role


class DuplicateNameError(Exception):
    """Shu to'liq ism bilan xodim allaqachon mavjud."""


class DuplicatePhoneError(Exception):
    """Shu telefon raqami bilan xodim allaqachon mavjud."""


class EmployeeNotFoundError(Exception):
    """Berilgan employee_id bo'yicha xodim topilmadi."""


async def create_employee(
    *,
    full_name: str,
    phone_number: str,
    role: Role,
    department_id: int | None = None,
    brigade_id: int | None = None,
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
        )
        await session.commit()
        return employee


async def update_employee(employee_id: int, **fields: object) -> Employee:
    """Bitta yoki bir nechta maydonni yangilaydi. `full_name`/`phone_number`
    o'zgartirilsa, dublikat tekshiruvi shu xodimning o'zini hisobga olmaydi."""
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
        await session.commit()
        return employee


async def deactivate_employee(employee_id: int) -> Employee:
    """Soft-delete: `is_active=False`. Xodim tarixi to'liq saqlanib qoladi."""
    return await update_employee(employee_id, is_active=False)


async def reactivate_employee(employee_id: int) -> Employee:
    return await update_employee(employee_id, is_active=True)
