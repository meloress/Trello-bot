# 4. Texnik qarz — review'lardan qolgan kichik topilmalar

Har biri **Minor** darajasida baholangan (xavfsiz, bloklovchi emas), lekin
vaqt o'tishi bilan yig'ilib ketmasligi uchun ro'yxatga olindi. Hech biri
hozircha foydalanuvchiga ta'sir qilmayapti (chunki tegishli frontend/real
foydalanish hali yo'q — `02`/`03`-fayllar hal bo'lgach, bularning ba'zilari
"real" bo'lib qoladi va ustuvorligi oshadi).

## Phase 1 — Zavod tegi
- `?factory_name=` bo'sh satr (`""`) bilan chaqirilsa, filtr sifatida
  qabul qilinadi (`Department.factory_name == ""`), "filtrsiz" deb emas.
  Hozircha frontend bu parametrni umuman jo'natmaydi — zararsiz. Frontend
  qo'shilganda: `factory_name or None` guardi kerak
  (`bot/miniapp/api/admin.py`, `/stats` route).

## Phase 3 — Fork/join
- **Join-fire idempotent emas**: 2 ishchi bir vaqtda oxirgi 2ta filial
  vazifasini tugatsa (masalan ikkalasi ham "Yakunlash" tugmasini deyarli
  bir vaqtda bossa), ikkalasi ham join bosqichini yaratishi mumkin
  (race condition). Tuzatish: `advance_task_stage()`da join yaratishdan
  oldin "shu previous_task_id uchun join task allaqachon yaratilganmi"
  tekshiruvi qo'shish.
- `POST /departments/{id}/fork-targets` input tekshiruvsiz: mavjud
  bo'lmagan `target_department_id` → 500 xato (400 emas); o'z-o'ziga fork
  qilish (department o'zini o'ziga target qilib ko'rsatishi) bloklanmagan.
- Filial (branch) vazifasi tugaganda ham `notify_client_stage_advanced`
  xabari ketadi — mijozga "bosqich o'tdi" deyiladi, aslida hali boshqa
  filiallar kutilmoqda. Kichik UX nuqson, mexanizm buzilmagan.

## Phase 5 — Stop kengaytmalari
- `seller_ids` ichida dublikat ID kelsa, `IntegrityError` chiqadi
  (`ValueError` emas) — foydalanuvchiga tushunarsiz xato ko'rinishi
  mumkin. Tuzatish: `create_task()`da `set(seller_ids)` yoki aniqroq
  tekshiruv.

## Phase 6 — Sig'im statistikasi
- `GET /admin/stats/capacity` docstring'i noto'g'ri funksiya nomiga
  ishora qiladi (`stats_service._month_bounds` deydi, aslida
  `penalty_service.month_bounds` chaqiriladi) — faqat izoh xatosi.
- `since` parametri berilib, `until` berilmasa (yoki aksincha), ikkalasi
  ham "joriy oy" default'iga tushadi — xato bermaydi, kutilmagan bo'lishi
  mumkin.

## Phase 7 — Tezlik-asosidagi to'lov
- Sozlamalar tekshiruvi xatosi `InvalidReminderScheduleError` nomi bilan
  chiqadi (aslida speed-tier uchun) — chalkashtiruvchi nom, funksional
  xato emas.
- `max_days` maydoniga kasr son (masalan "1.5") kiritilsa, jimgina
  butun songa kesiladi (`1`), rad etilmaydi.

## Phase 8 — Kunlik hisobot
- Migratsiyada `server_default='false'` (matn) ishlatilgan, boshqa
  joylarda `sa.false()` — funksional farq yo'q, faqat uslub farqi.
- `list_missing_for_date()` va admin route'dagi "kim topshirmagan"
  hisoblash mantiqi ikki joyda takrorlangan — birlashtirilishi mumkin.
- `main.py`dagi router tartib tuzatishi (bu ish davomida topilgan,
  `/mijoz`ga tegishli eski xato) alohida commit emas, feature commit
  ichida ketgan — funksional muammo emas, faqat git tarixi tozaligi.

## Phase 9 — MISC kategoriya
- Admin MISC ro'yxatida har vazifa uchun xodim ismini alohida so'rov
  bilan oladi (N+1) — hozirgi hajmda muammo emas, ko'p vazifa bo'lsa
  sekinlashishi mumkin.
- Yangi admin route'ning bo'lim-cheklash (department-scope) tekshiruvi
  faqat kod o'qish orqali tasdiqlangan, haqiqiy HTTP so'rov orqali test
  qilinmagan (real auth middleware'siz).

## Deploy paytida topilgan (bu ro'yxatga yangi qo'shilgan)
- Mini App static fayllari (`bot/miniapp/server.py`) uchun
  `Cache-Control` headerlari yo'q — Telegram WebView eski JS/CSS'ni
  keshda saqlab qolishi mumkin, har deploy'dan keyin foydalanuvchi
  Telegram'ni to'liq yopib qayta ochishi kerak bo'lmoqda. Batafsil:
  `06-production-tayyorgarlik.md`.
