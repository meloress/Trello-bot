"""Xodimni Telegram akkauntiga bog'lash (5.2-band).

Xodim ADMIN tomonidan oldindan bazaga kiritiladi (`phone_number` bilan,
`telegram_id=NULL`). Xodim botga birinchi marta `/start` bosganda Telegram'ning
o'z "Kontakt yuborish" tugmasi orqali telefon raqamini yuboradi — bu servis
o'sha mavjud yozuvni topib, `telegram_id`ni bog'laydi. Ism o'rniga aynan
TELEFON RAQAMI ishlatiladi, chunki u Telegram tomonidan tasdiqlanadi (ismni
esa har kim yozib, boshqa xodimning shaxsini egallab olishi mumkin edi).
**Yangi xodim yozuvi bu yerda hech qachon yaratilmaydi** — faqat admin
oldindan kiritgan yozuvga bog'lanadi (5.2-band: "Kim kimga signal olishini
ADMIN belgilaydi" tamoyili bilan bir xil — xodim o'zini o'zi ro'yxatga qo'sha
olmaydi).
"""

from core.database import async_session
from db.models.employee import Employee
from db.repositories import EmployeeRepository


class EmployeeNotFoundError(Exception):
    """Bunday telefon raqami bilan xodim bazada topilmadi."""


class AlreadyLinkedError(Exception):
    """Xodim allaqachon boshqa Telegram akkauntga bog'langan."""


async def link_employee_to_telegram(phone_number: str, telegram_id: int) -> Employee:
    async with async_session() as session:
        employee_repo = EmployeeRepository(session)

        employee = await employee_repo.find_by_normalized_phone(phone_number)
        if employee is None:
            raise EmployeeNotFoundError(f"'{phone_number}' raqami bilan xodim topilmadi")

        if employee.telegram_id is not None and employee.telegram_id != telegram_id:
            raise AlreadyLinkedError("Bu xodim allaqachon boshqa Telegram akkauntga bog'langan")

        if employee.telegram_id != telegram_id:
            await employee_repo.update(employee, telegram_id=telegram_id)
            await session.commit()

        return employee
