#!/usr/bin/env python3
"""Build the story index page from the built readers.

Derived, never hand-written: pages, sentences, kanji-word counts, leech words
and approved words all come out of each reader's embedded DATA, and the
summaries come out of `stories-index.md`. That keeps one source for each fact
and means a rebuilt story cannot leave the index stale.

Story order is the reading order, which is deliberate and not alphabetical, so
it is passed in rather than globbed.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

import indexmd
import stats

# Reading order, levels and archived versions all come from the manifest. A
# hardcoded list was fine for five stories and does not survive fifty.
CORPUS = json.loads((Path(__file__).resolve().parent / "corpus.json").read_text(encoding="utf-8"))
ORDER = [s["slug"] for s in CORPUS["stories"]]
VERSIONS = {s["slug"]: s.get("versions", []) for s in CORPUS["stories"]}
# The level was in stories-index.md's Reading Order table until that table was
# deleted; the card is the only place it is shown now. data-level is also what a
# later level filter would key on.
LEVELS = {s["slug"]: s.get("level") for s in CORPUS["stories"]}

summaries = indexmd.summaries


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
    sum_p = f'<p class="sum">{html.escape(text)}</p>' if text else '<p class="sum none">—</p>'
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
    HERE = Path(__file__).resolve().parent
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
        TEMPLATE.replace("__CARDS__", cards)
        .replace("__TOTALS__", totals)
        # Hand-kept until 2026-09-14, and one story short of the count printed
        # in the header the whole time.
        .replace("__TITLES__", html.escape(" · ".join(s["title"] for s in built))),
        encoding="utf-8")
    print(f"{out}\n  {len(built)} stories · {totals}")


TEMPLATE = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#faf7f0" />
    <!-- start_url points here, so this is the page an install opens on. -->
    <link rel="manifest" href="manifest.webmanifest" />
    <link rel="apple-touch-icon" href="apple-touch-icon.png" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="default" />
    <title>物語 — 目次</title>
    <style>
      :root {
        --paper: #faf7f0;
        --ink: #22201c;
        --muted: #8a8377;
        --rule: #e2dcd0;
        --accent: #7a5c2e;
        --weak: #da117b;
        --new: #0d7c86;
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --paper: #16151a;
          --ink: #e8e4dc;
          --muted: #8b8578;
          --rule: #2c2a31;
          --accent: #d3b075;
          --weak: #f74395;
          --new: #4fc2ce;
        }
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--paper);
        color: var(--ink);
        font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
      }
      header, footer {
        display: flex;
        align-items: baseline;
        gap: 1rem;
        padding: 0.9rem 1.5rem;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.85rem;
        color: var(--muted);
      }
      /* Sticky rather than the reader's fixed frame. This page is one long
         scrolling list, so pinning <main> as its own scroll container would
         inset the scrollbar to the 46rem column, and a pinned footer would
         hold nothing worth keeping on screen. An opaque background is required
         or the cards show through as they pass under it. */
      header {
        border-bottom: 1px solid var(--rule);
        position: sticky;
        top: 0;
        z-index: 2;
        background: var(--paper);
      }
      footer { border-top: 1px solid var(--rule); margin-top: auto; }
      h1 { font-size: 1.1rem; margin: 0; color: var(--ink); font-weight: 600; white-space: nowrap; }
      .spacer { flex: 1; }
      header { gap: 0.6rem; }
      #totals { min-width: 0; text-align: right; line-height: 1.4; }
      header .btn { flex: none; }

      main {
        flex: 1;
        width: 100%;
        max-width: 46rem;
        margin: 0 auto;
        padding: 2.5rem 1.5rem 3rem;
      }
      .lede {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.95rem;
        line-height: 1.65;
        color: var(--muted);
        margin: 0 0 2rem;
      }

      /* Reading order is the point of the list, so the cards are a single
         column and carry their position rather than being a grid to scan.

         The box is drawn on .cell rather than on the a.card inside it. Every
         control — the stepper, the stars, the 感想 box, the version links —
         has to sit outside the anchor, because a button or a link nested in a
         link is invalid and browsers silently close the outer one. With the
         border on the anchor those controls all fell outside the box they
         belong to, and the 詳細 disclosure had revealed content on both sides
         of itself. One box per story, and the anchor is just the part of it
         that navigates. */
      .cell {
        position: relative;
        padding: 1.3rem 1.5rem 1.2rem 3.4rem;
        margin-bottom: 0.9rem;
        border: 1px solid var(--rule);
        border-radius: 10px;
        counter-increment: story;
        transition: border-color 0.12s ease, background 0.12s ease;
      }
      .card {
        display: block;
        text-decoration: none;
        color: inherit;
      }
      main { counter-reset: story; }
      .cell::before {
        content: counter(story);
        position: absolute;
        left: 1.4rem;
        top: 1.45rem;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.8rem;
        font-variant-numeric: tabular-nums;
        color: var(--muted);
      }
      /* Keyed on the anchor, not on the box. The box is the whole row now, but
         only a.card navigates — lighting the row up while the pointer sits on
         the stars or the 感想 box promises a click that does nothing. */
      .cell:has(a.card:hover) {
        border-color: var(--accent);
        background: color-mix(in srgb, var(--accent) 6%, transparent);
      }
      .card .rt {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.68rem;
        letter-spacing: 0.06em;
        color: var(--accent);
        margin-bottom: 0.15rem;
      }
      .card h2 { font-size: 1.7rem; margin: 0 0 0.5rem; font-weight: 600; }
      .sum {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.95rem;
        line-height: 1.6;
        color: var(--ink);
        margin: 0 0 0.7rem;
      }
      .meta, .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.9rem;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.74rem;
        color: var(--muted);
        font-variant-numeric: tabular-nums;
      }
      .meta { margin-top: 0.45rem; }
      .chips { gap: 0.5rem; margin-top: 0.5rem; }
      /* Earlier drafts, so a rewrite can be read against what it replaced. */
      .vers {
        display: flex; align-items: center; gap: 0.4rem;
        margin-top: 0.55rem; font-size: 0.72rem; opacity: 0.7;
      }
      .vers .ver, .vers .cur {
        border: 1px solid var(--rule); border-radius: 999px; padding: 0.05rem 0.5rem;
      }
      .vers .ver { color: var(--accent); text-decoration: none; }
      .vers .ver:hover { border-color: var(--accent); }
      .vers .cur { background: var(--rule); }
      .chip {
        padding: 0.12rem 0.5rem;
        border-radius: 4px;
        border: 1px solid var(--rule);
      }
      .chip.weak { color: var(--weak); border-color: color-mix(in srgb, var(--weak) 40%, transparent); }
      .chip.new { color: var(--new); border-color: color-mix(in srgb, var(--new) 40%, transparent); }

      /* The level was the one column of the deleted Reading Order table that
         nothing else showed. */
      .lv {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.62rem;
        font-weight: 400;
        letter-spacing: 0.04em;
        color: var(--muted);
        border: 1px solid var(--rule);
        border-radius: 999px;
        padding: 0.1rem 0.45rem;
        margin-inline-start: 0.6rem;
        vertical-align: 0.35em;
      }
      .sum.none { color: var(--muted); }

      /* Collapsed is the default, and the line it draws is what you need to
         PICK a story against what you need to FINISH with one. Title, reading,
         level, blurb and the bar stay; the counts, the marked words, the stars,
         the 感想 box and the version links wait behind 詳細. At seven stories
         this is tidiness; the list is what it is protecting at fifty. */
      .cell:not(.open) .meta,
      .cell:not(.open) .chips,
      .cell:not(.open) .rate,
      .cell:not(.open) .note,
      .cell:not(.open) .vers { display: none; }
      .disc {
        display: block;
        margin: 0.1rem 0 0;
        /* Same trade the .btn pills make: 44px of hit area, nowhere near 44px
           of ink. This one gates every detail on every row, so it is the last
           control on the page that should be hard to hit with a thumb. */
        padding: 0.6rem 0.7rem 0.6rem 0;
        min-height: 44px;
        border: 0;
        background: none;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.72rem;
        color: var(--muted);
        text-align: start;
        cursor: pointer;
      }
      .disc:hover { color: var(--accent); }
      .disc::before { content: "▸ "; }
      .cell.open .disc::before { content: "▾ "; }
      .disc .fin { display: none; }

      /* A story you have finished is a line, not a card. Collapsed is already
         the default, but the default still spends a reading, a title, three
         lines of blurb and a full bar on something there is nothing left to
         decide about — and the list is a ladder walked down once, so what is
         behind you is most of what you scroll past. 了 is the whole of what a
         finished row still has to say.

         The title stays a link, because finishing a story is not the same as
         being done with it. Everything else on the line — from the title's end
         to the right edge — is the disclosure, which is why .disc takes the
         rest of the row rather than sitting under it. */
      .cell.done:not(.open) {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        padding-top: 0.15rem;
        padding-bottom: 0.15rem;
      }
      /* The row is one 44px line now, so the counter's fixed top would sit it
         above the title. Not 50% — 編集 wraps .manage onto a second line, and a
         centred number would then float between the two. */
      .cell.done:not(.open)::before { top: 1rem; }
      .cell.done:not(.open) .rt,
      .cell.done:not(.open) .sum,
      .cell.done:not(.open) .prog { display: none; }
      .cell.done:not(.open) .card { min-width: 0; }
      .cell.done:not(.open) h2 { font-size: 1.05rem; margin: 0; }
      .cell.done:not(.open) .manage { flex: 0 0 100%; }
      /* flex: 1 is the hit area. The 44px the tall form buys with padding, this
         form buys by spanning the row — the same trade, and a bigger target. */
      .cell.done:not(.open) .disc {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.35rem;
        margin: 0;
        padding: 0 0 0 0.7rem;
      }
      .cell.done:not(.open) .disc::before { content: "▸"; }
      .cell.done:not(.open) .disc .dlabel { display: none; }
      /* Reads as a .chip.new, because that is what it is: a mark on the story
         rather than a label on the control. */
      .cell.done:not(.open) .disc .fin {
        display: inline-block;
        font-size: 0.78rem;
        color: var(--new);
        border: 1px solid color-mix(in srgb, var(--new) 40%, transparent);
        border-radius: 4px;
        padding: 0.12rem 0.5rem;
      }
      .cell.done:not(.open) .disc:hover .fin {
        background: color-mix(in srgb, var(--new) 12%, transparent);
      }

      /* Continue reading. The catalogue is a ladder you walk down once, so the
         one row that matters on almost every visit is the story already open —
         which is otherwise however far down the list you have got. Built from
         the progress map at paint time, so it costs nothing at build time and
         is simply absent on a device that has never read anything. */
      .resume {
        display: flex;
        align-items: baseline;
        gap: 0.7rem;
        margin: 0 0 1.6rem;
        padding: 0.9rem 1.1rem;
        border: 1px solid var(--accent);
        border-radius: 10px;
        background: color-mix(in srgb, var(--accent) 7%, transparent);
        text-decoration: none;
        color: inherit;
      }
      .resume[hidden] { display: none; }
      .resume:hover { background: color-mix(in srgb, var(--accent) 13%, transparent); }
      .resume .rlabel {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        color: var(--accent);
        white-space: nowrap;
      }
      .resume .rtitle { font-size: 1.15rem; font-weight: 600; }
      .resume .rpct {
        margin-inline-start: auto;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.72rem;
        color: var(--muted);
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
      }

      .prog {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-top: 0.55rem;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.72rem;
        color: var(--muted);
        font-variant-numeric: tabular-nums;
      }
      /* display:flex would otherwise beat the UA's [hidden] rule and show an
         empty bar on every unread story. */
      .prog[hidden] { display: none; }
      .prog .track {
        flex: 1;
        max-width: 9rem;
        height: 3px;
        border-radius: 999px;
        background: var(--rule);
        overflow: hidden;
      }
      .prog .track i { display: block; height: 100%; background: var(--accent); }
      .cell.done .prog { color: var(--new); }
      .cell.done .prog .track i { background: var(--new); }

      /* Controls live outside a.card for the same reason .vers does: a button
         inside an anchor is a tap the anchor eats. Revealed together by the
         header's 編集 toggle rather than per row, because correcting progress
         is a thing you sit down to do, not something to trip over mid-scroll. */
      .manage {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.55rem 0 0;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.75rem;
      }
      .manage[hidden] { display: none; }
      .manage .mspacer { flex: 1; }
      .manage .step { display: inline-flex; align-items: center; gap: 0.3rem; }
      .manage output {
        min-width: 3.6rem;
        text-align: center;
        color: var(--muted);
        font-variant-numeric: tabular-nums;
      }
      /* Always visible, unlike .manage: a rating is something you give on the
         way out of a story, not a correction you sit down to make. Outside
         a.card for the same reason .manage is — a button inside an anchor is a
         tap the anchor eats. */
      .rate {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.55rem 0 0;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.75rem;
      }
      .rate .mspacer { flex: 1; }
      .stars { display: inline-flex; align-items: center; }
      /* No pill: five bordered buttons in a row read as a toolbar rather than
         as one control. The 44px target is still there, in the hit area. */
      .stars button {
        font: inherit;
        font-size: 1.05rem;
        line-height: 1;
        background: transparent;
        border: 0;
        padding: 0 0.1rem;
        min-width: 32px;
        min-height: 44px;
        color: var(--rule);
        cursor: pointer;
      }
      .stars button[aria-pressed="true"] { color: var(--accent); }
      .stars button:hover { color: color-mix(in srgb, var(--accent) 55%, var(--rule)); }
      .note {
        font: 0.8rem/1.6 -apple-system, system-ui, sans-serif;
        width: 100%;
        margin: 0.45rem 0 0;
        color: var(--ink);
        background: transparent;
        border: 1px solid var(--rule);
        border-radius: 8px;
        padding: 0.5rem 0.6rem;
        resize: vertical;
      }
      .note[hidden] { display: none; }
      .note:focus { outline: none; border-color: var(--accent); }

      .btn, .manage button, .rate .notebtn, .sync button {
        font: inherit;
        white-space: nowrap;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.75rem;
        color: var(--ink);
        background: transparent;
        border: 1px solid var(--rule);
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
        /* 44px of touch target without 44px of ink: the visual pill stays small
           while the hit area clears Apple's minimum on a phone. */
        min-height: 44px;
        cursor: pointer;
      }
      .manage .step button { min-width: 44px; }
      .btn:hover, .manage button:hover, .rate .notebtn:hover, .sync button:hover {
        border-color: var(--accent);
        color: var(--accent);
      }
      .btn[aria-pressed="true"] { background: var(--rule); }
      /* After the base button rule, not before it: same specificity, so the
         later selector is the one that decides the colour. */
      .rate .notebtn.has { color: var(--accent); border-color: var(--accent); }
      .cell.done .manage [data-act="done"] { color: var(--new); border-color: var(--new); }

      .sync {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.78rem;
        color: var(--muted);
        margin-top: 2.2rem;
        padding-top: 1.3rem;
        border-top: 1px solid var(--rule);
      }
      .sync summary { cursor: pointer; color: var(--accent); }
      .sync a { color: var(--accent); }
      .sync a[hidden] { display: none; }
      .sync .sbody { margin-top: 0.9rem; display: grid; gap: 0.7rem; }
      .sync .srow { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
      .sync input[type="password"] {
        font: inherit;
        flex: 1;
        min-width: 14rem;
        min-height: 44px;
        padding: 0 0.6rem;
        color: var(--ink);
        background: transparent;
        border: 1px solid var(--rule);
        border-radius: 8px;
      }
      .sync textarea {
        font: 0.72rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
        width: 100%;
        color: var(--ink);
        background: transparent;
        border: 1px solid var(--rule);
        border-radius: 8px;
        padding: 0.6rem;
        resize: vertical;
      }
      .sync textarea[hidden] { display: none; }
      .sync .sstat { margin: 0; }
      .sync .sstat.bad { color: var(--weak); }
      .sync .sstat.good { color: var(--new); }
      .sync p { margin: 0; line-height: 1.65; }

      .keys {
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.78rem;
        line-height: 1.7;
        color: var(--muted);
        margin: 2.2rem 0 0;
        padding-top: 1.3rem;
        border-top: 1px solid var(--rule);
      }
      .keys kbd {
        font: inherit;
        border: 1px solid var(--rule);
        border-radius: 4px;
        padding: 0.05rem 0.35rem;
        color: var(--ink);
      }
    </style>
  </head>
  <body>
    <header>
      <h1>物語</h1>
      <span class="spacer"></span>
      <span id="totals">__TOTALS__<span id="readtot"></span></span>
      <button class="btn" id="edit" type="button" aria-pressed="false">編集</button>
    </header>

    <main>
      <p class="lede">
        Written entirely inside the known-word set, so nothing here needs a dictionary.
        The order is graded by what the prose asks of you, not by vocabulary. Read down the list.
      </p>

      <a class="resume" id="resume" href="#" hidden>
        <span class="rlabel"></span>
        <span class="rtitle"></span>
        <span class="rpct"></span>
      </a>

__CARDS__
      <p class="keys">
        In a story: tap a kanji word for its reading, in place. Tap it twice for its
        English meaning, in a sheet at the foot of the page.
        Tap between words — the kana and the punctuation — for the whole sentence's
        readings, and twice for the sentence in English.
        <kbd>f</kbd> reveals every reading at once.
        Swipe to turn the page, or <kbd>←</kbd> <kbd>→</kbd>;
        <kbd>設</kbd> holds writing mode, 改行, 綴じ, type size, theme and ふりがな;
        <kbd>目次</kbd> comes back here.
        <br />
        Red 傍点 beside a word is a leech: known, but on a card that keeps failing.
        Teal circles with a visible reading is approved but not yet learned.
      </p>

      <details class="sync" id="sync">
        <summary>読書記録の同期</summary>
        <div class="sbody">
          <p>
            Progress is kept in this browser, and browsers throw that away — WebKit deletes
            all script-writable storage after seven days without a visit, and a Home Screen
            web app starts with an empty store of its own. Connecting a GitHub token keeps a
            copy in a secret gist instead, shared by every device that pastes the same token.
            The gist is a plain JSON file you can open and correct by hand, and its revision
            history is the undo.
          </p>
          <div class="srow">
            <input type="password" id="tok" placeholder="GitHub token (Gists: write)"
                   autocomplete="off" autocapitalize="off" spellcheck="false" />
            <button id="conn" type="button">接続</button>
            <button id="disc" type="button">解除</button>
          </div>
          <p class="sstat" id="sstat">—</p>
          <p><a id="glink" href="#" target="_blank" rel="noopener" hidden>gist を開く</a></p>
          <div class="srow">
            <button id="exp" type="button">書き出し</button>
            <button id="imp" type="button">読み込み</button>
            <span class="mspacer"></span>
            <button id="wipe" type="button">全消去</button>
          </div>
          <textarea id="box" rows="10" spellcheck="false" hidden
                    aria-label="読書記録の JSON"></textarea>
        </div>
      </details>
    </main>

    <footer>
      <span>__TITLES__</span>
      <span class="spacer"></span>
      <span>known-word-reader</span>
    </footer>
    <script src="sync.js"></script>
    <script>
      // Progress is written by the readers into this device's localStorage, so
      // it cannot be baked in here. Pages serves this page and every reader from
      // one origin, so the store they write is the store this reads. Everything
      // is wrapped because a mailed or file:// copy throws on the accessor
      // itself, and because this page must stay readable with no Sync at all.
      (function () {
        var S = window.Sync;
        var $ = function (id) { return document.getElementById(id); };
        var cells = [].slice.call(document.querySelectorAll(".cell[data-slug]"));
        // Date.now() is the clock; this is the order. Two edits inside one
        // millisecond carry the same `at`, the merge gives a tie to the remote,
        // and the second edit then loses to the copy of the first that its own
        // push has already put in the gist — a stepper tap that silently undoes
        // itself. Only this page edits fast enough to tie with itself, so the
        // monotonic stamp lives here rather than in the merge rule, which still
        // gives the remote a genuine tie so two devices converge.
        var last = 0;
        var now = function () {
          var t = Date.now();
          last = t > last ? t : last + 1;
          return last;
        };

        // A note long enough to be a document is a note that belongs in the
        // vault, not in a gist every reader on every device pulls on boot.
        var NOTE_MAX = 2000;

        var slot = function (key) {
          try { return JSON.parse(localStorage.getItem("japanese-stories:" + key)) || {}; }
          catch (e) { return {}; }
        };

        var read = function () { return S ? S.local() : slot("progress"); };
        var readR = function () { return S ? S.reviews() : slot("reviews"); };

        var put = function (key, map) {
          if (S) { if (key === "progress") S.saveLocal(map); else S.saveReviews(map); return; }
          try { localStorage.setItem("japanese-stories:" + key, JSON.stringify(map)); } catch (e) {}
        };

        // One push, debounced or not, and it repaints both halves. Typing in a
        // note must not fire a pull-merge-push per keystroke, and a star must
        // not wait a second and a half to leave the device.
        var flush = null;
        var pushNow = function () {
          if (flush) { clearTimeout(flush); flush = null; }
          if (!S) return;
          S.push().then(function (r) { paint(r.map); paintR(r.reviews); });
        };
        var pushSoon = function () {
          if (!S) return;
          if (flush) clearTimeout(flush);
          flush = setTimeout(pushNow, 1500);
        };

        // Every mutation goes through one of these, so the push and the repaint
        // cannot be forgotten at one call site and not another.
        var save = function (map) { put("progress", map); paint(map); pushNow(); };
        var saveR = function (map, soon) {
          put("reviews", map);
          paintR(map);
          if (soon) pushSoon(); else pushNow();
        };

        var total = function (cell) { return Number(cell.dataset.pages) || 1; };

        function paint(all) {
          if (!all || typeof all !== "object") all = {};
          var done = 0;
          // The row the 続き block will point at: whichever unfinished story was
          // touched last, falling back to the first one not yet finished.
          var open = null, openAt = -1, openPage = 0, next = null;
          for (var i = 0; i < cells.length; i++) {
            var cell = cells[i], rec = all[cell.dataset.slug];
            var prog = cell.querySelector(".prog");
            var out = cell.querySelector('[data-out="page"]');
            var mark = cell.querySelector('[data-act="done"]');
            // Anything that is not a record is skipped rather than trusted: a
            // version field added at the top level later would read as a slug.
            var ok = rec && typeof rec === "object" && !Array.isArray(rec);
            var n = total(cell);
            // rec.of is ignored — it is only what the device believed the last
            // time it read this story.
            var page = ok ? Number(rec.page) : NaN;
            if (!isFinite(page) || page < 1) page = NaN;
            else if (page > n) page = n;
            // Whether the story is finished is the reader's verdict, read back,
            // never re-derived here. Reaching the last authored page is not the
            // same thing: that page is usually split across screens on a phone,
            // and `page >= total` painted 読了 with a screen still to go.
            var fin = ok && rec.done === true;
            if (isFinite(page) || fin) {
              // Floored, because page 1 of 41 rounds to under a pixel and an
              // empty bar reads as "not started".
              var pct = fin ? 100 : Math.max(4, Math.round((page / n) * 100));
              prog.querySelector("i").style.width = pct + "%";
              prog.querySelector(".pct").textContent =
                fin ? "読了" : page + " / " + n;
              prog.hidden = false;
            } else {
              prog.hidden = true;
            }
            cell.classList.toggle("done", !!fin);
            if (fin) done++;
            else {
              if (!next) next = cell;
              var at = ok ? Number(rec.at) : NaN;
              if (isFinite(page) && isFinite(at) && at > openAt) {
                open = cell; openAt = at; openPage = page;
              }
            }
            if (out) out.textContent = isFinite(page) ? page + " / " + n : "—";
            if (mark) mark.textContent = fin ? "未読" : "読了";
          }
          $("readtot").textContent = done ? " · 読了 " + done + "/" + cells.length : "";
          resume(open, openPage, next);
          autoOpen(all, null);
        }

        // 続き on the story already in hand, 次へ on the first one not yet
        // finished — first in reading order, not first after the last one
        // finished, so skipping ahead leaves the skipped story offered.
        // Gone entirely once the corpus is read out.
        function resume(open, page, next) {
          var el = $("resume");
          if (!el) return;
          var cell = open || next;
          if (!cell) { el.hidden = true; return; }
          var a = cell.querySelector("a.card");
          el.setAttribute("href", a ? a.getAttribute("href") : "#");
          el.querySelector(".rlabel").textContent = open ? "続き" : "次へ";
          el.querySelector(".rtitle").textContent = cell.dataset.title || "";
          el.querySelector(".rpct").textContent =
            open ? page + " / " + total(cell) : total(cell) + " ページ";
          el.hidden = false;
        }

        // A story you have finished and not yet rated opens itself, so the
        // stars are still in front of you on the way out — which is the whole
        // reason they do not sit behind 編集. A row the reader has opened or
        // closed by hand is left alone; a preference beats a default.
        // Both callers already hold the map they painted from, and a push or a
        // pull paints from the merged result rather than from the store — so
        // going back to localStorage here can disagree with what is on screen.
        // A write that silently failed on quota is enough to produce it.
        function autoOpen(prog, revs) {
          prog = prog || read();
          revs = revs || readR();
          for (var i = 0; i < cells.length; i++) {
            var cell = cells[i];
            if (shut[cell.dataset.slug] || cell.classList.contains("open")) continue;
            var p = prog[cell.dataset.slug], r = revs[cell.dataset.slug];
            var fin = p && typeof p === "object" && p.done === true;
            var rated = r && typeof r === "object" && Number(r.stars) >= 1;
            if (fin && !rated) disclose(cell, true);
          }
        }

        function disclose(cell, on) {
          cell.classList.toggle("open", on);
          var btn = cell.querySelector(".disc");
          if (btn) btn.setAttribute("aria-expanded", on ? "true" : "false");
        }

        // Which rows have been shut by hand, so the auto-open does not undo the
        // correction on the next load. A Home Screen install relaunches on
        // every visit, so an in-memory flag would mean it never held at all.
        // Device-local and out of the gist deliberately: this is where this
        // screen is scrolled to, not anything about the reading.
        var shut = slot("shut");
        function remember(slug, on) {
          if (on) delete shut[slug]; else shut[slug] = 1;
          try {
            localStorage.setItem("japanese-stories:shut", JSON.stringify(shut));
          } catch (e) {}
        }

        function paintR(all) {
          if (!all || typeof all !== "object") all = {};
          for (var i = 0; i < cells.length; i++) {
            var cell = cells[i], rec = all[cell.dataset.slug];
            var ok = rec && typeof rec === "object" && !Array.isArray(rec);
            var stars = ok ? Math.round(Number(rec.stars)) : NaN;
            if (!isFinite(stars) || stars < 1) stars = 0;
            else if (stars > 5) stars = 5;
            var buttons = cell.querySelectorAll('[data-act="star"]');
            for (var j = 0; j < buttons.length; j++) {
              buttons[j].setAttribute(
                "aria-pressed", Number(buttons[j].dataset.n) <= stars ? "true" : "false");
            }
            var note = ok && typeof rec.note === "string" ? rec.note : "";
            var ta = cell.querySelector("textarea.note");
            // A pull landing mid-sentence must not take the sentence away, so a
            // focused box is left exactly as it is. The blur repaints it, which
            // is what stops a note merged in while it sat focused-and-empty
            // from being overwritten by the next keystroke.
            if (ta && ta !== document.activeElement && ta.value !== note) ta.value = note;
            var btn = cell.querySelector(".notebtn");
            if (btn) btn.classList.toggle("has", !!note);
          }
          autoOpen(null, all);
        }

        // A hand-set review carries `at` for the same reason a hand-set record
        // does: it is what outranks a stale device on the merge.
        function review(slug, fn, soon) {
          var all = readR();
          var rec = all[slug] && typeof all[slug] === "object" && !Array.isArray(all[slug])
            ? all[slug] : {};
          var next = fn(Object.assign({}, rec));
          if (typeof next.note === "string" && next.note.length > NOTE_MAX) {
            next.note = next.note.slice(0, NOTE_MAX);
          }
          next.at = now();
          all[slug] = next;
          saveR(all, soon);
        }

        function star(cell, n) {
          if (!(n >= 1 && n <= 5)) return;
          var slug = cell.dataset.slug;
          var rec = readR()[slug];
          var cur = rec && typeof rec === "object" ? Number(rec.stars) : 0;
          // Tapping the star that is already lit takes the rating back off.
          // Nothing else can undo a mis-tap, and a star nobody meant is a
          // verdict the generator would read as real.
          review(slug, function (r) { r.stars = cur === n ? 0 : n; return r; }, false);
        }

        // A hand-set record carries `at` so it outranks a stale device on the
        // merge, and `doneAt` whenever it touches 読了 — that stamp is the only
        // thing that can take a 読了 away, since reading alone only ever ORs it
        // on. Fields the reader owns (`sub`, `of`) are left where they are.
        function edit(slug, fn) {
          var all = read();
          var rec = all[slug] && typeof all[slug] === "object" ? all[slug] : {};
          var next = fn(Object.assign({}, rec));
          next.at = now();
          all[slug] = next;
          save(all);
        }

        function act(cell, what) {
          var slug = cell.dataset.slug, n = total(cell);
          if (what === "clear") {
            // Position only. Losing your place in a story is not withdrawing
            // what you thought of it; the lit star is its own undo.
            // A tombstone, not a deletion. An absent slug merges to whatever the
            // gist still holds, so deleting the key would undo itself on the very
            // next pull. A dated record with no page is what actually travels,
            // and it paints as unread because paint() keys the bar on `page`.
            edit(slug, function () {
              return { sub: 0, of: n, done: false, doneAt: now() };
            });
            return;
          }
          if (what === "done") {
            edit(slug, function (r) {
              var fin = r.done !== true;
              r.done = fin;
              r.doneAt = now();
              // Marking 読了 by hand means the story is behind you, so the
              // position goes with it rather than being left mid-book.
              if (fin) { r.page = n; r.sub = 0; }
              else if (!isFinite(Number(r.page))) { r.page = 1; r.sub = 0; }
              r.of = n;
              return r;
            });
            return;
          }
          var d = what === "inc" ? 1 : -1;
          edit(slug, function (r) {
            var p = Number(r.page);
            if (!isFinite(p)) p = d > 0 ? 1 : n;
            else p = Math.min(n, Math.max(1, p + d));
            r.page = p;
            // The screen index within a page cannot survive a page change, and
            // the reader clamps it against a split this page cannot know.
            r.sub = 0;
            r.of = n;
            return r;
          });
        }

        // One delegated listener rather than a handler per row, so adding a
        // story adds no wiring.
        var main = document.querySelector("main");

        main.addEventListener("click", function (e) {
          var btn = e.target.closest ? e.target.closest("button[data-act]") : null;
          if (!btn) return;
          var cell = btn.closest(".cell[data-slug]");
          if (!cell) return;
          var what = btn.dataset.act;
          // Ahead of act(): an unrecognised action falls through to its
          // stepper branch, so a disclosure tap would turn a page.
          if (what === "more") {
            var on = !cell.classList.contains("open");
            disclose(cell, on);
            remember(cell.dataset.slug, on);
            return;
          }
          if (what === "star") { star(cell, Number(btn.dataset.n)); return; }
          if (what === "note") {
            var ta = cell.querySelector("textarea.note");
            if (!ta) return;
            var show = ta.hidden;
            // A collapsed row puts the box in a display:none subtree, where it
            // cannot take focus and so is not skipped by paintR's focused-box
            // guard — the next pull would overwrite what was being typed.
            // Revealing the box opens the row that holds it.
            if (show) disclose(cell, true);
            ta.hidden = !show;
            btn.setAttribute("aria-expanded", show ? "true" : "false");
            if (show) ta.focus();
            return;
          }
          act(cell, what);
        });

        // Typed straight into localStorage and pushed on a debounce: the local
        // write is what makes a lost push harmless, since the page pushes again
        // on its next load anyway.
        main.addEventListener("input", function (e) {
          var ta = e.target.closest ? e.target.closest("textarea.note") : null;
          if (!ta) return;
          var cell = ta.closest(".cell[data-slug]");
          if (cell) review(cell.dataset.slug, function (r) { r.note = ta.value; return r; }, true);
        });

        main.addEventListener("focusout", function (e) {
          if (!e.target.closest || !e.target.closest("textarea.note")) return;
          if (flush) pushNow();
          paintR(readR());
        });

        // The tab away, the app switch and the Home Screen swipe all land here,
        // and only this one is reliable on iOS.
        window.addEventListener("pagehide", function () { if (flush) pushNow(); });

        $("edit").addEventListener("click", function () {
          var on = $("edit").getAttribute("aria-pressed") !== "true";
          $("edit").setAttribute("aria-pressed", on ? "true" : "false");
          for (var i = 0; i < cells.length; i++) {
            var row = cells[i].querySelector(".manage");
            if (row) row.hidden = !on;
          }
        });

        paint(read());
        paintR(readR());

        // ------------------------------------------------------------ sync --
        if (!S) return;

        var stat = $("sstat"), box = $("box");
        var WORDS = { idle: "未接続", busy: "同期中…", ok: "同期済み",
                      error: "同期できません", rejected: "トークンが拒否されました",
                      off: "同期は無効です" };

        function showStatus(s) {
          var text = s.message || WORDS[s.state] || s.state;
          if (s.state === "ok" && s.at) {
            text += " · " + new Date(s.at).toLocaleTimeString();
          }
          if (s.state === "idle" && !s.connected) text = WORDS.idle;
          stat.textContent = text;
          stat.className = "sstat" + (s.state === "ok" ? " good"
            : s.state === "error" || s.state === "rejected" ? " bad" : "");
          $("conn").textContent = s.connected ? "再接続" : "接続";
          $("disc").hidden = !s.connected;
          // The store, openable. gist.github.com/<id> resolves without the owner
          // in the path, so no username has to be stored to build this.
          var link = $("glink");
          link.hidden = !s.gist;
          if (s.gist) link.href = "https://gist.github.com/" + s.gist;
        }

        S.onChange(showStatus);
        showStatus(S.status());

        $("conn").addEventListener("click", function () {
          var t = $("tok").value;
          if (!t) { $("tok").focus(); return; }
          S.connect(t).then(function (r) {
            // The token is in localStorage now; leaving it in a form field as
            // well only widens where it can be read off a shoulder.
            $("tok").value = "";
            paint((r && r.map) || read());
            paintR((r && r.reviews) || readR());
          }, function () { $("tok").value = ""; });
        });

        $("disc").addEventListener("click", function () { S.forget(); });

        $("exp").addEventListener("click", function () {
          box.hidden = false;
          // The envelope the gist holds, so an export and the store read the
          // same. A bare progress map still imports, for anything exported
          // before reviews existed.
          box.value = JSON.stringify({ v: 1, progress: read(), reviews: readR() }, null, 2);
          box.focus();
          box.select();
          if (navigator.clipboard) navigator.clipboard.writeText(box.value).catch(function () {});
        });

        // Import merges by the same rule the gist does, so pasting an older
        // export cannot pull a story backwards. Replacing outright is what the
        // per-row controls and 全消去 are for.
        $("imp").addEventListener("click", function () {
          if (box.hidden) { box.hidden = false; box.value = ""; box.focus(); return; }
          var incoming;
          try { incoming = JSON.parse(box.value); } catch (e) {
            stat.textContent = "JSON が読めません";
            stat.className = "sstat bad";
            return;
          }
          if (!S.plain(incoming)) {
            stat.textContent = "JSON がオブジェクトではありません";
            stat.className = "sstat bad";
            return;
          }
          var enveloped = S.plain(incoming.progress) || S.plain(incoming.reviews);
          var prog = enveloped
            ? (S.plain(incoming.progress) ? incoming.progress : {})
            : incoming;
          var revs = enveloped && S.plain(incoming.reviews) ? incoming.reviews : {};
          // Written together and pushed once: two saves would each pull, merge
          // and PATCH, and the first PATCH would be a revision saying half of
          // what the paste meant.
          var mergedP = S.merge(read(), prog);
          var mergedR = S.mergeReviews(readR(), revs);
          put("progress", mergedP);
          put("reviews", mergedR);
          paint(mergedP);
          paintR(mergedR);
          pushNow();
          box.hidden = true;
        });

        $("wipe").addEventListener("click", function () {
          // No confirm(): a modal dialog blocks the extension driving this page
          // in the harness, and the gist's revision history is the real undo.
          // Two deliberate taps behind a closed <details> is the guard.
          if ($("wipe").dataset.armed !== "1") {
            $("wipe").dataset.armed = "1";
            $("wipe").textContent = "本当に全消去";
            setTimeout(function () {
              $("wipe").dataset.armed = "";
              $("wipe").textContent = "全消去";
            }, 4000);
            return;
          }
          $("wipe").dataset.armed = "";
          $("wipe").textContent = "全消去";
          // Tombstones rather than an empty map: an empty map merges to whatever
          // the gist still holds and the wipe would undo itself on the next
          // pull. A dated, page-less record is what actually travels.
          var all = read(), out = {};
          for (var k in all) {
            if (Object.prototype.hasOwnProperty.call(all, k)) {
              out[k] = { sub: 0, done: false, doneAt: now(), at: now() };
            }
          }
          var allR = readR(), outR = {};
          for (var j in allR) {
            if (Object.prototype.hasOwnProperty.call(allR, j)) {
              outR[j] = { stars: 0, note: "", at: now() };
            }
          }
          put("progress", out);
          put("reviews", outR);
          paint(out);
          paintR(outR);
          pushNow();
        });

        // Asking is free where it is honoured and a no-op where it is not.
        if (navigator.storage && navigator.storage.persist) {
          navigator.storage.persist().catch(function () {});
        }

        S.push().then(function (r) { paint(r.map); paintR(r.reviews); });
      })();
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    main()
