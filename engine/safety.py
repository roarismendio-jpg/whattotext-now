"""Comment safety net for a fully hands-off mental-health-adjacent account.

- Possible crisis language -> one public reply with crisis resources (never "counseling"),
  logged for the weekly report. Not hidden: hiding can feel like being silenced.
- Spam / scams / slurs -> hidden.
The AI never writes free-form replies to people in distress. Only the fixed message below.
"""
import re
from datetime import datetime, timezone

from . import ig

CRISIS = re.compile(
    r"(kill(ing)? myself|\bkms\b|suicid|end it all|want to die|wanna die|don'?t want to (be here|live|exist)|"
    r"self[- ]?harm|hurt(ing)? myself|cutting myself|no reason to live|better off without me|unalive)", re.I)
SPAM = re.compile(r"(dm me for|check my bio|promo|crypto|forex|onlyfans|link in my bio|giveaway winner|cash app)", re.I)
SLURS = re.compile(r"\b(kys)\b", re.I)  # extend as needed; "kys" aimed at others is abuse

CRISIS_REPLY = ("we're really glad you said something. if you're in the US, you can call or text 988 any time "
                "to talk to someone right now. if you're somewhere else, findahelpline.com lists free lines "
                "near you. if you're in danger right now, call your local emergency number.")


def classify(text):
    if SLURS.search(text):
        return "abuse"
    if CRISIS.search(text):
        return "crisis"
    if SPAM.search(text):
        return "spam"
    return "ok"


def scan(c, posts):
    """posts: rows with ig_media_id. Returns counts by kind."""
    counts = {"crisis": 0, "spam": 0, "abuse": 0, "ok": 0}
    for p in posts:
        try:
            items = ig.comments(p["ig_media_id"])
        except ig.IGError:
            continue
        for cm in items:
            if c.execute("select 1 from comment_log where comment_id=?", (cm["id"],)).fetchone():
                continue
            kind = classify(cm.get("text", ""))
            action = "none"
            try:
                if kind == "crisis":
                    ig.reply(cm["id"], CRISIS_REPLY)
                    action = "replied_resources"
                elif kind in ("spam", "abuse"):
                    ig.hide(cm["id"])
                    action = "hidden"
            except ig.IGError as e:
                action = f"error: {e}"[:200]
            c.execute("insert into comment_log values(?,?,?,?,?,?)",
                      (cm["id"], p["id"], datetime.now(timezone.utc).isoformat(), kind, action,
                       (cm.get("text") or "")[:500]))
            counts[kind] += 1
    c.commit()
    return counts
