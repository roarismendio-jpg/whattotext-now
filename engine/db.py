"""Local SQLite store (free, no API quotas)."""
import json
import sqlite3
from .config import ROOT

DB_PATH = ROOT / "data" / "engine.db"

SCHEMA = """
create table if not exists posts(
  id text primary key, spec text, format text, cluster text, hook_pattern text, pair text,
  kind text default 'regular',            -- regular | trial
  status text default 'draft',            -- draft | ready | scheduled | published | failed | killed
  scheduled_at text, media text, media_urls text,
  ig_media_id text, permalink text, published_at text, error text,
  winner integer default 0, created_at text default (datetime('now'))
);
create table if not exists metrics(
  post_id text, ts text, reach int, views int, likes int, comments int, shares int, saves int,
  follows int, reposts int, skip_rate real, avg_watch_ms real
);
create table if not exists followers(date text primary key, count int);
create table if not exists tests(
  id text primary key, variable text, hypothesis text, arms text, metric text,
  min_reach int, window_h int, decision_rule text, status text default 'running', result text
);
create table if not exists learnings(ts text default (datetime('now')), text text);
create table if not exists comment_log(comment_id text primary key, post_id text, ts text, kind text, action text, text text);
create table if not exists kv(k text primary key, v text);
"""


def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def kv_get(c, k, default=None):
    r = c.execute("select v from kv where k=?", (k,)).fetchone()
    return r["v"] if r else default


def kv_set(c, k, v):
    c.execute("insert into kv(k,v) values(?,?) on conflict(k) do update set v=excluded.v", (k, str(v)))
    c.commit()


def spec(row):
    return json.loads(row["spec"])


def latest_metrics(c, post_id):
    return c.execute("select * from metrics where post_id=? order by ts desc limit 1", (post_id,)).fetchone()


def follower_count(c):
    r = c.execute("select count from followers order by date desc limit 1").fetchone()
    return r["count"] if r else 0
