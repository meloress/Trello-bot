from sqlalchemy import select

from db.models.department_fork_target import DepartmentForkTarget
from db.repositories.base import BaseRepository


class DepartmentForkTargetRepository(BaseRepository[DepartmentForkTarget]):
    model = DepartmentForkTarget

    async def list_by_department(self, department_id: int) -> list[DepartmentForkTarget]:
        """Shu fork NUQTASIdan chiqadigan barcha tarmoq (target) qatorlari."""
        result = await self.session.execute(
            select(DepartmentForkTarget).where(DepartmentForkTarget.department_id == department_id)
        )
        return list(result.scalars().all())

    async def list_by_target_department(
        self, target_department_id: int
    ) -> list[DepartmentForkTarget]:
        """Teskari qidiruv: shu target'ga qaysi fork nuqta(lar)i ulanadi."""
        result = await self.session.execute(
            select(DepartmentForkTarget).where(
                DepartmentForkTarget.target_department_id == target_department_id
            )
        )
        return list(result.scalars().all())
