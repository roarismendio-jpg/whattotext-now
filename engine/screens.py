"""Phone-native screens: Notes, chat, mail. Generic UI (not a copy of any brand's app).

All carousel slides are 1080x1350 (4:5). Reels use 1080x1920.
"""
from functools import lru_cache
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"

# palette
PAPER = "#FBFAF6"
INK = "#1C1C1E"
GRAY = "#8E8E93"
LIGHT = "#E9E9EB"
LINE = "#E3E1DA"
BLUE = "#0A84FF"
AMBER = "#D49B00"
RED = "#E5484D"
GREEN = "#2E9E5B"
HANDLE = "@whattotext.now"

# ---------------- device state (status bar) ----------------
# Every screen gets a real-looking status bar: a clock that fits the moment, a battery that
# isn't full. Set per post with set_device(p) so no two posts look like the same template.
DEVICE = {"clock": "11:42", "battery": 38, "date": "Today at 11:42 PM", "dark": False}


def set_device(p):
    import random as _r
    rng = _r.Random(sum(map(ord, p.get("id", "x"))) * 7919)
    stamps = [c.get("stamp", "") for c in p.get("context", []) if isinstance(c, dict)]
    stamps += [o.get("stamp", "") for o in p.get("script", []) if isinstance(o, dict)]
    m = None
    for st in stamps:
        m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", st or "", re.I) or m
    hm = re.search(r"\b(\d{1,2})\s*(am|pm)\b", p.get("hook", ""), re.I)
    if m:
        h12, mm, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        mm = min(59, mm + rng.randint(0, 3))
    elif hm:  # "the text to send at 2am" -> the phone says 2:xx
        h12, mm, ap = int(hm.group(1)), rng.randint(3, 47), hm.group(2).upper()
    else:
        night = p.get("theme") == "dark" or "night" in (p.get("cluster", "") + p.get("hook", "")).lower()
        h24 = rng.choice([23, 23, 0, 1, 22]) if night else rng.randint(8, 21)
        mm = rng.randint(0, 59)
        ap = "AM" if h24 < 12 else "PM"
        h12 = h24 % 12 or 12
    DEVICE["clock"] = f"{h12}:{mm:02d}"
    DEVICE["date"] = f"Today at {h12}:{mm:02d} {ap}"
    DEVICE["battery"] = rng.choice([rng.randint(9, 34), rng.randint(35, 88)])
    DEVICE["dark"] = p.get("theme") == "dark"
    return DEVICE


def status_bar(d, W, dark=None):
    dark = DEVICE["dark"] if dark is None else dark
    c = "white" if dark else INK
    f = font("SemiBold", 34)
    d.text((70, 18), DEVICE["clock"], font=f, fill=c)
    y = 40
    x = W - 262  # signal bars
    for i in range(4):
        h = 9 + i * 6
        d.rounded_rectangle((x + i * 13, y + 10 - h, x + i * 13 + 8, y + 10), radius=2, fill=c)
    cx, cy = W - 168, y + 10  # wifi: three arcs + dot
    for r in (24, 16, 8):
        d.arc((cx - r, cy - r - 2, cx + r, cy + r - 2), 225, 315, fill=c, width=5)
    b = DEVICE["battery"]
    bx, by = W - 124, y - 14  # battery
    d.rounded_rectangle((bx, by, bx + 54, by + 26), radius=7, outline=c if not dark else "#8E8E93", width=3)
    d.rounded_rectangle((bx + 57, by + 8, bx + 61, by + 18), radius=2, fill=c if not dark else "#8E8E93")
    fill = RED if b < 20 else c
    d.rounded_rectangle((bx + 5, by + 5, bx + 5 + max(4, int(44 * b / 100)), by + 21), radius=3, fill=fill)


@lru_cache(maxsize=64)
def font(weight: str, size: int):
    return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)


def wrap(draw, text, fnt, width):
    """Word-wrap respecting explicit newlines. Returns list of lines ('' = blank line)."""
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        lines, line = [], ""
        for word in para.split(" "):
            test = (line + " " + word).strip()
            if draw.textlength(test, font=fnt) <= width or not line:
                line = test
            else:
                lines.append(line)
                line = word
        lines.append(line)
        # avoid a one-word last line inside this paragraph
        if len(lines) >= 2 and " " not in lines[-1] and lines[-2].count(" ") >= 2:
            head, tail = lines[-2].rsplit(" ", 1)
            cand = tail + " " + lines[-1]
            if draw.textlength(cand, font=fnt) <= width:
                lines[-2], lines[-1] = head, cand
        out.extend(lines)
    return out


def fit_text(draw, text, weight, width, max_h, start, minimum, lh=1.32):
    size = start
    while size >= minimum:
        f = font(weight, size)
        lines = wrap(draw, text, f, width)
        h = len(lines) * int(size * lh)
        if h <= max_h:
            return f, lines, int(size * lh)
        size -= 2
    f = font(weight, minimum)
    return f, wrap(draw, text, f, width), int(minimum * lh)


def handle_mark(d, W, H, color=GRAY):
    f = font("Medium", 26)
    w = d.textlength(HANDLE, font=f)
    d.text(((W - w) / 2, H - 62), HANDLE, font=f, fill=color)


# ---------------- Notes ----------------

def notes_header(d, W, date_str=None):
    date_str = date_str or DEVICE["date"]
    status_bar(d, W, dark=False)
    d.text((54, 96), "‹ Notes", font=font("Regular", 38), fill=AMBER)
    # share + more icons (simple shapes)
    d.ellipse((W - 150, 100, W - 112, 138), outline=AMBER, width=4)
    for i in range(3):
        d.ellipse((W - 88 + i * 16, 116, W - 80 + i * 16, 124), fill=AMBER)
    f = font("Regular", 26)
    tw = d.textlength(date_str, font=f)
    d.text(((W - tw) / 2, 186), date_str, font=f, fill=GRAY)


def notes_title_slide(title, sub=None, W=1080, H=1350, date_str=None):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    notes_header(d, W, date_str)
    f, lines, lh = fit_text(d, title, "Bold", W - 140, H - 520, 92, 54, lh=1.18)
    y = 300
    for ln in lines:
        d.text((70, y), ln, font=f, fill=INK)
        y += lh
    if sub:
        y += 30
        d.text((70, y), sub, font=font("Regular", 38), fill=GRAY)
    handle_mark(d, W, H)
    return img


def notes_body_slide(heading, items, numbered=False, W=1080, H=1350, footer=None, date_str=None):
    """items: list of strings; rendered as a note with optional heading."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    notes_header(d, W, date_str)
    y = 230
    if heading:
        fh, hl, hlh = fit_text(d, heading, "Bold", W - 140, 260, 60, 44, lh=1.18)
        for ln in hl:
            d.text((70, y), ln, font=fh, fill=INK)
            y += hlh
        y += 30
    avail = H - y - (200 if footer else 140)
    size = 58
    while size >= 32:
        f = font("Regular", size)
        lh = int(size * 1.34)
        blocks = [wrap(d, it, f, W - 140 - 60) for it in items]
        total = sum(len(b) * lh for b in blocks) + (len(blocks) - 1) * int(size * 0.7)
        if total <= avail:
            break
        size -= 2
    for i, b in enumerate(blocks):
        marker = f"{i + 1}." if numbered else "–"
        d.text((70, y), marker, font=f, fill=AMBER if numbered else GRAY)
        for ln in b:
            d.text((130, y), ln, font=f, fill=INK)
            y += lh
        y += int(size * 0.7)
    if footer:
        ff = font("Regular", 26)
        for j, ln in enumerate(wrap(d, footer, ff, W - 140)):
            d.text((70, H - 190 + j * 34), ln, font=ff, fill=GRAY)
    handle_mark(d, W, H)
    return img


# ---------------- Chat ----------------

def chat_header(d, W, name, top=0, height=250):
    d.rectangle((0, top, W, top + height), fill="#F6F6F6")
    d.line((0, top + height, W, top + height), fill=LINE, width=2)
    status_bar(d, W, dark=False)
    d.text((40, top + 70), "‹", font=font("Regular", 72), fill=BLUE)
    cx = W // 2
    r = 52
    d.ellipse((cx - r, top + 50, cx + r, top + 50 + 2 * r), fill="#A7A9B0")
    initial = (name.strip()[:1] or "?").upper()
    fi = font("SemiBold", 48)
    iw = d.textlength(initial, font=fi)
    d.text((cx - iw / 2, top + 50 + r - 30), initial, font=fi, fill="white")
    fn = font("Regular", 30)
    nw = d.textlength(name + " ›", font=fn)
    d.text((cx - nw / 2, top + 168), name + " ›", font=fn, fill=INK)


def bubble(d, text, y, W, mine, size=44, maxw_ratio=0.74, sender=None, strike=False):
    f = font("Regular", size)
    maxw = int(W * maxw_ratio)
    pad_x, pad_y = 34, 24
    lines = wrap(d, text, f, maxw - 2 * pad_x)
    lh = int(size * 1.3)
    tw = max(d.textlength(ln, font=f) for ln in lines) if lines else 0
    bw = int(tw + 2 * pad_x)
    bh = int(len(lines) * lh + 2 * pad_y - (lh - size) * 0.6)
    if sender and not mine:
        d.text((70, y), sender, font=font("Regular", 26), fill=GRAY)
        y += 38
    x0 = W - 40 - bw if mine else 40
    fill = BLUE if mine else LIGHT
    d.rounded_rectangle((x0, y, x0 + bw, y + bh), radius=42, fill=fill)
    ty = y + pad_y - 4
    for ln in lines:
        d.text((x0 + pad_x, ty), ln, font=f, fill="white" if mine else INK)
        ty += lh
    if strike:
        d.line((x0 - 10, y + bh / 2, x0 + bw + 10, y + bh / 2), fill=RED, width=8)
    return y + bh, (x0, y, x0 + bw, y + bh)


def stamp(d, text, y, W):
    f = font("Regular", 26)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, y), text, font=f, fill=GRAY)
    return y + 54


def input_bar(d, W, y, placeholder="Message"):
    d.ellipse((34, y + 8, 94, y + 68), fill="#E5E5EA")
    d.text((52, y + 6), "+", font=font("Regular", 50), fill=GRAY)
    d.rounded_rectangle((112, y, W - 34, y + 76), radius=38, outline="#D1D1D6", width=3, fill="white")
    d.text((140, y + 18), placeholder, font=font("Regular", 34), fill="#B0B0B5")


def chat_slide(name, label, message, context=None, W=1080, H=1350, note=None, strike=False, tag=None, tag_color=None, size=52):
    """Conversation anchored above the input bar, like a real thread."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    chat_header(d, W, name)
    # measure on a scratch canvas, then draw bottom-anchored
    def layout(draw, y0, dry):
        y = y0
        if label:
            f = font("SemiBold", 28)
            t = label.upper()
            tw = draw.textlength(t, font=f) + 44
            if not dry:
                draw.rounded_rectangle(((W - tw) / 2, y, (W + tw) / 2, y + 54), radius=27, fill="#F2F2F7")
                draw.text(((W - tw) / 2 + 22, y + 11), t, font=f, fill=GRAY)
            y += 96
        for c in (context or []):
            if c.get("stamp"):
                y = stamp(draw, c["stamp"], y, W) if not dry else y + 54
            y, _ = bubble(draw, c["text"], y, W, c.get("from") == "me", sender=c.get("name"), size=size - 4)
            y += 24
        y += 8
        y, _ = bubble(draw, message, y, W, True, strike=strike, size=size)
        return y
    scratch = ImageDraw.Draw(Image.new("RGB", (W, H)))
    h = layout(scratch, 0, True)
    bottom = H - 200 - (90 if tag or not strike else 40) - (120 if note else 0)
    y0 = max(290, bottom - h)
    y = layout(d, y0, False)
    if tag:
        f = font("Bold", 30)
        tw = d.textlength(tag, font=f) + 40
        d.rounded_rectangle((W - 40 - tw, y + 16, W - 40, y + 70), radius=27, fill=tag_color or GREEN)
        d.text((W - 40 - tw + 20, y + 26), tag, font=f, fill="white")
    elif not strike:
        f = font("Regular", 24)
        d.text((W - 40 - d.textlength("Delivered", font=f), y + 10), "Delivered", font=f, fill=GRAY)
    if note:
        fn = font("Regular", 28)
        for j, ln in enumerate(wrap(d, note, fn, W - 160)):
            d.text((80, H - 300 + j * 38), ln, font=fn, fill=GRAY)
    input_bar(d, W, H - 170)
    f = font("Medium", 24)
    d.text(((W - d.textlength(HANDLE, font=f)) / 2, H - 70), HANDLE, font=f, fill="#C7C7CC")
    return img


# ---------------- Mail ----------------

def mail_slide(label, subject, body, W=1080, H=1350, to="professor"):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 170), fill="#F6F6F6")
    status_bar(d, W, dark=False)
    d.text((44, 86), "Cancel", font=font("Regular", 36), fill=BLUE)
    f = font("SemiBold", 38)
    t = "New Message"
    d.text(((W - d.textlength(t, font=f)) / 2, 84), t, font=f, fill=INK)
    d.ellipse((W - 104, 80, W - 46, 138), fill=BLUE)
    d.polygon([(W - 75, 94), (W - 90, 112), (W - 60, 112)], fill="white")
    d.line((W - 75, 108, W - 75, 126), fill="white", width=6)
    y = 190
    if label:
        fl = font("SemiBold", 26)
        tl = label.upper()
        tw = d.textlength(tl, font=fl) + 40
        d.rounded_rectangle((44, y, 44 + tw, y + 50), radius=25, fill="#F2F2F7")
        d.text((64, y + 10), tl, font=fl, fill=GRAY)
        y += 74
    for k, v in (("To:", to), ("Subject:", subject)):
        d.text((44, y + 18), k, font=font("Regular", 34), fill=GRAY)
        d.text((44 + d.textlength(k + " ", font=font("Regular", 34)), y + 18), v, font=font("Regular", 34), fill=INK)
        y += 84
        d.line((44, y, W, y), fill=LINE, width=2)
    y += 36
    fb, lines, lh = fit_text(d, body, "Regular", W - 100, H - y - 120, 42, 30, lh=1.38)
    for ln in lines:
        d.text((44, y), ln, font=fb, fill=INK)
        y += lh
    handle_mark(d, W, H)
    return img


# ---------------- Number ----------------

def number_slide(number, stat, source, W=1080, H=1350):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    notes_header(d, W)
    fnum = font("Bold", 260 if len(number) <= 4 else 190)
    d.text((64, 300), number, font=fnum, fill=AMBER)
    y = 300 + int(fnum.size * 1.12)
    f, lines, lh = fit_text(d, stat, "SemiBold", W - 140, 380, 62, 40, lh=1.2)
    for ln in lines:
        d.text((70, y), ln, font=f, fill=INK)
        y += lh
    fs = font("Regular", 28)
    d.text((70, H - 170), "source: " + source, font=fs, fill=GRAY)
    handle_mark(d, W, H)
    return img
