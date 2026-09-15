#!/usr/bin/env python3
"""Measure the axes the grading ladder actually claims.

This used to report page and word counts, which is why two false claims survived
in stories-index.md: that sentence length ramps across the set (it does not, the
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
TAGGED = re.compile(r"(言った|言う|聞いた|聞く|答えた|答える|呼んだ|叫んだ|続けた|と[、。])")

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
        "sentences": sum(len(p) for p in d["pages"]),
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


def vocabulary(jp):
    """Content-word tokens by dictionary form, for the recycling measure.

    Ichiran, not a kanji-run regex. The regex counts 立っていた as 立 and glues
    kanji across particles (もう一度箱を → 一度箱), so a story with varied verbs
    scores as low-recycling no matter how tightly its vocabulary is held. That
    is an artifact to rewrite prose against. Segmentation is cached, so the real
    tokeniser costs nothing after the first run; the regex stays as a fallback
    for when Ichiran is not up.
    """
    body = "\n".join(jp)
    try:
        import ichiran

        toks = [
            (t["bases"][0] if t["bases"] else t["surface"])
            for t in ichiran.tokens(body)
            if any("一" <= c <= "鿿" for c in t["surface"])
        ]
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
    aligned = [t for t in ichiran.align(joined) if "raw" not in t]
    return [[t for t in aligned if start <= t["start"] < end] for start, end in spans]


def _relative_clause(toks, classes):
    """A plain-form verb or i-adjective sitting directly before a noun.

    Approximate, and deliberately conservative: the noun is required to contain
    kanji, so relative clauses landing on a kana noun (ひと, ところ) are missed.
    It undercounts rather than inventing subordination that is not there.
    """
    for a, b in zip(toks, toks[1:]):
        cls = classes.get(a["bases"][0] if a["bases"] else a["surface"], [])
        if not any(c in pos.VERB_CLASSES or c in ADJ_I for c in cls):
            continue
        if not RENTAI.search(a["surface"]) or not ichiran.has_kanji(b["surface"]):
            continue
        bcls = classes.get(b["bases"][0] if b["bases"] else b["surface"], [])
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
    jp = sentences(path)
    pg = pages(path)
    lens = [len(s) for s in jp]
    body = "\n".join(jp)
    toks, real = vocabulary(jp)
    types = {}
    for t in toks:
        types[t] = types.get(t, 0) + 1

    quotes = [s for s in jp if s.startswith("「")]
    untagged = [s for s in quotes if not TAGGED.search(s)]
    run = best = 0
    for s in jp:
        if s.startswith("「") and not TAGGED.search(s):
            run += 1
            best = max(best, run)
        else:
            run = 0

    found = {k: len(re.findall(v, body)) for k, v in GRAMMAR_PATTERNS.items()}
    sub_share, sub_full = subordination(jp)
    return {
        "slug": Path(path).stem,
        "subordinate_share": sub_share,
        "subordinate_full": sub_full,
        "sentences": len(jp),
        "pages": len(pg),
        "mean_len": st.mean(lens),
        "stdev_len": st.pstdev(lens),
        "pct_over_30": 100 * sum(1 for n in lens if n > 30) / len(lens),
        "pct_under_10": 100 * sum(1 for n in lens if n < 10) / len(lens),
        "sent_per_page": len(jp) / len(pg),
        "tokens": len(toks),
        "types": len(types),
        "real_tokens": real,
        "hapax_rate": 100 * sum(1 for v in types.values() if v == 1) / len(types),
        "repeated_share": 100 * sum(v for v in types.values() if v >= 3) / len(toks),
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
        if s.startswith(("#", ">")):
            continue
        if not s:
            units.append(None)
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        en = nxt.lstrip("> ").strip() if nxt.startswith(">") else ""
        units.append((i + 1, furigana.strip(s), en))

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
            print(f"  {'tagged' if TAGGED.search(ja) else '      '} {n:>4}  {en or ja}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    ap.add_argument("--strict", action="store_true", help="exit nonzero on an unmet target")
    ap.add_argument("--turns", action="store_true",
                    help="print adjacent quoted lines so speaker alternation can be checked")
    args = ap.parse_args()

    if args.diff:
        a, b = (analyze(p) for p in args.diff)
        table([a, b], [Path(args.diff[0]).stem, Path(args.diff[1]).stem])
        return

    paths = args.paths or [STORIES / f"{s['slug']}.txt" for s in CORPUS["stories"]]

    if args.turns:
        for path in paths:
            print_turns(path)
        return
    analyses = [analyze(p) for p in paths]
    entries = {s["slug"]: s for s in CORPUS["stories"]}
    table(analyses, [a["slug"][:14] for a in analyses])

    print()
    failed = False
    for a in analyses:
        story = entries.get(a["slug"])
        if story is None:
            continue
        level = story["level"]
        fails = check_targets(a, level) + check_brief(a, story)
        if fails:
            failed = True
            print(f"{a['slug']} (level {level}):")
            for f in fails:
                print(f"  MISS  {f}")
        else:
            print(f"{a['slug']} (level {level}): targets met")
    if failed and args.strict:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
