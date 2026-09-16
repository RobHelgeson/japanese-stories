# Calibration

Where every threshold in `scripts/corpus.json` came from, what was measured against what, and which conclusions were wrong.

This used to live inside `corpus.json` as `_comment` keys on the `budgets` block — 8.6KB of prose wrapped around five values, each key one unwrapped line of JSON, so none of it diffed and none of it could carry a heading or a table. Moved out on 2026-09-16. The numbers stayed; a one-line pointer stayed with them.

**Nothing here is a gate.** `stats.py --strict` enforces the numbers in `corpus.json`. This file is the argument behind them, and § The reference band is explicitly the thing that must never become one.

## The budgets are rates, not counts

They scale with story length. A fixed "5+ occurrences per new word" would have spent 5.7% of the shortest story's content tokens on two words, which reads as engineered, so the occurrence minimum is a rate too.

The mandatory requirement is qualitative and no script checks it: **a new word's first occurrence must sit in a sentence that frames its meaning.**

## `min_repeated_share` 0.4

The fraction of content tokens belonging to words that appear three or more times — how much of what you read is vocabulary you meet again.

It replaced a hapax-rate gate that was set at 50% by guesswork and is unreachable: hapax runs 57–79% across the corpus, and the floor belonged to the longest story rather than the tightest. Hapax also punishes verb variety, since every distinct verb is another word seen once.

The 0.4 floor is calibrated against the corpus — 城の鐘 62%, 猫を探す探偵 54%, 迷子の手紙 44% — and it correctly flags the two weakest, 終電 at 31% and 時計の音 v1 at 30%.

## `min_sentence_stdev` 6.0

A floor set just under the lowest stdev any story had recorded. Measured today the corpus runs 6.7 (終電) to 11.5 (行かなかった人の地図); nothing has ever scored 6.0, which is what a floor should do.

> **Corrected 2026-09-14.** This was documented as "the best observed value (迷子の手紙 6.5)". Wrong twice: 6.0 is a floor under the _lowest_, not the best, and the 6.5 figure was stale — 迷子の手紙 measures 7.4 today, having been revised since. The floor itself never changed; only the description of it was wrong.

## `subordinate_share` — measured, deliberately not gated

The share of sentences carrying a subordinate clause (連用形 chain, relative clause, or one of the ladder's own subordinators). `stats.py` reports it and nothing gates it, and the 2026-09-14 calibration settled why it should stay that way.

Across 25 authentic texts, `subordinate_share` varies more **within** one author than between this corpus and authentic prose: per-author medians 新美南吉 47.9, 宮沢賢治 48.4, 小川未明 61.7, against our 43.9–58.8, with two of the three inside our range. Bin-matched we sit at or above authentic in every bin. There is no band here to gate against.

The measure's own limit: it is binary per sentence, so five clauses chained with て score what one ので clause scores. That looked like a hiding place for a real gap. It is not — see correction (b).

## The reference band

External calibration against 25 public-domain 児童文学 texts (新美南吉 / 宮沢賢治 / 小川未明, 新字新仮名, NDC K913), stratified by author and binned into equal-width thirds of this corpus's character range. Run by `reference.py`.

Re-measured 2026-09-15 after the quote-turn merge, which redefined a source line as a whole speech turn and moved both corpora. These figures supersede the 2026-09-14 set. All are **bin-matched** — the corpus splits 4/2/1 across the bins while the reference splits 7/8/10, so a pooled column would mislead.

**Read beside, never gate on.** See `AUTHORING.md` § Metrics are floors, not targets.

1. **The corpus is compressed on sentence length, and this is the finding.** `mean_len` 16.3–21.0 against a bin-matched 28.5–32.6; `stdev_len` 6.4–11.6 against 18.9–21.2; `pct_over_30` 3.8–18.6 against 35.2–43.0, every story below its own bin. Measured in Ichiran **tokens**, which orthography does not move, the gap is 8.9 per sentence against 12.0 — **1.34x**. In characters it reads 1.60x, and the difference between the two is kana: children's books spend more characters on the same content. Quote the token figure.
2. **Not on subordination.** Bin-matched we are at or above authentic in every bin: short 43.9–53.0 against 50.0, mid 51.1–53.5 against 48.7, long 58.8 against 52.4. The expectation that opened this work was that the corpus would be flatter here. It is not.
3. **`min_sentence_stdev` 6.0 is very low against authentic prose** (bin-matched 18.9–21.2). Not raised, and it must not be: "variance bought long-only" is already a documented failure mode, and a persuasive external number is precisely how it would recur. A craft observation for the revision pass, nothing more.
4. **`min_repeated_share` 0.4 is vindicated and conservative.** Bin-matched we recycle harder than authentic prose in every bin: short 48.7–64.4 against 36.7, mid 60.7–63.5 against 49.5, long 72.7 against 51.6.
5. **`distinct_constructions` runs above authentic rates in every bin** (19–26 vs 16 short, 28–32 vs 20 mid, 26 vs 22 long): the ladder pushes construction variety past what children's literature does. See § The asymmetry.
6. **城の鐘 is the story worth a rhythm pass** — declared level 5, but `mean_len` 16.9, `stdev` 7.1 and `pct_over_30` 5.5 are level 1 numbers. The ladder grades construction inventory and says nothing about sentence architecture.
7. **Untested: whether the gap closes up the ladder.** Level and token count are collinear across all seven stories measured, so nothing separates the ladder from length at n=7. Breaking that needs a level 1 story at ~1100 tokens or a level 5 at ~400, which is a brief rather than an analysis.
8. **Caveat on the band.** 小川未明 is the outlier author — `subordinate_share` 61.7 against 48.4 and 47.9, `pct_over_30` 47.7 against 36.1 and 42.3 — and he is 505 of the 617 eligible texts. An unstratified sample would have measured him and called it authentic prose.
9. **The band is diagnostic, not a target.** Authentic children's books are written for readers with native grammar and no kanji; this reader is the inverse. A 賢治 sentence of 368 characters is easy for a Japanese eight-year-old and hard here.

### Four ways to misread it

```bash
python3 reference.py --compare    # our numbers beside authentic 児童文学
```

- **Never run the vocabulary checks against it.** `new_words`, `leech_seeds` and unknown-token counts are meaningless on a text nobody wrote to Rob's known set. `reference.py` never imports `vocab` or `check`, and asserts it rather than trusting anyone to remember.
- **Orthography is a real confound, not a detail.** Children's books write verbs in kana; this project writes them in kanji, because kanji recognition is the point. On 新美南吉's ｜飴《あめ》だま only 18% of tokens carry kanji on the surface against 48–52% here, so `repeated_share` and `hapax_rate` are reported on both a surface and a lemma basis. Compare like with like or not at all.
- **`untagged_pct` does not transfer.** Aozora usually sets the attribution in the sentence _after_ the quote, where `TAGGED` cannot see it. How often is strongly author-dependent — 宮沢賢治 runs near 100%, 小川未明 as low as 25% — so it measures typographic habit rather than difficulty.
- **Level and length are collinear** across all seven stories measured, so "does the gap close as the ladder rises" cannot currently be answered: every metric that rises with level also rises with token count.

`reference.py`'s own docstring records all four at length, and `scripts/reference.json` — the manifest of sampled 青空文庫 texts — is read by that script and nothing else.

## The asymmetry

The corpus applies opposite strategies to its two axes, and only one of them was a decision.

**Vocabulary is recycled far harder than authentic prose does** — bin-matched `repeated_share` 48.7–72.7 against 36.7–52.4. That is correct, and it is what a graded reader is for.

**Grammar is spread thinner.** `distinct_constructions` runs above authentic rates in every length bin, because `min_carried` 0.6 forces a story to keep exercising 60% of every lower rung while `min_present` forces breadth within its own. Authentic children's literature does the reverse: fewer constructions, used more.

Nothing is changed on the strength of this — n=7 is not enough to move a ladder, and construction breadth is arguably the point of a _teaching_ corpus in a way it is not for a story. Recorded so the next person to widen `min_carried` knows the corpus is already wider than its model.

## Corrections

Kept because each one was wrong in a way worth not repeating.

**(a) The figures were re-measured, 2026-09-15**, after the quote-turn merge redefined a source line as a whole speech turn. Both corpora moved. The length gap has shrunk each time an artifact came out of it — 1.81x (characters, old split), then 1.51x (tokens, old split), now 1.34x (tokens, correct split). It is real, and it is smaller than first reported.

**(b) A clause-density measure was built and reverted.** The theory was that `subordinate_share` saturates because it is binary, so counting subordination _events_ would expose a gap. It produces a number, and the number does not mean that: events per 100 characters run 2.76 here against 2.43 authentic — this corpus is already denser per character — and events per sentence correlate with `mean_len` at r=0.805, restating a measure already reported. The implementation was unsound besides: `TE_CHAIN` requires a kanji after て/で and so undercounts kana-heavy reference text (r=0.53 with a text's kanji ratio), the instrumental particle で before a kanji noun counts as a clause, ので double-counts against `TE_CHAIN`, and 前に matches 目の前に. **The corpus's problem is that its sentences are short, not that its clauses are sparse.**

**(c) `corpus_bins()` counted characters over source lines while `measure()` reports `chars` over `prose_sentences`.** Once a line became a speech turn the two drifted enough that a story fell outside its own corpus's range and binned as `None`, crashing `--compare`. Both now count the same way, and reference bins are computed live rather than read from the manifest, which records whatever `--sample` measured at the time.

**(d) `ichiran.align()` drops any token it cannot locate by string search without advancing its cursor**, and on some reference texts that discards most of the alignment. Only `_relative_clause` consumes it, so reference `subordinate_share` is a floor rather than an estimate — conservative in the direction that would weaken finding (2). **Still unfixed**; it predates this work.

**(e) `min_sentence_stdev` 6.0 was documented as the best value any story had hit.** It is a floor just under the lowest. See § `min_sentence_stdev` 6.0.

## Two claims the reading order once made, both false

Recorded here rather than in `stories/stories-index.md`, where they sat until 2026-09-16 and where nothing measured them.

**"Sentence length escalates across the set."** It does not. In the original five, mean sentence length ran 17.7, 19.2, 17.5, 18.1, 16.9 characters — 城の鐘 had the _shortest_ sentences of the five, and three of the five contained no sentence over 30 characters at all.

**"終電's distinguishing difficulty is untagged dialogue."** Its untagged proportion was the _lowest_ of the five at 52.9%, against 83.3% in 時計の音, and 迷子の手紙 held the longest untagged run.

The ladder was inverted on the one axis it claimed. `stats.py` now measures every declared axis, so this cannot drift again — which is the general lesson: a claim about the corpus that no script computes is a claim that will eventually be wrong.

## The leech pool was a bug, not a writing decision

The set carried 11 leech words across five stories before 2026-09-10 and 63 after. `weak_forms()` read only `Card_Morph_Map`, which AnkiMorphs populates for the `Morphs::*` decks alone, so of 876 unsuspended leech cards it could see 35. Reading the Core, Jlab and Duolingo note fields as well took the usable pool from 14 kanji words to 189.

## Related

- `AUTHORING.md` — the craft spec, and where the floors are stated as rules
- `scripts/corpus.json` — the numbers themselves
- `scripts/reference.py` — `--compare` regenerates the band; it writes no threshold and exits zero regardless
