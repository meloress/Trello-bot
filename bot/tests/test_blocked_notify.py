"""TZ 5.6 — "xabarnomani foydalanuvchi o'chira olmasligi".

Telegram'da bloklashni MAJBURLAB to'xtatib bo'lmaydi, shuning uchun uni
KO'RINADIGAN qilamiz: bot bloklangani `TelegramForbiddenError` orqali
bilinadi va shu xodimning rahbariga + barcha ADMIN'larga signal ketadi
(`notification_service._report_blocked`).

Bazaga/Telegram'ga ulanmaydi: `async_session` va `EmployeeRepository` soxta
obyektlar bilan almashtiriladi. Oddiy `python tests/test_blocked_notify.py`.

Eng muhim tekshiruv — REKURSIYA: signalni qabul qiluvchi adminning O'ZI ham
botni bloklagan bo'lsa, "bloklandi" xabari yana "bloklandi" xabarini
keltirib chiqarmasligi kerak (aks holda bot cheksiz siklda qotib qolardi).
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram.exceptions import TelegramForbiddenError  # noqa: E402

import services.notification_service as ns  # noqa: E402
from utils.enums import Role  # noqa: E402

NAZORAT_DEPT, MEBEL_DEPT = 10, 1

WORKER = SimpleNamespace(
    id=1, full_name="Ishchi Ismoilov", telegram_id=100, manager_id=5, role=Role.WORKER,
    department_id=NAZORAT_DEPT,
)
# Mebel ("Fasad seh") MUZLATILGAN — bu xodim bloklasa ham signal ketmasligi kerak.
MEBEL_WORKER = SimpleNamespace(
    id=2, full_name="Mebel Ishchisi", telegram_id=200, manager_id=5, role=Role.WORKER,
    department_id=MEBEL_DEPT,
)
MANAGER = SimpleNamespace(
    id=5, full_name="Rahbar", telegram_id=500, manager_id=None, role=Role.SUPERVISOR,
    department_id=NAZORAT_DEPT,
)
ADMIN = SimpleNamespace(
    id=9, full_name="Admin", telegram_id=900, manager_id=None, role=Role.ADMIN, department_id=None
)
# Ikkinchi admin ATAYLAB bor: rekursiya/kaskad xavfi aynan BIR NECHTA admin
# bo'lganda paydo bo'ladi (A haqidagi signal B'ga ketadi, B ham bloklagan
# bo'lsa — B haqidagi signal A'ga, va hokazo).
ADMIN2 = SimpleNamespace(
    id=10, full_name="Admin Ikki", telegram_id=901, manager_id=None, role=Role.ADMIN,
    department_id=None,
)
PEOPLE = [WORKER, MEBEL_WORKER, MANAGER, ADMIN, ADMIN2]

DEPARTMENTS = {
    MEBEL_DEPT: SimpleNamespace(id=MEBEL_DEPT, module="mebel"),
    NAZORAT_DEPT: SimpleNamespace(id=NAZORAT_DEPT, module="fasad_sex"),
}


class _FakeDepartmentRepo:
    def __init__(self, _session):
        pass

    async def get_by_id(self, department_id):
        return DEPARTMENTS.get(department_id)


class _FakeBot:
    def __init__(self, blocked=()):
        self.blocked = set(blocked)
        self.sent = []
        self.calls = 0

    async def send_message(self, chat_id, text, reply_markup=None):
        self.calls += 1
        assert self.calls < 50, "cheksiz rekursiya: bloklangan chat yana bloklanish signalini qo'zg'atdi"
        if int(chat_id) in self.blocked:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")
        self.sent.append((int(chat_id), text))


class _FakeEmployeeRepo:
    def __init__(self, _session):
        pass

    async def get_by_telegram_id(self, telegram_id):
        return next((p for p in PEOPLE if p.telegram_id == telegram_id), None)

    async def get_by_id(self, employee_id):
        return next((p for p in PEOPLE if p.id == employee_id), None)

    async def list_by_role(self, role, *, active_only=True):
        return [p for p in PEOPLE if p.role == role]


class _FakeSession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc_info):
        return False


async def main() -> None:
    original_session, original_repo = ns.async_session, ns.EmployeeRepository
    original_dept_repo = ns.DepartmentRepository
    ns.async_session = lambda: _FakeSession()
    ns.EmployeeRepository = _FakeEmployeeRepo
    ns.DepartmentRepository = _FakeDepartmentRepo
    try:
        # --- 1. Bloklangan xodim -> rahbar + admin signal oladi ---
        ns._blocked_reported.clear()
        bot = _FakeBot(blocked=[WORKER.telegram_id])
        ok = await ns._send(bot, WORKER.telegram_id, "Yangi vazifa")
        assert ok is False, "bloklangan chatga yuborish False qaytarishi kerak"
        alerted = {chat_id for chat_id, _ in bot.sent}
        assert alerted == {MANAGER.telegram_id, ADMIN.telegram_id, ADMIN2.telegram_id}, (
            f"rahbar va barcha adminlar signal olishi kerak, kelgan: {alerted}"
        )
        assert all(WORKER.full_name in text for _, text in bot.sent)

        # --- 2. Takroriy urinish qayta signal QILMAYDI (spam bo'lmasin) ---
        before = len(bot.sent)
        await ns._send(bot, WORKER.telegram_id, "Yana bir vazifa")
        assert len(bot.sent) == before, "bir xil xodim haqida ikkinchi marta signal ketmasligi kerak"

        # --- 3. REKURSIYA/KASKAD: ikkala adminning O'ZI ham bloklagan ---
        # `_report_blocked()` ichidagi yuborishlar `report_block=False` bilan
        # ketadi, ya'ni admin haqidagi YANGI signal umuman qo'zg'atilmaydi.
        # Usiz: A bloklangani B'ga xabar qiladi, B bloklangani A'ga... —
        # bitta hodisadan kaskad chiqadi.
        ns._blocked_reported.clear()
        bot = _FakeBot(blocked=[WORKER.telegram_id, ADMIN.telegram_id, ADMIN2.telegram_id])
        await ns._send(bot, WORKER.telegram_id, "Yangi vazifa")
        assert [c for c, _ in bot.sent] == [MANAGER.telegram_id], (
            "faqat rahbar xabar olishi kerak (ikkala admin bloklagan), kaskadsiz"
        )
        # 1 ta asl xabar + 3 ta signal urinishi (rahbar, admin, admin2) = 4.
        # Kaskad boshlansa bu son keskin oshadi.
        assert bot.calls == 4, f"ortiqcha yuborish urinishi bor (kaskad): {bot.calls}"
        assert not any(ADMIN.full_name in text for _, text in bot.sent), (
            "adminning o'zi bloklagani haqida yangi signal qo'zg'atilmasligi kerak"
        )

        # --- 4. Sex GURUHI (xodim emas) — signal qo'zg'atmaydi ---
        ns._blocked_reported.clear()
        bot = _FakeBot(blocked=[])
        bot.blocked.add(-1001234567890)
        await ns._send(bot, "-1001234567890", "Guruhga xabar")
        assert bot.sent == [], "guruh uchun 'xodim bloklagan' signali yuborilmasligi kerak"

        # --- 5. MEBEL MUZLATILGAN: mebel xodimi bloklasa signal KETMAYDI ---
        # Bu yangi kanal (TZ 5.6) faqat Nazorat Trello talabi; mebel
        # adminlariga ilgari bo'lmagan xabar yubormaslik kerak.
        ns._blocked_reported.clear()
        bot = _FakeBot(blocked=[MEBEL_WORKER.telegram_id])
        await ns._send(bot, MEBEL_WORKER.telegram_id, "Yangi vazifa")
        assert bot.sent == [], "mebel xodimi uchun bloklash signali yuborilmasligi kerak"

        # --- 6. Noma'lum telegram_id (bazada yo'q) — jim o'tadi ---
        ns._blocked_reported.clear()
        bot = _FakeBot(blocked=[777])
        await ns._send(bot, 777, "salom")
        assert bot.sent == [], "bazada yo'q chat uchun signal yuborilmaydi"
    finally:
        ns.async_session, ns.EmployeeRepository = original_session, original_repo
        ns.DepartmentRepository = original_dept_repo
        ns._blocked_reported.clear()

    print("test_blocked_notify: HAMMASI O'TDI")


if __name__ == "__main__":
    asyncio.run(main())
