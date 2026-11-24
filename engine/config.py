"""Settings from .env (no dependencies)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def _load():
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load()


def get(key, default=None, required=False):
    v = os.environ.get(key, default)
    if required and not v:
        raise SystemExit(f"Missing {key} in .env (see .env.example)")
    return v


def set_value(key, value):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n")
    os.environ[key] = value


TZ = get("TIMEZONE", "America/Chicago")
GRAPH = get("GRAPH_VERSION", "v24.0")
REGULAR_SLOTS = [s.strip() for s in get("REGULAR_SLOTS", "12:10,17:40,21:30").split(",")]
TRIAL_SLOTS = [s.strip() for s in get("TRIAL_SLOTS", "10:20,14:50,19:05,22:40,23:55").split(",")]
TRIALS_PER_DAY = int(get("TRIALS_PER_DAY", "3"))
TRIAL_MIN_FOLLOWERS = int(get("TRIAL_MIN_FOLLOWERS", "200"))
MAX_REGULAR_PER_DAY = int(get("MAX_REGULAR_PER_DAY", "3"))
EXPLORE_SHARE = float(get("EXPLORE_SHARE", "0.3"))
AI_LABEL = get("AI_LABEL_SYNTHETIC_MEDIA", "false").lower() == "true"
