# Authoring a story

Write a story the reader can read without a dictionary, at a declared difficulty level.

Everything below is enforced or measured by the scripts in `scripts/`. Run them; do not eyeball.

**Two gates, in order. Stop at each one.** Gate 1 settles what the story is briefed to be. Gate 2 settles whether it is a story at all, in English, before a single Japanese sentence is written. Only then draft.

## Before writing

```bash
cd scripts
export ICHIRAN_URL=http://localhost:3005
python3 have.py 単語1 単語2 ...      # ✓ known / ✗ not / ✓ (weak) leech. Batch 30-50.
python3 stats.py                      # every story against its declared level
python3 reviews.py                    # what the reader thought of the ones so far
```

Read `stories/tokei-no-oto.txt` first. It is the worked example and the only story written against this spec from the start.

Anki must be running (AnkiConnect on `:8765`) and Ichiran must be reachable at `$ICHIRAN_URL`. See README.md.

## The target reader

**N3, with a few scattered N2/N1 points.** Do not infer the level from a generated lesson set — that records which lessons have been generated, not what is readable. Conflating the two produced a ladder pitched at N1.

## Gate 1 — the brief

```bash
python3 brief.py [--level N] [--pages N] [--register R] [--new-words N]
                 [--leech-seeds N] [--repeats F] [--grammar-focus a,b]
                 [--dialogue PCT[,untagged]] [--topic "..."]
```

Print the table, **then stop and ask.** Do not draft until the brief is confirmed.

| Parameter       | Default                  | Checked by                                        |
| --------------- | ------------------------ | ------------------------------------------------- |
| `level`         | 3 — N3 voice             | `stats.py` level ladder                           |
| `pages`         | 25, ±10%                 | `stats.py` brief check                            |
| `topic`         | none — propose 2-3       | Gate 2                                            |
| `register`      | `quiet-realism`          | Gate 2                                            |
| `new_words`     | 1.0 per 100 tokens       | `stats.py` brief check                            |
| `repeats`       | ≥40% repeated-word share | `stats.py` target                                 |
| `leech_seeds`   | 1.5 per 100 tokens       | `stats.py` brief check                            |
| `grammar_focus` | none                     | `stats.py` brief check — all must be present      |
| `dialogue`      | unconstrained            | `stats.py` brief check — ±10, untagged means ≥90% |
| `mode`          | `new`                    | see Modes                                         |

Every parameter has a default, so a bare invocation is a complete brief. Defaults live in `corpus.json`'s `defaults` block, not here — a default nothing reads is a suggestion. `grammar_focus` names must be keys of `GRAMMAR_PATTERNS` in `stats.py`; `brief.py` rejects the rest.

With no topic given, propose two or three domains the corpus has not used. The six so far are watches, letters, trains, a bathhouse, a missing cat, and a cast bell.

**Run `reviews.py` before proposing anything.** It prints the star ratings and notes from the contents page against the level, register and length each was a verdict on. Read the notes rather than the averages: a note naming what dragged or what had to be re-read is a constraint on the next brief, while a mean over three ratings is a number looking for a pattern. Say which review you are responding to when a parameter departs from the default because of one — an unattributed change to `dialogue` or `register` is indistinguishable from a whim, and the brief is the only record either way. Nothing here is automatic: no parameter is derived from a rating, and a low-rated register is not retired on the strength of one story.

**Persist the brief.** Once it is confirmed, `python3 brief.py --json` emits the block for the story's `corpus.json` entry. Add it **by hand** — that file is hand-maintained and carries comment keys and one-line arrays that `json.dump` would reformat. Persisting it is the whole point: nothing recorded what a story was supposed to be, which is how ｜猫《ねこ》を｜探《さが》す｜探偵《たんてい》 ran 24% long and ｜城《しろ》の｜鐘《かね》 14% without either being noticed.

## Gate 2 — the story, in English

Before any Japanese exists, write and stop on:

```
PREMISE   two or three sentences
AFTERWORD full spoiler, in English — what the story is actually doing
BEATS     6-10, each joined to the next by だから or しかし
```

**Write the afterword first.** It used to be written last, as a patch for the removed theme statement. Inverted, it is the design document: if you cannot write the afterword before drafting, you do not have a story yet, you have a situation. It already has a canonical home — the `## Afterwords` section of `stories/stories-index.md` — so writing it first means writing it where it will live.

Record the premise and beats as `_premise` on the `corpus.json` entry, alongside the existing `_feature` and `_note` prose keys.

## Craft

The rules below are what to do. The prohibitions further down are what not to do. Both matter; only one of them used to be written here.

- **Causality, not sequence.** Between consecutive beats you must be able to put だから or しかし. If the only honest connective is そして or それから, it is a list of events and not yet a story. That is what the beat sheet is testing.
- **One turn, and the reader can point at it.** Something is different at the end than at the beginning, and there is a specific sentence where it changed. ｜城《しろ》の｜鐘《かね》 states its distinction exactly once, in dialogue, on page 11.
- **Plant and pay off.** ｜猫《ねこ》を｜探《さが》す｜探偵《たんてい》 plants the boxes clue on page 7 and does not recall it until page 20.
- **Concrete before abstract.** An abstract noun has to be earned by a physical detail that came first. This serves the vocabulary constraint too: concrete nouns are what the known set is richest in.
- **Withhold, never confuse.** The reader sees one sentence at a time and the inference chains run thirty-plus sentences. Information must stay retrievable — plant it concretely, and never ask the reader to hold an ambiguity across pages.

### The English has to stand alone

Read only the `>` lines, top to bottom, ignoring the Japanese. **It must be a short story worth reading.** Not a gloss track, not a sequence of captions. This is half of what actually gets read, and it is the cheapest strong check available.

### Register

`quiet-realism` is the default and describes the current six: one concrete object at the centre, close narration, ends on an image rather than a claim. That was a house style that fell out of the recycling requirement rather than a decision, so it is now a declared choice — `folktale` and `procedural` already exist in the corpus as undeclared one-offs. Register changes voice and structure. It never relaxes the narrow-domain rule, because the object at the centre is the recycling engine.

## The level ladder

Levels live in `scripts/corpus.json`. A level is a **rung, not a checklist**: `min_present` is how many of its constructions the story must actually use, and it must also carry ≥60% of every lower level's constructions. Level 5 is deliberately sparse — a handful of marked N2 forms inside otherwise-N3 prose, never a wall.

Declare the story's level in `corpus.json` and let `stats.py --strict` tell you whether you hit it.

## The budgets

Rates, not counts, computed from the story's own token count by `stats.py`:

| Budget                           | Rate                                        |
| -------------------------------- | ------------------------------------------- |
| New words                        | 1.0 per 100 kanji tokens                    |
| Leech seeds                      | 1.5 per 100 kanji tokens                    |
| Minimum occurrences per new word | `max(2, round(tokens / 150))`               |
| Repeated-word share              | ≥40% of tokens are words appearing 3+ times |
| Sentence length stdev            | ≥6.0                                        |

**The mandatory rule about new words is qualitative and no script checks it: the first occurrence must sit in a sentence that frames the meaning from context.** Repetition past that is what makes the word stick, but framing is what makes it derivable rather than a lookup.

Corollary for word choice: admit a new word only when it is the story's own subject matter, so it recurs without the prose working at it. ｜城《しろ》の｜鐘《かね》 repeats ｜鐘《かね》 36 times because it is about bells. If a draft has to reach to repeat a word, it is the wrong word.

Per-story new words go in that story's `new_words` block in `corpus.json`, **not** in `approved-words.json`, which stays a short global list of permanent allowances. Declaring is required rather than optional: `check.py`'s particle-splitting fallback accepts ｜部品《ぶひん》 as 部 + 品, so the unknown detector never sees compounds, and an undeclared new word gets no marking in the reader.

Leech words come from `vocab.weak_forms()` — kanji words tagged leech in Anki and above the known threshold. Reading one in context beats another card review. Use them where they fit; never force one.

## Format

```
# ｜題名《だいめい》

一文。
> One sentence.
次の文。
> The next sentence.

（空行がページを分ける）
```

- **One Japanese sentence per line, each immediately followed by its translation on a `>` line.** The 1:1 coupling is load-bearing and nothing checks it at build time. Split a Japanese sentence and you must write the second translation.
- **One quoted turn per line, however many sentences it holds.** 「」 brackets a turn — everything one speaker says before anybody else speaks or the narration resumes — not a sentence. Sentences inside a turn are divided by 。 as usual, and the last one drops its 。 before the 」. This is the only place the one-sentence-per-line rule yields, and it has to: the alternative is a closing 」 in the middle of somebody still talking.
- Blank line separates pages. Aim for four to five sentences a page.
- **This format once became a style rule by accident.** The 1:1 coupling made long multi-clause sentences awkward to keep aligned, so the first five stories were written almost entirely in short declaratives: mean 17 characters, standard deviation 4.6, and three of the five contained no sentence over 30 characters at all. Vary length deliberately. The stdev floor exists to catch exactly this.
- **The coupling is not a reason to write short.** Write the long sentence and translate it as one long sentence. What the coupling really discourages is **subordination** — 連用形 chaining, relative clauses, ので / のに / ながら — and those are the level ladder's own constructions, so writing around it works against the ladder. `stats.py` reports `subordinate_share` for this; it is measured and not yet gated.

### 「」 is the speaker attribution

Most quoted lines carry no dialogue tag, so a reader has nothing but the brackets to go on: a new 「 means the speaker changed, or the same speaker stopped and started again. Splitting a continuous turn across several 「」 therefore *says* something false, and there is no other cue to contradict it.

```
✗ 「あの鐘は、私が四十の時に作った」        ✓ 「あの鐘は、私が四十の時に作った。当時の王の命令だ。戦争のための鐘だった」
  「当時の王の命令だ。戦争のための鐘だった」
```

The ✗ column is two people. It is one man telling one story, and it shipped that way — the September 2026 audit found 21 turns split like this across six of the seven stories, produced by reading the one-sentence-per-line rule as though it outranked the brackets.

**But a beat is a real reason to open a second 「.** A speaker who stops, is not answered, and starts again is two turns, and the brackets are how that silence is written. ｜終電《しゅうでん》 is built on this: almost nothing is attributed, her replies come in separate four-to-eight character bursts against his long over-polite questions, and the narration hands the reader that key outright — 彼女の返事はいつも短い。私の質問は、どうしても長くなる。Merging those turns inverts the one cue the story gives. It was audited and deliberately left split.

So the test is not "same speaker, therefore merge". It is **continuous or not**: one breath with nothing between the sentences is one 「」, and a pause the reader is meant to feel is two.

**A narrative tag closes the turn.** 「｜海《うみ》は」と｜祖父《そふ》は｜言《い》った。「｜青《あお》かったか」 is right and stays two lines: the tag interrupts, so the same speaker's continuation opens a fresh 「. So does a page break, which is why a turn never spans one.

```bash
python3 stats.py ../stories/<slug>.txt --turns   # every run of adjacent quoted lines
```

Read down each block and name a speaker for every line. Tagged lines say who they are and close their turn; the rest alternate unless a beat says otherwise. Two neighbours you would give to the same speaker, with no silence between them, are one turn wrongly split. Nothing gates this — neither speaker identity nor a pause is recoverable from the text, so the script prints and you judge.


## Furigana

Annotate ambiguous readings in the source as `｜漢字《かな》`. The build trusts the annotation over both Ichiran and the global override table.

Annotate any token a parser could plausibly get wrong. The audit of the first five found 31 errors, concentrated in ｜下《した》 read as もと, ｜中《なか》 as ちゅう, and ｜空《そら》 as から. Also annotate register choices such as ｜皆《みな》 over みんな, and compounds a parser splits wrongly: ｜町中《まちじゅう》 was being forced to まちなか by the global rule.

An annotation on a verb stem covers its inflection, so `｜行《い》った` correctly yields いった.

`readings-overrides.json` is the legacy mechanism and is being retired as stories are annotated. It replaces readings by bare surface across the whole corpus, which cannot be right for a genuinely ambiguous token. Do not add to it; annotate instead.

## Writing rules

- **Never state the theme.** A parallel revision pass in September 2026 produced the same defect in four of five stories, in nearly the same grammatical shape: a closing `〜というのは、こういうことなのだろう` sentence explaining the point. All were cut.
- **But do not leave the reader nothing.** Cutting those lines is what made the stories hard to unwind, because the inference chains run thirty-plus sentences in a reader that shows one sentence at a time. The replacement is the **afterword** — now written at Gate 2, before drafting, and filed in the `## Afterwords` section of `stories/stories-index.md`, which the reader folds away until the last page. Write one for every story.
- **No em dashes, en dashes, or standalone hyphens-as-pause in the English translations.** Hyphenated compound words are fine. Translations should read as natural literary English, never as glosses.
- Personal names must survive segmentation whole. ｜竜崎《りゅうざき》 splits into ｜竜《りゅう》 + ｜崎《さき》; ｜松田《まつだ》、｜青山《あおやま》、｜梓《あずさ》、｜澪《みお》 do not.
- Keep the domain narrow. That is what produces recycling, and it is the only honest way to hit the repeated-word share floor.

## The revision pass

Five failure modes, each found the expensive way. Run this against every draft.

| Failure                          | Evidence                                                      | Check                                                      |
| -------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| Closing thesis sentence          | 4 of 5 stories, near-identical shape                          | Does the last page state what it means? Cut it.            |
| Flat short declaratives          | mean 17 chars, stdev 4.6; 3 of 5 had nothing over 30          | Is every sentence one clause?                              |
| Variance bought long-only        | ｜猫《ねこ》 +24%, ｜城《しろ》の｜鐘《かね》 +14% over brief | Are the long sentences long from structure, or more nouns? |
| Circumlocution to dodge unknowns | 一緒に暮らしている人 for ｜飼《か》い｜主《ぬし》             | Is a phrase working around a word rather than using one?   |
| One turn split across several 「」 | 21 turns, six of seven stories, Sept 2026                 | `stats.py --turns`; does a 」 close mid-breath, with no beat? |

## Metrics are floors, not targets

**Every threshold catches a specific failure this corpus actually produced. None is a target to optimise.** A story can meet all of them and still be inert; a story can miss one and still be the right story, in which case say so and ship it.

This clause is load-bearing rather than decorative: two of the five failures above were _caused_ by optimising a metric. Sentence variance was bought by writing long, and driving the unknown-word count to zero is what produced the circumlocutions.

### The reference band is not a floor either

```bash
python3 reference.py --compare    # our numbers beside authentic 児童文学
```

Every floor in `corpus.json` is calibrated from this project's own output — `min_repeated_share` 0.4 from an observed 44-62% spread, `min_sentence_stdev` 6.0 from just under the lowest stdev any story had recorded. A corpus measured against itself can be no better than its own best member, so `reference.py` reads the same structural axes off public-domain children's literature from 青空文庫 (新美南吉, 宮沢賢治, 小川未明, in 新字新仮名, NDC K913), sampled per author and binned against equal-width thirds of the corpus's own character range.

**It reports a band. It gates nothing, and it must not become a gate.** The danger here is larger than the one this section already describes: "real authors score 21.5" is a far more persuasive argument for chasing a number than "our lowest story scored 6.7" ever was, and writing to the band would buy the same variance the same dishonest way. `reference.py` writes no threshold, never touches `corpus.json`, and exits zero regardless.

Four things about it that are easy to get wrong, all recorded at length in the script's docstring:

- **Never run the vocabulary checks against it.** `new_words`, `leech_seeds` and unknown-token counts are meaningless on a text nobody wrote to Rob's known set. `reference.py` never imports `vocab` or `check`, and asserts it rather than trusting anyone to remember.
- **Orthography is a real confound, not a detail.** Children's books write verbs in kana; this project writes them in kanji, because kanji recognition is the point. On 新美南吉's ｜飴《あめ》だま only 18% of tokens carry kanji on the surface against 48-52% here, so `repeated_share` and `hapax_rate` are reported on both a surface and a lemma basis. Compare like with like or not at all.
- **`untagged_pct` does not transfer.** Aozora usually sets the attribution in the sentence _after_ the quote, where `TAGGED` cannot see it. How often is strongly author-dependent — 宮沢賢治 runs near 100%, 小川未明 as low as 25% — so it measures typographic habit rather than difficulty.
- **Level and length are collinear across all seven stories**, so "does the gap close as the ladder rises" cannot currently be answered: every metric that rises with level also rises with token count. Breaking that needs a level 1 story at ~1100 tokens or a level 5 at ~400, which is a brief rather than an analysis.

## Validate, then build

```bash
python3 stats.py ../stories/<slug>.txt --turns --strict   # turns, then level/brief/rhythm
python3 check.py ../stories/<slug>.txt                    # vocabulary; slow, ~30-60s
python3 rebuild.py                                        # only stale stories; index.py last
```

`--turns` prints and never fails, so it is the one step here that cannot tell you it was skipped. Run it anyway: nothing else in the pipeline sees a split turn, which is how 28 of them shipped.

`rebuild.py` handles ordering, and knows which build input touches which output — editing an afterword in `stories-index.md` re-segments the story it belongs to, while editing `reader.js` or `reader.css` only rewrites the shared engine. Do not run `build.py` and `index.py` by hand unless you know why: `index.py` reads the built readers, so rebuilding a story after it leaves the contents page stale with nothing to flag it.

Unknown words no longer block a build; they print a note. `--strict` restores the old gate.

To work on the reader UI rather than a story, `python3 build.py <story> --split <scratch-dir>` writes one story into a scratch directory in the same linked shape `docs/` uses, with flat filenames. Edit `scripts/reader.css` or `scripts/reader.js`, re-run, reload — nothing re-segments.

## Where a story lands

Four places. Miss one and the corpus is inconsistent in a way only some of them report:

1. `stories/<slug>.txt` — the story
2. `scripts/corpus.json` `stories[]` — entry with `level`, `brief`, `_premise`, `new_words`, in reading order
3. `stories/stories-index.md` `## Summaries` — one bullet. Without it `index.py` warns and the card ships with no blurb and no kana reading; nothing else in the pipeline checks
4. `stories/stories-index.md` `## Afterwords` — one bullet, written at Gate 2

## Modes

- **new** — the default, all four steps above.
- **revise `<slug>`** — edit the `.txt` in place. The brief already exists; re-run `stats.py --strict` against it.
- **version `<slug>`** — archive the current text to `stories/versions/<slug>.vN.txt`, add `vN` to that entry's `versions[]`, then write the new current. `rebuild.py` builds archived versions too, so A/B comparison stays available via `stats.py --diff`.

## Committing

Two lanes.

**A story-only change** — a new or revised `.txt`, its `corpus.json` entry, its `stories-index.md` bullets, and the rebuilt files under `docs/` — goes straight to `main` once `stats.py --strict` and `check.py` pass. Those are the review: they are stricter about a story than reading the generated HTML would be.

**Anything touching the engine** — `scripts/*.py`, `reader.html`, `reader.css`, `reader.js` — goes on a branch, gets reviewed, and is merged. A change that touches both takes the engine lane.

Rebuilding after an engine change rewrites every story, so keep that commit separate from the change that caused it.

## Never

- Do not add to `approved-words.json` without asking. It is deliberately a short list.
- Do not edit `docs/index.html`. It is generated.
- Do not write the `brief` block programmatically. Edit `corpus.json` by hand.
