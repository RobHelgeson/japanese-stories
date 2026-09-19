"""Offline checks for everything this package decides. No Ichiran, no network.

Two kinds of case, and the split matters:

**Fixtures** are real nodes lifted out of recorded responses (`fixtures.json`),
with their gloss lists cut to one sense and nothing else touched. They are here
because a shape invented to suit the walk proves only that the walk agrees with
itself — which is exactly how a two-step conjugation went unglossed across the
whole corpus without a test noticing.

**Constructed cases** are for rules the recorded corpus cannot exercise: a
container Ichiran has never actually sent as a dict, a via chain nested deeper
than one level, an alignment budget that has to refuse a gap. They are marked
where they appear.

Run: python3 scripts/ichiran/selftest.py
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # invoked as a file rather than a module
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ichiran.model import Word
from ichiran.offsets import Placed, _share, place, spread
from ichiran.walk import flatten, read

FIXTURES = json.loads((Path(__file__).parent / "fixtures.json").read_text(encoding="utf-8"))


def _word(key):
    return Word.read(FIXTURES[key])


# (fixture, surface, ranked dictionary forms, first gloss). Each one is a rule.
FIXTURE_CASES = [
    # One step: the conj node carries its own reading and gloss.
    ("conj-one-step", "行った", ("行う",), "to perform"),
    # Two steps. The dictionary entry is down in conj[].via[], and reading it at
    # a fixed depth is what left every passive, causative and potential in the
    # corpus with an empty gloss and no lemma — 67 tokens across 8 stories.
    ("conj-via-only", "つけた", ("突く",), "to prick"),
    # A resolved sibling beside a via-only one. The via node is Ichiran's
    # competing parse of a DIFFERENT word, not the next layer of this one, and
    # merging the two put the rival verb at dictionary_forms[0] on nothing but
    # codepoint order.
    ("conj-resolved-beside-via", "片付けて", ("片付ける",), "to tidy up"),
    # Two resolved siblings ARE genuine ambiguity, and all of them survive in
    # Ichiran's order. Sorting this picks the lemma by which kana comes first in
    # Unicode.
    ("conj-two-resolved", "つけず", ("付ける", "付く", "着く"), "to attach"),
]


def fixtures():
    """The model over real recorded nodes."""
    ok = True
    for key, surface, forms, gloss_starts in FIXTURE_CASES:
        word = _word(key)
        good = (
            word.surface == surface
            and word.dictionary_forms == forms
            and word.gloss().startswith(gloss_starts)
        )
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {key}")
        if not good:
            print(f"       want {surface} {forms} {gloss_starts!r}...")
            print(f"       got  {word.surface} {word.dictionary_forms} {word.gloss()!r}")

    # An alternative group is ranked, shares one surface, and is ONE word with
    # several readings — not several words.
    alt = _word("alternative")
    good = len(alt.parses) > 1 and len({p.surface for p in alt.parses}) == 1
    good &= alt.preferred is alt.parses[0]
    good &= all(a.score >= b.score for a, b in zip(alt.parses, alt.parses[1:]))
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} alternative group is one ranked word")

    # A compound's parts carry the morphology; the compound carries the surface.
    comp = _word("compound-contracted")
    parts = flatten(comp)
    good = comp.surface == "熱すぎて" and comp.kana == "あつすぎて"
    good &= [p.surface for p in parts] == ["熱い", "すぎて"]
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} compound keeps the printed surface, parts keep the words")

    # Conjugation grammar, which nothing read before the connector existed.
    infl = _word("conj-two-resolved").preferred.inflections
    good = bool(infl) and infl[0].negative and infl[0].type == "Non-past"
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} inflection carries type and the negative flag")
    return ok


# Shapes the recorded corpus does not contain. Every one is a guard whose cost
# of being wrong is a crash or a silently truncated chain rather than one lost
# word, which is why they are asserted rather than assumed.
def _gloss(text):
    return [{"gloss": text, "pos": "[v1]"}]


CONSTRUCTED = [
    # nil serializes as []. An empty list where a string belongs is not a value.
    ("nil as []", {"text": "空", "kana": [], "reading": [], "conj": []}, "空", (), ""),
    # A dict where a list belongs. Never observed in 295 responses; an unguarded
    # walk iterates its keys and calls .get on a string, taking the whole
    # segmentation pass down.
    ("dict conj", {"text": "見て", "conj": {"reading": "見る 【みる】", "gloss": _gloss("to see")}},
     "見て", ("見る",), "to see"),
    ("dict via", {"text": "見られて", "conj": [{"via": {"reading": "見る 【みる】", "gloss": _gloss("to see")}}]},
     "見られて", ("見る",), "to see"),
    # via nests exactly one level deep in all 2,325 recorded occurrences.
    # Nothing in Ichiran's output promises that.
    ("via nested twice", {"text": "x", "conj": [{"via": [{"via": [{"reading": "書く 【かく】", "gloss": _gloss("to write")}]}]}]},
     "x", ("書く",), "to write"),
    # Zero-width glue, both characters. で‌はある is five codepoints, and a form
    # carrying one of these matches nothing anywhere.
    ("zero-width glue", {"text": "中には", "kana": "なか​には", "conj": [{"reading": "中​には 【なか​には】", "gloss": _gloss("among")}]},
     "中には", ("中には",), "among"),
    # Nothing to reduce to. None, not the surface: "no dictionary form" and
    # "the dictionary form is the surface" are different facts and stats.py
    # counts them differently.
    ("no conj", {"text": "から"}, "から", (), ""),
]


def constructed():
    ok = True
    for name, node, surface, forms, gloss in CONSTRUCTED:
        try:
            word = Word.read(node)
            got = (word.surface, word.dictionary_forms, word.gloss())
        except Exception as exc:  # a crash here is the finding, not an error
            ok = False
            print(f"  FAIL {name} raised {exc!r}")
            continue
        good = got == (surface, forms, gloss)
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {name}")
        if not good:
            print(f"       want {(surface, forms, gloss)}")
            print(f"       got  {got}")
    return ok


# (compound surface, canonical parts, characters each part covers). The
# contracted cases are the whole reason the compound is placed before it is
# split: not one of these parts is a substring of the document at its own
# position, and three of them are not substrings of it at all.
SHARE = [
    ("入っている", ["入って", "いる"], [3, 2]),            # plain: parts are literal
    ("熱すぎて", ["熱い", "すぎて"], [1, 3]),               # 熱い contracts to 熱
    ("通してくれん", ["通して", "くれない"], [3, 3]),        # くれない contracts to くれん
    ("言わなくちゃ", ["言わなくて", "は"], [4, 2]),          # は covers ちゃ, sharing no prefix
    ("こりこりしてる", ["こりこり", "して", "いる"], [4, 2, 1]),
]


def shares():
    """The compound split. Verified against all 10,541 recorded compounds."""
    ok = True
    for surface, parts, want in SHARE:
        got = _share(surface, parts)
        good = got == want and sum(got) == len(surface) and all(n > 0 for n in got)
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {surface} = {' + '.join(parts)}")
        if not good:
            print(f"       want {want}, got {got} (covers {sum(got)} of {len(surface)})")
    return ok


# (text, surfaces Ichiran returned, the pieces place() should lay down). A piece
# is ("raw", text) for punctuation and ("tok", text) for a placed word, so one
# list states what survived, what it holds, and where the punctuation went.
PLACEMENT = [
    ("空が青い。", ["空", "が", "青い"],
     [("tok", "空"), ("tok", "が"), ("tok", "青い"), ("raw", "。")]),
    ("「はい」と言った", ["はい", "と", "言った"],
     [("raw", "「"), ("tok", "はい"), ("raw", "」"), ("tok", "と"), ("tok", "言った")]),
    # The budget. An unbounded find matches the second 熱い, takes the cursor
    # with it and orphans everything between — which on インドラの網 cost 1661 of
    # 1683 tokens. A gap is crossed only when the words already dropped can
    # account for its word characters. Kana counts: a guard that charged only
    # kanji would wave this through.
    ("熱いと言ったが湯は熱い", ["熱い", "と", "言った", "が", "湯", "は", "熱い"],
     [("tok", "熱い"), ("tok", "と"), ("tok", "言った"), ("tok", "が"), ("tok", "湯"),
      ("tok", "は"), ("tok", "熱い")]),
    # A drop funds the gap directly after it. 熱い is nowhere in the text, and
    # the 熱 it stands for is charged against it.
    ("熱すぎる", ["熱い", "すぎる"],
     [("tok", "熱"), ("tok", "すぎる")]),
    # ...and nothing later. The 氷 dropped at the start must not buy the gap
    # before the second 湯, four words downstream. Without the reset the budget
    # accumulates until the guard is inert a few drops into any real document —
    # and that version passes every case written before this one.
    ("湯は水と湯だ", ["氷", "湯", "は", "湯", "だ"],
     [("tok", "湯"), ("tok", "は"), ("raw", "水と湯だ")]),
]


def placement():
    ok = True
    for text, surfaces, want in PLACEMENT:
        words = [Word.read({"text": s}) for s in surfaces]
        pieces = place(text, words)
        got = [("tok", p.text) if isinstance(p, Placed) else ("raw", p.text) for p in pieces]
        # Offsets are the point of the function, so check them rather than
        # trusting the surfaces: every piece abuts the last, the text is
        # covered, and a piece holds the text its own offsets name.
        spans = [(p.start, p.end) for p in pieces]
        contiguous = all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
        covered = not spans or (spans[0][0] == 0 and spans[-1][1] == len(text))
        honest = all(text[p.start:p.end] == p.text for p in pieces)
        good = got == want and contiguous and covered and honest
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {text}")
        if not good:
            print(f"       want {want}")
            print(f"       got  {got}")
            print(f"       contiguous={contiguous} covered={covered} honest={honest}")
    return ok


def spreading():
    """A compound placed whole, then split over the text it actually covers."""
    doc_text = "湯が熱すぎて飲めない"
    word = _word("compound-contracted")
    pieces = place(doc_text, [Word.read({"text": "湯"}), Word.read({"text": "が"}), word])
    parts = [p for piece in pieces if isinstance(piece, Placed) for p in spread(piece)]
    got = [(p.text, p.start, p.end) for p in parts]
    want = [("湯", 0, 1), ("が", 1, 2), ("熱", 2, 3), ("すぎて", 3, 6)]
    good = got == want
    # The point of spreading: 熱 is placed, and it still knows what it was cut
    # from. The compound, not the component — 熱すぎて and あつすぎて cover exactly
    # the text that was printed, so a caller slices that at offset 0 and gets あつ.
    # The component's own 熱い/あつい describes a word the document does not hold,
    # which is why `canonical` is None here and a cut is not needed.
    carried = next((p for p in parts if p.text == "熱"), None)
    good &= carried is not None and carried.part_of == ("熱すぎて", "あつすぎて", 0)
    good &= carried is not None and carried.canonical is None
    print(f"  {'ok  ' if good else 'FAIL'} 熱すぎて placed whole, split into 熱 + すぎて")
    if not good:
        print(f"       want {want}")
        print(f"       got  {got}")
    return good


# (surface, kana as Ichiran sends it, the reading it has to become). A compound's
# kana is its parts' readings with separators between them, and 熱すぎて having none
# is why one example read as a general rule. Measured over the 384 recorded
# responses: 2,376 of 11,051 compound parses carry a space, 0 of 275,650
# non-compound parses do.
READINGS = [
    # Separator at a component boundary that is also a kanji/okurigana boundary.
    ("廃業する", "はいぎょう する", "はいぎょうする"),
    # No kana anchor before the separator: alignment cannot recover from this one,
    # it bails to a single unsplit pair and the token ships with no reading.
    ("頼ろうとする", "たよろう とする", "たよろうとする"),
    # Separator interior to the surface, so the space lands at the HEAD of a later
    # kanji run's ruby — 来《 き》 — which truncate() accepts rather than refuses.
    # The only class of the three that ships looking correct.
    ("行ったり来たり", "いったり きたり", "いったりきたり"),
    # Zero-width glue sitting against the separator: 358 recorded kana hold both,
    # and 18,274 hold zero-width with no space at all. The case is here because a
    # reading needs BOTH cleanups, not because they have an order — `.split()`
    # discards whitespace runs and `translate` removes zero-width, over disjoint
    # characters, so the two commute and either order is correct.
    # What fails is doing only one of them: `raw.replace(" ", "")` takes the space
    # and leaves the non-joiner welded to ところ, shipping 所《ところ‌》. That is
    # the reimplementation this case exists to catch.
    ("所へ", "ところ ‌へ", "ところへ"),
    # Controls: nothing to join, and the value must survive untouched.
    ("熱すぎて", "あつすぎて", "あつすぎて"),
    ("青い", "あおい", "あおい"),
]


def readings():
    """A compound's kana arrives separated, and has to be joined to be a reading."""
    ok = True
    for surface, sent, want in READINGS:
        got = Word.read({"text": surface, "kana": sent}).preferred.kana
        good = got == want
        ok &= good
        note = "" if sent == want else "  (separated)"
        print(f"  {'ok  ' if good else 'FAIL'} {surface} reads {want}{note}")
        if not good:
            print(f"       sent {sent!r} -> got {got!r}, want {want!r}")
    return ok


def response_shape():
    """The chunk nesting, including the shapes a bad response can arrive in."""
    ok = True
    # ["romaji", word, []] — the third element is empty in all 195,278 recorded
    # triples and is NOT the alternatives list it looks like.
    doc = read([" ", [[[["sora", {"text": "空", "kana": "そら"}, []]], 12]], "。"])
    good = [w.surface for w in doc.words] == ["空"] and len(doc.chunks) == 3
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} chunks, runs and the word triple")

    for name, bad in [("not a list", {"nope": 1}), ("empty", []),
                      ("malformed run", [[[]]]), ("run without words", [[["x"]]])]:
        try:
            words = read(bad).words
            good = words == ()
        except Exception as exc:
            good = False
            print(f"  FAIL {name} raised {exc!r}")
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {name} yields no words rather than raising")
    return ok


def main():
    groups = [
        ("recorded shapes", fixtures),
        ("shapes the corpus does not contain", constructed),
        ("compound split", shares),
        ("placement", placement),
        ("placement then split", spreading),
        ("compound readings", readings),
        ("response shape", response_shape),
    ]
    ok = True
    for title, fn in groups:
        print(f"\n{title}")
        ok &= bool(fn())
    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
