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
import time
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


# A host that answers on the second try is the normal case here, not the
# exceptional one: Ichiran runs in Docker on a machine that sleeps, and the
# first request after it wakes can time out while the container comes back.
RETRY_DELAYS = (2, 5, 10)


def _urls(url=None):
    """The servers to try, in order. An explicit url wins over the environment.

    Callers outside this repo pass the URL — a skill has it on its own command
    line and has no reason to reach through an environment variable to deliver
    it. Inside the repo nothing passes one, so the env var stays the only
    configuration and the error below is still what an unset one produces.
    """
    raw = url if url else os.environ.get(ENV, "")
    raw = raw.strip()
    if not raw:
        raise RuntimeError(
            f"{ENV} is not set. Point it at an Ichiran server, e.g.\n"
            f"  export {ENV}=http://localhost:3005\n"
            "See README.md — Ichiran is required for segmentation."
        )
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


def fetch(text, url=None, timeout=180, retries=len(RETRY_DELAYS)):
    """One segmentation request, trying each configured URL in turn.

    Every URL is tried before any of them is retried, because the usual reason
    to configure two is that one of them is an mDNS name python's resolver
    cannot see — retrying that one first just spends the backoff on a name that
    will never resolve.
    """
    payload = json.dumps({"text": text}).encode()
    urls = _urls(url)
    last = None
    for attempt in range(max(1, retries)):
        for base in urls:
            req = urllib.request.Request(
                f"{base}/segmentation",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.load(r)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
        if attempt < retries - 1:
            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    raise RuntimeError(f"Ichiran unreachable on {urls}: {last}")


def probe(url=None, timeout=10):
    """Whether Ichiran answers at all. One try, no retries, never raises."""
    try:
        return bool(fetch("テスト", url=url, timeout=timeout, retries=1))
    except Exception:
        return False


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


def segment(text, url=None, cache=True):
    """Cached segmentation. Only a text this machine has never seen hits Ichiran.

    `cache=False` is for callers whose texts are not a corpus — a one-off word
    lookup has nothing to gain from a cache entry and no reason to leave one in
    somebody else's directory.
    """
    global hits, misses
    if not cache:
        return fetch(text, url=url)
    hit = cached(text)
    if hit is not None:
        hits += 1
        return hit
    misses += 1
    return store(text, fetch(text, url=url))


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
