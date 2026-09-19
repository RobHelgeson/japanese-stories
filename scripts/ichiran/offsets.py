"""Where each word sits in the source text.

Ichiran does not return offsets, and it cannot be asked for them: the response
rewrites the punctuation it does not segment (。 becomes ". ", 「」 become '"'),
so it is not a transcript of its input. Verified by reconstructing all 342
recorded responses and hashing them against the cache key they are stored
under — 2 matched. The words therefore have to be found in the document, and
this module is the only place that does it.

What makes that safe is keeping compounds whole. Ichiran returns a canonical
surface for the parts of some inflections — 熱すぎて has components 熱い and
すぎて, and the document contains neither — so a walk that splits compounds is
left hunting for text that was never written. It was: `str.find` located the
next real 熱い a thousand characters downstream, dragged the cursor past
everything between, and orphaned every token in it. インドラの網 aligned 22 of
its 1683 tokens that way.

The compound node carries both the written surface and its reading (`text` 熱
すぎて, `kana` あつすぎて), so keeping it whole means the surface being searched
for is one that exists. The budget below survives as a guard rather than a
correction — see `_affordable`.
"""

import re
from dataclasses import dataclass

# Kana and kanji together: what may never turn up in the gap between two words,
# because Ichiran drops punctuation and never a word.
WORD = re.compile(r"[ぁ-ゖァ-ヺーｰ㐀-䶿一-鿿豈-﫿々]")


@dataclass(frozen=True)
class Raw:
    """Source text no word claimed: punctuation, nearly always."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Placed:
    """A word, and the span of the source text it covers.

    `text` is what the document actually says; `word.surface` is what Ichiran
    called it. They differ only where a canonical surface had to be carried into
    a gap, which keeping compounds whole has made rare — `canonical` is how a
    caller tells, and is None when there is nothing to tell.
    """

    word: object
    text: str
    start: int
    end: int

    @property
    def canonical(self):
        return self.word.surface if self.word.surface != self.text else None


def _affordable(text, start, end, dropped):
    """Whether the words already dropped can account for the gap being crossed.

    A guard, not a correction. Punctuation is free, because Ichiran drops it by
    design and the raw chunks exist to carry it. Word characters are charged
    against the surfaces dropped since the last match, which is exactly the text
    a canonical surface stands in for.

    Dropping a word costs one word. Letting the cursor run costs the rest of the
    document, and does it silently — which is why the budget resets on every
    match rather than accumulating. A budget that accumulates goes inert a few
    drops into any real document, and passes every test written before that
    happens.
    """
    return len(WORD.findall(text[start:end])) <= sum(len(w.surface) for w in dropped)


def _gap(text, start, end, dropped):
    """The pieces of the source a matched word skipped over.

    Punctuation, usually, and then it is one Raw as it has always been. But a
    gap also opens where Ichiran returned a canonical surface for what is
    written here, and then the word characters in the gap ARE that word's text.
    Where exactly one word was dropped they are given to it, so it keeps its
    reading, gloss and dictionary forms and the caller can see from `canonical`
    that they describe a longer word than the one printed.

    Two dropped words share one gap with nothing to say where the boundary
    between them falls, so both stay lost rather than one being guessed.
    """
    span = text[start:end]
    hits = [m.start() for m in WORD.finditer(span)]
    if len(dropped) != 1 or not hits:
        return [Raw(span, start, end)]
    lo, hi = hits[0], hits[-1] + 1
    out = []
    if lo:
        out.append(Raw(span[:lo], start, start + lo))
    out.append(Placed(dropped[0], span[lo:hi], start + lo, start + hi))
    if hi < len(span):
        out.append(Raw(span[hi:], start + hi, end))
    return out


def _share(surface, parts):
    """How many characters of `surface` each canonical part accounts for.

    A compound's parts are canonical and its `text` is what was printed, so the
    two differ exactly where an inflection contracted: 熱すぎて is 熱い + すぎて,
    通してくれん is 通して + くれない. Measured over the 8,978 recorded compounds,
    every difference is a part truncated at its own tail — no part is reordered,
    inserted or replaced — so walking a cursor and letting each part take the
    longest prefix of what is left recovers the split exactly.

    Whatever the last part could not match is still text that was printed, so it
    goes to that part rather than becoming a gap: 言わなくちゃ is 言わなくて + は,
    and ちゃ belongs to the second part even though it shares no prefix with it.
    """
    out = []
    pos = 0
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            out.append(len(surface) - pos)
            break
        n = 0
        while n < len(part) and pos + n < len(surface) and part[n] == surface[pos + n]:
            n += 1
        out.append(n)
        pos += n
    return out


def spread(piece):
    """A placed compound as its components, each over the text it covers.

    The compound is what gets placed, because it is the only node carrying the
    printed surface. It is not what gets read: 通してくれん is one node and two
    words, and a reader that makes it a single token has taken something away
    from the page to satisfy the parser. So the span comes from the compound and
    the granularity comes from its parts.

    A part that would cover nothing is dropped rather than emitted empty.
    """
    from .model import Word

    parse = piece.word.preferred
    if not parse.is_compound:
        return (piece,)
    widths = _share(piece.text, [c.surface for c in parse.components])
    out = []
    at = 0
    for component, width in zip(parse.components, widths):
        if width > 0:
            out.append(
                Placed(
                    word=Word(parses=(component,)),
                    text=piece.text[at:at + width],
                    start=piece.start + at,
                    end=piece.start + at + width,
                )
            )
        at += width
    return tuple(out) or (piece,)


def place(text, words):
    """`words` laid down over `text`: every piece contiguous, the whole covered.

    Taking an explicit word list rather than a text keeps the matching rule
    testable with no Ichiran and no network — see selftest.py.
    """
    out = []
    pos = 0
    dropped = []
    for word in words:
        surface = word.surface
        if not surface:
            continue
        idx = text.find(surface, pos)
        if idx < 0 or not _affordable(text, pos, idx, dropped):
            dropped.append(word)
            continue
        if idx > pos:
            out.extend(_gap(text, pos, idx, dropped))
        out.append(Placed(word, surface, idx, idx + len(surface)))
        pos = idx + len(surface)
        dropped = []
    if pos < len(text):
        out.append(Raw(text[pos:], pos, len(text)))
    return tuple(out)


def align(text):
    """Words interleaved with the punctuation Ichiran drops, each with offsets.

    Segmentation is one round trip per call and Ichiran is not fast, so callers
    pass the whole document at once and slice the result by offset.

    Compounds are placed whole and then spread, so the offsets come from the
    node that knows the printed surface and the tokens come out at the
    granularity the page was written at.
    """
    from . import words as _words

    placed = place(text, _words(text))
    return tuple(
        part
        for piece in placed
        for part in (spread(piece) if isinstance(piece, Placed) else (piece,))
    )
