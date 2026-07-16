# 6-bosqich: Umumiy test, ishga tushirish, SaaS tayyorgarlik

Holat: NAVBATDA (loyihaning oxirgi rasmiy bosqichi). TZda "3-etap,
6-bosqich": "Umumiy test, ishga tushirish; SaaS tayyorgarlik: billing
(Ping), obuna, video darslar bo'limi".

TZ manbasi: 15-band to'liq (SaaS mahsulot, "AmoCRM qotili"), 16-band
(nofunksional talablar — ishonchlilik, multi-tenant tayyorlik), 14-band
(texnik arxitektura — billing/hosting qatorlari).

## Bu bosqich ikkita SIFAT JIHATDAN FARQLI qismdan iborat

1. **Umumiy test/ishga tushirish** — 1-5-bosqichlarda qurilgan tizimni
   yaxlit tekshirish, production'ga chiqarish. Bu — muhandislik ishi, TZda
   aniq band raqami yo'q (natija sifatida yozilgan), lekin CLAUDE.mddagi
   "har bosqich real infratuzilmada sinovdan o'tkaziladi" qoidasining
   YAKUNIY, katta ko'lamli varianti.
2. **SaaS tayyorgarlik** (15-band) — bu TZning o'zi tan olgan **2-FAZA**
   ishi: "Ikkinchi faza: SaaS mahsulot... amalga oshirilishi 2-fazada."
   15-band ochilishida shunday deyilgan: bu "arxitekturaga BOSHIDANOQ
   ta'sir qiladi (multi-tenant bo'lishga tayyorlab qurish kerak), lekin
   amalga oshirilishi 2-fazada." Demak, 6-bosqichda kutilayotgan narsa —
   TO'LIQ SaaS emas, balki **billing/obuna INFRASTRUKTURASINI tayyorlash**.

## A. Umumiy test va ishga tushirish

Hozircha kodda avtomatik test suite yo'q (`bot/tests/` bo'sh skelet,
`requirements.txt`da pytest yo'q — CLAUDE.md tasdiqlaydi). Bu bosqichda:

- Barcha 1-5-bosqichlar TO'LIQ tugagan va real infratuzilmada alohida-
  alohida sinovdan o'tgan bo'lishi SHART (oldingi bosqichlar shartisiz bu
  bosqich boshlanmaydi).
- **Uchdan-uchga (end-to-end) stsenariy testi**: real Trello "Test" board +
  Railway DB'da butun oqim — yangi buyurtma yaratish -> bir necha bosqich
  bo'ylab o'tish -> kechikish -> jarima -> 8.3 avto-o'tkazish -> yakunlash
  -> statistika/hisobot -> mijoz xabarnomasi — bittа uzun smoke-test
  skriptida (`bot/_smoke_e2e_full.py`) ketma-ket tekshiriladi.
- **Production infratuzilmaga o'tish**: xosting (VPS/bulut, 14-band) tanlab
  bot va (agar tayyor bo'lsa) web panelni 24/7 ishga tushirish; bu — DevOps
  ishi, TZda aniq host tanlanmagan (ochiq savol).
- **Production Trello board'lariga o'tish**: "Fasad seh" (production)
  boardida haqiqiy sinov EMAS, balki HAQIQIY ishga tushirish — bu bosqichda
  test board o'rniga birinchi marta production board bilan ishlanadi,
  ehtiyotkorlik bilan (backup, rollback rejasi bilan).
- Xatolik holatida avtomatik backup/qayta ishga tushirish (16-band
  talabi) — process supervisor (masalan `systemd`/`pm2`/Docker restart
  policy) sozlanishi kerak, TZda aniq vosita ko'rsatilmagan.

## B. Billing (Ping) integratsiyasi (14.1/15.2-band)

TZ matni: "To'lov faqat billing (Ping) integratsiyasi orqali — to'g'ridan-
to'g'ri karta ulanmaydi (soliq xavfi)." va "OBUNA (podpiska) modeli: mijoz
to'lamasa tizim AVTOMATIK O'CHADI."

TZ 19-band ochiq savol #13: "SaaS obunaning narxi va Ping billing
shartnomasi tafsilotlari (2-faza boshlanishidan oldin)" — **TO'LIQ
BLOKLANGAN**, bu ishni boshlashdan oldin biznes tomonidan Ping bilan
shartnoma va narxlash tugallangan bo'lishi SHART. Dasturiy jihatdan hech
narsa qilib bo'lmaydi — bu tashqi integratsiya, hujjatlashtirilgan API
kelmaguncha texnik loyihalash mumkin emas.

## C. Obuna va multi-tenant tayyorlik (15.1/15.2/16-band)

TZ 16-band: "Multi-tenant tayyorlik: arxitektura kelajakda bir nechta
korxonaga xizmat qilishga (SaaS) to'sqinlik qilmasligi kerak." Bu talab
ARXITEKTURAGA 1-bosqichdan beri yashirin ta'sir qilib kelgan (masalan,
`departments`/`employees` global emas, balki mustaqil qatorlar sifatida
loyihalangan) — lekin HALI hech qanday `organization_id`/tenant ustuni
qo'shilmagan (`shared/db-schema.md`da aniq yozilgan: "`organizations` —
15-band, multi-tenant (SaaS) fazasi uchun" hali yaratilmagan jadval
ro'yxatida).

**Bu qismni to'liq amalga oshirish KATTA REFAKTORING** (deyarli har bir
jadvalga `organization_id` FK qo'shish, har bir so'rovni shu bilan
filtrlash) — TZning o'zi buni "2-fazada amalga oshiriladi" deb aytadi, ya'ni
**hozirgi 6 bosqichlik rejaning tashqarisida**. Shu sabab bu hujjatda faqat
BELGILAB QO'YILADI, konkret implementatsiya rejasi yozilmaydi — 2-faza
boshlanganda alohida TZ/reja kerak bo'ladi.

## D. Video darslar bo'limi (15.2-band)

TZ matni: "O'rgatish: KO'CHIRIB BO'LMAYDIGAN video darslar Telegram
(himoyalangan kanal) yoki sayt ichiga joylanadi; mijoz kirib tartib bilan
ko'radi." Bu ham SaaS-mijozlar (kelajakdagi boshqa mebel sexlari) uchun,
ICHKI Melores Mebel jamoasi uchun EMAS. 2-faza doirasida.

- "Ko'chirib bo'lmaydigan" (nusxa olib bo'lmaydigan) — texnik jihatdan
  to'liq himoya mumkin emas (screen recording doim mavjud), lekin oddiy
  chora: Telegram'ning "forward taqiqlangan" himoyalangan kanal xususiyati
  yoki web'da video streaming (yuklab olishsiz) — texnik tanlov, 2-faza
  boshlanganda hal qilinadi.

## Bu bosqich uchun yakuniy xulosa

**A qismi (umumiy test/ishga tushirish)** — bu 6 bosqichlik rejaning
haqiqiy YAKUNI, 1-5-bosqichlar tugagach albatta bajariladi.

**B/C/D qismlari (SaaS: billing, multi-tenant, video darslar)** — TZning
o'zi bularni "2-faza" deb ataydi va ochiq savol #13 orqali biznes
tomonidan hali TASDIQLANMAGAN shartlarga (Ping shartnomasi, narxlash)
bog'liq. **Tavsiya**: A qismi tugagach, B/C/D uchun alohida yangi
suhbatda, yangilangan biznes ma'lumotlar bilan (Ping shartnomasi imzo­
langanmi, narxlash tasdiqlanganmi) qaytadan rejalashtirish — bu hujjat
faqat TZda nima yozilganini qamrab oladi, hozirgi loyihaning texnik
holatidan kelib chiqmagan taxminiy reja YOZILMAYDI.

## Ochiq savollar (2-faza boshlanishidan oldin, TZ 19-band)

1. SaaS obunaning narxi va Ping billing shartnomasi tafsilotlari (#13) —
   BOSHQA hamma narsadan oldin hal qilinishi kerak.
2. Xosting/VPS tanlovi (A qismi uchun, TZda ko'rsatilmagan).

## Tekshirish rejasi

- **A**: yuqorida tavsiflangan `_smoke_e2e_full.py` + production'ga
  chiqarilgandan keyin kamida bir necha kunlik "kuzatuv davri" (log
  monitoring, xatoliklarni kuzatish) — avtomatlashtirilgan test emas,
  operatsion nazorat.
- **B/C/D**: 2-faza rejalashtirilganda alohida aniqlanadi.
