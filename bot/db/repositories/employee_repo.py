from sqlalchemy import select

from db.models.employee import Employee
from db.repositories.base import BaseRepository
from utils.enums import Role


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

    async def list_active(self) -> list[Employee]:
        """9-band: MISC vazifa uchun xodim tanlashda — bo'limga bog'lanmagan
        holda barcha faol xodimlar (masalan "Ofisni tozalash" istalgan
        bo'limdan odamga berilishi mumkin)."""
        result = await self.session.execute(select(Employee).where(Employee.is_active.is_(True)))
        return list(result.scalars().all())
