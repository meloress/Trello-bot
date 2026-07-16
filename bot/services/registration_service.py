"""Xodimni Telegram akkauntiga bog'lash (5.2-band).

Xodim ADMIN tomonidan oldindan bazaga kiritiladi (`full_name` bilan,
`telegram_id=NULL`). Xodim botga birinchi marta `/start` bosganda o'z to'liq
ismini kiritadi — bu servis o'sha mavjud yozuvni topib, `telegram_id`ni
bog'laydi. **Yangi xodim yozuvi bu yerda hech qachon yaratilmaydi** — faqat
admin oldindan kiritgan yozuvga bog'lanadi (5.2-band: "Kim kimga signal
olishini ADMIN belgilaydi" tamoyili bilan bir xil — xodim o'zini o'zi
ro'yxatga qo'sha olmaydi).
"""

from core.database import async_session
from db.models.employee import Employee
from db.repositories import EmployeeRepository


class EmployeeNotFoundError(Exception):
    """Bunday to'liq ism bilan xodim bazada topilmadi."""


class AmbiguousNameError(Exception):
    """Bir nechta xodim bir xil ismga ega — ism orqali bittasini aniqlab bo'lmaydi."""


class AlreadyLinkedError(Exception):
    """Xodim allaqachon boshqa Telegram akkauntga bog'langan."""


async def link_employee_to_telegram(full_name: str, telegram_id: int) -> Employee:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)

        matches = await employee_repo.list_by_full_name(full_name)
        if not matches:
            raise EmployeeNotFoundError(f"'{full_name}' ismli xodim topilmadi")
        if len(matches) > 1:
            raise AmbiguousNameError(f"'{full_name}' ismli bir nechta xodim topildi")

        employee = matches[0]
        if employee.telegram_id is not None and employee.telegram_id != telegram_id:
            raise AlreadyLinkedError(f"'{full_name}' allaqachon boshqa Telegram akkauntga bog'langan")

        if employee.telegram_id != telegram_id:
            await employee_repo.update(employee, telegram_id=telegram_id)
            await session.commit()

        return employee
