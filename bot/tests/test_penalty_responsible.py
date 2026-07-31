"""Ball KIMGA yozilishini tekshiradi (`penalty_service._write_scores_for_employees`).

Bazaga ulanmaydi — repository'lar soxta (fake) obyektlar bilan almashtiriladi,
shuning uchun oddiy `python tests/test_penalty_responsible.py` bilan ishlaydi
(loyihada pytest yo'q).

Qamrab olingan holatlar:
  1. Ishchi(lar) bor          -> ballar ishchilarga + brigadirga ulush
  2. Faqat brigadir           -> ball TO'LIQ brigadirga, ulush YO'Q
  3. Faqat admin/sotuvchi     -> hech kimga ball yozilmaydi
  4. Ishchi + brigadir birga  -> faqat ishchi (brigadir ulush orqali oladi)
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.enums import Role  # noqa: E402


class _FakeKpiRepo:
    def __init__(self):
        self.created = []

    async def create(self, *, employee_id, score, reason):
        log = SimpleNamespace(id=len(self.created) + 1, employee_id=employee_id, score=score, reason=reason)
        self.created.append(log)
        return log


class _FakeEmployeeRepo:
    def __init__(self, employees):
        self._by_id = {e.id: e for e in employees}

    async def get_by_id(self, employee_id):
        return self._by_id.get(employee_id)


class _FakeBrigadeRepo:
    def __init__(self, brigades):
        self._by_id = {b.id: b for b in brigades}

    async def get_by_id(self, brigade_id):
        return self._by_id.get(brigade_id)


def _emp(id_, role, brigade_id=None, name=None):
    return SimpleNamespace(
        id=id_, role=role, brigade_id=brigade_id,
        full_name=name or f"{role.value}-{id_}", telegram_id=1000 + id_,
    )


async def _run(employees, employee_ids, score=-2, ratio=0.4, penalize_all=True):
    """`_write_scores_for_employees`ni soxta repository'lar bilan chaqiradi."""
    import services.penalty_service as ps

    brigade = SimpleNamespace(id=7, brigadier_id=90, name="Kraska — Brigadir")
    kpi_repo = _FakeKpiRepo()
    fake_emp_repo = _FakeEmployeeRepo(employees)
    fake_brig_repo = _FakeBrigadeRepo([brigade])

    orig = (ps.EmployeeRepository, ps.BrigadeRepository, ps.KpiLogRepository)
    ps.EmployeeRepository = lambda _s: fake_emp_repo
    ps.BrigadeRepository = lambda _s: fake_brig_repo
    ps.KpiLogRepository = lambda _s: kpi_repo
    try:
        logs = await ps._write_scores_for_employees(
            None, employee_ids=employee_ids, score=score,
            reason="test", task_id=1, task_title="Test vazifa", brigade_share_ratio=ratio,
            penalize_all=penalize_all,
        )
    finally:
        ps.EmployeeRepository, ps.BrigadeRepository, ps.KpiLogRepository = orig
    return [(l.employee_id, l.score) for l in logs]


async def main():
    brigadier = _emp(90, Role.BRIGADIER, brigade_id=7)
    worker_a = _emp(91, Role.WORKER, brigade_id=7)
    worker_b = _emp(92, Role.WORKER, brigade_id=7)
    admin = _emp(94, Role.ADMIN)
    seller = _emp(95, Role.SELLER)
    everyone = [brigadier, worker_a, worker_b, admin, seller]

    # 1. Odatdagi holat: ishchiga to'liq, brigadirga ulush (-2 * 0.4 = -0.8 -> -1)
    got = await _run(everyone, [91])
    assert got == [(91, -2), (90, -1)], got

    # 2. TUZATISH: faqat brigadir tayinlangan -> ball TO'LIQ unga, ulush yo'q.
    #    Avval bu holatda ro'yxat BO'SH bo'lardi (hech kimga jarima yo'q).
    got = await _run(everyone, [90])
    assert got == [(90, -2)], got

    # 3. Faqat admin/sotuvchi -> hech kimga ball yozilmaydi
    assert await _run(everyone, [94, 95]) == []

    # 4. Ishchi + brigadir birga -> brigadir ikki marta olmaydi (faqat ulush)
    got = await _run(everyone, [90, 91])
    assert got == [(91, -2), (90, -1)], got

    # 5. Bir nechta ishchi -> har biriga to'liq, brigadirga har biri uchun ulush
    got = await _run(everyone, [91, 92])
    assert got == [(91, -2), (90, -1), (92, -2), (90, -1)], got

    # 6. Musbat ball (muddatdan oldin tugatish) ham xuddi shunday ishlaydi
    assert await _run(everyone, [90], score=5) == [(90, 5)]

    # 7. Noma'lum employee_id -> jimgina o'tkazib yuboriladi
    assert await _run(everyone, [99999]) == []

    # 8. SPEC.md §7: `penalize_all_assignees=False` -> faqat BIRINCHI mas'ul
    #    ("asosiy mas'ul"), brigadir ulushi ham faqat shundan hisoblanadi.
    got = await _run(everyone, [91, 92], penalize_all=False)
    assert got == [(91, -2), (90, -1)], got

    # 9. Faqat brigadirlar bo'lgan holatda ham chegara ishlaydi
    brigadier_b = _emp(93, Role.BRIGADIER)
    got = await _run(everyone + [brigadier_b], [90, 93], penalize_all=False)
    assert got == [(90, -2)], got

    print("test_penalty_responsible: 9/9 OK")


if __name__ == "__main__":
    asyncio.run(main())
