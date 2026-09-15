#!/usr/bin/env python3
"""A structural band from authentic children's prose, to read beside our numbers.

Every floor in corpus.json is derived from this project's own output:
min_repeated_share 0.4 came from an observed 44-62% spread, and
min_sentence_stdev 6.0 is the best value any story has ever hit. A corpus
measured only against itself can be no better than its own best member, and a
systemic flatness in it would be invisible. This reads the same axes off
public-domain 児童文学 so the corpus has something outside itself to sit beside.

青空文庫 is the source, and it already shares this project's ruby syntax:
｜漢字《かな》 is Aozora's own convention, so furigana.strip() reads a downloaded
text with no translation step. The subset is 新美南吉, 宮沢賢治 and 小川未明 in
新字新仮名, NDC K913 — children's literature, which is the closest authentic
analogue to a graded reader. Deliberately not 漱石 or 芥川: pre-war literary
Japanese sets a bar modern prose would not clear either.

WHAT THIS MUST NEVER DO
-----------------------
Report anything about the known-word constraint. new_words, leech_seeds and the
unknown-token checks are meaningless on a text nobody wrote to Rob's vocabulary,
and a number that looks like a vocabulary finding here would be pure noise. This
module therefore never imports vocab or check, and test_no_vocab_import() asserts
it — the guarantee is structural rather than a matter of remembering.

AND WHAT IT MUST NEVER BECOME
-----------------------------
A floor. AUTHORING.md's "metrics are floors, not targets" clause is load-bearing:
two of the four documented failure modes were *caused* by optimising a metric.
A reference band converted into a gate is that same failure wearing a better
disguise, and it would be worse than the failures it replaced, because "real
authors score 15.8" is a far more persuasive argument for chasing a number than
"our best story scored 6.5" ever was. Nothing here writes to corpus.json and
nothing here exits nonzero.

THREE THINGS THAT DECIDE WHETHER THE COMPARISON IS HONEST
---------------------------------------------------------
1. LENGTH. Hapax rate and repeated_share both fall with length, so an unmatched
   comparison lies. Texts are binned against the corpus's own character terciles,
   computed at sample time rather than hardcoded. Characters and not tokens,
   because tokens are exactly what point 2 is about.

2. ORTHOGRAPHY, which is the confound the plan for this work did not anticipate.
   stats.py's `tokens` counts tokens whose *surface* carries kanji. Children's
   books write verbs in kana for children who cannot yet read kanji; this project
   writes them in kanji because kanji recognition is the entire point. Measured on
   新美南吉's 飴だま: 18% of tokens keep kanji on the surface, against 48-52% here.
   Binning on `tokens` would therefore pair an Aozora text against a corpus story
   roughly 2.7x shorter in real terms — the precise lie point 1 exists to prevent,
   arriving through a different door. repeated_share and hapax_rate are reported
   on BOTH bases for the same reason: on the surface basis they measure recycling
   among the nouns an author chose to write in kanji here and nearly everything
   there, which is not one measurement.

3. ERA AND REGISTER. Only structure is comparable. Anything vocabulary-shaped is
   noise and is not reported.

A FOURTH, FOUND WHILE BUILDING: untagged_pct DOES NOT TRANSFER.
Aozora sets a quote on its own line and its attribution in the *next* sentence:

    「おオい、ちょっとまってくれ。」
    と、どての向こうから手をふりながら、さむらいが走ってきて、舟にとびこみました。

stats.py's TAGGED looks inside the quoted sentence, where と、 structurally is
not. Every Aozora quote reads untagged, which is a typographic convention and not
a difficulty. It is computed, shown struck through, and excluded from the band.

A FIFTH: 小川未明 is 505 of the 617 eligible texts. An unstratified draw would
measure one author's idiolect and call it authentic prose, so the sample is drawn
per author and the per-author bands are printed. If the three authors disagree
more than we differ from them, there is no single band worth quoting.

Usage:
    export ICHIRAN_URL=http://host:3005
    python3 reference.py --sample     # choose texts, write reference.json
    python3 reference.py --compare    # measure them, print the band
"""

import argparse
import csv
import io
import json
import random
import re
import statistics as st
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import furigana
import stats

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".refcache"
MANIFEST = HERE / "reference.json"

INDEX_URL = "https://www.aozora.gr.jp/index_pages/list_person_all_extended_utf8.zip"
AUTHORS = ("新美 南吉", "宮沢 賢治", "小川 未明")

# NDC K913 is juvenile Japanese fiction; the K is what makes it children's
# literature rather than 913's general fiction. 新字新仮名 is the transcription
# policy of the 底本, not the author's own orthography, and it is what makes a
# pre-war text readable as modern prose.
NDC = "K913"
ORTHOGRAPHY = "新字新仮名"

UA = {"User-Agent": "japanese-stories/reference (personal research; low volume)"}

# Aozora's own markup. ［＃…］ is 注記, the input volunteer's structural and
# typographic notes; ※［＃…］ is a gaiji description standing in for a character
# outside JIS X 0208. Both are apparatus rather than prose and neither should
# reach a sentence-length measurement.
CHUUKI = re.compile(r"※?［＃[^］]*］")
LEGEND = re.compile(r"^-{10,}$")
FOOTER = re.compile(r"^(底本|訳者|入力|校正|青空文庫)[：:]")

# Sentence-final punctuation, unless a closing bracket follows it: 「…。」 is one
# sentence, not a sentence and a stray bracket.
SPLIT = re.compile(r"(?<=[。！？])(?![」』）］〉》])")


def test_no_vocab_import():
    """The known-word modules must not be reachable from here.

    Asserted rather than documented because the prohibition is the one thing
    about this module that cannot be allowed to erode: a number derived from
    Rob's vocabulary would look like a finding and mean nothing.
    """
    banned = {"vocab", "check"} & set(sys.modules)
    if banned:
        raise AssertionError(f"reference.py must not reach {sorted(banned)}")
    return True


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def index_rows():
    """The Aozora master index, cached. One fetch instead of 617 card scrapes."""
    path = CACHE / "aozora-index.csv"
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        blob = _get(INDEX_URL)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            path.write_bytes(z.read(name))
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def eligible(rows):
    """Public-domain 児童文学 by the three authors, in modern orthography."""
    out = []
    for r in rows:
        if r["役割フラグ"] != "著者":
            continue
        if f"{r['姓']} {r['名']}" not in AUTHORS:
            continue
        if r["文字遣い種別"] != ORTHOGRAPHY:
            continue
        if r["作品著作権フラグ"] != "なし" or r["人物著作権フラグ"] != "なし":
            continue
        if NDC not in r["分類番号"]:
            continue
        if not r["テキストファイルURL"].endswith(".zip"):
            continue
        out.append(
            {
                "id": r["作品ID"],
                "author": f"{r['姓']}{r['名']}",
                "title": r["作品名"],
                "url": r["テキストファイルURL"],
            }
        )
    return out


def fetch_text(work):
    """The raw Shift_JIS text of one work, cached on disk."""
    path = CACHE / f"{work['id']}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    CACHE.mkdir(exist_ok=True)
    blob = _get(work["url"])
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        raw = z.read(name)
    text = raw.decode("shift_jis", errors="replace")
    path.write_text(text, encoding="utf-8")
    time.sleep(0.3)  # Aozora is a volunteer library; do not hammer it.
    return text


def body(text):
    """Prose only: header, ruby legend, 注記 and 底本 colophon all removed.

    An Aozora file opens with title and author, optionally a legend block fenced
    by two rules explaining the ruby notation, then the prose, then a colophon.
    The header ends at the first blank line, which is the one structural rule the
    format keeps consistently enough to parse on.
    """
    lines, seen_rule, out = text.replace("\r\n", "\n").split("\n"), 0, []
    for line in lines:
        s = line.rstrip()
        if FOOTER.match(s.strip()):
            break
        if LEGEND.match(s.strip()):
            seen_rule += 1
            continue
        if seen_rule == 1:  # inside the legend block
            continue
        out.append(s)
    # Drop the title/author header: everything up to and including the first
    # blank line that follows a non-blank one.
    start = 0
    for i, s in enumerate(out):
        if not s.strip() and i and out[i - 1].strip():
            start = i + 1
            break
    out = out[start:]
    text = "\n".join(out)
    text = CHUUKI.sub("", text)
    return "\n".join(l.lstrip("　 ") for l in text.split("\n") if l.strip())


ENDS = ("。", "！", "？", "」", "』", "）")


def to_sentences(text):
    """One authored sentence per element, Aozora's line breaks undone.

    Aozora breaks a line wherever a quote starts, so a single sentence is
    routinely spread over three lines:

        舟が出ようとすると、
        「おオい、ちょっとまってくれ。」
        と、どての向こうから手をふりながら、さむらいが走ってきて、とびこみました。

    Splitting per line scores that as three sentences of 10, 16 and 35
    characters instead of one of 61, which drives mean_len and pct_over_30 down
    and the sentence count up — precisely the axes this whole comparison exists
    to test, and in precisely the direction that would flatter our corpus. So a
    line that does not end in sentence-final punctuation is joined to the next,
    and a 「…」 line is joined to a following line that opens with と, which is
    Aozora's attribution shape rather than a new sentence.

    This does mean a quote stops being sentence-initial, so stats.measure's
    dialogue_pct and untagged_pct are not readable off the result. That is
    handled rather than hidden: untagged_pct is excluded from the band outright,
    and dialogue is reported as dialogue_any_pct, computed the same way on both
    corpora so neither is measured by a rule written for the other.
    """
    lines = [
        furigana.strip(l).strip()
        for l in body(text).split("\n")
        if furigana.strip(l).strip()
    ]
    joined, i = [], 0
    while i < len(lines):
        cur = lines[i]
        while i + 1 < len(lines):
            nxt = lines[i + 1]
            runs_on = not cur.endswith(ENDS)
            attribution = cur.endswith(("」", "』")) and nxt.startswith("と")
            if not (runs_on or attribution):
                break
            cur += nxt
            i += 1
        joined.append(cur)
        i += 1
    return [s.strip() for l in joined for s in SPLIT.split(l) if s.strip()]


def corpus_bins():
    """The corpus's own character terciles, and its per-story characters.

    Computed rather than hardcoded so the bins follow the corpus as it grows.
    Characters, not tokens — see point 2 in the module docstring.
    """
    sizes = []
    for s in stats.CORPUS["stories"]:
        jp = stats.sentences(stats.STORIES / f"{s['slug']}.txt")
        sizes.append(sum(len(x) for x in jp))
    lo, hi = min(sizes), max(sizes)
    a = lo + (hi - lo) / 3
    b = lo + 2 * (hi - lo) / 3
    return (lo, a, b, hi), sizes


def bin_of(chars, edges):
    lo, a, b, hi = edges
    if chars < lo or chars > hi:
        return None
    return "short" if chars < a else "mid" if chars < b else "long"


def sample(per_cell=3, seed=20260914, pool_cap=90):
    """Choose the reference texts and write the manifest.

    Stratified by author because 小川未明 is 505 of the 617 eligible works and a
    proportional draw would be a study of 小川未明. Capped per author for the
    same reason on the download side: the two scarce authors are taken whole, the
    abundant one is sampled, so the candidate pool costs ~200 small requests
    rather than 617.
    """
    rng = random.Random(seed)
    pool = eligible(index_rows())
    by_author = {}
    for w in pool:
        by_author.setdefault(w["author"], []).append(w)

    edges, corpus_sizes = corpus_bins()
    print(f"corpus characters {int(edges[0])}-{int(edges[3])}, "
          f"bin edges {int(edges[1])} / {int(edges[2])}")
    for a, ws in sorted(by_author.items()):
        print(f"  eligible  {a:<8} {len(ws)}")

    candidates = []
    for author, ws in sorted(by_author.items()):
        picked = ws if len(ws) <= pool_cap else rng.sample(ws, pool_cap)
        print(f"\nmeasuring {author}: {len(picked)} candidates")
        for i, w in enumerate(picked, 1):
            try:
                chars = sum(len(s) for s in to_sentences(fetch_text(w)))
            except Exception as e:
                print(f"  skip {w['title']}: {e}")
                continue
            w = dict(w, chars=chars, bin=bin_of(chars, edges))
            candidates.append(w)
            if i % 25 == 0:
                print(f"  {i}/{len(picked)}")

    chosen = []
    for author in sorted(by_author):
        for name in ("short", "mid", "long"):
            cell = [c for c in candidates if c["author"] == author and c["bin"] == name]
            rng.shuffle(cell)
            chosen.extend(cell[:per_cell])
            print(f"cell {author:<8} {name:<6} {len(cell):>3} eligible -> {len(cell[:per_cell])}")

    MANIFEST.write_text(
        json.dumps(
            {
                "_comment": (
                    "Reference texts for the structural band, chosen by reference.py "
                    "--sample. Stratified by author and by the corpus's own character "
                    "terciles. This is a band to read beside our numbers, never a floor: "
                    "see reference.py's docstring and AUTHORING.md's 'Metrics are floors, "
                    "not targets'."
                ),
                "seed": seed,
                "per_cell": per_cell,
                "corpus_chars": {"min": int(edges[0]), "max": int(edges[3])},
                "bin_edges": [int(edges[1]), int(edges[2])],
                "texts": sorted(chosen, key=lambda c: (c["author"], c["chars"])),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n{len(chosen)} texts -> {MANIFEST.name}")


# The axes that survive an era, a register and an orthography difference. pages,
# sent_per_page and the token counts are omitted: the first two need authored
# page breaks a reference text has none of, and the third is the orthography
# confound itself rather than a measure through it.
BAND = [
    ("mean_len", "{:.1f}"),
    ("stdev_len", "{:.1f}"),
    ("pct_over_30", "{:.1f}"),
    ("pct_under_10", "{:.1f}"),
    ("subordinate_share", "{:.1f}"),
    ("repeated_share", "{:.1f}"),
    ("lemma_repeated_share", "{:.1f}"),
    ("hapax_rate", "{:.1f}"),
    ("lemma_hapax_rate", "{:.1f}"),
    ("dialogue_any_pct", "{:.1f}"),
    ("distinct_constructions", "{:.0f}"),
]


def dialogue_any_pct(jp):
    """Share of sentences containing a quote, wherever in the sentence it sits.

    stats.measure's dialogue_pct tests startswith("「"), which is exact for this
    project's one-sentence-per-line sources and wrong for reconstructed Aozora
    sentences, where the quote usually sits between a setup clause and its
    attribution. Measured here, the same way on both sides, rather than by
    loosening stats.py and moving seven settled numbers.
    """
    return 100 * sum(1 for s in jp if "「" in s) / len(jp)


def _iqr(vals):
    vals = sorted(vals)
    if len(vals) < 4:
        return st.median(vals), min(vals), max(vals)
    q = st.quantiles(vals, n=4)
    return st.median(vals), q[0], q[2]


def compare():
    test_no_vocab_import()
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    texts = man["texts"]

    ref = []
    for i, w in enumerate(texts, 1):
        print(f"segmenting {i}/{len(texts)} {w['author']} {w['title']}", flush=True)
        jp = to_sentences(fetch_text(w))
        a = stats.measure(jp)
        a["dialogue_any_pct"] = dialogue_any_pct(jp)
        a["author"], a["title"], a["bin"] = w["author"], w["title"], w["bin"]
        ref.append(a)

    ours = []
    for s in stats.CORPUS["stories"]:
        path = stats.STORIES / f"{s['slug']}.txt"
        a = stats.analyze(path)
        a["dialogue_any_pct"] = dialogue_any_pct(stats.sentences(path))
        ours.append(a)
    levels = {s["slug"]: s["level"] for s in stats.CORPUS["stories"]}

    print("\n" + "=" * 96)
    print("OUR CORPUS vs AUTHENTIC 児童文学  —  a band to read beside, NOT a floor")
    print("=" * 96)
    w1 = 24
    print(f"{'metric':<{w1}}" + "".join(f"{('L%d' % levels[a['slug']]):>8}" for a in ours)
          + f"{'│':>4}{'ref med':>10}{'ref IQR':>16}")
    for key, fmt in BAND:
        row = f"{key:<{w1}}" + "".join(fmt.format(a[key]).rjust(8) for a in ours)
        med, lo, hi = _iqr([r[key] for r in ref])
        print(row + f"{'│':>4}{fmt.format(med):>10}"
              + f"{(fmt.format(lo) + '-' + fmt.format(hi)):>16}")

    med, lo, hi = _iqr([r["untagged_pct"] for r in ref])
    print(f"{'untagged_pct':<{w1}}" + "".join("{:.1f}".format(a["untagged_pct"]).rjust(8) for a in ours)
          + f"{'│':>4}{med:>10.1f}{(str(round(lo,1)) + '-' + str(round(hi,1))):>16}"
          + "   NOT COMPARABLE")
    print("    untagged_pct: Aozora sets attribution in the sentence after the quote,")
    print("    so every quote reads untagged. Convention, not difficulty. Excluded.")

    print("\nper author (median), to show whether one band is even a fair summary:")
    print(f"{'metric':<{w1}}" + "".join(f"{a:>12}" for a in sorted({r['author'] for r in ref}))
          + f"{'spread':>10}")
    for key, fmt in BAND:
        meds = [st.median([r[key] for r in ref if r["author"] == a])
                for a in sorted({r["author"] for r in ref})]
        print(f"{key:<{w1}}" + "".join(fmt.format(m).rjust(12) for m in meds)
              + fmt.format(max(meds) - min(meds)).rjust(10))

    print("\nby length bin (reference median), the control for point 1:")
    print(f"{'metric':<{w1}}" + "".join(f"{b:>12}" for b in ("short", "mid", "long")))
    for key, fmt in BAND:
        cells = []
        for b in ("short", "mid", "long"):
            vals = [r[key] for r in ref if r["bin"] == b]
            cells.append(fmt.format(st.median(vals)) if vals else "-")
        print(f"{key:<{w1}}" + "".join(c.rjust(12) for c in cells))

    print(f"\nreference n={len(ref)}  "
          f"chars {min(r['chars'] for r in ref)}-{max(r['chars'] for r in ref)}  "
          f"(corpus {man['corpus_chars']['min']}-{man['corpus_chars']['max']})")
    print("NOTHING HERE IS A GATE. No corpus.json threshold is written by this script.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", action="store_true", help="choose texts, write reference.json")
    ap.add_argument("--compare", action="store_true", help="measure them, print the band")
    ap.add_argument("--per-cell", type=int, default=3)
    args = ap.parse_args()
    if args.sample:
        sample(per_cell=args.per_cell)
    elif args.compare:
        compare()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
