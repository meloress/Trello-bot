"""Telegram WebApp `initData` autentifikatsiyasi (Telegram hujjatlari
bo'yicha HMAC-SHA256 imzo tekshiruvi). Chat handlerlardagi
`middlewares/auth.py`ning Mini App analogi: shu yerda ham foydalanuvchi
`employees.telegram_id` orqali aniqlanadi va so'rovga biriktiriladi — lekin
manba Telegram update emas, brauzer yuborgan `X-Telegram-Init-Data` header.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from aiohttp import web

from config import settings
from core.database import async_session
from db.repositories import EmployeeRepository
from utils.enums import Role

logger = logging.getLogger(__name__)

INIT_DATA_MAX_AGE_SECONDS = 24 * 3600
INIT_DATA_HEADER = "X-Telegram-Init-Data"


class InitDataInvalidError(Exception):
    """`initData` imzosi noto'g'ri, eskirgan yoki formatga mos emas."""


def _verify_init_data(init_data: str, bot_token: str) -> dict[str, str]:
    if not init_data:
        raise InitDataInvalidError("initData bo'sh")

    pairs = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataInvalidError("hash maydoni yo'q")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InitDataInvalidError("hash mos kelmadi")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise InitDataInvalidError("auth_date noto'g'ri")
    if time.time() - auth_date > INIT_DATA_MAX_AGE_SECONDS:
        raise InitDataInvalidError("initData muddati o'tgan")

    return pairs


@web.middleware
async def auth_middleware(request: web.Request, handler):
    init_data = request.headers.get(INIT_DATA_HEADER, "")
    try:
        pairs = _verify_init_data(init_data, settings.bot_token)
        user = json.loads(pairs["user"])
        telegram_id = int(user["id"])
    except (InitDataInvalidError, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.info("Mini App autentifikatsiya rad etildi: %s", exc)
        return web.json_response({"error": "unauthorized"}, status=401)

    async with async_session() as session:
        employee = await EmployeeRepository(session).get_by_telegram_id(telegram_id)

    if employee is None:
        return web.json_response({"error": "not_registered"}, status=403)
    if not employee.is_active:
        return web.json_response({"error": "inactive"}, status=403)

    request["employee"] = employee
    return await handler(request)


def role_middleware(*roles: Role):
    """Sub-app darajasida ulanadigan rol tekshiruvi — `RoleAccessMiddleware`ning
    Mini App analogi. `auth_middleware` allaqachon `request["employee"]`ni
    o'rnatgan bo'lishi kerak (parent app'da ulangan)."""

    @web.middleware
    async def middleware(request: web.Request, handler):
        employee = request.get("employee")
        if employee is None or (roles and employee.role not in roles):
            return web.json_response({"error": "forbidden"}, status=403)
        return await handler(request)

    return middleware
