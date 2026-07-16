from sqlalchemy import select

from db.models.app_setting import AppSetting
from db.repositories.base import BaseRepository


class AppSettingRepository(BaseRepository[AppSetting]):
    model = AppSetting

    async def get_singleton(self) -> AppSetting:
        """Jadval doim bitta qatordan iborat (migratsiya orqali seed qilingan)."""
        result = await self.session.execute(select(AppSetting).limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            raise RuntimeError(
                "app_settings jadvalida qator yo'q — 'f490887dee10' migratsiyasi qo'llanganini tekshiring"
            )
        return row
