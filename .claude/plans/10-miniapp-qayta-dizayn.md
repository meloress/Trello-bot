# Mini App vizual qayta dizayni — premium-minimal, indigo urg'u

Holat: **YO'NALISH TASDIQLANGAN (2026-07-28), amalga oshirish hali BOSHLANMAGAN.**
Bu TZ talabi emas — foydalanuvchining "hozirgi dizayn juda jiddiy/korporativ,
kreativroq/zamonaviyroq/animatsiyali bo'lsin" so'rovi asosidagi vizual
qayta ko'rish. Barcha rol (Ishchi/Brigadir/Rahbar/Sotuvchi) va ikkala modul
(mebel/fasad_sex) qamraladi — bu **faqat taqdimot/CSS/animatsiya** ishi,
hech qanday `services/`, `miniapp/api/*.py`, yoki business-logika o'zgarmaydi.

## Kelib chiqishi

Figma bu sessiyada avtorizatsiya qilinmagani sabab (`plugin:figma:figma`
MCP ulanmagan), yo'nalish o'rniga interaktiv HTML maket (Claude Artifact)
orqali ko'rsatildi va tasdiqlandi:
`https://claude.ai/code/artifact/fa40dec0-8c6e-439f-bc67-101928f69156`
(vaqtinchalik scratchpad faylidan nashr qilingan — **bu hujjat** endi
yo'nalishning doimiy manbasi, chunki artifact manba fayli sessiyadan keyin
saqlanmaydi). Foydalanuvchi tanlagan yo'nalish:

- Umumiy uslub: **Premium-minimal, nafis mikro-animatsiyalar** (Apple/Linear
  uslubi) — "Qorong'i/neon-gradient (bold)" va "Yorqin/o'ynoqi (playful)"
  variantlaridan tanlab olingan.
- Urg'u rang: **Zamonaviy indigo/binafsha-ko'k** ("Yashilni saqlash" va
  "Issiq amber" variantlaridan tanlab olingan) — hozirgi zaytun-yashil
  (`--accent: #2f6f62`) o'rnini bosadi.
- Qamrov: **barcha rol, asosiy ekranlar to'liq to'plami** birinchi bosqichda
  (keyin qolgan ekranlarga kengaytiriladi).

## Dizayn tizimi (artifact'dan olingan aniq qiymatlar)

### Ranglar (light)
```
--bg: #f4f4f9;            --bg-tint: #ecebf7;
--surface: #ffffff;        --surface-sunken: #edecf5;
--ink: #15151f;            --ink-soft: #63616f;   --ink-faint: #9997a3;
--line: #e3e1ec;           --line-strong: #cfccdd;
--accent: #4f3ff0;         --accent-strong: #3a2ccb;
--accent-soft: #ece9fd;    --accent-glow: rgba(79,63,240,.28);  --accent-ink: #ffffff;
--positive: #158f5c;       --positive-bg: #e3f5ec;
--warning: #a8690a;        --warning-bg: #f8ecd6;
--critical: #d63356;       --critical-bg: #fbe6ec;
```
### Ranglar (dark)
```
--bg: #0b0b12;             --bg-tint: #111018;
--surface: #16151f;        --surface-sunken: #1d1c28;
--ink: #edecf5;            --ink-soft: #a5a2b5;   --ink-faint: #6d6a7d;
--line: #29283a;           --line-strong: #37354a;
--accent: #8676ff;         --accent-strong: #a89bff;
--accent-soft: #241f45;    --accent-glow: rgba(134,118,255,.35);
--positive: #3fcf8e;       --positive-bg: #0f2a20;
--warning: #e2ab53;        --warning-bg: #332512;
--critical: #ff7691;       --critical-bg: #34141c;
```
Semantik ranglar (`--positive`/`--warning`/`--critical`) urg'u rangidan
QASDDAN mustaqil — CLAUDE.md'dagi "Gotchas"da eslatilgan colorblind-safe
tekshiruvni (`dataviz` skill'ining `validate_palette.js`) haqiqiy
implementatsiyada QAYTA ishga tushirish kerak, chunki bu aniq qiymatlar
mockup uchun tanlangan, rasmiy validatsiyadan hali o'tmagan.

### Tipografiya
Tashqi shrift YO'Q (Artifact CSP CDN'ni bloklaydi, real Mini App'da ham
shrift yuklash infratuzilmasi yo'q) — `-apple-system, "SF Pro Text",
"Segoe UI", system-ui, sans-serif` tizim shrifti saqlanadi, lekin kuchli
tip-shkala bilan: sarlavhalar `font-weight:800`, `letter-spacing:-0.02em`;
raqamlar (`--font-mono`, tabular-nums) og'irroq vazn bilan ajratiladi.
Bu — Telegram WebView uchun ataylab qilingan amaliy tanlov (tezkor, native
hissi), zamonaviylik rang/animatsiya/ikonka orqali keladi, shrift orqali emas.

### Ikon tizimi
Hozirgi emoji-ikonkalar (📦🏠💰🗂️📸🔁⏳📋👥📊👤🛑✅▶️➕💾 va h.k. — `app.js`
bo'ylab o'nlab joyda) chiziq-uslubidagi (stroke, 24×24, currentColor) inline
SVG ikonlar bilan almashtiriladi. To'liq ro'yxat va tayyor SVG path'lar
artifact manbasida (`ic-home`, `ic-box`, `ic-list`, `ic-clock`, `ic-user`,
`ic-users`, `ic-chart`, `ic-phone`, `ic-chevron-r/l`, `ic-check`, `ic-pause`,
`ic-play`, `ic-alert`, `ic-plus`, `ic-inbox`, `ic-trend`, `ic-edit`) — bu
hujjatga ko'chirilmadi (uzun), implementatsiya boshlanganda artifact
sahifasidan (`WebFetch` orqali) yoki quyidagi "Amalga oshirish tartibi"dagi
3-bosqichda qayta yaratiladi.

### Animatsiya prinsiplari
- **Kartochkalar ketma-ket paydo bo'ladi** (`stagger`): `animation: fadeUp
  .5s cubic-bezier(.22,1,.36,1) both; animation-delay: calc(var(--i)*55ms)`
  — har elementga inline `style="--i:N"`.
- **Raqamlar sanaladi** (hero-tile'lar, ball): `requestAnimationFrame` bilan
  ~650ms cubic ease-out, `prefers-reduced-motion: reduce` bo'lsa o'tkazib
  yuboriladi (darhol yakuniy qiymat ko'rsatiladi).
- **Tab-bar va rol-almashtirgichda sirg'anuvchi pill**: aktiv tugma ustida
  joylashgan `position:absolute` fon, `transform`/`width` orqali
  `.4s cubic-bezier(.22,1,.36,1)` bilan animatsiyalanadi (`offsetLeft`/
  `offsetWidth` o'lchab joylashtiriladi, oyna o'lchami o'zgarsa qayta
  hisoblanadi).
- **Ekranlar orasida slide-o'tish**: oldinga navigatsiya — o'ngdan kirish,
  orqaga — chapdan kirish, tab almashtirish — fade. Barchasi CSS
  `@keyframes` + JS'da klass qo'shish orqali (`enter-fwd`/`enter-back`/
  `enter-fade`).
- Hammasi `@media (prefers-reduced-motion: reduce)` ostida o'chiriladi.

### Komponent naqshlari (deyarli 1:1 hozirgi `app.css` klasslariga mos)
Mockup ataylab hozirgi klass nomlarini takrorladi — bu amalga oshirish
**qayta yozish emas, TOKEN/QOIDA almashtirish** ekanini bildiradi:
`nav-card`, `task-card`, `hero-tile`, `status-pill`, `member-card`, `panel`,
`kv-row`, `segmented`, `tab-item`, `alert-card`, `profile-head`,
`avatar`/`avatar-lg` — bularning barchasi joriy `app.css`da allaqachon bor,
faqat rang/radius/soya/animatsiya qoidalari yangilanadi. Yangi qo'shiladigan
narsalar: `.role-pill-bg`/`.tab-pill-bg` (sirg'anuvchi indikator), `.stagger`
klassi, `.stage-track`/`.stage-dot` (sotuvchi lid-bosqich progressi —
hozirgi appda yo'q, yangi komponent), ikon-sprite (`<svg><defs>` bloki,
`index.html`ga bir marta qo'shiladi).

## Amalga oshirish tartibi (bosqichma-bosqich, xavfni kamaytirish uchun)

Bitta katta PR o'rniga, xavfsizroq: **1-bosqich butun ilovaga tegadi
(faqat token/rang), 2-3-bosqich ekran-ekran kengaytiriladi.**

1. **Token/rang almashtirish** (`bot/miniapp/public/css/app.css`) — faqat
   `:root`/`@media (prefers-color-scheme)`/`[data-theme]` bloklarini
   yuqoridagi qiymatlarga almashtirish + mavjud komponent qoidalariga
   yangi radius/soya/o'tish (`transition`) qo'shish. Hech qanday HTML/JS
   o'zgarmaydi — shu bosqichning o'zi butun ilovani (barcha rol, ikkala
   modul) darhol zamonaviylashtiradi, chunki har bir ekran shu tokenlardan
   foydalanadi.
2. **Animatsiya qatlami** (`bot/miniapp/public/js/app.js`) — umumiy
   yordamchi funksiyalar qo'shiladi: `animateCountUp(el)`, ekran
   render'lariga `stagger` klassini qo'yish (mavjud `setScreen()` chaqiruv
   naqshini o'zgartirmasdan, faqat generatsiya qilingan HTML'ga
   `class="... stagger" style="--i:N"` qo'shish), tab-bar/rol-almashtirgich
   uchun sirg'anuvchi pill (`renderTabBar()`ga qo'shimcha).
3. **Ikon tizimi** — SVG sprite `index.html`ga qo'shiladi, so'ng
   rol-rol emoji ikonlar almashtiriladi (Ishchi → Brigadir → Rahbar →
   Sotuvchi tartibida, har biri alohida tekshirib commit qilinadi — eng
   mexanik, eng ko'p qator o'zgaradigan qism).

Har bosqich alohida commit/tekshiruv — 1-bosqichdan keyin allaqachon
foydalanuvchi ko'rgan yo'nalishning katta qismi jonli bo'ladi.

## Tekshirish rejasi

Bu servis/DB o'zgarishi emas (avtomatlashtirilgan test yo'q, kerak ham
emas) — CLAUDE.md'ning UI-o'zgarish qoidasiga ko'ra: `run` skill orqali
botni lokal ishga tushirib, real Telegram WebView (yoki brauzerda
`MINIAPP_BASE_URL`) orqali kamida bitta ekranni har rol uchun (Ishchi,
Brigadir, Rahbar, Sotuvchi) HAM yorug', HAM qorong'i temada ko'rish, va
mavjud funksionallik (tugmalar, forma, MainButton, orqaga navigatsiya)
hali ishlashini tasdiqlash — bu faqat taqdimot qatlami, lekin CSS
qoidalaridagi xato (masalan `[hidden]` ustidan `display` yozib yuborish —
mockup'ni tuzatishda topilgan haqiqiy xato, xuddi shunga o'xshash boshqa
joylar bo'lishi mumkin) funksional regressiyaga olib kelishi mumkin.

## Tugagach

- `shared/db-schema.md`ga o'zgarish kerak emas (sxema tegilmaydi).
- `CLAUDE.md`dagi "Mini App... Frontend" bo'limiga qisqa yangilanish
  qo'shiladi (yangi token qiymatlari + ikon tizimi eslatib o'tiladi).
- Ushbu hujjat `.claude/plans/`dan olib tashlanadi, README'dagi qator ham.
