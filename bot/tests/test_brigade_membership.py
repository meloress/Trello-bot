"""Brigada avtomatik yaratilishi/bog'lanishini tekshiradi
(`services/employee_service.sync_brigade_links`).

Bazaga ulanmaydi — repository'lar soxta (fake) obyektlar bilan almashtiriladi,
shuning uchun oddiy `python tests/test_brigade_membership.py` bilan ishlaydi
(loyihada pytest yo'q).

Qamrab olingan holatlar:
  1. BRIGADIR + bo'lim        -> brigada yaratiladi, o'zi ham a'zo bo'ladi,
                                 bo'limdagi brigadasiz ishchilar bog'lanadi
  2. Qo'shimcha bo'lim        -> ikkinchi brigada (Elyor: Kraska + Shkurka)
  3. Qo'shimcha bo'lim olindi -> brigada o'chmaydi, brigadirsiz qoladi
  4. Rol BRIGADIR emas        -> boshqargan brigadalari brigadirsiz qoladi
  5. Yangi ISHCHI             -> bo'limidagi yagona brigadaga bog'lanadi
  6. Bo'limda 2 brigada       -> noaniq, ishchi tegilmaydi
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.enums import Role  # noqa: E402
import services.employee_service as es  # noqa: E402


class _FakeBrigadeRepo:
    def __init__(self, brigades):
        self.brigades = list(brigades)

    async def list_by_department(self, department_id):
        return [b for b in self.brigades if b.department_id == department_id]

    async def list_by_brigadier_id(self, brigadier_id):
        return [b for b in self.brigades if b.brigadier_id == brigadier_id]

    async def create(self, **fields):
        brigade = SimpleNamespace(id=max([b.id for b in self.brigades], default=0) + 1, **fields)
        self.brigades.append(brigade)
        return brigade

    async def update(self, obj, **fields):
        for key, value in fields.items():
            setattr(obj, key, value)
        return obj


class _FakeEmployeeRepo:
    def __init__(self, employees):
        self.employees = list(employees)

    async def list_by_department(self, department_id, *, active_only=True):
        return [e for e in self.employees if e.department_id == department_id and e.is_active]

    async def update(self, obj, **fields):
        for key, value in fields.items():
            setattr(obj, key, value)
        return obj


class _FakeDepartmentRepo:
    def __init__(self, departments):
        self._by_id = {d.id: d for d in departments}

    async def get_by_id(self, department_id):
        return self._by_id.get(department_id)


KRASKA, SHKURKA = 40, 39
DEPARTMENTS = [
    SimpleNamespace(id=KRASKA, name="Kraska"),
    SimpleNamespace(id=SHKURKA, name="Shkurka"),
]


def _emp(id_, role, department_id=None, brigade_id=None, name=None):
    return SimpleNamespace(
        id=id_, role=role, department_id=department_id, brigade_id=brigade_id,
        full_name=name or f"Xodim {id_}", is_active=True,
    )


def _run(employee, employees, brigades, led_department_ids=None):
    """`sync_brigade_links`ni soxta repolar bilan ishga tushiradi."""
    brigade_repo = _FakeBrigadeRepo(brigades)
    employee_repo = _FakeEmployeeRepo(employees)

    orig = (es.BrigadeRepository, es.EmployeeRepository, es.DepartmentRepository)
    es.BrigadeRepository = lambda _s: brigade_repo
    es.EmployeeRepository = lambda _s: employee_repo
    es.DepartmentRepository = lambda _s: _FakeDepartmentRepo(DEPARTMENTS)
    try:
        asyncio.run(es.sync_brigade_links(None, employee, led_department_ids))
    finally:
        es.BrigadeRepository, es.EmployeeRepository, es.DepartmentRepository = orig
    return brigade_repo, employee_repo


def test_brigadier_gets_brigade_and_workers():
    elyor = _emp(146, Role.BRIGADIER, KRASKA, name="Yoldoshov Elyor")
    worker = _emp(147, Role.WORKER, KRASKA)
    other_department_worker = _emp(148, Role.WORKER, SHKURKA)

    brigade_repo, _ = _run(elyor, [elyor, worker, other_department_worker], [])

    assert len(brigade_repo.brigades) == 1
    brigade = brigade_repo.brigades[0]
    assert brigade.brigadier_id == elyor.id
    # Nom xabarlarda ishlatiladi — bo'lim nomi ichida bo'lishi shart.
    assert brigade.name == "Kraska — Yoldoshov Elyor"
    assert elyor.brigade_id == brigade.id, "brigadir o'z brigadasiga a'zo bo'lmasa, o'z balini ko'rmaydi"
    assert worker.brigade_id == brigade.id
    assert other_department_worker.brigade_id is None, "boshqa bo'lim ishchisi tegilmasligi kerak"


def test_second_department_creates_second_brigade():
    elyor = _emp(146, Role.BRIGADIER, KRASKA, name="Yoldoshov Elyor")
    shkurka_worker = _emp(144, Role.WORKER, SHKURKA)

    brigade_repo, _ = _run(elyor, [elyor, shkurka_worker], [], led_department_ids=[SHKURKA])

    assert len(brigade_repo.brigades) == 2, "ikkita bo'limga rahbarlik = ikkita brigada"
    assert {b.department_id for b in brigade_repo.brigades} == {KRASKA, SHKURKA}
    assert all(b.brigadier_id == elyor.id for b in brigade_repo.brigades)
    shkurka = next(b for b in brigade_repo.brigades if b.department_id == SHKURKA)
    assert shkurka_worker.brigade_id == shkurka.id


def test_removed_department_keeps_brigade_without_brigadier():
    elyor = _emp(146, Role.BRIGADIER, KRASKA, name="Yoldoshov Elyor")
    shkurka = SimpleNamespace(id=7, name="Shkurka — Yoldoshov Elyor", department_id=SHKURKA, brigadier_id=elyor.id)
    member = _emp(144, Role.WORKER, SHKURKA, brigade_id=shkurka.id)

    brigade_repo, _ = _run(elyor, [elyor, member], [shkurka], led_department_ids=[])

    assert shkurka in brigade_repo.brigades, "brigada o'chirilmaydi (KPI tarixi bog'liq)"
    assert shkurka.brigadier_id is None
    assert member.brigade_id == shkurka.id


def test_demoted_brigadier_releases_brigades():
    elyor = _emp(146, Role.WORKER, KRASKA, name="Yoldoshov Elyor")
    kraska = SimpleNamespace(id=3, name="Kraska — Yoldoshov Elyor", department_id=KRASKA, brigadier_id=elyor.id)

    _run(elyor, [elyor], [kraska])

    assert kraska.brigadier_id is None, "ishchilikka tushirilgan odam brigadir bo'lib qolmasligi kerak"


def test_worker_joins_single_brigade_of_department():
    kraska = SimpleNamespace(id=3, name="Kraska — Yoldoshov Elyor", department_id=KRASKA, brigadier_id=146)
    worker = _emp(150, Role.WORKER, KRASKA)

    _run(worker, [worker], [kraska])

    assert worker.brigade_id == kraska.id


def test_worker_untouched_when_department_has_two_brigades():
    first = SimpleNamespace(id=3, name="Kraska — A", department_id=KRASKA, brigadier_id=146)
    second = SimpleNamespace(id=4, name="Kraska — B", department_id=KRASKA, brigadier_id=200)
    worker = _emp(150, Role.WORKER, KRASKA)

    _run(worker, [worker], [first, second])

    assert worker.brigade_id is None, "qaysi brigada ekani noaniq — qo'lda tanlanadi"


if __name__ == "__main__":
    test_brigadier_gets_brigade_and_workers()
    test_second_department_creates_second_brigade()
    test_removed_department_keeps_brigade_without_brigadier()
    test_demoted_brigadier_releases_brigades()
    test_worker_joins_single_brigade_of_department()
    test_worker_untouched_when_department_has_two_brigades()
    print("OK — brigada bog'lanishi 6 holatda ham to'g'ri")
