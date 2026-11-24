"""Typing reels and thread reels.

A chat screen where a message gets typed with real hesitation (a first draft typed, paused
over, deleted), then sent. Thread reels continue: the other person types ("…"), replies,
days pass, the conversation moves. 1080x1920, 30fps, original synthesized sound
(keyboard clicks, send swoosh, receive tick): no music licensing needed.

Script ops (list, in order):
  {"t": "text"}                 type text
  {"p": 0.8}                    pause (seconds)
  {"d": 12}                     backspace n chars
  {"send": true}                send what's in the compose box
  {"them": "text"}              other person types (dots) then their bubble appears
  {"stamp": "Thursday 9:14 PM"} time label in the thread (use to show days passing)

Spec options:
  "theme": "light" | "dark"     dark = late-night look (good for night topics)
  "start_mid": true             open mid-sentence (first typed op pre-filled, hook hold 0.3s)
  "hook_hold": 1.6              seconds before typing starts (default 1.6)
"""
import random
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import screens as S

W, H, FPS = 1080, 1920, 30
SR = 44100
KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]

THEMES = {
    "light": dict(bg="white", header="#F6F6F6", line="#E3E1DA", text=S.INK, sub=S.GRAY, them_bub="#E9E9EB",
                  them_txt=S.INK, me_bub=S.BLUE, kb="#D1D3D9", key="white", key_txt=S.INK, key_dn="#B5B8BF",
                  key_fn="#ADB1B9", field="white", field_line="#D1D1D6", ph="#B0B0B5", hook_bg="white",
                  hook_txt=S.INK, hook_line="#E5E5EA", avatar="#A7A9B0"),
    "dark": dict(bg="black", header="#161618", line="#2C2C2E", text="#F2F2F7", sub="#8E8E93", them_bub="#262629",
                 them_txt="#F2F2F7", me_bub=S.BLUE, kb="#2B2B2D", key="#5A5A5E", key_txt="white", key_dn="#3A3A3C",
                 key_fn="#3F3F42", field="#1C1C1E", field_line="#3A3A3C", ph="#6E6E73", hook_bg="white",
                 hook_txt=S.INK, hook_line="#E5E5EA", avatar="#5F6066"),
}


# ---------- timeline ----------

def build_timeline(p, seed):
    """Events: (t, kind, payload). kinds: prefill, key, del, send, dots_on, them, stamp."""
    rnd = random.Random(seed)
    script = p["script"]
    start_mid = p.get("start_mid", False)
    t = 0.3 if start_mid else float(p.get("hook_hold", 1.6))
    text, ev = "", []
    first_type_done = False
    for op in script:
        if "t" in op:
            if start_mid and not first_type_done:
                text += op["t"]
                ev.append((0.0, "prefill", text))
                first_type_done = True
                continue
            first_type_done = True
            for ch in op["t"]:
                text += ch
                ev.append((t, "key", (text, ch)))
                base = rnd.uniform(0.035, 0.07)
                if ch == " ":
                    base += rnd.uniform(0.01, 0.03)
                if ch in ".,?!":
                    base += rnd.uniform(0.08, 0.15)
                t += base
        elif "p" in op:
            t += op["p"]
        elif "d" in op:
            for i in range(op["d"]):
                text = text[:-1]
                ev.append((t, "del", text))
                t += 0.09 if i < 3 else 0.035
        elif op.get("send"):
            ev.append((t, "send", text))
            text = ""
            t += 0.5
        elif "them" in op:
            ev.append((t, "dots_on", None))
            t += min(2.2, 0.9 + len(op["them"]) * 0.012)
            ev.append((t, "them", op["them"]))
            t += 0.4 + len(op["them"]) * 0.03  # reading time
        elif "stamp" in op:
            ev.append((t, "stamp", op["stamp"]))
            t += 0.6
    total = t + 2.2
    return ev, total


def final_messages(p):
    """Text of every message sent by 'me' (for checks)."""
    ev, _ = build_timeline(p, 1)
    return [e[2] for e in ev if e[1] == "send"]


# ---------- drawing ----------

def draw_header(d, th, name):
    d.rectangle((0, 0, W, 250), fill=th["header"])
    d.line((0, 250, W, 250), fill=th["line"], width=2)
    d.text((40, 70), "‹", font=S.font("Regular", 72), fill=S.BLUE)
    cx, r = W // 2, 52
    d.ellipse((cx - r, 50, cx + r, 50 + 2 * r), fill=th["avatar"])
    ini = (name.strip()[:1] or "?").upper()
    fi = S.font("SemiBold", 48)
    d.text((cx - d.textlength(ini, font=fi) / 2, 50 + r - 30), ini, font=fi, fill="white")
    fn = S.font("Regular", 30)
    d.text((cx - d.textlength(name + " ›", font=fn) / 2, 168), name + " ›", font=fn, fill=th["text"])


def bubble(d, th, text, y, mine, size=44, sender=None, dry=False):
    f = S.font("Regular", size)
    maxw = int(W * 0.74)
    px, py = 34, 24
    lines = S.wrap(d, text, f, maxw - 2 * px)
    lh = int(size * 1.3)
    bw = int(max(d.textlength(ln, font=f) for ln in lines) + 2 * px)
    bh = int(len(lines) * lh + 2 * py - (lh - size) * 0.6)
    if sender and not mine:
        if not dry:
            d.text((70, y), sender, font=S.font("Regular", 26), fill=th["sub"])
        y += 38
    x0 = W - 40 - bw if mine else 40
    if not dry:
        d.rounded_rectangle((x0, y, x0 + bw, y + bh), radius=42, fill=th["me_bub"] if mine else th["them_bub"])
        ty = y + py - 4
        for ln in lines:
            d.text((x0 + px, ty), ln, font=f, fill="white" if mine else th["them_txt"])
            ty += lh
    return y + bh


def dots_bubble(d, th, y, t, dry=False):
    bw, bh = 150, 92
    if not dry:
        d.rounded_rectangle((40, y, 40 + bw, y + bh), radius=42, fill=th["them_bub"])
        for i in range(3):
            phase = (t * 3 - i * 0.33) % 1
            a = 0.35 + 0.65 * (1 - abs(phase - 0.5) * 2)
            col = tuple(int(c * a + bc * (1 - a)) for c, bc in zip((142, 142, 147), (233, 233, 235) if th is THEMES["light"] else (38, 38, 41)))
            cx = 40 + 42 + i * 33
            d.ellipse((cx - 11, y + bh / 2 - 11, cx + 11, y + bh / 2 + 11), fill=col)
    return y + bh


def stamp(d, th, text, y, dry=False):
    if not dry:
        f = S.font("Regular", 26)
        d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=th["sub"])
    return y + 54


def draw_keyboard(d, th, top, pressed=None):
    d.rectangle((0, top, W, H), fill=th["kb"])
    kw, kh, gap = 92, 128, 14
    y = top + 24
    f = S.font("Regular", 48)
    for row in KEY_ROWS:
        x = (W - (len(row) * kw + (len(row) - 1) * gap)) / 2
        for ch in row:
            d.rounded_rectangle((x, y, x + kw, y + kh), radius=12, fill=th["key_dn"] if pressed == ch else th["key"])
            d.text((x + kw / 2 - d.textlength(ch, font=f) / 2, y + 30), ch, font=f, fill=th["key_txt"])
            x += kw + gap
        y += kh + 24
    d.rounded_rectangle((250, y, W - 250, y + kh), radius=12, fill=th["key_dn"] if pressed == " " else th["key"])
    d.rounded_rectangle((40, y, 230, y + kh), radius=12, fill=th["key_fn"])
    d.rounded_rectangle((W - 230, y, W - 40, y + kh), radius=12, fill=th["key_fn"])


def compose(d, th, text, kb_top, cursor_on, dry=False, size=46):
    f = S.font("Regular", size)
    lines = S.wrap(d, text, f, W - 112 - 34 - 150) if text else [""]
    lh = int(size * 1.28)
    h = max(84, len(lines) * lh + 30)
    y1 = kb_top - 26
    y0 = y1 - h
    if dry:
        return y0
    d.ellipse((34, y1 - 76, 94, y1 - 16), fill=th["field_line"])
    d.text((52, y1 - 80), "+", font=S.font("Regular", 50), fill=th["sub"])
    d.rounded_rectangle((112, y0, W - 34, y1), radius=40, outline=th["field_line"], width=3, fill=th["field"])
    if text:
        y = y0 + 14
        for ln in lines:
            d.text((140, y), ln, font=f, fill=th["text"])
            y += lh
        cx, cy = 140 + d.textlength(lines[-1], font=f) + 4, y - lh
        d.ellipse((W - 112, y1 - 74, W - 46, y1 - 8), fill=S.BLUE)
        d.polygon([(W - 79, y1 - 62), (W - 96, y1 - 40), (W - 62, y1 - 40)], fill="white")
        d.line((W - 79, y1 - 44, W - 79, y1 - 20), fill="white", width=6)
    else:
        d.text((140, y0 + 20), "Message", font=S.font("Regular", 40), fill=th["ph"])
        cx, cy = 138, y0 + 18
    if cursor_on:
        d.rectangle((cx, cy + 6, cx + 4, cy + size + 6), fill=S.BLUE)
    return y0


def hook_box(d, th, text):
    f, lines, lh = S.fit_text(d, text, "Bold", W - 220, 300, 62, 44, lh=1.18)
    bh = len(lines) * lh + 56
    widest = max(d.textlength(ln, font=f) for ln in lines)
    x0 = (W - widest) / 2 - 36
    d.rounded_rectangle((x0, 300, W - x0, 300 + bh), radius=28, fill=th["hook_bg"], outline=th["hook_line"], width=3)
    y = 326
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=th["hook_txt"])
        y += lh
    return 300 + bh


def _draw_thread(d, th, items, y0, t, dry=False):
    y = y0
    for it in items:
        k = it[0]
        if k == "stamp":
            y = stamp(d, th, it[1], y, dry)
        elif k == "dots":
            y = dots_bubble(d, th, y, t, dry) + 22
        else:
            y = bubble(d, th, it[1], y, k == "me", sender=it[2] if len(it) > 2 else None, dry=dry) + 22
    return y


def render_reel(p, out_dir: Path, seed=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    th = THEMES[p.get("theme", "light")]
    seed = seed if seed is not None else sum(map(ord, p["id"]))
    ev, total = build_timeline(p, seed)
    kb_top = H - 640
    n = int(total * FPS)

    thread = []
    for c in p.get("context", []):
        if c.get("stamp"):
            thread.append(("stamp", c["stamp"]))
        thread.append(("me" if c.get("from") == "me" else "them", c["text"], c.get("name")))
    base = Image.new("RGB", (W, H), th["bg"])
    draw_header(ImageDraw.Draw(base), th, p.get("contact", ""))

    out = out_dir / f"{p['id']}.mp4"
    silent = out_dir / f".{p['id']}_v.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                             "-crf", "20", "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    scratch = ImageDraw.Draw(Image.new("RGB", (W, H)))
    hook_bottom = hook_box(scratch, th, p["hook"])
    ei, text, pressed, pressed_until, dots = 0, "", None, -1, False
    last_sent_at = None
    for fi in range(n):
        t = fi / FPS
        while ei < len(ev) and ev[ei][0] <= t:
            _, kind, pl = ev[ei]
            if kind in ("prefill", "del"):
                text = pl
            elif kind == "key":
                text, ch = pl
                pressed, pressed_until = ch.lower(), t + 0.08
            elif kind == "send":
                thread.append(("me", pl))
                text, last_sent_at = "", t
            elif kind == "dots_on":
                dots = True
            elif kind == "them":
                dots = False
                thread.append(("them", pl))
            elif kind == "stamp":
                thread.append(("stamp", pl))
            ei += 1
        items = thread + ([("dots",)] if dots else [])
        img = base.copy()
        d = ImageDraw.Draw(img)
        comp_top = compose(scratch, th, text, kb_top, False, dry=True)
        h = _draw_thread(scratch, th, items, 0, t, dry=True)
        top_limit = 300 + 260  # under the hook box
        y0 = comp_top - 40 - h
        if y0 < top_limit:  # thread too tall: scroll, oldest messages go under the header/hook
            pass
        y_end = _draw_thread(d, th, items, y0, t)
        if last_sent_at is not None and items and items[-1][0] == "me":
            f = S.font("Regular", 26)
            d.text((W - 40 - d.textlength("Delivered", font=f), y_end - 18), "Delivered", font=f, fill=th["sub"])
        d.rectangle((0, 250, W, hook_bottom + 24), fill=th["bg"])  # scrolled messages tuck under the hook
        draw_header(d, th, p.get("contact", ""))  # header stays on top of scrolled messages
        draw_keyboard(d, th, kb_top, pressed if t < pressed_until else None)
        compose(d, th, text, kb_top, cursor_on=(int(t * 2) % 2 == 0))
        hook_box(d, th, p["hook"])
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()

    wav = out_dir / f".{p['id']}.wav"
    synth_audio(ev, total, wav, seed)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", "-movflags", "+faststart", str(out)],
                   check=True)
    silent.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    return out


# ---------- audio ----------

def synth_audio(ev, total, path, seed):
    rng = np.random.default_rng(seed)
    n = int(total * SR) + SR
    buf = rng.standard_normal(n).astype(np.float32) * 0.0025  # faint room tone

    def add(at, s):
        i = int(at * SR)
        L = max(0, min(len(s), n - i))
        buf[i:i + L] += s[:L]

    def click(at, gain, tone):
        L = int(0.022 * SR)
        tt = np.arange(L) / SR
        s = (rng.standard_normal(L).astype(np.float32) * 0.5 + np.sin(2 * np.pi * tone * tt).astype(np.float32) * 0.6)
        add(at, s * np.exp(-tt * 260).astype(np.float32) * gain)

    def swoosh(at):
        L = int(0.32 * SR)
        tt = np.arange(L) / SR
        ph = 2 * np.pi * np.cumsum(500 + 2600 * tt / tt[-1]) / SR
        add(at, (np.sin(ph) * np.sin(np.pi * tt / tt[-1]) * 0.18).astype(np.float32))

    def tick(at):
        L = int(0.18 * SR)
        tt = np.arange(L) / SR
        s = (np.sin(2 * np.pi * 1320 * tt) + 0.5 * np.sin(2 * np.pi * 1980 * tt)) * np.exp(-tt * 22) * 0.12
        add(at, s.astype(np.float32))

    for t, kind, pl in ev:
        if kind == "key":
            click(t, rng.uniform(0.28, 0.42), 1200 if pl[1] == " " else rng.uniform(1800, 2600))
        elif kind == "del":
            click(t, 0.3, 1500)
        elif kind == "send":
            swoosh(t)
        elif kind == "them":
            tick(t)
    buf = np.clip(buf, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
