"""Zakaz topiclari va shabloni (2026-11-05): kim yangi zakaz, polniy uy
guruhlash, shablon sanalari. Bazasiz/tarmoqsiz: `python tests/test_order_topics.py`.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import order_template as ot  # noqa: E402

TZ = timezone(timedelta(hours=5))


def cid(at: datetime, n: int = 0) -> str:
    """Trello id: birinchi 8 belgi — yaratilgan vaqt."""
    return f"{int(at.timestamp()):08x}{n:016x}"


def t(day, month=10, hour=10):
    return datetime(2026, month, day, hour, tzinfo=TZ)


def _kinds():
    k = ot.stage_kind
    assert k("zakaz tushti stopda") == "STOP" and k("Shkurkadan chiqqan zakazla (stopda rang tanlanmagan)") == "STOP"
    # Avaz aka (kontrol) kroy REJASIGA kiradi, lekin kroy reali faqat Abdullohning listidan
    assert k("KANTROLNIY AVAZ AKA 24 soat") == "KONTROL"
    assert k("Abdulloh jiyan chizish 24 soat") == k("Abdulloh kroy chizish 24 soat") == "KROY"
    assert k("GIPLAB Abdulloh 24") == k("Fayl yeg'ish  va zapchast 24") == "GIPLAB"
    assert k("Shpon va shkurka sehta yasalvotti 15 sutka") == "SEH_SHPON"
    assert k("LAMINOX FAYL TASHALDI 24") == "SEH_LAMINOX" and k("Laminox 100% tayyor") == "SKLAD_LAMINOX"
    assert k("Malyarka sklad Qurish va O'rash 24 soat") == "SKLAD_SHPON"
    assert k("Dostavka qilinishi kerak 24") == "FINISH" and k("5 NOYABR") is None and k("taminot srochniymas") is None


def _new_orders():
    since = t(1, 11)
    old_korpus = {"id": cid(t(20, 9)), "name": "2610 Adxam aka Chig'atoy shkaf ( Husniddin ) 28.09 - 30.10"}
    fasad_copy = {"id": cid(t(2, 11)), "name": "FASAD 2610 Adxam aka Chig'atoy shkaf ( Husniddin ) 28.09 - 30.10"}
    fresh = {"id": cid(t(3, 11)), "name": "2700 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12"}
    cards = [old_korpus, fasad_copy, fresh]
    new = [(c["id"], c["name"]) for c in (fasad_copy, fresh)]
    # eski zakazning keyin nusxalangan FASAD kartasi — yangi zakaz emas
    assert ot.new_orders(new, cards, since, set()) == [(fresh["id"], fresh["name"])]
    # raqami allaqachon topicda bo'lsa — o'sha topicga qo'shiladi
    assert ot.new_orders(new, cards, since, {"2610"}) == new


def _issues():
    since = t(1, 11)
    lists = {"W": "KANTROLNIY AVAZ AKA", "D": "13 DEKABR"}
    old = {"id": cid(t(1, 9)), "name": "2700 Karim aka Yunusobod kuxnya ( Jasur ) 01.09 - 01.10", "idList": "W", "closed": True}
    cards = [
        old,
        {"id": cid(t(3, 11), 1), "name": "2700 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12", "idList": "W"},  # raqam band
        {"id": cid(t(3, 11), 2), "name": "2701 Vali aka Sergili shkaf ( Jasur )", "idList": "W"},                 # sana yo'q
        {"id": cid(t(3, 11), 3), "name": "2702 Gani aka Olmazor shkaf", "idList": "W"},                           # format
        {"id": cid(t(3, 11), 4), "name": "2703 Gul opa Tuzel shkaf ( Jasur ) 03.11 - 03.12", "idList": "D"},     # nusxa
        {"id": cid(t(3, 11), 5), "name": "2704-2710 Nodir aka Novza", "idList": "D"},                             # eslatma — jim
        {"id": cid(t(3, 11), 6), "name": "FASAD 2701 Vali aka Sergili shkaf ( Jasur ) 03.11 - 03.12", "idList": "W"},  # o'sha mijoz
    ]
    got = {title.split(" —")[0]: lines for title, lines in ot.name_issues(cards, lists, since, set())}
    assert len(got) == 4, got
    assert got["Nomi formatda emas"] == ["2702 Gani aka Olmazor shkaf — «KANTROLNIY AVAZ AKA»"]
    assert len(got["Raqam boshqa mijozda ishlatilgan"]) == 1 and "avval «Karim»" in got["Raqam boshqa mijozda ishlatilgan"][0]
    assert got["Nomida topshirish sanasi yo'q"] == ["2701 Vali aka Sergili shkaf ( Jasur )"]
    assert got["Zakaz kartasi sana listiga nusxalangan"][0].startswith("2703 Gul opa")
    # hammasi to'g'ri bo'lsa — bo'sh (nazoratchiga xabar ketmaydi)
    assert ot.name_issues([cards[6]], lists, since, set()) == []


def _plan_topics():
    house = [(cid(t(3, 11), i), f"{2700 + i} Anvar aka Tuzel xona{i} ( Jasur ) 03.11 - 30.12") for i in range(3)]
    single = [(cid(t(3, 11), 9), "2710 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12"),
              (cid(t(3, 11, 11), 10), "FASAD 2710 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12")]
    join, create = ot.plan_topics(house + single, {}, {})
    assert join == []
    titles = {title: ids for title, _, ids in create}
    assert titles["Anvar aka Tuzel — POLNIY UY ( Jasur ) 03.11"] == [c for c, _ in house], titles
    # bir raqamli korpus + FASAD — bitta topic, nomi avval ochilgan kartaniki
    assert titles[single[0][1]] == [single[0][0], single[1][0]], titles
    # 2 ta zakaz — polniy uy emas
    _, create2 = ot.plan_topics(house[:2], {}, {})
    assert len(create2) == 2 and all(key is None for _, key, _ in create2)
    # ochiq polniy uyga keyin qo'shilgan zakaz va ma'lum raqam — mavjud topicga
    later = [(cid(t(4, 11)), "2720 Anvar aka Tuzel podval ( Jasur ) 03.11 - 30.12"),
             (cid(t(4, 11), 1), "FASAD 2710 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12")]
    join, create = ot.plan_topics(later, {"2710": 55}, {"anvar aka tuzel": 77})
    assert join == [(later[0][0], 77), (later[1][0], 55)] and create == [], (join, create)


def _render():
    card = {"id": cid(t(28, 9)), "name": "FASAD 2610 Adxam aka Chig'atoy shkaf ( Husniddin ) 28.09. - 30.10", "labels": []}
    korpus = [(t(29, 9), "KANTROLNIY AVAZ AKA"), (t(5, 10), "Abdulloh kroy chizish 24"), (t(6, 10), "GIPLAB Abdulloh 24"),
              (t(12, 10, 11), "taminot srochniymas")]
    own = [(t(12, 10, 9), "Fayl yeg'ish  va zapchast 24"), (t(12, 10, 11), "taminot srochniymas"),
           (t(12, 10, 14), "Shpon va shkurka sehta yasalvotti 15 sutka"),
           (t(2, 11), "Shkurkadan chiqqan zakazla (stopda rang tanlanmagan)"), (t(4, 11), "kraska seh 72 soat")]
    now = t(5, 11)
    text, sig, finished = ot.render(card, own, [korpus], now)
    lines = text.split("\n")
    assert "BUYURTMANI     38- KUNI" in lines[2], lines[2]
    assert "KROY BO'LIMI 28.09-03.10" in text                       # 1+2+2 kun zakaz sanasidan
    assert "Real                      05.10__06.10" in text, text    # kroy tarixi korpus kartasidan; Avaz akadagi 29.09 emas
    assert "GIPLAB 06.10-07.10" in text and "06.10__12.10" in text   # reja kroyning REAL tugashidan, chiqish = birinchi boshqa list
    assert "sehga KETTI 12.10" in text
    assert "SEHDAN CHIQDI 29.10" in text, text                       # 12.10 + 15 kun + 2 kun stop
    assert "STOPDA TURGAN: 2 kun 0 soat" in text and "hozir" not in text
    assert "TOPSHIRISH MUDDATI: 30.10" in text and not finished

    # skladga chiqdi -> tugadi; imzo o'zgaradi
    done = own + [(t(6, 11), "Malyarka sklad Qurish va O'rash 24 soat"), (t(6, 11, 11), "Dostavka qilinishi kerak 24")]
    text2, sig2, finished2 = ot.render(card, done, [korpus], t(7, 11))
    assert finished2 and "♦️real    06.11" in text2 and "TOPSHIRILGAN MUDDAT: 06.11" in text2 and sig2 != sig
    # skladni o'tkazib yuborgan karta — keyingi listga o'tgan kun
    skip = own + [(t(7, 11), "Dastafka qilingan")]
    assert "♦️real    07.11" in ot.render(card, skip, [korpus], t(8, 11))[0]
    # kun o'tgani imzoni o'zgartirmaydi (har kuni qayta yuborilmaydi)
    assert ot.render(card, own, [korpus], t(6, 11))[1] == sig

    # sehdan OLDIN adashib dostavkaga qo'yilgan, keyin haqiqiy sklad — chiqish skladniki
    oops = own[:1] + [(t(12, 10, 10), "Dostavka qilinishi kerak 24")] + own[1:] + [(t(6, 11), "Malyarka sklad Qurish va O'rash")]
    assert "♦️real    06.11" in ot.render(card, oops, [korpus], t(7, 11))[0]
    # ... skladni o'tkazib yuborsa — sehdan KEYINGI list (sehdan oldingi adashish emas)
    oops2 = oops[:-1] + [(t(7, 11), "Dastafka qilingan")]
    assert "♦️real    07.11" in ot.render(card, oops2, [korpus], t(8, 11))[0]
    # yil nomda yo'q: dekabrda ochilgan "02.01" zakazi keyingi yilniki, oktabrdagi "28.09" — shu yilniki
    assert ot.order_dates("2800 A aka B ( C ) 02.01 - 15.02", t(30, 12))[0].year == 2027
    assert ot.order_dates("2800 A aka B ( C ) 28.09 - 30.10", t(2, 10)) == (t(28, 9, 0), t(30, 10, 0))
    assert ot.order_dates("2800 A aka B ( C ) 20.12 - 25.01", t(22, 12))[1].year == 2027

    # laminox yo'li: 7 kun, chiqish = "Laminox 100% tayyor"
    lam = [(t(12, 10, 14), "LAMINOX FAYL TASHALDI 24"), (t(18, 10), "Laminox 100% tayyor")]
    text3, _, fin3 = ot.render(card, lam, [korpus], t(20, 10))
    assert "SEHDAN CHIQDI 19.10" in text3 and "♦️real    18.10" in text3 and fin3, text3
    # eman yo'li — laminox bilan bir xil: 7 kun, chiqish = "eman 100% tayyor"
    eman = [(t(12, 10, 14), "Eman yoki muborak fayl tashaldi"), (t(18, 10), "eman 100% tayyor")]
    text4, _, fin4 = ot.render(card, eman, [korpus], t(20, 10))
    assert "SEHDAN CHIQDI 19.10" in text4 and "♦️real    18.10" in text4 and fin4, text4
    # boshlang'ich "zakaz tushti stopda" kutishi stop emas
    intake = [(t(28, 9), "zakaz tushti stopda"), (t(1, 10), "KANTROLNIY AVAZ AKA")]
    assert "STOPDA TURGAN: \n" in ot.render(card, intake, [], t(2, 10))[0]


def _view():
    """Rasm ma'lumoti: korpus + FASAD bitta zakaz; zakaz OXIRGI kartasi chiqqanda tugaydi."""
    from services import order_card_image

    korpus = {"id": cid(t(20, 9)), "name": "2610 Adxam aka Chig'atoy shkaf ( Husniddin ) 28.09 - 30.10", "labels": []}
    fasad = {"id": cid(t(28, 9)), "name": "FASAD 2610 Adxam aka Chig'atoy shkaf ( Husniddin ) 28.09 - 30.10", "labels": []}
    k_ev = [(t(29, 9), "KANTROLNIY AVAZ AKA"), (t(5, 10), "Abdulloh kroy chizish 24"), (t(6, 10), "GIPLAB Abdulloh 24"),
            (t(12, 10, 11), "taminot srochniymas"), (t(12, 10, 12), "LAMINOX FAYL TASHALDI 24"),
            (t(16, 10), "Laminox 100% tayyor")]
    f_ev = [(t(12, 10, 9), "Fayl yeg'ish  va zapchast 24"), (t(12, 10, 11), "taminot srochniymas"),
            (t(12, 10, 14), "Shpon va shkurka sehta yasalvotti 15 sutka"),
            (t(2, 11), "Shkurkadan chiqqan zakazla (stopda rang tanlanmagan)"), (t(4, 11), "kraska seh 72 soat")]
    abdulloh = [(t(5, 10, 9) + timedelta(minutes=55), "Muruvatullayev Abdulloh")]  # ko'chirishdan 5 daqiqa oldin
    readded = [(t(12, 10, 14), "Muruvatullayev Abdulloh")]  # FASAD nusxasi uni sehda qayta qo'shadi — seh ishchisi emas
    staff = ["Muruvatullayev Abdulloh", "Jasurbek Qosimov"]

    def view(f_events, now, staff=staff):
        parts = [ot.analyze(korpus, k_ev, [f_events], now, abdulloh),
                 ot.analyze(fasad, f_events, [k_ev], now, readded)]
        return ot.order_view(parts, now, staff)

    model, sig, finished = view(f_ev, t(5, 11))
    assert not finished                                          # korpus 16.10 da chiqdi, FASAD hali sehda
    assert model["title"] == "2610 Adxam aka Chig'atoy shkaf  (+FASAD)", model["title"]
    assert model["banner"][0] == "KECHIKMOQDA" and model["banner"][3] == "6 kun o'tdi" and model["banner"][4] == "red"
    assert model["banner"][1] == "Hozir (04.11 dan): kraska seh", model["banner"][1]
    rows = {r[0]: r for r in model["rows"]}
    assert rows["Kroy"][2:] == ("05.10 – 06.10", "Muruvatullayev Abdulloh", ("+3 kun", "red")), rows["Kroy"]
    assert rows["GIPLAB"][2:] == ("06.10 – 12.10", "Muruvatullayev Abdulloh", ("+5 kun", "red"))  # list nomidan
    assert rows["Seh"][3] is None, rows["Seh"]
    # ikki xodim bir xil ismli — list nomidagi so'z o'zi
    two = view(f_ev, t(5, 11), staff + ["Karimov Abdulloh"])[0]["rows"][1][3]
    assert two == "Abdulloh", two
    # o'tgan bosqich kechikkani banner'ni qizil qilmaydi — hozirgi bosqich rejada bo'lsa VAQTIDA
    early = view(f_ev[:3], t(20, 10))[0]
    assert early["banner"][0] == "VAQTIDA" and early["banner"][3] == "10 kun bor", early["banner"]
    # seh rejasi: GIPLAB real tugashi 12.10 + 15 kun (shpon — uzunrog'i) + 2 kun stop
    assert rows["Seh"][1:3] == ("12.10 – 29.10", "12.10 – davom etmoqda") and rows["Seh"][4] == ("+7 kun", "red")
    assert rows["Topshirish"][2:] == ("—", None, ("+6 kun", "red"))
    assert [s[1] for s in model["steps"]] == ["done", "done", "run", "todo", "todo"], model["steps"]
    assert model["stop"] == "STOPDA TURGAN: jami 2 kun 0 soat" and model["footer"] == ot.PENALTY_LINE
    assert model["subtitle"] == "Sotuvchi: Husniddin   ·   Zakaz: 28.09   ·   Bugun: 05.11.2026   ·   38-kun"
    assert view(f_ev, t(6, 11))[1] == sig                       # kun o'tgani imzoni o'zgartirmaydi
    assert order_card_image.draw(model)[1:4] == b"PNG"

    # stopda turgan zakaz
    stopped = view(f_ev[:4], t(3, 11))[0]
    assert stopped["steps"][2][1] == "stop" and "hozir stopda: Shkurkadan chiqqan" in stopped["stop"]

    # FASAD ham skladga chiqdi — zakaz tugadi, kechikkani zakazning oxirgi kartasidan
    model2, sig2, finished2 = view(f_ev + [(t(6, 11), "Malyarka sklad Qurish va O'rash 24 soat")], t(7, 11))
    assert finished2 and sig2 != sig
    assert model2["banner"][0] == "TOPSHIRILDI — KECHIKDI" and model2["banner"][3] == "7 kun kech", model2["banner"]
    assert dict((r[0], r) for r in model2["rows"])["Seh"][2] == "12.10 – 06.11"
    assert [s[1] for s in model2["steps"]] == ["done"] * 5 and model2["footer"] == ot.FINAL_LINE
    assert model2["stop"] == "STOPDA TURGAN: jami 2 kun 0 soat"  # oxirgi xabarda ham jami stop qoladi
    assert order_card_image.draw(model2)[1:4] == b"PNG"


def _job():
    """Job: yangi zakazga topic ochadi, shablon yuboradi, o'zgarmasa qayta yubormaydi,
    tugasa topicni yopadi; kartalar ochilayotganda (SETTLE) kutadi."""
    import asyncio
    from types import SimpleNamespace
    from jobs import order_topics_job as job
    from utils.enums import Role

    now = datetime.now(timezone.utc)
    rows, calls = [], []
    card = {"id": cid(now - timedelta(minutes=10)), "name": "2700 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 03.12",
            "labels": [], "closed": False, "idList": "L1"}
    history_calls, photos, dms = [], [], []
    trello_down, down_calls = False, []
    moves = [{"date": (now - timedelta(minutes=9)).isoformat(), "data": {"list": {"name": "KANTROLNIY AVAZ AKA"}}}]

    class Trello:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def _request(self, method, path, params=None):
            if trello_down:
                down_calls.append(path)
                raise RuntimeError("Trello javob bermadi")
            if path.endswith("/cards/all"):
                return list(board)
            if path.endswith("/lists"):
                return [{"id": "L1", "name": "KANTROLNIY AVAZ AKA"}, {"id": "L2", "name": "Malyarka sklad Qurish va O'rash"},
                        {"id": "L3", "name": "13 DEKABR"}]
            history_calls.append(path)
            return list(reversed(moves))

    class Bot:
        async def create_forum_topic(self, chat_id, name):
            calls.append(("topic", name))
            return SimpleNamespace(message_thread_id=500)

        async def send_message(self, chat_id, text, message_thread_id=None):
            if message_thread_id is None:  # guruh emas — nazoratchiga shaxsiy xabar
                dms.append((chat_id, text))
                return
            calls.append(("send", message_thread_id))
            photos.append(None)  # matn — rasm chizilmagan (zaxira)

        async def send_photo(self, chat_id, photo, caption=None, message_thread_id=None):
            calls.append(("send", message_thread_id))
            photos.append(caption)

        async def close_forum_topic(self, chat_id, thread_id):
            calls.append(("close", thread_id))

        async def edit_forum_topic(self, chat_id, thread_id, name):
            calls.append(("rename", name))
            if fail_rename:
                raise RuntimeError("rename rad etildi")

        async def reopen_forum_topic(self, chat_id, thread_id):
            calls.append(("reopen", thread_id))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def commit(self):
            pass

    class Repo:
        def __init__(self, _s):
            pass

        async def list_all(self):
            return list(rows)

        async def create(self, **kw):
            rows.append(SimpleNamespace(**{"id": len(rows) + 1, "signature": None, "finished_at": None,
                                           "house_key": None, "topic_name": None, **kw}))

        async def get_by_id(self, id_):
            return rows[id_ - 1]

        async def update(self, obj, **kw):
            for k, v in kw.items():
                setattr(obj, k, v)

    async def board_id(_trello):
        return "B"

    async def staff():
        return {"m-a": ("Abdulloh", Role.WORKER)}

    async def observers():
        return [999]

    board = [card]

    fail_rename = False

    saved = (job.async_session, job.OrderTopicRepository, job.nazorat_trello_watch_job._resolve_board_id,
             job.settings.order_group_chat_id, job.settings.order_topics_since, job._staff, job._observers,
             job.DAILY_RETRY_SECONDS)
    job.async_session, job.OrderTopicRepository, job._staff, job._observers = Session, Repo, staff, observers
    job.DAILY_RETRY_SECONDS = 0
    job.nazorat_trello_watch_job._resolve_board_id = board_id
    job.settings.order_group_chat_id, job.settings.order_topics_since = -100, now - timedelta(days=1)
    try:
        run = lambda: asyncio.run(job.run(Bot(), Trello))
        assert run() == 1 and calls == [("topic", card["name"]), ("send", 500)], calls
        calls.clear()
        history_calls.clear()
        assert run() == 0 and calls == [] and history_calls == []  # kun davomida — xabar ham, Trello tarixi ham yo'q
        assert asyncio.run(job.run_daily(Bot(), Trello)) == 1 and calls == [("send", 500)], calls  # ertalab 08:00
        calls.clear()
        # birinchi xabar hali ketmagan + nom o'zgartirish rad etildi: yuborilgani saqlanadi,
        # keyingi yurishda QAYTA yuborilmaydi (oldin har 5 daqiqada qayta ketardi)
        fail_rename = True
        rows[0].signature = None
        card["name"] = "2700 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 07.12"
        assert run() == 1 and calls == [("send", 500), ("rename", card["name"])], calls
        calls.clear()
        assert run() == 0 and calls == [("rename", card["name"])], calls
        fail_rename = False
        calls.clear()
        moves.append({"date": now.isoformat(), "data": {"listAfter": {"name": "Malyarka sklad Qurish va O'rash"}}})
        card["idList"] = "L2"
        card["name"] = "2700 Ali aka Chilonzor kuxnya ( Jasur ) 03.11 - 10.12"
        assert run() == 1 and calls == [("send", 500), ("rename", card["name"]), ("close", 500)], calls
        calls.clear()
        assert run() == 0 and calls == []                       # tugagan — boshqa yuborilmaydi
        # tugagan zakazga keyin yangi karta (ostatka) — o'sha topic qayta ochiladi
        old_id = card["id"]
        card["id"] = cid(now - timedelta(minutes=5), 7)
        card["name"] = "2700 Ali aka Chilonzor OSTATKA ( Jasur ) 03.11 - 10.12"
        card["idList"] = "L1"
        moves[:] = moves[:1]
        assert run() == 1 and calls == [("reopen", 500), ("send", 500)], calls
        calls.clear()
        rows[:] = [r for r in rows if r.card_id == old_id]
        # yangi karta hozirgina ochilgan (polniy uy kelayotgan bo'lishi mumkin) — kutiladi
        rows.clear()
        card["id"] = cid(now - timedelta(minutes=1))
        card["name"] = "2701 Vali aka Yunusobod shkaf ( Jasur ) 03.11 - 10.12"
        assert run() == 0 and calls == [] and rows == []
        assert photos and None not in photos, photos  # hammasi rasm, matn zaxirasi ishlatilmagan

        # korpus + keyin GIPLAB'da nusxalangan FASAD — bitta zakaz, bitta rasm
        rows.clear()
        korpus = {"id": cid(now - timedelta(minutes=10), 20), "name": "2702 Gul opa Sergili shkaf ( Jasur ) 03.11 - 10.12",
                  "labels": [], "closed": False, "idList": "L1"}
        board[:] = [korpus]
        assert run() == 1 and calls == [("topic", korpus["name"]), ("send", 500)], calls
        calls.clear()
        fasad = dict(korpus, id=cid(now - timedelta(minutes=5), 21), name="FASAD " + korpus["name"])
        board.append(fasad)
        assert run() == 0 and calls == [], calls                # qo'shilgan FASAD kun davomida alohida xabar chiqarmaydi
        assert len(rows) == 2 and rows[1].thread_id == 500 and rows[1].signature is not None
        history_calls.clear()
        assert run() == 0 and history_calls == []               # ... va keyin har 5 daqiqada tarix so'ramaydi
        assert asyncio.run(job.run_daily(Bot(), Trello)) == 1 and calls == [("send", 500)], calls  # ertalab: 2 karta — 1 rasm
        calls.clear()
        moves.append({"date": now.isoformat(), "data": {"listAfter": {"name": "Malyarka sklad Qurish va O'rash"}}})
        korpus["idList"] = "L2"
        assert run() == 0 and calls == []                       # korpus skladda, FASAD hali yo'q — zakaz tugamagan
        fasad["idList"] = "L2"
        assert run() == 1 and calls == [("send", 500), ("close", 500)], calls
        assert all(r.finished_at for r in rows)
        assert dms == []                                        # kamchilik yo'q — nazoratchiga xabar ham yo'q

        # nazoratchiga: formati buzuq karta (topic ochilmaydi), botda yo'q Trello odami; sana listidagi nusxa — zakaz emas
        rows.clear()
        calls.clear()
        good = dict(korpus, id=cid(now - timedelta(minutes=10), 30), name="2703 Ali aka Olmazor shkaf ( Jasur ) 03.11 - 10.12",
                    idList="L1")
        broken = dict(good, id=cid(now - timedelta(minutes=10), 31), name="2704 Vali aka Sergili shkaf 03.11 - 10.12")
        copy = dict(good, id=cid(now - timedelta(minutes=10), 32), name="2705 Gani aka Chilonzor shkaf ( Jasur ) 03.11 - 10.12",
                    idList="L3")
        board[:] = [good, broken, copy]
        moves[:] = moves[:1] + [{"type": "addMemberToCard", "date": now.isoformat(), "data": {"idMember": "m-x"},
                                 "member": {"id": "m-x", "fullName": "Jama Jamwid"}}]
        assert asyncio.run(job.run_daily(Bot(), Trello)) == 1 and calls == [("topic", good["name"]), ("send", 500)], calls
        assert [r.card_id for r in rows] == [good["id"]]          # formati buzuq va sana listidagi — topicsiz
        assert len(dms) == 1 and dms[0][0] == 999, dms
        text = dms[0][1]
        assert "topic OCHILMADI" in text and broken["name"] in text, text
        assert "sana listiga nusxalangan" in text and copy["name"] in text, text
        assert "Jama Jamwid — zakaz 2703" in text, text
        dms.clear()
        calls.clear()

        # 08:00 da Trello javob bermadi — 6 marta urinadi, keyin nazoratchiga "hisobot ketmadi"
        trello_down = True
        assert asyncio.run(job.run_daily(Bot(), Trello)) == 0 and calls == []
        assert len(dms) == 1 and "UMUMAN ketmadi" in dms[0][1], dms
        assert len(down_calls) == job.DAILY_ATTEMPTS == 6, down_calls  # 30 daqiqa davomida qayta urindi
    finally:
        (job.async_session, job.OrderTopicRepository, job.nazorat_trello_watch_job._resolve_board_id,
         job.settings.order_group_chat_id, job.settings.order_topics_since, job._staff, job._observers,
         job.DAILY_RETRY_SECONDS) = saved


if __name__ == "__main__":
    _kinds()
    _new_orders()
    _issues()
    _plan_topics()
    _render()
    _view()
    _job()
    print("test_order_topics: OK")
