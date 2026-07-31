# 4. Texnik qarz — review'lardan qolgan kichik topilmalar

**2026-07-31 holati: ✅ HAMMASI YOPILDI.** Barcha funksional topilmalar
tuzatildi va xavfsizlik testi yozildi. Qolgan uch qator — "qasddan
shunday" yoki "orqaga qaytarib bo'lmaydi" toifasida (oxirgi jadvalga
qarang).

Har biri **Minor** darajasida baholangan edi (xavfsiz, bloklovchi emas),
lekin yig'ilib ketmasligi uchun ro'yxatga olingan edi.

## Phase 1 — Zavod tegi
- ✅ **TUZATILDI (2026-07-31)**: `?factory_name=` bo'sh satr (`""`) bilan
  chaqirilsa, filtr sifatida qabul qilinardi (`Department.factory_name ==
  ""`), "filtrsiz" deb emas. `bot/miniapp/api/admin.py`, `/stats` route —
  `factory_name = request.query.get("factory_name") or None` guardi
  qo'shildi.

## Phase 3 — Fork/join
- ✅ **TUZATILDI (2026-07-31)**: **Join-fire idempotent emas edi**: 2
  ishchi bir vaqtda oxirgi 2ta filial vazifasini tugatsa, ikkalasi ham
  join bosqichini yaratishi mumkin edi (race condition). Oddiy
  check-then-insert yetarli emasligi haqiqiy `asyncio.gather` sinovida
  tasdiqlandi (ikkalasi ham tekshiruvdan committan oldin o'tib ketdi,
  2 ta join task yaratildi) — shu sabab `pg_advisory_xact_lock(hashtext(card_id))`
  bilan tuzatildi (`task_service.advance_task_stage()`): ikkinchi chaqiruv
  birinchisi commit qilguncha bloklanadi, keyin qayta tekshiruvda
  birinchisi yaratgan join taskni topib, o'shani qaytaradi. Real DB'da
  sinov qilindi ("Fayl yig'ish"→3 filial→"Korpus sexi" zanjiri
  ishlatilib): ikkala parallel chaqiruv bir xil join task id qaytardi
  (dublikat yo'q), keyin test qatorlari (DB + Trello karta) o'chirildi.
- ✅ **TUZATILDI (2026-07-31)**: `POST /departments/{id}/fork-targets`
  input tekshiruvsiz edi: mavjud bo'lmagan `target_department_id` → 500
  xato (400 emas); o'z-o'ziga fork qilish bloklanmagan edi. Endi:
  `target_department_ids`dagi har bir id avval mavjudligi tekshiriladi
  (topilmasa 400), va `department_id`ning o'ziga fork qilish rad etiladi.
- ✅ **TUZATILDI (2026-07-31)**: Filial (branch) vazifasi tugaganda ham
  `notify_client_stage_advanced` xabari ketardi — mijozga "bosqich o'tdi"
  deyilardi, aslida hali boshqa filiallar kutilayotgan yoki buyurtma
  allaqachon terminal bo'lgan holatda ham. `miniapp/api/worker.py`:
  `advance_task_stage()` natijasi `None` bo'lsa (terminal HAM, join
  kutish HAM) endi client'ga xabar yuborilmaydi.

## Phase 5 — Stop kengaytmalari
- ✅ **TUZATILDI (2026-07-31)**: `seller_ids` ichida dublikat ID kelsa,
  `IntegrityError` chiqardi (`ValueError` emas). `task_service.create_task()`:
  `seller_ids = list(dict.fromkeys(seller_ids or []))` bilan dedup qilindi.

## Phase 6 — Sig'im statistikasi
- ✅ **TUZATILDI (2026-07-31)**: `GET /admin/stats/capacity` docstring'i
  noto'g'ri funksiya nomiga ishora qilardi — `penalty_service.month_bounds`
  deb tuzatildi.
- `since` parametri berilib, `until` berilmasa (yoki aksincha), ikkalasi
  ham "joriy oy" default'iga tushadi — tekshirildi, bu qasddan "ikkalasi
  birga yoki hech biri" qoidasi, xato emas. O'zgartirilmadi.

## Phase 8 — Kunlik hisobot — ✅ MAVZUDAN CHIQDI (2026-07-31)

Bu bo'limdagi barcha topilmalar **kunlik rasm/video hisobot
funksiyasiga** tegishli edi. O'sha funksiya rahbar talabiga ko'ra
("umuman kerak emas") 2026-07-31'da koddan **butunlay o'chirildi**
(`services/daily_report_service.py`, `jobs/daily_report_job.py`,
`handlers/common/daily_report.py`, model/repository, admin route va Mini
App ekrani). Ya'ni:

- Duplikat "kim topshirmagan" mantiqi — avval `get_compliance_for_date()`
  bilan birlashtirilgan edi, keyin butun fayl bilan birga o'chdi.
- Migratsiyadagi `server_default='false'` uslub farqi — migratsiya
  fayliga tegilmadi (tarixiy, ishlab turibdi), lekin endi hech qanday
  kod o'sha ustunni o'qimaydi.

Qolgan yagona (funksional bo'lmagan) eslatma: `main.py`dagi router
tartib tuzatishi alohida commit emas, feature commit ichida ketgan —
faqat git tarixi tozaligi masalasi, orqaga qaytarib tuzatib bo'lmaydi.

## Phase 9 — MISC kategoriya
- ✅ **TUZATILDI (2026-07-31)**: Admin MISC ro'yxati (`GET /admin/misctasks`)
  har biriktirish uchun xodim ismini alohida so'rov bilan olardi
  (vazifa × biriktirish = N*M so'rov). Endi xodim ismlari bitta
  `list_all()` bilan lug'atga yuklanadi. Bu ekran mebel'da yashirilgan
  (`screenAdminMiscTasks` faqat `fasad_sex`da ko'rinadi), shuning uchun
  tuzatish mebel'ga tegmaydi.
- ✅ **TUZATILDI (2026-07-31)**: admin route'larning bo'lim-cheklash
  (`_department_scope_ok`) tekshiruvi faqat kod o'qish orqali
  tasdiqlangan edi. Endi `bot/tests/test_miniapp_authz.py` bor —
  **haqiqiy HTTP so'rovlar** bilan, 4 qatlamda, 18 ta tekshiruv:
  1. `_department_scope_ok()` sof funksiya sifatida (8 ta rol/bo'lim
     kombinatsiyasi — nazoratchi boshqa bo'limga kira olmasligi,
     bo'limsiz nazoratchi cheklovsizligi, admin cheklovsizligi).
  2. Nazoratchi boshqa bo'lim resursiga HTTP orqali murojaat qilsa 403;
     imzosiz / buzilgan imzo / **boshqa bot tokeni bilan imzolangan**
     so'rovlar 401.
  3. Ishchi `/admin`, `/brigadier`, `/seller` sub-app'lariga kira
     olmasligi (rol darveshi).
  4. Ro'yxatdan o'tmagan va deaktivlashtirilgan xodim 403.

  Bazasiz/Telegramsiz ishlaydi: `miniapp.auth`ning DB qidiruvi soxta
  obyekt bilan almashtiriladi, so'rovlar localhost'ga boradi. Tanlangan
  endpoint'lar bo'lim tekshiruvidan o'tmasa bazaga umuman tegmaydi,
  shuning uchun rad etish yo'lini bazasiz sinash mumkin.

  **Testning haqiqiyligi isbotlandi** — ikki xil sabotaj bilan
  tekshirildi: (a) `_department_scope_ok` doim `True` qaytaradigan
  qilinganda yiqildi; (b) `role_middleware` o'chirilganda ishchi
  `/admin/stats/capacity`dan **200** oldi (403 o'rniga) va test buni
  ushladi.

## 1.3-band bajarilishida topilgan (2026-07-31)
- ✅ **TUZATILDI (2026-07-31)**: `POST /admin/departments`
  (`miniapp/api/admin.py`) so'rov tanasidan `module`ni o'qimas edi —
  `Department.module`ning `default="mebel"`i har doim ishlar edi.
  Natijada Mini App'ning "Yangi material turi" formasi
  (`screenAddMaterialTemplate`, fasad_sex uchun mo'ljallangan) orqali
  yaratilgan har qanday bo'lim sukut bo'yicha `module="mebel"`ga tushib
  qolardi — foydalanuvchiga hech qanday xato ko'rsatilmasdan, bo'lim
  "yo'qolgandek" ko'rinardi (fasad_sex ro'yxatida chiqmasdi). Laminoks/
  Eman/dub shu sabab bu topilgach to'g'ridan-to'g'ri DB orqali (`module`
  aniq ko'rsatilib) yaratildi. Endi tuzatildi: `create_department()`
  `body.get("module", "mebel")`ni o'qiydi, `screenAddMaterialTemplate`
  `module: nav.module`ni jo'natadi — bundan buyon forma orqali ham
  to'g'ri modulga tushadi.

## Deploy paytida topilgan
- ✅ **TUZATILDI (2026-07-31)**: Mini App static fayllari
  (`bot/miniapp/server.py`) uchun `Cache-Control` headerlari yo'q edi —
  Telegram WebView eski JS/CSS'ni keshda saqlab qolardi, har deploy'dan
  keyin foydalanuvchi Telegram'ni to'liq yopib qayta ochishi kerak
  bo'lardi. `no_cache_middleware` qo'shildi + `tests/test_miniapp_cache_headers.py`
  bilan pinlandi. Batafsil: `06-production-tayyorgarlik.md` 6.1.

## Yakuniy holat (2026-07-31)

Barcha funksional topilmalar yopildi. Qolgani:

| Topilma | Holat |
|---|---|
| `_department_scope_ok` HTTP testi | ✅ Yozildi (`tests/test_miniapp_authz.py`, 18 tekshiruv) |
| `since`/`until` juftlik qoidasi | Qasddan shunday, o'zgartirilmaydi |
| Migratsiyada `server_default='false'` uslubi | Tarixiy, tegilmaydi |
| `main.py` router tuzatishi alohida commit emas | Git tarixi, qaytarib bo'lmaydi |

**Ya'ni bu bo'limda bajarilishi kerak bo'lgan ish qolmadi** — qolgan uch
qator "qasddan shunday" yoki "orqaga qaytarib bo'lmaydi" toifasida.
