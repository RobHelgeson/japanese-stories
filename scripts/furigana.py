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


if __name__ == "__main__":
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
        print(s, "->", align(s, r))
