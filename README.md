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
| Tap the top or bottom edge | show the bars; tap it again to put them away         |
| `設`                       | writing mode, 改行, 綴じ, type size, theme, ふりがな |
| `目次`                     | back to the contents page                            |

Kana, particles and punctuation are not wrapped as words, so "between words" is about half of every line and easy to hit with a thumb. Which is also why the bars have their own gesture: every tap on the text now means something, so the strip the bars occupy is what is left to summon them with. It is a toggle rather than a summons, because it is the only gesture that can be — there is nowhere else to tap that does not already belong to a word or a sentence.

On a mouse, hovering a word reveals its reading and a double click opens the sheet. `Tab` reaches every kanji word and every translated sentence, and `Enter` opens the sheet directly — a sentence with no translation is not a tab stop, because there would be nothing to open.

The reading and the meaning stay one gesture apart on purpose: a story built from words you already know should not put the English in reach of the same tap that asks how a kanji is pronounced. That separation used to be three buttons in the bar — ふ, 訳, 意 — which meant the page did nothing at all until one of them was armed. Moving it into the gesture is what let them go.

Two kinds of word are marked, with 傍点 — the sesame dots Japanese prose uses to draw attention to a word. **Red sesame** is a leech: a known word on a card that keeps being failed, with its reading hidden. **Teal circles with the reading shown** is a new word, approved for this story but not yet learned.

Preferences and your place in each story are remembered per device.

## The contents page

One row per story in reading order, with its level, and the whole thing is generated — `index.py` takes the order, the level and the archived versions from `corpus.json`, the blurb from `stories-index.md`, and the pages, sentences, 漢字語 counts and marked words back out of each built reader. Nothing about a story is stated twice, so a rebuilt story cannot leave the page stale. A story with no blurb still gets a row, without its kana reading either since both come from the same bullet; `index.py` warns rather than stopping a rebuild that has already spent a minute per story in Ichiran. Nothing else checks, so the warning is the only notice.

The row shows what you need to **pick** a story: the title, its reading, its level, the blurb and how far in you are. 詳細 opens what you need to **finish** with one — the counts, the 苦手 and 新出 words, the stars, the 感想 box and the links to earlier drafts. At seven stories that is tidiness; the list is what it is protecting at fifty.

続き at the top is the story already in hand, whichever was read most recently, or 次へ on the first one not yet finished. It is built from the progress record at paint time, so it is simply absent on a device that has never read anything, and gone once the set is read out.

## Keeping your place

Progress is written to `localStorage` as you read, and that is the working copy. Browsers throw it away, though: WebKit deletes all script-writable storage after seven days of browser use without a visit, and a Home Screen web app starts with a storage container of its own rather than the Safari tab's. Two things address that, and they are meant to be done in this order.

**Connect a gist.** 読書記録の同期 on the contents page takes a GitHub token — fine-grained, **Gists: write**, nothing else — and keeps a copy of your progress in a secret gist. Every device that pastes the same token finds the same gist by filename and shares it; you never carry a gist id around. Per slug the later timestamp wins, so two devices converge without a lock, and a push that would write what is already there is skipped, which keeps the gist's revision list usable as an undo history rather than a log of page turns.

The store is a plain JSON file on github.com, so correcting a bad record is something you can do by hand in the gist editor, with its revision history behind you. `?nosync` disables the whole thing for a load, the way `?nostore` does for `localStorage`.

**Then add it to the Home Screen.** That is what stops the seven-day eviction, because a standalone web app gets its own counter of days of use. Do it after connecting, not before: the install begins with an empty store, so it will read as zero progress until you paste the token into it and let it pull.

編集 on the contents page opens per-story controls — mark 読了 or 未読, move the resume page, clear one story — alongside 書き出し / 読み込み for the whole record as JSON. Import merges by the same rule the gist does, so pasting an older export cannot pull a story backwards. Clearing writes a dated empty record rather than deleting the key, because a deletion merges back to whatever the gist still holds and would undo itself on the next pull. 消去 clears the place, not the rating.

## Rating a story

Every row on the contents page carries five stars and a 感想 box, and a story you have finished without rating opens itself so the stars are in front of you — the rating is given on the way out of a story, not sat down to. The note stays behind its own button, because a star is the ask and a written note is the extra. Tapping a star sets the rating; tapping the star that is already lit takes it back off, which is the only undo there is. The note is free text, capped at 2000 characters, saved as you type and pushed on a short debounce.

Ratings travel in the same secret gist as progress, in a `reviews` map beside `progress` rather than as fields on the progress record. That separation is the whole point: a progress record is replaced whole by whichever side carries the later timestamp, and every page turn bumps that timestamp, so a rating stored there would be erased the next time another device turned a page in the same story.

```bash
python3 reviews.py                  # the ratings and notes, joined to corpus.json
python3 reviews.py --file exp.json  # from a 書き出し export instead, no network
```

A row you open or close by hand stays that way, across reloads — the auto-open is a default, and a default that reasserts itself is not one. That one flag is kept in `localStorage` and deliberately not in the gist: it is where this screen is scrolled to, not anything about the reading.

`reviews.py` is the reading end, and it is what a new story's brief is chosen against: it prints each rating beside the level, register and length it was a verdict on, then the averages by level and by register, with their counts, and every note in full. A rating is one number and the note underneath it is where the reason lives. It reads the gist through `gh`, which already holds a token with the gist scope, so nothing has to be kept in step with the phone.

### Snapshots, for when something is about to churn the store

The gist's revision history is the everyday undo, and hand-correcting one record in the gist editor is what a gist was chosen for. `progress.py` is for the other case — a known-good copy taken before a device test that is going to swipe every story to its last page.

```bash
python3 progress.py                    # save, to ~/Documents/Code/.japanese-stories-backups
python3 progress.py --restore <file>   # put that snapshot back
python3 progress.py --restore <file> -n   # print what it would write, change nothing
```

**A restore is not a paste,** and pasting the file into the gist editor restores nothing. Every record's `at` is bumped to the moment of the restore, because the later stamp takes the record and a device that read while the snapshot sat on disk holds newer stamps than the file does; without the bump the next device to sync merges its own records back over the restore. `doneAt` is bumped too, since it is the only thing that can take a 読了 away. And a slug the gist holds but the snapshot does not gets the same dated, page-less tombstone 消去 writes, because an absent key merges to whatever the other side still has.

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

`scripts/reference.json` is the odd one out: a manifest of public-domain 青空文庫 children's stories used as an external yardstick for sentence rhythm and subordination, because every other threshold in the project is calibrated from the project's own output. It is read by `reference.py` and by nothing else, and it gates nothing. See AUTHORING.md § The reference band is not a floor either.

A story source is plain text: a `# title` line, then alternating Japanese sentences and `>` English translations, with a blank line between pages. Furigana is authored inline as `｜漢字《かんじ》`. Everything else — level, brief, new-word budget, reading order — lives in `scripts/corpus.json`.

## Building

```bash
cd scripts
export ICHIRAN_URL=http://localhost:3005
python3 rebuild.py          # rebuild stale stories in reading order, then the index
```

`rebuild.py` is the entry point. It walks the reading order in `corpus.json` rather than globbing, and always runs `index.py` last — the contents page is generated from the built readers, so anything rebuilt after it would leave it stale.

A live story is three outputs with three different inputs, and only the first is expensive:

| Output                           | Stale against                                     | Needs Ichiran + Anki |
| -------------------------------- | ------------------------------------------------- | -------------------- |
| `data/<slug>.js`                 | the story `.txt`, the afterword, the `.py` engine | yes                  |
| `<slug>.html`                    | `reader.html`, `build.py`                         | no                   |
| `reader.css` / `.js` / `sync.js` | `reader.css`, `reader.js`, `sync.js`, `build.py`  | no                   |

So editing the reader's styling or behaviour now rewrites two files in about a second, and re-segments nothing.

`docs/versions/` is left out of all of this. An archived draft is self-contained and **frozen** — it keeps the engine it published with, because an archive that re-renders with today's code preserves the story and not the reading it shipped with. `--versions` rebuilds them anyway.

| Command                                  | What it does                                                          |
| ---------------------------------------- | --------------------------------------------------------------------- |
| `python3 stats.py --strict`              | level ladder, brief compliance, sentence rhythm, word recycling       |
| `python3 check.py ../stories/<slug>.txt` | every content token is known or decomposes into known pieces (slow)   |
| `python3 have.py 単語1 単語2`            | quick known / unknown / leech lookup                                  |
| `python3 brief.py`                       | resolve and print a story brief before drafting                       |
| `python3 reviews.py`                     | star ratings and notes, joined to level, register and length          |
| `python3 progress.py`                    | snapshot the progress gist; `--restore` puts one back                 |
| `python3 reference.py --compare`         | our structural numbers beside authentic 児童文学 — a band, not a gate |
| `python3 rebuild.py --all`               | force a full rebuild — use after cards mature in Anki                 |
| `python3 rebuild.py --versions`          | also rebuild the frozen archives in `docs/versions/`                  |

### Requirements

This repo **cannot build in CI**, by design. Three of its inputs are local to the machine that owns the vocabulary:

- **[Ichiran](https://github.com/tshatrov/ichiran)** for segmentation, reachable at `$ICHIRAN_URL`. Comma-separate the variable to give a fallback — Python's resolver misses mDNS, so an mDNS name wants a bare IP after it. Segmentation is the slow part; budget about a minute per story on a cold cache.
- **Anki**, running, with [AnkiConnect](https://ankiweb.net/shared/info/2055492159) on `localhost:8765` and [AnkiMorphs](https://github.com/mortii/anki-morphs). `vocab.py` reads the AnkiMorphs database read-only for lemmas past a 21-day interval, and queries AnkiConnect for the decks AnkiMorphs is configured not to index.
- **A JMdict cache** at `~/.cache/kanji-of-the-day/jmdict-eng.json`, which `pos.py` reduces to the conjugation classes it needs.

`scripts/pos-table.json` and `scripts/.deck-words-cache.json` are derived from those and are gitignored — run `python3 pos.py` and `python3 vocab.py --refresh` to regenerate them after cloning.

## Publishing

GitHub Pages serves the `docs/` directory from `main`. There is no workflow and no build step: `rebuild.py` writes the finished HTML, and pushing it publishes it.

`reader.css` and `reader.js` are served at stable URLs under Pages' own `max-age=600`, so a freshly pushed engine change can be up to ten minutes stale on a device that has the old one cached. Content-hashed filenames would close that window, at the cost of rewriting every story shell on every engine change — which is the expense this layout exists to remove. Ten minutes is the trade.
