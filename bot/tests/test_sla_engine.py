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
  §5.2 chizish navbat qoidasi (srochniy / norma ichida / normadan oshgan)
  §5.3 blok SLA — muddat ko'chadi, jarima faqat blokdan chiqishda
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import services.penalty_service as penalty_service  # noqa: E402
import services.task_service as task_service  # noqa: E402
import services.timer_service as timer_service  # noqa: E402
from utils.enums import TaskStatus  # noqa: E402


def _dept(id_=1, *, module="fasad_sex", sla=None, urgent=None, quota=None, over=None,
          block=None, next_id=None):
    return SimpleNamespace(
        id=id_, name=f"dept-{id_}", module=module, default_sla_hours=sla,
        sla_urgent_hours=urgent, daily_quota_orders=quota, sla_over_quota_hours=over,
        sla_block_id=block, next_department_id=next_id,
    )


def _task(*, department_id=1, urgent=False, deadline=None):
    return SimpleNamespace(
        id=99, current_department_id=department_id, is_urgent=urgent, deadline=deadline
    )


class _FakeDepartmentRepo:
    """Bitta bo'lim (eski testlar) yoki id -> bo'lim jadvali (blok testlari)."""

    def __init__(self, department):
        self._by_id = department if isinstance(department, dict) else None
        self._department = None if isinstance(department, dict) else department

    async def get_by_id(self, department_id):
        if self._by_id is not None:
            return self._by_id.get(department_id)
        return self._department


class _CapturingTaskRepo:
    """`create()`ga uzatilgan maydonlarni ushlab qoladi. `created_today` —
    §5.2 navbat qoidasi uchun "bugun shu bo'limda nechta bosqich ochilgan"."""

    def __init__(self, *, created_today=0, previous_task=None):
        self.kwargs = None
        self._created_today = created_today
        self._previous_task = previous_task

    def __call__(self, _session):
        return self

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(id=1, **kwargs)

    async def get_by_id(self, _task_id):
        return self._previous_task

    async def count_created_in_department_since(self, *, department_id, since):
        return self._created_today


async def _spawn_with(department, *, created_today=0, previous_task=None, departments=None):
    """`_spawn_pending_stage()`ni soxta repolar bilan chaqiradi va yaratilgan
    qatorning maydonlarini qaytaradi."""
    task_repo = _CapturingTaskRepo(created_today=created_today, previous_task=previous_task)
    original_dept_repo = task_service.DepartmentRepository
    original_task_repo = task_service.TaskRepository
    task_service.DepartmentRepository = lambda _s: _FakeDepartmentRepo(departments or department)
    task_service.TaskRepository = task_repo
    try:
        await task_service._spawn_pending_stage(
            None,
            department_id=department.id,
            previous_task_id=7 if previous_task is not None else None,
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


async def _inside_block(departments, task):
    original = penalty_service.DepartmentRepository
    penalty_service.DepartmentRepository = lambda _s: _FakeDepartmentRepo(departments)
    try:
        return await penalty_service._is_inside_sla_block(None, task)
    finally:
        penalty_service.DepartmentRepository = original


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

    # --- §5.2: navbat qoidasi — kun ichida normagacha standart muddat ---
    drawing = _dept(module="fasad_sex", sla=48, urgent=24, quota=5, over=72)
    fields = await _spawn_with(drawing, created_today=3, previous_task=_task())
    hours = round((fields["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600)
    assert hours == 48, f"kun ichida 4-o'rin (norma 5) -> 48 soat kutilgan, kelgan: {hours}"

    # --- §5.2: normadan oshgan (6-buyurtma, norma 5) -> 72 soat ---
    fields = await _spawn_with(drawing, created_today=5, previous_task=_task())
    hours = round((fields["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600)
    assert hours == 72, f"normadan oshgan -> 72 soat kutilgan, kelgan: {hours}"

    # --- §5.2: srochniy navbatdan qat'i nazar 24 soat ---
    fields = await _spawn_with(drawing, created_today=50, previous_task=_task(urgent=True))
    hours = round((fields["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600)
    assert hours == 24, f"srochniy -> 24 soat kutilgan, kelgan: {hours}"
    assert fields["is_urgent"] is True, "srochnost keyingi bosqichga ko'chishi kerak"

    # --- §5.2: norma sozlanmagan bo'limda qoida ishlamaydi ---
    fields = await _spawn_with(_dept(sla=48), created_today=99, previous_task=_task())
    hours = round((fields["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600)
    assert hours == 48, "navbat qoidasi sozlanmagan bo'limda standart muddat qolishi kerak"

    # --- §5.3: blok ichida muddat ko'chadi, qayta hisoblanmaydi ---
    # Shkurka(1) -> Kraska(2) -> Malyarka(3), hammasi "paint" blokida;
    # Malyarka'dan keyin blokdan tashqaridagi Dostavka(4).
    block_deadline = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    shkurka = _dept(1, sla=360, block="paint", next_id=2)
    kraska = _dept(2, sla=360, block="paint", next_id=3)
    malyarka = _dept(3, sla=360, block="paint", next_id=4)
    dostavka = _dept(4, sla=24, block=None, next_id=None)
    chain = {1: shkurka, 2: kraska, 3: malyarka, 4: dostavka}

    fields = await _spawn_with(
        kraska,
        previous_task=_task(department_id=1, deadline=block_deadline),
        departments=chain,
    )
    assert fields["deadline"] == block_deadline, (
        "blok ichida muddat blokka kirgandagidek qolishi kerak, qayta hisoblanmasligi"
    )

    # --- §5.3: blokka KIRISH — muddat yangidan hisoblanadi ---
    fields = await _spawn_with(
        shkurka,
        previous_task=_task(department_id=4, deadline=block_deadline),
        departments=chain,
    )
    hours = round((fields["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600)
    assert hours == 360, f"blokka kirishda 360 soat (15 kun) kutilgan, kelgan: {hours}"

    # --- §5.3: jarima faqat blokdan CHIQISHDA ---
    assert await _inside_block(chain, _task(department_id=1)) is True, "Shkurka — blok ichida"
    assert await _inside_block(chain, _task(department_id=2)) is True, "Kraska — blok ichida"
    assert await _inside_block(chain, _task(department_id=3)) is False, (
        "Malyarka — blokning chiqishi, jarima shu yerda hisoblanishi kerak"
    )
    assert await _inside_block(chain, _task(department_id=4)) is False, "Dostavka bloksiz"

    print("test_sla_engine: HAMMASI O'TDI")


if __name__ == "__main__":
    asyncio.run(main())
