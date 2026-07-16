from datetime import datetime, timedelta, timezone

# Toshkent doim UTC+5 (yozgi vaqtga o'tmaydi) — xabarlarda mahalliy vaqt ko'rsatiladi.
TASHKENT_TZ = timezone(timedelta(hours=5))


def format_dt(value: datetime) -> str:
    return value.astimezone(TASHKENT_TZ).strftime("%d.%m.%Y %H:%M")
