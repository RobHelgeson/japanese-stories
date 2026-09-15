#!/usr/bin/env python3
"""A structural band from authentic children's prose, to read beside our numbers.

Every floor in corpus.json is derived from this project's own output:
min_repeated_share 0.4 came from an observed 44-62% spread, and
min_sentence_stdev 6.0 is a floor set just under the lowest any story had
recorded. A corpus measured only against itself can be no better than its own
best member, and a
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
authors score 21.2" is a far more persuasive argument for chasing a number than
"our lowest story scored 6.7" ever was. Nothing here writes to corpus.json and
nothing here exits nonzero.

THREE THINGS THAT DECIDE WHETHER THE COMPARISON IS HONEST
---------------------------------------------------------
1. LENGTH. Hapax rate and repeated_share both fall with length, so an unmatched
   comparison lies. Texts are binned against equal-width thirds of the corpus's
   own character range, computed at sample time rather than hardcoded. They are
   NOT terciles: the corpus itself splits 4/2/1 across them, so the long-bin
   comparison is against a single story. Characters and not tokens, because
   tokens are exactly what point 2 is about.

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
not. How often this happens is strongly author-dependent — measured over the
sample, 宮沢賢治 runs 96.6-100.0% untagged while 小川未明 runs 25.0-76.0% — so
what the metric reads off a reference text is typographic habit rather than
difficulty. It is computed, printed under the pooled table marked NOT
COMPARABLE, and excluded from the band.

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
# ［＃…］ and ※［＃…］ are the standard forms; ［※N］ is the inline marker a
# volunteer uses to key a note in a glossary block, and appears in 1 of 202.
CHUUKI = re.compile(r"※?［＃[^］]*］|［※\d+］")
RULE = re.compile(r"^-{10,}$")
FOOTER = re.compile(r"^(底本|訳者|入力|校正|青空文庫)[：:]")

# Sentence-final punctuation, unless a closing bracket follows it: 「…。」 is one
# sentence, not a sentence and a stray bracket.
SPLIT = re.compile(r"(?<=[。！？])(?![」』）］〉》])")

# A quote's attribution line, which continues the sentence the quote is in.
# Testing startswith("と") alone also catches ところが, とうとう, となり and
# ともだち: 21 false joins across the 202-text candidate pool, one of them inside
# the sample, where it fused two sentences into a 148-character outlier on the
# exact axes this comparison measures.
ATTRIB = re.compile(
    r"^と\s*[、。]"
    r"|^と(?:いい|いっ|いう|言|云|聞|き[きい]|答|こた|叫|さけ|尋|たず"
    r"|つぶや|続|つづ|呼|よ[びん]|思|おも|書|かい|笑|わら)"
)

# A bare section number on its own line. Unterminated, so the run-on rule would
# otherwise glue 一 to the paragraph under it — visible in 6 of the 25 sampled
# texts as a first sentence reading 一常念御坊は、….
HEADING = re.compile(r"^[一二三四五六七八九十百〇\d０-９]{1,4}$")

# 宮沢賢治 and 新美南吉 set songs and chants as runs of unpunctuated short lines,
# which the run-on rule would join into one enormous "sentence" — 9 source lines
# in タネリ, 13 in the worst candidate. Three is enough for a real sentence broken
# across a quote and its attribution, and short of a verse.
MAX_JOIN = 3

# Below this many surface-kanji tokens, repeated_share and hapax_rate stop
# describing prose and start describing the handful of words an author happened
# to write in kanji. ひよりげた is 2,252 characters and 27 such tokens across 7
# types, which scored a repeated_share of 77.8 — the highest of all 25, and an
# artifact. Such a text still measures fine structurally, so it is kept for
# sentence rhythm and dropped only from the vocabulary-shaped aggregates.
MIN_TOKENS = 100

# Apparatus a rule-delimited block can contain: the ruby legend, the input
# volunteer's notes. Used only to sanity-check the block chosen as prose.
APPARATUS = re.compile(r"^[●※]|【[^】]*】|：ルビ|表記について|入力者注")


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


def _get(url, tries=3):
    """One fetch, retried with backoff, never faster than the throttle.

    The throttle lives here rather than at the call site so it cannot be skipped
    by an early return or an exception. It was previously after the cache write
    in fetch_text(), which meant a run of server errors sent up to 202 back-to-
    back requests at a volunteer-run library with no delay at all. Retrying also
    keeps the seeded sample reproducible: a work dropped by one transient failure
    changes cell membership, and therefore changes what the seeded shuffle picks.
    """
    last = None
    for n in range(tries):
        time.sleep(0.3 * (n + 1))
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            last = e
    raise RuntimeError(f"{url} failed after {tries} tries: {last}")


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
    if "�" in text:
        print(f"  warn {work['title']}: undecodable characters, counted as prose")
    path.write_text(text, encoding="utf-8")
    return text


def body(text):
    """Prose only: header, ruby legend, 注記 and 底本 colophon all removed.

    Rule lines delimit apparatus, but they are NOT reliably paired. The obvious
    reading — first rule opens the legend, second closes it — silently destroys
    a file whose legend is introduced by a ［表記について］ heading and closed by
    a single rule, because then the rule *below* the legend is read as the one
    above the prose. On 宮沢賢治's ガドルフの百合 that returned 338 characters of
    input-volunteer glossary and discarded 5,944 characters of story, and it did
    so silently: the text simply measured too short to bin and dropped out of the
    pool. The near miss is the worse half — an apparatus block that happened to
    fall inside the length band would have entered the sample measured as prose.

    So: cut the colophon, split on rules, and keep the longest block. Both layouts
    put the story in the largest one, and neither needs its fences to be paired.
    """
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if FOOTER.match(line.strip()):
            break
        lines.append(line.rstrip())

    blocks, cur = [], []
    for line in lines:
        if RULE.match(line.strip()):
            blocks.append(cur)
            cur = []
        else:
            cur.append(line)
    blocks.append(cur)

    if len(blocks) > 1:
        prose = max(blocks, key=lambda b: sum(len(x) for x in b))
    else:
        # No rules at all, so the title and author are still attached. They end
        # at the first blank line following a non-blank one.
        prose = blocks[0]
        for i, s in enumerate(prose):
            if not s.strip() and i and prose[i - 1].strip():
                prose = prose[i + 1:]
                break

    text = CHUUKI.sub("", "\n".join(prose))
    # Full-width spaces, not just the leading indent. 新美南吉's early readers are
    # 分かち書き — word-spaced for children — and on ひよりげた the interior spaces
    # are 281 of 2,252 characters. Left in, they inflate every length axis by
    # ~12% on exactly the texts whose rhythm is being compared, and this corpus
    # has no such spaces to inflate in return.
    return "\n".join(l.replace("　", "").strip() for l in text.split("\n") if l.strip())


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
        if HEADING.match(cur):
            joined.append(cur)
            i += 1
            continue
        for _ in range(MAX_JOIN):
            if i + 1 >= len(lines):
                break
            nxt = lines[i + 1]
            runs_on = not cur.endswith(ENDS)
            attribution = cur.endswith(("」", "』")) and ATTRIB.match(nxt)
            if not (runs_on or attribution) or HEADING.match(nxt):
                break
            cur += nxt
            i += 1
        joined.append(cur)
        i += 1
    return [s.strip() for l in joined for s in SPLIT.split(l) if s.strip()]


def corpus_bins():
    """Equal-width thirds of the corpus's character range, and its per-story chars.

    Computed rather than hardcoded so the bins follow the corpus as it grows.
    Characters, not tokens — see point 2 in the module docstring.

    Counted over prose_sentences, which is what stats.measure reports `chars`
    over. Counting source lines here instead put the edges in different units
    from the value binned against them, and once a line became a whole speech
    turn upstream the two drifted far enough that a story fell outside its own
    corpus's range and binned as None.
    """
    sizes = []
    for s in stats.CORPUS["stories"]:
        jp = stats.prose_sentences(stats.sentences(stats.STORIES / f"{s['slug']}.txt"))
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
                    "equal-width character thirds. This is a band to read beside our numbers, "
                    "never a floor: "
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

    edges, _ = corpus_bins()
    ref = []
    for i, w in enumerate(texts, 1):
        print(f"segmenting {i}/{len(texts)} {w['author']} {w['title']}", flush=True)
        jp = to_sentences(fetch_text(w))
        a = stats.measure(jp)
        # stats.py degrades to a kanji-run regex when Ichiran is down, and says so
        # only in these two flags. Unchecked, an outage prints a complete and
        # plausible band in which lemma_repeated_share exactly equals
        # repeated_share — i.e. one that quietly reports the opposite of the
        # orthography finding this whole module is built on.
        if not a["real_tokens"] or not a["subordinate_full"]:
            raise SystemExit(
                f"Ichiran unavailable (real_tokens={a['real_tokens']}, "
                f"subordinate_full={a['subordinate_full']}) on {w['title']}. "
                "The band would be measured by the regex fallback and is not "
                "comparable; set ICHIRAN_URL and re-run."
            )
        a["dialogue_any_pct"] = dialogue_any_pct(jp)
        a["author"], a["title"] = w["author"], w["title"]
        a["thin"] = a["tokens"] < MIN_TOKENS
        # Binned live off the measured value rather than read from the manifest.
        # The manifest records what --sample measured, and a change to the
        # sentence split moves both corpora; trusting it would compare a
        # freshly-measured story against a stale bin.
        a["bin"] = bin_of(a["chars"], edges)
        ref.append(a)

    thin = [r for r in ref if r["thin"]]
    if thin:
        print(f"\n{len(thin)} text(s) under {MIN_TOKENS} surface-kanji tokens; kept for")
        print("sentence structure, excluded from repeated_share / hapax_rate:")
        for r in thin:
            print(f"  {r['author']} {r['title']} — {r['tokens']} tokens, {r['chars']} chars")

    ours = []
    for s in stats.CORPUS["stories"]:
        path = stats.STORIES / f"{s['slug']}.txt"
        a = stats.analyze(path)
        a["dialogue_any_pct"] = dialogue_any_pct(stats.sentences(path))
        a["bin"] = bin_of(a["chars"], edges)
        ours.append(a)
    levels = {s["slug"]: s["level"] for s in stats.CORPUS["stories"]}

    def pool(key, b=None):
        """Reference values for a metric, bin-restricted and thin-filtered."""
        vocab_shaped = "repeated_share" in key or "hapax" in key
        return [
            r[key] for r in ref
            if (b is None or r["bin"] == b) and not (vocab_shaped and r["thin"])
        ]

    print("\n" + "=" * 104)
    print("OUR CORPUS vs AUTHENTIC 児童文学  —  a band to read beside, NOT a floor")
    print("=" * 104)
    w1 = 24
    bins = ("short", "mid", "long")
    # Each story sits under the reference median for ITS OWN length bin. A single
    # pooled column was the first version and it was quietly dishonest: the
    # corpus splits 4/2/1 across these bins while the reference splits 7/9/9, so
    # for repeated_share — the one axis that really moves with length — our four
    # short stories appeared to sit at the authentic median when bin-matched they
    # are about a third above it.
    print(f"{'metric':<{w1}}" + "".join(f"{('L%d' % levels[a['slug']]):>8}" for a in ours)
          + f"{'│':>3}" + "".join(f"{('ref ' + b):>9}" for b in bins))
    print(f"{'(our story bin)':<{w1}}" + "".join(f"{(a['bin'] or '—')[:5]:>8}" for a in ours)
          + f"{'│':>3}" + "".join(f"{('n=%d' % len(pool('mean_len', b))):>9}" for b in bins))
    for key, fmt in BAND:
        row = f"{key:<{w1}}" + "".join(fmt.format(a[key]).rjust(8) for a in ours)
        cells = []
        for b in bins:
            vals = pool(key, b)
            cells.append(fmt.format(st.median(vals)) if vals else "-")
        print(row + f"{'│':>3}" + "".join(c.rjust(9) for c in cells))

    print(f"\n{'pooled reference':<{w1}}{'median':>10}{'IQR':>18}")
    for key, fmt in BAND:
        med, lo, hi = _iqr(pool(key))
        print(f"{key:<{w1}}{fmt.format(med):>10}"
              + f"{(fmt.format(lo) + '-' + fmt.format(hi)):>18}")

    med, lo, hi = _iqr([r["untagged_pct"] for r in ref])
    print(f"{'untagged_pct':<{w1}}{med:>10.1f}{(str(round(lo,1)) + '-' + str(round(hi,1))):>18}"
          + "   NOT COMPARABLE")
    print("    Aozora usually sets attribution in the sentence after the quote, where")
    print("    stats.TAGGED cannot see it. Strongly author-dependent rather than")
    print("    universal — 宮沢賢治 runs near 100%, 小川未明 as low as 25% — so it")
    print("    measures typographic habit, not difficulty. Excluded from the band.")

    print("\nper author (median), to show whether one band is even a fair summary:")
    print(f"{'metric':<{w1}}" + "".join(f"{a:>12}" for a in sorted({r['author'] for r in ref}))
          + f"{'spread':>10}")
    authors = sorted({r["author"] for r in ref})
    for key, fmt in BAND:
        vocab_shaped = "repeated_share" in key or "hapax" in key
        meds = []
        for a in authors:
            vals = [
                r[key] for r in ref
                if r["author"] == a and not (vocab_shaped and r["thin"])
            ]
            meds.append(st.median(vals) if vals else None)
        cells = "".join((fmt.format(m) if m is not None else "-").rjust(12) for m in meds)
        got = [m for m in meds if m is not None]
        spread = fmt.format(max(got) - min(got)) if len(got) > 1 else "-"
        print(f"{key:<{w1}}{cells}{spread:>10}")

    print(f"\nreference n={len(ref)}  "
          f"chars {min(r['chars'] for r in ref)}-{max(r['chars'] for r in ref)}  "
          f"(corpus {man['corpus_chars']['min']}-{man['corpus_chars']['max']}, "
          f"bins are equal-WIDTH thirds, not terciles: we split "
          f"{'/'.join(str(sum(1 for a in ours if a['bin'] == b)) for b in bins)} across them)")
    stray = [r for r in ref if r["bin"] is None]
    if stray:
        print(f"{len(stray)} reference text(s) now outside the corpus character range, "
              "pooled only:")
        for r in stray:
            print(f"  {r['author']} {r['title']} — {r['chars']} chars")
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
