"""Ichiran's segmentation output, read once and read properly.

The rest of this repo used to reach into the raw JSON at fixed depths, and two
bugs shipped from it in one session. Both were invisible: a gloss that never
resolved looks exactly like a word that has none, and a base form picked by
Unicode order looks exactly like one picked by Ichiran.

    from ichiran import align, tokens

    for word in tokens("空が青い"):
        word.surface            # 青い, as written
        word.dictionary_form    # 青い
        word.gloss()            # "blue; azure"
        word.preferred.inflections

Three rules hold everything here together, and each one is a bug that got out:

1. **Which parse is right is decided in exactly one place** — `Word.preferred`,
   which is Ichiran's own ranking. It used to be decided implicitly, by three
   different orderings in three modules, one of which was codepoint order.
2. **Ichiran's order is never sorted.** `dictionary_forms[0]` is the top-ranked
   parse because the response ranked it, not because it sorted first.
3. **The written surface belongs to the compound, not its parts.** 熱すぎて has
   components 熱い and すぎて and neither is in the document; only the compound
   node knows what was actually printed.

Everything in this package works offline against recorded responses. See
`selftest.py` — `python3 scripts/ichiran/selftest.py` needs no Ichiran and no
network, and the fixtures are real responses rather than shapes invented to
suit the walk.

The modules are named for what they hold rather than for the call they serve,
because `ichiran.align` the function and `ichiran.align` the module cannot both
win an import:

    client.py   the network and the cache      segment(text) -> raw response
    model.py    what a response is made of     Word, Parse, Step, Sense
    walk.py     response -> words              read(response) -> Document
    offsets.py  words -> where they sit        align(text), place(text, words)
"""

import re

from .client import cached, clear, fetch, probe, segment, stats
from .model import Counter, Inflection, Parse, Sense, Step, Word
from .offsets import Placed, Raw, align, place
from .walk import Document, Interlude, Run, flatten, read

KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々]")


def has_kanji(s):
    return bool(KANJI.search(s))


def words(text, url=None, cache=True):
    """Every word in `text`, compounds kept whole, in reading order."""
    return read(segment(text, url=url, cache=cache)).words


def tokens(text, url=None, cache=True):
    """Every word in `text`, compounds split into their parts.

    For callers counting vocabulary rather than pointing at the page: a
    frequency table wants 熱い and すぎて, and does not care that the document
    says 熱すぎて. Anything that has to locate a word in the source uses
    `align` instead, where the compound stays whole because it is the only node
    that knows the written form.
    """
    return tuple(part for word in words(text, url=url, cache=cache) for part in flatten(word))


__all__ = [
    "Counter", "Document", "Inflection", "Interlude", "Parse", "Placed", "Raw",
    "Run", "Sense", "Step", "Word", "align", "cached", "clear", "fetch",
    "flatten", "has_kanji", "place", "probe", "read", "segment", "stats",
    "tokens", "words",
]
