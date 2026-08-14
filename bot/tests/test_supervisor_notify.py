"""TZ 3-band / 7.2-jadval — nazoratchi (sex nachalnigi) signal olishi.

TZ: "Rahbarga boradigan barcha signallar unga ham parallel boradi". Kodda
esa sakkizta xabar funksiyasi nazoratchini FAQAT `list_by_department()`
orqali qidirardi, ya'ni BO'LIMSIZ nazoratchi hech qanday signal olmasdi —
vaholanki tizimning qolgan qismida bo'limsiz SUPERVISOR "global" hisoblanadi
(`miniapp/api/admin.py._department_scope_ok`). Amalda mavjud yagona
nazoratchining bo'limi bo'sh edi, ya'ni TZ 7.2 jadvalidagi to'rt signalning
hech biri unga bormasdi.

Endi hammasi bitta `_add_supervisors()` orqali o'tadi — shu yerda pinlanadi.

Bazaga/Telegram'ga ulanmaydi. Oddiy `python tests/test_supervisor_notify.py`.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import services.notification_service as ns  # noqa: E402
from utils.enums import Role, TaskType  # noqa: E402

SHPON, SHKURKA = 38, 39

# Bo'limsiz nazoratchi — AYNAN shu holat buzilgan edi (production'dagi
# Habibulla Yusupkho'jayev shunday saqlangan).
GLOBAL_SUPERVISOR = SimpleNamespace(
    id=95, full_name="Bo'limsiz Nazoratchi", telegram_id=950, role=Role.SUPERVISOR,
    department_id=None, manager_id=None, is_active=True,
)
SHPON_SUPERVISOR = SimpleNamespace(
    id=96, full_name="Shpon Nazoratchisi", telegram_id=960, role=Role.SUPERVISOR,
    department_id=SHPON, manager_id=None, is_active=True,
)
# Boshqa bo'lim nazoratchisi — SHPON vazifasi haqida xabar OLMASLIGI kerak.
SHKURKA_SUPERVISOR = SimpleNamespace(
    id=97, full_name="Shkurka Nazoratchisi", telegram_id=970, role=Role.SUPERVISOR,
    department_id=SHKURKA, manager_id=None, is_active=True,
)
WORKER = SimpleNamespace(
    id=149, full_name="Mahmudov Abrorxon", telegram_id=1490, role=Role.WORKER,
    department_id=SHPON, manager_id=None, is_active=True,
)

PEOPLE = [GLOBAL_SUPERVISOR, SHPON_SUPERVISOR, SHKURKA_SUPERVISOR, WORKER]

TASK = SimpleNamespace(
    id=162, title="2529 Salamatina spalniy", task_type=TaskType.ORDER,
    current_department_id=SHPON, deadline=None, finished_at=None,
)
MISC_TASK = SimpleNamespace(
    id=900, title="Ofis ishi", task_type=TaskType.MISC,
    current_department_id=None, deadline=None, finished_at=None,
)


class _FakeEmployeeRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, employee_id):
        return next((p for p in PEOPLE if p.id == employee_id), None)

    async def list_by_role(self, role, *, active_only=True):
        return [p for p in PEOPLE if p.role == role and (not active_only or p.is_active)]


class _FakeTaskRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, task_id):
        return {TASK.id: TASK, MISC_TASK.id: MISC_TASK}.get(task_id)


class _FakeAssignmentRepo:
    def __init__(self, _session):
        pass

    async def list_by_task(self, task_id):
        return [SimpleNamespace(employee_id=WORKER.id)] if task_id == TASK.id else []


class _FakeDepartmentRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, department_id):
        names = {SHPON: "Shpon", SHKURKA: "Shkurka"}
        if department_id not in names:
            return None
        return SimpleNamespace(id=department_id, name=names[department_id], module="mebel")


class _FakeSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc_info):
        return False


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((int(chat_id), text))


async def main() -> None:
    saved = (ns.async_session, ns.EmployeeRepository, ns.TaskRepository,
             ns.TaskAssignmentRepository, ns.DepartmentRepository)
    ns.async_session = lambda: _FakeSession()
    ns.EmployeeRepository = _FakeEmployeeRepo
    ns.TaskRepository = _FakeTaskRepo
    ns.TaskAssignmentRepository = _FakeAssignmentRepo
    ns.DepartmentRepository = _FakeDepartmentRepo
    try:
        # --- 1. _add_supervisors: kim qo'shiladi, kim yo'q ---
        recipients: dict[int, int | None] = {}
        await ns._add_supervisors(None, recipients, SHPON)

        assert GLOBAL_SUPERVISOR.id in recipients, (
            "bo'limsiz nazoratchi signal olmadi — aynan tuzatilgan xato shu"
        )
        assert SHPON_SUPERVISOR.id in recipients, "o'z bo'limi nazoratchisi signal olmadi"
        assert SHKURKA_SUPERVISOR.id not in recipients, (
            "boshqa bo'lim nazoratchisi begona vazifa haqida signal oldi"
        )
        assert WORKER.id not in recipients, "nazoratchi bo'lmagan xodim qo'shildi"

        # --- 2. Bo'limsiz vazifa (MISC): faqat global nazoratchi ---
        recipients = {}
        await ns._add_supervisors(None, recipients, None)
        assert recipients == {GLOBAL_SUPERVISOR.id: GLOBAL_SUPERVISOR.telegram_id}, recipients

        # --- 3. Mavjud qabul qiluvchilar o'chib ketmaydi ---
        recipients = {WORKER.id: WORKER.telegram_id}
        await ns._add_supervisors(None, recipients, SHPON)
        assert recipients[WORKER.id] == WORKER.telegram_id, "ijrochi ro'yxatdan tushib ketdi"

        # --- 4. TZ 7.2: "Bosqich yakunlandi -> Nazoratchi" ---
        bot = _FakeBot()
        await ns.notify_stage_completed(bot, TASK.id)
        targets = {chat for chat, _ in bot.sent}
        assert targets == {GLOBAL_SUPERVISOR.telegram_id, SHPON_SUPERVISOR.telegram_id}, targets
        assert "Bosqich yakunlandi" in bot.sent[0][1]
        assert WORKER.full_name in bot.sent[0][1], "ijrochi ismi xabarda yo'q"
        assert "Shpon" in bot.sent[0][1], "bo'lim nomi xabarda yo'q"

        # --- 5. MISC vazifada "bosqich" tushunchasi yo'q -> xabar ham yo'q ---
        bot = _FakeBot()
        await ns.notify_stage_completed(bot, MISC_TASK.id)
        assert bot.sent == [], "MISC vazifa uchun bosqich xabari yuborildi"

        print("OK — nazoratchi signallari (bo'limsiz + bo'limli), TZ 7.2 bosqich xabari")
    finally:
        (ns.async_session, ns.EmployeeRepository, ns.TaskRepository,
         ns.TaskAssignmentRepository, ns.DepartmentRepository) = saved


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
