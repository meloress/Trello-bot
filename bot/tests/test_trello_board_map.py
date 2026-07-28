"""`services/trello_board_map.py` tasniflashini haqiqiy "Fasad seh" doskasidagi
25 ta ro'yxat nomi ustida tekshiradi (Trello'ga ulanmaydi — nomlar nusxasi).

    .venv/Scripts/python tests/test_trello_board_map.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.trello_board_map import build_board_map, parse_hours  # noqa: E402
from utils.enums import TrelloListKind  # noqa: E402

SHPON = SimpleNamespace(id=38, name="Shpon", trello_list_keywords="shpon")
SHKURKA = SimpleNamespace(id=39, name="Shkurka", trello_list_keywords="shkurka")
KRASKA = SimpleNamespace(id=40, name="Kraska", trello_list_keywords="kraska,malyarka")
DEPARTMENTS = [SHPON, SHKURKA, KRASKA]

# (nom, kutilgan_kind, kutilgan_bo'lim, kutilgan_soat)
W, Q = TrelloListKind.WORK, TrelloListKind.QUEUE
CASES = [
    ("Fasad sehga hali kroy tushmadi",                     Q, None,    None),
    ("shpon hali boshlanmadik",                            Q, None,    None),
    ("Zoxid shpon brigada",                                W, "Shpon", None),
    ("Abror shpon brigada",                                W, "Shpon", None),
    ("Rustam shpon seh",                                   W, "Shpon", None),
    ("mirjalol shpon seh",                                 W, "Shpon", None),
    ("jamshid shpon seh",                                  W, "Shpon", None),
    ("shkurka hali tasdiqlanmadi",                         Q, None,    None),
    ("shkurka Xayot ishlanvotti 72 soat",                  W, "Shkurka", 72),
    ("shkurka Bexruz Asliddin ishlanvotti 72 soat",        W, "Shkurka", 72),
    ("shkurka sanjar (sardor)ishlanvotti 72 soat",         W, "Shkurka", 72),
    ("shkurka Hudayor",                                    W, "Shkurka", None),
    ("shkurka Husan ishlanvotti 72 soat",                  W, "Shkurka", 72),
    ("shkurka zokir ishlanvotti 72 soat",                  W, "Shkurka", 72),
    ("shkurkadan chiqqan rang tanlangan zakazla",          Q, None,    None),
    ("shkurkdan chiqqan  rang tanlanmagan   zakazlar",     Q, None,    None),
    ("kraska bobur 72 soat(elyor)",                        W, "Kraska", 72),
    ("kraska ELYOR 72 soat(elyor)",                        W, "Kraska", 72),
    ("kraska Nurilla 72 soat(elyor)",                      W, "Kraska", 72),
    ("kraska Xikmatilla 72soat",                           W, "Kraska", 72),
    ("Malyarka qurish orash 24 soat oralmagani",           W, "Kraska", 24),
    ("dastavka qilinishi kerak  24 soat",                  Q, None,    None),
    ("dastavka qilingan",                                  Q, None,    None),
    ("ustanovka ishlanvotti",                              Q, None,    None),
    ("100%bitkan atchot topshirilgan va raxbartasdigi ku", Q, None,    None),
]


def main() -> None:
    mapped = build_board_map([{"id": f"L{i}", "name": n} for i, (n, *_) in enumerate(CASES)], DEPARTMENTS)

    failures = []
    for got, (name, want_kind, want_dept, want_hours) in zip(mapped, CASES):
        dept = got["department"].name if got["department"] else None
        if (got["kind"], dept, got["hours"]) != (want_kind, want_dept, want_hours):
            failures.append(
                f"  {name!r}\n     kutilgan: {want_kind.value}/{want_dept}/{want_hours}"
                f"\n     olindi:   {got['kind'].value}/{dept}/{got['hours']}"
            )

    work = [m for m in mapped if m["kind"] == TrelloListKind.WORK]
    per_dept = {}
    for m in work:
        per_dept[m["department"].name] = per_dept.get(m["department"].name, 0) + 1

    if failures:
        print("XATOLAR:\n" + "\n".join(failures))
        raise SystemExit(1)

    # Bosqichlar bo'yicha ish ro'yxatlari soni — haqiqiy doskadagi holat
    assert per_dept == {"Shpon": 5, "Shkurka": 6, "Kraska": 5}, per_dept
    assert len(work) == 16 and len(mapped) - len(work) == 9, (len(work), len(mapped))

    # Yangi brigada ro'yxati qo'shilsa — sozlamasiz o'zi tanilishi kerak
    new = build_board_map([{"id": "X", "name": "Sardor shpon brigada 48 soat"}], DEPARTMENTS)[0]
    assert new["kind"] is TrelloListKind.WORK and new["department"].name == "Shpon" and new["hours"] == 48, new

    # Notanish ro'yxat -> QUEUE (ish ochilmaydi, xavfsiz standart)
    unknown = build_board_map([{"id": "Y", "name": "Yangi qandaydir ro'yxat"}], DEPARTMENTS)[0]
    assert unknown["kind"] is TrelloListKind.QUEUE and unknown["department"] is None

    # Kalit so'zi yo'q bo'lim hech qaysi ro'yxatni egallamaydi
    blank = SimpleNamespace(id=99, name="Sozlanmagan", trello_list_keywords=None)
    assert build_board_map([{"id": "Z", "name": "Zoxid shpon brigada"}], [blank])[0]["kind"] is TrelloListKind.QUEUE

    assert parse_hours("kraska Xikmatilla 72soat") == 72
    assert parse_hours("Zoxid shpon brigada") is None
    assert parse_hours("0 soat") is None

    print(f"test_trello_board_map: {len(CASES)}/{len(CASES)} ro'yxat to'g'ri tasniflandi")
    print(f"  ish ro'yxatlari: {per_dept}  | kutish ro'yxatlari: {len(mapped) - len(work)}")
    print("  yangi ro'yxat avto-tanildi, notanish ro'yxat xavfsiz QUEUE bo'ldi  OK")


if __name__ == "__main__":
    main()
