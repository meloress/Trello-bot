# Nazorat Trello (Fasad sex) — hali qilinmagan ishlar

Bu papka **loyihadagi YAGONA faol ish ro'yxati**. `.claude/plans/`
(mebel/"Fasad seh" yo'l xaritasi) 2026-07-31'da o'chirildi — o'sha modul
100% tugagan va muzlatilgan, unga tegilmaydi. Bu papka faqat **HALI
QOLGAN, bajarilishi kerak bo'lgan** ishlarni jamlaydi — kod tomondan modul to'liq qurilgan va production'da
jonli (`main` branch, Railway'da deploy qilingan), lekin haqiqiy Fasad sex
liniyasi ishlashi uchun quyidagi ishlar hali kerak.

Bajarilgan ikkita band (frontend boshqaruv tugmalari, real rol-ekranlari)
to'liq yopilgani uchun bu papkadan o'chirildi — tarixi git logda saqlanadi.

## Holat jadvali

| # | Hujjat | Mazmuni | Muhimlik |
|---|---|---|---|
| 1 | [01-haqiqiy-zanjir-yaratish.md](01-haqiqiy-zanjir-yaratish.md) | Zanjirning o'zi DB'da tayyor. 1.3 ✅ bajarildi, 1.4 qaror qayd etildi (yaratish keyinga qoldirildi), **xodim biriktirish (1.5) davom etmoqda** — demo Trello board tayyor, bo'lim-list moslashtirish va xodim ro'yxatdan o'tishi kutilmoqda | 🔴 ENG MUHIM — modul hali amalda ishlatilmagan |
| 2 | [04-texnik-qarz-topilmalar.md](04-texnik-qarz-topilmalar.md) | **✅ 2026-07-31: HAMMASI YOPILDI.** Join-race (`pg_advisory_xact_lock`), fork-targets validatsiya, factory_name filtri, seller_ids dedup, MISC N+1, `module` bug, va xavfsizlik testi (`test_miniapp_authz.py`, 18 tekshiruv). Qolgani — "qasddan shunday" izohlari | ✅ YOPILDI |
| 3 | [05-tz-ochiq-savollar.md](05-tz-ochiq-savollar.md) | TZning o'z ochiq savollari — **✅ 2026-07-31: HAMMASI YOPILDI** (14/14). Qismi rahbar javobi bilan, qismi haqiqiy board ustidan empirik tekshiruv bilan. Kunlik rasm/video hisobot funksiyasi butunlay o'chirildi | ✅ YOPILDI |
| 4 | [06-production-tayyorgarlik.md](06-production-tayyorgarlik.md) | **✅ 2026-07-31: kod tomondan tugadi.** Cache-Control tuzatildi (+test), 6.3/6.5 mavzudan chiqdi. Qolgan 6.2/6.4 — kod emas, haqiqiy foydalanish sinovi (01 §1.5 ga bog'liq) | ✅ Kod tayyor |

## Tekshirilgan holat (2026-07-31, real kod + real DB)

Quyidagilar taxmin emas — kod va production DB ustidan tekshirilgan:

- **Kod tuzatishlari**: 9/9 tuzatish kodda mavjudligi grep bilan
  tasdiqlandi (factory_name guard, `pg_advisory_xact_lock`, fork-targets
  validatsiya, notify guard, seller_ids dedup, capacity docstring,
  `module` parametri, cache middleware, MISC N+1).
- **Testlar**: 5/5 o'tadi (`test_brigade_membership`, `test_miniapp_authz`,
  `test_miniapp_cache_headers`, `test_penalty_responsible`,
  `test_trello_board_map`). Importlar va JS sintaksisi toza.
- **Ikkita yangi test sabotaj bilan tekshirildi** — ataylab buzilganda
  yiqilishi tasdiqlandi (bo'sh test emas).
- **Material shablonlari (1.3)**: DB'da 6 ta bo'lim, hammasi
  `module='fasad_sex'`, zanjir to'g'ri bog'langan (94→95→96, 97→98→99).
- **17-bosqichli asosiy zanjir**: hammasida `trello_list_id` bor,
  fork/join to'g'ri, asl boardga ulangan (demo repoint qaytarilgan).
- **Test qoldiqlari tozalangan**: `JOIN-RACE-SMOKE` vazifalari 0 ta.
- **1.5 hali ochiq**: `fasad_sex` bo'limlarida **0 faol xodim, 0 vazifa**.

## ⚠️ Yakuniy xulosa: kod tugadi, ish ma'lumotga qoldi

**Bo'lim holati:**

| Bo'lim | Holat |
|---|---|
| `01` Zanjir | 1.3 ✅ · 1.4 ✅ (qaror) · **1.5 ⏳ OCHIQ** |
| `04` Texnik qarz | ✅ Hammasi yopildi (xavfsizlik testi ham yozildi) |
| `05` TZ savollari | ✅ 14/14 yopildi |
| `06` Production | ✅ Kod tugadi (6.2/6.4 sinov — 1.5 ga bog'liq) |

**Qolgan yagona bloklovchi — `01` §1.5, va u kod emas:**

1. 17 ta `fasad_sex` bo'limi qaysi "nazorat trello" listiga mos kelishi
   (rahbar beradi — nomlar bir xil emas, masalan "Montaj (Ustanovka)"
   o'rniga boardda 7 ta alohida brigada listi bor).
2. Kamida bitta real xodim botga `/start` orqali ro'yxatdan o'tib, o'sha
   bo'limlardan biriga tayinlanishi.

Shu ikkitasidan keyingina 6.2 (E2E sinov) va 6.4 (job'lar kuzatuvi)
boshlanadi. Sinov uchun demo board tayyor:
`https://trello.com/b/Y3eXUO8Q/nazorat-trello-demo` (haqiqiy boardning
51 listi, kartasiz).

**Ochiq qolgan texnik kamchilik yo'q.**
