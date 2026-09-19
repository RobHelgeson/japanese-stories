"""A read model for Ichiran's segmentation JSON.

Callers of this package never touch the raw response. That is the whole point:
two shipped bugs came from reaching into it at a fixed depth, and both were
invisible because a missing gloss looks exactly like a word that has none.

Every shape claim below was measured against the 295 responses recorded in
scripts/.segcache on 2026-09-19 — 195,278 word entries, 223,507 conj nodes,
15,193 alternative groups. A claim the corpus cannot settle says so, and the
code handles the unobserved case rather than asserting it away.

The response is Common Lisp's jsown output, which is why the shapes are the way
they are:

    $                     list of chunks, alternating
    chunk                 str  — non-Japanese text, PUNCTUATION NORMALIZED
                          list — [[words, score]], always exactly one pair
    words                 list of ["romaji", word, []]
    word                  see Parse below; or {"alternative": [word, ...]}

The `str` chunks are not the source text. Ichiran rewrites 。 as ". " and 「」
as '"', so a response cannot reconstruct its own input — verified by hashing
the reconstruction against the cache key, which matched 2 of 342 times. Any
alignment has to search the document rather than replay the response.

Two conventions bite anything that reads this JSON naively:

1. **nil serializes as `[]`.** `{"ordinal": []}` means ordinal is false; the
   true case writes `true`. So an absent scalar is an empty list, not null —
   which is also why a "dict or list" guard was the wrong worry. `_flag` and
   `_text` below are where that is handled, and they are the only places.

2. **An absent repeated field is omitted, not empty.** `gloss` is missing on
   39,144 word entries rather than `[]`, because the gloss lives on the conj
   node instead. Reading `entry["gloss"]` is a KeyError; reading it with a
   default hides the conjugated case, which is bug one.
"""

from dataclasses import dataclass, field


def _nodes(value):
    """A repeated field as a list of dicts, whatever Ichiran actually sent.

    Every one of `conj`, `gloss`, `via`, `alternative`, `components` and `prop`
    is a list in all 295 recorded responses — the dict case has never been
    observed. The guard survives anyway because iterating a bare dict yields its
    keys, so an unguarded walk calls .get on a string and takes the whole
    segmentation pass down instead of degrading to one lost word.
    """
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _flag(value):
    """A Lisp boolean, where nil arrives as `[]` rather than false or null."""
    return value is True


# Ichiran glues some readings together with a zero-width character, so で‌はある
# is five codepoints rather than four. Nothing downstream can see the difference
# and every comparison fails: a word that is known reads as unknown, with
# nothing anywhere saying why.
#
# Two of these are in the recorded corpus and they were not both being handled.
# The non-joiner is the common one (18,639 occurrences) and is what the
# 2026-09-16 fix stripped. The zero-width SPACE is rarer (1,139) and was missed,
# which left 33 base forms unmatchable — 中には, 時には, 七十五年, 六十三 and the
# rest of the compound particles and numerals — and put one inside 時には's
# displayed ruby. Hardcoding the character there was evidence for is what made
# the first fix incomplete, so this is the class: joiner and BOM too, neither
# yet observed here but neither distinguishable from the two that were.
ZERO_WIDTH = str.maketrans("", "", "​‌‍﻿")


def _text(value):
    """A string field, where nil arrives as `[]` and zero-width glue has to go."""
    return value.translate(ZERO_WIDTH) if isinstance(value, str) else ""


def _number(value):
    return value if isinstance(value, (int, float)) and value is not True else None


@dataclass(frozen=True)
class Sense:
    """One dictionary sense — an entry of a `gloss` list.

    `pos` is JMdict's part-of-speech tag as Ichiran prints it, brackets and all:
    "[v5k,vt]". It is a display string, not a parsed field, because that is the
    only form the response carries.
    """

    text: str
    pos: str = ""
    info: str = ""

    @classmethod
    def read(cls, node):
        return cls(
            text=_text(node.get("gloss")),
            pos=_text(node.get("pos")),
            info=_text(node.get("info")),
        )


@dataclass(frozen=True)
class Inflection:
    """What one conjugation step did, from a conj node's `prop`.

    43,564 of these are recorded and nothing in the repo reads one today. They
    are the answer to "what form is this token in" — `type` is Ichiran's own
    label ("Conjunctive (~te)", "Past (~ta)"), and `negative` and `formal` are
    the flags that would otherwise have to be recovered from the label text.
    """

    pos: str = ""
    type: str = ""
    negative: bool = False
    formal: bool = False

    @classmethod
    def read(cls, node):
        return cls(
            pos=_text(node.get("pos")),
            type=_text(node.get("type")),
            negative=_flag(node.get("neg")),
            formal=_flag(node.get("fml")),
        )


@dataclass(frozen=True)
class Step:
    """One link in a conjugation chain.

    A conj node is one of exactly two shapes in the corpus, and they do not
    overlap: `(gloss, prop, reading, readok)` — it carries its own entry — or
    `(prop, readok, via)` — it defers to the layer beneath. So `resolved` is a
    real discriminator rather than a heuristic, and `via` is populated only on
    the deferring shape.

    One step hangs its reading and gloss right here, so 過ぎて carries
    過ぎる 【すぎる】 on the node itself. A second step pushes the dictionary
    entry down into `via`: 描かれて is the te-form of the passive of 描く, and
    only the via node knows the word is 描く or that it means "to draw".
    """

    reading: str = ""
    senses: tuple = ()
    inflections: tuple = ()
    via: tuple = ()

    @property
    def resolved(self):
        return bool(self.reading or self.senses)

    @classmethod
    def read(cls, node):
        return cls(
            reading=_text(node.get("reading")),
            senses=tuple(Sense.read(g) for g in _nodes(node.get("gloss"))),
            inflections=tuple(Inflection.read(p) for p in _nodes(node.get("prop"))),
            via=tuple(cls.read(v) for v in _nodes(node.get("via"))),
        )


@dataclass(frozen=True)
class Counter:
    """A numeric counter reading. `ordinal` is the field that arrives as `[]`."""

    value: str = ""
    ordinal: bool = False

    @classmethod
    def read(cls, node):
        return cls(value=_text(node.get("value")), ordinal=_flag(node.get("ordinal")))


@dataclass(frozen=True)
class Parse:
    """One way Ichiran read a surface: a dictionary entry and its inflection.

    `surface` is the text as written. That matters for compounds, where it is
    the ONLY node carrying it: 熱すぎて has components 熱い and すぎて, neither of
    which appears in the document. See `components`.
    """

    surface: str = ""
    kana: str = ""
    reading: str = ""
    score: int = 0
    seq: int = None
    senses: tuple = ()
    steps: tuple = ()
    suffix: str = ""
    counter: Counter = None
    components: tuple = ()
    compound: tuple = ()
    raw: dict = field(default=None, repr=False, compare=False)

    @classmethod
    def read(cls, node):
        counter = node.get("counter")
        return cls(
            surface=_text(node.get("text")),
            kana=_text(node.get("kana")),
            reading=_text(node.get("reading")),
            score=_number(node.get("score")) or 0,
            seq=_number(node.get("seq")),
            senses=tuple(Sense.read(g) for g in _nodes(node.get("gloss"))),
            steps=tuple(Step.read(c) for c in _nodes(node.get("conj"))),
            suffix=_text(node.get("suffix")),
            counter=Counter.read(counter) if isinstance(counter, dict) else None,
            components=tuple(cls.read(c) for c in _nodes(node.get("components"))),
            compound=tuple(_text(x) for x in node.get("compound") or [] if isinstance(x, str)),
            raw=node,
        )

    @property
    def is_compound(self):
        return bool(self.components)

    @property
    def chain(self):
        """The conjugation steps that describe this parse, Ichiran's order kept.

        `via` is overloaded, and that is the trap the second bug came from.
        Sometimes it is the next layer of the SAME word (描かれて → 描く).
        Sometimes it is Ichiran's competing parse of a DIFFERENT word: 折れ is
        折れる, and equally the potential of 折る — Ichiran gives the preferred
        parse its own `reading` and leaves the rival to a via-only sibling.
        Merging both made 折る a base form of 折れる.

        So a sibling that resolved directly is Ichiran's answer and the via-only
        siblings beside it are dropped; `via` is read only when no sibling
        resolved, which is exactly the genuine multi-step case.

        Order is Ichiran's own ranking and is load-bearing — see
        `dictionary_forms`.
        """
        direct = [s for s in self.steps if s.resolved]
        for step in direct or self.steps:
            yield step
            if not step.resolved:
                for node in step.via:
                    yield node
                    yield from _via_chain(node)

    @property
    def dictionary_forms(self):
        """Dictionary forms for this parse, best first.

        Ranked, not sorted. Where a surface is genuinely ambiguous — 片付け is
        both 片付ける and 片付く — Ichiran orders the parses by score and callers
        read the first as *the* dictionary form. Sorting that by codepoint picks
        the lemma by whichever kana happens to come first in Unicode, which is
        how う-row 折る beat え-row 折れる.
        """
        out = []
        for step in self.chain:
            form = _headword(step.reading)
            if form and form not in out:
                out.append(form)
        return tuple(out)

    @property
    def dictionary_form(self):
        """The dictionary form, or None where Ichiran offered no conjugation.

        None rather than the surface: a caller that wants to fall back to the
        surface should say so, because the two cases mean different things and
        `stats.py` counts them differently.
        """
        forms = self.dictionary_forms
        return forms[0] if forms else None

    @property
    def dictionary_readings(self):
        """(written form, kana) for each entry this parse resolved to, ranked.

        A caller showing a dictionary form to a learner needs its reading, not
        the surface's: 描かれて is えがかれて, and the entry it resolves to is
        描く 【えがく】. Reading the kana off the surface would label the lemma
        with the inflected word's pronunciation.
        """
        out = []
        for step in self.chain:
            pair = _split_reading(step.reading)
            if pair[0] and pair not in out:
                out.append(pair)
        return tuple(out)

    @property
    def lemma_kana(self):
        """Kana for `lemma` — the dictionary form's reading, or the surface's."""
        readings = self.dictionary_readings
        return readings[0][1] if readings else self.kana

    @property
    def lemma(self):
        """The dictionary form, falling back to the surface where there is none.

        Callers wrote `bases[0] if bases else surface` in four places, which is
        fine until one of them writes it differently. It is a different question
        from `dictionary_form` — that one answers "did Ichiran reduce this?" and
        has to be able to say no.
        """
        return self.dictionary_form or self.surface

    @property
    def inflections(self):
        """Every conjugation step's grammar, outermost first."""
        return tuple(i for step in self.chain for i in step.inflections)

    @property
    def pos(self):
        """Part-of-speech tags, from the senses that carry them."""
        return tuple(dict.fromkeys(s.pos for s in self.all_senses if s.pos))

    @property
    def all_senses(self):
        """This parse's senses, plus those its conjugation chain resolved to.

        A conjugated word carries no `gloss` of its own — that is bug one, and
        the reason this is one accessor rather than two fields for callers to
        remember to check.
        """
        return (*self.senses, *(s for step in self.chain for s in step.senses))

    def gloss(self, limit=120):
        """The leading sense of each entry this parse resolved to.

        The first sense, not every sense, and that is a content decision rather
        than a formatting one. Joining all of them and cutting at 120 characters
        shipped JMdict's vulgar senses into the published reader: 割れ目 came
        back as "chasm; interstice; crevice; crack; cleft; split; rift; fissure;
        vulva; slit; cunt; vagina; twat", and 何 carried one past the cut in four
        stories. Ichiran strips JMdict's [vulg] tags, so there is no tag left to
        filter on — but a vulgar sense is never sense 1, and sense 1 is what a
        graded reader wanted anyway. 猫 is "cat", not "cat; shamisen; geisha;
        wheelbarrow".

        One sense per entry rather than one sense overall, because a genuinely
        ambiguous surface can resolve to several entries and they are all real:
        つけず is 付ける, 付く and 着く, and dropping the rest would answer a
        question the reader is entitled to see every half of.

        The limit stays as a backstop on a single very long sense. It is no
        longer what stands between the reader and the rest of the entry.

        Where the word carries senses of its own, those are the word and the
        conjugation chain is a rival analysis rather than a continuation of it —
        the same overloading that makes `via` dangerous, one level up. Joining
        the two produced strings that define two different words at once: より
        came back as "than; to have the nerve to; to be bastard enough to",
        which is the particle followed by an unrelated auxiliary, in 44 places
        across the live stories. で was "at; in; be; is"; 煙 was "smoke; fumes;
        smoky". A conjugated verb has no senses of its own, so the chain is all
        there is, and it answers there.
        """
        entries = [self.senses] if self.senses else [s.senses for s in self.chain]
        leading = [senses[0].text for senses in entries if senses]
        joined = "; ".join(dict.fromkeys(t for t in leading if t))
        return joined[:limit] if limit else joined


def _via_chain(step):
    """`chain` for a via node, which is itself a Step rather than a Parse.

    Never fires on the recorded corpus: `via` nests exactly one level deep in
    all 2,325 occurrences, and no via node carries a `conj` of its own. It is
    here because nothing in Ichiran's output promises that, and the cost of
    being wrong is a silently truncated chain.
    """
    direct = [s for s in step.via if s.resolved]
    for child in direct or step.via:
        yield child
        if not child.resolved:
            yield from _via_chain(child)


def _split_reading(reading):
    """A "書く 【かく】" reading string as (written form, kana).

    All 337,950 recorded readings are either this shape or a bare form with no
    【】 at all, in which case the form is its own kana — which is what a
    kana-only word looks like.
    """
    head, sep, tail = reading.partition("【")
    if not sep:
        form = reading.strip()
        return form, form
    return head.strip(), tail.rstrip("】").strip()


def _headword(reading):
    """The written form out of a "書く 【かく】" reading string."""
    return _split_reading(reading)[0]


@dataclass(frozen=True)
class Word:
    """A segmented word and every parse Ichiran offered for it, best first.

    **This is where the ambiguity decision lives, and it is the only place.**
    Before the connector it was made implicitly in three modules: `_walk` took
    `alternative[0]`, `_base_forms` sorted by codepoint, and `build.py` and
    `stats.py` each read `bases[0]`. Two of those three orderings were Ichiran's
    ranking and one was Unicode's, and nothing said which you were getting.

    `alternative` groups are ranked by score, descending, in all 15,193 recorded
    groups, and every alternative in a group shares the same `text`. So the
    surface is never in question — only which word it is.
    """

    parses: tuple

    @property
    def preferred(self):
        """Ichiran's own answer: the highest-scoring parse."""
        return self.parses[0]

    @property
    def surface(self):
        return self.preferred.surface

    @property
    def kana(self):
        return self.preferred.kana

    @property
    def is_compound(self):
        return self.preferred.is_compound

    @property
    def dictionary_forms(self):
        return self.preferred.dictionary_forms

    @property
    def dictionary_form(self):
        return self.preferred.dictionary_form

    @property
    def lemma(self):
        return self.preferred.lemma

    @property
    def lemma_kana(self):
        return self.preferred.lemma_kana

    @property
    def dictionary_readings(self):
        return self.preferred.dictionary_readings

    @property
    def seq(self):
        return self.preferred.seq

    @property
    def pos(self):
        return self.preferred.pos

    @property
    def inflections(self):
        return self.preferred.inflections

    def gloss(self, limit=120):
        return self.preferred.gloss(limit)

    @classmethod
    def read(cls, node):
        """One word entry, or an `alternative` group, as a ranked Word.

        An alternative wrapper has no fields of its own — `('alternative',)` is
        its entire key set — so the surface comes from the parses inside it.
        """
        alts = _nodes(node.get("alternative"))
        if alts:
            return cls(parses=tuple(Parse.read(a) for a in alts))
        return cls(parses=(Parse.read(node),))
