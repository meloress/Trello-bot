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
from datetime import datetime, timedelta, timezone
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
    current_department_id=SHPON,
    # 3 kun + bir oz zaxira: `_deadline_window()` kunni pastga yaxlitlaydi,
    # ya'ni aniq 72 soat chegarada "2 kun" bo'lib qolishi mumkin edi.
    deadline=datetime.now(timezone.utc) + timedelta(days=3, hours=1),
    finished_at=None,
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


KPI_LOGS = {
    1: SimpleNamespace(id=1, employee_id=WORKER.id, score=-8, reason="Kechikish: 94 soat"),
    2: SimpleNamespace(id=2, employee_id=WORKER.id, score=1, reason="27 soat oldin tugatildi"),
}


class _FakeKpiRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, kpi_log_id):
        return KPI_LOGS.get(kpi_log_id)


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
             ns.TaskAssignmentRepository, ns.DepartmentRepository, ns.KpiLogRepository)
    ns.async_session = lambda: _FakeSession()
    ns.EmployeeRepository = _FakeEmployeeRepo
    ns.TaskRepository = _FakeTaskRepo
    ns.TaskAssignmentRepository = _FakeAssignmentRepo
    ns.DepartmentRepository = _FakeDepartmentRepo
    ns.KpiLogRepository = _FakeKpiRepo
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

        # --- 6. "Yangi vazifa" — nazoratchiga UCHINCHI SHAXS ohangida ---
        # Ishchiga "Sizga yangi vazifa" boradi; nazoratchiga esa kim olgani.
        bot = _FakeBot()
        await ns.notify_task_started(bot, TASK.id)
        by_chat = {chat: text for chat, text in bot.sent}

        assert GLOBAL_SUPERVISOR.telegram_id in by_chat, (
            "nazoratchi 'yangi vazifa' hodisasi haqida umuman xabar olmadi"
        )
        assert "Sizga" not in by_chat[GLOBAL_SUPERVISOR.telegram_id], (
            "nazoratchiga ishchi matni ketdi — uchinchi shaxs ohangi kutilgan"
        )
        assert WORKER.full_name in by_chat[GLOBAL_SUPERVISOR.telegram_id]
        assert "ishini oldi" in by_chat[GLOBAL_SUPERVISOR.telegram_id]
        assert "(3 kun)" in by_chat[GLOBAL_SUPERVISOR.telegram_id], (
            f"muddat oynasi ko'rinmadi: {by_chat[GLOBAL_SUPERVISOR.telegram_id]!r}"
        )
        assert by_chat[WORKER.telegram_id].startswith("🆕 Yangi vazifa"), (
            "ishchining o'z xabari o'zgarib ketdi"
        )

        # --- 7. Jarima VA bonus — ikkalasi ham nazoratchiga ---
        for kpi_id, marker in ((1, "📉"), (2, "📈")):
            bot = _FakeBot()
            await ns.notify_penalty_applied(bot, kpi_id)
            supervisor_texts = [
                text for chat, text in bot.sent
                if chat in (GLOBAL_SUPERVISOR.telegram_id, SHPON_SUPERVISOR.telegram_id)
            ]
            assert len(supervisor_texts) == 2, f"kpi {kpi_id}: {supervisor_texts}"
            assert all(txt.startswith(marker) for txt in supervisor_texts), supervisor_texts
            assert all(WORKER.full_name in txt for txt in supervisor_texts)
            worker_text = next(text for chat, text in bot.sent if chat == WORKER.telegram_id)
            assert "Sizga" in worker_text, "ishchining o'z xabari o'zgarib ketdi"

        # --- 8. Ikki marta yubormaslik: nazoratchi ayni paytda ijrochi ---
        # `_supervisor_chat_ids` asosiy matnni olganlarni chiqarib tashlashi kerak.
        chat_ids = await ns._supervisor_chat_ids(None, SHPON, {GLOBAL_SUPERVISOR.id})
        assert GLOBAL_SUPERVISOR.telegram_id not in chat_ids, chat_ids
        assert SHPON_SUPERVISOR.telegram_id in chat_ids, chat_ids

        # --- 9. Nazoratchi FAQAT "Fasad seh"ni ko'radi ---
        # Bo'limsiz nazoratchi ilgari ikkala modulni olardi, natijada modul
        # tanlash ekrani va Profildagi "tizimni almashtirish" tugmasi chiqardi.
        from miniapp.api.common import _resolve_available_modules
        from utils.modules import MEBEL, NAZORAT_TRELLO

        assert _resolve_available_modules(GLOBAL_SUPERVISOR, None) == [MEBEL], (
            "bo'limsiz nazoratchiga Nazorat Trello ham ko'rinyapti"
        )
        # Admin — avvalgidek ikkalasi (bu o'zgarish nazoratchiga tegishli).
        admin = SimpleNamespace(role=Role.ADMIN, department_id=None)
        assert _resolve_available_modules(admin, None) == [MEBEL, NAZORAT_TRELLO]
        # Bo'lim biriktirilgan nazoratchi — o'sha bo'limning moduli.
        nazorat_dept = SimpleNamespace(module=NAZORAT_TRELLO)
        scoped = SimpleNamespace(role=Role.SUPERVISOR, department_id=75)
        assert _resolve_available_modules(scoped, nazorat_dept) == [NAZORAT_TRELLO], (
            "bo'lim orqali Nazorat Trello nazoratchisi qilish yo'li yopilib qolgan"
        )

        print("OK — nazoratchi signallari, TZ 7.2 bosqich xabari, "
              "yangi vazifa/ball xabarlari, dublikat himoyasi, modul qamrovi")
    finally:
        (ns.async_session, ns.EmployeeRepository, ns.TaskRepository,
         ns.TaskAssignmentRepository, ns.DepartmentRepository, ns.KpiLogRepository) = saved


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
