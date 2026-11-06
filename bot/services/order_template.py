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

import math
import re
from datetime import datetime, timedelta, timezone

from utils.formatters import TASHKENT_TZ

HOUSE_MIN_ORDERS = 3
# Kontrol (Avaz aka) 1 kun; Abdulloh: jiyan 2 + kroychi 2 — karta unga o'tgan kundan (foydalanuvchi, 2026-11-06)
KONTROL_DAYS, KROY_DAYS, GIPLAB_DAYS = 1, 2 + 2, 1
SEH_DAYS = {"SHPON": 15, "LAMINOX": 7, "EMAN": 7}  # eman = laminox (foydalanuvchi, 2026-11-05)
_NUMBER = re.compile(r"\b(\d{3,5})\b")
_HEADER = re.compile(r"\b(\d{3,5})\s+(.+?)\s*\(\s*([^)]*?)\s*\)")
_DATES = re.compile(r"(\d{1,2})\.(\d{1,2})\.?\s*[-/]+\s*(\d{1,2})\.{1,2}(\d{1,2})")
_LATER = ("korpus sehga keldi", "korpus sklad", "dostavka", "pul olinishi")
# ustanovka: "Dastafka qilingan" -> brigada/ustanovka listlari -> "yopilgan zakazlar(punkti kop zakazlar)";
# korpus kartasi esa "bitkan korpuslar (ARXIV)" ga tushadi — u ham yopilgan (2026-11-06, real doska)
_UST = ("dastafka qilingan", "ustanovka", "brigada")
_CLOSED = ("yopilgan zakaz", "bitkan korpus", "yopildi")

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
    if any(k in n for k in _CLOSED):
        return "CLOSED"
    if any(k in n for k in _UST):
        return "UST"
    if any(k in n for k in _LATER):
        return "FINISH"
    return None


# sehdan keyingi listlar (sklad'ni o'tkazib yuborgan karta uchun "sehdan chiqdi")
_AFTER_SEH = ("FINISH", "UST", "CLOSED")
# zakaz shu yerda tugaydi — 5 daqiqalik yurish faqat shunda karta tarixini so'raydi
FINISH_KINDS = ("CLOSED",)


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


_DATE_LIST = re.compile(r"^\s*\d{1,2}\s+[a-z']+\s*$", re.I)


def is_date_list(list_name: str) -> bool:
    """"13 DEKABR", "1 NOYABR" — eslatma nusxalar turadigan sana listlari (zakaz u yerdan o'tmaydi)."""
    return bool(_DATE_LIST.match(list_name or ""))


def name_issues(all_cards, list_names: dict, since: datetime, tracked_ids: set):
    """Nazoratchiga: odam qo'li bilan yozilgan, bot to'g'ri o'qiy olmaydigan
    kartalar (`since` dan keyingilari). Qaytaradi: [(sarlavha, [qator, ...])]."""
    bad, reused, no_date, copies = [], [], [], []
    earlier = {}
    for c in sorted(all_cards, key=lambda c: card_created(c["id"])):
        lst = list_names.get(c.get("idList"), "")
        number, header = order_number(c["name"]), parse_header(c["name"])
        fresh = not c.get("closed") and card_created(c["id"]) >= since
        if fresh and number and is_date_list(lst):
            if header:
                copies.append(f"{c['name'][:90]} — «{lst}»")
            continue
        if fresh and number and not header and c["id"] not in tracked_ids:
            bad.append(f"{c['name'][:90]} — «{lst[:30]}»")
        if header and not is_date_list(lst):
            first = (header[2].split() or [""])[0].lower()
            others = {w for w in earlier.get(number, ()) if w != first}
            if fresh and others:
                reused.append(f"{c['name'][:90]} — bu raqam avval «{sorted(others)[0].capitalize()}» zakazida")
            earlier.setdefault(number, set()).add(first)
            if fresh and order_dates(c["name"], card_created(c["id"]))[1] is None:
                no_date.append(c["name"][:90])
    return [(title, lines) for title, lines in (
        ("Nomi formatda emas — guruhda topic OCHILMADI\n(to'g'ri: 2700 Ism aka Manzil buyum ( Sotuvchi ) 03.11 - 03.12)", bad),
        ("Raqam boshqa mijozda ishlatilgan — zakazlar aralashib ketadi, raqamni tekshiring", reused),
        ("Nomida topshirish sanasi yo'q — rasmda muddat chiqmaydi", no_date),
        ("Zakaz kartasi sana listiga nusxalangan — hisobga olinmadi", copies),
    ) if lines]


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


def _plan(start, kon_s, kon_e, kroy_e, gip_e, seh_days, seh_stop):
    """Reja: har bosqich oldingisining REAL tugashidan (bo'lmasa — rejasidan) boshlanadi.
    Kontrol 1 kun — karta Kontrolga tushgan paytdan (karta ochilmasdan oldingi kunlar
    Avaz akaga yozilmaydi), bo'lmasa zakaz sanasidan; Abdulloh (jiyan 2 + kroychi 2) — unga o'tgan kundan."""
    p_kon_s = kon_s or start
    p_kon_e = p_kon_s + timedelta(days=KONTROL_DAYS)
    p_kroy_s = kon_e or p_kon_e
    p_kroy_e = p_kroy_s + timedelta(days=KROY_DAYS)
    p_gip_s = kroy_e or p_kroy_e
    p_gip_e = p_gip_s + timedelta(days=GIPLAB_DAYS)
    p_seh_s = gip_e or p_gip_e
    return {"kon_s": p_kon_s, "kon_e": p_kon_e, "kroy_s": p_kroy_s, "kroy_e": p_kroy_e, "gip_s": p_gip_s, "gip_e": p_gip_e,
            "seh_s": p_seh_s, "seh_e": p_seh_s + timedelta(days=seh_days) + seh_stop}


def analyze(card: dict, events, sibling_events=(), now: datetime | None = None, people=()) -> dict:
    """Bitta kartaning tarixidan bosqich sanalari. events — kartaning o'z
    [(vaqt, list nomi)] tarixi; sibling_events — shu raqamli boshqa kartalarniki
    (FASAD karta GIPLAB'da korpus kartadan nusxalanadi — kontrol/kroy tarixi o'sha
    kartada); people — [(vaqt, ism)]: kartaga qo'shilgan ishchi/brigadirlar.
    Imzo faqat haqiqiy o'zgarishda o'zgaradi (kun hisobi kiritilmagan)."""
    now = now or datetime.now(timezone.utc)
    events = sorted(events)
    created = card_created(card["id"])
    start, deadline = order_dates(card["name"], created)
    start = start or created.astimezone(TASHKENT_TZ)

    first = {}
    for at, lst in events:
        first.setdefault(stage_kind(lst), at)

    spans = {}
    for stage in ("KONTROL", "KROY", "GIPLAB"):
        own = _span(events, stage)
        others = [s for s in (_span(sorted(ev), stage) for ev in sibling_events) if s[0]]
        s0 = min([x for x in [own[0]] + [s[0] for s in others] if x], default=None)
        e0 = own[1] if own[0] else next((s[1] for s in others if s[1]), None)
        spans[stage] = (s0, e0)
    (kon_s, kon_e), (kroy_s, kroy_e), (gip_s, gip_e) = spans["KONTROL"], spans["KROY"], spans["GIPLAB"]

    route = next((k[4:] for at, lst in events if (k := stage_kind(lst) or "").startswith("SEH_")), None)
    if route is None:
        akril = any((label.get("name") or "").lower().startswith("akril") for label in card.get("labels", []))
        route = "LAMINOX" if akril else "SHPON"
    seh_s = first.get("SEH_" + route)
    # sehdan chiqish: seh boshlangandan keyingi birinchi sklad (bo'lmasa — undan keyingi list);
    # sehdan OLDINGI tasodifiy ko'chirish (masalan adashib dostavkaga) chiqish emas
    after = [(at, stage_kind(lst)) for at, lst in events if seh_s is None or at >= seh_s]
    out = (next((at for at, k in after if k == "SKLAD_" + route), None)
           or next((at for at, k in after if k in _AFTER_SEH), None))
    # ustanovka: sklad'dan keyin "Dastafka qilingan"/brigada -> "yopilgan zakazlar" ("bitkan korpuslar")
    later = [(at, k) for at, k in after if out and at >= out]
    ust_e = next((at for at, k in later if k == "CLOSED"), None)
    ust_s = next((at for at, k in later if k in ("UST", "CLOSED")), None)

    # stop: zakaz ishga tushgandan keyin (boshlang'ich "zakaz tushti stopda" kutishi stop emas)
    begun = min([x for x in (kon_s, kroy_s, gip_s, seh_s) if x], default=None)
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
    signature = "|".join([card["name"], route, *(_d(x) for x in (kon_s, kroy_s, kroy_e, gip_s, gip_e, seh_s, out,
                                                                 ust_s, ust_e)), str(stops), str(stopped_now)])
    lists = {}  # bosqich -> birinchi list nomi ("GIPLAB Abdulloh 24") — kim ishlaganini list nomidan bilish uchun
    for ev in [events, *sibling_events]:
        for _, lst in ev:
            if (k := stage_kind(lst) or "") in ("KONTROL", "KROY", "GIPLAB") or k.startswith("SEH_"):
                lists.setdefault(k[:3] if k.startswith("SEH_") else k, lst)
    return {"name": card["name"], "created": created, "start": start, "deadline": deadline, "route": route,
            "lists": lists, "kon_s": kon_s, "kon_e": kon_e,
            "kroy_s": kroy_s, "kroy_e": kroy_e, "gip_s": gip_s, "gip_e": gip_e, "seh_s": seh_s, "out": out,
            "ust_s": ust_s, "ust_e": ust_e,
            "stop": stop, "stops": stops, "stopped_now": stopped_now, "seh_stop": seh_stop,
            "last": events[-1] if events else None, "people": sorted(people), "signature": signature}


def _hours(stop: timedelta) -> str:
    hours = int(stop.total_seconds() // 3600)
    return f"{hours // 24} kun {hours % 24} soat"


def render(card: dict, events, sibling_events=(), now: datetime | None = None):
    """Eski matnli shablon: (matn, imzo, tugadi_mi). Endi faqat rasm chizilmay
    qolganda zaxira sifatida yuboriladi."""
    now = now or datetime.now(timezone.utc)
    a = analyze(card, events, sibling_events, now)
    start, deadline, kroy_s, kroy_e, gip_s, gip_e, seh_s, out = (
        a[k] for k in ("start", "deadline", "kroy_s", "kroy_e", "gip_s", "gip_e", "seh_s", "out"))
    p = _plan(start, a["kon_s"], a["kon_e"], kroy_e, gip_e, SEH_DAYS[a["route"]], a["seh_stop"])
    stop_txt = _hours(a["stop"]) + (" (hozir stopda)" if a["stopped_now"] else "") if a["stops"] else ""
    today = now.astimezone(TASHKENT_TZ)
    text = "\n".join([
        card["name"],
        " Zakaz muddatlari:",
        f" BUGUN {today:%d.%m.%y} Y.    BUYURTMANI     {(today.date() - start.date()).days}- KUNI",
        "PLAN",
        f"KROY BO'LIMI {_d(p['kroy_s'])}-{_d(p['kroy_e'])}",
        f"Real                      {_d(kroy_s)}__{_d(kroy_e)}",
        f"GIPLAB {_d(p['gip_s'])}-{_d(p['gip_e'])}",
        f"Real                      {_d(gip_s)}__{_d(gip_e)}",
        f"SEHGA O'TDI  {_d(p['seh_s'])}",
        f"real                        sehga KETTI {_d(seh_s)}",
        f"SEHDAN CHIQDI {_d(p['seh_e'])}",
        f"♦️real    {_d(out)}",
        f"USTANOVKA    real {_d(a['ust_s'])}__{_d(a['ust_e'])}",
        "",
        f"📌ZAKAZ TOPSHIRISH MUDDATI: {_d(deadline)}",
        f"♻️ZAKAZ TOPSHIRILGAN MUDDAT: {_d(a['ust_e'])}",
        f"❗️STOPDA TURGAN: {stop_txt}",
        PENALTY_FOOTER,
    ])
    return text, a["signature"], a["ust_e"] is not None


PENALTY_LINE = "Jarimalar: 1–2 kun: kuniga −1 ball  ·  2–4 kun: kuniga −3 ball  ·  4–6 kun: ish haqidan 50%  ·  6+ kun: 100%"
FINAL_LINE = "Bu oxirgi xabar — zakaz topici yopiladi (o'chirilmaydi, tarix qoladi)."
# ustanovkaga doim shu ikkalasi javobgar (foydalanuvchi, 2026-11-06)
UST_RESPONSIBLE = "Avaz Axrarov · Mohir Mavlonov"
# kartaga odam qo'shish ko'pincha listga ko'chirishdan bir necha soniya oldin bo'ladi
PEOPLE_SLACK = timedelta(minutes=10)
_LIST_TAIL = re.compile(r"\s*\d+\s*(soat|sutka)?\s*$", re.I)


def _merge(parts, s_key, e_key):
    """Bosqich butun zakaz uchun: eng erta boshlanish; tugash — shu bosqichga
    kirgan HAMMA karta chiqqanda (eng kechi)."""
    started = [p for p in parts if p[s_key]]
    s = min((p[s_key] for p in started), default=None)
    e = max(p[e_key] for p in started) if started and all(p[e_key] for p in started) else None
    return s, e


def _day(x):
    return x.astimezone(TASHKENT_TZ).date()


def _late(plan_e, real_e, current, today):
    """FARQ ustuni: tugagan — reja bilan farq; hozirgi bosqich — rejagacha qolgan kun."""
    if plan_e is None:
        return None
    if real_e:
        late = (_day(real_e) - _day(plan_e)).days
        return (f"+{late} kun", "red") if late > 0 else ("o'z vaqtida", "green")
    if current:
        left = (_day(plan_e) - today).days
        return (f"{left} kun bor", "green") if left > 0 else ("bugun", "amber") if left == 0 else (f"+{-left} kun", "red")
    return None


def _real(s, e):
    if s and e:
        return f"{_d(s)} – {_d(e)}"
    return f"{_d(s)} – davom etmoqda" if s else _d(e) if e else "—"


def _words(text, min_len=1):
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) >= min_len}


def order_view(parts, now: datetime | None = None, staff=(), penalty=None):
    """Bitta zakaz (bir raqamli hamma kartalar: korpus + FASAD ...) uchun rasm
    ma'lumoti. parts — har karta uchun `analyze()` natijasi. Zakaz OXIRGI
    kartasi ustanovkadan chiqib yopilganda tugaydi ("yopilgan zakazlar";
    korpus kartasi — "bitkan korpuslar"). staff — bazadagi ishchi/brigadir
    ismlari (list nomidagi ismni tanish uchun). penalty(soat) — botning soatbay
    jarima hisobi (`penalty_service.hourly_penalty`); BALL ustuni shu bilan.
    Qaytaradi: (model, imzo, tugadi_mi) — model `order_card_image.draw()` uchun."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(TASHKENT_TZ)
    main = min(parts, key=lambda p: p["created"])
    start, deadline = min(p["start"] for p in parts), main["deadline"]
    kon_s, kon_e = _merge(parts, "kon_s", "kon_e")
    kroy_s, kroy_e = _merge(parts, "kroy_s", "kroy_e")
    gip_s, gip_e = _merge(parts, "gip_s", "gip_e")
    seh_s = min((p["seh_s"] for p in parts if p["seh_s"]), default=None)
    out = max(p["out"] for p in parts) if all(p["out"] for p in parts) else None
    ust_s = min((p["ust_s"] for p in parts if p["ust_s"]), default=None)
    finished = all(p["ust_e"] for p in parts)
    closed = max(p["ust_e"] for p in parts) if finished else None
    plan = _plan(start, kon_s, kon_e, kroy_e, gip_e, max(SEH_DAYS[p["route"]] for p in parts),
                 max(p["seh_stop"] for p in parts))
    open_parts = [p for p in parts if not p["ust_e"]]
    stopped_now = any(p["stopped_now"] for p in open_parts)
    joined = {}  # odam zakazga BIRINCHI marta qachon qo'shilgan (FASAD nusxasi uni qayta qo'shadi — bu hisob emas)
    for at, name in sorted(x for p in parts for x in p["people"]):
        joined.setdefault(name, at)
    lists = {}
    for p in sorted(parts, key=lambda p: p["created"]):
        for k, v in p["lists"].items():
            lists.setdefault(k, v)

    def who(stage, s, e):
        """Kim: shu bosqichda kartaga qo'shilgan ishchi/brigadir; bo'lmasa — list nomidagi ism."""
        if not s:
            return None
        # bosqich tugashidan 10 daqiqa oldin qo'shilgan odam — KEYINGI bosqichniki (oldin qo'shib, keyin ko'chiradi)
        end = e - PEOPLE_SLACK if e else now
        names = [n for n, at in sorted(joined.items(), key=lambda x: x[1]) if s - PEOPLE_SLACK <= at < end]
        if names:
            return names[-1]
        words = _words(lists.get(stage))
        hits = [(n, sorted(words & _words(n, 4))) for n in staff if words & _words(n, 4)]
        if len(hits) == 1:
            return hits[0][0]
        return hits[0][1][0].capitalize() if hits else None  # ikki xodim bir xil ismli ("abdulloh") — list nomidagicha

    # (kalit, nom, real boshi, real oxiri, reja boshi, reja oxiri, kim)
    stages = [
        ("KONTROL", "Kontrol", kon_s, kon_e, plan["kon_s"], plan["kon_e"]),
        ("KROY", "Kroy", kroy_s, kroy_e, plan["kroy_s"], plan["kroy_e"]),
        ("GIPLAB", "GIPLAB", gip_s, gip_e, plan["gip_s"], plan["gip_e"]),
        ("SEH", "Seh", seh_s, out, plan["seh_s"], plan["seh_e"]),
        # ustanovka rejasi — sklad'dan zakazning topshirish muddatigacha (umumiy srok ichida)
        ("UST", "Ustanovka", ust_s, closed, out or plan["seh_e"], deadline),
    ]
    # bosqichni chetlab o'tgan karta (masalan GIPLAB'siz) — keyingi bosqich boshlangan bo'lsa o'tgan hisoblanadi
    done = {}
    for i, (key, _, s, e, _, _) in enumerate(stages):
        done[key] = bool(e) or (not s and any(x[2] or x[3] for x in stages[i + 1:]))
    current = next((key for key, *_ in stages if not done[key]), None)

    def ball(plan_e, real_e, cur):
        """Botning soatbay jarima tizimi: reja tugaganidan keyin boshlangan har soat."""
        if penalty is None or plan_e is None or not (real_e or cur):
            return 0
        hours = math.ceil(((real_e or now) - plan_e).total_seconds() / 3600)
        return (penalty(hours) or 0) if hours > 0 else 0

    rows = []
    for key, label, s, e, p_s, p_e in stages:
        rows.append((label, f"{_d(p_s)} – {_d(p_e)}" if p_e else "—", _real(s, e),
                     UST_RESPONSIBLE if key == "UST" else who(key, s, e),
                     _late(p_e, e, current == key, today.date()), ball(p_e, e, current == key)))
    late = (_day(closed) - _day(deadline)).days if finished and deadline else None
    left = (_day(deadline) - today.date()).days if deadline else None
    if finished:
        top = None if late is None else (f"{-late} kun oldin", "green") if late < 0 else \
            ("o'z kunida", "green") if late == 0 else (f"+{late} kun", "red")
        big = "" if late is None else f"{-late} kun oldin" if late < 0 else "o'z kunida" if late == 0 else f"{late} kun kech"
    else:
        top = None if left is None else (f"{left} kun bor", "green") if left > 0 else \
            ("bugun", "amber") if left == 0 else (f"+{-left} kun", "red")
        big = "" if left is None else f"{left} kun bor" if left > 0 else "bugun" if left == 0 else f"{-left} kun o'tdi"
    rows.append(("Topshirish", _d(deadline) or "—", _d(closed) or "—", None, top, round(sum(r[5] for r in rows), 2)))

    if finished:
        tone = "red" if late and late > 0 else "green"
        word = "TOPSHIRILDI — " + ("KECHIKDI" if tone == "red" else "VAQTIDA")
        line2 = f"Zakaz {_d(closed)} da yopildi — ustanovka tugadi. Kuzatuv yakunlandi."
    else:
        # banner — HOZIRGI holat: muddat o'tgan yoki hozirgi bosqich rejadan chiqqan (o'tgan kechikish jadvalda)
        now_row = rows[[key for key, *_ in stages].index(current)][4]
        behind = (left is not None and left < 0) or bool(now_row and now_row[1] == "red")
        tone = "red" if behind else "amber" if stopped_now else "blue" if current == "KONTROL" else "green"
        word = {"red": "KECHIKMOQDA", "amber": "STOPDA", "blue": "KONTROLDA", "green": "VAQTIDA"}[tone]
        lasts = [p["last"] for p in open_parts if p["last"]]
        labels = list(dict.fromkeys(_LIST_TAIL.sub("", name).strip() for _, name in lasts))
        line2 = f"Hozir ({_d(min(at for at, _ in lasts))} dan): " + " · ".join(labels) if lasts else "Hozir: —"
        if current == "KONTROL":
            line2 += " — kroy hali boshlanmagan"
    right_small = f"Topshirish muddati {_d(deadline)}" if deadline else "Topshirish muddati yozilmagan"

    def step(label, key, done_sub, cur_sub, todo_sub):
        if done[key]:
            return label, "done", done_sub
        if current == key:
            return label, "stop" if stopped_now else "run", cur_sub
        return label, "todo", todo_sub

    steps = [
        step("Kontrol", "KONTROL", _d(kon_e), f"reja {_d(plan['kon_e'])} gacha", f"reja {_d(plan['kon_e'])}"),
        step("Kroy", "KROY", _d(kroy_e), f"reja {_d(plan['kroy_e'])} gacha", f"reja {_d(plan['kroy_e'])}"),
        step("GIPLAB", "GIPLAB", _d(gip_e), f"reja {_d(plan['gip_e'])} gacha", f"reja {_d(plan['gip_e'])}"),
        step("Seh", "SEH", _real(seh_s, out) if seh_s else _d(out),
             f"{_d(seh_s)} dan" if seh_s else f"reja {_d(plan['seh_e'])} gacha", f"reja {_d(plan['seh_s'])} dan"),
        ("Sklad", "done", _d(out)) if done["SEH"] else ("Sklad", "todo", f"reja {_d(plan['seh_e'])}"),
        step("Ustanovka", "UST", _real(ust_s, closed) if ust_s else _d(closed),
             f"{_d(ust_s)} dan" if ust_s else "", ""),
        ("Topshirish", "done", _d(closed)) if finished else ("Topshirish", "todo", f"reja {_d(deadline)}" if deadline else ""),
    ]

    stop_total = max(p["stop"] for p in parts)
    stop = None
    if sum(p["stops"] for p in parts):
        stop = f"STOPDA TURGAN: jami {_hours(stop_total)}"
        stopped = [p["last"][1] for p in open_parts if p["stopped_now"]]
        if stopped:
            stop += f"   ·   hozir stopda: {_LIST_TAIL.sub('', stopped[0]).strip()}"

    header = parse_header(main["name"])
    title = main["name"].split("(")[0].strip()
    extras = [p["name"].split()[0] for p in parts if p is not main and not p["name"].split()[0].isdigit()]
    if extras:
        title += "  (+" + ", ".join(dict.fromkeys(extras)) + ")"
    bits = [f"Sotuvchi: {header[3]}"] if header and header[3] else []
    bits.append(f"Zakaz: {_d(start)}")
    if finished:
        bits += [f"Tugadi: {closed.astimezone(TASHKENT_TZ):%d.%m.%Y}", f"{(_day(closed) - start.date()).days} kunda"]
    else:
        bits += [f"Bugun: {today:%d.%m.%Y}", f"{(today.date() - start.date()).days}-kun"]
    model = {
        "title": title, "subtitle": "   ·   ".join(bits), "caption": main["name"],
        "banner": (word, line2, right_small, big, tone), "steps": steps, "rows": rows, "stop": stop,
        "footer": FINAL_LINE if finished else PENALTY_LINE,
    }
    return model, "||".join(sorted(p["signature"] for p in parts)), finished
