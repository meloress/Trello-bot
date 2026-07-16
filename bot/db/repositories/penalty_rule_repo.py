from sqlalchemy import or_, select

from db.models.penalty_rule import PenaltyRule
from db.repositories.base import BaseRepository


class PenaltyRuleRepository(BaseRepository[PenaltyRule]):
    model = PenaltyRule

    async def find_applicable_rule(
        self, hours_late: int, department_id: int | None
    ) -> PenaltyRule | None:
        """hours_late ni [min_hours_late, max_hours_late) oralig'iga tushiradigan
        qoidani topadi (max_hours_late=NULL -> ochiq yuqori chegara, ya'ni "va undan
        keyin ham"). Hech qanday qoida qamrab olmasa (masalan, hali sozlanmagan
        bosqichdan keyingi kechikish) — atayin None qaytaradi, eng oxirgi ma'lum
        qiymatga "yopishib qolmaydi". department'ga xos qoida global (NULL) qoidadan
        ustun turadi."""
        stmt = (
            select(PenaltyRule)
            .where(
                PenaltyRule.min_hours_late <= hours_late,
                or_(PenaltyRule.max_hours_late.is_(None), PenaltyRule.max_hours_late > hours_late),
                or_(PenaltyRule.department_id == department_id, PenaltyRule.department_id.is_(None)),
            )
            .order_by(PenaltyRule.department_id.is_(None).asc(), PenaltyRule.min_hours_late.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
