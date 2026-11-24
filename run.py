#!/usr/bin/env python3
"""@whattotext engine — CLI

  python3 run.py import content/batch01.json   # add posts (drafts) + register pair tests
  python3 run.py render [--local]              # render drafts -> ready (and host media unless --local)
  python3 run.py preview content/batch01.json  # render a batch to out/preview (no DB, no hosting)
  python3 run.py plan [--days 2]               # fill posting slots (regular; trials once >=200 followers)
  python3 run.py publish [--dry-run]           # publish due posts
  python3 run.py insights                      # pull metrics for posts from last 21 days
  python3 run.py safety                        # scan comments (crisis replies, hide spam)
  python3 run.py tick                          # cron, every 15 min: everything above, on schedule
  python3 run.py report [--json]               # what the weekly agent reads
  python3 run.py dashboard                     # writes data/dashboard.html
  python3 run.py status | refresh-token | prune
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine import config, db, planner
from engine.config import ROOT

OUT = ROOT / "out"
LOG = ROOT / "data" / "engine.log"
REQUIRED = {"id", "format", "cluster", "hook_pattern", "hook", "caption"}
CAROUSELS = {"copy_carousel", "mail_carousel", "notes_carousel", "dont_send", "number_carousel"}


def log(msg):
    line = f"{datetime.now(planner.TZ):%Y-%m-%d %H:%M} {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def now():
    return datetime.now(timezone.utc)


# ---------- content ----------

def cmd_import(path):
    c = db.conn()
    items = json.loads(Path(path).read_text())
    added, pairs, tests = 0, {}, {}
    for p in items:
        missing = REQUIRED - set(p)
        if missing:
            raise SystemExit(f"{p.get('id')}: missing {missing}")
        if c.execute("select 1 from posts where id=?", (p["id"],)).fetchone():
            continue
        test = p.get("test")
        pair = p.get("pair") or (test["id"] if test else None)
        c.execute("insert into posts(id, spec, format, cluster, hook_pattern, pair, status) values(?,?,?,?,?,?, 'draft')",
                  (p["id"], json.dumps(p), p["format"], p["cluster"], p["hook_pattern"], pair))
        added += 1
        if test:
            tests.setdefault(test["id"], {"variable": test["variable"], "hypothesis": test["hypothesis"], "arms": []})["arms"].append(p["id"])
        elif p.get("pair"):
            pairs.setdefault(p["pair"], []).append(p["id"])
    for tid, t in tests.items():
        c.execute("insert or ignore into tests(id, variable, hypothesis, arms, metric, min_reach, window_h, decision_rule) values(?,?,?,?,?,?,?,?)",
                  (tid, t["variable"], t["hypothesis"], json.dumps(t["arms"]), "score (skip rate for opening tests)", 300, 48,
                   "winner if score ratio >= 1.3 after all arms judged; else inconclusive"))
    for pid, arms in pairs.items():
        if len(arms) >= 2:
            c.execute("insert or ignore into tests(id, variable, hypothesis, arms, metric, min_reach, window_h, decision_rule) "
                      "values(?,?,?,?,?,?,?,?)",
                      (f"format-{pid}", "format", "same topic as typing reel vs carousel: which earns more sends+saves+follows per reach?",
                       json.dumps(arms), "score", 500, 48, "winner if score ratio >= 1.3 after both judged; else inconclusive"))
    c.commit()
    log(f"imported {added} posts, {len(pairs)} format pairs, {len(tests)} pre-registered tests")


def _render_one(p, out_dir):
    if p["format"] in ("typing_reel", "thread_reel"):
        from engine import reels
        return [reels.render_reel(p, out_dir)]
    from engine import carousels
    return carousels.render_carousel(p, out_dir)


def cmd_render(local=False):
    """Render every draft, then host all media in ONE commit/push (fast on GitHub Pages)."""
    c = db.conn()
    rendered = {}
    for row in c.execute("select * from posts where status='draft'").fetchall():
        p = db.spec(row)
        try:
            rendered[row["id"]] = _render_one(p, OUT / row["id"])
        except Exception as e:
            c.execute("update posts set error=? where id=?", (f"render: {e}"[:1000], row["id"]))
            c.commit()
            log(f"render FAILED {row['id']}: {e}")
    if not rendered:
        return
    urls = {k: [] for k in rendered}
    if not local:
        from engine import hosting
        urls = hosting.publish_batch(rendered)
    for pid, paths in rendered.items():
        c.execute("update posts set media=?, media_urls=?, status='ready', error=null where id=?",
                  (json.dumps([str(x) for x in paths]), json.dumps(urls.get(pid, [])), pid))
    c.commit()
    log(f"rendered {len(rendered)} posts{'' if local else ' + hosted'}")


def cmd_preview(path):
    for p in json.loads(Path(path).read_text()):
        paths = _render_one(p, OUT / "preview")
        print(f"{p['id']:5} {p['format']:16} {len(paths)} file(s)  {p['hook']}")


# ---------- publish ----------

def cmd_publish(dry=False):
    import os
    from engine import ig
    if os.environ.get("PUBLISH", "on") != "on":
        dry = True  # publishing switched off (repo variable PUBLISH != on)
    c = db.conn()
    due = c.execute("select * from posts where status='scheduled' and scheduled_at <= ? order by scheduled_at",
                    (datetime.now(planner.TZ).isoformat(),)).fetchall()
    since = (now() - timedelta(hours=24)).isoformat()
    regular_24h = c.execute("select count(*) n from posts where status='published' and kind='regular' and published_at > ?",
                            (since,)).fetchone()["n"]
    for row in due[:2]:  # at most 2 per tick, keeps a natural rhythm
        p = db.spec(row)
        if row["kind"] == "regular" and regular_24h >= config.MAX_REGULAR_PER_DAY:
            log(f"daily regular cap reached; {row['id']} waits")
            continue
        urls = json.loads(row["media_urls"] or "[]")
        if dry:
            log(f"[dry-run] would publish {row['id']} ({row['kind']} {row['format']}, {len(urls)} media)")
            continue
        try:
            if row["format"] in ("typing_reel", "thread_reel"):
                mid, link = ig.publish_reel(urls[0], p["caption"], trial=row["kind"] == "trial", ai_label=config.AI_LABEL)
            else:
                mid, link = ig.publish_carousel(urls, p["caption"], ai_label=config.AI_LABEL)
            c.execute("update posts set status='published', ig_media_id=?, permalink=?, published_at=?, error=null where id=?",
                      (mid, link, now().isoformat(), row["id"]))
            regular_24h += row["kind"] == "regular"
            log(f"PUBLISHED {row['kind']} {row['id']} -> {link}")
        except Exception as e:
            msg = str(e)
            if row["kind"] == "trial" and "trial" in msg.lower():
                # not eligible / trial limit: return to backlog as a regular candidate
                c.execute("update posts set status='ready', scheduled_at=null, kind='regular', error=? where id=?", (msg[:1000], row["id"]))
                db.kv_set(c, "trials_blocked_until", (now() + timedelta(days=1)).isoformat())
                log(f"trial rejected for {row['id']}, back to backlog: {msg[:160]}")
            else:
                c.execute("update posts set status='failed', error=? where id=?", (msg[:1000], row["id"]))
                log(f"publish FAILED {row['id']}: {msg[:200]}")
        c.commit()


# ---------- measure ----------

def cmd_insights():
    from engine import ig
    c = db.conn()
    since = (now() - timedelta(days=21)).isoformat()
    rows = c.execute("select * from posts where status='published' and published_at > ?", (since,)).fetchall()
    for row in rows:
        try:
            m = ig.insights(row["ig_media_id"])
        except Exception as e:
            log(f"insights failed {row['id']}: {e}")
            continue
        c.execute("insert into metrics values(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (row["id"], now().isoformat(), m.get("reach"), m.get("views"), m.get("likes"), m.get("comments"),
                   m.get("shares"), m.get("saved"), m.get("follows"), m.get("reposts"),
                   m.get("reels_skip_rate"), m.get("ig_reels_avg_watch_time")))
    c.commit()
    winners = planner.flag_winners(c)
    tests = planner.evaluate_tests(c)
    log(f"insights: {len(rows)} posts; winners flagged: {winners}; tests decided: {tests}")


def cmd_followers():
    from engine import ig
    c = db.conn()
    a = ig.account()
    c.execute("insert into followers(date,count) values(?,?) on conflict(date) do update set count=excluded.count",
              (datetime.now(planner.TZ).date().isoformat(), a.get("followers_count", 0)))
    c.commit()
    log(f"followers {a.get('followers_count')}")


def cmd_safety():
    from engine import safety
    c = db.conn()
    since = (now() - timedelta(days=14)).isoformat()
    posts = c.execute("select * from posts where status='published' and published_at > ?", (since,)).fetchall()
    counts = safety.scan(c, posts)
    if counts["crisis"] or counts["spam"] or counts["abuse"]:
        log(f"safety: {counts}")


def cmd_plan(days=2):
    c = db.conn()
    blocked = db.kv_get(c, "trials_blocked_until")
    if blocked and datetime.fromisoformat(blocked) > now():
        config.TRIALS_PER_DAY = 0
    planned = planner.plan(c, days=days)
    for iso, kind, pid in planned:
        log(f"planned {kind} {pid} at {iso[:16]}")
    left = c.execute("select count(*) n from posts where status='ready' and scheduled_at is null").fetchone()["n"]
    if left < 9:
        log(f"LOW BACKLOG: {left} ready posts left. Weekly batch needed.")


def cmd_tick():
    c = db.conn()
    t = now()

    def due(key, hours):
        last = db.kv_get(c, key)
        if not last or t - datetime.fromisoformat(last) > timedelta(hours=hours):
            db.kv_set(c, key, t.isoformat())
            return True
        return False

    steps = [("render", cmd_render, 0), ("plan", cmd_plan, 0), ("publish", cmd_publish, 0), ("safety", cmd_safety, 0)]
    if due("last_insights", 3):
        steps.append(("insights", cmd_insights, 0))
    if due("last_followers", 20):
        steps.append(("followers", cmd_followers, 0))
    if due("last_dashboard", 1):
        steps.append(("dashboard", cmd_dashboard, 0))
    if due("last_refresh", 24 * 6):
        steps.append(("refresh", cmd_refresh, 0))
    if due("last_prune", 24):
        steps.append(("prune", cmd_prune, 0))
    for name, fn, _ in steps:
        try:
            fn()
        except SystemExit as e:
            log(f"{name}: {e}")
        except Exception as e:
            log(f"{name} error: {e}")


def cmd_report(as_json=False, days=7):
    c = db.conn()
    rows = planner.judged(c)
    recent = [r for r in rows if datetime.fromisoformat(r["published_at"]) > now() - timedelta(days=days)]
    fol = [dict(r) for r in c.execute("select * from followers order by date")]
    rep = {
        "followers_now": fol[-1]["count"] if fol else 0,
        "followers_last_30": fol[-30:],
        "phase": "trials" if db.follower_count(c) >= config.TRIAL_MIN_FOLLOWERS else "pre-200 (regular only)",
        "published_window": len(recent),
        "arms_all_time": {" x ".join(k): v for k, v in planner.arm_stats(rows).items()},
        "arms_by_cluster": {k[0]: v for k, v in planner.arm_stats(rows, key=lambda r: (r["cluster"],)).items()},
        "winners_to_remix": [r for r in rows if c.execute("select winner from posts where id=?", (r["id"],)).fetchone()["winner"]],
        "top_window": sorted([r for r in recent if r["score"] is not None], key=lambda r: -r["score"])[:5],
        "bottom_window": sorted([r for r in recent if r["judged"]], key=lambda r: r["score"])[:5],
        "tests": [dict(t) for t in c.execute("select * from tests")],
        "backlog_ready": c.execute("select count(*) n from posts where status='ready' and scheduled_at is null").fetchone()["n"],
        "scheduled": c.execute("select count(*) n from posts where status='scheduled'").fetchone()["n"],
        "failed": [dict(id=r["id"], error=r["error"]) for r in c.execute("select id, error from posts where status='failed'")],
        "comment_safety": {r["kind"]: r["n"] for r in c.execute("select kind, count(*) n from comment_log group by kind")},
        "used_hooks": [db.spec(r)["hook"] for r in c.execute("select spec from posts")],
    }
    if as_json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(f"followers {rep['followers_now']} · phase {rep['phase']} · published (7d) {rep['published_window']} · backlog {rep['backlog_ready']}")
        for k, v in sorted(rep["arms_all_time"].items(), key=lambda kv: -kv[1]["mean"]):
            print(f"  {k:45} n={v['n']:3} mean={v['mean']:.1f}")
    return rep


def cmd_dashboard():
    from engine import dashboard
    c = db.conn()
    p = dashboard.build(c, ROOT / "data" / "dashboard.html")
    log(f"dashboard -> {p}")


def cmd_refresh():
    from engine import ig
    log(f"token refreshed, expires_in={ig.refresh_token()}")


def cmd_prune():
    from engine import hosting
    n = hosting.prune()
    if n:
        log(f"pruned {n} old media folders")


def cmd_ci():
    """One GitHub Actions run: restore encrypted state, import content, tick, save state, push."""
    import os
    import subprocess
    from engine import statecrypt
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    enc_db, plain_db, enc_tok = data / "engine.db.enc", data / "engine.db", data / "token.enc"
    if enc_db.exists():
        statecrypt.decrypt_file(enc_db, plain_db)
    tok = statecrypt.load_token(enc_tok) or os.environ.get("IG_ACCESS_TOKEN")
    if tok:
        os.environ["IG_ACCESS_TOKEN"] = tok
    for f in sorted((ROOT / "content").glob("*.json")):
        cmd_import(str(f))
    if tok:
        cmd_tick()
    else:
        log("no Instagram token yet: rendering + planning only")
        for fn in (cmd_render, cmd_plan):
            try:
                fn()
            except Exception as e:
                log(f"{fn.__name__} error: {e}")
    try:
        rep = cmd_report(as_json=False)
        (data / "report.json").write_text(json.dumps(rep, indent=2, default=str))
        from engine import dashboard
        dashboard.build(db.conn(), ROOT / "dashboard.html")
    except Exception as e:
        log(f"report error: {e}")
    statecrypt.encrypt_file(plain_db, enc_db)
    if os.environ.get("IG_ACCESS_TOKEN"):
        statecrypt.save_token(os.environ["IG_ACCESS_TOKEN"], enc_tok)
    plain_db.unlink(missing_ok=True)
    lines = LOG.read_text().splitlines()[-400:] if LOG.exists() else []
    LOG.write_text("\n".join(lines) + "\n")
    git = ["git", "-C", str(ROOT)]
    keep = ["data/engine.db.enc", "data/token.enc", "data/report.json", "data/engine.log", "dashboard.html"]
    keep = [p for p in keep if (ROOT / p).exists()]  # a missing path makes `git add` add nothing at all
    subprocess.run(git + ["add", "--"] + keep, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "state"], check=False)
    subprocess.run(git + ["pull", "-q", "--rebase", "origin", "main"], check=False)
    subprocess.run(git + ["push", "-q", "origin", "HEAD:main"], check=True)


def cmd_status():
    from engine import ig
    print(json.dumps(ig.account(), indent=2))
    print(json.dumps(ig.quota(), indent=2))
    c = db.conn()
    print({r["status"]: r["n"] for r in c.execute("select status, count(*) n from posts group by status")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--days", type=int, default=None)
    a = ap.parse_args()
    cmds = {
        "import": lambda: cmd_import(a.arg), "render": lambda: cmd_render(a.local), "preview": lambda: cmd_preview(a.arg),
        "plan": lambda: cmd_plan(a.days or 2), "publish": lambda: cmd_publish(a.dry_run), "insights": cmd_insights,
        "followers": cmd_followers, "safety": cmd_safety, "tick": cmd_tick, "report": lambda: cmd_report(a.json, a.days or 7),
        "dashboard": cmd_dashboard, "refresh-token": cmd_refresh, "prune": cmd_prune, "status": cmd_status, "ci": cmd_ci,
    }
    if a.cmd not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[a.cmd]()


if __name__ == "__main__":
    main()
