"""Scoring, explore/exploit scheduling (Thompson-style sampling over arms), test evaluation,
winner detection. Arms = (format, hook_pattern)."""
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, db

TZ = ZoneInfo(config.TZ)
MIN_REACH = {"regular": 500, "trial": 300}
JUDGE_AFTER_H = 48
REEL_FORMATS = {"typing_reel", "thread_reel"}


def now():
    return datetime.now(timezone.utc)


def score(m, fmt):
    if not m or not m["reach"]:
        return None
    r = m["reach"]
    s = ((m["shares"] or 0) * 3 + (m["saves"] or 0) * 2 + (m["follows"] or 0) * 10 +
         (m["comments"] or 0) + (m["likes"] or 0) * 0.5) / r * 1000
    if fmt in REEL_FORMATS and m["skip_rate"] is not None:
        sk = m["skip_rate"] / 100 if m["skip_rate"] > 1 else m["skip_rate"]
        s *= (1 - 0.5 * sk)
    return round(s, 2)


def judged(c):
    """Published posts old enough and with enough reach to count. Returns list of dicts."""
    out = []
    for p in c.execute("select * from posts where status='published'"):
        pub = datetime.fromisoformat(p["published_at"])
        m = db.latest_metrics(c, p["id"])
        if not m:
            continue
        ready = (now() - pub) >= timedelta(hours=JUDGE_AFTER_H) and (m["reach"] or 0) >= MIN_REACH[p["kind"]]
        out.append({"id": p["id"], "format": p["format"], "hook_pattern": p["hook_pattern"], "cluster": p["cluster"],
                    "kind": p["kind"], "pair": p["pair"], "published_at": p["published_at"], "permalink": p["permalink"],
                    "reach": m["reach"], "views": m["views"], "shares": m["shares"], "saves": m["saves"],
                    "follows": m["follows"], "skip_rate": m["skip_rate"], "score": score(m, p["format"]),
                    "judged": ready, "hook": db.spec(p).get("hook")})
    return out


def arm_stats(rows, key=lambda r: (r["format"], r["hook_pattern"])):
    g = defaultdict(list)
    for r in rows:
        if r["judged"] and r["score"] is not None:
            g[key(r)].append(r["score"])
    return {k: {"n": len(v), "mean": statistics.mean(v), "median": statistics.median(v)} for k, v in g.items()}


def _sample(stats, arm, prior_mean, prior_sd, rnd):
    s = stats.get(arm)
    if not s:
        return rnd.gauss(prior_mean, prior_sd)  # untried arms get prior uncertainty
    n = s["n"] + 2  # shrink toward prior
    mean = (s["mean"] * s["n"] + prior_mean * 2) / n
    return rnd.gauss(mean, prior_sd / (n ** 0.5))


def pick(candidates, stats, rnd, explore_share):
    """candidates: list of post rows. Returns one row."""
    arms = defaultdict(list)
    for p in candidates:
        arms[(p["format"], p["hook_pattern"])].append(p)
    all_scores = [s["mean"] for s in stats.values()]
    prior_mean = statistics.mean(all_scores) if all_scores else 1.0
    prior_sd = (statistics.pstdev(all_scores) if len(all_scores) > 1 else 0) or max(prior_mean * 0.5, 0.5)
    if rnd.random() < explore_share:
        arm = min(arms, key=lambda a: (stats.get(a, {}).get("n", 0), rnd.random()))
    else:
        arm = max(arms, key=lambda a: _sample(stats, a, prior_mean, prior_sd, rnd))
    return sorted(arms[arm], key=lambda p: p["created_at"])[0]


def eligible(row, kind, day):
    """Respects spec options: trial_only (test arms never hit the grid), not_before / not_after (YYYY-MM-DD)."""
    sp = json.loads(row["spec"])
    if sp.get("trial_only") and kind != "trial":
        return False
    if sp.get("not_before") and day < sp["not_before"]:
        return False
    if sp.get("not_after") and day > sp["not_after"]:
        return False
    return True


def _slot_times(day, slots):
    return [datetime.strptime(f"{day} {s}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ) for s in slots]


def plan(c, days=2, seed=None):
    """Fill empty regular (and, once eligible, trial) slots for the next `days` days."""
    rnd = random.Random(seed)
    stats = arm_stats(judged(c))
    followers = db.follower_count(c)
    trials_on = followers >= config.TRIAL_MIN_FOLLOWERS
    n_pub = c.execute("select count(*) n from posts where status='published' and kind='regular'").fetchone()["n"]
    planned = []
    today = datetime.now(TZ).date()
    for dd in range(days + 1):
        day = (today + timedelta(days=dd)).isoformat()
        taken = {r["scheduled_at"] for r in c.execute("select scheduled_at from posts where scheduled_at like ?", (f"{day}%",))}
        used_pairs = {r["pair"] for r in c.execute("select pair from posts where scheduled_at like ? and pair is not null", (f"{day}%",))}
        jobs = [("regular", t) for t in _slot_times(day, config.regular_slots(n_pub))]
        if trials_on:
            jobs += [("trial", t) for t in _slot_times(day, config.TRIAL_SLOTS[:config.TRIALS_PER_DAY])]
        for kind, t in jobs:
            if t <= datetime.now(TZ) + timedelta(minutes=20):
                continue
            iso = t.isoformat()
            if iso in taken:
                continue
            q = "select * from posts where status='ready' and scheduled_at is null"
            cands = [p for p in c.execute(q) if (kind == "regular" or p["format"] in REEL_FORMATS)
                     and not (p["pair"] and p["pair"] in used_pairs) and eligible(p, kind, day)]
            if not cands:
                continue
            p = pick(cands, stats, rnd, config.EXPLORE_SHARE)
            c.execute("update posts set scheduled_at=?, kind=?, status='scheduled' where id=?", (iso, kind, p["id"]))
            if p["pair"]:
                used_pairs.add(p["pair"])
            planned.append((iso, kind, p["id"]))
    c.commit()
    return planned


def flag_winners(c):
    rows = [r for r in judged(c) if r["judged"]]
    recent = [r for r in rows if datetime.fromisoformat(r["published_at"]) > now() - timedelta(days=21)]
    if len(recent) < 4:
        return []
    med_s = statistics.median([r["score"] for r in recent])
    med_r = statistics.median([r["reach"] for r in recent])
    winners = [r["id"] for r in recent if r["score"] >= 1.5 * med_s or r["reach"] >= 2 * med_r]
    for pid in winners:
        c.execute("update posts set winner=1 where id=?", (pid,))
    c.commit()
    return winners


def evaluate_tests(c):
    rows = {r["id"]: r for r in judged(c)}
    results = []
    for t in c.execute("select * from tests where status='running'"):
        arms = json.loads(t["arms"])
        got = [rows.get(a) for a in arms]
        if not all(g and g["judged"] for g in got):
            continue
        best = max(got, key=lambda g: g["score"])
        other = min(got, key=lambda g: g["score"])
        ratio = best["score"] / other["score"] if other["score"] else float("inf")
        res = (f"{best['id']} won on {t['variable']} ({best['score']} vs {other['score']}, x{ratio:.2f})" if ratio >= 1.3
               else f"inconclusive (x{ratio:.2f})")
        c.execute("update tests set status='done', result=? where id=?", (res, t["id"]))
        results.append((t["id"], res))
    c.commit()
    return results
