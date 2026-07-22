"""Mini App HTTP serveri (aiohttp): statik frontend + `/api/miniapp/*` REST
API. Bot jarayoni ichida, `main.py`da polling bilan bir vaqtda ishga
tushadi (`asyncio.gather`) — alohida deploy/servis emas.

Rol bo'yicha ruxsat sub-app darajasida ulanadi (`role_middleware`): parent
`api_app`ning `auth_middleware`si `request["employee"]`ni o'rnatadi, har bir
rol sub-app'i (`/admin`, `/brigadier`, `/seller`) o'z ustiga qo'shimcha
tekshiruv qo'shadi. `common`/`worker` sub-app darajasiga muhtoj emas — har
qanday RO'YXATDAN O'TGAN xodim uchun ochiq (worker amallari chatdagi kabi
faqat vazifaga BIRIKTIRILGAN bo'lishga tayanadi, rolga emas)."""

from pathlib import Path

from aiogram import Bot
from aiohttp import web

from miniapp.api import admin, brigadier, common, seller, worker
from miniapp.auth import auth_middleware, role_middleware
from utils.enums import Role

PUBLIC_DIR = Path(__file__).resolve().parent / "public"


def create_app(bot: Bot) -> web.Application:
    api_app = web.Application(middlewares=[auth_middleware])
    api_app.add_routes(common.routes)
    api_app.add_routes(worker.routes)

    admin_app = web.Application(middlewares=[role_middleware(Role.ADMIN, Role.SUPERVISOR)])
    admin_app.add_routes(admin.routes)
    api_app.add_subapp("/admin", admin_app)

    brigadier_app = web.Application(middlewares=[role_middleware(Role.BRIGADIER, Role.SUPERVISOR)])
    brigadier_app.add_routes(brigadier.routes)
    api_app.add_subapp("/brigadier", brigadier_app)

    seller_app = web.Application(middlewares=[role_middleware(Role.SELLER)])
    seller_app.add_routes(seller.routes)
    api_app.add_subapp("/seller", seller_app)

    app = web.Application()
    app["bot"] = bot
    app.add_subapp("/api/miniapp", api_app)
    app.router.add_static("/", PUBLIC_DIR, show_index=False)
    return app


async def run(bot: Bot, port: int) -> None:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
