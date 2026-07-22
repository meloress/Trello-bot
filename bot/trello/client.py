"""Trello REST API bilan asinxron ishlash uchun yupqa wrapper (aiohttp asosida).

Xavfsizlik: API key/token faqat so'rov parametrlari sifatida (aiohttp `params=`
orqali, avtomatik URL-encode qilingan holda) yuboriladi — hech qachon loglarga
yoki foydalanuvchiga ko'rinadigan xabarlarga chiqarilmaydi (`TrelloAPIError`
xabari faqat status va Trello javobini o'z ichiga oladi, so'rov parametrlarini
emas). Har so'rov uchun aniq timeout bor — tarmoq muammosida bot cheksiz
"osilib" qolmaydi.
"""

from datetime import datetime

import aiohttp

TRELLO_BASE_URL = "https://api.trello.com/1"
DEFAULT_TIMEOUT_SECONDS = 15.0


class TrelloAPIError(Exception):
    """Trello API muvaffaqiyatsiz (4xx/5xx) javob qaytardi."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"Trello API xatosi (status={status}): {body[:500]}")


class TrelloClient:
    """`async with` ichida ishlatiladi — har chaqiruv o'z aiohttp sessiyasini
    ochib-yopadi, global/uzoq umr ko'radigan holat saqlanmaydi."""

    def __init__(
        self, api_key: str, token: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        self._auth = {"key": api_key, "token": token}
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "TrelloClient":
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, *, params: dict | None = None) -> object:
        if self._session is None:
            raise RuntimeError("TrelloClient faqat 'async with TrelloClient(...) as client' ichida ishlatiladi")

        full_params = {**self._auth, **(params or {})}
        async with self._session.request(method, f"{TRELLO_BASE_URL}{path}", params=full_params) as response:
            body = await response.text()
            if response.status >= 400:
                raise TrelloAPIError(response.status, body)
            if not body:
                return None
            return await response.json(content_type=None)

    async def create_board(self, name: str) -> dict:
        """Yangi Trello board yaratadi (masalan demo/ko'rgazma ma'lumotlari
        uchun, real "Fasad seh"/"Test" board'lariga tegmasdan)."""
        return await self._request("POST", "/boards", params={"name": name})

    async def create_list(self, board_id: str, name: str) -> dict:
        """Berilgan board'da yangi list (ustun) yaratadi."""
        return await self._request(
            "POST", "/lists", params={"name": name, "idBoard": board_id}
        )

    async def create_card(
        self, list_id: str, name: str, desc: str = "", due: datetime | None = None
    ) -> dict:
        """Trello'da yangi karta yaratadi. Muvaffaqiyatli bo'lsa to'liq JSON
        javobini qaytaradi (kamida `id`, `shortLink`, `url` maydonlari bor)."""
        params = {"idList": list_id, "name": name, "desc": desc}
        if due is not None:
            params["due"] = due.isoformat()
        return await self._request("POST", "/cards", params=params)

    async def get_card(self, card_id: str) -> dict:
        """Kartaning joriy holatini oladi (6.3-band: kunlik sinxronizatsiya
        uchun) — `name`, `closed`, `due`, `idBoard`, `idLabels`, `idList`
        maydonlarini qaytaradi (`idList` — 6.1/7.4-band: karta qaysi bo'lim
        list'ida turganini tekshirish uchun). Karta Trello'da butunlay
        o'chirilgan bo'lsa, Trello 404 qaytaradi va bu
        `TrelloAPIError(status=404, ...)` sifatida ko'tariladi."""
        return await self._request(
            "GET", f"/cards/{card_id}", params={"fields": "name,closed,due,idBoard,idLabels,idList"}
        )

    async def list_board_labels(self, board_id: str) -> list[dict]:
        """Board'dagi barcha labellarni oladi (`id`, `name`, `color`)."""
        return await self._request(
            "GET", f"/boards/{board_id}/labels", params={"fields": "name,color"}
        )

    async def create_label(self, board_id: str, name: str, color: str) -> dict:
        """Board'da yangi label yaratadi (masalan status-rang uchun, 6.3-band)."""
        return await self._request(
            "POST", f"/boards/{board_id}/labels", params={"name": name, "color": color}
        )

    async def add_label_to_card(self, card_id: str, label_id: str) -> None:
        await self._request("POST", f"/cards/{card_id}/idLabels", params={"value": label_id})

    async def remove_label_from_card(self, card_id: str, label_id: str) -> None:
        await self._request("DELETE", f"/cards/{card_id}/idLabels/{label_id}")

    async def move_card_to_list(self, card_id: str, list_id: str) -> None:
        """Kartani boshqa list'ga ko'chiradi (6.1/7.4-band: ko'p bosqichli
        buyurtma bir bo'limdan keyingisiga o'tganda, bitta karta list'lar
        orasida ko'chib yuradi)."""
        await self._request("PUT", f"/cards/{card_id}", params={"idList": list_id})

    async def get_member_id(self, username: str) -> str:
        """6.2-band: Trello username -> a'zo ID (24 xonali hex). Username
        topilmasa Trello 404 qaytaradi (`TrelloAPIError(status=404, ...)`) —
        chaqiruvchi (employee_management.py) buni "username topilmadi" deb
        foydalanuvchiga ko'rsatadi."""
        member = await self._request("GET", f"/members/{username}", params={"fields": "id"})
        return member["id"]

    async def add_member_to_card(self, card_id: str, member_id: str) -> None:
        await self._request("POST", f"/cards/{card_id}/idMembers", params={"value": member_id})

    async def remove_member_from_card(self, card_id: str, member_id: str) -> None:
        await self._request("DELETE", f"/cards/{card_id}/idMembers/{member_id}")

    async def create_checklist(self, card_id: str, name: str) -> dict:
        """6.2-band: kartaga yangi checklist qo'shadi (bo'lim zanjiri
        bosqichlari uchun, `task_service.create_task()`)."""
        return await self._request("POST", "/checklists", params={"idCard": card_id, "name": name})

    async def add_checklist_item(self, checklist_id: str, name: str) -> dict:
        return await self._request(
            "POST", f"/checklists/{checklist_id}/checkItems", params={"name": name}
        )

    async def check_checklist_item_by_name(self, card_id: str, checklist_id: str, item_name: str) -> None:
        """Checklist punktini NOMI bo'yicha topib "complete" deb belgilaydi
        (`advance_task_stage()`: eski bosqich nomi shu orqali belgilanadi).
        Mos punkt topilmasa (masalan qo'lda o'chirilgan bo'lsa) jim
        o'tkaziladi — bu ikkinchi-darajali effekt, asosiy oqimni to'xtatmaydi."""
        items = await self._request(
            "GET", f"/checklists/{checklist_id}/checkItems", params={"fields": "name"}
        )
        match = next((item for item in items if item.get("name") == item_name), None)
        if match is None:
            return
        await self._request(
            "PUT", f"/cards/{card_id}/checkItem/{match['id']}", params={"state": "complete"}
        )
