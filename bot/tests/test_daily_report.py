"""Kunlik hisobot jadvali (Trello + checklist ustunlari, telefonga sig'adigan) — bazasiz."""
import html
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.stats_service import DailyRow, format_daily_report, short_name

assert short_name("Jasur") == "Jasur"
assert short_name("Habibulla Yusupkho'jayev") == "Habibulla Y."
assert short_name("Xotam aka haydovchi") == "Xotam aka h."
assert short_name("Yusupkhojayev Jamshid") == "Yusupkhojayev"
assert short_name("Muruvatullayev Abdulloh") == "Muruvatullay…"

rows = [
    DailyRow("Ali <a>", 2, -1.5, -3, 3, 1, 0.7, True, -0.7, penalties=1),
    DailyRow("Vali", 0, 0, 0, None, 0, 0, False, 0),
    DailyRow("Habibulla Yusupkho'jayev", 1, 2, 2, 3, 3, 0, True, 0),
]
t = format_daily_report(date(2026, 11, 14), rows)
pre = t[t.index("<pre>") + 5:t.index("</pre>")].split("\n")
assert pre[0].split() == ["Xodim", "Baj", "Ball", "Jar", "Chek", "ChB"], pre[0]  # checklist — Jarimadan keyin
assert max(len(html.unescape(ln)) for ln in pre) <= 40  # telefonda o'ralmaydi
assert pre[2].split() == ["Habibulla", "Y.", "1", "2", "0", "3/3", "0"], pre[2]  # eng yaxshi tepada
assert pre[3].split() == ["Vali", "0", "0", "0", "—", "—"], pre[3]
assert pre[4].split() == ["Ali", "&lt;a&gt;", "2", "-1,5", "1", "1/3", "-0,7"], pre[4]  # HTML escape
assert "to'liq javob 1/2, jarima -0,7" in t and "14.11.2026" in t
print("test_daily_report: OK")
