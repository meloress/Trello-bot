# Qolgan ishlar rejasi (2026-07-17 chuqur TZ auditidan keyin)

Bu papka endi **faqat tugallanmagan ishlarni** kuzatadi. Avvalgi 6 bosqichlik
tarixiy hujjatlar (01-06, har biri "Bajarilgan" deb yopilgan) bu yerdan olib
tashlandi — ular endi kerak emas, chunki:

- To'liq qaror tarixi (nima nega shunday qilingan, foydalanuvchi bilan qanday
  kelishilgan) **git tarixida** saqlanadi (`git log --oneline`, eski
  commitlar: "Phase 2: ...", "Phases 3-5: ...").
- Joriy sxema va band-band izohlar **`shared/db-schema.md`**da yuritiladi —
  har bir jadval/ustun TZ band raqami bilan izohlangan, doim yangilanadi.
- Arxitektura va konvensiyalar **`CLAUDE.md`**da.

Eski hujjatlar kerak bo'lsa: `git log -- .claude/plans/` orqali topiladi.

## Nima uchun bu ro'yxat paydo bo'ldi

2026-07-17'da `TZ_content.txt` (443 qatorli to'liq TZ matni) boshidan oxirigача
qayta o'qilib, HAR BIR band amaldagi kod bilan (servislar, handlerlar,
migratsiyalar) solishtirildi. TZ §1-13, 16-17 (ishlab chiqarish yadrosi)
YUQORI ANIQLIKDA amalga oshirilgan holda topildi — lekin audit 5 ta ANIQ
bo'shliqni (TZning qat'iy talabi, ochiq savol emas) va Phase 6'ning hali
bajarilmagan qismini aniqladi. Quyidagi hujjatlar shularning har biri uchun.

## Holat jadvali

| # | Hujjat | TZ bandi | Mazmuni | Holat |
|---|---|---|---|---|
| 1 | [01-stop-trello-izoh.md](01-stop-trello-izoh.md) | 7.5 | "Stop" bosilganda Trello kartasiga izoh yozish | ANIQLANGAN BO'SHLIQ — rejalashtirilgan |
| 2 | [02-label-holatlari.md](02-label-holatlari.md) | 6.3 | Label avtomatikasi 3 holatdan 5 holatga (Stop rangi + Bugun/Ogohlantirish ajratish) | ANIQLANGAN BO'SHLIQ — rejalashtirilgan |
| 3 | [03-yonalish-statistikasi.md](03-yonalish-statistikasi.md) | 10.1 | Bo'lim (yo'nalish) bo'yicha statistika kesimi | ANIQLANGAN BO'SHLIQ — rejalashtirilgan |
| 4 | [04-web-xodim-qoshish.md](04-web-xodim-qoshish.md) | 4.2 | Web panel orqali xodim qo'shish | QARORGA MUHTOJ — ikkita variant taqdim etilgan |
| 5 | [05-ochiq-vazifalar-royxati.md](05-ochiq-vazifalar-royxati.md) | 9 | MISC vazifalarning hammaga ochiq ro'yxati | ANIQLANGAN BO'SHLIQ — rejalashtirilgan |
| 6 | [06-production-launch.md](06-production-launch.md) | 17 (6-bosqich, A-qism) | E2E smoke test ishga tushirish + Railway'ga chiqarish | TAYYOR, ISHGA TUSHIRISH QOLDI |
| 7 | [07-tz-ochiq-savollar.md](07-tz-ochiq-savollar.md) | 19 | TZning o'z ochiq savollari — konsolidatsiyalangan holat | KUZATUV RO'YXATI |
| 8 | [08-saas-tayyorgarlik.md](08-saas-tayyorgarlik.md) | 15 (6-bosqich, B/C/D-qism) | Ping billing / multi-tenant / video darslar | BLOKLANGAN (Ping shartnomasi kutilmoqda) |

## Ishlash tartibi

1-5 — mustaqil, bir-biriga bog'liq emas, istalgan tartibda olinishi mumkin
(4-raqamli hujjat qaror talab qiladi, boshqalarga to'sqinlik qilmaydi). 6 —
1-5 tugagach yoki alohida-alohida ham bajarilishi mumkin (bir-biriga
bog'liq emas, faqat "hammasi tugagach yakuniy E2E test" degan tavsiya bor).
7 — kod emas, kuzatuv. 8 — hozircha tegilmaydi (tashqi blokerga bog'liq).

Har bir hujjat tugagach: shu jadvaldagi holat yangilanadi, `shared/db-schema.md`
(agar sxema o'zgargan bo'lsa) yangilanadi, va **hujjatning o'zi bu papkadan
olib tashlanadi** (git tarixida saqlanib qoladi) — README'dagi qator ham olib
tashlanadi. Bu papka doim faqat "hali qolgan" ishlarni aks ettiradi.
