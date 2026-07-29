# Brigada tizimi: yaratish mexanizmi yo'qligi + bitta brigadir bir nechta bo'limga rahbarlik qilishi

Holat: KOD TAYYOR (2026-07-29) — deploy va ma'lumot bog'lash qoldi.
Qolgan qadamlar hujjat oxirida ("Deploydan keyingi ma'lumot qadami").

Manba: TZning o'zidan emas — 2026-07-29 kuni haqiqiy production ma'lumotlarini
(real xodimlar, real Trello bog'lanishlari) kiritish jarayonida topilgan
amaliy bo'shliq. Mebel ("Fasad seh") moduli doirasida, lekin tuzatish
umumiy (`Brigade`/`BrigadeRepository`/`brigadier.py`) bo'lgani uchun
fasad_sex moduliga ham tegishli bo'ladi.

## Nima topildi

### 1. `brigades` jadvali production'da BO'SH, va uni to'ldiradigan hech qanday ekran yo'q

Real xodimlarni (2 brigadir + 10 ishchi) Mini App orqali "Xodim qo'shish"
ekranidan kiritib chiqilgach, bazani tekshirilganda `brigades` jadvalida
**0 ta qator** chiqdi. Butun kodni qidirilganda, `BrigadeRepository(...).create(...)`
faqat bitta joyda chaqirilar ekan — `bot/_seed_demo_data.py` (demo
ma'lumot skripti, production uchun ishlatilmaydi). Ya'ni:

- Mini App'da "Brigada yaratish" degan ekran/endpoint **umuman mavjud emas**.
- Shu sabab xodim tahrirlash ekranidagi "Brigada (ixtiyoriy)" dropdown
  (`renderBrigadeOptions()`, `miniapp/public/js/app.js`) har doim faqat
  bo'sh placeholder ("—") ko'rsatadi — `GET /admin/brigades?department_id=X`
  har qanday bo'lim uchun bo'sh ro'yxat qaytaradi, chunki so'rash uchun
  hech narsa yo'q.
- Natija: birorta ishchining `employees.brigade_id`si o'rnatilmagan holda
  qoladi, va `penalty_service._apply_brigade_share_for_worker()`ning birinchi
  qatori (`if worker.brigade_id is None: return None`) darhol ishga tushib,
  **brigadir hech qachon 8.4-band ulushini (0.33) olmaydi** — ishchiga
  jarima/bonus yozilsa ham, brigadirga hech narsa yozilmaydi va hech qanday
  bildirishnoma bormaydi. Bu — oldin muhokama qilingan "-1 ball → brigadirga
  0 bo'lib qoladi" (yaxlitlash) muammosidan MUTLAQO KATTAROQ va tub sababli
  bo'shliq: brigadalar yo'qligi tufayli ulush umuman ishlamaydi, faqat -1
  balda emas, HAR QANDAY balda.

### 2. Kod "bitta brigadir = bitta brigada" deb qattiq taxmin qiladi — baza esa buni cheklamaydi

`db/models/employee.py`dagi `Employee.led_brigades: Mapped[list["Brigade"]]`
munosabati aslida bitta xodim BIR NECHA brigadaga rahbarlik qila olishini
ALLAQACHON qo'llab-quvvatlaydi (`brigades.brigadier_id`da unique
cheklov yo'q). Lekin amaliy kod bunga zid:

- `db/repositories/brigade_repo.py`ning `get_by_brigadier_id()` metodi
  `scalar_one_or_none()` ishlatadi — agar bitta xodim 2 ta brigadaga
  rahbar bo'lsa, bu metod `MultipleResultsFound` xatosi bilan **qulaydi**.
- `miniapp/api/brigadier.py`ning `_resolve_brigade()` funksiyasi BRIGADIER
  roli uchun `brigade_id` so'rov parametrini umuman qabul qilmaydi (faqat
  SUPERVISOR uchun bor) — ya'ni qaysi brigadasini so'rayotganini
  ko'rsatishning imkoni yo'q.
- `_employee_in_scope()` ham xuddi shunday — faqat BITTA brigadaga nisbatan
  tekshiradi.
- `screenBrigadierHome()` (frontend) — brigadir uchun faqat bitta
  "Brigada" ekranini chizadi, ikkinchisini tanlash imkoniyati yo'q.

### 3. Real holat: Yoldoshov Elyor — bitta odam ikkita bo'limga (Kraska VA Shkurka) rahbar

Foydalanuvchi tasdiqladi: amalda Elyor ikkala brigadaga ham javobgar.
Bu — yuqoridagi #2 bandning nazariy emas, **haqiqiy, hozir kerak bo'lgan**
holati.

### 4. Tekshirilishi kerak bo'lgan ma'lumot xatosi (kod emas, qo'lda tuzatish)

Elyorga kiritilgan Trello username — `malikayoldosheva`. Lekin bu username
haqiqiy "Fasad seh" doskasida **BOSHQA odamga** ("Malika Yoldosheva")
tegishli ekani `GET /boards/{id}/members` orqali tasdiqlandi. Bu brigadalar
tizimini yoqishdan OLDIN tekshirilib, to'g'irlanishi kerak — aks holda
Elyorning ishlari Malikaning Trello hisobiga yozilib qoladi.

## Qaror qilingan yechim (foydalanuvchi bilan kelishilgan)

Alohida "Brigada yaratish" ekrani qurish O'RNIGA — sodda va real hayotga
yaqinroq avtomatik yondashuv:

1. **Xodimni BRIGADIR deb belgilaganda (bo'lim tanlangan holda) — tizim
   o'sha bo'limda unga avtomatik BITTA brigada yaratadi** (alohida "brigada
   nomi" so'ramasdan, masalan xodimning ismi yoki bo'lim nomi asosida).
   Reuse: agar allaqachon mavjud bo'lsa, qayta yaratilmaydi.
2. **Ishchi qo'shish/tahrirlashda "Brigada" dropdown'i endi abstrakt
   nomlar emas, balki BRIGADIRLAR ro'yxatini ko'rsatadi** — ishchi
   "kimning brigadasida ishlayman" deb brigadirni tanlaydi, tizim o'zi
   tegishli `brigade_id`ga bog'laydi.
3. **Bitta brigadir bir nechta bo'limga rahbarlik qiladigan kam uchraydigan
   holat uchun** (Elyor kabi) — o'sha brigadirning profilida qo'shimcha,
   ixtiyoriy maydon: **"Yana qaysi bo'limga rahbarlik qiladi"** — tanlansa,
   o'sha bo'limda ham unga avtomatik ikkinchi brigada yaratiladi.
4. Brigadirning Mini App'dagi "Brigada" ekrani — agar u faqat 1 ta
   brigadaga rahbar bo'lsa, **hech narsa o'zgarmaydi** (ko'pchilik uchun).
   2+ bo'lsa, yuqorida kichik tanlov (masalan "Kraska | Shkurka" tugmalari)
   chiqib, tanlangan brigada bo'yicha a'zolar/ball alohida ko'rsatiladi.
5. Brigadirga boradigan xabarlarga (yangi vazifa, 8.4-band ulush, Trello
   orqali topshirilgani tasdig'i) **bo'lim/brigada nomi aniq qo'shiladi**
   — masalan "...Kraska bo'limi bo'yicha..." — shunda ikkita brigadasi
   bor odam har bir xabar qaysi brigadasiga tegishli ekanini bilib turadi.

## Kerak bo'ladigan aniq o'zgarishlar

### Backend
- `db/repositories/brigade_repo.py`: `get_by_brigadier_id()` (scalar,
  ko'plik holatda qulaydi) → `list_by_brigadier_id()` (ro'yxat qaytaradi).
- Xodim yaratish/tahrirlash (`services/employee_service.py` yoki
  `miniapp/api/admin.py`dagi employee create/update): rol BRIGADIER
  bo'lsa va bo'lim tanlangan bo'lsa — mos brigada avtomatik
  yaratiladi/qidiriladi (get-or-create), `brigadier_id=employee.id`.
- Brigadir profiliga qo'shimcha bo'lim(lar) qo'shish uchun kichik
  endpoint/maydon — tanlangan har bir qo'shimcha bo'lim uchun yana bitta
  brigada avtomatik yaratiladi.
- `miniapp/api/brigadier.py`:
  - `_resolve_brigade()` — BRIGADIER uchun ham `brigade_id` so'rov
    parametrini qabul qiladi (bittadan ko'p brigadasi bo'lsa), 1 ta bo'lsa
    parametrsiz ham ishlayveradi (orqaga moslik).
  - `_employee_in_scope()` — nishon xodimning `brigade_id`si so'ragan
    brigadirning BARCHA boshqargan brigadalaridan biriga tegishli ekanini
    tekshiradi (bittasiga emas).
  - Yangi endpoint: `GET /brigadier/my-brigades` — so'ragan brigadirning
    o'zi boshqargan barcha brigadalari (id, nom, bo'lim nomi).
- `services/notification_service.py`: `notify_task_started`,
  `_apply_brigade_share_for_worker`ning `reason` matni,
  `notify_task_delegated_via_trello` — bo'lim/brigada nomini aniq qo'shish.

### Frontend (`miniapp/public/js/app.js`)
- `screenAddEmployee`/`screenEmployeeDetail`: "Brigada" maydoni endi
  brigadirlar ro'yxatidan tanlanadi (abstrakt brigada nomlari emas).
- `screenBrigadierHome()`: brigadirning `my-brigades`sini oldindan
  so'rab, 1 tadan ko'p bo'lsa tanlov (tab/segmented) qo'shish; tanlangan
  brigadaga qarab `/brigadier/brigade?brigade_id=X` chaqirish.

### Ma'lumot (Elyor uchun, kod emas)
- Avval uning Trello username xatosini (`malikayoldosheva` → to'g'ri
  qiymat) tuzatish.
- Mexanizm tayyor bo'lgach: unga Kraska (mavjud, avtomatik) + Shkurka
  (qo'shimcha, ixtiyoriy maydon orqali) — ikkala brigada ham yaratiladi.

## Amalda nima qilindi (2026-07-29)

Rejadagidan farqlar (soddaroq yo'l topilgani uchun):

- **Ishchi uchun brigada tanlanmaydi** — ishchi BO'LIMI bo'yicha o'sha
  bo'limning brigadasiga avtomatik bog'lanadi (`employee_service.sync_brigade_links`).
  Bo'limda 2 brigada bo'lsa noaniq, tegilmaydi (qo'lda tanlanadi).
- **Yangi endpoint qo'shilmadi**: `GET /brigadier/brigades` BRIGADIER uchun
  o'zi boshqargan brigadalarni qaytaradigan bo'ldi (yo'l-yo'lakay: ilgari
  brigadirga bo'limdagi BEGONA brigadalar ham ko'rinardi), `GET /brigadier/brigade`
  javobiga `brigades` + `own_score` qo'shildi.
- **Brigadirning o'z bali brigadadan mustaqil** (`own_score`) — aks holda
  ikkinchi brigada ekranida "—" bo'lib qolardi.
- **Brigada nomi = `"{Bo'lim} — {Ism}"`** (masalan "Kraska — Yoldoshov Elyor"),
  shu sabab 5-band (xabarlarda bo'lim ko'rinishi) qo'shimcha so'rovsiz hal
  bo'ldi: ulush sababida brigada nomi, vazifa/claim xabarlarida bo'lim nomi.
- **Davom ettirish ham tasdiq talab qiladi** (foydalanuvchi qarori,
  2026-07-29): `ClaimActionType.RESUME` qo'shildi (migratsiya shart emas —
  ustun `native_enum=False`), `claim_service.approve_claim` uchinchi tarmoq
  bilan `timer_service.resume_task`ni chaqiradi. Brigadirning eski,
  tasdiqsiz ishlaydigan `POST /members/{id}/tasks/{tid}/resume` endpointi
  `resume-claim` bilan almashtirildi; ishchining o'z `POST /tasks/{id}/resume`i
  mebel uchun 409 qaytaradigan bo'ldi (Pauza/Yakunlash bilan bir xil).
  `notification_service.notify_task_resumed` ishlatilmay qolgani uchun
  o'chirildi.
- **Brigadirlikdan tushirilgan xodim** boshqargan brigadalari avtomatik
  brigadirsiz qoladi, ustiga `_active_brigadier_ids`/`list_department_brigadiers`
  rol bo'yicha ham filtrlaydi (eski ma'lumot uchun).
- Rahbarlikdan olingan bo'lim brigadasi **o'chirilmaydi** — `brigadier_id=None`
  bo'ladi, a'zolari va KPI tarixi joyida qoladi. Yangi brigadir o'sha bo'limga
  tayinlansa, yangi brigada yaratilmay o'sha "yetim" brigada olinadi.

Tekshiruv: `bot/tests/test_brigade_membership.py` (6 holat, bazasiz, oddiy
`python tests/test_brigade_membership.py`).

## Deploydan keyingi ma'lumot qadami

**Tartib muhim**: avval Railway'ga deploy, keyin ma'lumot. Elyorga ikkinchi
brigada YARATILSA, eski koddagi `get_by_brigadier_id()` (`scalar_one_or_none`)
`MultipleResultsFound` bilan quladi — ya'ni deploy qilinmagan bot uning
Brigada ekranini umuman ocholmaydi.

Deploydan keyin (Mini App'dan, alohida skript shart emas):

1. Abrayev Ilhom (Shpon) — Xodim tafsiloti → Saqlash. "Shpon — Abrayev Ilhom"
   brigadasi yaratiladi, Shpondagi 3 ishchi avtomatik bog'lanadi.
2. Yoldoshov Elyor (Kraska) — "Yana qaysi bo'limga rahbarlik qiladi" →
   Shkurka belgilanadi → Saqlash. Ikkita brigada yaratiladi, Shkurkadagi
   7 ishchi avtomatik bog'lanadi.
3. Tekshirish: brigadirning Brigada ekranida ikkita tanlov chiqadi, a'zolar
   to'g'ri bo'linadi.

(4-band — Elyorning `malikayoldosheva` Trello hisobi — **tuzatilmaydi**:
foydalanuvchi tasdiqladi, bu uning oilaviy hisobi, hamma biladi.)

## Tugagach

- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
- `shared/db-schema.md`ning `brigades`/`employees` bo'limi (agar
  avtomatik-yaratish xatti-harakati tavsiflansa) yangilanadi.
- `CLAUDE.md`ga bir qatorlik eslatma: brigada endi qo'lda emas, rol
  BRIGADIER bo'lganda avtomatik yaratiladi.
