# 日本語 Known-Word Stories

Short Japanese stories written entirely inside a fixed known-word set, and a reader that shows furigana only when you ask for it.

**📖 Read them: <https://robhelgeson.github.io/japanese-stories/>**

The constraint is the whole idea. Every story is written against a vocabulary list derived from a real Anki collection, so a reader who has learned those words can read a whole story without a dictionary. Each story is allowed a small, declared budget of new words, and each of those has to be introduced in a sentence that frames its meaning before it is ever used plainly.

## The reader

A story is a small HTML shell beside a shared `reader.css`, `reader.js` and `sync.js`, with its own annotated text in `data/<slug>.js`. Classic `<link>` and `<script src>`, no modules — so a story still opens straight off the filesystem; it needs its siblings, so copy the folder rather than the one file. The only network request the reader ever makes is the optional progress sync below, and without it nothing is fetched at all.

Stories were self-contained single files until the site was published, which was the right shape for mailing one around and the wrong one to maintain: `reader.css` and `reader.js` were inlined into all eleven readers, so a one-line CSS change rewrote 2.5MB and had to re-segment every story through Ichiran to do it. `docs/versions/` is still built the old way — see [Publishing](#publishing).

Text is vertical by default, as Japanese literary prose is, and a page never scrolls: an authored page too big for the screen is split across screens that keep its page number.

|                            |                                                      |
| -------------------------- | ---------------------------------------------------- |
| Tap a kanji word           | its reading, in place, attached to the kanji         |
| Tap again                  | put the reading away                                 |
| Double tap a kanji word    | its meaning, in a sheet at the foot of the page      |
| Tap between words          | the reading for the whole sentence                   |
| Double tap between words   | that sentence in English                             |
| `f`                        | reveal every reading at once (also 設 → ふりがな)    |
| Swipe                      | turn the page (touch; on a mouse use the arrows)     |
| `←` `→`                    | turn pages, following the binding direction          |
| Tap the top or bottom edge | bring the bars back after they fade                  |
| `設`                       | writing mode, 改行, 綴じ, type size, theme, ふりがな |
| `目次`                     | back to the contents page                            |

Kana, particles and punctuation are not wrapped as words, so "between words" is about half of every line and easy to hit with a thumb. Which is also why the bars have their own gesture: every tap on the text now means something, so the strip the bars occupy is what is left to summon them with.

On a mouse, hovering a word reveals its reading and a double click opens the sheet. `Tab` reaches every kanji word and every translated sentence, and `Enter` opens the sheet directly — a sentence with no translation is not a tab stop, because there would be nothing to open.

The reading and the meaning stay one gesture apart on purpose: a story built from words you already know should not put the English in reach of the same tap that asks how a kanji is pronounced. That separation used to be three buttons in the bar — ふ, 訳, 意 — which meant the page did nothing at all until one of them was armed. Moving it into the gesture is what let them go.

Two kinds of word are marked, with 傍点 — the sesame dots Japanese prose uses to draw attention to a word. **Red sesame** is a leech: a known word on a card that keeps being failed, with its reading hidden. **Teal circles with the reading shown** is a new word, approved for this story but not yet learned.

Preferences and your place in each story are remembered per device.

## Keeping your place

Progress is written to `localStorage` as you read, and that is the working copy. Browsers throw it away, though: WebKit deletes all script-writable storage after seven days of browser use without a visit, and a Home Screen web app starts with a storage container of its own rather than the Safari tab's. Two things address that, and they are meant to be done in this order.

**Connect a gist.** 読書記録の同期 on the contents page takes a GitHub token — fine-grained, **Gists: write**, nothing else — and keeps a copy of your progress in a secret gist. Every device that pastes the same token finds the same gist by filename and shares it; you never carry a gist id around. Per slug the later timestamp wins, so two devices converge without a lock, and a push that would write what is already there is skipped, which keeps the gist's revision list usable as an undo history rather than a log of page turns.

The store is a plain JSON file on github.com, so correcting a bad record is something you can do by hand in the gist editor, with its revision history behind you. `?nosync` disables the whole thing for a load, the way `?nostore` does for `localStorage`.

**Then add it to the Home Screen.** That is what stops the seven-day eviction, because a standalone web app gets its own counter of days of use. Do it after connecting, not before: the install begins with an empty store, so it will read as zero progress until you paste the token into it and let it pull.

編集 on the contents page opens per-story controls — mark 読了 or 未読, move the resume page, clear one story — alongside 書き出し / 読み込み for the whole record as JSON. Import merges by the same rule the gist does, so pasting an older export cannot pull a story backwards. Clearing writes a dated empty record rather than deleting the key, because a deletion merges back to whatever the gist still holds and would undo itself on the next pull.

## Layout

```
scripts/          the engine — build, validate, segment, inflect
stories/          story sources (.txt) and stories-index.md (summaries + afterwords)
docs/             what GitHub Pages serves
  reader.css      one copy, shared by every live story
  reader.js       one copy
  sync.js         one copy — progress sync, shared with the contents page
  manifest.webmanifest, icon-*.png     the Home Screen install
  data/<slug>.js  one story's annotated text
  <slug>.html     a ~5KB shell linking the three
  versions/       archived drafts, self-contained and frozen
AUTHORING.md      the craft spec a new story is written against
```

A story source is plain text: a `# title` line, then alternating Japanese sentences and `>` English translations, with a blank line between pages. Furigana is authored inline as `｜漢字《かんじ》`. Everything else — level, brief, new-word budget, reading order — lives in `scripts/corpus.json`.

## Building

```bash
cd scripts
export ICHIRAN_URL=http://localhost:3005
python3 rebuild.py          # rebuild stale stories in reading order, then the index
```

`rebuild.py` is the entry point. It walks the reading order in `corpus.json` rather than globbing, and always runs `index.py` last — the contents page is generated from the built readers, so anything rebuilt after it would leave it stale.

A live story is three outputs with three different inputs, and only the first is expensive:

| Output               | Stale against                                     | Needs Ichiran + Anki |
| -------------------- | ------------------------------------------------- | -------------------- |
| `data/<slug>.js`     | the story `.txt`, the afterword, the `.py` engine | yes                  |
| `<slug>.html`        | `reader.html`, `build.py`                         | no                   |
| `reader.css` / `.js` / `sync.js` | `reader.css`, `reader.js`, `sync.js`, `build.py` | no       |

So editing the reader's styling or behaviour now rewrites two files in about a second, and re-segments nothing.

`docs/versions/` is left out of all of this. An archived draft is self-contained and **frozen** — it keeps the engine it published with, because an archive that re-renders with today's code preserves the story and not the reading it shipped with. `--versions` rebuilds them anyway.

| Command                                  | What it does                                                        |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `python3 stats.py --strict`              | level ladder, brief compliance, sentence rhythm, word recycling     |
| `python3 check.py ../stories/<slug>.txt` | every content token is known or decomposes into known pieces (slow) |
| `python3 have.py 単語1 単語2`            | quick known / unknown / leech lookup                                |
| `python3 brief.py`                       | resolve and print a story brief before drafting                     |
| `python3 rebuild.py --all`               | force a full rebuild — use after cards mature in Anki               |
| `python3 rebuild.py --versions`          | also rebuild the frozen archives in `docs/versions/`                |

### Requirements

This repo **cannot build in CI**, by design. Three of its inputs are local to the machine that owns the vocabulary:

- **[Ichiran](https://github.com/tshatrov/ichiran)** for segmentation, reachable at `$ICHIRAN_URL`. Comma-separate the variable to give a fallback — Python's resolver misses mDNS, so an mDNS name wants a bare IP after it. Segmentation is the slow part; budget about a minute per story on a cold cache.
- **Anki**, running, with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) on `localhost:8765` and [AnkiMorphs](https://github.com/mortii/anki-morphs). `vocab.py` reads the AnkiMorphs database read-only for lemmas past a 21-day interval, and queries AnkiConnect for the decks AnkiMorphs is configured not to index.
- **A JMdict cache** at `~/.cache/kanji-of-the-day/jmdict-eng.json`, which `pos.py` reduces to the conjugation classes it needs.

`scripts/pos-table.json` and `scripts/.deck-words-cache.json` are derived from those and are gitignored — run `python3 pos.py` and `python3 vocab.py --refresh` to regenerate them after cloning.

## Publishing

GitHub Pages serves the `docs/` directory from `main`. There is no workflow and no build step: `rebuild.py` writes the finished HTML, and pushing it publishes it.

`reader.css` and `reader.js` are served at stable URLs under Pages' own `max-age=600`, so a freshly pushed engine change can be up to ten minutes stale on a device that has the old one cached. Content-hashed filenames would close that window, at the cost of rewriting every story shell on every engine change — which is the expense this layout exists to remove. Ten minutes is the trade.
