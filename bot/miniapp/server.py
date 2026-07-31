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


async def _index(request: web.Request) -> web.FileResponse:
    """`add_static` "/" so'roviga index.html'ni AVTOMATIK bermaydi (uni
    papka sifatida ko'radi, `show_index=False` bo'lgani uchun 403 qaytaradi)
    — Mini App ochilganda aynan shu "/" so'raladi, shuning uchun aniq route
    kerak. Static mount'dan OLDIN ro'yxatga olinishi kerak."""
    return web.FileResponse(PUBLIC_DIR / "index.html")


@web.middleware
async def no_cache_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Telegram'ning Mini App WebView'i statik fayllarni (JS/CSS) juda
    qattiq keshlaydi: Railway'ga deploy qilingandan keyin ham foydalanuvchi
    eski `app.js`ni ko'rib turaveradi — Telegram'ni fon/oldinga o'tkazish
    yetmaydi, uni TO'LIQ yopib qayta ochish kerak bo'lardi (haqiqiy holat).
    Sababi: `add_static`/`FileResponse` hech qanday `Cache-Control`
    yubormaydi, shuning uchun WebView o'z heuristikasi bilan keshlaydi.

    `no-cache` = "keshla, lekin ISHLATISHDAN OLDIN serverdan so'ra".
    `no-store` EMAS — `FileResponse` `Last-Modified`/`ETag` yuboradi, shuning
    uchun fayl o'zgarmagan bo'lsa javob bo'sh `304` bo'ladi (arzon), o'zgargan
    bo'lsa darhol yangisi keladi. Root ilovaga ulangani uchun statik fayllarni
    ham, `/api/miniapp/*` JSON javoblarini ham qamrab oladi — API javoblari
    ham keshlanmasligi kerak (ball/vazifa holati doim yangi bo'lsin).

    `setdefault` — agar biror handler o'zi aniq `Cache-Control` qo'ysa,
    ustidan yozilmaydi."""
    response = await handler(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    return response


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

    app = web.Application(middlewares=[no_cache_middleware])
    # `add_subapp()` sub-app "state"ni ota-ilovadan avtomatik meros qilib
    # olmaydi — shu sabab "bot" faqat shu (ROOT) darajada saqlanadi, va
    # handlerlar ichida (istalgan chuqurlikdagi sub-app bo'lsa ham)
    # `request.app["bot"]` EMAS, `request.config_dict["bot"]` orqali
    # o'qiladi (aiohttp'ning shu maqsad uchun mo'ljallangan ChainMapProxy'i —
    # `match_info.apps` bo'yicha barcha ota-ilovalarni ko'rib chiqadi).
    app["bot"] = bot
    app.add_subapp("/api/miniapp", api_app)
    app.router.add_get("/", _index)
    app.router.add_static("/", PUBLIC_DIR, show_index=False)
    return app


async def run(bot: Bot, port: int) -> None:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
