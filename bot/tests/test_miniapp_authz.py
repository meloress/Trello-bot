"""Mini App ruxsat (authorization) tekshiruvlari — HAQIQIY HTTP so'rovlar
orqali, `04-texnik-qarz-topilmalar.md`dagi "faqat kod o'qish bilan
tasdiqlangan" kamchiligini yopadi.

Ikki qatlam tekshiriladi:
  1. `_department_scope_ok()` — sof funksiya sifatida, hamma rol
     kombinatsiyasida (nazoratchi o'z bo'limidan tashqariga kira olmasligi).
  2. Butun HTTP zanjiri — `auth_middleware` (initData HMAC imzosi) +
     `role_middleware` (sub-app rol darveshi) + endpoint ichidagi
     bo'lim-cheklash — haqiqiy `aiohttp` server, haqiqiy imzolangan
     so'rovlar bilan.

Bazaga ULANMAYDI va Telegram'ga chiqmaydi: `miniapp.auth`ning DB
qidiruvi soxta obyektlar bilan almashtiriladi, so'rovlar esa
localhost'dagi efemer portga boradi. Tanlangan endpoint'lar bo'lim
tekshiruvidan O'TA OLMAGAN holatda bazaga umuman murojaat qilmaydi —
shuning uchun rad etish yo'lini bazasiz sinash mumkin.

Oddiy `python tests/test_miniapp_authz.py` bilan ishlaydi (pytest yo'q).
"""

import asyncio
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

from utils.enums import Role  # noqa: E402

BOT_TOKEN = "123456:TEST-TOKEN-NOT-REAL"


def _emp(role, department_id, telegram_id=555, is_active=True):
    return SimpleNamespace(
        id=1, role=role, department_id=department_id,
        telegram_id=telegram_id, is_active=is_active, full_name="Test Xodim",
    )


# --------------------------------------------------------------------------
# 1-qatlam: `_department_scope_ok()` sof funksiya sifatida
# --------------------------------------------------------------------------

def test_scope_function():
    from miniapp.api.admin import _department_scope_ok

    cases = [
        # (rol,               xodim bo'limi, so'ralgan bo'lim, kutilgan)
        (Role.ADMIN,          None,  7,    True),   # admin cheklovsiz
        (Role.ADMIN,          3,     7,    True),   # bo'limli admin ham cheklovsiz
        (Role.SUPERVISOR,     3,     3,    True),   # o'z bo'limi — mumkin
        (Role.SUPERVISOR,     3,     7,    False),  # BOSHQA bo'lim — RAD
        (Role.SUPERVISOR,     3,     None, False),  # bo'limsiz resurs — RAD
        (Role.SUPERVISOR,     None,  7,    True),   # global nazoratchi — cheklovsiz
        (Role.WORKER,         3,     7,    True),   # bu funksiya ishchini cheklamaydi
        (Role.BRIGADIER,      3,     7,    True),   #   (ular boshqa gate ostida)
    ]
    for role, own_dept, target_dept, expected in cases:
        request = {"employee": _emp(role, own_dept)}
        got = _department_scope_ok(request, target_dept)
        assert got is expected, f"{role.value} own={own_dept} target={target_dept}: {got} != {expected}"
    print(f"  1-qatlam: _department_scope_ok {len(cases)}/{len(cases)} holat to'g'ri")


# --------------------------------------------------------------------------
# 2-qatlam: haqiqiy HTTP — imzo + rol darveshi + bo'lim cheklash
# --------------------------------------------------------------------------

def _sign_init_data(telegram_id: int, token: str = BOT_TOKEN) -> str:
    """Telegram WebApp initData'sini haqiqiy qoidasi bo'yicha imzolaydi
    (secret = HMAC_SHA256("WebAppData", bot_token)) — `miniapp/auth.py`
    aynan shu tekshiruvni bajaradi."""
    pairs = {
        "auth_date": str(int(time.time())),
        "query_id": "TEST",
        "user": json.dumps({"id": telegram_id, "first_name": "Test"}),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _install_fake_auth_db(employee):
    """`auth_middleware`ning DB qidiruvini almashtiradi — shu test uchun
    haqiqiy Postgres kerak emas. Qaytarilgan funksiya asl holatni tiklaydi."""
    import miniapp.auth as auth

    original_session, original_repo, original_token = (
        auth.async_session, auth.EmployeeRepository, auth.settings.bot_token,
    )

    class _FakeRepo:
        def __init__(self, session):
            pass

        async def get_by_telegram_id(self, telegram_id):
            if employee is None or employee.telegram_id != telegram_id:
                return None
            return employee

    auth.async_session = lambda: _FakeSession()
    auth.EmployeeRepository = _FakeRepo
    auth.settings.bot_token = BOT_TOKEN

    def restore():
        auth.async_session = original_session
        auth.EmployeeRepository = original_repo
        auth.settings.bot_token = original_token

    return restore


async def _serve(app):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    return runner, runner.addresses[0][1]


async def test_http_layer():
    from miniapp.server import create_app

    # Nazoratchi (SUPERVISOR), 3-bo'limga biriktirilgan.
    supervisor = _emp(Role.SUPERVISOR, department_id=3, telegram_id=555)
    restore = _install_fake_auth_db(supervisor)
    runner, port = await _serve(create_app(bot=object()))
    base = f"http://127.0.0.1:{port}/api/miniapp"

    try:
        async with aiohttp.ClientSession() as http:
            signed = {"X-Telegram-Init-Data": _sign_init_data(555)}

            # (a) O'Z bo'limi bo'lmagan bo'limni tahrirlash -> 403.
            #     Bu endpoint bo'lim tekshiruvidan o'tmasa bazaga TEGMAYDI.
            async with http.post(f"{base}/admin/departments/7", headers=signed, json={}) as r:
                assert r.status == 403, f"boshqa bo'lim tahriri 403 kutilgan, {r.status} keldi"
                assert "doirangizda emas" in (await r.json())["error"]

            # (b) Boshqa bo'lim statistikasi -> 403 (xuddi shunday, bazasiz).
            async with http.get(f"{base}/admin/stats/capacity?department_id=7", headers=signed) as r:
                assert r.status == 403, f"boshqa bo'lim statistikasi 403 kutilgan, {r.status} keldi"

            # (c) Imzosiz so'rov -> 401 (auth_middleware).
            async with http.get(f"{base}/admin/stats/capacity?department_id=3") as r:
                assert r.status == 401, f"imzosiz so'rov 401 kutilgan, {r.status} keldi"

            # (d) Buzilgan imzo -> 401. Faqat hash almashtiriladi.
            bad = _sign_init_data(555).replace("hash=", "hash=00")
            async with http.get(f"{base}/admin/stats/capacity?department_id=3",
                                headers={"X-Telegram-Init-Data": bad}) as r:
                assert r.status == 401, f"buzilgan imzo 401 kutilgan, {r.status} keldi"

            # (e) BOSHQA bot tokeni bilan imzolangan (o'g'irlangan/soxta) -> 401.
            other = _sign_init_data(555, token="999:BOSHQA-TOKEN")
            async with http.get(f"{base}/admin/stats/capacity?department_id=3",
                                headers={"X-Telegram-Init-Data": other}) as r:
                assert r.status == 401, f"boshqa token bilan imzo 401 kutilgan, {r.status} keldi"
        print("  2-qatlam: nazoratchi cheklovi + imzo tekshiruvi 5/5 OK")
    finally:
        await runner.cleanup()
        restore()


async def test_role_gate():
    """Rol darveshi: ISHCHI `/admin/*` ga umuman kira olmasligi kerak
    (sub-app darajasidagi `role_middleware`) — bo'lim tekshiruviga
    yetib ham bormaydi."""
    from miniapp.server import create_app

    worker = _emp(Role.WORKER, department_id=3, telegram_id=777)
    restore = _install_fake_auth_db(worker)
    runner, port = await _serve(create_app(bot=object()))
    base = f"http://127.0.0.1:{port}/api/miniapp"

    try:
        async with aiohttp.ClientSession() as http:
            signed = {"X-Telegram-Init-Data": _sign_init_data(777)}
            for path in ("/admin/stats/capacity?department_id=3", "/brigadier/brigade", "/seller/leads"):
                async with http.get(f"{base}{path}", headers=signed) as r:
                    assert r.status == 403, f"ishchi uchun {path}: 403 kutilgan, {r.status} keldi"
                    assert (await r.json())["error"] == "forbidden"
        print("  3-qatlam: ishchi admin/brigadir/sotuvchi bo'limlariga kira olmadi 3/3 OK")
    finally:
        await runner.cleanup()
        restore()


async def test_inactive_and_unknown():
    """Ro'yxatdan o'tmagan va deaktivlashtirilgan xodim -> 403."""
    from miniapp.server import create_app

    runner, port = await _serve(create_app(bot=object()))
    base = f"http://127.0.0.1:{port}/api/miniapp"
    try:
        async with aiohttp.ClientSession() as http:
            # Notanish telegram_id (DB'da yo'q)
            restore = _install_fake_auth_db(None)
            try:
                async with http.get(f"{base}/admin/stats/capacity?department_id=3",
                                    headers={"X-Telegram-Init-Data": _sign_init_data(555)}) as r:
                    assert r.status == 403 and (await r.json())["error"] == "not_registered", r.status
            finally:
                restore()

            # Bor, lekin deaktivlashtirilgan
            restore = _install_fake_auth_db(_emp(Role.ADMIN, None, telegram_id=555, is_active=False))
            try:
                async with http.get(f"{base}/admin/stats/capacity?department_id=3",
                                    headers={"X-Telegram-Init-Data": _sign_init_data(555)}) as r:
                    assert r.status == 403 and (await r.json())["error"] == "inactive", r.status
            finally:
                restore()
        print("  4-qatlam: ro'yxatdan o'tmagan / deaktiv xodim rad etildi 2/2 OK")
    finally:
        await runner.cleanup()


async def _main():
    test_scope_function()
    await test_http_layer()
    await test_role_gate()
    await test_inactive_and_unknown()
    print("test_miniapp_authz: HAMMASI OK")


asyncio.run(_main())
