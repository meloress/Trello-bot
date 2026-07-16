# Trello + Telegram bot + Web boshqaruv paneli

Mebel ishlab chiqarish korxonasi uchun ishlab chiqarish, nazorat, KPI va sotuvni boshqarish tizimi.
To'liq talablar: [Trello_Telegram_TZ_v2.1_ToLiq.docx](../Trello_Telegram_TZ_v2.1_ToLiq.docx)

## Tuzilma

- `bot/` — Python + aiogram: Telegram bot va backend server (Trello sync, taymerlar, KPI/jarima hisob-kitobi, scheduler)
- `web/` — Node.js: Admin/Rahbar boshqaruv paneli
- `shared/` — ikkala servis ham tayanadigan umumiy baza sxemasi hujjati

Ikkala servis bitta PostgreSQL bazasini (`DATABASE_URL`) ulashadi. Baza migratsiyalarini
**faqat `bot/` (Alembic)** boshqaradi — `web/` faqat mavjud sxema ustida o'qish/yozish qiladi.

## Ishga tushirish

### Bot
```
cd bot
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
alembic upgrade head
python main.py
```

VS Code interpretatori `.vscode/settings.json` orqali `bot/.venv`ga avtomatik ishora qiladi.

### Web panel
```
cd web
npm install
npm start
```

`.env.example` asosida `.env` faylini to'ldiring.
