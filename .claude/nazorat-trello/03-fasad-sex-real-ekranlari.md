# 3. Fasad sex modulining haqiqiy ekranlari (hozir placeholder)

## ✅ 2026-07-27: bajarildi

Tekshiruvda ma'lum bo'ldiki, worker/brigadier/seller uchun mavjud ekranlar
(`screenWorkerOrders`, `screenTaskList("misc")`, `screenWorkerScore`,
`screenBrigadierHome`, `screenSellerHome`) — hech biri modulga (mebel/
fasad_sex) qarab backend'da filtrlanmaydi: ular xodimning o'z tayinlovi
(`task_assignments`/`brigade_id`) bo'yicha ishlaydi, bo'lim qaysi modulga
tegishli ekanidan qat'iy nazar to'g'ri ma'lumot qaytaradi. Ya'ni "haqiqiy
ekranlar" allaqachon bor edi — BLOKLOVCHI muammo faqat **frontend
marshrutlashda** edi: `tabDefsForRole()` `module === "fasad_sex"` bo'lganda
ROLdan qat'iy nazar hammaga `screenAdminHome`ni qaytarardi, shu sabab
worker/brigadir shu bo'limga tushib ADMIN-only endpoint'ga urilib 403
ko'rardi.

Tuzatish: `tabDefsForRole()`dagi modul-bo'yicha-hammasini-almashtirish bloki
olib tashlandi — endi tab to'plami faqat ROLga qarab tanlanadi (avvalgidek),
`module` esa faqat worker'ning "Buyurtmalar" tab yorlig'ini Fasad sex uchun
"Bosqichlar"ga almashtirish uchun ishlatiladi (`screenWorkerOrders`dagi
bo'lim sarlavhasi ham xuddi shunday). Natijada:

- **Worker/brigadier/seller**: o'z rolining odatdagi ekranlarini ko'radi
  (Fasad sex bo'limiga tayinlangan bo'lsa ham) — hech qanday yangi ekran
  yozishga hojat qolmadi, chunki mavjudlari allaqachon modul-agnostik edi.
- **Admin/supervisor**: avval fasad_sex tanlanganda faqat Bosh sahifa+Profil
  ko'rar edi (Statistika/Xodimlar/Moliyaviy yo'qolib qolardi) — endi ikkala
  modulda ham to'liq 5 tabni ko'radi (bu ekranlar ham modulga qarab
  filtrlanmaydi, shu sabab qisqartirishning hech qanday asosi yo'q edi).

Kod: `bot/miniapp/public/js/app.js` (`tabDefsForRole`, `screenWorkerOrders`),
`bot/miniapp/public/js/i18n.js` (`tab_stages`/`myStages`/`noStages` qo'shildi,
ishlatilmay qolgan `fasadHomeTab` olib tashlandi). Backend'da o'zgarish
kerak bo'lmadi.

---

**Original muammo tavsifi (tarixiy kontekst uchun saqlanadi):**

## Muammo

Phase 0'da Mini App'ga "qaysi tizim" tanlash ekrani qo'shilganda,
`fasad_sex` moduli uchun HALI haqiqiy bosh sahifa/tab ekranlari yo'q edi
(chunki hech qanday Fasad sex ma'lumoti yo'q edi). Shu sabab hozircha
`fasad_sex` moduli tanlanganda **mavjud, mebel-uchun-mo'ljallangan
`screenAdminHome`/`screenProfile` ekranlari qaytadan ko'rsatiladi**
(placeholder sifatida).

## Nega bu BLOKLOVCHI muammo

`screenAdminHome` faqat **ADMIN/SUPERVISOR** uchun ishlaydigan backend
endpoint'larni chaqiradi (`/admin/dashboard`, `/admin/pending-setup`,
va h.k.). Agar **ISHCHI yoki BRIGADIR** xodimi `fasad_sex` tegli bo'limga
tayinlansa (`employees.department_id` → shu bo'lim `module="fasad_sex"`),
u Mini App ochganda avtomatik shu placeholder'ga tushadi va **403 xatosi**
ko'radi — chunki placeholder ADMIN-only endpoint chaqiradi, ishchiga emas.

Bu — Phase 0'ning o'z review'ida ANIQ topilgan va yakuniy (whole-branch)
review'da ham qayta tasdiqlangan ochiq masala.

## Kerak bo'lgan ish

Haqiqiy Fasad sex bosh sahifa + tab to'plami qurish, TZning o'z
sxemasiga mos (dastlabki eskiz `bu-endi-proektning-ikkinchi-agile-planet.md`
faylida — HTML mockup sifatida ham chizilgan edi):

- **Ishchi/brigadir uchun**: Bosh sahifa (o'z vazifalari) / Bosqichlar
  (Fasad sex'ga tegishli bosqichlar ro'yxati) / Profil.
- **Admin/nazoratchi uchun**: allaqachon `screenAdminHome` ishlaydi (bu
  ADMIN uchun to'g'ri, chunki ADMIN har doim ikkala modulni ham ko'ra
  oladi) — MUAMMO faqat ishchi/brigadir/sotuvchi kabi rollar uchun.

## Amaliy tavsiya

`01-haqiqiy-zanjir-yaratish.md`dagi zanjir yaratilgach, birinchi navbatda
**faqat ADMIN/SUPERVISOR**ni shu bo'limlarga tayinlang (ular hozirgi
placeholder bilan ham ishlay oladi). Ishchi/brigadir tayinlashdan OLDIN,
albatta shu bosqichni (haqiqiy `fasad_sex` bosh sahifa/tab ekranlarini
qurish) bajarish kerak — bu alohida, o'rtacha hajmdagi frontend ishi.
