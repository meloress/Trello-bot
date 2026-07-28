"""Bazaning to'liq zaxira nusxasi (JSON). FAQAT O'QIYDI — hech narsani o'zgartirmaydi.

Ishlatish:
    .venv/Scripts/python _backup_db.py            -> bot/_backups/db_YYYYmmdd_HHMMSS.json

Har qanday ommaviy o'chirish/tozalashdan OLDIN ishga tushiring. Fayl barcha
jadvallardagi barcha qatorlarni saqlaydi, shuning uchun keyin qайta tiklash
mumkin (`_restore_db.py` yo'q — kerak bo'lsa JSON'dan qo'lda INSERT qilinadi,
lekin muhimi: ma'lumot YO'QOLMAYDI).
"""

import asyncio
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.database import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "_backups"


def _encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


async def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"db_{stamp}.json"

    dump: dict[str, list[dict]] = {}
    async with async_session() as session:
        tables = [r[0] for r in (await session.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))).all()]

        for table in tables:
            rows = (await session.execute(text(f'SELECT * FROM "{table}"'))).mappings().all()
            dump[table] = [dict(r) for r in rows]
            print(f"  {table:<28} {len(rows):>6} qator")

    out_path.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=_encode), encoding="utf-8")
    total = sum(len(v) for v in dump.values())
    print(f"\nZaxira saqlandi: {out_path}")
    print(f"Jami {total} qator, {len(dump)} jadval, {out_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    asyncio.run(main())
