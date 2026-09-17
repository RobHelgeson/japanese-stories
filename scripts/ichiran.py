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
    dropped = []
    for tok in toks:
        surface = tok["surface"]
        idx = text.find(surface, pos)
        if idx < 0 or len(WORD.findall(text[pos:idx])) > sum(len(t["surface"]) for t in dropped):
            dropped.append(tok)
            continue
        if idx > pos:
            out.extend(_gap(text, pos, idx, dropped))
        out.append({**tok, "start": idx, "end": idx + len(surface)})
        pos = idx + len(surface)
        dropped = []
    if pos < len(text):
        out.append({"raw": text[pos:], "start": pos, "end": len(text)})
    return out


def _gap(text, start, end, dropped):
    """The pieces of the text a matched token skipped over.

    Punctuation, usually, and then it is one raw chunk as it has always been.
    But a gap also opens where Ichiran returned a canonical surface for what is
    written here — 熱すぎて is 熱い + すぎて, and 熱い is nowhere to be placed — and
    then the word characters in the gap are the text that token stands for. Where
    exactly one token was dropped they are given to it, with its reading, gloss
    and bases intact and `lemma` recording what Ichiran actually called it, so
    the caller can cut the reading down to what is here. Two dropped tokens share
    one gap with nothing to say where the boundary between them falls, so both
    stay lost rather than one of them being guessed.
    """
    span = text[start:end]
    hits = [m.start() for m in WORD.finditer(span)]
    if len(dropped) != 1 or not hits:
        return [{"raw": span, "start": start, "end": end}]
    lo, hi = hits[0], hits[-1] + 1
    tok = dropped[0]
    out = []
    if lo:
        out.append({"raw": span[:lo], "start": start, "end": start + lo})
    out.append({**tok, "surface": span[lo:hi], "lemma": tok["surface"],
                "start": start + lo, "end": start + hi})
    if hi < len(span):
        out.append({"raw": span[hi:], "start": start + hi, "end": end})
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
# ("raw", text) for punctuation, ("tok", surface) for a token found where it was
# expected, and (lemma, text) for one Ichiran could not place that was carried
# into the gap — so one list states what survived, what it holds, and where the
# punctuation went.
SELFTEST = [
    (
        "空が青い。",
        ["空", "が", "青い"],
        [("tok", "空"), ("tok", "が"), ("tok", "青い"), ("raw", "。")],
    ),
    (
        "「はい」と言った",
        ["はい", "と", "言った"],
        [("raw", "「"), ("tok", "はい"), ("raw", "」"), ("tok", "と"), ("tok", "言った")],
    ),
    # 熱すぎて segments as 熱い + すぎて and the text holds 熱, so the lemma is
    # unplaceable. The gap it opens is its own text, so it is given it and keeps
    # its reading, gloss and bases; `lemma` is what the caller cuts them down by.
    (
        "湯が熱すぎて",
        ["湯", "が", "熱い", "すぎて"],
        [("tok", "湯"), ("tok", "が"), ("熱い", "熱"), ("tok", "すぎて")],
    ),
    # The same lemma occurring later is the defect the budget exists for: an
    # unbounded find matches that 熱い and takes the cursor with it, orphaning
    # すぎて, 湯 and は. The gap is 5 word characters against a 2-character
    # surface, so it is refused.
    (
        "熱すぎて湯は熱い",
        ["熱い", "すぎて", "湯", "は", "熱い"],
        [("熱い", "熱"), ("tok", "すぎて"), ("tok", "湯"), ("tok", "は"), ("tok", "熱い")],
    ),
    # Dialect negatives arrive canonical too, and the text is shorter than the
    # lemma either way: くれん against くれない. Punctuation on either side of the
    # carried text stays raw, so the token is the word and nothing else.
    (
        "「通してくれん」\n嘘だ",
        ["通して", "くれない", "嘘", "だ"],
        [("raw", "「"), ("tok", "通して"), ("くれない", "くれん"), ("raw", "」\n"),
         ("tok", "嘘"), ("tok", "だ")],
    ),
    # Punctuation before the carried text splits off the same way.
    (
        "木は、大きすぎる",
        ["木", "は", "大きい", "すぎる"],
        [("tok", "木"), ("tok", "は"), ("raw", "、"), ("大きい", "大き"), ("tok", "すぎる")],
    ),
    # Kana is word text, not punctuation. いてた segments as いて + いた and the
    # text holds た, so the lemma's next real occurrence is the trap - and here
    # everything between is kana, so a guard that only counted kanji would wave
    # it through. This is インドラの網's own opening, in miniature.
    (
        "そこにいてたからいた",
        ["そこ", "に", "いて", "いた", "から", "いた"],
        [("tok", "そこ"), ("tok", "に"), ("tok", "いて"), ("いた", "た"),
         ("tok", "から"), ("tok", "いた")],
    ),
    # A drop funds the gap directly after it and nothing later. Without the reset
    # the budget accumulates down the document until the guard is inert again -
    # here the second 湯 is genuinely unplaceable, and must not be bought with
    # the slack 熱い left behind two words earlier.
    (
        "熱すぎて湯は水と湯だ",
        ["熱い", "すぎて", "湯", "は", "湯", "だ"],
        [("熱い", "熱"), ("tok", "すぎて"), ("tok", "湯"), ("tok", "は"),
         ("raw", "水と湯だ")],
    ),
    # Two tokens dropped in a row share one gap, and nothing in it says where the
    # boundary between them falls. Both stay lost rather than one being guessed.
    (
        "大き高すぎる",
        ["大きい", "高い", "すぎる"],
        [("raw", "大き高"), ("tok", "すぎる")],
    ),
]


def selftest():
    """_interleave's matching rule, over hand-built token lists. No Ichiran needed."""

    def kind(piece):
        if "raw" in piece:
            return ("raw", piece["raw"])
        if "lemma" in piece:
            return (piece["lemma"], piece["surface"])
        return ("tok", piece["surface"])

    ok = True
    for text, surfaces, want in SELFTEST:
        pieces = _interleave(text, [{"surface": x} for x in surfaces])
        got = [kind(x) for x in pieces]
        # Offsets are the whole point of the function, so check them rather than
        # trusting the surfaces: every piece must abut the last and cover the
        # text, and a carried token must hold the text its own offsets name.
        spans = [(x["start"], x["end"]) for x in pieces]
        contiguous = all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
        covered = not spans or (spans[0][0] == 0 and spans[-1][1] == len(text))
        honest = all(text[x["start"]:x["end"]] == x.get("raw", x.get("surface"))
                     for x in pieces)
        good = got == want and contiguous and covered and honest
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {text}")
        if not good:
            print(f"       want {want}")
            print(f"       got  {got}")
            print(f"       contiguous={contiguous} covered={covered} honest={honest}")
    return ok


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    for t in tokens(sys.argv[1]):
        print(f"{t['surface']}\t{t['kana']}\t{'/'.join(t['bases'])}")
