"""Mebel moduli: Trello doskasidagi ro'yxatlarni NOMIGA qarab tasniflash.

Nega bu kerak. Haqiqiy "Fasad seh" doskasida bitta ishlab chiqarish bosqichiga
BIR NECHTA ro'yxat to'g'ri keladi — har brigadaga bittadan ("Zoxid shpon
brigada", "Abror shpon brigada", "shkurka zokir ishlanvotti 72 soat", ...) —
ustiga kutish ro'yxatlari ("shpon hali boshlanmadik") va bosqichdan keyingi
ro'yxatlar ("dastavka qilingan", "ustanovka ishlanvotti") ham bor.
`departments.trello_list_id` bitta ustun bo'lgani uchun bu modelga sig'masdi.

Yechim: bazada BIRORTA ham ro'yxat ID'si saqlanmaydi. Har pollda doskadagi
ro'yxatlar qaytadan o'qiladi va NOMIGA qarab tasniflanadi. Natijasi:
  - Trello'da yangi brigada ro'yxati qo'shilsa — keyingi pollda o'zi tanadi;
  - ro'yxat o'chirilsa — shunchaki ro'yxatdan chiqadi, hech narsa buzilmaydi;
  - ro'yxat nomi o'zgarsa — yangi nomга qarab qayta tasniflanadi;
  - Trello hisobi/tokeni almashtirilsa — faqat doska ID'sini yangilash kifoya.

Tasniflash tartibi (MUHIM — birinchi mos kelgani g'olib):
  1. Nomda KUTISH belgisi bormi ("hali boshlanmadik", "chiqqan", "dastavka",
     "ustanovka", ...) -> QUEUE. Bu tekshiruv BIRINCHI, chunki bunday nomlarda
     bosqich nomi ham uchraydi ("shkurkadan chiqqan ..." ichida "shkurka" bor,
     lekin bu shkurka ishi emas, undan CHIQQAN buyurtmalar navbati).
  2. Nomda biror bo'limning kalit so'zi bormi -> o'sha bo'limning WORK ro'yxati.
  3. Hech qaysi -> QUEUE (xavfsiz standart: notanish ro'yxatda ish ochilmaydi).

QUEUE ro'yxatining qaysi bo'limga tegishli ekani AHAMIYATSIZ — u yerda hech
qanday vazifa ochilmaydi, xatti-harakat bir xil: shu kartaning ochiq vazifasi
bo'lsa, demak u ish ro'yxatidan chiqib ketgan, ya'ni bosqich tugagan.
"""

import re

from utils.enums import TrelloListKind

# Ro'yxat KUTISH/o'tish ro'yxati ekanini bildiruvchi nom bo'laklari (kichik
# harfda solishtiriladi). Bular ish ro'yxati EMAS: karta bu yerda navbat
# kutadi yoki bosqichdan allaqachon chiqib ketgan.
QUEUE_MARKERS = (
    "hali boshlanmadi",   # "shpon hali boshlanmadik"
    "hali tasdiqlanmadi",  # "shkurka hali tasdiqlanmadi"
    "tushmadi",            # "Fasad sehga hali kroy tushmadi"
    "chiqqan",             # "shkurkadan chiqqan rang tanlangan zakazlar"
    "dastavka",            # "dastavka qilinishi kerak" / "dastavka qilingan"
    "ustanovka",           # "ustanovka ishlanvotti"
    "bitkan",              # "100%bitkan atchot topshirilgan ..."
    "atchot",
)

# "72 soat", "24soat", "72 soat(elyor)" — ro'yxat nomidagi muddat.
_HOURS_RE = re.compile(r"(\d+)\s*soat", re.IGNORECASE)


def parse_hours(list_name: str) -> int | None:
    """Ro'yxat nomidan muddat soatini oladi ("kraska ELYOR 72 soat" -> 72).

    Muddat bazada saqlanmaydi — foydalanuvchi Trello'da nomni o'zgartirsa,
    muddat ham darhol o'zgaradi. Nomda soat bo'lmasa None (bunday ro'yxatdagi
    karta uchun kartaning O'Z `due` sanasi ishlatiladi, u ham bo'lmasa vazifa
    ochilmay kutiladi)."""
    if not list_name:
        return None
    match = _HOURS_RE.search(list_name)
    if match is None:
        return None
    hours = int(match.group(1))
    return hours if hours > 0 else None


def _keywords(department) -> list[str]:
    raw = (department.trello_list_keywords or "").strip()
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def classify_list(list_name: str, departments) -> tuple[TrelloListKind, object | None]:
    """Bitta ro'yxatni tasniflaydi.

    Qaytaradi: (kind, department). `kind=WORK` bo'lsa `department` — o'sha
    ro'yxat tegishli bo'lim; `kind=QUEUE` bo'lsa department doim None
    (kutish ro'yxatida bo'lim ahamiyatsiz, xatti-harakat bir xil)."""
    name = (list_name or "").lower()

    for marker in QUEUE_MARKERS:
        if marker in name:
            return TrelloListKind.QUEUE, None

    for department in departments:
        for keyword in _keywords(department):
            if keyword in name:
                return TrelloListKind.WORK, department

    return TrelloListKind.QUEUE, None


def build_board_map(lists: list[dict], departments) -> list[dict]:
    """Doskadagi barcha ro'yxatlarni tasniflab, bitta ro'yxat qilib qaytaradi.

    `lists` — Trello `/boards/{id}/lists` javobi (har biri {"id", "name"}).
    Har element: {"id", "name", "kind", "department", "hours"}."""
    mapped = []
    for li in lists:
        kind, department = classify_list(li.get("name", ""), departments)
        mapped.append({
            "id": li["id"],
            "name": li.get("name", ""),
            "kind": kind,
            "department": department,
            "hours": parse_hours(li.get("name", "")) if kind == TrelloListKind.WORK else None,
        })
    return mapped
