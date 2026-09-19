#!/usr/bin/env python3
"""How the narration sounds: sentence-final form, タ/ル alternation, overt pronouns.

Native-level readers report that this corpus reads as English designed and
Japanese rendered. Nothing in the validation stack can see that. stats.py counts
tokens, sentence-length spread, construction inventory, repeated-word share,
subordination and quote turns; check.py measures vocabulary; reference.py
measures four structural axes against 児童文学. Not one of them looks at what a
sentence *ends in*, and sentence-final form is where a Japanese narrator's voice
mostly lives. A story can pass every gate in this repo and still run a dozen or
more narration sentences without changing tense once, and spend a quarter of its
narration on three endings. Those two are `run_max` and `final3_top3_pct` in the
table below, per story.

NO FIGURE FROM A RUN IS WRITTEN DOWN HERE
-----------------------------------------
Every number --compare computes it also prints, so a copy in this docstring is a
second version of the same state with nothing keeping the two in step. That is
not hypothetical: the first draft of this file quoted a run of 33 and a top-3
share of 55%, and one revision pass over the stories took them to 14 and 27%
without a line of this module changing. Those two are kept above as the record of
what went stale; every other figure is gone. The prose below names the shapes and
the arguments and sends you to the run for the values.

Two kinds of number do stay. The five measures deliberately NOT made, under FIVE
THINGS below, which --compare cannot recompute because it does not compute them
at all — each carries the date it was measured. And the correlations quoted from
CALIBRATION.md § Corrections, which are the record of a decision already taken
elsewhere and are not this corpus's to move.

WHAT THIS IS
------------
A printing report. It prints a band and exits zero. It gates nothing and it
writes no threshold.

AND WHAT IT MUST NEVER BECOME
-----------------------------
A gate. AUTHORING.md § "Metrics are floors, not targets" is load-bearing here:
two of the five documented failure modes were *caused* by optimising a metric,
and this file measures the axis most easily optimised into nonsense. A past-tense
share can be walked from 95% to 70% in an afternoon by converting descriptions to
the historical present, and the result would score better and read worse. The
numbers below say where to look, never what to hit.

NARRATION ONLY, AND WHY THE RULE LIVES HERE
-------------------------------------------
Dialogue has its own register, its own tense habits and its own pronouns —
「彼女は来ない」 in a speech turn is not the overt-pronoun tell that the same
words are in narration. So every figure here is computed over narration alone.

stats.prose_sentences() cannot supply that: it deliberately keeps quoted dialogue
and splits inside it, and CALIBRATION.md § Corrections records what happens when
that rule moves — seven settled numbers shift, and min_sentence_stdev is
calibrated in the old units. The precedent for a metric that cannot reuse it is
reference.py's dialogue_any_pct, defined outside stats.py for exactly this
reason. This follows it.

The rule is one rule, applied to both corpora:

  1. A unit that OPENS with 「 or 『 is a speech turn and is dropped whole.
     "Starts with 「" is already this repo's definition of a dialogue line —
     stats.measure's dialogue_pct is built on it — so this is not a new
     convention, it is the existing one applied to a new question.
  2. Quote spans inside the surviving units are removed, so an embedded quote
     cannot contribute its own ending to the inventory.
  3. What is left is split on 。！？.

A unit is a source line here and a reconstructed sentence there, which is the
same asymmetry reference.py handles: Aozora breaks a line wherever a quote
starts, so reference.to_sentences() is imported rather than re-derived. Writing a
second splitter would have put the two corpora in different units, and the drift
would have looked like a finding.

The cost is named rather than hidden: an attribution that trails its own quote on
the same line — 「行く」と答えた。 — goes with the turn, while the same clause in
a line that opens with narration is kept. That is a typographic accident, not a
principle. It is accepted because the alternative is worse: attribution tags are
formulaic and almost always past, so keeping them makes past_pct partly a
measure of how much dialogue a story has.

THE BAND IS PLAIN-FORM ONLY, AND THIS IS THE LOAD-BEARING DECISION
------------------------------------------------------------------
Most of reference.py's texts narrate in ですます調, and most of the narration
sentences in that sample are polite; --compare prints both counts. This corpus
is 100% 常体.

Ending concentration measured across that split measures politeness, not voice:
ました is one ending doing the work of た, ていた, かった and だった at once, so a
ですます text scores as flat no matter how varied its verbs are, and a 常体 text
scores as varied no matter how flat it is. The sign of the finding is not even
stable under the confound.

So the sample is re-split by narration register and only the 常体 texts are used.
register() does the splitting and POLITE_MAX is the cut; --compare prints which
texts survived it, the worst kept figure, the best rejected one, and the empty
space between. The split is not a judgement call and that print is how you check
rather than take it on trust. But **the surviving n is the weak point of this
entire report** — it is a handful of texts, not a sample — and the n is printed
beside every authentic figure for that reason, the way reference.py prints n=
under each reference column.

It is worse than it looks for the referential layer: --compare also prints how
many of the survivors narrate in the first person, and the answer has been one.
Every first-person comparison here rests on that text. Treat a single authentic
figure as a direction, not a bound.

FIVE THINGS DELIBERATELY NOT MEASURED
-------------------------------------
体言止め, ようだ, かもしれない, だろうか, and 私 density. An earlier pass called
all five missing from this corpus. They are not. Nothing recomputes what follows,
because nothing computes it, so it is stated with the date it was taken and must
be re-taken by hand to be trusted: measured 2026-09-19 against the plain-form
subset, 体言止め runs 0.00-2.31% here against 0.00-1.10% there, and first-person
density 19.2-29.1 per 100 narration sentences across the stories that have a
first-person narrator, against 花をうめる's 45.1 — above every story we have. The
earlier reading was the ですます confound above: a polite text ends in でした, not
in a bare noun, so 体言止め looked rare in the reference set because the reference
set was polite.

Every one of the five is already at or above authentic rate, so a metric on them
would invent a target real prose does not hit. That is the exact failure this
repo keeps recording, and the reason they are named here is so the next person
does not rediscover them and add them. The figures above are stated once, here,
rather than printed: a number in the report is a number someone will try to move.

NO ICHIRAN, AND NO KANJI-KEYED REGEX
------------------------------------
Every measure is a regex over raw text, so this runs offline and instantly.
Nothing here requires a kanji character, deliberately: CALIBRATION.md §
Corrections (b) reverted a clause-density measure partly because TE_CHAIN
requires a kanji after て/で, which correlated the result with a text's kanji
ratio at r=0.53 and undercounted kana-heavy reference prose. Children's books
write verbs in kana; this project writes them in kanji; a measure that keys on
kanji measures that difference and calls it style.

The one place the trap could still bite is the final 3-gram, whose key is three
raw characters and so carries stem orthography — 見えた against みえた. --compare
therefore recomputes the correlation on every run rather than assuming it away,
and it does not come out clean: within this corpus, where orthography policy is
constant, kanji ratio and ending entropy correlate positively. A kanji stem makes
the 3-gram key more distinctive, so a kanji-heavy text scores as more varied.

That is the confound, and it runs the wrong way to explain the finding. The
authentic texts are the kana-heavy side, so the mechanism predicts they should
score LOWER than us. They score higher. The gap survives the confound and is
understated by it, which is the opposite of what happened to TE_CHAIN. --compare
prints the two kanji ratios, both correlations and both entropy bands together,
under "confound checks", so the whole argument can be re-read off a run — which
is the point, because a story edit moves every figure in it.

The one lexical exception to "no kanji in a pattern" is 彼/彼女, matched in kanji
only: かれ in kana collides with every passive in the language (置かれた,
書かれて), and the pronoun is not written in kana in either corpus.

NOT A RESTATEMENT OF mean_len
-----------------------------
The standing bar from the same correction — correction (b) died partly because
subordination events per sentence correlated with mean_len at r=0.805, restating
a measure stats.py already reports. That 0.805 is the one figure quoted here from
outside: it is CALIBRATION.md's record of a decision already taken, not a number
this module can recompute. Ending entropy clears the bar — it correlates with
stats.py's own mean_len moderately and negatively, where a restatement would be
strong and positive. --compare recomputes and prints that r, along with the
correlation against narration length, since entropy rises with sample size and
the stories are of very different lengths.

Usage:
    python3 voice.py --compare     # our narration beside authentic 常体 prose
    python3 voice.py --selftest    # the classifiers, on a fixture table
"""

import argparse
import json
import math
import re
import statistics as st
import sys
from collections import Counter

import reference
import stats

# Quote handling for rule 2. Balanced spans first; then an unclosed opener and a
# dangling closer, which appear once reference.SPLIT has divided a multi-sentence
# quote — 「あ。い。」 becomes 「あ。 and い。」 and neither is balanced.
QUOTE_BALANCED = re.compile(r"「[^」]*」|『[^』]*』")
QUOTE_OPEN = re.compile(r"「[^」]*$|『[^』]*$")
QUOTE_CLOSE = re.compile(r"^[^「]*」|^[^『]*』")
TURN_OPEN = ("「", "『")

# Borrowed, not restated. The module docstring's argument for importing
# reference.to_sentences — two corpora measured in different units would make the
# drift look like a finding — applies with more force to a splitter that is used
# on both of them here. This was a character-for-character copy of stats.SENT_END
# and there was nothing to stop the two drifting apart.
SENT_END = stats.SENT_END
TRIM = "。！？…―—・、，,」』）］〉》　 "

# のだ系, in its の form only. Checked before anything else, because のだ ends in
# だ and is not past while のだった ends in た and is not a plain past.
#
# The colloquial ん form is NOT matched, and that is a decision rather than an
# oversight. んだ is ambiguous with the 音便 past of every む/ぶ/ぬ verb — 読んだ,
# 死んだ, 学んだ — and the ambiguity is real in kana rather than resolvable:
# 学んだ and 静かなんだ agree on なんだ. Reading ん as explanatory therefore called
# 読んだ present, and 誰も来ませんでした explanatory, because ませんでした also ends
# in んでした. Both were caught by the fixture table below. のだ's ん form is a
# spoken register and does not occur in narration in either corpus — 0 of 865
# narration sentences here and 0 of the authentic 常体 set — so ん is read as
# 音便 past instead. A story that narrates in 〜んだ would be miscounted; the
# fixture table pins that case so the limitation cannot drift silently.
NODA_PAST = re.compile(r"の(?:だった|であった|でした)$")
NODA_NONPAST = re.compile(r"の(?:だ|である|です|だろう|であろう|でしょう)$")

# 推量, narrowly: the だろう family, sentence-final. ようだ and かもしれない are
# modality too and are deliberately absent — see the docstring. のだろう counts
# here AND under のだ系; the two rates overlap by design and are not summed.
SUIRYOU = re.compile(r"(?:だろう|であろう|でしょう)$")

POLITE_PAST = re.compile(r"(?:ました|ませんでした|でした)$")
POLITE_NONPAST = re.compile(r"(?:ます|ません|ましょう|です|でしょう|ございます)$")

# 音便 past written だ. Only ん qualifies: 読んだ, 飛んだ, 死んだ. The ぐ-verb form
# 泳いだ is knowingly NOT counted, because い+だ is also every adjectival noun in
# the language — きらいだ, きれいだ, みたいだ, くらいだ — and separating them needs
# a closed stem list whose misses would INVENT past tense. The undercount is
# measured rather than assumed: zero sentences in this corpus end that way and
# one does in the plain reference set (ぬいだ, in 花をうめる).
ONBIN_DA = re.compile(r"んだ$")

# Third person, kanji only. See the docstring's note on かれ. The lookahead on the
# last alternative is not decoration: without it 彼女は backtracks to the bare 彼
# alternative when the particle group fails, and 女 counts as "some other
# particle" — which reported 終電 at 17.4 pronouns per 100 sentences in the
# `other` row and the same 17.4 in the total, i.e. every genitive counted twice.
PRONOUN_3P = r"(?:彼女たち|彼女ら|彼女|彼ら|彼(?![女ら]))"
# Named in English rather than by their particles because these become row
# labels, and a CJK character is double-width in a terminal while str padding
# counts it as one — a table mixing the two lines up under no padding width.
PARTICLE_GROUPS = (
    ("topic", r"[はが]"),
    ("genitive", r"の"),
    ("object", r"[をに]"),
)
PRONOUN_RE = {
    name: re.compile(PRONOUN_3P + part) for name, part in PARTICLE_GROUPS
}
PRONOUN_ANY = re.compile(PRONOUN_3P)

# First person, used ONLY to decide which texts are comparable on the referential
# layer. No density is printed from it — 私 density is one of the five measures
# this report deliberately does not make, for the reason the docstring gives.
# The particle lookahead is what makes it usable in kana: bare おれ matches
# しおれず and bare わたし matches 渡した, and 花をうめる contains the first.
#
# MULTILINE is what makes the `|$` branch mean what it says. measure() runs this
# over the narration joined with newlines, so without it `$` is the end of the
# whole text and only the last sentence could ever take that branch — a
# first-person 体言止め sentence (…残っているのは私) anywhere else matched
# nothing. There is no `^` in the pattern for the flag to affect.
FIRST_PERSON = re.compile(
    r"(?:私|わたくし|わたし|僕|ぼく|俺|おれ)(?:たち|ども|ら)?(?=[はがのをにもとでへかや、。]|$)",
    re.MULTILINE,
)
# Per 100 narration sentences. The cut is wide: across the 常体 reference texts
# 花をうめる runs 45.1, 久助君の話 2.6 — a framing narrator who is not the
# subject — and 泉ある家 0.0.
FIRST_PERSON_MIN = 5.0

# A text is 常体 below this share of polite narration endings. The threshold is
# nowhere near anything: across reference.json's 25 texts the plain handful sit
# near zero and the next one up is past halfway, so any cut in that gap picks the
# same texts. --compare prints both edges of the gap and the width between them,
# so it can be re-checked rather than trusted, and that print is authoritative
# over any figure written down here.
POLITE_MAX = 20.0


def denarrate(unit):
    """A unit with its dialogue removed, or "" if it was a speech turn.

    Rules 1 and 2 of the narration rule, in one place so both corpora get the
    same one.
    """
    if unit.startswith(TURN_OPEN):
        return ""
    s = QUOTE_BALANCED.sub("", unit)
    s = QUOTE_OPEN.sub("", s)
    s = QUOTE_CLOSE.sub("", s)
    return s


def narration(units):
    """Narration sentences from source lines or reconstructed sentences."""
    out = []
    for unit in units:
        for part in SENT_END.split(denarrate(unit)):
            part = part.strip(TRIM)
            if part:
                out.append(part)
    return out


def story_narration(path):
    return narration(stats.sentences(path))


def ref_narration(work):
    """Narration of one 青空文庫 text, split by reference.py's own rule."""
    return narration(reference.to_sentences(reference.fetch_text(work)))


def tail(sentence):
    """The sentence with terminal punctuation and brackets trimmed."""
    return sentence.rstrip(TRIM)


def predicate(t):
    """A tail with its interrogative か removed, so its ending can be read.

    Every pattern below is $-anchored, SENT_END splits on ？ rather than keeping
    it, and か is not in TRIM — so a question arrived at the classifiers with か
    still attached and missed all of them at once. 〜ですか was neither polite nor
    non-past; 〜ましたか was neither polite nor past; 〜のだろうか was neither のだ系
    nor 推量. All four are live: 泉ある家, a KEPT reference text, narrates
    （田畑の地味のお調べですか, and 時計の音 has a のだろうか.

    か is stripped here rather than added to TRIM because TRIM also feeds the
    final-3 ending key, and ですか really is a different ending from です. Folding
    the two would move every entropy and top-3 figure in the report, and would
    additionally count だろうか into the 推量 rate that the module docstring lists
    among the five measures this report does not make.
    """
    return t[:-1] if t.endswith("か") else t


def is_polite(t):
    p = predicate(t)
    return bool(POLITE_PAST.search(p) or POLITE_NONPAST.search(p))


def is_noda(t):
    p = predicate(t)
    return bool(NODA_PAST.search(p) or NODA_NONPAST.search(p))


def is_suiryou(t):
    return bool(SUIRYOU.search(predicate(t)))


def is_past(t):
    """タ or ル, on a trimmed sentence tail.

    Order matters and is the whole of the implementation: のだ系 first because it
    owns both an ending in だ that is not past and an ending in た that is not a
    plain past; then the polite pair, so a ですます sentence is classified rather
    than falling through to `endswith("た")` by accident; then た; then ん+だ.
    """
    t = predicate(t)
    if NODA_PAST.search(t):
        return True
    if NODA_NONPAST.search(t):
        return False
    if POLITE_PAST.search(t):
        return True
    if POLITE_NONPAST.search(t):
        return False
    if t.endswith("た"):
        return True
    return bool(ONBIN_DA.search(t))


def final3(t):
    """The ending key this report counts: the last three characters of a tail.

    Takes tail()'s output rather than a raw sentence, so measure() can count
    endings off the tails it already holds and the key has exactly one
    definition. It was inlined there before, which left FINAL3_SELFTEST pinning a
    function nothing called — the key could be changed in measure() and the
    selftest would stay green. The fixtures run tail() first, so they still pin
    TRIM, which is where the real decision lives.
    """
    return t[-3:]


def entropy(counts):
    """Shannon entropy of a Counter, in bits."""
    n = sum(counts.values())
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def tense_runs(flags):
    """Lengths of every maximal same-tense run, in order.

    No flags is no runs. `cur` starts at 1 and used to be appended
    unconditionally, so an empty text reported [1] — a phantom run of one, which
    reads as maximum alternation and is the one direction that looks good here.
    """
    if not flags:
        return []
    out, cur = [], 1
    for a, b in zip(flags, flags[1:]):
        if a == b:
            cur += 1
        else:
            out.append(cur)
            cur = 1
    out.append(cur)
    return out


def register(jp):
    """Share of narration sentences ending in ですます. The 常体 test.

    A text with no narration has no polite narration, so the share is 0.0 rather
    than a ZeroDivisionError. Nothing reaches that path through measure(), which
    refuses an empty text outright — POLITE_MAX would otherwise read 0.0% as
    exemplary 常体 and keep it.
    """
    if not jp:
        return 0.0
    return 100 * sum(1 for s in jp if is_polite(tail(s))) / len(jp)


def measure(jp):
    """Every figure this report prints, from narration sentences alone.

    None when there is no narration to measure, which callers skip and report.
    A short text, an all-dialogue text, or a draft whose every line opens with 「
    reaches here empty, and every figure below divides by n.
    """
    if not jp:
        return None
    tails = [tail(s) for s in jp]
    n = len(jp)
    flags = [is_past(t) for t in tails]
    runs = tense_runs(flags)
    finals = Counter(final3(t) for t in tails)
    top3 = finals.most_common(3)
    # Newline-joined, matching stats.measure, and for the same reason: with the
    # sentences butted together a character-level pattern matches straight across
    # a sentence boundary. 鏡に映ったのは彼 + 女の声が聞こえた produced a 彼女 that
    # is in neither sentence, which inflated the pronoun rows the report is built
    # on. Kanji is still counted over the sentences themselves, so the separator
    # cannot dilute the ratio the confound check reads.
    body = "\n".join(jp)
    chars = sum(len(s) for s in jp)
    kanji = sum(len(r) for r in stats.KANJI_RUN.findall(body))

    a = {
        "n": n,
        "past_pct": 100 * sum(flags) / n,
        "run_max": max(runs),
        "run_mean": st.mean(runs),
        "final3_entropy": entropy(finals),
        "final3_top3_pct": 100 * sum(v for _, v in top3) / n,
        "noda_pct": 100 * sum(1 for t in tails if is_noda(t)) / n,
        "suiryou_pct": 100 * sum(1 for t in tails if is_suiryou(t)) / n,
        "polite_pct": register(jp),
        "top3": top3,
        "kanji_ratio": 100 * kanji / chars if chars else 0.0,
    }
    for name, _ in PARTICLE_GROUPS:
        a[f"pron_{name}"] = 100 * len(PRONOUN_RE[name].findall(body)) / n
    a["pron_total"] = 100 * len(PRONOUN_ANY.findall(body)) / n
    # Arithmetic rather than a fourth regex, so the split always reconciles with
    # the total no matter what the particle groups are changed to.
    a["pron_other"] = a["pron_total"] - sum(
        a[f"pron_{name}"] for name, _ in PARTICLE_GROUPS
    )
    # A boolean, deliberately. It says which texts are comparable on the
    # referential layer; the rate behind it is 私 density and is not reported.
    a["first_person"] = (
        100 * len(FIRST_PERSON.findall(body)) / n >= FIRST_PERSON_MIN
    )
    return a


def pearson(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else 0.0


def plain_reference():
    """The 常体 subset of reference.json, measured. Never the whole sample.

    Returns (kept, rejected, skipped) so --compare can print the register split
    it is resting on instead of asserting it, and can say which texts it could
    not measure at all. Everything is already in scripts/.refcache/, so this
    costs no network.

    A text with no narration is skipped by name rather than aborting the report.
    Every text in the manifest today has narration, but the manifest is editable
    and `reference.py --refresh` is the moment a short or all-dialogue text
    arrives — one of those used to take the whole run down with a traceback.
    """
    man = json.loads(reference.MANIFEST.read_text(encoding="utf-8"))
    kept, rejected, skipped = [], [], []
    for w in man["texts"]:
        a = measure(ref_narration(w))
        if a is None:
            skipped.append(f"{w['author']} {w['title']}")
            continue
        a["author"], a["title"] = w["author"], w["title"]
        (kept if a["polite_pct"] < POLITE_MAX else rejected).append(a)
    return kept, rejected, skipped


# Keys are ASCII on purpose. A CJK row label is double-width in a terminal and a
# table mixing the two does not line up under any single padding width, which is
# why reference.py prints bare metric keys too. The legend carries the Japanese.
ROWS = [
    ("past_pct", "{:.1f}"),
    ("run_max", "{:.0f}"),
    ("run_mean", "{:.2f}"),
    ("final3_entropy", "{:.2f}"),
    ("final3_top3_pct", "{:.1f}"),
    ("noda_pct", "{:.1f}"),
    ("suiryou_pct", "{:.1f}"),
]

PRONOUN_ROWS = [
    ("pron_topic", "{:.1f}"),
    ("pron_genitive", "{:.1f}"),
    ("pron_object", "{:.1f}"),
    ("pron_other", "{:.1f}"),
    ("pron_total", "{:.1f}"),
]

LEGEND = [
    ("past_pct", "タ/ル alternation: share of narration sentences in past tense"),
    ("run_max", "longest unbroken run of one tense"),
    ("run_mean", "mean length of a same-tense run"),
    ("final3_entropy", "Shannon entropy of the last-3-character ending, bits"),
    ("final3_top3_pct", "share of narration carried by this text's top 3 endings"),
    ("noda_pct", "のだ系 rate (のだ / のだった / のである / のだろう), sentence-final"),
    ("suiryou_pct", "推量 rate (だろう / でしょう / であろう), sentence-final"),
    ("pron_*", "彼 / 彼女 / 彼ら per 100 narration sentences. The split is the"),
    ("", "point: topic は/が, genitive の, object を/に. A genitive 彼女の"),
    ("", "is ordinary Japanese; a topic 彼女は every third sentence is the"),
    ("", "tell, and a pooled figure would not tell them apart."),
]


def band(kept, key, fmt):
    """Median and range of an authentic figure, with its n always attached."""
    vals = [a[key] for a in kept]
    return fmt.format(st.median(vals)), f"{fmt.format(min(vals))}-{fmt.format(max(vals))}"


def stats_mean_len(path):
    """stats.measure's own mean_len, recomputed without Ichiran.

    The standing bar from CALIBRATION.md § Corrections (b) is that a new measure
    must not restate mean_len, so the correlation has to be against stats.py's
    figure — over every prose sentence, dialogue included — and not against a
    narration-only mean of this module's own making. It is a pure length average
    with no token counting in it, so it is taken directly from prose_sentences
    rather than through stats.measure, which would try to reach Ichiran.
    """
    sn = stats.prose_sentences(stats.sentences(path))
    return st.mean(len(s) for s in sn)


def compare():
    reference.test_no_vocab_import()
    kept, rejected, skipped = plain_reference()
    if not kept:
        raise SystemExit("no 常体 text in reference.json; the band cannot be built")

    ours, ours_skipped = [], []
    for s in stats.CORPUS["stories"]:
        path = stats.STORIES / f"{s['slug']}.txt"
        a = measure(story_narration(path))
        if a is None:
            ours_skipped.append(s["slug"])
            continue
        a["slug"], a["level"] = s["slug"], s["level"]
        a["mean_len"] = stats_mean_len(path)
        ours.append(a)
    if not ours:
        raise SystemExit("no story has narration; there is nothing to compare")

    w1, wc, wb = 18, 8, 12
    width = w1 + wc * len(ours) + 3 + wb * 2
    print("=" * width)
    print("NARRATION VOICE  —  a band to read beside, NOT a gate")
    print("=" * width)
    head = (f"{'metric':<{w1}}" + "".join(f"{('L%d' % a['level']):>{wc}}" for a in ours)
            + f"{'│':>3}" + f"{'auth med':>{wb}}{'auth range':>{wb}}")
    print(head)
    print(f"{'narration sents':<{w1}}" + "".join(f"{a['n']:>{wc}}" for a in ours)
          + f"{'│':>3}" + f"{('n=%d' % len(kept)):>{wb}}"
          + f"{('%d sents' % sum(a['n'] for a in kept)):>{wb}}")
    print("-" * width)

    for key, fmt in ROWS:
        med, rng = band(kept, key, fmt)
        print(f"{key:<{w1}}" + "".join(fmt.format(a[key]).rjust(wc) for a in ours)
              + f"{'│':>3}" + f"{med:>{wb}}{rng:>{wb}}")
    print("-" * width)
    for key, fmt in PRONOUN_ROWS:
        med, rng = band(kept, key, fmt)
        print(f"{key:<{w1}}" + "".join(fmt.format(a[key]).rjust(wc) for a in ours)
              + f"{'│':>3}" + f"{med:>{wb}}{rng:>{wb}}")
    print("=" * width)

    # Named, not counted away. A text with no narration is invisible in every
    # figure above, so the one place it can be reported is here.
    if ours_skipped:
        print(f"\nSKIPPED, no narration to measure: {', '.join(ours_skipped)}")
    if skipped:
        print(f"\nSKIPPED from reference.json, no narration: {', '.join(skipped)}")

    print("\ncolumns, in corpus.json order:")
    for a in ours:
        print(f"  L{a['level']}  {a['slug']}")
    print("\nrows:")
    for key, text in LEGEND:
        print(f"  {key:<16} {text}")

    fp = [a for a in kept if a["first_person"]]
    print(f"\nFirst-person narration: {len(fp)} of the {len(kept)} authentic 常体 texts "
          f"({', '.join(a['title'] for a in fp) or 'none'}),")
    print(f"against {sum(1 for a in ours if a['first_person'])} of our {len(ours)}. "
          "Every first-person comparison here rests on that one text.")
    print("私 density itself is NOT reported: every story already sits at or below the")
    print("authentic rate, so a metric on it would invent a target it does not need to")
    print("hit. See the module docstring's list of five.")

    print("\ntop 3 endings, per story:")
    for a in ours:
        got = ", ".join(f"{k} {100*v/a['n']:.0f}%" for k, v in a["top3"])
        print(f"  {a['slug']:<26} {got}")
    print("  authentic 常体:")
    for a in kept:
        got = ", ".join(f"{k} {100*v/a['n']:.0f}%" for k, v in a["top3"])
        print(f"    {a['author']} {a['title']:<8} n={a['n']:>3}  {got}")

    edge_in = max(a["polite_pct"] for a in kept)
    edge_out = min(a["polite_pct"] for a in rejected) if rejected else float("nan")
    polite_sents = sum(a["n"] * a["polite_pct"] / 100 for a in kept + rejected)
    total = sum(a["n"] for a in kept + rejected)
    print(f"\nregister split of reference.json, cut at {POLITE_MAX:.0f}% polite endings:")
    print(f"  kept  {len(kept):>2} 常体 texts   — {edge_in:.1f}% polite at worst")
    print(f"  cut   {len(rejected):>2} ですます texts — {edge_out:.1f}% polite at best")
    print(f"  {edge_out - edge_in:.1f} points of empty space between them, so the cut is "
          "not a judgement call.")
    print(f"  {len(rejected)} of {len(kept) + len(rejected)} texts and "
          f"{100*polite_sents/total:.0f}% of all narration sentences in the sample are "
          "ですます.")
    print("  Ending concentration measured across that split would report politeness")
    print("  rather than voice — ました alone does the work of た, ていた, かった and")
    print("  だった at once. This is why the band is the 常体 subset and nothing else.")

    every = ours + kept
    print("\nconfound checks, recomputed every run (see the module docstring):")
    for label, xs, ys, note in (
        (f"kanji ratio, all {len(every)} texts",
         [a["kanji_ratio"] for a in every], [a["final3_entropy"] for a in every],
         "the TE_CHAIN trap, CALIBRATION.md (b), ran r=0.53"),
        (f"kanji ratio, our {len(ours)} only",
         [a["kanji_ratio"] for a in ours], [a["final3_entropy"] for a in ours],
         "orthography policy is constant here: the clean test"),
        (f"stats.mean_len, our {len(ours)}",
         [a["mean_len"] for a in ours], [a["final3_entropy"] for a in ours],
         "a restatement would sit near correction (b)'s r=0.805"),
        (f"narration n, our {len(ours)}",
         [float(a["n"]) for a in ours], [a["final3_entropy"] for a in ours],
         "entropy rises with sample size; this says how much"),
    ):
        print(f"  final3_entropy vs {label:<26} r={pearson(xs, ys):+.3f}   ({note})")
    ours_k = st.mean(a["kanji_ratio"] for a in ours)
    ref_k = st.mean(a["kanji_ratio"] for a in kept)
    print(f"  narration kanji ratio: ours {ours_k:.0f}%, authentic {ref_k:.0f}%.")
    print("  The second r is the one that matters and it is positive: inside this corpus")
    print("  MORE kanji goes with HIGHER ending entropy, because a kanji stem makes the")
    print(f"  3-gram key more distinctive. The authentic texts are the kana-heavy side at"
          f" {ref_k:.0f}%,")
    print("  so that mechanism predicts they should score LOWER than us. They score")
    print("  higher. The gap is therefore understated by the confound, not produced by")
    print("  it — which is the opposite of what happened to TE_CHAIN.")

    print("\nn=3 IS THE WEAK POINT OF THIS REPORT, and one of the three is first-person.")
    print("Read the authentic column as a direction, not a bound.")
    print("NOTHING HERE IS A GATE. No corpus.json threshold is written by this script.")


# (sentence, past, のだ系, 推量, polite). Each line is a case the ordering in
# is_past() exists to get right, and every one of them was wrong under the
# obvious rule "ends in た or だ".
SELFTEST = [
    ("雨が降っていた。", True, False, False, False),
    ("雨が降っている。", False, False, False, False),
    ("空は青かった。", True, False, False, False),
    ("空は青い。", False, False, False, False),
    ("誰も来なかった。", True, False, False, False),
    ("彼は先生だった。", True, False, False, False),
    # Bare copula だ. The naive rule called all of these past; 終電 and 時計の音
    # carry 48 such sentences between them.
    ("彼は先生だ。", False, False, False, False),
    ("話す相手がいないからだ。", False, False, False, False),
    ("残っているのは私だけだ。", False, False, False, False),
    ("同じはずだ。", False, False, False, False),
    # 音便 past, which shares that ending and is not copula.
    ("本を読んだ。", True, False, False, False),
    ("祖母は死んだ。", True, False, False, False),
    # のだ系: ends in だ and is not past; ends in た and is not a plain past.
    ("誰も来なかったのだ。", False, True, False, False),
    ("誰も来なかったのだった。", True, True, False, False),
    ("それが答えなのである。", False, True, False, False),
    ("雨が降ったのだろう。", False, True, True, False),
    # 推量.
    ("明日は雨が降るだろう。", False, False, True, False),
    ("彼も来るでしょう。", False, False, True, True),
    # ですます. Present only in the reference sample, and the register test is
    # what keeps that sample out of the band.
    ("雨が降りました。", True, False, False, True),
    ("雨が降ります。", False, False, False, True),
    ("それは本でした。", True, False, False, True),
    ("それは本です。", False, False, False, True),
    ("誰も来ませんでした。", True, False, False, True),
    # THE KNOWN MISS, pinned rather than fixed. Colloquial んだ is read as 音便
    # past. See the note on NODA_PAST: it does not occur in narration in either
    # corpus, and the alternative is calling 読んだ present.
    ("知らないんだ。", True, False, False, False),
    # 体言止め and a な-ending, both non-past and neither measured elsewhere.
    ("静かな廊下。", False, False, False, False),
    ("鏡を磨く。", False, False, False, False),
    # Questions. SENT_END eats ？ and TRIM does not carry か, so every one of
    # these used to reach the classifiers with か attached and answer False four
    # times over. The first two are live: 泉ある家 narrates お調べですか and
    # 時計の音 has a のだろうか.
    ("田畑の地味のお調べですか。", False, False, False, True),
    ("直せない状態のまま残したのだろうか。", False, True, True, False),
    ("どうしてこの町へきましたか。", True, False, False, True),
    ("どんなに幸福でしたか。", True, False, False, True),
    ("どなたか知っているかたはありませんか。", False, False, False, True),
    ("おそうじしたのはいつだったか。", True, False, False, False),
    ("やはり兵太郎君じゃないか。", False, False, False, False),
    # か that is not interrogative: the stripped character must not turn a
    # non-past ending into something it is not. そう and しよう match nothing
    # either way, which is the point — か leaves no residue of its own.
    ("食ってやるとしようか。", False, False, False, False),
]

# (units in, narration sentences out). The narration rule, including the two
# shapes reference.SPLIT produces from a multi-sentence quote.
NARRATION_SELFTEST = [
    (["「行こう」と彼は言った。"], []),
    (["私は「行こう」と答えた。"], ["私はと答えた"]),
    (["雨が降っていた。窓を閉めた。"], ["雨が降っていた", "窓を閉めた"]),
    (["「あ。", "い」と言った。"], ["と言った"]),
    (["外は暗い。"], ["外は暗い"]),
    (["「ただいま」"], []),
]

# (sentence, its ending key). Run through tail() first, the way measure() does,
# so these pin TRIM as much as the slice.
FINAL3_SELFTEST = [
    ("雨が降っていた。", "ていた"),
    ("空は青かった。", "かった"),
    ("彼は先生だった。", "だった"),
    ("鏡を磨く。", "を磨く"),
    # か is trimmed by neither tail() nor the key, only by predicate(), so a
    # question is its own ending and not a second copy of です.
    ("お調べですか。", "ですか"),
]


def selftest():
    ok = True
    for sentence, past, noda, suiryou, polite in SELFTEST:
        t = tail(sentence)
        got = (is_past(t), is_noda(t), is_suiryou(t), is_polite(t))
        want = (past, noda, suiryou, polite)
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {sentence:<24} "
              f"past={got[0]!s:<5} のだ={got[1]!s:<5} 推量={got[2]!s:<5} 丁寧={got[3]}")
        if not good:
            print(f"       want past={want[0]} のだ={want[1]} 推量={want[2]} 丁寧={want[3]}")

    for units, want in NARRATION_SELFTEST:
        got = narration(units)
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} narration {units} -> {got}")
        if not good:
            print(f"       want {want}")

    for sentence, want in FINAL3_SELFTEST:
        got = final3(tail(sentence))
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} final3 {sentence} -> {got}")
        if not good:
            print(f"       want {want}")

    # tense_runs is the headline measure's other half, and an off-by-one in it
    # would move run_max on every story at once. [] is the case that was wrong:
    # it reported [1], a run that is not there, and a phantom run of one reads as
    # perfect alternation.
    for flags, want in [
        ([True] * 5, [5]),
        ([True, False, True], [1, 1, 1]),
        ([True, True, False, False, False, True], [2, 3, 1]),
        ([False], [1]),
        ([], []),
    ]:
        got = tense_runs(flags)
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} tense_runs {flags} -> {got}")

    # An empty text is skipped, not divided by. Every figure in measure() has n
    # in its denominator, so one unmeasurable text used to end the whole report
    # in a traceback rather than a line naming it.
    for label, got in (("measure([])", measure([])), ("register([])", register([]))):
        want = None if "measure" in label else 0.0
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {label} -> {got!r} (want {want!r})")

    # The sentences are joined with a separator, so a character pattern cannot
    # run across a boundary. Neither pair below contains 彼女; butted together
    # they each produce one, in the row that is the actual tell. The 彼 in the
    # first sentence is real and still counts, under `other`.
    for units, key in (
        (["鏡に映ったのは彼", "女の声が聞こえた"], "pron_genitive"),
        (["鏡に映ったのは彼", "女は声をあげた"], "pron_topic"),
    ):
        a = measure(units)
        good = a[key] == 0.0 and a["pron_other"] == 50.0
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} 彼女 across a sentence boundary -> "
              f"{key} {a[key]:.1f}, other {a['pron_other']:.1f} (want 0.0, 50.0)")

    # 体言止め in the first person, which the `|$` branch of FIRST_PERSON's
    # lookahead is there for and could not reach without MULTILINE: before, only
    # the last sentence of a text could take it.
    fp = measure(["残っているのは私", "鏡を磨く"] + ["外は暗い"] * 18)
    ok &= fp["first_person"]
    print(f"  {'ok  ' if fp['first_person'] else 'FAIL'} first person at a "
          f"sentence end, not the text end -> {fp['first_person']} (want True)")

    h = entropy(Counter({"a": 1, "b": 1, "c": 1, "d": 1}))
    good = abs(h - 2.0) < 1e-9
    ok &= good
    print(f"  {'ok  ' if good else 'FAIL'} entropy of 4 equal outcomes -> {h:.3f} (want 2.000)")
    return bool(ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--compare", action="store_true",
                    help="our narration beside authentic 常体 prose")
    ap.add_argument("--selftest", action="store_true",
                    help="the classifiers, on a fixture table")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(0 if selftest() else 1)
    elif args.compare:
        compare()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
