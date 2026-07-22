import re
from datetime import datetime, timedelta, timezone

from utils.enums import Role

# Toshkent doim UTC+5 (yozgi vaqtga o'tmaydi) — xabarlarda mahalliy vaqt ko'rsatiladi.
TASHKENT_TZ = timezone(timedelta(hours=5))


def normalize_phone(raw: str | None) -> str:
    """Faqat raqamlarni qoldiradi, oxirgi 9 ta raqamni qaytaradi (O'zbekiston
    mahalliy raqam uzunligi) — +998/998/bo'shliq/tire farqidan qat'i nazar
    solishtirish uchun. Admin turli formatda kiritgan bo'lishi mumkin, Telegram
    kontakti esa o'z formatida keladi — ikkalasini ham shu bilan solishtiramiz."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-9:] if len(digits) >= 9 else digits

# Mini App (`miniapp/api/*.py`) va bildirishnomalarda ishlatiladigan rol
# nomlari — avval `keyboards/admin_kb.py`da edi (chat UI o'chirilgach shu
# yerga ko'chirildi, "umumiy ko'rsatish-logikasi" konvensiyasiga mos).
ROLE_LABELS: dict[Role, str] = {
    Role.WORKER: "👷 Ishchi",
    Role.BRIGADIER: "👨‍💼 Brigadir",
    Role.SUPERVISOR: "🕵️ Nazoratchi",
    Role.ADMIN: "👔 Rahbar/Admin",
    Role.OBSERVER: "👀 Kuzatuvchi",
    Role.SELLER: "💼 Sotuvchi",
}


def format_dt(value: datetime) -> str:
    return value.astimezone(TASHKENT_TZ).strftime("%d.%m.%Y %H:%M")
