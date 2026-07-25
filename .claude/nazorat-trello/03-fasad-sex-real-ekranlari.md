# 3. Fasad sex modulining haqiqiy ekranlari (hozir placeholder)

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
