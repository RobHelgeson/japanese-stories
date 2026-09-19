"""The walk from a raw segmentation response to a document of Words.

Nothing here decides which parse is right or where a token sits in the source
text. The first is `Word.preferred` in model.py, the second is align.py. This
module's only job is to turn Ichiran's nesting into a flat reading-order
sequence without losing anything on the way.
"""

from dataclasses import dataclass

from .model import Word


@dataclass(frozen=True)
class Interlude:
    """A `str` chunk: text Ichiran did not segment, with punctuation rewritten.

    Kept rather than dropped, because it is the only record that something sat
    between two runs. It is NOT the source text — 。 comes back as ". " and 「」
    as '"' — so it can order the runs but never locate them.
    """

    text: str


@dataclass(frozen=True)
class Run:
    """A segmented stretch of Japanese: the words, and Ichiran's score for them.

    A chunk holds exactly one of these in all 43,401 recorded chunks. The
    response nests it as `[[words, score]]` anyway, so the container is a list
    of competing whole-chunk segmentations that has never held more than one.
    If Ichiran is ever asked for several, the extras land here rather than being
    silently concatenated into the reading order the way an unguarded walk would
    do it.
    """

    words: tuple
    score: int = 0


@dataclass(frozen=True)
class Document:
    """A whole response: interludes and runs, in order."""

    chunks: tuple

    @property
    def runs(self):
        return tuple(c for c in self.chunks if isinstance(c, Run))

    @property
    def words(self):
        """Every word in reading order, compounds kept whole.

        Whole, because the compound node is the only one carrying the surface as
        written: 熱すぎて has components 熱い and すぎて and neither is in the
        document. Callers that want the pieces ask for them — see `flatten`.
        """
        return tuple(w for run in self.runs for w in run.words)


def _words(node, out):
    """Word entries in reading order, from Ichiran's nesting.

    A word arrives as ["romaji", {...}, []] — the third element is an empty list
    in all 195,278 recorded triples, and is not the alternatives list it looks
    like. Alternatives are a key on the word itself.
    """
    if isinstance(node, dict):
        if "alternative" in node or "text" in node:
            out.append(Word.read(node))
        return
    if isinstance(node, list):
        for item in node:
            if (
                isinstance(item, list)
                and len(item) == 3
                and isinstance(item[0], str)
                and isinstance(item[1], dict)
            ):
                _words(item[1], out)
            else:
                _words(item, out)


def read(response):
    """A raw segmentation response as a Document."""
    chunks = []
    for chunk in response if isinstance(response, list) else []:
        if isinstance(chunk, str):
            chunks.append(Interlude(chunk))
            continue
        for pair in chunk if isinstance(chunk, list) else []:
            # [words, score]. A malformed pair yields no words rather than
            # raising: one unreadable run costs a clause, a raise costs the book.
            if not isinstance(pair, list) or not pair:
                continue
            words = []
            _words(pair[0], words)
            score = pair[1] if len(pair) > 1 and isinstance(pair[1], int) else 0
            chunks.append(Run(words=tuple(words), score=score))
    return Document(chunks=tuple(chunks))


def flatten(word):
    """A word as its component parts, or as itself where it has none.

    Splitting a compound loses the written surface, so this is for callers that
    want morphology rather than position — a frequency count, a known-word
    check. Anything that has to point at the document keeps the compound whole.
    """
    parse = word.preferred
    if not parse.is_compound:
        return (word,)
    return tuple(Word(parses=(c,)) for c in parse.components)
