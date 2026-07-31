"""Ikki modul ("mebel"/Fasad seh va "fasad_sex"/Nazorat Trello) ma'lumoti
BIR-BIRIGA ARALASHMASLIGINI tekshiradi (`miniapp/util.py`).

Ular bitta bazani baham ko'radi, lekin alohida korxona: Nazorat Trello'da
Fasad seh xodimi/bo'limi/vazifasi ko'rinmasligi kerak va aksincha.

Bazaga ulanmaydi — `DepartmentRepository` soxta obyekt bilan almashtiriladi,
shuning uchun oddiy `python tests/test_module_isolation.py` bilan ishlaydi
(loyihada pytest yo'q).
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import miniapp.util as util  # noqa: E402

DEPARTMENTS = [
    SimpleNamespace(id=1, module="mebel"),
    SimpleNamespace(id=2, module="mebel"),
    SimpleNamespace(id=10, module="fasad_sex"),
    SimpleNamespace(id=11, module="fasad_sex"),
]


class _FakeDepartmentRepo:
    def __init__(self, _session):
        pass

    async def list_all(self):
        return DEPARTMENTS


def _request(module):
    """Faqat `headers` kerak — aiohttp Request'ning qolgani ishlatilmaydi."""
    return SimpleNamespace(headers={"X-Module": module} if module else {})


async def _scope(module):
    original = util.DepartmentRepository
    util.DepartmentRepository = _FakeDepartmentRepo
    try:
        return await util.module_scope(_request(module), None)
    finally:
        util.DepartmentRepository = original


async def main():
    fasad = await _scope("fasad_sex")
    mebel = await _scope("mebel")
    none_scope = await _scope(None)

    # 1. Har modul faqat O'Z bo'limlarini ko'radi.
    assert fasad == {10, 11}, fasad
    assert mebel == {1, 2}, mebel

    # 2. Sarlavha yo'q (eski/tashqi chaqiruvchi) -> filtr umuman qo'llanmaydi.
    assert none_scope is None
    assert util.in_module(none_scope, 1) and util.in_module(none_scope, 10)

    # 3. Nazorat Trello'da Fasad seh bo'limi/xodimi KO'RINMAYDI (asosiy shikoyat).
    assert not util.in_module(fasad, 1)
    assert not util.in_module(fasad, 2)
    assert util.in_module(fasad, 10)

    # 4. Va teskarisi — Fasad seh ham Nazorat Trello ma'lumotini olmaydi
    #    (mebel moduli "muzlatilgan": bu tekshiruv uni himoya qiladi).
    assert not util.in_module(mebel, 10)
    assert util.in_module(mebel, 1)

    # 5. Bo'limi YO'Q xodim (bo'lim biriktirilmagan admin/nazoratchi) hech
    #    qaysi modulga tegishli emas -> IKKALASIDA ham ko'rinadi.
    assert util.in_module(fasad, None)
    assert util.in_module(mebel, None)

    # 6. Noma'lum modul nomi -> bo'sh doira, hech qanday bo'lim o'tmaydi
    #    (xato yozilgan sarlavha "hammasini ko'rsat"ga aylanib ketmasin).
    unknown = await _scope("boshqa")
    assert unknown == set()
    assert not util.in_module(unknown, 1) and not util.in_module(unknown, 10)
    assert util.in_module(unknown, None)

    print("OK: test_module_isolation")


asyncio.run(main())
