"""Zakaz holati rasmi (foydalanuvchi tasdiqlagan ko'rinish, 2026-11-06):
sarlavha, holat banneri, bosqichlar chizig'i, PLAN/REAL/FARQ jadvali.
Ma'lumot `order_template.order_view()` dan; bu modul faqat chizadi.
Shrift loyiha ichida (DejaVu Sans — kirill va o'zbek lotini bor), Railway'da
tizim shrifti yo'q."""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from utils.formatters import fmt_ball

S = 2  # telefon ekranida tiniq bo'lishi uchun 2x
W = 1080
_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
INK, SOFT, LINE, GREY, BLUE = "#202124", "#5f6368", "#dadce0", "#bdc1c6", "#1967d2"
TONE = {"red": ("#c5221f", "#fce8e6"), "green": ("#137333", "#e6f4ea"), "amber": ("#b06000", "#fef7e0"),
        "blue": ("#1967d2", "#e8f0fe"), "grey": ("#80868b", "#f1f3f4")}


@lru_cache(maxsize=None)
def font(size, bold=False):
    return ImageFont.truetype(str(_FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size * S)


def P(*xs):
    return [v * S for v in xs]


def _clean(text) -> str:
    return "".join(ch for ch in str(text or "") if ord(ch) <= 0xFFFF)  # emoji shriftda yo'q — kvadrat chiqmasin


def _fit(g, text, f, width) -> str:
    text = _clean(text)
    if g.textlength(text, font=f) / S <= width:
        return text
    while text and g.textlength(text + "…", font=f) / S > width:
        text = text[:-1]
    return text + "…"


def draw(model: dict) -> bytes:
    img = Image.new("RGB", (W * S, 1500 * S), "white")
    g = ImageDraw.Draw(img)
    x0, x1 = 24, W - 24

    g.rectangle(P(0, 0, W, 92), fill="#1f2a44")
    g.text(P(x0, 16), _fit(g, model["title"], font(23, True), x1 - x0), font=font(23, True), fill="white")
    g.text(P(x0, 54), _fit(g, model["subtitle"], font(16), x1 - x0), font=font(16), fill="#c9d1e3")
    y = 108

    word, line2, right_small, right_big, tone = model["banner"]
    fg, bg = TONE[tone]
    g.rounded_rectangle(P(x0, y, x1, y + 108), 14 * S, fill=bg)
    g.rounded_rectangle(P(x0, y, x0 + 12, y + 108), 6 * S, fill=fg)
    right_w = max(g.textlength(right_small, font=font(16)), g.textlength(right_big, font=font(34, True))) / S
    left_w = x1 - 24 - right_w - 24 - (x0 + 32)
    g.text(P(x0 + 32, y + 14), _fit(g, word, font(32, True), left_w), font=font(32, True), fill=fg)
    g.text(P(x0 + 32, y + 62), _fit(g, line2, font(19, True), left_w), font=font(19, True), fill=INK)
    g.text(P(x1 - 24, y + 18), right_small, font=font(16), fill=SOFT, anchor="ra")
    g.text(P(x1 - 24, y + 42), right_big, font=font(34, True), fill=fg, anchor="ra")
    y += 108 + 26

    steps = model["steps"]
    n = len(steps)
    left, right = x0 + 56, x1 - 56
    cy = y + 30
    xs = [left + i * (right - left) / (n - 1) for i in range(n)]
    for i in range(n - 1):
        col = TONE["green"][0] if steps[i + 1][1] != "todo" else GREY
        g.line(P(xs[i], cy, xs[i + 1], cy), fill=col, width=6 * S)
    for (label, state, sub), cx in zip(steps, xs):
        r = 22
        if state == "done":
            g.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=TONE["green"][0])
            g.line(P(cx - 10, cy + 1, cx - 3, cy + 9), fill="white", width=4 * S)
            g.line(P(cx - 3, cy + 9, cx + 11, cy - 8), fill="white", width=4 * S)
        elif state == "run":
            g.ellipse(P(cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6), fill=TONE["blue"][1])
            g.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=BLUE)
            g.ellipse(P(cx - 7, cy - 7, cx + 7, cy + 7), fill="white")
        elif state == "stop":
            g.ellipse(P(cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6), fill=TONE["amber"][1])
            g.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=TONE["amber"][0])
            g.rectangle(P(cx - 8, cy - 9, cx - 3, cy + 9), fill="white")
            g.rectangle(P(cx + 3, cy - 9, cx + 8, cy + 9), fill="white")
        else:
            g.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill="white", outline=GREY, width=4 * S)
        sub_col = {"done": TONE["green"][0], "run": BLUE, "stop": TONE["amber"][0], "todo": SOFT}[state]
        g.text(P(cx, cy + 36), label, font=font(16, True), fill=SOFT if state == "todo" else INK, anchor="ma")
        g.text(P(cx, cy + 60), _fit(g, sub, font(13), (right - left) / (n - 1) - 8), font=font(13), fill=sub_col,
               anchor="ma")
    y = cy + 96

    cols = [("BOSQICH", 160), ("PLAN", 190), ("REAL", 290), ("FARQ", 180), ("BALL", x1 - x0 - 820)]
    g.rectangle(P(x0, y, x1, y + 40), fill="#f1f3f4")
    cx = x0
    for name, w in cols:
        g.text(P(cx + 16, y + 12), name, font=font(14, True), fill=SOFT)
        cx += w
    top = y
    y += 40
    rows = model["rows"]
    for i, (stage, plan, real, who, diff, ball) in enumerate(rows):
        cx = x0
        g.text(P(cx + 16, y + 20), stage, font=font(17, True), fill=INK)
        cx += cols[0][1]
        g.text(P(cx + 16, y + 21), plan, font=font(16), fill=SOFT)
        cx += cols[1][1]
        if who:
            g.text(P(cx + 16, y + 10), real, font=font(16, True), fill=SOFT if real == "—" else INK)
            g.text(P(cx + 16, y + 36), _fit(g, who, font(13, True), cols[2][1] - 24), font=font(13, True), fill=BLUE)
        else:
            g.text(P(cx + 16, y + 21), real, font=font(16, True), fill=SOFT if real == "—" else INK)
        cx += cols[2][1]
        if diff:
            dfg, dbg = TONE[diff[1]]
            tw = g.textlength(diff[0], font=font(15, True)) / S
            g.rounded_rectangle(P(cx + 14, y + 15, cx + 38 + tw, y + 49), 17 * S, fill=dbg)
            g.text(P(cx + 26, y + 23), diff[0], font=font(15, True), fill=dfg)
        else:
            g.text(P(cx + 16, y + 21), "—", font=font(16), fill=SOFT)
        cx += cols[3][1]
        # BALL: botning soatbay jarimasi; oxirgi qator (Topshirish) — zakaz bo'yicha jami
        tone = TONE["red"][0] if ball < 0 else TONE["green"][0] if ball > 0 else SOFT
        text = ("Jami " if i == len(rows) - 1 else "") + fmt_ball(ball).replace("-", "−")
        g.text(P(cx + 16, y + 21), text, font=font(17, True), fill=tone)
        y += 64
        g.line(P(x0, y, x1, y), fill=LINE, width=S)
    g.rectangle(P(x0, top, x1, y), outline=LINE, width=S)
    y += 14
    if model["stop"]:
        fg, bg = TONE["amber"]
        g.rounded_rectangle(P(x0, y, x1, y + 48), 10 * S, fill=bg)
        g.text(P(x0 + 18, y + 14), _fit(g, model["stop"], font(16, True), x1 - x0 - 36), font=font(16, True), fill=fg)
        y += 48 + 14
    g.text(P(x0, y), _fit(g, model["footer"], font(13), x1 - x0), font=font(13), fill=SOFT)
    y += 34
    buf = io.BytesIO()
    img.crop((0, 0, W * S, y * S)).save(buf, "PNG", optimize=True)
    return buf.getvalue()
