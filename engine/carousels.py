"""Turns a post spec (content/*.json) into carousel slide images."""
from pathlib import Path
from . import screens as S


def build_slides(p):
    fmt = p["format"]
    S.set_device(p)
    slides = []
    if fmt == "copy_carousel":
        n = len(p["versions"])
        slides.append(S.notes_title_slide(p["hook"], sub=f"{n} versions you can copy  →"))
        for i, v in enumerate(p["versions"]):
            slides.append(S.chat_slide(p.get("contact", ""), f"{i + 1} of {n} · {v['label']}", v["text"], context=v.get("context") or p.get("context")))
        if p.get("avoid"):
            slides.append(S.notes_body_slide("what not to say", p["avoid"]))
        slides.append(S.notes_body_slide("why these work", p["why"]))
    elif fmt == "mail_carousel":
        n = len(p["versions"])
        slides.append(S.notes_title_slide(p["hook"], sub=f"{n} templates  →"))
        for i, v in enumerate(p["versions"]):
            slides.append(S.mail_slide(f"{i + 1} of {n} · {v['label']}", v["subject"], v["text"], to=v.get("to") or p.get("to", "professor")))
        slides.append(S.notes_body_slide("why these work", p["why"]))
    elif fmt == "notes_carousel":
        slides.append(S.notes_title_slide(p["hook"], sub="swipe  →"))
        items = p["notes"]
        per = 3 if max(len(x) for x in items) > 70 else 4
        chunks = [items[i:i + per] for i in range(0, len(items), per)]
        for j, ch in enumerate(chunks):
            last = j == len(chunks) - 1
            slides.append(S.notes_body_slide(None, ch, footer=("source: " + p["source"]) if (last and p.get("source")) else None))
    elif fmt == "dont_send":
        slides.append(S.notes_title_slide(p["hook"], sub="swipe for what to send instead  →"))
        slides.append(S.chat_slide(p.get("contact", ""), "don't send", p["bad"], context=p.get("context"), strike=True, tag="don't", tag_color=S.RED))
        slides.append(S.chat_slide(p.get("contact", ""), "send this instead", p["good"], context=p.get("context"), tag="send this", tag_color=S.GREEN))
        slides.append(S.notes_body_slide("why", p["why"]))
    elif fmt == "number_carousel":
        slides.append(S.number_slide(p["number"], p["stat"], p["source"]))
        slides.append(S.notes_body_slide(None, p["then"]))
        if p.get("copy"):
            slides.append(S.chat_slide("someone you thought of", "copy this", p["copy"]))
    else:
        raise ValueError(f"not a carousel format: {fmt}")
    return slides


def render_carousel(p, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(build_slides(p)[:10]):  # IG carousel max 10
        path = out_dir / f"{p['id']}_{i + 1:02d}.jpg"
        img.convert("RGB").save(path, "JPEG", quality=92)
        paths.append(path)
    return paths
