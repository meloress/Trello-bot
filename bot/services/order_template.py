"""Nazorat Trello: zakaz holati shabloni — guruhdagi har bir zakaz topiciga
yuboriladigan matn (foydalanuvchi namunasi, 2026-11-05). Faqat Trello
tarixidan quriladi; bu modul toza funksiyalar — Trello/Telegram'ga murojaat
`jobs/order_topics_job.py` da.

Foydalanuvchi qoidalari:
  - reja: KROY = Kontrol 1 + Abdulloh jiyan 2 + Abdulloh kroychi 2 kun (karta
    nomidagi zakaz sanasidan); kroy REALI esa faqat Abdullohning listiga
    ("jiyan chizish"/"kroy chizish") o'tgan kundan — Avaz akadagi kun emas; GIPLAB 1 kun, SEH: shpon 15 kun ("Shpon va
    shkurka sehta" -> "Malyarka sklad"), laminox 7 kun ("LAMINOX FAYL
    TASHKENT" -> "Laminox 100% tayyor"), eman ham 7 kun ("Eman yoki muborak fayl
    tashaldi" -> "eman 100% tayyor"); har bosqich rejasi oldingisining REAL
    tugashidan boshlanadi; stopdagi vaqt seh rejasiga qo'shiladi;
  - "sehdan chiqdi" real = sklad listiga o'tgan kun; skladni o'tkazib
    yuborgan karta — undan keyingi listga o'tgan kun;
  - topshirish muddati — karta nomidagi ikkinchi sana;
  - dostavka/ustanovka qatorlari yo'q: zakaz sklad bilan tugaydi;
  - polniy uy = bir vaqtda tushgan, ismi+manzili bir xil 3+ zakaz — bitta topic.
"""

import re
from datetime import datetime, timedelta, timezone

from utils.formatters import TASHKENT_TZ

HOUSE_MIN_ORDERS = 3
KROY_DAYS, GIPLAB_DAYS = 1 + 2 + 2, 1
SEH_DAYS = {"SHPON": 15, "LAMINOX": 7, "EMAN": 7}  # eman = laminox (foydalanuvchi, 2026-11-05)
_NUMBER = re.compile(r"\b(\d{3,5})\b")
_HEADER = re.compile(r"\b(\d{3,5})\s+(.+?)\s*\(\s*([^)]*?)\s*\)")
_DATES = re.compile(r"(\d{1,2})\.(\d{1,2})\.?\s*[-/]+\s*(\d{1,2})\.{1,2}(\d{1,2})")
_LATER = ("korpus sehga keldi", "korpus sklad", "dostavka", "dastafka", "brigada", "ustanovka",
          "arxiv", "yopilgan", "pul olinishi")

PENALTY_FOOTER = (
    "ESLATIB O'TAMIZ VAQTIDA BITIRMAGANLIK UCHUN JARIMALAR!\n"
    "1-2 KUN KUNIGA: -1balldan\n"
    "2-4 KUN KUNIGA: -3balldan\n"
    "4-6 KUN O'TSA: Ishlagan ish haqidan 50% ob qolinadi.\n"
    "6 KUNDAN KEYIN: Ish haqi 100% ob qolinadi!"
)


def stage_kind(list_name: str) -> str | None:
    """Real doskadagi list nomi -> shablon bosqichi (None = shablonga ta'sir qilmaydi)."""
    n = (list_name or "").lower()
    if "stop" in n:
        return "STOP"
    if "kantrolniy" in n:
        return "KONTROL"  # kroy REJASIGA kiradi (1 kun), lekin kroy reali emas (foydalanuvchi qarori)
    if "jiyan chizish" in n or "kroy chizish" in n:
        return "KROY"
    if "giplab" in n or "fayl yeg" in n:
        return "GIPLAB"
    if "malyarka sklad" in n:
        return "SKLAD_SHPON"
    if "laminox 100%" in n:
        return "SKLAD_LAMINOX"
    if "eman 100%" in n:
        return "SKLAD_EMAN"
    if "shpon" in n and "sehta" in n:
        return "SEH_SHPON"
    if "laminox fayl tashaldi" in n:
        return "SEH_LAMINOX"
    if "eman yoki muborak fayl" in n:
        return "SEH_EMAN"
    if any(k in n for k in _LATER):
        return "FINISH"
    return None


FINISH_KINDS = ("SKLAD_SHPON", "SKLAD_LAMINOX", "SKLAD_EMAN", "FINISH")


def card_created(card_id: str) -> datetime:
    """Trello id'ning birinchi 8 belgisi — yaratilgan vaqt (unix)."""
    return datetime.fromtimestamp(int(card_id[:8], 16), timezone.utc)


def order_number(name: str) -> str | None:
    m = _NUMBER.search(name or "")
    return m[1] if m else None


def parse_header(name: str):
    """(raqam, mijoz kaliti, mijoz matni, sotuvchi) yoki None — zakaz kartasi emas."""
    m = _HEADER.search(name or "")
    if not m:
        return None
    client = " ".join(m[2].split()[:3])  # "Ism aka Manzil"
    return m[1], client.lower(), client, m[3]


def order_dates(name: str, created: datetime):
    """Karta nomidagi "olingan - topshirish" sanalari (yilsiz) -> datetime."""
    m = _DATES.search(name or "")
    if not m:
        return None, None
    d1, m1, d2, m2 = map(int, m.groups())
    local = created.astimezone(TASHKENT_TZ)
    try:
        # yil nomda yo'q — karta ochilgan sanaga eng yaqini (dekabrda ochilgan "02.01" — keyingi yil)
        start = min((datetime(y, m1, d1, tzinfo=TASHKENT_TZ) for y in (local.year - 1, local.year, local.year + 1)),
                    key=lambda d: abs(d - local))
        end = datetime(start.year + (m2 < m1), m2, d2, tzinfo=TASHKENT_TZ)
    except ValueError:
        return None, None
    return start, end


def new_orders(new_cards, all_cards, since: datetime, tracked_numbers: set):
    """Topic kerak bo'lgan kartalar: raqami allaqachon topicda (FASAD nusxasi
    -> o'sha topicga qo'shiladi) yoki raqamning doskadagi ENG BIRINCHI kartasi
    `since` dan keyin ochilgan (yangi zakaz). Eski zakazning keyin nusxalangan
    kartasi o'tkaziladi. Yangi zakaz qaysi listda ochilishi muhim emas: 2026-07
    da "zakaz tushti stopda", 2026-10 da "KANTROLNIY AVAZ AKA" edi."""
    first_seen = {}
    for card in all_cards:
        number = order_number(card["name"])
        if number:
            created = card_created(card["id"])
            first_seen[number] = min(first_seen.get(number, created), created)
    return [(card_id, name) for card_id, name in new_cards
            if (number := order_number(name)) and (number in tracked_numbers or first_seen.get(number, since) >= since)]


def plan_topics(new_cards, numbers_threads: dict, house_threads: dict):
    """Yangi kartalarni topiclarga taqsimlaydi.

    new_cards: [(card_id, name)] — hali topicsiz kartalar.
    numbers_threads: {zakaz raqami: thread_id} — mavjud topiclar.
    house_threads: {mijoz kaliti: thread_id} — ochiq polniy uy topiclari.
    Qaytaradi: (join, create) — join: [(card_id, thread_id)];
    create: [(topic nomi, mijoz kaliti yoki None, [card_id, ...])].
    """
    join, fresh = [], {}
    for card_id, name in new_cards:
        header = parse_header(name)
        if header is None:
            continue
        number, key = header[0], header[1]
        if number in numbers_threads:
            join.append((card_id, numbers_threads[number]))
        elif key in house_threads:
            join.append((card_id, house_threads[key]))
        else:
            fresh.setdefault(key, {}).setdefault(number, []).append((card_id, name))
    create = []
    for key, by_number in fresh.items():
        if len(by_number) >= HOUSE_MIN_ORDERS:
            first = min(by_number.values())[0][1]
            _, _, client, seller = parse_header(first)
            start, _ = order_dates(first, card_created(min(by_number.values())[0][0]))
            title = f"{client} — POLNIY UY ( {seller} )" + (f" {start:%d.%m}" if start else "")
            create.append((title[:128], key, [c for cards in by_number.values() for c, _ in cards]))
        else:
            for cards in by_number.values():
                main = min(cards, key=lambda c: card_created(c[0]))  # avval yaratilgani — korpus
                create.append((main[1][:128], None, [c for c, _ in cards]))
    return join, create


def _d(x) -> str:
    return x.astimezone(TASHKENT_TZ).strftime("%d.%m") if x else ""


def _span(events, stage):
    """Bosqich: birinchi kirgan payt .. undan keyin boshqa listga birinchi chiqqan payt."""
    idx = next((i for i, (_, lst) in enumerate(events) if stage_kind(lst) == stage), None)
    if idx is None:
        return None, None
    start = events[idx][0]
    end = next((at for at, lst in events[idx:] if stage_kind(lst) != stage), None)
    return start, end


def render(card: dict, events, sibling_events=(), now: datetime | None = None):
    """(matn, imzo, tugadi_mi). events — kartaning o'z [(vaqt, list nomi)]
    tarixi; sibling_events — shu raqamli boshqa kartalarniki (FASAD karta
    GIPLAB'da korpus kartadan nusxalanadi — kroy tarixi o'sha kartada).
    Imzo faqat haqiqiy o'zgarishda o'zgaradi (kun hisobi kiritilmagan)."""
    now = now or datetime.now(timezone.utc)
    events = sorted(events)
    start, deadline = order_dates(card["name"], card_created(card["id"]))
    start = start or card_created(card["id"]).astimezone(TASHKENT_TZ)

    first = {}
    for at, lst in events:
        first.setdefault(stage_kind(lst), at)

    spans = {}
    for stage in ("KROY", "GIPLAB"):
        own = _span(events, stage)
        others = [s for s in (_span(sorted(ev), stage) for ev in sibling_events) if s[0]]
        s0 = min([x for x in [own[0]] + [s[0] for s in others] if x], default=None)
        e0 = own[1] if own[0] else next((s[1] for s in others if s[1]), None)
        spans[stage] = (s0, e0)
    (kroy_s, kroy_e), (gip_s, gip_e) = spans["KROY"], spans["GIPLAB"]

    route = next((k[4:] for at, lst in events if (k := stage_kind(lst) or "").startswith("SEH_")), None)
    if route is None:
        akril = any((label.get("name") or "").lower().startswith("akril") for label in card.get("labels", []))
        route = "LAMINOX" if akril else "SHPON"
    seh_s = first.get("SEH_" + route)
    # sehdan chiqish: seh boshlangandan keyingi birinchi sklad (bo'lmasa — undan keyingi list);
    # sehdan OLDINGI tasodifiy ko'chirish (masalan adashib dostavkaga) chiqish emas
    after = [(at, stage_kind(lst)) for at, lst in events if seh_s is None or at >= seh_s]
    out = (next((at for at, k in after if k == "SKLAD_" + route), None)
           or next((at for at, k in after if k == "FINISH"), None))

    # stop: zakaz ishga tushgandan keyin (boshlang'ich "zakaz tushti stopda" kutishi stop emas)
    begun = min([x for x in (first.get("KONTROL"), kroy_s, gip_s, seh_s) if x], default=None)
    stop, seh_stop, since, stops = timedelta(), timedelta(), None, 0
    for at, lst in events + [(now, "")]:
        if since is not None:
            stop += at - since
            if seh_s and since >= seh_s:
                seh_stop += at - since
            since = None
        if lst and stage_kind(lst) == "STOP" and begun and at >= begun and not (out and at >= out):
            since, stops = at, stops + 1
    stopped_now = bool(events) and stage_kind(events[-1][1]) == "STOP" and stops > 0

    p_kroy_e = start + timedelta(days=KROY_DAYS)
    p_gip_s = kroy_e or p_kroy_e
    p_gip_e = p_gip_s + timedelta(days=GIPLAB_DAYS)
    p_seh_s = gip_e or p_gip_e
    days = SEH_DAYS[route]
    p_seh_e = p_seh_s + timedelta(days=days) + seh_stop if days else None

    stop_txt = ""
    if stops:
        hours = int(stop.total_seconds() // 3600)
        stop_txt = f"{hours // 24} kun {hours % 24} soat" + (" (hozir stopda)" if stopped_now else "")
    today = now.astimezone(TASHKENT_TZ)
    text = "\n".join([
        card["name"],
        " Zakaz muddatlari:",
        f" BUGUN {today:%d.%m.%y} Y.    BUYURTMANI     {(today.date() - start.date()).days}- KUNI",
        "PLAN",
        f"KROY BO'LIMI {_d(start)}-{_d(p_kroy_e)}",
        f"Real                      {_d(kroy_s)}__{_d(kroy_e)}",
        f"GIPLAB {_d(p_gip_s)}-{_d(p_gip_e)}",
        f"Real                      {_d(gip_s)}__{_d(gip_e)}",
        f"SEHGA O'TDI  {_d(p_seh_s)}",
        f"real                        sehga KETTI {_d(seh_s)}",
        f"SEHDAN CHIQDI {_d(p_seh_e)}",
        f"♦️real    {_d(out)}",
        "",
        f"📌ZAKAZ TOPSHIRISH MUDDATI: {_d(deadline)}",
        f"♻️ZAKAZ TOPSHIRILGAN MUDDAT: {_d(out)}",
        f"❗️STOPDA TURGAN: {stop_txt}",
        PENALTY_FOOTER,
    ])
    signature = "|".join([card["name"], route, *(_d(x) for x in (kroy_s, kroy_e, gip_s, gip_e, seh_s, out)),
                          str(stops), str(stopped_now)])
    return text, signature, out is not None
