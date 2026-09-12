"""Read-through cache for Ichiran segmentation, keyed on text content.

Segmentation is the only slow step in a build: roughly a minute per story, over
the network, to a service that must be running. Everything else in the pipeline
is local and sub-second.

Keyed on sha256 of the exact text, which gives the invalidation the corpus needs
for free. Segmentation depends only on the text, and validation depends only on
the vocabulary, so the two never invalidate each other: maturing cards in Anki
re-runs validation without re-segmenting anything, and editing one story leaves
every other story's cache intact. That separation is what keeps a rebuild cheap
as the number of stories grows.
"""

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, ".segcache")

hits = 0
misses = 0


def _path(text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    return os.path.join(DIR, f"{digest}.json")


def get(text):
    path = _path(text)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None  # A truncated entry is a miss, not a crash.


def put(text, value):
    os.makedirs(DIR, exist_ok=True)
    tmp = _path(text) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    os.replace(tmp, _path(text))  # Atomic, so an interrupted write cannot poison the cache.
    return value


def through(text, compute):
    """Return the cached segmentation for `text`, computing it on a miss."""
    global hits, misses
    cached = get(text)
    if cached is not None:
        hits += 1
        return cached
    misses += 1
    return put(text, compute(text))


def stats():
    return f"segmentation cache: {hits} hit, {misses} miss"


def clear():
    if not os.path.isdir(DIR):
        return 0
    n = 0
    for name in os.listdir(DIR):
        if name.endswith((".json", ".tmp")):
            os.remove(os.path.join(DIR, name))
            n += 1
    return n


if __name__ == "__main__":
    import sys

    if "--clear" in sys.argv:
        print(f"removed {clear()} entries")
    else:
        n = len(os.listdir(DIR)) if os.path.isdir(DIR) else 0
        size = sum(os.path.getsize(os.path.join(DIR, f)) for f in os.listdir(DIR)) if n else 0
        print(f"{n} entries, {size / 1e6:.1f}MB in {DIR}")
