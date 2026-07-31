"""Mini App statik fayllari `Cache-Control` header'i bilan berilishini
tekshiradi (`miniapp/server.py`'ning `no_cache_middleware`'i).

Nega kerak: header bo'lmasa Telegram WebView eski `app.js`ni keshda saqlab
qoladi va deploy'dan keyin foydalanuvchi yangi kodni ko'rmaydi (Telegram'ni
to'liq yopib qayta ochishi kerak bo'ladi) — haqiqiy uchragan muammo.

Bazaga ulanmaydi, Telegram'ga chiqmaydi: soxta Bot obyekti bilan ilova
ko'tariladi va localhost'dagi efemer portga so'rov yuboriladi. Oddiy
`python tests/test_miniapp_cache_headers.py` bilan ishlaydi (loyihada
pytest yo'q).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402

from miniapp.server import create_app  # noqa: E402


async def _run() -> None:
    # create_app faqat `app["bot"] = bot` uchun ishlatadi — hech qachon
    # chaqirmaydi, shuning uchun istalgan obyekt bo'lishi mumkin.
    app = create_app(bot=object())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = runner.addresses[0][1]

    try:
        async with aiohttp.ClientSession() as session:
            # 1) "/" (index.html — aniq route, `_index`)
            async with session.get(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200, resp.status
                assert resp.headers.get("Cache-Control") == "no-cache", resp.headers.get("Cache-Control")

            # 2) statik fayl (`add_static` — aynan keshlanib qolgan yo'l)
            async with session.get(f"http://127.0.0.1:{port}/js/app.js") as resp:
                assert resp.status == 200, resp.status
                assert resp.headers.get("Cache-Control") == "no-cache", resp.headers.get("Cache-Control")
                # 304 revalidatsiya ishlashi uchun ETag/Last-Modified kerak —
                # `no-store` emas, `no-cache` tanlanganining sababi shu.
                assert resp.headers.get("ETag") or resp.headers.get("Last-Modified")

            # 3) API sub-app javobi ham keshlanmasligi kerak. Auth'siz 401
            #    qaytadi — middleware baribir header qo'shishi shart.
            async with session.get(f"http://127.0.0.1:{port}/api/miniapp/me") as resp:
                assert resp.headers.get("Cache-Control") == "no-cache", resp.headers.get("Cache-Control")
    finally:
        await runner.cleanup()

    print("test_miniapp_cache_headers: 3/3 OK (index, statik fayl, API javobi)")


asyncio.run(_run())
