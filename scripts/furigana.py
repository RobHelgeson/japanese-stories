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


def _pair(m):
    """(surface, reading) from either alternative of MARKUP."""
    return (m.group(1) or m.group(3), m.group(2) or m.group(4))


def strip(text):
    """Markup removed, leaving the bare text a parser should see."""
    return MARKUP.sub(lambda m: _pair(m)[0], text)


def parse(line):
    """(plain line, {offset in plain line: (surface, reading)})."""
    plain, authored, pos, last = [], {}, 0, 0
    for m in MARKUP.finditer(line):
        plain.append(line[last : m.start()])
        pos += m.start() - last
        surface, reading = _pair(m)
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


def selftest():
    """align() on the demo set, then truncate()'s cuts and its refusals."""
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
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if selftest() else 1)  # --selftest accepted; there is no other mode
