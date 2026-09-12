"""Ichiran segmentation: text -> flat token list with readings and base forms."""

import json
import os
import re
import urllib.request

import cache

# No default: the server is whatever host runs Ichiran, and hardcoding one would
# put a private network address in a public repo. Comma-separate for a fallback —
# python's resolver misses mDNS, so an mDNS name wants a bare IP after it.
ENV = "ICHIRAN_URL"
KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々]")
READING_BASE = re.compile(r"^(.+?)\s*【(.+?)】$")


def _urls():
    raw = os.environ.get(ENV, "").strip()
    if not raw:
        raise RuntimeError(
            f"{ENV} is not set. Point it at an Ichiran server, e.g.\n"
            f"  export {ENV}=http://localhost:3005\n"
            "See README.md — Ichiran is required for segmentation."
        )
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


def _fetch(text):
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


def segment(text):
    """Cached segmentation. Only a text this machine has never seen hits Ichiran."""
    return cache.through(text, _fetch)


def _base_forms(entry):
    """Dictionary forms this entry could reduce to, from its conjugation chain."""
    out = set()
    for c in entry.get("conj") or []:
        m = READING_BASE.match(c.get("reading", ""))
        if m:
            out.add(m.group(1).strip())
        elif c.get("reading"):
            out.add(c["reading"].strip())
        out |= _base_forms(c.get("via", {}) if isinstance(c.get("via"), dict) else {})
    return out


def _walk(node, out):
    """Collect leaf word entries in reading order from Ichiran's nested output."""
    if isinstance(node, dict):
        if "components" in node:
            for c in node["components"]:
                _walk(c, out)
            return
        if "alternative" in node:
            _walk(node["alternative"][0], out)
            return
        if "text" in node:
            out.append(node)
        return
    if isinstance(node, list):
        for item in node:
            # Word entries arrive as ["romaji", {...}, [alternatives]]
            if (
                isinstance(item, list)
                and len(item) == 3
                and isinstance(item[0], str)
                and isinstance(item[1], dict)
            ):
                _walk(item[1], out)
            else:
                _walk(item, out)


def tokens(text):
    """Return [{surface, kana, bases}] for the Japanese runs in `text`."""
    entries = []
    _walk(segment(text), entries)
    out = []
    for e in entries:
        surface = e.get("text", "")
        if not surface:
            continue
        glosses = []
        for g in e.get("gloss") or []:
            glosses.append(g.get("gloss", ""))
        for c in e.get("conj") or []:
            for g in c.get("gloss") or []:
                glosses.append(g.get("gloss", ""))
        out.append(
            {
                "surface": surface,
                "kana": (e.get("kana") or "").replace("\u200c", ""),
                "bases": sorted(_base_forms(e)) or [surface],
                "gloss": "; ".join(dict.fromkeys(g for g in glosses if g))[:120],
            }
        )
    return out


def align(text):
    """Tokens interleaved with the punctuation Ichiran drops, each with offsets.

    Segmentation is one round trip per call and Ichiran is not fast, so callers
    pass the whole document at once and slice the result by offset.
    """
    out = []
    pos = 0
    for tok in tokens(text):
        idx = text.find(tok["surface"], pos)
        if idx < 0:
            continue
        if idx > pos:
            out.append({"raw": text[pos:idx], "start": pos, "end": idx})
        out.append({**tok, "start": idx, "end": idx + len(tok["surface"])})
        pos = idx + len(tok["surface"])
    if pos < len(text):
        out.append({"raw": text[pos:], "start": pos, "end": len(text)})
    return out


def has_kanji(s):
    return bool(KANJI.search(s))


if __name__ == "__main__":
    import sys

    for t in tokens(sys.argv[1]):
        print(f"{t['surface']}\t{t['kana']}\t{'/'.join(t['bases'])}")
