from sqlalchemy import select

from db.models.employee import Employee
from db.repositories.base import BaseRepository
from utils.enums import Role
from utils.formatters import normalize_phone


class EmployeeRepository(BaseRepository[Employee]):
    model = Employee

    async def list_by_role(self, role: Role, *, active_only: bool = True) -> list[Employee]:
        """Bo'limga bog'lanmagan holda rol bo'yicha qidirish — masalan barcha
        ADMIN'larni topish uchun (6.1/7.4-band: bo'lim nazoratchisi yo'q
        holatda ham signal yetib borishi kerak)."""
        stmt = select(Employee).where(Employee.role == role)
        if active_only:
            stmt = stmt.where(Employee.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_telegram_id(self, telegram_id: int) -> Employee | None:
        """Bot /start bosganda xodimni telegram_id orqali tanib olish (5.2-band)."""
        result = await self.session.execute(
            select(Employee).where(Employee.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def list_by_department(
        self, department_id: int, *, active_only: bool = True
    ) -> list[Employee]:
        stmt = select(Employee).where(Employee.department_id == department_id)
        if active_only:
            stmt = stmt.where(Employee.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_full_name(self, full_name: str) -> list[Employee]:
        """Ro'yxatdan o'tish oqimida ism bo'yicha registr-sezmas qidirish (5.2-band).
        Ro'yxat qaytaradi (bitta emas) — chunki ismlar takrorlanishi mumkin,
        chaqiruvchi bir nechta mos kelgan holatni o'zi hal qiladi."""
        result = await self.session.execute(
            select(Employee).where(Employee.full_name.ilike(full_name.strip()))
        )
        return list(result.scalars().all())

    async def get_by_phone_number(self, phone_number: str) -> Employee | None:
        """5.1-band: xodim qo'shishda telefon raqami bo'yicha dublikat tekshiruvi."""
        result = await self.session.execute(
            select(Employee).where(Employee.phone_number == phone_number)
        )
        return result.scalar_one_or_none()

    async def find_by_normalized_phone(self, phone_number: str) -> Employee | None:
        """5.2-band: ro'yxatdan o'tishda Telegram kontakti orqali kelgan
        raqamni moslashtirish — admin turli formatda kiritgan bo'lishi mumkin
        (+998/998/bo'shliqlar), shuning uchun aniq satr solishtirish o'rniga
        raqamlar bo'yicha solishtiriladi."""
        target = normalize_phone(phone_number)
        if not target:
            return None
        result = await self.session.execute(
            select(Employee).where(Employee.phone_number.is_not(None))
        )
        for employee in result.scalars().all():
            if normalize_phone(employee.phone_number) == target:
                return employee
        return None

    async def list_by_brigade(self, brigade_id: int, *, active_only: bool = True) -> list[Employee]:
        """8.3-band: brigadaga o'tkazishda yangi brigada A'ZOLARI (`reassign_task_brigade`)."""
        stmt = select(Employee).where(Employee.brigade_id == brigade_id)
        if active_only:
            stmt = stmt.where(Employee.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[Employee]:
        """9-band: MISC vazifa uchun xodim tanlashda — bo'limga bog'lanmagan
        holda barcha faol xodimlar (masalan "Ofisni tozalash" istalgan
        bo'limdan odamga berilishi mumkin)."""
        result = await self.session.execute(select(Employee).where(Employee.is_active.is_(True)))
        return list(result.scalars().all())
