"""Ikki ishlab chiqarish moduli — VA ULARNING NOMLARIDAGI TUZOQ.

╔══════════════════════════════════════════════════════════════════════════╗
║  DIQQAT: bazadagi qiymat foydalanuvchi ko'radigan nom BILAN MOS EMAS.    ║
║                                                                          ║
║    departments.module = "mebel"      ->  ekranda "Fasad seh"             ║
║    departments.module = "fasad_sex"  ->  ekranda "Nazorat Trello"        ║
║                                                                          ║
║  Ya'ni `"fasad_sex"` degan matn "Fasad seh"ni ANGLATMAYDI — u aynan      ║
║  BOSHQA modul, "Nazorat Trello". Bu chalkashlik jamoani bir necha bor    ║
║  adashtirgan (suhbat o'rtasida ham).                                     ║
╚══════════════════════════════════════════════════════════════════════════╝

Shu sabab kodda bu matnlar TO'G'RIDAN-TO'G'RI yozilmaydi — quyidagi
konstantalar ishlatiladi:

    from utils.modules import MEBEL, NAZORAT_TRELLO

    if department.module == MEBEL:          # "Fasad seh" — MUZLATILGAN
    if department.module == NAZORAT_TRELLO: # "Nazorat Trello" — faol ish

Nega qiymatlarning O'ZI o'zgartirilmagan: ular ishlab chiqarish bazasida
yozilgan (`departments.module`), Mini App'ning `X-Module` sarlavhasida
uzatiladi va MUZLATILGAN mebel modulining o'nlab guard'ida ishlatiladi.
Qiymatni almashtirish bitta o'tkazib yuborilgan guard evaziga jonli
KPI/xabarnoma oqimini jimgina buzishi mumkin edi — konstanta esa xuddi
shu foydani (kod o'qilganda adashmaslik) nol xavf bilan beradi.

UCHINCHI ma'no, chalkashtirmang: `MiscCategory.FASAD_SEX` ("fasad_sex")
— bu MODUL EMAS, maxsus vazifaning turi (TZ 6.2: "ofis / fasad sex /
ustanovkachi + svarshik"). U `tasks.misc_category` ustunida yashaydi va
`departments.module` bilan hech qanday aloqasi yo'q.

Testlarda konstanta emas, XOM matn ("mebel"/"fasad_sex") ataylab
qoldirilgan: ular bazada haqiqatda nima yozilishini pinlaydi, ya'ni
kimdir konstanta qiymatini o'zgartirsa test yiqiladi.
"""

# Mebel liniyasi — Mini App'da "Fasad seh". 2026-07-31 dan beri MUZLATILGAN:
# bu modul xatti-harakatini o'zgartirish taqiqlanadi (CLAUDE.md).
MEBEL = "mebel"

# Nazorat Trello — yagona faol ish olib borilayotgan modul.
# E'TIBOR BERING: qiymati "fasad_sex", lekin bu "Fasad seh" EMAS.
NAZORAT_TRELLO = "fasad_sex"

ALL_MODULES = (MEBEL, NAZORAT_TRELLO)

# Foydalanuvchiga ko'rinadigan nomlar. Kodda modul haqida matn yozilsa
# (log, xabar, xato matni) shu yerdan olinadi — xom qiymat ("fasad_sex")
# hech qachon foydalanuvchiga ko'rsatilmasin.
MODULE_LABELS = {
    MEBEL: "Fasad seh",
    NAZORAT_TRELLO: "Nazorat Trello",
}


def label(module: str | None) -> str:
    """Modul qiymatini odam o'qiydigan nomga aylantiradi."""
    return MODULE_LABELS.get(module, module or "—")


def demo() -> None:
    """Tuzoqning o'zini pinlaydigan kichik tekshiruv."""
    assert label(NAZORAT_TRELLO) == "Nazorat Trello", "qiymat 'fasad_sex' — nomi 'Fasad seh' EMAS"
    assert label(MEBEL) == "Fasad seh"
    assert NAZORAT_TRELLO != "nazorat_trello", "baza qiymati ataylab eski nomda qolgan"
    assert set(ALL_MODULES) == set(MODULE_LABELS), "har modulning ko'rinadigan nomi bo'lishi shart"
    print("utils/modules: OK")


if __name__ == "__main__":
    demo()
