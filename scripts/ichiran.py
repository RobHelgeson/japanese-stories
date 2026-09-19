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
# Ichiran joins some readings with a zero-width character: で‌はある is five
# codepoints, not four, and 時には's reading carries a zero-width space. They
# are invisible in every context this project has — a base form that holds one
# silently fails to match a known word, and a kana reading that holds one
# renders it inside the furigana. Strip at the boundary so nothing downstream
# has to know they exist.
ZERO_WIDTH = re.compile(r"[​‌‍﻿]")


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


def _children(node, key):
    """`conj` or `via` as a list of nodes, whatever container Ichiran sent.

    Every cached response holds a list, but the guard the first version of
    _base_forms carried says a bare dict was seen at least once. Iterating a
    dict yields its keys, so an unguarded walk calls .get on a string and takes
    the whole segmentation pass down instead of degrading to one lost word.
    """
    child = node.get(key)
    if isinstance(child, dict):
        return [child]
    return [c for c in (child or []) if isinstance(c, dict)]


def _resolved(step):
    """Whether a conjugation step carries its own entry rather than delegating."""
    return bool(step.get("reading") or step.get("gloss"))


def _chain(entry):
    """The conjugation steps that describe this entry, Ichiran's order kept.

    One step hangs its reading and gloss on the `conj` node itself, so 過ぎて
    carries 過ぎる 【すぎる】 right there. A second step pushes the dictionary
    entry down into that step's `via`: 描かれて is the te-form of the passive of
    描く, and only `conj[0].via[0]` knows the word is 描く or that it means "to
    draw". Reaching in at a fixed depth is what used to lose every passive,
    causative and potential in the corpus.

    But `via` is also where Ichiran parks a competing parse of a *different*
    word, and that is the trap. 折れ is 折れる, and it is equally the potential of
    折る — Ichiran gives the first its own reading and leaves the second to a
    via-only sibling. Merging the two makes 折る a base form of 折れる, and since
    callers read bases[0] as the dictionary form, the wrong verb wins on nothing
    but sort order. So a sibling that resolved directly is Ichiran's answer and
    the via-only siblings beside it are dropped; `via` is read only when no
    sibling resolved, which is exactly the genuine multi-step case.

    Order is Ichiran's own ranking and is load-bearing — see _base_forms.
    """
    steps = _children(entry, "conj")
    direct = [c for c in steps if _resolved(c)]
    for step in direct or steps:
        yield step
        if not _resolved(step):
            for node in _children(step, "via"):
                yield node
                yield from _chain(node)


def _base_forms(chain):
    """Dictionary forms from an already-walked chain, best parse first.

    Ranked, not sorted. Where a surface is genuinely ambiguous — 片付け is both
    片付ける and 片付く — Ichiran orders the parses by score and bases[0] is read
    downstream as *the* dictionary form. Sorting that by codepoint picked the
    lemma by which kana happens to come first in Unicode.
    """
    out = []
    for node in chain:
        m = READING_BASE.match(node.get("reading", "") or "")
        form = m.group(1).strip() if m else (node.get("reading") or "").strip()
        form = ZERO_WIDTH.sub("", form)
        if form and form not in out:
            out.append(form)
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
        chain = list(_chain(e))
        glosses = []
        for g in e.get("gloss") or []:
            glosses.append(g.get("gloss", ""))
        for node in chain:
            for g in node.get("gloss") or []:
                glosses.append(g.get("gloss", ""))
        out.append(
            {
                "surface": surface,
                "kana": ZERO_WIDTH.sub("", e.get("kana") or ""),
                "bases": _base_forms(chain) or [surface],
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

# Conjugation shapes, trimmed from recorded Ichiran responses. The glosses are
# cut to one sense each; nothing else is edited, because the point is that the
# walk reads the real nesting rather than a shape convenient to it.
def _g(text):
    return [{"gloss": text}]


CHAIN_SELFTEST = [
    # One step: reading and gloss sit on the conj node itself.
    (
        "過ぎて",
        {"conj": [{"reading": "過ぎる 【すぎる】", "gloss": _g("to pass through")}]},
        ["過ぎる"],
        "to pass through",
    ),
    # Two steps: te-form of the passive, so only conj[0].via[0] knows the word.
    # Reaching in at a fixed depth is what left every passive glossless.
    (
        "描かれて",
        {"conj": [{"via": [{"reading": "描く 【えがく】", "gloss": _g("to draw")}]}]},
        ["描く"],
        "to draw",
    ),
    # A resolved sibling beside a via-only one: 折れ is 折れる, and equally the
    # potential of 折る. Ichiran ranked 折れる first by giving it its own reading,
    # so 折る is a competing parse and must not become a base form of it.
    (
        "折れ",
        {"conj": [
            {"reading": "折れる 【おれる】", "gloss": _g("to break")},
            {"via": [{"reading": "折る 【おる】", "gloss": _g("to fold")}]},
        ]},
        ["折れる"],
        "to break",
    ),
    # Two resolved siblings are genuine ambiguity, and both survive — in
    # Ichiran's order, which is why bases is ranked rather than sorted. Sorting
    # puts 片付く first on nothing but く sorting before け.
    (
        "片付け",
        {"conj": [
            {"reading": "片付ける 【かたづける】", "gloss": _g("to tidy up")},
            {"reading": "片付く 【かたづく】", "gloss": _g("to be put in order")},
        ]},
        ["片付ける", "片付く"],
        "to tidy up; to be put in order",
    ),
    # A dict where a list is expected must not take the segmentation pass down.
    ("dict via", {"conj": [{"via": {"reading": "見る 【みる】", "gloss": _g("to see")}}]},
     ["見る"], "to see"),
    ("dict conj", {"conj": {"reading": "見る 【みる】", "gloss": _g("to see")}},
     ["見る"], "to see"),
    # Zero-width joins are invisible and load-bearing: で‌はある holds a U+200C
    # and 時には's reading a U+200B. One makes a base form unmatchable against
    # the known-word set, the other renders inside the furigana.
    (
        "zero-width",
        {"conj": [{"reading": "で‌は​ある", "gloss": _g("to be")}]},
        ["ではある"],
        "to be",
    ),
    # Nothing to reduce to: the caller falls back to the surface.
    ("no conj", {}, [], ""),
]


def chain_selftest():
    """_chain / _base_forms over recorded conj shapes. No Ichiran needed."""
    ok = True
    for name, entry, want_bases, want_gloss in CHAIN_SELFTEST:
        try:
            chain = list(_chain(entry))
            bases = _base_forms(chain)
            gloss = "; ".join(dict.fromkeys(
                g.get("gloss", "") for n in chain for g in n.get("gloss") or []
            ))
        except Exception as exc:  # a crash here is the finding, not an error
            ok = False
            print(f"  FAIL {name} raised {exc!r}")
            continue
        good = bases == want_bases and gloss == want_gloss
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {name}")
        if not good:
            print(f"       want {want_bases} / {want_gloss!r}")
            print(f"       got  {bases} / {gloss!r}")
    return ok


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
        sys.exit(0 if all([chain_selftest(), selftest()]) else 1)
    for t in tokens(sys.argv[1]):
        print(f"{t['surface']}\t{t['kana']}\t{'/'.join(t['bases'])}")
