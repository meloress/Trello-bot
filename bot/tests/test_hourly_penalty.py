"""Nazorat Trello jarimasi soatbay (2026-11-04): `penalty_rules` qatori — shu
oraliqdagi har sutka uchun ball, soatlarga bo'linib jamlanadi; mebel esa eski
oraliq usulida qoladi.

Bazasiz: oddiy `python tests/test_hourly_penalty.py`.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import penalty_service  # noqa: E402
from utils.formatters import fmt_ball  # noqa: E402


def rule(lo, hi, score, department_id=None):
    return SimpleNamespace(min_hours_late=lo, max_hours_late=hi, score=score, department_id=department_id)


# Bazadagi haqiqiy global jadval (2026-11-04).
RULES = [rule(0, 24, -1), rule(24, 48, -1), rule(48, 72, -3), rule(72, 96, -3), rule(96, None, -5)]


def _hourly_checks():
    hp = penalty_service.hourly_penalty
    expected = {0: 0, 1: -0.04, 12: -0.5, 49: -2.13, 51: -2.38, 24: -1, 36: -1.5, 48: -2, 60: -3.5, 72: -5,
                84: -6.5, 96: -8, 108: -10.5, 120: -13, 144: -18}
    for hours, score in expected.items():
        assert hp(RULES, hours) == score, (hours, hp(RULES, hours), score)

    # bo'limga xos qator globaldan ustun
    assert hp(RULES + [rule(0, 24, -2, department_id=75)], 24) == -2
    # 24 soatdan boshqa kenglikdagi qator: ball o'z oralig'iga bo'linadi
    assert hp([rule(0, 12, -1), rule(12, None, -2)], 12) == -1
    # qamralmagan soat -> None (jim "0" emas)
    assert hp([rule(0, 24, -1)], 30) is None


def _format_checks():
    assert fmt_ball(-1.5) == "-1,5" and fmt_ball(-2) == "-2" and fmt_ball(3) == "+3" and fmt_ball(-0.04) == "-0,04" and fmt_ball(0) == "0"


async def _module_checks():
    """Soatbay faqat Nazorat Trello bo'limida; mebel va bo'limsiz — eski usul."""
    class Repo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, department_id):
            return {75: SimpleNamespace(module="fasad_sex"), 3: SimpleNamespace(module="mebel")}.get(department_id)

    saved = penalty_service.DepartmentRepository
    penalty_service.DepartmentRepository = Repo
    try:
        assert await penalty_service._is_nazorat_trello(None, 75) is True
        assert await penalty_service._is_nazorat_trello(None, 3) is False
        assert await penalty_service._is_nazorat_trello(None, None) is False
    finally:
        penalty_service.DepartmentRepository = saved


async def _ceil_checks():
    """10 daqiqa kechikish: Nazorat Trello'da 1 soat (soatbay), mebelda 0 soat (eski)."""
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
    captured = []

    class Session:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    class TaskRepo:
        def __init__(self, _s):
            pass

        async def get_by_id(self, task_id):
            return SimpleNamespace(id=task_id, finished_at=t0 + timedelta(minutes=10), deadline=t0,
                                   reassigned_at=None, current_department_id=task_id)

    class AssignmentRepo:
        def __init__(self, _s):
            pass

        async def list_by_task(self, task_id):
            return [SimpleNamespace(employee_id=169)]

    async def not_in_block(session, task):
        return False

    async def is_nazorat(session, department_id):
        return department_id == 75

    async def apply(**kw):
        captured.append((kw["hours_late"], kw["hourly"]))
        return []

    names = ("async_session", "TaskRepository", "TaskAssignmentRepository", "_is_inside_sla_block",
             "_is_nazorat_trello", "apply_penalty_for_employees")
    saved = [getattr(penalty_service, n) for n in names]
    for n, v in zip(names, (Session, TaskRepo, AssignmentRepo, not_in_block, is_nazorat, apply)):
        setattr(penalty_service, n, v)
    try:
        await penalty_service.calculate_and_apply_task_penalty(75)  # Nazorat Trello
        await penalty_service.calculate_and_apply_task_penalty(3)   # mebel
        assert captured == [(1, True), (0, False)], captured
    finally:
        for n, v in zip(names, saved):
            setattr(penalty_service, n, v)


async def _share_checks():
    """Brigadir ulushi: Nazorat Trello (kasr) — 2 xonagacha, mebel — butun son."""
    created = []

    class Brigades:
        async def get_by_id(self, _id):
            return SimpleNamespace(id=1, brigadier_id=9, name="B", department_id=75)

    class Employees:
        async def get_by_id(self, _id):
            return SimpleNamespace(id=9, full_name="Brigadir", telegram_id=1)

    class Kpi:
        async def create(self, **kw):
            created.append(kw["score"])
            return SimpleNamespace(**kw)

    worker = SimpleNamespace(id=5, full_name="Ishchi", brigade_id=1)
    for fractional in (True, False):
        await penalty_service._apply_brigade_share_for_worker(
            Brigades(), Employees(), Kpi(), worker=worker, worker_score=-1.5, ratio=0.33,
            task_id=1, task_title="T", fractional=fractional,
        )
    # -1.5 * 0.33 = -0.495: kasrda -0.50 (yarmi yuqoriga), butunda 0 -> yozilmaydi
    assert created == [-0.5], created


def _report_checks():
    from services.stats_service import format_stats_table

    stats = [SimpleNamespace(full_name="A", completed_tasks=1, total_score=-12.25, penalty_count=2),
             SimpleNamespace(full_name="B", completed_tasks=0, total_score=0, penalty_count=0)]
    rows = format_stats_table(stats, "T").strip("`\n").split("\n")
    table = [r for r in rows if "|" in r]
    assert len({r.index("|", r.index("|", r.index("|") + 1) + 1) for r in table}) == 1, table  # ustunlar tekis
    assert any(r.split("|")[2].strip() == "0" for r in table), table  # "+0" emas


if __name__ == "__main__":
    _hourly_checks()
    _format_checks()
    asyncio.run(_module_checks())
    asyncio.run(_ceil_checks())
    asyncio.run(_share_checks())
    _report_checks()
    print("test_hourly_penalty: OK")
