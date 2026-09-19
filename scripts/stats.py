#!/usr/bin/env python3
"""Measure the axes the grading ladder actually claims.

This used to report page and word counts, which is why two false claims survived
in the reading-order prose, since moved to CALIBRATION.md: that sentence length ramps across the set (it does not, the
longest story has the shortest sentences) and that 終電's distinguishing feature
is untagged dialogue (it has the lowest untagged proportion of the five). If the
set is graded by construction, the tool has to measure construction.

Runs on the .txt sources so it can be used while drafting, before a build.
"""

import argparse
import json
import re
import statistics as st
from pathlib import Path

import furigana
import ichiran
import pos

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
STORIES = HERE.parent / "stories"

KANJI_RUN = re.compile(r"[一-鿿々]+")

# Attribution markers. A quoted line carrying none of these leaves the speaker to
# be inferred from register and content, which is the difficulty 終電 claims.
TAGGED = re.compile(
    r"(言った|言う|言って|聞いた|聞く|答えた|答える|尋ねた|尋ねる|呼んだ|叫んだ|続けた|と[、。])"
)


def tag_of(line):
    """The narrative tag on a quoted line: whatever follows the closing 」.

    This used to run against the whole line, which was sound while a line held one
    sentence and stopped being so when a line became a whole turn. 城の鐘's
    「…次の鐘を作れと言った。私は作らされた」 is reported speech *inside* the quote,
    and matching it counted an unattributed turn as attributed — which is backwards,
    because the untagged lines are exactly the ones whose speaker has to be inferred.
    """
    if not line.startswith("「"):
        return ""
    end = line.rfind("」")
    return line[end + 1:] if end >= 0 else ""

GRAMMAR_PATTERNS = {
    "ている": r"てい[るたまなかっ]|でい[るたまなかっ]",
    "たい": r"たい[。、とがけ]|たかった",
    "ことができる": r"ことができ|ことが出来",
    "てから": r"てから",
    "まえに": r"前に",
    "ば cond": r"[えけせてねへめれげぜでべ]ば[、。]",
    "たら cond": r"たら[、。]",
    "なら cond": r"なら[、。ば]",
    "ながら": r"ながら",
    "のに": r"のに[、。]",
    "ので/ため": r"ので[、。]|ために|ため[、。]",
    "ようだ/ような": r"ように|ような|ようだ|ようで",
    "らしい": r"らしい|らしく",
    "そう(様態/伝聞)": r"そう[だでにな]",
    "passive": r"[かがさたなはまやらわ]れ[るたてなまよ]|られ[るたてなまよ]",
    "causative": r"[かがさたなはまやらわ]せ[るたてなよ]|させ[るたてなよ]",
    "causative-passive": r"させられ|[かがさたなはまやらわ]せられ|[かがさたなはまやらわ]され[るた]",
    "てしまう": r"てしま|でしま|ちゃっ|じゃっ",
    "ておく": r"ておい|ておく|てお[きか]|とい[たて]",
    "ばかり": r"ばかり",
    "はず": r"はず",
    "ところ": r"ところ[だでをにへ、。]",
    "けれど": r"けれど|けども",
    "ほど/くらい": r"ほど|くらい|ぐらい",
    "わけ": r"わけ|訳[だでがはにを]",
    "ずに/ないで": r"ずに|ないで",
    "まま": r"まま",
    "すぎる": r"すぎ[るたて]|過ぎ[るたて]",
    "とおり": r"とおり|通り[に、。]",
    "一方で": r"一方",
    "にとって": r"にとって",
    "において": r"におい|における",
    "ものの": r"ものの",
    "として": r"として",
}


# The constructions above that actually subordinate a clause, as opposed to
# marking aspect or modality. ている and そうだ say something about one clause;
# ので and ながら join two.
SUBORDINATORS = {
    "てから", "まえに", "ば cond", "たら cond", "なら cond", "ながら", "のに",
    "ので/ため", "けれど", "ばかり", "ところ", "ほど/くらい", "ずに/ないで",
    "まま", "とおり", "一方で", "ものの",
}

# 連用形 chaining: a て/で form that continues into more clause material instead
# of ending the sentence. The auxiliaries are excluded because ている and てしまう
# extend one clause rather than joining two.
TE_AUX = r"(?:い[るたまなかっ]|お[きくいか]|しま|ちゃ|じゃ|く[るれた]|き[たて]|い[くっ]|み[るた]|あ[るっ])"
TE_CHAIN = re.compile(rf"[てで](?:、|(?!{TE_AUX})[一-鿿])")

# Plain-form endings that can sit in 連体形 directly before a noun.
RENTAI = re.compile(r"(?:[うくぐすつぬぶむるい]|た|だ|ない|なかった|かった)$")

ADJ_I = {"adj-i", "adj-ix"}


# Built-reader access, used by index.py to build the contents page. Kept here
# because the DATA blob is this module's other input format.
ROW = re.compile(r"const DATA = (\{.*?\});\n", re.S)
BLOB = re.compile(r"window\.STORY = (\{.*?\});\n", re.S)


def data_file(path):
    """The blob in a data/<slug>.js sidecar."""
    return json.loads(BLOB.search(Path(path).read_text(encoding="utf-8")).group(1))


def data_of(path):
    """A built reader's DATA, whether it carries it or links it.

    docs/versions/ is self-contained and answers from the document itself; a
    live story is a shell whose blob sits in data/<slug>.js beside it. Both are
    read here so no caller has to know which form a given reader took.
    """
    path = Path(path)
    hit = ROW.search(path.read_text(encoding="utf-8"))
    if hit:
        return json.loads(hit.group(1))
    side = path.parent / "data" / f"{path.stem}.js"
    if not side.exists():
        raise SystemExit(f"{path.name} links its data and {side} is missing")
    return data_file(side)


def read(path):
    """The stats a built reader carries in its DATA blob."""
    d = data_of(path)
    return {
        "file": Path(path).name,
        "title": d["title"],
        "pages": len(d["pages"]),
        # 文 means sentences. A built unit is a line, and since a line may be a
        # whole quoted turn the two diverge — counting units advertised 906 文
        # for a corpus holding 950 sentences.
        "sentences": sum(
            len(prose_sentences(["".join(t["t"] for t in sent["toks"])]))
            for page in d["pages"]
            for sent in page
        ),
        "units": sum(len(p) for p in d["pages"]),
        "words": d["stats"]["words"],
        "weak": d["stats"]["weak"],
        "stats": d["stats"],
    }


def sentences(path):
    """Japanese lines only, with ruby annotations stripped back to bare kanji."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(">") or line.startswith("#"):
            continue
        out.append(furigana.strip(line))
    return out


SENT_END = re.compile(r"[。！？]+")


def prose_sentences(lines):
    """The 。-terminated sentences inside the source lines.

    A line is one sentence or one whole quoted turn, so the two stopped being the
    same thing when turns were merged. Every rhythm measure below wants sentences:
    counting turns instead rescaled the lot without a word changing — 城の鐘's
    stdev went 6.9 to 9.7 on identical prose — and `min_sentence_stdev` is a floor
    calibrated in the old units, so the drift would have quietly relaxed it.

    A line with no terminator at all is still one sentence (「それは」).
    """
    out = []
    for line in lines:
        parts = [p for p in SENT_END.split(line) if p.strip("「」『』（）　 ")]
        out.extend(parts or [line])
    return out


def pages(path):
    blocks = Path(path).read_text(encoding="utf-8").split("\n\n")
    out = []
    for block in blocks:
        lines = [
            furigana.strip(l.strip())
            for l in block.splitlines()
            if l.strip() and not l.strip().startswith((">", "#"))
        ]
        if lines:
            out.append(lines)
    return out


def vocabulary(jp, basis="surface"):
    """Content-word tokens by dictionary form, for the recycling measure.

    Ichiran, not a kanji-run regex. The regex counts 立っていた as 立 and glues
    kanji across particles (もう一度箱を → 一度箱), so a story with varied verbs
    scores as low-recycling no matter how tightly its vocabulary is held. That
    is an artifact to rewrite prose against. Segmentation is cached, so the real
    tokeniser costs nothing after the first run; the regex stays as a fallback
    for when Ichiran is not up.

    `basis` decides which tokens count as content. `surface` keeps a token whose
    written form carries kanji, and is what every threshold in corpus.json was
    calibrated against. `lemma` keeps one whose dictionary form does, so つれた
    counts under 連れる. The two agree on this corpus, where verbs are written in
    kanji by design, and diverge hard on authentic children's prose, which writes
    them in kana: measured on 新美南吉's 飴だま, surface keeps 18% of tokens and
    lemma 35%, against 48-52% and 54-56% here. reference.py reports both for that
    reason — see its module docstring.
    """
    body = "\n".join(jp)
    try:
        import ichiran

        def keep(t):
            # The literal predicate the surface basis has always used, not
            # ichiran.has_kanji, whose wider ranges would move settled numbers.
            return any("一" <= c <= "鿿" for c in (t.surface if basis == "surface" else t.lemma))

        toks = [t.lemma for t in ichiran.tokens(body) if keep(t)]
        return toks, True
    except Exception:
        return [w for s in jp for w in KANJI_RUN.findall(s)], False


def _sentence_tokens(jp):
    """Ichiran tokens grouped back into their sentences.

    One segmentation pass over the joined body, sliced by offset — the same
    trick build.py uses, because Ichiran costs seconds per call regardless of
    input size and the result is cached.
    """
    joined = "\n".join(jp)
    spans, cursor = [], 0
    for s in jp:
        spans.append((cursor, cursor + len(s)))
        cursor += len(s) + 1
    aligned = [t for t in ichiran.align(joined) if isinstance(t, ichiran.Placed)]
    return [[t for t in aligned if start <= t.start < end] for start, end in spans]


def _relative_clause(toks, classes):
    """A plain-form verb or i-adjective sitting directly before a noun.

    Approximate, and deliberately conservative: the noun is required to contain
    kanji, so relative clauses landing on a kana noun (ひと, ところ) are missed.
    It undercounts rather than inventing subordination that is not there.
    """
    for a, b in zip(toks, toks[1:]):
        cls = classes.get(a.word.lemma, [])
        if not any(c in pos.VERB_CLASSES or c in ADJ_I for c in cls):
            continue
        if not RENTAI.search(a.text) or not ichiran.has_kanji(b.text):
            continue
        bcls = classes.get(b.word.lemma, [])
        if any(c in pos.VERB_CLASSES for c in bcls):
            continue
        return True
    return False


def subordination(jp):
    """Share of sentences carrying at least one subordinate clause.

    The measure the stdev floor was standing in for. Japanese literary prose is
    built on subordination — 連用形 chaining, relative clauses, ので / のに /
    ながら — and those are the level ladder's own constructions, so the 1:1
    translation coupling was quietly working against the ladder. A run-on string
    of nouns satisfies a stdev floor; it does not satisfy this.

    Falls back to the regex signals alone when Ichiran is down, which drops
    relative clauses and therefore understates the figure.
    """
    sub = [c for k, c in GRAMMAR_PATTERNS.items() if k in SUBORDINATORS]
    flat = [bool(TE_CHAIN.search(s)) or any(re.search(p, s) for p in sub) for s in jp]
    try:
        classes = pos.load()
        per_sentence = _sentence_tokens(jp)
    except Exception:
        return 100 * sum(flat) / len(jp), False
    hit = sum(
        1
        for f, toks in zip(flat, per_sentence)
        if f or _relative_clause(toks, classes)
    )
    return 100 * hit / len(jp), True


def analyze(path):
    a = measure(sentences(path), pages(path))
    a["slug"] = Path(path).stem
    return a


def measure(jp, pg=None):
    """Every structural axis, from a list of source lines alone.

    Split out of analyze() so a reference text can be put through the same
    implementation rather than a second one written to match it. A band from a
    parallel implementation would drift from the numbers it sits beside, and the
    drift would look like a finding. `pg` is optional because only this project's
    sources carry pages; a reference text has none and reports them as 0.

    `jp` is source LINES — one sentence, or one whole quoted turn — and every
    rhythm measure runs on prose_sentences(jp) instead, for the reason that
    function documents. That split is NOT a no-op on a reference text: Aozora
    normalisation keeps 「…。」と言った。 whole, and prose_sentences divides inside
    the quote, so 宮沢賢治's サガレンと八月 goes 92 elements to 113. That is the
    point of routing both through here rather than measuring each its own way —
    whatever the rule is, it is one rule, and the two corpora stay in the same
    units. It does mean the band has to be re-measured whenever this changes.
    """
    sn = prose_sentences(jp)
    lens = [len(s) for s in sn]
    body = "\n".join(jp)
    toks, real = vocabulary(jp)
    lem_toks, _ = vocabulary(jp, basis="lemma")
    types = {}
    for t in toks:
        types[t] = types.get(t, 0) + 1
    lem_types = {}
    for t in lem_toks:
        lem_types[t] = lem_types.get(t, 0) + 1

    quotes = [s for s in jp if s.startswith("「")]
    untagged = [s for s in quotes if not TAGGED.search(tag_of(s))]
    run = best = 0
    for s in jp:
        if s.startswith("「") and not TAGGED.search(tag_of(s)):
            run += 1
            best = max(best, run)
        else:
            run = 0

    found = {k: len(re.findall(v, body)) for k, v in GRAMMAR_PATTERNS.items()}
    sub_share, sub_full = subordination(sn)
    return {
        "slug": None,
        "subordinate_share": sub_share,
        "subordinate_full": sub_full,
        "sentences": len(sn),
        "lines": len(jp),
        "pages": len(pg) if pg else 0,
        "mean_len": st.mean(lens),
        "stdev_len": st.pstdev(lens),
        "pct_over_30": 100 * sum(1 for n in lens if n > 30) / len(lens),
        "pct_under_10": 100 * sum(1 for n in lens if n < 10) / len(lens),
        "sent_per_page": len(sn) / len(pg) if pg else 0.0,
        "chars": sum(lens),
        "tokens": len(toks),
        "types": len(types),
        "lemma_tokens": len(lem_toks),
        "real_tokens": real,
        "hapax_rate": 100 * sum(1 for v in types.values() if v == 1) / len(types),
        "repeated_share": 100 * sum(v for v in types.values() if v >= 3) / len(toks),
        "lemma_hapax_rate": 100 * sum(1 for v in lem_types.values() if v == 1) / len(lem_types),
        "lemma_repeated_share": 100 * sum(v for v in lem_types.values() if v >= 3) / len(lem_toks),
        "dialogue_pct": 100 * len(quotes) / len(jp),
        "untagged_pct": 100 * len(untagged) / len(quotes) if quotes else 0.0,
        "longest_untagged": best,
        "grammar": found,
        "distinct_constructions": sum(1 for v in found.values() if v),
    }


def budgets(tokens):
    b = CORPUS["budgets"]
    return {
        "new_words": round(tokens * b["new_words_per_100_tokens"] / 100),
        "leech_seeds": round(tokens * b["leech_seeds_per_100_tokens"] / 100),
        "min_occurrences": max(2, round(tokens / 150)),
    }


def check_brief(a, story):
    """Unmet parts of what this story was briefed to be.

    Nothing recorded the brief before, which is why 猫を探す探偵 could run 24%
    long and 城の鐘 14% without either being noticed. A story with no `brief`
    block is skipped entirely, so the five written before this existed keep
    passing untouched.
    """
    brief = story.get("brief") or {}
    fails = []

    if brief.get("pages"):
        want = brief["pages"]
        tol = CORPUS["defaults"]["page_tolerance"]
        lo, hi = round(want * (1 - tol)), round(want * (1 + tol))
        if not lo <= a["pages"] <= hi:
            off = 100 * (a["pages"] - want) / want
            fails.append(f"{a['pages']} pages, briefed {want} ({lo}-{hi}), {off:+.0f}%")

    if brief.get("new_words") is not None:
        declared = len(story.get("new_words") or {})
        if declared > brief["new_words"]:
            fails.append(f"{declared} new words declared, briefed {brief['new_words']}")

    missing = [c for c in brief.get("grammar_focus", []) if not a["grammar"].get(c)]
    if missing:
        fails.append(f"grammar focus absent: {', '.join(missing)}")

    d = brief.get("dialogue")
    if d and d.get("pct") is not None:
        lo, hi = d["pct"] - 10, d["pct"] + 10
        if not lo <= a["dialogue_pct"] <= hi:
            fails.append(f"dialogue {a['dialogue_pct']:.0f}%, briefed {d['pct']}% (±10)")
    if d and d.get("untagged") and a["untagged_pct"] < 90:
        fails.append(f"untagged dialogue {a['untagged_pct']:.0f}%, briefed untagged (≥90%)")

    return fails


def check_ruby(path):
    """Ruby markup in the source that a build will get wrong.

    Every other check here runs on furigana.strip()ed text, which is exactly
    where a broken annotation stops being visible: an unclosed ｜ strips to
    itself, so the line reads as prose and measures as prose, and the only place
    it surfaces is the built reader as a literal ｜ mid-sentence. A ｜ that
    over-captures is quieter still — it strips to plausible text and ships as
    ruby set over the wrong span. furigana.stray_markers finds both; one module
    owns the markup grammar and the predicate lives beside it.

    Reads the raw file rather than sentences(), because sentences() strips the
    markup before returning and drops the > and # lines entirely.

    ARCHIVED DRAFTS ARE NOT SCANNED, AND THAT IS AN ACCIDENT. main() walks
    corpus.json's live stories, so stories/versions/<slug>.<v>.txt is never
    passed here — not because a frozen draft was judged exempt, but because
    nothing ever walked it. It is not exempt: rebuild.py --versions builds those
    same sources through build.py into docs/versions/, so a broken annotation in
    one ships exactly as it would from a live story. As of 2026-09-19 two of them
    carry a stray ｜ (ikanakatta-hito-no-chizu.v1, rouka-no-kagami.v1) and
    neither has ever been built — corpus.json declares the versions and no HTML
    exists for them — so the next --versions run would publish both faults with
    nothing having complained. Scanning them needs no Ichiran and no analyze();
    it is this function over a wider list of paths.

    WHAT THIS DOES NOT COVER: a *well-formed* annotation on a > translation line.
    That is a real fault — build.py stores a translation line verbatim, so its
    ruby ships into the reader as raw ｜漢字《かな》 markup — but it is not a
    stray marker and stray_markers will not report it, because there is nothing
    wrong with the markup. It is wrong only for where it is. Reading the raw file
    means those lines are scanned; it does not mean this check knows what to say
    about them. Fixing it belongs on the build path, not in an optional report.
    """
    fails = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        for col in furigana.stray_markers(line):
            fails.append(
                f"line {n}, column {col + 1}: ｜ opens no sound annotation "
                f"— …{line[max(0, col - 4):col + 12]}…"
            )
    return fails


def check_targets(a, level):
    """Unmet requirements for this story's declared level.

    A level is a rung, not a checklist: the story must use `min_present` of its
    own level's constructions and keep exercising most of the lower levels, but
    it is never required to use every form the level makes available.

    Every threshold here catches a specific failure this corpus actually
    produced. None is a target to optimise — a story can meet all of them and
    still be inert, and two of the known failures were caused by optimising one.
    """
    fails = []
    spec = CORPUS["levels"][str(level)]
    own = spec["constructions"]
    present = [c for c in own if a["grammar"].get(c)]
    if len(present) < spec["min_present"]:
        absent = [c for c in own if c not in present]
        fails.append(
            f"level {level}: {len(present)}/{spec['min_present']} required constructions "
            f"(available and unused: {', '.join(absent)})"
        )

    carried = [c for n in range(1, level) for c in CORPUS["levels"][str(n)]["constructions"]]
    if carried:
        hit = sum(1 for c in carried if a["grammar"].get(c))
        if hit / len(carried) < CORPUS["min_carried"]:
            missing = [c for c in carried if not a["grammar"].get(c)]
            fails.append(
                f"carries {hit}/{len(carried)} lower-level constructions, "
                f"under {CORPUS['min_carried']:.0%} (missing: {', '.join(missing)})"
            )

    floor = 100 * CORPUS["budgets"]["min_repeated_share"]
    if a["repeated_share"] < floor:
        fails.append(f"repeated-word share {a['repeated_share']:.0f}% under {floor:.0f}%")
    if a["stdev_len"] < CORPUS["budgets"]["min_sentence_stdev"]:
        fails.append(f"sentence stdev {a['stdev_len']:.1f} under {CORPUS['budgets']['min_sentence_stdev']}")
    return fails


ROWS = [
    ("sentences", "{:.0f}"), ("pages", "{:.0f}"), ("tokens", "{:.0f}"),
    ("mean_len", "{:.1f}"), ("stdev_len", "{:.1f}"), ("pct_over_30", "{:.1f}"),
    ("pct_under_10", "{:.1f}"), ("sent_per_page", "{:.1f}"),
    ("repeated_share", "{:.1f}"), ("hapax_rate", "{:.1f}"), ("subordinate_share", "{:.1f}"),
    ("dialogue_pct", "{:.1f}"), ("untagged_pct", "{:.1f}"), ("longest_untagged", "{:.0f}"),
    ("distinct_constructions", "{:.0f}"),
]


def table(analyses, labels):
    w = max(22, *(len(l) + 2 for l in labels))
    print(f"{'metric':<24}" + "".join(f"{l:>{w}}" for l in labels))
    for key, fmt in ROWS:
        print(f"{key:<24}" + "".join(fmt.format(a[key]).rjust(w) for a in analyses))
    print(f"\n{'budget (derived)':<24}" + "".join(" " * w for _ in labels))
    for key in ("new_words", "leech_seeds", "min_occurrences"):
        print(f"  {key:<22}" + "".join(str(budgets(a["tokens"])[key]).rjust(w) for a in analyses))


def turns(path):
    """Every run of adjacent quoted lines, with its translations.

    Whether two neighbouring 「」 are two speakers or one speaker cut in half is
    the one thing in this format no script can decide: the source carries no
    speaker marks, so alternation is the whole of the attribution. What it can do
    is put the run in front of the author, because a split turn is invisible one
    line at a time and obvious as a block. A page break ends a run, since a turn
    never crosses one.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    units = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(">"):
            continue
        if not s or s.startswith("#"):
            units.append(None)
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        en = nxt.lstrip("> ").strip() if nxt.startswith(">") else ""
        # The translations carry annotations too — personal names, mostly — and
        # 行かなかった人の地図 is both the story with the most of them and the one
        # whose runs are hardest to attribute.
        units.append((i + 1, furigana.strip(s), furigana.strip(en)))

    runs, run = [], []
    for u in units + [None]:
        if u and u[1].startswith("「"):
            run.append(u)
        else:
            if len(run) > 1:
                runs.append(run)
            run = []
    return runs


def print_turns(path):
    """One block per run. Read down it and name a speaker for every line.

    A tagged line states its own speaker and closes the turn, so the line under
    it opens a new one whoever says it. Everything else has to alternate; two
    adjacent lines you would give to the same speaker are one turn wrongly split,
    and belong on one line inside one 「」.
    """
    runs = turns(path)
    print(f"\n{Path(path).stem} — {len(runs)} runs of adjacent quoted lines")
    for run in runs:
        print()
        for n, ja, en in run:
            print(f"  {'tagged' if TAGGED.search(tag_of(ja)) else '      '} {n:>4}  {en or ja}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    ap.add_argument("--strict", action="store_true", help="exit nonzero on an unmet target")
    ap.add_argument("--turns", action="store_true",
                    help="print adjacent quoted lines so speaker alternation can be checked")
    args = ap.parse_args()

    if args.diff and args.turns:
        ap.error("--turns reads a story's own runs; --diff compares two sets of metrics")

    if args.diff:
        a, b = (analyze(p) for p in args.diff)
        table([a, b], [Path(args.diff[0]).stem, Path(args.diff[1]).stem])
        return

    paths = args.paths or [STORIES / f"{s['slug']}.txt" for s in CORPUS["stories"]]

    if args.turns:
        for path in paths:
            print_turns(path)
        # A report, not a mode: --strict still has to run, or an author who asked
        # for both would read "no output" as "the gate passed".
        if not args.strict:
            return
        print()
    analyses = [analyze(p) for p in paths]
    entries = {s["slug"]: s for s in CORPUS["stories"]}
    table(analyses, [a["slug"][:14] for a in analyses])

    print()
    failed = False
    for path, a in zip(paths, analyses):
        story = entries.get(a["slug"])
        # Markup is checked on every path, corpus member or not: it is a property
        # of the file rather than of a declared level, and a draft not yet in
        # corpus.json is exactly when a broken annotation gets written.
        fails = check_ruby(path)
        if story is not None:
            fails += check_targets(a, story["level"]) + check_brief(a, story)
        elif not fails:
            continue
        label = f"{a['slug']}" + (f" (level {story['level']})" if story else "")
        if fails:
            failed = True
            print(f"{label}:")
            for f in fails:
                print(f"  MISS  {f}")
        else:
            print(f"{label}: targets met")
    if failed and args.strict:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
