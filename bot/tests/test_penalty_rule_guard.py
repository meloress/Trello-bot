"""TZ 1.3/8.1 — jarima jadvali (`penalty_rules`) tahriri uchun himoya.

Bazaga ulanmaydi: `_global_top_rule_survives()` sof funksiya, qoidalar
`SimpleNamespace` bilan taqlid qilinadi. Oddiy
`python tests/test_penalty_rule_guard.py` bilan ishlaydi.

Nima qo'riqlanadi: GLOBAL jadvalda `max_hours_late IS NULL` (ochiq yuqori
chegara) qatori DOIM qolishi kerak. `find_applicable_rule()` ataylab eng
yaqin bracketga yopishib qolmaydi — mos qator topilmasa `None` qaytaradi,
va job yo'llarida bu faqat ogohlantirish logi. Ya'ni ochiq qator
o'chirilsa, yetarlicha kech tugagan HAR QANDAY vazifa jimgina jarimasiz
o'tib ketadi (xato ham chiqmaydi) — shuning uchun bunday tahrir 409 bilan
rad etilishi kerak.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from miniapp.api.admin import _global_top_rule_survives, _parse_penalty_rule_body  # noqa: E402


def _rule(id_, *, department_id=None, min_h=0, max_h=None):
    return SimpleNamespace(
        id=id_, department_id=department_id, min_hours_late=min_h, max_hours_late=max_h
    )


# Haqiqiy jadval: 4 ta yopiq oraliq + 1 ta ochiq (id=5).
RULES = [
    _rule(1, min_h=0, max_h=24),
    _rule(2, min_h=24, max_h=48),
    _rule(3, min_h=48, max_h=72),
    _rule(4, min_h=72, max_h=96),
    _rule(5, min_h=96, max_h=None),
]


def main() -> None:
    # --- O'chirish ---
    assert not _global_top_rule_survives(RULES, changed_id=5, new_max_hours=None, deleting=True), (
        "yagona ochiq qatorni o'chirishga ruxsat berilmasligi kerak"
    )
    assert _global_top_rule_survives(RULES, changed_id=2, new_max_hours=None, deleting=True), (
        "oddiy yopiq qatorni o'chirish mumkin"
    )

    # --- Tahrirlash ---
    assert not _global_top_rule_survives(RULES, changed_id=5, new_max_hours=200, deleting=False), (
        "yagona ochiq qatorga yuqori chegara qo'yish teshik ochadi"
    )
    assert _global_top_rule_survives(RULES, changed_id=5, new_max_hours=None, deleting=False), (
        "ochiq qatorning boshqa maydonlarini tahrirlash mumkin"
    )
    assert _global_top_rule_survives(RULES, changed_id=1, new_max_hours=12, deleting=False), (
        "boshqa qatorni tahrirlash ochiq qatorga tegmaydi"
    )

    # --- Ikkita ochiq qator bo'lsa bittasini o'chirish mumkin ---
    two_open = RULES + [_rule(6, min_h=500, max_h=None)]
    assert _global_top_rule_survives(two_open, changed_id=5, new_max_hours=None, deleting=True), (
        "ikkinchi ochiq qator qolsa o'chirishga ruxsat"
    )

    # --- Bo'limga xos qatorlar global himoyaga kirmaydi ---
    dept_only = [_rule(7, department_id=3, min_h=0, max_h=None)]
    assert not _global_top_rule_survives(dept_only, changed_id=7, new_max_hours=1, deleting=False), (
        "bo'lim qatori global ochiq qator o'rnini bosa olmaydi"
    )

    # --- Validatsiya ---
    fields, error = _parse_penalty_rule_body(
        {"min_hours_late": 0, "max_hours_late": 24, "score": -1}
    )
    assert error is None and fields["max_hours_late"] == 24 and fields["department_id"] is None

    fields, error = _parse_penalty_rule_body({"min_hours_late": 96, "max_hours_late": "", "score": -12})
    assert error is None and fields["max_hours_late"] is None, "bo'sh max = ochiq chegara"

    for bad, why in (
        ({"min_hours_late": 24, "max_hours_late": 24, "score": -1}, "max <= min"),
        ({"min_hours_late": -1, "max_hours_late": 24, "score": -1}, "manfiy min"),
        ({"min_hours_late": 0, "max_hours_late": 24, "score": 0}, "score 0"),
        ({"max_hours_late": 24, "score": -1}, "min yo'q"),
    ):
        _, error = _parse_penalty_rule_body(bad)
        assert error is not None, f"rad etilishi kerak edi: {why}"

    print("test_penalty_rule_guard: HAMMASI O'TDI")


if __name__ == "__main__":
    main()
