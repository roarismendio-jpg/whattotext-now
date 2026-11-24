"""Free public hosting for media via GitHub Pages (no card, no cost).

Setup once: create a PUBLIC repo (e.g. whattotext-media), enable Pages (branch main, root),
clone it to MEDIA_REPO_DIR. Instagram downloads each file from its public URL at publish time.
"""
import shutil
import subprocess
import time
from pathlib import Path

import requests

from . import config


def publish_batch(groups):
    """groups: {subdir: [paths]} -> {subdir: [urls]}. One commit, one push, one wait."""
    repo = Path(config.get("MEDIA_REPO_DIR", ".")).expanduser()
    base = config.get("MEDIA_BASE_URL", required=True).rstrip("/")
    out = {}
    for subdir, paths in groups.items():
        dest = repo / "media" / subdir
        dest.mkdir(parents=True, exist_ok=True)
        out[subdir] = []
        for p in paths:
            shutil.copy2(p, dest / Path(p).name)
            out[subdir].append(f"{base}/media/{subdir}/{Path(p).name}")
    if not out:
        return out
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["add", "media"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", f"media: {len(out)} posts"], check=False)
    subprocess.run(git + ["pull", "-q", "--rebase", "origin", "main"], check=False)
    subprocess.run(git + ["push", "-q", "origin", "HEAD:main"], check=True)
    wait_live([u for us in out.values() for u in us], timeout=900)
    return out


def publish_files(paths, subdir):
    return publish_batch({subdir: paths})[subdir]


def _legacy_publish_files(paths, subdir):
    repo = Path(config.get("MEDIA_REPO_DIR", required=True)).expanduser()
    base = config.get("MEDIA_BASE_URL", required=True).rstrip("/")
    dest = repo / subdir
    dest.mkdir(parents=True, exist_ok=True)
    urls = []
    for p in paths:
        shutil.copy2(p, dest / Path(p).name)
        urls.append(f"{base}/{subdir}/{Path(p).name}")
    git = ["git", "-C", str(repo)]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", f"media {subdir}"], check=False)
    subprocess.run(git + ["push", "-q"], check=True)
    wait_live(urls)
    return urls


def wait_live(urls, timeout=420):
    """GitHub Pages takes ~30-120s to deploy; Instagram must be able to fetch the file."""
    start = time.time()
    pending = list(urls)
    while pending and time.time() - start < timeout:
        pending = [u for u in pending if requests.head(u, timeout=20).status_code != 200]
        if pending:
            time.sleep(10)
    if pending:
        raise RuntimeError(f"media not live after {timeout}s: {pending[:2]}")


def prune(keep_days=10):
    """Delete media older than keep_days from the repo (Instagram has its own copy after publishing)."""
    repo = Path(config.get("MEDIA_REPO_DIR", ".")).expanduser() / "media"
    if not repo.exists():
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for d in repo.iterdir():
        if d.is_dir() and not d.name.startswith(".") and d.stat().st_mtime < cutoff:
            shutil.rmtree(d)
            removed += 1
    if removed:
        git = ["git", "-C", str(repo.parent)]
        subprocess.run(git + ["add", "-A", "media"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "prune old media"], check=False)
        subprocess.run(git + ["push", "-q", "origin", "HEAD:main"], check=False)
    return removed
