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


def card(story, summary, versions=()):
    href = html.escape(story["file"])
    title = html.escape(story["title"])
    reading, text = summary
    st = story["stats"]
    # One slug for the row's identity and its version hrefs, so they cannot disagree.
    slug = Path(story["file"]).stem
    chips = ""
    if st["weak"]:
        chips += f'<span class="chip weak">苦手 {html.escape("、".join(st["weak"]))}</span>'
    if st.get("approved"):
        chips += f'<span class="chip new">新出 {html.escape("、".join(st["approved"]))}</span>'
    return f"""    <div class="cell" data-slug="{html.escape(slug)}" data-pages="{story["pages"]}">
      <a class="card" href="{href}">
        <div class="rt">{html.escape(reading)}</div>
        <h2>{title}</h2>
        <p class="sum">{html.escape(text)}</p>
        <div class="meta">
          <span>{story["pages"]} ページ</span>
          <span>{story["sentences"]} 文</span>
          <span>{st["words"]} 漢字語</span>
        </div>
        <div class="chips">{chips}</div>
        <div class="prog" hidden><span class="track"><i></i></span><span class="pct"></span></div>
      </a>
{version_links(slug, versions)}    </div>
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
    missing = [s["title"] for s in built if s["title"] not in sums]
    if missing:
        sys.exit(f"No summary in stories-index.md for: {', '.join(missing)}")

    cards = "".join(
        card(s, sums[s["title"]], VERSIONS.get(Path(s["file"]).stem, [])) for s in built
    )
    known = built[0]["stats"]["knownVocab"]
    totals = (
        f'{len(built)} 編 · {sum(s["pages"] for s in built)} ページ · '
        f'{sum(s["sentences"] for s in built)} 文 · 既知語彙 {known}'
    )

    out = out_dir / "index.html"
    out.write_text(TEMPLATE.replace("__CARDS__", cards).replace("__TOTALS__", totals), encoding="utf-8")
    print(f"{out}\n  {len(built)} stories · {totals}")


TEMPLATE = """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>物語 — 目次</title>
    <style>
      :root {
        --paper: #faf7f0;
        --ink: #22201c;
        --muted: #8a8377;
        --rule: #e2dcd0;
        --accent: #7a5c2e;
        --weak: #b4562a;
        --new: #2f7d6a;
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --paper: #16151a;
          --ink: #e8e4dc;
          --muted: #8b8578;
          --rule: #2c2a31;
          --accent: #d3b075;
          --weak: #e0895e;
          --new: #6cc5ab;
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
      h1 { font-size: 1.1rem; margin: 0; color: var(--ink); font-weight: 600; }
      .spacer { flex: 1; }

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

      /* The version row sits outside the card's anchor — nesting a link inside
         a link is invalid and browsers silently close the outer one. */
      .cell { margin-bottom: 0.9rem; }
      .cell .card { margin-bottom: 0; }
      .cell .vers { margin: 0.4rem 0 0 3.4rem; }

      /* Reading order is the point of the list, so the cards are a single
         column and carry their position rather than being a grid to scan. */
      .card {
        display: block;
        position: relative;
        padding: 1.3rem 1.5rem 1.2rem 3.4rem;
        margin-bottom: 0.9rem;
        border: 1px solid var(--rule);
        border-radius: 10px;
        text-decoration: none;
        color: inherit;
        counter-increment: story;
        transition: border-color 0.12s ease, background 0.12s ease;
      }
      main { counter-reset: story; }
      .card::before {
        content: counter(story);
        position: absolute;
        left: 1.4rem;
        top: 1.45rem;
        font-family: -apple-system, system-ui, sans-serif;
        font-size: 0.8rem;
        font-variant-numeric: tabular-nums;
        color: var(--muted);
      }
      .card:hover {
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
      .chips { gap: 0.5rem; margin-top: 0.5rem; }
      /* Earlier drafts, so a rewrite can be read against what it replaced. */
      .vers {
        display: flex; align-items: center; gap: 0.4rem;
        margin-top: 0.65rem; font-size: 0.72rem; opacity: 0.7;
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
      <span>__TOTALS__<span id="readtot"></span></span>
    </header>

    <main>
      <p class="lede">
        Written entirely inside the known-word set, so nothing here needs a dictionary.
        The order is graded by what the prose asks of you, not by vocabulary. Read down the list.
      </p>

__CARDS__
      <p class="keys">
        In a story: hover a kanji word for its reading, click to pin it.
        <kbd>f</kbd> or <kbd>ふりがな</kbd> reveals every reading,
        <kbd>t</kbd> or <kbd>訳</kbd> every translation, and
        <kbd>意味</kbd> turns on meanings for the word under the cursor.
        Click a line away from a kanji word for just that one translation.
        <kbd>←</kbd> <kbd>→</kbd> turn pages; <kbd>目次</kbd> comes back here.
        <br />
        A dotted red underline is a leech word: known, but on a card that keeps failing.
        A solid teal underline with a visible reading is approved but not yet learned.
      </p>
    </main>

    <footer>
      <span>時計の音 · 迷子の手紙 · 終電 · 猫を探す探偵 · 城の鐘</span>
      <span class="spacer"></span>
      <span>known-word-reader</span>
    </footer>
    <script>
      // Progress is written by the readers into this device's localStorage, so
      // it cannot be baked in here. Pages serves this page and every reader from
      // one origin, so the store they write is the store this reads. Wrapped
      // because a mailed or file:// copy throws on the accessor itself.
      (function () {
        var raw;
        try { raw = localStorage.getItem("japanese-stories:progress"); } catch (e) { return; }
        if (!raw) return;
        var all; try { all = JSON.parse(raw); } catch (e) { return; }
        if (!all || typeof all !== "object") return;
        var cells = document.querySelectorAll(".cell[data-slug]"), read = 0;
        for (var i = 0; i < cells.length; i++) {
          var cell = cells[i], rec = all[cell.dataset.slug];
          // Anything that is not a record is skipped rather than trusted: a
          // version field added at the top level later would read as a slug.
          if (!rec || typeof rec !== "object" || Array.isArray(rec)) continue;
          var total = Number(cell.dataset.pages);
          // rec.of is ignored — it is only what the device believed the last
          // time it read this story.
          var page = Number(rec.page);
          if (!total || !isFinite(page) || page < 1) continue;
          if (page > total) page = total;
          var finished = rec.done === true || page >= total;
          var prog = cell.querySelector(".prog");
          // Floored, because page 1 of 41 rounds to under a pixel and an empty
          // bar reads as "not started".
          prog.querySelector("i").style.width =
            (finished ? 100 : Math.max(4, Math.round((page / total) * 100))) + "%";
          prog.querySelector(".pct").textContent = finished ? "読了" : page + " / " + total;
          prog.hidden = false;
          if (finished) { cell.classList.add("done"); read++; }
        }
        if (read) document.getElementById("readtot").textContent =
          " · 読了 " + read + "/" + cells.length;
      })();
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    main()
