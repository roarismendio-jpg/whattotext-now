"""Official Instagram Graph API. Works with either token type Meta issues:
- Instagram-login user token ("IGAA..."): graph.instagram.com, refreshed every 6 days.
- Business/system-user token ("EAA...", new apps since 2026, never expires): graph.facebook.com,
  addressed by the Instagram account's ID (IG_USER_ID, auto-discovered from the token).
Publishing (incl. trial reels), insights, comment moderation. No follow/like/DM automation.
"""
import json
import time
import requests
from . import config

IG_BASE, FB_BASE = "https://graph.instagram.com", "https://graph.facebook.com"
_ig_id_cache = {}


def _is_ig_login_token():
    return _tok().startswith("IG")


def _base():
    return IG_BASE if _is_ig_login_token() else FB_BASE


class IGError(Exception):
    pass


def _url(path):
    return f"{_base()}/{config.GRAPH}/{path}"


def _tok():
    return config.get("IG_ACCESS_TOKEN", required=True)


def _me():
    explicit = config.get("IG_USER_ID", "")
    if explicit:
        return explicit
    if _is_ig_login_token():
        return "me"
    tok = _tok()
    if tok not in _ig_id_cache:  # business token: find the Instagram account it was granted
        j = _check(requests.get(f"{FB_BASE}/{config.GRAPH}/debug_token",
                                params={"input_token": tok, "access_token": tok}, timeout=30))
        ids = [t for g in j.get("data", {}).get("granular_scopes", []) if g.get("scope", "").startswith("instagram")
               for t in g.get("target_ids", [])]
        if not ids:
            raise IGError("token has no Instagram account attached; set IG_USER_ID")
        _ig_id_cache[tok] = ids[0]
    return _ig_id_cache[tok]


def _check(r):
    try:
        j = r.json()
    except ValueError:
        raise IGError(f"HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code >= 400 or "error" in j:
        raise IGError(json.dumps(j.get("error", j))[:800])
    return j


def get(path, params=None):
    return _check(requests.get(_url(path), params={**(params or {}), "access_token": _tok()}, timeout=60))


def post(path, data=None):
    return _check(requests.post(_url(path), data={**(data or {}), "access_token": _tok()}, timeout=60))


def account():
    if _is_ig_login_token():
        return get("me", {"fields": "user_id,username,followers_count,media_count"})
    return get(_me(), {"fields": "id,username,followers_count,media_count"})


def quota():
    return get(f"{_me()}/content_publishing_limit", {"fields": "quota_usage,config"})


def _wait(cid, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = get(cid, {"fields": "status_code,status"})
        if s.get("status_code") == "FINISHED":
            return
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise IGError(f"container {cid}: {s}")
        time.sleep(8)
    raise IGError(f"container {cid} timed out")


def _publish(cid):
    mid = post(f"{_me()}/media_publish", {"creation_id": cid})["id"]
    meta = get(mid, {"fields": "permalink,timestamp"})
    return mid, meta.get("permalink")


def publish_carousel(urls, caption, ai_label=False):
    extra = {"is_ai_generated": "true"} if ai_label else {}
    if len(urls) == 1:
        c = post(f"{_me()}/media", {"image_url": urls[0], "caption": caption, **extra})
        _wait(c["id"])
        return _publish(c["id"])
    kids = [post(f"{_me()}/media", {"image_url": u, "is_carousel_item": "true"})["id"] for u in urls[:10]]
    for k in kids:
        _wait(k)
    parent = post(f"{_me()}/media", {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption, **extra})
    _wait(parent["id"])
    return _publish(parent["id"])


def publish_reel(video_url, caption, trial=False, cover_url=None, ai_label=False):
    data = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"}
    if trial:
        # Shown to non-followers first; Instagram auto-shares to followers if it performs.
        data["trial_params"] = json.dumps({"graduation_strategy": "SS_PERFORMANCE"})
    if cover_url:
        data["cover_url"] = cover_url
    if ai_label:
        data["is_ai_generated"] = "true"
    c = post(f"{_me()}/media", data)
    _wait(c["id"])
    return _publish(c["id"])


METRICS = ["reach", "views", "likes", "comments", "shares", "saved", "follows", "reposts",
           "reels_skip_rate", "ig_reels_avg_watch_time"]


def insights(media_id):
    def parse(j):
        out = {}
        for d in j.get("data", []):
            v = (d.get("values") or [{}])[0].get("value")
            if v is None:
                v = (d.get("total_value") or {}).get("value")
            out[d["name"]] = v
        return out
    try:
        return parse(get(f"{media_id}/insights", {"metric": ",".join(METRICS)}))
    except IGError:
        out = {}
        for m in METRICS:  # not every metric exists for every media type
            try:
                out.update(parse(get(f"{media_id}/insights", {"metric": m})))
            except IGError:
                pass
        return out


def comments(media_id):
    return get(f"{media_id}/comments", {"fields": "id,text,timestamp,username,hidden", "limit": 50}).get("data", [])


def reply(comment_id, message):
    return post(f"{comment_id}/replies", {"message": message})


def hide(comment_id):
    return post(comment_id, {"hide": "true"})


def refresh_token():
    if not _is_ig_login_token():
        return "never (business token)"
    r = requests.get(f"{IG_BASE}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": _tok()}, timeout=30)
    j = _check(r)
    config.set_value("IG_ACCESS_TOKEN", j["access_token"])
    return j.get("expires_in")
