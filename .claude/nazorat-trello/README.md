# Nazorat Trello (Fasad sex) — hali qilinmagan ishlar

Bu papka `.claude/plans/09-fasad-sex-modul.md`dan FARQLI: o'sha hujjat
BAJARILGAN 10 bosqichning tarixini (review natijalari, commit'lar bilan)
saqlaydi. Bu papka esa faqat **HALI QOLGAN, bajarilishi kerak bo'lgan**
ishlarni jamlaydi — kod tomondan modul to'liq qurilgan va production'da
jonli (`main` branch, Railway'da deploy qilingan), lekin haqiqiy Fasad sex
liniyasi ishlashi uchun quyidagi ishlar hali kerak.

## Holat jadvali

| # | Hujjat | Mazmuni | Muhimlik |
|---|---|---|---|
| 1 | [01-haqiqiy-zanjir-yaratish.md](01-haqiqiy-zanjir-yaratish.md) | ✅ 2026-07-24: asosiy 17-bosqichli zanjir yaratildi (yangi Trello board, DB'da to'liq fork/join). Ochiq qoldi: material turlari (1.3), 2-zavod (1.4), xodim biriktirish (1.5, #3ga bog'liq) | ✅ ASOSIY QISM BAJARILDI |
| 2 | [02-frontend-boshqaruv-tugmalari.md](02-frontend-boshqaruv-tugmalari.md) | ✅ 2026-07-24: bo'lim tahrirlash ekrani, fork-target tanlagich, sotuvchi multi-select qo'shildi (2.1/chain va material-shablon aslida allaqachon bor ekan — hujjat eskirgan edi) | ✅ BAJARILDI |
| 3 | [03-fasad-sex-real-ekranlari.md](03-fasad-sex-real-ekranlari.md) | Fasad sex modulining haqiqiy bosh sahifa/tab ekranlari (hozir placeholder) | BLOKLOVCHI — ishchi/brigadir tayinlashdan OLDIN shart |
| 4 | [04-texnik-qarz-topilmalar.md](04-texnik-qarz-topilmalar.md) | Review'lardan qolgan kichik (Minor) topilmalar — texnik qarz ro'yxati | O'RTA — hozircha xavfsiz, lekin yig'ilib qolmasin |
| 5 | [05-tz-ochiq-savollar.md](05-tz-ochiq-savollar.md) | TZning o'z ochiq savollari (rahbardan javob kutilmoqda) — `09z-fasad-sex-ochiq-savollar.md`ga havola | O'ZGARUVCHAN — javob kelgach kod bo'shashadi |
| 6 | [06-production-tayyorgarlik.md](06-production-tayyorgarlik.md) | Deploy/keshlash/test — jonli tizimni ishonchli qilish uchun qolgan ishlar | O'RTA |

## Qisqa xulosa (2026-07-24 holatiga)

- Kod: **100% tayyor** (+ shu sessiyada Sklad uchun kichik qo'shimcha:
  `activate_pending_stage()`ning mid-chain `starts_stopped` qo'llab-
  quvvatlashi va `overdue_watch_job`ning auto-resume qismi).
- Baza: **100% migratsiya qilingan** (`f3a7c1d9e4b6`gacha, shu jumladan
  yangi `stopped_auto_resume_after_hours` ustuni).
- Haqiqiy Fasad sex zanjiri: **✅ asosiy qismi yaratildi** (17 department,
  yangi Trello board). Ochiq qoldi: material turlari shabloni, ikkinchi
  zavod (kerak bo'lsa), xodimlarni bog'lash (#3ga bog'liq).
- Mini App'da "Fasad sex" tugmasini bosganda endi zanjir DB'da mavjud —
  lekin #3 (real ekranlar) hal qilinmaguncha, va xodimlar hali
  biriktirilmagani sabab, worker/brigadir darajasida hamon ishlatib
  bo'lmaydi. #3 shu sabab endi navbatdagi ENG MUHIM ish.
- #2 (frontend boshqaruv) ham shu sessiyada bajarildi: bo'lim
  ro'yxatidagi har bir qator endi bosiladi va to'liq tahrirlash ekranini
  ochadi (nom, Trello list ID, auto-reassign, starts_stopped,
  auto-resume soat, requires_join, factory_name, stop_target_list_id),
  undan ichkariga fork-target multi-select ekrani qo'shildi, va yangi
  buyurtma formasiga sotuvchi(lar) (≤3) checkbox ro'yxati qo'shildi.
  Yon-tuzatish: `update_department` endi `_department_scope_ok` bilan
  himoyalangan (avval SUPERVISOR har qanday bo'limni tahrirlay olardi —
  2026-07-22 auditda topilgan naqsh, shu endpoint o'sha safar
  qochirilgan edi).
