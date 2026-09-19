"""Transport and the read-through cache for Ichiran segmentation.

Segmentation is the only slow step in a build: roughly a minute per story, over
the network, to a service that must be running. Everything else is local and
sub-second.

The cache is keyed on sha256 of the exact text, which gives the invalidation the
corpus needs for free. Segmentation depends only on the text and validation only
on the vocabulary, so the two never invalidate each other: maturing cards in
Anki re-runs validation without re-segmenting anything, and editing one story
leaves every other story's cache intact. That separation is what keeps a rebuild
cheap as the number of stories grows.
"""

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# No default: the server is whatever host runs Ichiran, and hardcoding one would
# put a private network address in a public repo. Comma-separate for a fallback —
# python's resolver misses mDNS, so an mDNS name wants a bare IP after it.
ENV = "ICHIRAN_URL"
CACHE_ENV = "ICHIRAN_CACHE"

# Beside the package rather than inside it, so a vendored copy of this directory
# does not carry someone else's 295 recorded responses with it — and so the
# cache this repo already has stays where build.py and rebuild.py expect it.
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / ".segcache"

hits = 0
misses = 0


def cache_dir():
    return Path(os.environ.get(CACHE_ENV) or DEFAULT_CACHE)


def _urls():
    raw = os.environ.get(ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{ENV} is not set. Point it at an Ichiran server, e.g.\n"
            f"  export {ENV}=http://localhost:3005\n"
            "See README.md — Ichiran is required for segmentation."
        )
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


def fetch(text):
    """One segmentation request, trying each configured URL in turn."""
    payload = json.dumps({"text": text}).encode()
    urls = _urls()
    last = None
    for base in urls:
        req = urllib.request.Request(
            f"{base}/segmentation",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.URLError as e:
            last = e
    raise RuntimeError(f"Ichiran unreachable on {urls}: {last}")


def _path(text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    return cache_dir() / f"{digest}.json"


def cached(text):
    """The recorded response for `text`, or None. Never hits the network.

    This is what makes the package testable offline: every text the corpus has
    ever been built from is already on disk, so fixtures are recorded reality
    rather than shapes invented to suit the walk.
    """
    path = _path(text)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None  # A truncated entry is a miss, not a crash.


def store(text, value):
    path = _path(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # Atomic, so an interrupted write cannot poison the cache.
    return value


def segment(text):
    """Cached segmentation. Only a text this machine has never seen hits Ichiran."""
    global hits, misses
    hit = cached(text)
    if hit is not None:
        hits += 1
        return hit
    misses += 1
    return store(text, fetch(text))


def stats():
    return f"segmentation cache: {hits} hit, {misses} miss"


def clear():
    directory = cache_dir()
    if not directory.is_dir():
        return 0
    n = 0
    for path in directory.iterdir():
        if path.suffix in (".json", ".tmp") or path.name.endswith(".json.tmp"):
            path.unlink()
            n += 1
    return n
