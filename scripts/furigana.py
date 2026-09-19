"""Align a word's kana reading onto its kanji runs, and read the source markup."""

import re

KANA = re.compile(r"[ぁ-ゖァ-ヺーｰ]")

# ｜漢字《かな》, the story sources' furigana markup. Two shapes: with the ｜ marker
# the annotated run may contain kana (｜真ん中《まんなか》, ｜申し込む《もうしこむ》),
# because the marker says where it starts; without one, the run must be pure
# kanji or it would swallow the kana either side of it. align() below already
# handles a kana infix, so the marker form needs no special case downstream.
MARKUP = re.compile(
    r"｜([^《｜\n]+)《([ぁ-ゖァ-ヺー]+)》"
    r"|([一-鿿々]+)《([ぁ-ゖァ-ヺー]+)》"
)


def pair(m):
    """(surface, reading) from either alternative of MARKUP."""
    return (m.group(1) or m.group(3), m.group(2) or m.group(4))


def _misaligned(surface, reading):
    """True when a marker run holds both kinds of character and will not split.

    align() places a reading by matching the surface's own kana against it, so a
    mixed run that still comes back as one unsplit pair is a run whose kana are
    not in its reading. That is what over-capture looks like: どこにも見 with the
    reading み. A legitimate marker form always splits, because the kana it spans
    are the head of its own reading — ｜この家《このいえ》 anchors この and leaves
    家 to いえ, ｜真ん中《まんなか》 anchors the ん infix.

    A pure-kanji or pure-kana run is one run and cannot split, so it is not asked
    to: ｜見《み》 is a redundant marker, not a fault.
    """
    runs = _runs(surface)
    if len({kana for kana, _ in runs}) < 2:
        return False
    return len(align(surface, reading)) == 1


def stray_markers(line):
    """Character offsets of every ｜ in `line` that opens no sound annotation.

    Two faults, because a ｜ has two ways to go wrong and only one of them is
    visible in the output.

    **A ｜ that matches nothing.** MARKUP's marker alternative is
    ｜([^《｜\\n]+)《…》, whose run may not contain a second ｜ and may not cross a
    newline. ｜どこにも has no 《》 to close it and ｜そのままにしておいた。 runs to
    the end of the line, so neither matches — and because neither strip() nor
    parse() has an else branch, an unmatched ｜ is not a warning and not a
    counter. It is copied through as ordinary text, reaches ichiran.align() and
    is emitted as a token, so a literal ｜ ships into the published reader.

    **A ｜ that matches too much.** Group 1 is greedy and forbids only a second
    ｜, so a stray marker standing before kana swallows whatever 《kana》 comes
    next on the line: ｜どこにも見《み》えなく matches as a single annotation with
    the run どこにも見 and the reading み, and the reader gets ruby み set over
    five characters. Nothing is lost and nothing looks broken, which is why this
    is the worse of the two. _misaligned() above is the test.

    That second shape is why "every ｜ is the start of a MARKUP match" is not the
    predicate, though it is tempting and it was the first one written here. It is
    exact for the question it asks — ｜ cannot occur anywhere else inside a match,
    since group 1 excludes it, group 3 is kanji and both readings are kana — but
    that question is not the fault. The corpus's two real faults were reported by
    it only because each happened to carry a second ｜ that blocked the greedy
    run; removing that second ｜ made the line worse and the check silent.

    Neither shape may fire on the legitimate marker form, which is the whole
    reason the marker exists: ｜この家《このいえ》 and ｜そこに立《そこにた》
    annotate a run that starts with kana, and the bare-kanji alternative could
    not reach them. They match, and they align, so they are not reported.

    This lives here because furigana.py is the only module that owns the markup
    grammar: build.py, check.py and stats.py all reach markup through strip() and
    parse(), so one predicate beside MARKUP covers every consumer.
    """
    opens, bad = set(), []
    for m in MARKUP.finditer(line):
        if m.group(1) is None:
            continue
        opens.add(m.start())
        if _misaligned(m.group(1), m.group(2)):
            bad.append(m.start())
    bad += [i for i, c in enumerate(line) if c == "｜" and i not in opens]
    return sorted(bad)


def strip(text):
    """Markup removed, leaving the bare text a parser should see."""
    return MARKUP.sub(lambda m: pair(m)[0], text)


def parse(line):
    """(plain line, {offset in plain line: (surface, reading)})."""
    plain, authored, pos, last = [], {}, 0, 0
    for m in MARKUP.finditer(line):
        plain.append(line[last : m.start()])
        pos += m.start() - last
        surface, reading = pair(m)
        authored[pos] = (surface, reading)
        plain.append(surface)
        pos += len(surface)
        last = m.end()
    plain.append(line[last:])
    return "".join(plain), authored


def _to_hira(s):
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s
    )


def _runs(surface):
    """Surface split into alternating (is_kana, text) runs."""
    out = []
    for ch in surface:
        kana = bool(KANA.match(ch))
        if out and out[-1][0] == kana:
            out[-1][1] += ch
        else:
            out.append([kana, ch])
    return [(k, t) for k, t in out]


def align(surface, reading):
    """[(text, ruby_or_None)] pairs covering `surface`.

    Kana in the surface anchors the alignment; whatever falls between anchors is
    the reading of the kanji run there. Returns a single unsplit pair when the
    reading cannot be matched, so a bad alignment never silently mislabels kanji.
    """
    reading = _to_hira(reading or "")
    runs = _runs(surface)
    if not reading or not any(not k for k, _ in runs):
        return [(surface, None)]

    hira_runs = [(k, _to_hira(t)) for k, t in runs]

    def solve(i, pos):
        if i == len(runs):
            return [] if pos == len(reading) else None
        is_kana, text = runs[i]
        hira = hira_runs[i][1]
        if is_kana:
            if not reading.startswith(hira, pos):
                return None
            rest = solve(i + 1, pos + len(hira))
            return None if rest is None else [(text, None)] + rest
        # Kanji run: try the shortest reading first, longest last.
        last = i == len(runs) - 1
        for end in range(pos + 1, len(reading) + 1):
            if last and end != len(reading):
                continue
            rest = solve(i + 1, end)
            if rest is not None:
                return [(text, reading[pos:end])] + rest
        return None

    return solve(0, 0) or [(surface, reading)]


def portion(pairs, start, end):
    """The part of `pairs` covering `[start, end)` of the text they align.

    For a compound's component. The compound node is the one that knows both what
    was printed and how the whole of it reads — 熱すぎて and あつすぎて — so
    aligning THAT and taking the slice at the component's offset gives each part
    its own reading directly. 熱 gets あつ because あつ is what sits over 熱 in the
    compound's own alignment, not because あつい was cut down to fit.

    That is the difference from `truncate`, which is given a reading for a word
    the document does not contain and has to shorten it. Here nothing is
    shortened: the alignment already covers exactly the printed text, and this
    reads a span out of it.

    Returns (pairs, kana), or None when the boundary falls inside a kanji run —
    its reading covers the whole run and cannot be apportioned across it, which is
    the same refusal `truncate` makes and for the same reason.
    """
    out, at = [], 0
    for text, ruby in pairs:
        lo, hi = at, at + len(text)
        at = hi
        if hi <= start or lo >= end:
            continue
        if lo >= start and hi <= end:
            out.append((text, ruby))
            continue
        # Straddles a boundary. Only a kana run can be split, because its reading
        # is its own text; a kanji run's ruby covers the run and nothing says how
        # to divide it.
        if ruby is not None:
            return None
        cut = text[max(start - lo, 0):min(end - lo, len(text))]
        if cut:
            out.append((cut, None))
    if not out:
        return None
    return out, _to_hira("".join(t if r is None else r for t, r in out))


def truncate(pairs, text):
    """`pairs` cut down to `text`, a shorter run starting at the same place.

    Ichiran hands back a canonical surface for some inflections — 熱すぎて comes
    back as 熱い + すぎて — so the reading was aligned to a word the document does
    not contain, and the pairs cover more than the text sitting here. What the
    text holds is the stem, which is the canonical minus its okurigana; okurigana
    is kana, so the cut lands in a kana run and every kanji reading either
    survives whole or the cut is refused. 熱い/あつい cut to 熱 is 熱《あつ》, and
    大きい/おおきい cut to 大き is 大《おお》き.

    Returns (pairs, kana), or None when the cut cannot be made honestly: through
    a kanji run, whose reading covers the run and cannot be apportioned across
    it, or against text that is not what these pairs start with.
    """
    out, kana, i = [], [], 0
    for surface, reading in pairs:
        if i >= len(text):
            break
        take = text[i : i + len(surface)]
        if take == surface:
            out.append((surface, reading))
            kana.append(surface if reading is None else reading)
            i += len(surface)
            continue
        if reading is not None or not surface.startswith(take):
            return None
        out.append((take, None))
        kana.append(take)
        i += len(take)
        break
    if i != len(text) or not out:
        return None
    return out, _to_hira("".join(kana))


# (canonical surface, its reading, the text actually written, expected cut). The
# first five are the corpus's own carried tokens; the rest are the refusals.
TRUNCATE_SELFTEST = [
    ("熱い", "あつい", "熱", ([("熱", "あつ")], "あつ")),
    ("薄い", "うすい", "薄", ([("薄", "うす")], "うす")),
    ("大きい", "おおきい", "大き", ([("大", "おお"), ("き", None)], "おおき")),
    # A contraction is not a prefix: くれない and くれん agree for two characters
    # and then do not. Nothing here can say what ん reads as, so nothing is said.
    ("くれない", "くれない", "くれん", None),
    ("おらない", "おらない", "おらん", None),
    # The cut may land in a kana run or on a run boundary, never inside a kanji
    # run - おとな covers 大人 as a unit and does not divide across it.
    ("大きい", "おおきい", "大", ([("大", "おお")], "おお")),
    ("大人しい", "おとなしい", "大", None),
    ("大人しい", "おとなしい", "大人", ([("大人", "おとな")], "おとな")),
    # Text the pairs do not start with, and text longer than they cover.
    ("熱い", "あつい", "寒", None),
    ("熱い", "あつい", "熱いもの", None),
    ("熱い", "あつい", "", None),
]


# (line, the offsets stray_markers should report). The first two are the corpus's
# two real faults, trimmed; the next two are the legitimate marker-form
# annotations they must not be confused with, both of which span a kana prefix
# and are exactly why the marker form exists.
MARKER_SELFTEST = [
    ("｜道《みち》が｜どこにも｜見《み》えなくなっていた。", [7]),
    ("｜向《む》きも、｜そのままにしておいた。", [8]),
    ("｜この家《このいえ》は｜私《わたし》のものになった。", []),
    ("｜そこに立《そこにた》っていた。", []),
    # A marker with no 《》 anywhere after it, and a doubled marker: the first is
    # what an unfinished annotation looks like, the second what a stray keystroke
    # looks like. Neither can match, and both used to be silent.
    ("｜どこにも", [0]),
    ("｜｜見《み》る", [0]),
    # The over-capture, which is the same two faults with the blocking ｜ removed.
    # These match, so an offsets-of-unmatched-｜ predicate reports nothing and the
    # reader gets み set over five characters. This is the worse shape and the
    # only one with no visible symptom.
    ("｜道《みち》が｜どこにも見《み》えなくなっていた。", [7]),
    ("｜向《む》きも、｜そのままに見《み》ておいた。", [8]),
    ("｜どこにも見《み》えなくなっていた。", [0]),
    # Legitimate mixed runs, which over-capture detection must leave alone: a
    # kana prefix, a kana infix and a kana suffix. MARKUP's own comment names the
    # last two as the reason the marker form accepts kana at all.
    ("｜真ん中《まんなか》に立っていた。", []),
    ("｜申し込む《もうしこむ》ことにした。", []),
    ("｜お母《おかあ》さんが呼んでいる。", []),
    # The bare-kanji alternative carries no marker and must not be asked for one.
    ("見《み》える。", []),
    ("そのままにしておいた。", []),
]


def selftest():
    """align() on the demo set, truncate()'s cuts and refusals, then stray ｜."""
    for s, r in [
        ("引き出し", "ひきだし"),
        ("暮らして", "くらして"),
        ("電灯をつけた", "でんとうをつけた"),
        ("時計", "とけい"),
        ("真夜中", "まよなか"),
        ("懐かしい", "なつかしい"),
        ("おじいさん", "おじいさん"),
        ("見つめる", "みつめる"),
    ]:
        print(f"  align   {s} -> {align(s, r)}")
    ok = True
    for surface, reading, text, want in TRUNCATE_SELFTEST:
        got = truncate(align(surface, reading), text)
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} truncate {surface}/{reading} to {text!r} -> {got}")
        if not good:
            print(f"       want {want}")
    for line, want in MARKER_SELFTEST:
        got = stray_markers(line)
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} stray ｜ in {line} -> {got}")
        if not good:
            print(f"       want {want}")
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if selftest() else 1)  # --selftest accepted; there is no other mode
