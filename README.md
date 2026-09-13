# 日本語 Known-Word Stories

Short Japanese stories written entirely inside a fixed known-word set, and a reader that shows furigana only when you ask for it.

**📖 Read them: <https://robhelgeson.github.io/japanese-stories/>**

The constraint is the whole idea. Every story is written against a vocabulary list derived from a real Anki collection, so a reader who has learned those words can read a whole story without a dictionary. Each story is allowed a small, declared budget of new words, and each of those has to be introduced in a sentence that frames its meaning before it is ever used plainly.

## The reader

A story is a small HTML shell beside a shared `reader.css` and `reader.js`, with its own annotated text in `data/<slug>.js`. Everything is local — classic `<link>` and `<script src>`, no network requests, no modules, no `fetch` — so a story still opens straight off the filesystem; it needs its siblings, so copy the folder rather than the one file.

Stories were self-contained single files until the site was published, which was the right shape for mailing one around and the wrong one to maintain: `reader.css` and `reader.js` were inlined into all eleven readers, so a one-line CSS change rewrote 2.5MB and had to re-segment every story through Ichiran to do it. `docs/versions/` is still built the old way — see [Publishing](#publishing).

Text is vertical by default, as Japanese literary prose is, and a page never scrolls: an authored page too big for the screen is split across screens that keep its page number.

|                          |                                                      |
| ------------------------ | ---------------------------------------------------- |
| Tap a kanji word         | its reading, in place, attached to the kanji         |
| Tap again                | put the reading away                                 |
| Double tap a kanji word  | its meaning, in a sheet at the foot of the page      |
| Tap between words        | the reading for the whole sentence                   |
| Double tap between words | that sentence in English                             |
| `f`                      | reveal every reading at once (also 設 → ふりがな)    |
| Swipe                    | turn the page (touch; on a mouse use the arrows)     |
| `←` `→`                  | turn pages, following the binding direction          |
| `設`                     | writing mode, 改行, 綴じ, type size, theme, ふりがな |
| `目次`                   | back to the contents page                            |

Kana, particles and punctuation are not wrapped as words, so "between words" is about half of every line and easy to hit with a thumb. On a mouse, hovering a word reveals its reading and a double click opens the sheet; `Tab` reaches every word and sentence, and `Enter` opens the sheet directly.

The reading and the meaning stay one gesture apart on purpose: a story built from words you already know should not put the English in reach of the same tap that asks how a kanji is pronounced. That separation used to be three buttons in the bar — ふ, 訳, 意 — which meant the page did nothing at all until one of them was armed. Moving it into the gesture is what let them go.

Two kinds of word are marked, with 傍点 — the sesame dots Japanese prose uses to draw attention to a word. **Red sesame** is a leech: a known word on a card that keeps being failed, with its reading hidden. **Teal circles with the reading shown** is a new word, approved for this story but not yet learned.

Preferences and your place in each story are remembered per device.

## Layout

```
scripts/          the engine — build, validate, segment, inflect
stories/          story sources (.txt) and stories-index.md (summaries + afterwords)
docs/             what GitHub Pages serves
  reader.css      one copy, shared by every live story
  reader.js       one copy
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
| `reader.css` / `.js` | `reader.css`, `reader.js`, `build.py`             | no                   |

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
