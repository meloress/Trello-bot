# TZ — Ishlab chiqarish nazorat tizimi (Telegram bot + Trello + Web panel)

> **Bu fayl VS Code'dagi Claude agenti uchun asosiy kontekst hujjati.**
> Loyiha ildiziga `SPEC.md` yoki `CLAUDE.md` nomi bilan qoʻyiladi.
> Agent har bir vazifani shu hujjatdagi qoidalarga tayanib bajaradi.

---

## 0. Agentga kirish prompt (VS Code'da birinchi xabar sifatida yuboriladi)

```
Sen shu repoda ishlaydigan senior backend dasturchisan.
Loyiha: mebel fabrikasi uchun ishlab chiqarish jarayonlarini nazorat qiluvchi tizim.
Barcha talablar SPEC.md faylida. Kod yozishdan oldin SPEC.md ni toʻliq oʻqi.

Qoidalar:
1. Biznes-mantiq (SLA hisoblash, jarima ball, STOP) faqat oʻz backendimizda boʻladi.
   Trello — bu shunchaki UI adapter, unga bogʻlanib qolmaymiz.
2. Har bir sex/kompaniya uchun jarayonlar va muddatlar konfiguratsiya orqali
   oʻzgaradi. Hech qanday muddat yoki bosqich kodga hardcode qilinmaydi.
3. Vaqt hisobi soat/daqiqa aniqligida (timestamp). Trello'ning sana maydoniga
   ishonmaymiz — u faqat kunni saqlaydi.
4. Har bir oʻzgarish uchun migration + test yoz.
5. SPEC.md dagi "Ochiq savollar" boʻlimidagi noaniq joylarda oʻzing qaror qabul
   qilma — menga savol ber.

Birinchi vazifa: 8-boʻlimdagi "Faza 1" ni bajar.
```

---

## 1. Loyihaning maqsadi

Mebel fabrikasida zakaz ishlab chiqarishning har bir bosqichini avtomatik nazorat qilish:

- Zakaz bosqichdan bosqichga oʻtganda **avtomatik muddat (SLA)** qoʻyiladi.
- Muddat oʻtib ketsa — oʻsha bosqichga biriktirilgan **aniq odamga jarima ball** yoziladi.
- Barcha ogohlantirishlar **Telegram** orqali (shaxsiy + sex guruhiga) boradi.
- Rahbar uchun **statistika**: kim qancha bajardi, qancha kechikdi, qancha STOP boʻldi.

**Muhim strategik talab:** tizim keyinchalik boshqa mebel kompaniyalariga sotiladi.
Shuning uchun jarayonlar soni, nomlari va muddatlari **har bir mijoz uchun sozlanadigan**
boʻlishi shart. Oddiy biznes = kam bosqich = arzon tarif; murakkab ishlab chiqarish =
koʻp bosqich = qimmat tarif.

---

## 2. Arxitektura

```
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│ Telegram bot│   │ Web panel    │   │ Trello      │
│ (ishchilar) │   │ (rahbar/admin)│  │ (adapter)   │
└──────┬──────┘   └──────┬───────┘   └──────┬──────┘
       │                 │                  │ webhook
       └────────────┬────┴──────────────────┘
                    ▼
          ┌───────────────────────┐
          │  CORE BACKEND (API)   │  ← yagona haqiqat manbai
          │  SLA engine           │
          │  Penalty engine       │
          │  Notification service │
          │  Scheduler (cron)     │
          └──────────┬────────────┘
                     ▼
               PostgreSQL + Redis
```

**Qoida:** Trello oʻchirilsa ham tizim ishlashda davom etadi. Trello faqat
vizual koʻrinish uchun sinxronlanadi (ikki tomonlama).

### Trello mapping (adapter uchun)
| Trello obyekti | Bizning obyekt |
|---|---|
| Board | Sex (workshop) |
| List | Stage (jarayon bosqichi) |
| Card | Order (zakaz) |
| Card members | Stage assignees |
| Label (rangli) | STOP holati / srochnost |
| Custom field | m², srochnost, sotuvchi |
| Card move (webhook) | `stage_transition` eventi |

---

## 3. Domain model (asosiy jadvallar)

```
Company        — mijoz kompaniya (multi-tenant)
Workshop       — sex (fasad sex, stolyarka, korpus sex, showroom...)
StageTemplate  — sex ichidagi bosqich: nomi, tartibi, default SLA, qoidalar
Order          — zakaz (nomer, mijoz, sotuvchi, m², srochnost flag)
OrderStage     — zakazning konkret bosqichi: entered_at, due_at, finished_at,
                 assignees[], status(active|stopped|done|overdue)
StopLog        — STOP boshlanishi/tugashi (muddatni "muzlatish" uchun)
Penalty        — jarima ball: user, order_stage, ball, sabab, sana
User           — xodim: telegram_id, rol, sex, rahbar_id
Task           — "vazifa buyurish" moduli (zakazdan mustaqil)
NotificationLog
```

---

## 4. Jarayon xaritasi (fasad sex — default shablon)

> Bu **default shablon**. Boshqa sex/kompaniyada bosqichlar qoʻshiladi/olib tashlanadi.
> Interfeysda **"+ Bosqich qoʻshish"** tugmasi boʻlishi shart.

| # | Kod | Nomi | Default SLA | Mas'ul |
|---|---|---|---|---|
| 1 | `order_intake` | Zakaz kiritish / vazifa buyurish | — | Sotuvchi / admin |
| 2 | `control_measure` | Kontrolniy zamer | **24 soat** | Zamerchi (1–2 kishi) |
| 3 | `drawing` | Chizish | **48 / 72 / 24 soat** (5.2-band) | Chizuvchi (2 kishi) |
| 4 | `gip_lab` | GIP-lab / tekshiruv ⚠️ | **24 soat** | ⚠️ aniqlanishi kerak |
| 5 | `file_prep` | Fayl yigʻish (+ zapchast yigʻish) | **24 soat** | Fayl yigʻuvchi |
| 6 | `supply` | Taʼminot | **SLA yoʻq** (ixtiyoriy) | Taʼminotchi |
| 7 | `file_dispatch` | Fayl tashlash (laminoks / eman / zavod-2) | **24 soat** | Har material boʻyicha alohida odam |
| 8 | `production` | Ishlab chiqarish | **72 soat (3 sutka)** | Zavod / brigada |
| 9 | `body_cut` | Raspil / korpus tayyorlash | konfig | Korpus ustasi |
| 10 | `body_shop` | Korpus sex | konfig (+24 soat muammo bildirish) | Korpus sex (1–2 kishi) |
| 11 | `veneer` | Shpon sex | **72 soat** | Shpon ustasi |
| 12 | `paint_block` | Shkurka → Kraska/Malyarka | **15 kun (butun blok uchun)** | Malyarka |
| 13 | `dry_pack` | Quritish / oʻrash / upakovka | konfig | — |
| 14 | `warehouse` | Sklad | odatda STOP holati | — |
| 15 | `delivery` | Dostavka (logistika) | **24 soat** | Logistika (3–4 kishi) |
| 16 | `installation` | Montaj / ustanovka | konfig | Brigada (7–9 brigada) |
| 17 | `done` | Yakunlandi | — | — |

### Tarmoqlanish (branching)
`gip_lab` / `file_prep` dan keyin zakaz **ikkiga boʻlinadi**:

```
                    ┌── FASAD tarmogʻi: file_dispatch → production → veneer → paint_block → dry_pack ──┐
gip_lab → file_prep ┤                                                                                  ├→ delivery → installation → done
                    └── KORPUS tarmogʻi: body_cut → body_shop → warehouse ────────────────────────────┘
```

**Muhim:** `delivery` bosqichiga oʻtish uchun **ikkala tarmoq ham** tugagan boʻlishi kerak.
Har bir tarmoq oʻz SLA'si va oʻz mas'uli bilan mustaqil hisoblanadi.

---

## 5. SLA (muddat) hisoblash mantigʻi

### 5.1 Asosiy qoida
- Muddat **zakaz shu bosqichga oʻtkazilgan aniq vaqtdan** boshlanadi:
  `due_at = entered_at + SLA_hours`
- `entered_at` — bizning bazadagi timestamp (soat:daqiqa aniqligida).
- ❌ Trello'ning "Начало / Start date" maydoni **ishlatilmaydi** — u faqat kunni saqlaydi.
- Bosqich tugaganda `finished_at` yoziladi. `finished_at > due_at` → **overdue**.

### 5.2 Chizish bosqichining maxsus navbat qoidasi
Kunlik norma: **5 punkt / kun ≈ 100 m²**.

```
if order.is_urgent:            SLA = 24 soat
elif kun ichidagi tartib ≤ 5:  SLA = 48 soat
else:                          SLA = 72 soat
```
Ya'ni bir kunda tushgan zakazlarning birinchi 5 tasiga 48 soat, qolganiga 72 soat.
Bu qoida **konfiguratsiyada** saqlanadi (`daily_quota`, `sla_within_quota`, `sla_over_quota`, `sla_urgent`).

### 5.3 Blok SLA (paint_block)
`shkurka + kraska + malyarka` — ichki bosqichlarga muddat qoʻyilmaydi, ammo
**butun blokdan chiqish 15 kun ichida** boʻlishi shart. Ichida erkin harakatlanish mumkin.

### 5.4 Eslatmalar (reminder)
- Muddat tugashiga **N soat qolganda** eslatma (konfig, default: 4 soat).
- Muddat oʻtganda darhol xabar + jarima ball.
- Kechikish davom etsa, har `M` soatda takroriy eslatma (default: 12 soat).

---

## 6. STOP mexanizmi

- Har qanday bosqichda zakazga **STOP** bosilishi mumkin (mijoz kutmoqda, material yoʻq va h.k.).
- STOP bosilganda:
  1. Taymer **toʻxtaydi** (`due_at` STOP davomiyligiga suriladi).
  2. Kartaga vizual belgi qoʻyiladi (Trello'da rangli label).
  3. **Avtomatik xabar** oʻsha zakazning sotuvchisiga boradi.
  4. `StopLog` ga yozuv tushadi.
- "STOP bosilgan zakazlar" degan alohida roʻyxat/filtr boʻladi.
- STOP olib tashlanganda taymer davom etadi.
- Statistikada STOP vaqti **ish vaqtidan chiqarib tashlanadi** — aks holda ishchi
  "men vaqtida qildim" deb bahslashadi.

---

## 7. Jarima ball (penalty) tizimi

- Jarima **bosqich darajasida** yoziladi, zakaz darajasida emas.
- Bir bosqichda 2 kishi biriktirilgan boʻlsa — ikkalasiga ham yoziladi (yoki konfig
  boʻyicha faqat asosiy mas'ulga). Sozlanadigan boʻlsin.
- Bosqichlar mustaqil: `gip_lab` kechiksa `file_prep` odamiga jarima **tushmaydi**.
- Ball miqdori konfiguratsiyada: masalan `1 ball / kechikkan 24 soat`.
- Rahbar (`user.manager_id`) ham xabarnomaga ulanishi mumkin.

### Bonus/motivatsiya (production bosqichi)
Ishlab chiqarish tezligiga qarab toʻlov farqlanadi:
`1 sutka → yuqori tarif`, `3 sutka → standart`, `5 sutka → past tarif`.
Tizim faqat **faktni qayd etadi va hisoblab beradi**, pul toʻlashni emas.

---

## 8. Xabarnomalar (Telegram)

| Hodisa | Kimga |
|---|---|
| Yangi vazifa biriktirildi | Mas'ul (shaxsiy) + sex guruhi |
| Muddat tugashiga N soat qoldi | Mas'ul |
| Muddat oʻtdi | Mas'ul + rahbar + sex guruhi |
| STOP bosildi | Zakaz sotuvchisi |
| Zakaz keyingi bosqichga oʻtdi | Yangi bosqich mas'uli |
| Kunlik xulosa (09:00) | Rahbar |

- Har sexning oʻz Telegram guruhi bor (fasad guruhi, krovat guruhi va h.k.) —
  `workshop.telegram_chat_id` da saqlanadi.
- Ishchi bot xabarlarini **oʻchira olmaydi** (mute/bezzvuk imkoni berilmaydi).
- Har bir ishchining shaxsiy paneli: **"Mening vazifalarim"** — faol vazifalar,
  qolgan vaqt, jarima ballari.

---

## 9. "Vazifa buyurish" moduli (zakazdan mustaqil)

Rahbar istalgan xodimga oddiy vazifa beradi (zakaz jarayoniga bogʻliq emas).

Kategoriyalar (default 3 ta, sozlanadi):
1. **Ofis xodimlari**
2. **Fasad sex**
3. **Ustanovkachilar + svarshiklar**

Har bir vazifada: matn, mas'ul, muddat (sana + soat), kategoriya.
Muddat oʻtsa — xuddi shu jarima ball mantigʻi ishlaydi.
Xodim oʻz panelidan "Mening vazifalarim" ni koʻradi va "Bajardim" bosadi.

---

## 10. Admin va konfiguratsiya (SaaS uchun kritik)

Admin panelda (parol bilan himoyalangan, faqat egasi/rahbar):

- Sexlarni yaratish/oʻchirish
- Har bir sex uchun bosqichlarni **qoʻshish, oʻchirish, tartibini oʻzgartirish**
- Har bir bosqich uchun: SLA soati, kunlik norma, jarima ball qiymati, mas'ullar
- Foydalanuvchilar, rollar, rahbar-boʻysunuvchi bogʻlanishi
- Telegram guruh ID lari
- Tarif rejasi: bosqichlar soniga qarab (showroom = soddalashtirilgan versiya)

**Rollar:** `owner`, `admin`, `manager` (sex boshligʻi), `seller`, `worker`, `logistics`.

---

## 11. Dashboard va statistika

Rahbar uchun:
- Zakazlar voronkasi: qaysi bosqichda nechta zakaz turibdi
- Har bir xodim: bajarilgan / kechikkan / jarima ball / oʻrtacha bajarish vaqti
- Har bir bosqich: oʻrtacha davomiylik vs reja (bottleneck aniqlash)
- Kunlik norma bajarilishi: punkt soni va m²
- STOP statistikasi: nechta zakaz, qancha vaqt, sabablari
- Davr boʻyicha filtr, Excel'ga eksport

---

## 12. Ishlab chiqish fazalari

**Faza 1 — Poydevor**
- DB sxema + migratsiyalar (3-boʻlim)
- Sex/bosqich konfiguratsiyasi (seed: fasad sex shabloni)
- Order CRUD + bosqichdan bosqichga oʻtkazish API
- SLA engine: `due_at` hisoblash, overdue aniqlash
- Testlar

**Faza 2 — Telegram bot**
- Autentifikatsiya (telegram_id ↔ user)
- "Mening vazifalarim", "Bajardim" tugmasi
- Xabarnomalar servisi + scheduler (eslatma, overdue)
- Guruhga yuborish

**Faza 3 — STOP + jarima**
- StopLog, taymerni muzlatish
- Penalty engine
- Sotuvchiga STOP xabari

**Faza 4 — Web panel**
- Rahbar dashboard, statistika, eksport
- Admin konfiguratsiya UI

**Faza 5 — Trello adapter**
- Ikki tomonlama sinxronizatsiya, webhook qabul qilish

**Faza 6 — Multi-tenant / SaaS**
- Kompaniyalar ajratilishi, tariflar, onboarding

---

## 13. ⚠️ Ochiq savollar (agent oʻzi hal qilmasin — soʻrasin)

1. **`gip_lab`** nima aniq? (GIP tekshiruvi? Gibka? Boshqa nom?) — bosqich nomi tasdiqlansin.
2. Kunlik norma **5 punkt / 100 m²** qaysi bosqichga tegishli: chizishgami yoki ishlab chiqarishgami?
3. Bir bosqichda 2 mas'ul boʻlsa jarima **ikkalasigami** yoki bittasigami?
4. Jarima ballning aniq qiymati va u maoshga qanday taʼsir qiladi?
5. Ish vaqti hisobga olinadimi? (24 soat = kalendar soatmi yoki ish soatimi? Dam olish kunlari?)
6. `installation` (montaj) bosqichi uchun standart muddat necha kun?
7. Zavodlar soni: laminoks, eman, zavod-2 — bular alohida bosqichmi yoki bitta bosqichning variantlarimi?
8. Showroom versiyasida qaysi bosqichlar qoladi?
