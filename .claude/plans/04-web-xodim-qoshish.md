# Web panel orqali xodim qo'shish

Holat: QARORGA MUHTOJ — ikkita variant bor, foydalanuvchi tanlashi kerak
(implementatsiyaga kirishdan oldin).

TZ manbasi: 4.2-band, aniq matn: *"Admin panelga kirish faqat ikki asosiy
ish uchun zarur bo'lib qolishi kerak: statistika ko'rish va xodim
qo'shish."*

## Nima bor (2026-07-17 audit natijasi)

`web/src/public/index.html` faqat login + statistika dashboard + reyting
modalidan iborat — xodim qo'shish UI'si yo'q. `web/src/server.js`da
`/api/stats` route'idan boshqa hech narsa yo'q.

Xodim qo'shish/tahrirlash/o'chirish TO'LIQ ishlaydi, lekin faqat BOTDA:
`bot/handlers/admin/employee_management.py` (`/employees` buyrug'i) — 5.1/
5.2-band talablarining barchasini qamraydi (qadam-baqadam forma, Trello
username tekshiruvi, rol/bo'lim/brigada tanlovi, o'chirish/tahrirlash).

**Bu funksional bo'shliq emas** (xodim qo'shish ishlaydi) — bu TZ ko'rsatgan
KANAL bilan haqiqiy kanal orasidagi farq. `CLAUDE.md`ning o'zi ham
noaniq: "TZ §4 scopes it to 'view stats, add employees' only" deb yozgan,
lekin real web/ kodi faqat statistikani qamraydi.

## Ikkita variant

### A-variant: Bot-only qoldirish, CLAUDE.md'ni to'g'irlash (TAVSIYA ETILADI)

Sabab: xodim qo'shish — ko'p qadamli forma (5.1-band: ism, telefon, Trello
username + tekshiruv, rol, bo'lim, brigada, tasdiqlash) — bu allaqachon
botning FSM naqshiga juda mos (xuddi vazifa yaratish, moliyaviy taklif
kiritish kabi boshqa ko'p qadamli oqimlar ham botda). Ikkinchi marta shu
formani web'da JavaScript bilan qayta yozish — mantiqiy dublikat, ikki joyda
saqlash og'irligi (xuddi `stats.js`ning `stats_service.py`ni qo'lda
takrorlashi kabi muammo yaratadi, endi ikkinchi joyda).

Bu holda faqat **hujjat yangilanadi** (kod o'zgarmaydi):
`CLAUDE.md`dagi *"web/ — ... TZ §4 scopes it to 'view stats, add
employees' only"* jumlasi *"TZ §4 aytadi, lekin amalda xodim qo'shish ham
botda (`/employees`) qoladi — web faqat statistika, chunki ko'p qadamli
forma botning FSM naqshiga tabiiy mos keladi"* deb aniqlashtiriladi.

### B-variant: Web'da ham xodim qo'shish formasi qurish

Agar TZning aynan shu bandini so'zma-so'z bajarish kerak bo'lsa:

- `web/src/routes/employees.js` (yangi): `POST /api/employees` (5.1-band
  maydonlari: full_name, phone_number, trello_username, role, department_id,
  brigade_id), `requireAuth` bilan himoyalangan.
- Trello username tekshiruvi: `web/`da Python `TrelloClient` yo'q — yangi
  `node-fetch`/`axios` chaqiruvi kerak (`GET https://api.trello.com/1/members/{username}`),
  YOKI botdagi mantiqni takrorlamaslik uchun web endpoint faqat DB'ga yozadi,
  tekshiruv keyinroq (admin botda tasdiqlaganidek) — bu ikkinchi holatda
  Trello-tekshiruv KAFOLATI yo'qoladi (5.1-band asosiy foydasi shu edi).
- `web/src/public/index.html`ga yangi forma bo'limi (4.1-band "bitta oyna"
  printsipi — modal sifatida, alohida sahifa emas).
- Amaliy xavf: ikki mustaqil "xodim qo'shish" yo'li (bot + web) paydo
  bo'ladi — validatsiya qoidalari (masalan telefon dublikat tekshiruvi)
  ikkalasida ham bir xil bo'lishi kerak, kelajakda ikkalasini sinxronlab
  turish qo'shimcha yuk.

## Tavsiya

A-variant (hujjatni to'g'irlash, kodga tegmaslik) — chunki funksional
talab (xodim qo'shish ADMIN uchun oson bo'lishi) allaqachon bajarilgan,
faqat KANAL boshqacha. B-variant faqat foydalanuvchi buni qat'iy talab
qilsa qurilsin.

## Keyingi qadam

Foydalanuvchidan tanlov so'ralishi kerak: A yoki B. Tanlov aniqlanmaguncha
bu band amalga oshirilmaydi.

## Tugagach

- A tanlansa: faqat `CLAUDE.md` yangilanadi, bu hujjat olib tashlanadi.
- B tanlansa: yuqoridagi reja bo'yicha kod yoziladi, `shared/db-schema.md`ga
  o'zgarish kerak emas (yangi jadval yo'q, mavjud `employees`ga yozadi).
