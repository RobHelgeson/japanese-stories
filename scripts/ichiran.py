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
# Kana and kanji together: what may never turn up in the gap between two
# tokens, because Ichiran drops punctuation and never a word. See _interleave().
WORD = re.compile(r"[ぁ-ゖァ-ヺーｰ㐀-䶿一-鿿豈-﫿々]")
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


def _interleave(text, toks):
    """align() over an explicit token list, so the matching rule is testable offline.

    A token's surface is usually a literal substring of the text at the cursor,
    but not always: Ichiran returns a canonical surface for some inflections, so
    熱すぎて comes back as 熱い + すぎて while the text holds 熱, and くれん comes
    back as くれない. The lemma is not there to be found, and `str.find` happily
    locates the next real 熱い a thousand characters downstream - which drags the
    cursor past everything in between and orphans every token in it. Dropping the
    token costs one word; letting the cursor move costs the rest of the document.

    So a gap is crossed only when the tokens already dropped can account for it.
    Punctuation is free, because Ichiran drops it by design and the raw chunks
    exist to carry it; word characters are charged against the surfaces dropped
    since the last match, which is exactly the text a canonical surface stands in
    for. Measured before this guard, インドラの網 aligned 22 of its 1683 tokens
    and the reference set as a whole aligned 78.3%.
    """
    out = []
    pos = 0
    slack = 0
    for tok in toks:
        surface = tok["surface"]
        idx = text.find(surface, pos)
        if idx < 0 or len(WORD.findall(text[pos:idx])) > slack:
            slack += len(surface)
            continue
        if idx > pos:
            out.append({"raw": text[pos:idx], "start": pos, "end": idx})
        out.append({**tok, "start": idx, "end": idx + len(surface)})
        pos = idx + len(surface)
        slack = 0
    if pos < len(text):
        out.append({"raw": text[pos:], "start": pos, "end": len(text)})
    return out


def align(text):
    """Tokens interleaved with the punctuation Ichiran drops, each with offsets.

    Segmentation is one round trip per call and Ichiran is not fast, so callers
    pass the whole document at once and slice the result by offset.
    """
    return _interleave(text, tokens(text))


def has_kanji(s):
    return bool(KANJI.search(s))


# (text, Ichiran's surfaces, the pieces _interleave should lay down). A piece is
# a token's surface or a raw run, in document order, so one list states both what
# survived and where the punctuation went.
SELFTEST = [
    (
        "空が青い。",
        ["空", "が", "青い"],
        ["空", "が", "青い", "。"],
    ),
    (
        "「はい」と言った",
        ["はい", "と", "言った"],
        ["「", "はい", "」", "と", "言った"],
    ),
    # 熱すぎて segments as 熱い + すぎて and the text holds 熱, so the lemma is
    # unplaceable. It is dropped, 熱 falls through as raw, and すぎて still lands
    # on its own offset - the cost is one token, not the tail of the document.
    (
        "湯が熱すぎて",
        ["湯", "が", "熱い", "すぎて"],
        ["湯", "が", "熱", "すぎて"],
    ),
    # The same lemma occurring later is the defect this guard exists for: an
    # unbounded find matches that 熱い and takes the cursor with it, orphaning
    # すぎて, 湯 and は. The gap is 5 word characters against a 2-character
    # surface, so it is refused.
    (
        "熱すぎて湯は熱い",
        ["熱い", "すぎて", "湯", "は", "熱い"],
        ["熱", "すぎて", "湯", "は", "熱い"],
    ),
    # Dialect negatives arrive canonical too, and the text is shorter than the
    # lemma either way: くれん against くれない, with 」 and a newline free.
    (
        "「通してくれん」\n嘘だ",
        ["通して", "くれない", "嘘", "だ"],
        ["「", "通して", "くれん」\n", "嘘", "だ"],
    ),
    # Kana is word text, not punctuation. いてた segments as いて + いた and the
    # text holds た, so the lemma's next real occurrence is the trap - and here
    # everything between is kana, so a guard that only counted kanji would wave
    # it through. This is インドラの網's own opening, in miniature.
    (
        "そこにいてたからいた",
        ["そこ", "に", "いて", "いた", "から", "いた"],
        ["そこ", "に", "いて", "た", "から", "いた"],
    ),
    # A drop funds the gap directly after it and nothing later. Without the reset
    # the budget accumulates down the document until the guard is inert again -
    # here the second 湯 is genuinely unplaceable, and must not be bought with
    # the slack 熱い left behind two words earlier.
    (
        "熱すぎて湯は水と湯だ",
        ["熱い", "すぎて", "湯", "は", "湯", "だ"],
        ["熱", "すぎて", "湯", "は", "水と湯だ"],
    ),
    # Two drops in a row fund one gap between them: 大きい and 高い are both
    # unplaceable, and 3 word characters is within their 5 of slack.
    (
        "大き高すぎる",
        ["大きい", "高い", "すぎる"],
        ["大き高", "すぎる"],
    ),
]


def selftest():
    """_interleave's matching rule, over hand-built token lists. No Ichiran needed."""
    ok = True
    for text, surfaces, want in SELFTEST:
        pieces = _interleave(text, [{"surface": s} for s in surfaces])
        got = [p.get("raw", p.get("surface")) for p in pieces]
        # Offsets are the whole point of the function, so check them rather than
        # trusting the surfaces: every piece must abut the last and cover the text.
        spans = [(p["start"], p["end"]) for p in pieces]
        contiguous = all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
        covered = not spans or (spans[0][0] == 0 and spans[-1][1] == len(text))
        good = got == want and contiguous and covered
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {text}")
        if not good:
            print(f"       want {want}")
            print(f"       got  {got}  contiguous={contiguous} covered={covered}")
    return ok


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    for t in tokens(sys.argv[1]):
        print(f"{t['surface']}\t{t['kana']}\t{'/'.join(t['bases'])}")
