# 2. Frontend'da yetishmayotgan tugma/ekranlar

## ✅ 2026-07-24: bajarildi

Tekshiruvda 2.1 (chain-link) va material-shablon formasi **allaqachon
mavjud** ekani ma'lum bo'ldi (`screenDepartmentChain`/`Edit`,
`screenAddMaterialTemplate`) — hujjat shu ikkitasi bo'yicha eskirgan edi.
Haqiqatan yo'q bo'lgan uchtasi qo'shildi:

- **2.3 (bo'lim tahrirlash) + 2.5 (stop-target)** — `screenDepartments`da
  har bir qator endi bosiladi (`fin-card` → `button`) va
  `screenDepartmentEdit`ni ochadi: nom, Trello list ID,
  `auto_reassign_after_48h`, `starts_stopped`,
  `stopped_auto_resume_after_hours` (yangi, Sklad uchun),
  `requires_join`, `factory_name`, `stop_target_list_id` — bittasi
  ichida. Shu ekrandan ichkariga ikkita nav-qator: mavjud
  chain-edit ekraniga va yangi fork-target ekraniga.
- **2.2 (fork-target)** — `screenDepartmentForkTargets`: boshqa barcha
  bo'limlarning checkbox ro'yxati, `GET/POST
  /departments/{id}/fork-targets` bilan to'liq almashtirish naqshida.
- **2.4 (sotuvchi biriktirish)** — yangi buyurtma formasida
  "Sotuvchi(lar) (≤3)" checkbox bo'limi (faqat `role=seller`
  xodimlar), `POST /admin/tasks`ga `seller_ids` sifatida yuboriladi.

Yon-tuzatish: `POST /admin/departments/{id}` endi
`_department_scope_ok`ni tekshiradi (2026-07-22 auditning naqshi bo'yicha
— avval bu ikkita endpoint, department create/update, shu tekshiruvni
o'tkazib yuborgan edi, SUPERVISOR har qanday bo'limni tahrirlay olardi).

Batafsil kod: `bot/miniapp/api/admin.py` (`list_departments`,
`update_department`), `bot/miniapp/public/js/app.js`
(`screenDepartmentEdit`, `screenDepartmentForkTargets`,
`screenNewTaskForm`), `bot/miniapp/public/js/i18n.js`.

---

**Original reja matni (tarixiy kontekst uchun saqlanadi):**

Har birida backend (API, ma'lumotlar bazasi) **100% tayyor va ishlaydi**
— faqat Mini App'da ularni sozlash uchun tugma/ekran yo'q. Hozircha bu
narsalarni men to'g'ridan-to'g'ri (skript/API orqali) sozlab beraman;
pastda har biri uchun qaysi backend endpoint tayyor ekani yozilgan —
kimdir keyinchalik shu ustiga tugma qo'shishi mumkin.

## 2.1. Bosqichlarni zanjirlash (chain-link) ekrani

- **Backend tayyor**: `POST /admin/departments/{id}/chain` —
  `{"next_department_id": <id>}`.
- **Yo'q**: bo'lim ro'yxatida "keyingi bosqich" tanlash dropdown/tugmasi.
  Hozircha zanjir faqat API chaqiruvi orqali bog'lanadi.

## 2.2. Fork-target (bo'linish) sozlash ekrani

- **Backend tayyor**: `GET/POST /departments/{id}/fork-targets` —
  bitta bosqichning bir nechta parallel filialga bo'linishini belgilaydi
  (masalan "Fayl yig'ish" → Korpus/Ichki/Fasad qismi).
- **Yo'q**: multi-select UI. Bu — Fasad sex zanjirining ENG murakkab
  qismi (fork/join), shu sabab UI qo'shish alohida e'tibor talab qiladi.

## 2.3. Bo'lim tafsilot/tahrirlash ekrani

- **Backend tayyor**: `POST /admin/departments/{id}` — nom, Trello list
  ID, `auto_reassign_after_48h`, `starts_stopped`, `requires_join`,
  `factory_name`, `stop_target_list_id`, `module` — hammasini
  o'zgartirish mumkin (bitta umumiy endpoint).
- **Yo'q**: bosilganda bitta bo'limning barcha maydonlarini ko'rsatib,
  tahrirlash imkonini beradigan ekran. Hozir faqat ro'yxat (nom + 2ta
  chip) va yaratish formasi bor — mavjud bo'limni O'ZGARTIRISH ekrani
  yo'q (Phase 2'da ataylab keyinga qoldirilgan edi).

## 2.4. Sotuvchi biriktirish (buyurtma yaratishda)

- **Backend tayyor**: `create_task()` `seller_ids: list[int]` (0-3 ta)
  qabul qiladi, `POST /admin/tasks`ga ham ulangan.
- **Yo'q**: yangi buyurtma yaratish formasida "Sotuvchi(lar)" multi-select
  maydoni. Hozircha sotuvchi API orqaligina biriktiriladi.

## 2.5. Stop → Trello list ko'chirish sozlamasi

- **Backend tayyor**: `departments.stop_target_list_id` — o'rnatilsa,
  shu bo'limda Stop bosilganda karta belgilangan list'ga ko'chadi
  (Resume'da qaytadi). Umumiy `POST /admin/departments/{id}` orqali
  o'rnatiladi.
- **Yo'q**: bo'lim tahrirlash ekranida "Stop bosilsa qaysi list'ga
  ko'chsin" tanlagich (2.3-band bilan bog'liq — ikkalasi bitta ekranda
  hal bo'lishi mumkin).

## Ishlash tartibi tavsiyasi

2.3 (bo'lim tahrirlash ekrani) — eng foydali, chunki 2.1/2.2/2.5ning
hammasi shu bitta ekran ichiga joylashtirilishi mumkin (bitta forma,
bir nechta bo'lim). 2.4 alohida (buyurtma yaratish formasiga tegishli).

Bu ishlarning barchasi — **kod yozish** ishi, kelgusi bosqichlarda
alohida topshiriq sifatida bajarilishi mumkin.
