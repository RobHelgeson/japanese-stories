#!/usr/bin/env python3
"""Build the story index page from the built readers.

Derived, never hand-written: pages, sentences, kanji-word counts, leech words
and approved words all come out of each reader's embedded DATA, and the
summaries come out of `stories-index.md`. That keeps one source for each fact
and means a rebuilt story cannot leave the index stale.

Story order is the reading order, which is deliberate and not alphabetical, so
it is passed in rather than globbed.

The page itself is contents.html / .css / .js, the same three-file shape
reader.html already had. They were one 1,050-line string literal in here until
2026-09-16, which put 40KB of CSS and JS beyond the reach of every tool that
reads either — no highlighting, no linter, no usable diff — and made this file
87% template by weight. Inlined at build time rather than linked, because the
contents page is one page: a second request buys no cache sharing, and the
harness fixture copies index.html on its own and would have to learn to carry
its siblings.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

import indexmd
import stats

HERE = Path(__file__).resolve().parent

# Reading order, levels and archived versions all come from the manifest. A
# hardcoded list was fine for five stories and does not survive fifty.
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
ORDER = [s["slug"] for s in CORPUS["stories"]]
VERSIONS = {s["slug"]: s.get("versions", []) for s in CORPUS["stories"]}
# The level was in stories-index.md's Reading Order table until that table was
# deleted; the card is the only place it is shown now. data-level is also what a
# later level filter would key on.
LEVELS = {s["slug"]: s.get("level") for s in CORPUS["stories"]}

summaries = indexmd.summaries


def template():
    """contents.html with its stylesheet and script substituted in.

    Raw, at the indentation the files themselves carry, which is what build.py
    does with __READER_CSS__ and __READER_JS__. The first cut re-indented both to
    six spaces so the output would byte-match the string literal this replaced —
    a useful proof while the extraction was being checked, and the wrong thing to
    keep: it would have silently pushed six spaces into any multi-line template
    literal, and it treated the same problem differently from the other builder.
    The marker consumes its own newline so the blank line does not survive it.
    """
    return (HERE / "contents.html").read_text(encoding="utf-8") \
        .replace("__CONTENTS_CSS__\n", (HERE / "contents.css").read_text(encoding="utf-8")) \
        .replace("__CONTENTS_JS__\n", (HERE / "contents.js").read_text(encoding="utf-8"))


def version_links(slug, versions):
    """Links to archived earlier drafts, so a rewrite can be read against them."""
    if not versions:
        return ""
    links = "".join(
        f'<a class="ver" href="versions/{html.escape(slug)}.{html.escape(v)}.html">{html.escape(v)}</a>'
        for v in versions
    )
    return f'        <div class="vers"><span>版</span>{links}<span class="cur">現行</span></div>\n'


# Rating is not a correction, so it does not sit behind 編集 with the progress
# stepper. Finishing a story and saying what it was worth is one gesture on the
# page you land on when you close the reader, or it does not happen.
STARS = "".join(
    f'\n          <button type="button" data-act="star" data-n="{n}" '
    f'aria-pressed="false" aria-label="星{n}つ">★</button>'
    for n in range(1, 6)
)


def card(story, summary, versions=()):
    href = html.escape(story["file"])
    title = html.escape(story["title"])
    reading, text = summary
    st = story["stats"]
    # One slug for the row's identity and its version hrefs, so they cannot disagree.
    slug = Path(story["file"]).stem
    lv = LEVELS.get(slug)
    chips = ""
    if st["weak"]:
        chips += f'<span class="chip weak">苦手 {html.escape("、".join(st["weak"]))}</span>'
    if st.get("approved"):
        chips += f'<span class="chip new">新出 {html.escape("、".join(st["approved"]))}</span>'
    # An unsummarised story still gets a card. index.py used to exit instead,
    # which made adding a story a two-file operation with a hard stop in the
    # middle of a rebuild; the gap is now visible on the page and in a warning.
    rt = f'<div class="rt">{html.escape(reading)}</div>\n        ' if reading else ""
    # Not escaped: indexmd.summaries returns ruby_html output, which escapes each
    # segment itself so an annotation renders and the prose around it cannot
    # inject tags. Same contract as the afterword the reader folds in.
    sum_p = f'<p class="sum">{text}</p>' if text else '<p class="sum none">—</p>'
    # data-title rather than reading the <h2> back: the heading carries the
    # level chip too, so its textContent is not the title.
    return f"""    <div class="cell" data-slug="{html.escape(slug)}" data-pages="{story["pages"]}" data-title="{title}"{f' data-level="{lv}"' if lv is not None else ""}>
      <a class="card" href="{href}">
        {rt}<h2>{title}{f'<span class="lv">Lv{lv}</span>' if lv is not None else ""}</h2>
        {sum_p}
        <div class="prog" hidden><span class="track"><i></i></span><span class="pct"></span></div>
      </a>
      <button type="button" class="disc" data-act="more" aria-expanded="false" aria-label="詳細"><span class="dlabel">詳細</span><span class="fin">了</span></button>
      <div class="meta">
        <span>{story["pages"]} ページ</span>
        <span>{story["sentences"]} 文</span>
        <span>{st["words"]} 漢字語</span>
      </div>
      <div class="chips">{chips}</div>
      <div class="rate">
        <span class="stars" role="group" aria-label="評価">{STARS}
        </span>
        <span class="mspacer"></span>
        <button type="button" class="notebtn" data-act="note" aria-expanded="false">感想</button>
      </div>
      <textarea class="note" rows="3" maxlength="2000" hidden aria-label="感想"
                placeholder="What worked, what dragged, what you had to re-read. This feeds the next story's brief."></textarea>
{version_links(slug, versions)}      <div class="manage" hidden>
        <button type="button" data-act="done">読了</button>
        <span class="step">
          <button type="button" data-act="dec" aria-label="一つ前のページへ">−</button>
          <output data-out="page">—</output>
          <button type="button" data-act="inc" aria-label="一つ先のページへ">＋</button>
        </span>
        <span class="mspacer"></span>
        <button type="button" data-act="clear">消去</button>
      </div>
    </div>
"""


read = stats.read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path, nargs="?", default=HERE.parent / "docs",
                    help="built readers; index.html is written here")
    ap.add_argument("--src", type=Path, default=HERE.parent / "stories",
                    help="where stories-index.md lives")
    ap.add_argument("names", nargs="*", default=None)
    args = ap.parse_args()

    out_dir = args.out_dir
    names = args.names or ORDER

    built = [read(out_dir / f"{n}.html") for n in names]
    sums = summaries(args.src / "stories-index.md")
    # A missing summary is a gap to fill, not a reason to stop a rebuild that
    # has already spent a minute per story in Ichiran. The card renders with an
    # em dash where the blurb goes, so the gap is visible on the page too.
    missing = [s["title"] for s in built if s["title"] not in sums]
    if missing:
        print(f"warning: no summary in stories-index.md for: {', '.join(missing)}",
              file=sys.stderr)

    cards = "".join(
        card(s, sums.get(s["title"], ("", "")), VERSIONS.get(Path(s["file"]).stem, []))
        for s in built
    )
    known = built[0]["stats"]["knownVocab"]
    totals = (
        f'{len(built)} 編 · {sum(s["pages"] for s in built)} ページ · '
        f'{sum(s["sentences"] for s in built)} 文 · 既知語彙 {known}'
    )

    out = out_dir / "index.html"
    out.write_text(
        template().replace("__CARDS__", cards).replace("__TOTALS__", totals),
        encoding="utf-8")
    print(f"{out}\n  {len(built)} stories · {totals}")


if __name__ == "__main__":
    main()
