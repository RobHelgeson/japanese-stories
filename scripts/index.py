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
      <div class="manage" hidden>
        <button type="button" data-act="done">読了</button>
        <span class="step">
          <button type="button" data-act="dec" aria-label="一つ前のページへ">−</button>
          <output data-out="page">—</output>
          <button type="button" data-act="inc" aria-label="一つ先のページへ">＋</button>
        </span>
        <span class="mspacer"></span>
        <button type="button" data-act="clear">消去</button>
      </div>
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

      /* Controls live outside a.card for the same reason .vers does: a button
         inside an anchor is a tap the anchor eats. Revealed together by the
         header's 編集 toggle rather than per row, because correcting progress
         is a thing you sit down to do, not something to trip over mid-scroll. */
      .manage {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.4rem 0 0 3.4rem;
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
      .btn, .manage button, .sync button {
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
      .btn:hover, .manage button:hover, .sync button:hover { border-color: var(--accent); color: var(--accent); }
      .btn[aria-pressed="true"] { background: var(--rule); }
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
      <span>時計の音 · 迷子の手紙 · 終電 · 煙突の煙 · 猫を探す探偵 · 城の鐘</span>
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
        var now = function () { return Date.now(); };

        var read = function () {
          if (S) return S.local();
          try { return JSON.parse(localStorage.getItem("japanese-stories:progress")) || {}; }
          catch (e) { return {}; }
        };

        // Every mutation goes through here, so the push and the repaint cannot
        // be forgotten at one call site and not another.
        var save = function (map) {
          if (S) { S.saveLocal(map); paint(map); S.push().then(function (r) { paint(r.map); }); return; }
          try { localStorage.setItem("japanese-stories:progress", JSON.stringify(map)); } catch (e) {}
          paint(map);
        };

        var total = function (cell) { return Number(cell.dataset.pages) || 1; };

        function paint(all) {
          if (!all || typeof all !== "object") all = {};
          var done = 0;
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
            if (out) out.textContent = isFinite(page) ? page + " / " + n : "—";
            if (mark) mark.textContent = fin ? "未読" : "読了";
          }
          $("readtot").textContent = done ? " · 読了 " + done + "/" + cells.length : "";
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
        document.querySelector("main").addEventListener("click", function (e) {
          var btn = e.target.closest ? e.target.closest(".manage button[data-act]") : null;
          if (!btn) return;
          var cell = btn.closest(".cell[data-slug]");
          if (cell) act(cell, btn.dataset.act);
        });

        $("edit").addEventListener("click", function () {
          var on = $("edit").getAttribute("aria-pressed") !== "true";
          $("edit").setAttribute("aria-pressed", on ? "true" : "false");
          for (var i = 0; i < cells.length; i++) {
            var row = cells[i].querySelector(".manage");
            if (row) row.hidden = !on;
          }
        });

        paint(read());

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
          }, function () { $("tok").value = ""; });
        });

        $("disc").addEventListener("click", function () { S.forget(); });

        $("exp").addEventListener("click", function () {
          box.hidden = false;
          box.value = JSON.stringify(read(), null, 2);
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
          save(S.merge(read(), incoming.progress && S.plain(incoming.progress)
            ? incoming.progress : incoming));
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
          save(out);
        });

        // Asking is free where it is honoured and a no-op where it is not.
        if (navigator.storage && navigator.storage.persist) {
          navigator.storage.persist().catch(function () {});
        }

        S.push().then(function (r) { paint(r.map); });
      })();
    </script>
  </body>
</html>
"""


if __name__ == "__main__":
    main()
