"""`miniapp/public/js/i18n.js` — uz va ru bloklarida bir xil kalitlar borligi.

Nega kerak: `t()` topilmagan kalit uchun kalitning O'ZINI qaytaradi
(`I18N[lang][key] ?? key`). Ya'ni kalit `uz`ga qo'shilib `ru`ga qo'shilmasa,
rus tilidagi foydalanuvchi ekranda "supervisorOrderHint" degan xom matnni
ko'radi — xato ham, log ham yo'q, jimgina buziladi. Ilgari bu faqat qo'lda
"ikkala blokni solishtir" deb hujjatlashtirilgan edi.

Boshqa testlar kabi: pytest yo'q, baza yo'q, tarmoq yo'q.
    .venv/Scripts/python tests/test_i18n_parity.py
"""

import re
import sys
from pathlib import Path

I18N_PATH = Path(__file__).resolve().parent.parent / "miniapp" / "public" / "js" / "i18n.js"

# Blok boshi: "  uz: {" / "  ru: {" — faylda faqat shu ikkitasi shu darajada.
_BLOCK_RE = re.compile(r"^  (uz|ru): \{$")
# Bitta qatorda bir nechta kalit bo'lishi mumkin
# (`tab_orders: "...", tab_stages: "..."`), shu sabab qator ichidan HAMMASI
# qidiriladi. Matn qiymatlari OLDIN olib tashlanadi — aks holda tarjima
# matnining o'zidagi ikki nuqta ("Muddat: ...") soxta kalit bo'lib chiqadi.
_KEY_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:")
_STRING_RE = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`")


def parse_blocks(text: str) -> dict[str, list[str]]:
    """i18n.js'dagi uz/ru bloklaridan kalit ro'yxatini oladi."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        header = _BLOCK_RE.match(raw)
        if header:
            current = header.group(1)
            blocks[current] = []
            continue
        if current is None:
            continue
        if raw == "  },":  # blok tugadi
            current = None
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        # Faqat kalit darajasidagi qatorlar (4 bo'sh joy bilan boshlanadi).
        if not raw.startswith("    "):
            continue
        blocks[current].extend(_KEY_RE.findall(_STRING_RE.sub('""', raw)))
    return blocks


def main() -> None:
    text = I18N_PATH.read_text(encoding="utf-8")
    blocks = parse_blocks(text)

    assert set(blocks) == {"uz", "ru"}, f"uz/ru bloklari topilmadi: {sorted(blocks)}"

    uz, ru = blocks["uz"], blocks["ru"]
    assert len(uz) > 100, f"uz bloki juda kichik ({len(uz)}) — parser buzilgan bo'lishi mumkin"

    for lang, keys in (("uz", uz), ("ru", ru)):
        duplicates = {k for k in keys if keys.count(k) > 1}
        assert not duplicates, f"{lang} blokida takrorlangan kalit: {sorted(duplicates)}"

    uz_set, ru_set = set(uz), set(ru)
    missing_ru = sorted(uz_set - ru_set)
    missing_uz = sorted(ru_set - uz_set)

    assert not missing_ru, f"ru blokida yo'q ({len(missing_ru)}): {missing_ru}"
    assert not missing_uz, f"uz blokida yo'q ({len(missing_uz)}): {missing_uz}"

    # Nazoratchi ekranlari kalitlari haqiqatan qo'shilganini pinlaydi — yuqoridagi
    # tenglik tekshiruvi ikkala blokdan ham o'chirilsa jim o'tib ketardi.
    for key in ("tab_control", "controlBoardTitle", "lateNow", "stoppedNow",
                "needsAttention", "teamTitle", "worstFirstHint"):
        assert key in uz_set, f"nazoratchi kaliti yo'q: {key}"

    # `app.js`da chaqirilgan HAR BIR matnli kalit lug'atda bormi. Kalit
    # yo'qligi ham xato bermaydi — ekranda kalitning o'zi chiqadi.
    # Hisoblanadigan kalitlar (`t(SOME_MAP[x])`, `t(cond ? "a" : "b")`) bu
    # regexga tushmaydi — ular baribir ikkala tarmog'i bilan literal bo'lib
    # yoziladi va alohida topiladi.
    app_js = (I18N_PATH.parent / "app.js").read_text(encoding="utf-8")
    # Yopuvchi qo'shtirnoqdan keyin `)` yoki `,` bo'lishi shart — aks holda
    # `t("period_" + value)` kabi qo'shib yasaladigan kalitlarning PREFIKSI
    # (`period_`) mustaqil kalit deb topilardi.
    used = set(re.findall(r"\bt\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\"\s*[),]", app_js))
    assert len(used) > 50, f"app.js dan kalitlar topilmadi ({len(used)}) — regex buzilgan"
    unknown = sorted(used - uz_set)
    assert not unknown, f"app.js lug'atda yo'q kalitni chaqiradi: {unknown}"

    print(f"OK — {len(uz_set)} kalit, uz va ru to'liq mos; app.js dan {len(used)} kalit tekshirildi")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
