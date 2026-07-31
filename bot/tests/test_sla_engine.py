"""SPEC.md Faza 1 — SLA dvigateli.

Bazaga ulanmaydi: `DepartmentRepository` va sessiya soxta obyektlar bilan
almashtiriladi, shuning uchun oddiy `python tests/test_sla_engine.py` bilan
ishlaydi (loyihada pytest yo'q).

Qamrab olingan holatlar:
  §5.1 muddat = bosqichga kirgan payt + bo'lim SLA'si
       - fasad_sex + SLA           -> muddat avtomatik hisoblanadi
       - SLA sozlanmagan (NULL)    -> muddat NULL (qo'lda kiritiladi)
       - mebel bo'limi             -> SLA e'tiborga OLINMAYDI (muzlatilgan modul)
  §6.1 "Stop" taymerni muzlatadi
       - fasad_sex                 -> to'xtash davomiyligi qaytariladi
       - mebel                     -> None (muddat surilmaydi)
       - teskari/nol oraliq        -> None (muddat ORQAGA surilmaydi)
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import services.task_service as task_service  # noqa: E402
import services.timer_service as timer_service  # noqa: E402
from utils.enums import TaskStatus  # noqa: E402


def _dept(id_=1, *, module="fasad_sex", sla=None):
    return SimpleNamespace(id=id_, name=f"dept-{id_}", module=module, default_sla_hours=sla)


class _FakeDepartmentRepo:
    def __init__(self, department):
        self._department = department

    async def get_by_id(self, department_id):
        return self._department


class _CapturingTaskRepo:
    """`create()`ga uzatilgan maydonlarni ushlab qoladi."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, _session):
        return self

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(id=1, **kwargs)


async def _spawn_with(department):
    """`_spawn_pending_stage()`ni soxta repolar bilan chaqiradi va yaratilgan
    qatorning maydonlarini qaytaradi."""
    task_repo = _CapturingTaskRepo()
    original_dept_repo = task_service.DepartmentRepository
    original_task_repo = task_service.TaskRepository
    task_service.DepartmentRepository = lambda _s: _FakeDepartmentRepo(department)
    task_service.TaskRepository = task_repo
    try:
        await task_service._spawn_pending_stage(
            None,
            department_id=department.id,
            previous_task_id=7,
            card_id="card-1",
            checklist_id=None,
            title="Zakaz-42",
            description=None,
            client_id=None,
        )
    finally:
        task_service.DepartmentRepository = original_dept_repo
        task_service.TaskRepository = original_task_repo
    return task_repo.kwargs


async def _paused_with(department, *, stopped_at, resumed_at, department_id=1):
    original = timer_service.DepartmentRepository
    timer_service.DepartmentRepository = lambda _s: _FakeDepartmentRepo(department)
    try:
        task = SimpleNamespace(current_department_id=department_id)
        return await timer_service._paused_shift(None, task, stopped_at, resumed_at)
    finally:
        timer_service.DepartmentRepository = original


async def main() -> None:
    # --- §5.1: fasad_sex bo'limida SLA muddatni avtomatik qo'yadi ---
    before = datetime.now(timezone.utc)
    fields = await _spawn_with(_dept(module="fasad_sex", sla=48))
    after = datetime.now(timezone.utc)
    assert fields["status"] == TaskStatus.PENDING_SETUP, "bosqich baribir xodim tayinlanishini kutadi"
    deadline = fields["deadline"]
    assert deadline is not None, "SLA sozlangan bo'lsa muddat avtomatik qo'yilishi kerak"
    # Muddat aynan "bosqichga kirgan payt + 48 soat" oralig'ida bo'lishi kerak.
    assert before + timedelta(hours=48) <= deadline <= after + timedelta(hours=48), (
        f"muddat entered_at + 48 soat bo'lishi kerak, kelgan: {deadline}"
    )

    # --- §5.1: SLA sozlanmagan bo'lim — eski xatti-harakat (qo'lda kiritish) ---
    fields = await _spawn_with(_dept(module="fasad_sex", sla=None))
    assert fields["deadline"] is None, "SLA yo'q bo'lsa muddat NULL bo'lib qolishi kerak"

    # --- Mebel muzlatilgan: SLA ustuni qiymati bo'lsa ham e'tiborga olinmaydi ---
    fields = await _spawn_with(_dept(module="mebel", sla=72))
    assert fields["deadline"] is None, "mebel modulida muddat Trello'dan keladi, SLA ustuni o'qilmaydi"

    # --- §6.1: fasad_sex'da "Stop" davomiyligi muddatga qo'shiladi ---
    stopped_at = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    resumed_at = stopped_at + timedelta(hours=5, minutes=30)
    paused = await _paused_with(_dept(module="fasad_sex"), stopped_at=stopped_at, resumed_at=resumed_at)
    assert paused == timedelta(hours=5, minutes=30), f"to'xtash davomiyligi noto'g'ri: {paused}"

    # --- §6.1: mebelda muddat surilmaydi ---
    paused = await _paused_with(_dept(module="mebel"), stopped_at=stopped_at, resumed_at=resumed_at)
    assert paused is None, "mebelda 'Stop' muddatga ta'sir qilmasligi kerak"

    # --- Bo'limi yo'q vazifa (MISC) — surilmaydi ---
    paused = await _paused_with(
        _dept(module="fasad_sex"), stopped_at=stopped_at, resumed_at=resumed_at, department_id=None
    )
    assert paused is None, "bo'limi yo'q vazifada muddat surilmaydi"

    # --- Teskari oraliq: muddat ORQAGA surilib ishchini jazolamasligi kerak ---
    paused = await _paused_with(
        _dept(module="fasad_sex"), stopped_at=resumed_at, resumed_at=stopped_at
    )
    assert paused is None, "manfiy oraliq muddatni orqaga surmasligi kerak"

    print("test_sla_engine: HAMMASI O'TDI")


if __name__ == "__main__":
    asyncio.run(main())
