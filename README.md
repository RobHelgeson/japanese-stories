# 日本語 Known-Word Stories

Short Japanese stories written entirely inside a fixed known-word set, and a reader that shows furigana only when you ask for it.

**📖 Read them: <https://robhelgeson.github.io/japanese-stories/>**

The constraint is the whole idea. Every story is written against a vocabulary list derived from a real Anki collection, so a reader who has learned those words can read a whole story without a dictionary. Each story is allowed a small, declared budget of new words, and each of those has to be introduced in a sentence that frames its meaning before it is ever used plainly.

## The reader

Each story is a single self-contained HTML file — CSS, JavaScript, and the whole annotated text inlined, no network requests at all. That is deliberate: a story has to survive being opened from `file://`, mailed, or dropped onto a tablet, and a multi-file bundle does not.

|                    |                                |
| ------------------ | ------------------------------ |
| Hover a kanji word | its reading, in a gloss box    |
| Click a word       | pins the gloss                 |
| `ふりがな` / `f`   | reveal every reading           |
| `訳` / `t`         | show all English translations  |
| Click a sentence   | show just that one translation |
| `意味`             | inline meanings                |
| `←` `→`            | turn pages                     |

Two kinds of word are marked. A **dotted red underline** is a leech — a known word on a card that keeps being failed; its reading stays hidden. A **solid teal underline with the reading shown** is a new word, approved for this story but not yet learned.

## Layout

```
scripts/      the engine — build, validate, segment, inflect
stories/      story sources (.txt) and stories-index.md (summaries + afterwords)
docs/         the built readers; this is what GitHub Pages serves
AUTHORING.md  the craft spec a new story is written against
```

A story source is plain text: a `# title` line, then alternating Japanese sentences and `>` English translations, with a blank line between pages. Furigana is authored inline as `｜漢字《かんじ》`. Everything else — level, brief, new-word budget, reading order — lives in `scripts/corpus.json`.

## Building

```bash
cd scripts
export ICHIRAN_URL=http://localhost:3005
python3 rebuild.py          # rebuild stale stories in reading order, then the index
```

`rebuild.py` is the entry point. It walks the reading order in `corpus.json` rather than globbing, rebuilds only what is stale against every build input (including `reader.js`, `reader.css`, and the afterwords), covers the archived drafts in `versions/`, and always runs `index.py` last — the contents page is generated from the built readers, so anything rebuilt after it would leave it stale.

| Command                                  | What it does                                                        |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `python3 stats.py --strict`              | level ladder, brief compliance, sentence rhythm, word recycling     |
| `python3 check.py ../stories/<slug>.txt` | every content token is known or decomposes into known pieces (slow) |
| `python3 have.py 単語1 単語2`            | quick known / unknown / leech lookup                                |
| `python3 brief.py`                       | resolve and print a story brief before drafting                     |
| `python3 rebuild.py --all`               | force a full rebuild — use after cards mature in Anki               |

### Requirements

This repo **cannot build in CI**, by design. Three of its inputs are local to the machine that owns the vocabulary:

- **[Ichiran](https://github.com/tshatrov/ichiran)** for segmentation, reachable at `$ICHIRAN_URL`. Comma-separate the variable to give a fallback — Python's resolver misses mDNS, so an mDNS name wants a bare IP after it. Segmentation is the slow part; budget about a minute per story on a cold cache.
- **Anki**, running, with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) on `localhost:8765` and [AnkiMorphs](https://github.com/mortii/anki-morphs). `vocab.py` reads the AnkiMorphs database read-only for lemmas past a 21-day interval, and queries AnkiConnect for the decks AnkiMorphs is configured not to index.
- **A JMdict cache** at `~/.cache/kanji-of-the-day/jmdict-eng.json`, which `pos.py` reduces to the conjugation classes it needs.

`scripts/pos-table.json` and `scripts/.deck-words-cache.json` are derived from those and are gitignored — run `python3 pos.py` and `python3 vocab.py --refresh` to regenerate them after cloning.

## Publishing

GitHub Pages serves the `docs/` directory from `main`. There is no workflow and no build step: `rebuild.py` writes the finished HTML, and pushing it publishes it.
