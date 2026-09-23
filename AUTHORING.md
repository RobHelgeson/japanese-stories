# Authoring a story

Write a story the reader can read without a dictionary, at a declared difficulty level.

Everything below is enforced or measured by the scripts in `scripts/`. Run them; do not eyeball.

**Two gates, in order. Stop at each one.** Gate 1 settles what the story is briefed to be. Gate 2 settles whether it is a story at all, in English, before a single Japanese sentence is written — and it is built backward, from the climax. Only then draft — and the draft runs the other way round, in Japanese, a page at a time, with the English written last. See § Drafting.

## Before writing

```bash
cd scripts
export ICHIRAN_URL=http://localhost:3005   # or wherever your Ichiran runs; comma-separate fallbacks
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
python3 brief.py [--level N] [--pages N] [--page-slack N] [--register R]
                 [--new-words N] [--leech-seeds N] [--repeats F]
                 [--grammar-focus a,b] [--dialogue PCT[,untagged]] [--topic "..."]
```

Print the table, **then stop and ask.** Do not draft until the brief is confirmed.

| Parameter       | Default                  | Checked by                                        |
| --------------- | ------------------------ | ------------------------------------------------- |
| `level`         | 3 — N3 voice             | `stats.py` level ladder                           |
| `pages`         | 25, ±10%                 | `stats.py` brief check                            |
| `page_slack`    | none — `page_tolerance`  | `stats.py` brief check — ±N pages, absolute       |
| `topic`         | none — propose 2-3       | Gate 2                                            |
| `register`      | `quiet-realism`          | Gate 2                                            |
| `new_words`     | 1.0 per 100 tokens       | `stats.py` brief check                            |
| `repeats`       | ≥40% repeated-word share | `stats.py` target                                 |
| `leech_seeds`   | 1.5 per 100 tokens       | `stats.py` brief check                            |
| `grammar_focus` | none                     | `stats.py` brief check — all must be present      |
| `dialogue`      | unconstrained            | `stats.py` brief check — ±10, untagged means ≥90% |
| `mode`          | `new`                    | see Modes                                         |

**`page_slack` widens the page check for one story, in pages rather than as a percentage.** Without it the range is `page_tolerance`, the global 10%. It is there because some shapes cannot be briefed to a length honestly — a story built backward from a climax does not know how many pages the descent needs until the beats exist. Set it at Gate 1, where it is on the record, and say why. Note what it costs: `--page-slack 10` on a 25-page brief accepts 15 to 35, which is ±40%, and both of the overruns that made the brief worth persisting at all — ｜猫《ねこ》を｜探《さが》す｜探偵《たんてい》 at 24% and ｜城《しろ》の｜鐘《かね》 at 14% — would have passed it. A slack wide enough to swallow the failure the check exists to catch is not a check. Use the default unless the brief has a reason.

Every parameter has a default, so a bare invocation is a complete brief. Defaults live in `corpus.json`'s `defaults` block, not here — a default nothing reads is a suggestion. `grammar_focus` names must be keys of `GRAMMAR_PATTERNS` in `stats.py`; `brief.py` rejects the rest.

With no topic given, propose two or three domains the corpus has not used. The six so far are watches, letters, trains, a bathhouse, a missing cat, and a cast bell.

**Run `reviews.py` before proposing anything.** It prints the star ratings and notes from the contents page against the level, register and length each was a verdict on. Read the notes rather than the averages: a note naming what dragged or what had to be re-read is a constraint on the next brief, while a mean over three ratings is a number looking for a pattern. Say which review you are responding to when a parameter departs from the default because of one — an unattributed change to `dialogue` or `register` is indistinguishable from a whim, and the brief is the only record either way. Nothing here is automatic: no parameter is derived from a rating, and a low-rated register is not retired on the strength of one story.

**Persist the brief.** Once it is confirmed, `python3 brief.py --json` emits the block for the story's `corpus.json` entry. Add it **by hand** — that file is hand-maintained and carries comment keys and one-line arrays that `json.dump` would reformat. Persisting it is the whole point: nothing recorded what a story was supposed to be, which is how ｜猫《ねこ》を｜探《さが》す｜探偵《たんてい》 ran 24% long and ｜城《しろ》の｜鐘《かね》 14% without either being noticed.

## Gate 2 — the story, in English

Before any Japanese exists, write and stop on:

```
CLIMAX    one scene. Specific, unexpected, and emotionally messy
AFTERWORD full spoiler, in English — what the story is actually doing
PREMISE   two or three sentences
WANT      the external goal — tangible, visible, sayable in one clause
NEED      the internal one — the wound or the flaw the want is hiding
SHAPE     three-act (default), two-act, or five-act
BEATS     6-10, built backward from the climax, act boundaries marked,
          each resolving as a yes-but or a no-and
```

**The order of that list is itself the rule.** Every line above is produced against the lines above it, and the sheet is worth nothing produced in any other order — a climax chosen after the beats is the climax the beats were already heading for.

**Write the climax first, and do not write the obvious one.** A story composed front to back arrives at the ending it was always going to arrive at, because each beat is chosen to follow the one before it and the last one has nowhere else to go. So write the final scene before anything else exists: a specific scene rather than a representative one, with something in it nobody would have predicted from the premise, and a cost the character actually pays. Then build every earlier beat backward from it, planting what that particular climax needs in order to land as earned rather than arranged.

The September 2026 audit is the evidence. Six of eight stories ended by stating their own meaning, and in every case the evaluator named an earlier line as the real ending, unprompted — 網棚は、最後まで空いたままだった, 私は止めなかった, 部品の箱の隣ではなく、机の上に置いた。 Those endings were not chosen. They were arrived at, found thin, and then explained, which is what the closing thesis sentence in § Writing rules always is.

**The afterword is still written before drafting; it is now written second.** It used to be written last, as a patch for the removed theme statement, and inverting it made it the design document. The climax takes that job now, which changes what the afterword is rather than when it happens: it is a reading of a scene that already exists rather than a statement of intent, and that is a better test, because an afterword you cannot write off your own climax means the climax is not carrying anything. Everything else stands. If you cannot write it before drafting you have a situation and not a story, and it has a canonical home — the `## Afterwords` section of `stories/stories-index.md` — so writing it early means writing it where it will live.

**Want and need are two tracks, and the second is what makes the first cost something.** The want is the external goal: win the tournament, find the cat, finish the bell. It is visible, the character can say it out loud, and on its own it produces the straight line — wants X, does Y, gets X. The need is the internal one: the wound, the flaw, or the thing about themselves they have not admitted. Write both before the beats, and bind them with the rule that makes them a story rather than two lists: **the character cannot have the want until they face the need**, and most often they give up the want in order to get it.

This is the machinery behind § Craft's "one turn, and the reader can point at it". The turn is the sentence where the need is faced, and the want is what it costs. The old rule said a change happens somewhere; it never said the change was internal, and it never said anything was surrendered for it.

**Declare the shape.** Three are documented below. Three-act is the default and the others are chosen deliberately, per story, at this gate — not derived from the topic, the level, or the page count, and not a parameter of Gate 1. Name the shape on the sheet and mark the act boundaries on the beats, because an undeclared shape is indistinguishable from no shape.

**Every beat resolves as a yes-but or a no-and.** See § Craft, first rule. The beats are where that rule is enforced, and a sheet where it holds nowhere is the thing to send back.

### The three shapes

Beat counts are given as fractions of the sheet, not as numbers, because the sheet runs 6-10 and a fixed allocation would only be right at one length.

**Three-act — the default.** Setup, confrontation, resolution, with the twist in the third and its seeds in the first.

- **Act I, the first quarter.** The want is established and visible; the need is present and unnamed. The veiled setup goes here. A veiled plant reads at the time as something else — a habit, a piece of scenery, an offhand line — and only becomes a plant in retrospect. This is the shape to work hardest at, because a plant the reader files as a plant has already given the twist away.
- **Act II, the middle half.** The want is pursued and the pursuit costs. Each beat turns against the character. The need surfaces here, in what the pursuit keeps breaking, and is still not stated.
- **Act III, the last quarter.** The climax, which is where the Act I plants pay off and where the need is faced. The want is surrendered, transformed, or won in a form the character no longer wanted.

**Two-act.** Setup and rising action, then climax and resolution.

- **Act I, the first half.** Want established, need buried, pressure applied. There is no separate exposition beat; the want and the world arrive together in the first beat.
- **Act II, the second half.** The climax and everything after it. Because the break lands mid-sheet, the second half carries the whole descent as well as the turn, which makes this the shape with the most room after the climax — useful when the story is about the consequence rather than the reversal.
- Plant and pay off still applies and has less distance to work with. Plants go in the first two beats or they are not veiled, they are recent.

**Five-act.** Exposition, rising action, climax, falling action, catastrophe or resolution.

- **Acts I-II, the first two fifths.** Exposition, then rising action. The one shape that gives exposition a beat of its own.
- **Act III, the middle fifth.** The climax, structurally centred rather than at the end. Everything after it is consequence.
- **Acts IV-V, the last two fifths.** Falling action, then the resolution or the catastrophe. This is what five acts buy and it is the reason to choose the shape: two full acts in which the climax's damage plays out.
- **It needs the top of the beat range.** At six beats, five acts is roughly one beat each and the falling action gets a single line, which is the half of the shape worth having. Take this one at nine or ten beats or take a different one.

Whichever shape is declared, it is a shape to build toward and not a form to fill. A beat that exists because the act diagram has a slot there is worse than an act boundary in a slightly wrong place.

Record the whole sheet — climax, afterword reference, premise, want, need, shape, and beats — as `_premise` on the `corpus.json` entry, alongside the existing `_feature` and `_note` prose keys. It is a prose key and nothing parses it; write it as the sheet, not as a schema.

**The gate is bigger than it was, and that is deliberate.** The old sheet was three lines and could be approved at a glance. This one has a climax, two tracks, a declared shape, and a filter applied to every beat, and it takes a real reading. That is the cost of the enforcement mechanism: no script checks any of this, none should try (§ Metrics are floors, not targets), and the entire weight of six craft techniques rests on someone reading the sheet and sending it back. A skimmed Gate 2 enforces nothing.

## Craft

The rules below are what to do. The prohibitions further down are what not to do. Both matter; only one of them used to be written here.

- **Friction, not sequence.** Every beat resolves as a **yes, but** or a **no, and** — the character gets what the beat was for and it creates a new problem, or they fail and the situation worsens with it. A beat that simply succeeds is not a beat. The connective is how you check it: write the honest join to the next beat, and そして or それから means you have a list of events rather than a story, while だから or しかし means you have causality. **Causality is the floor, not the test.** An all-だから sheet joins perfectly and is still a character getting what they want in the order they wanted it, which is the straight line this rule exists to break. This is what the beat sheet is testing, and the old wording tested only the floor.
- **One turn, and the reader can point at it.** Something is different at the end than at the beginning, and there is a specific sentence where it changed. ｜城《しろ》の｜鐘《かね》 states its distinction exactly once, in dialogue, on page 11. The turn is where the need is faced and the want is paid — see § Gate 2, want and need. A turn in the external situation alone is an event, not a turn.
- **Plant and pay off, and veil the plant.** ｜猫《ねこ》を｜探《さが》す｜探偵《たんてい》 plants the boxes clue on page 7 and does not recall it until page 20. What that example does not yet do is hide it: a plant the reader files as a plant has spent the twist in advance. Plant it as a habit, a piece of scenery, or a line said for some other reason, so that it is doing visible work of its own at the time and a second job at the climax. This is structural under the three-act default, where the plants live in Act I and pay off in Act III.
- **Concrete before abstract.** An abstract noun has to be earned by a physical detail that came first. This serves the vocabulary constraint too: concrete nouns are what the known set is richest in.
- **Withhold, never confuse.** The reader sees one sentence at a time and the inference chains run thirty-plus sentences. Information must stay retrievable — plant it concretely, and never ask the reader to hold an ambiguity across pages.
- **Write from inside the culture, not from English with Japanese words.** The story has to be one a Japanese reader recognises as theirs, not an American story rendered into Japanese. This is the corpus's named defect and the audit found it at three depths. **Speech:** an eighty-year-old craftsman, a schoolboy, a knight captain and a middle-aged detective all spoke identical neutral textbook Japanese — no ｜役割語《やくわりご》 anywhere, 私 where a novel gives the dying master わし, no 〜ぞ / 〜な / 〜さ on any male character. Also あなた as a second-person address where Japanese uses the surname or nothing, and おばあさん used inside a family where it is おばあちゃん. **Fact:** a 定期券 carrying a company name, which is the 社員証; one 桶 left inverted as the anomaly, when inverted is how they are stored; 閉店 for a 銭湯 closing, which is 廃業; a conductor checking tickets on a 通勤 train; ten-day domestic mail, which is four at the outside; 部屋 and 表札 and a neighbour's garden in one dwelling. **Absence:** a story about a grandson clearing his grandfather's house containing no 遺品整理, no 形見, no ｜四十九日《しじゅうくにち》 — 形見 is the word for the watch. And season used only as a section marker, never as a subject, in a tradition that organises prose of this length by it. The corpus proves it can do this, so it is a process defect and not a capability one: ｜行《い》かなかった｜人《ひと》の｜地図《ちず》 gives four speakers four voices — 祖父 わし, 甚平 〜ん / 〜とな, 千代 わたし, 蓮 です・ます — and its 山は紙に入らん was named the single most Japanese line in the corpus. Check the era of every name against every other, and check any institution, object or procedure the story leans on before it becomes the story's centre. Nothing in the validation stack sees any of this.
- **Nobody says what they mean.** On-the-nose dialogue — a character stating what they feel, or answering the emotional question they were asked — is the default and has to be written against. Three constraints, applied per scene: **a secret**, one piece of information each character in the scene is actively keeping from the others; **misdirection**, no direct answer to a direct emotional question, so they change the subject, deflect into a physical action, or say something beside the point; and **conflicting agendas**, a different micro-goal per character, so one wants an answer and the other wants to leave the room. The vocabulary constraint bites unevenly here and picks the technique for you. Deflection into action and changing the subject cost nothing — a hand moved, a cup set down, a question about the weather are all inside the known set. Sarcasm and irony need range that set may not hold; check with `have.py` before building a scene on one. The corpus already has the good version: 「静かにしろ。音が聞こえない」 is a command with a reason and no softening, and 「この鏡は動かさないでください」 is a woman asking her own family with ください, which is neither an order nor a plea and says the whole power gradient without naming it.

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

**The mandatory rule about new words is qualitative and no script checks it: at its first occurrence the word must be doing something. It appears in an action or in a consequence — never in a sentence whose only business is to say what it means.** Repetition past that is what makes the word stick, but a first occurrence the reader can act on is what makes it derivable rather than a lookup.

This rule used to read "the first occurrence must sit in a sentence that frames the meaning from context," and apposition frames the meaning from context. So apposition is what the corpus produced. The four evaluators who read all eight stories in Japanese only, in September 2026, named this the single clearest tell that the text had not been written for a Japanese reader — one of them called it decisive on its own.

```
✗ ｜峠《とうげ》というのは、｜山《やま》と｜山《やま》の｜間《あいだ》の、｜一番《いちばん》｜低《ひく》いところである。
✗ ｜崖《がけ》とは、｜岩《いわ》が｜真《ま》っ｜直《す》ぐに｜立《た》っているところである。
✗ 番台は入り口の上にあって、そこからは男の方も女の方もよく見える。
✗ 席の｜上《うえ》には荷物を乗せる｜網棚《あみだな》があって、今夜はそこに何も乗っていない。
✗ 制服を着た｜車掌《しゃしょう》が、切符を確かめながら通路をゆっくり歩いてきた。
✗ ｜表《おもて》には、針が三本あった。
```

Every one of 峠, 崖, 番台, 網棚, 車掌 and 針 is a declared new word doing exactly what the old rule asked for. Three shapes, and the third is the one that hides:

- **The copula gloss** — というのは / とは. A dictionary entry with a 。 on it.
- **The existence statement** — 〜があって, 〜があった. Nothing happens; a thing is reported to be present so that it can be named.
- **The definitional pre-modifier** — 荷物を乗せる｜網棚《あみだな》, 制服を着た｜車掌《しゃしょう》. The main verb is an action, so the line passes a quick read, but the relative clause ahead of the noun is still the gloss: a rack for putting luggage on, a man wearing a uniform.

The 番台 line costs more than the others. It is wrong on the facts — a 番台 sits at the boundary of the 男湯 and the 女湯, not above the entrance — and the sightline it spends a whole sentence establishing is never used again in the story. Later in the same story the same word carries its own weight without any help: ｜石鹸《せっけん》と｜桶《おけ》を、番台の｜下《した》から私に｜渡《わた》しただけだった。 The owner reaches under it and hands something over. That is what 番台 means, and it introduces the new word 桶 in the same breath.

```
✓ ｜祖母《そぼ》が｜壁《かべ》に｜釘《くぎ》を｜一本《いっぽん》｜打《う》って、そこに｜掛《か》けたものだ。
```

Nobody is told what a 釘 is. It gets driven into a wall and something gets hung on it, and the reader has the word.

Corollary for word choice: admit a new word only when it is the story's own subject matter, so it recurs without the prose working at it. ｜城《しろ》の｜鐘《かね》 repeats ｜鐘《かね》 36 times because it is about bells. If a draft has to reach to repeat a word, it is the wrong word.

Per-story new words go in that story's `new_words` block in `corpus.json`, **not** in `approved-words.json`, which stays a short global list of permanent allowances. Declaring is required rather than optional: `check.py`'s particle-splitting fallback accepts ｜部品《ぶひん》 as 部 + 品, so the unknown detector never sees compounds, and an undeclared new word gets no marking in the reader.

Leech words come from `vocab.weak_forms()` — kanji words tagged leech in Anki and above the known threshold. Reading one in context beats another card review. Use them where they fit; never force one.

## Drafting

**Draft a page at a time — four to five sentences — as continuous Japanese prose, with no English anywhere in the buffer. Split it to lines and write the translations afterwards.**

The old order was sentence by sentence: a Japanese line, its `>` line, the next Japanese line. In September 2026 four native-level evaluators read all eight stories in Japanese only, with English and furigana stripped and the repo unreachable, and returned the same verdict independently — English-designed, Japanese-rendered, 5.0 to 6.5 out of 10 on naturalness.

The mechanism is tense. Past-tense share across the corpus runs 62–90% against an authentic plain-form 56–66%, and the longest unbroken same-tense run reaches 33 sentences in ｜行《い》かなかった｜人《ひと》の｜地図《ちず》 and 23 in ｜城《しろ》の｜鐘《かね》 and ｜煙突《えんとつ》の｜煙《けむり》, against an authentic 11–15. Japanese narration moves between タ and ル inside a scene and the reader does not notice; the English past does not move, and **tense is the one thing an English sentence cannot leave open.** So a Japanese sentence written into a slot beside a finished English one has had タ or ル chosen for it before a word of Japanese exists. Written forward as prose, with nothing English beside it, the choice happens where it belongs — at the paragraph, against what came before it in Japanese.

Three of the eight — ｜時計《とけい》の｜音《おと》, ｜迷子《まいご》の｜手紙《てがみ》, ｜終電《しゅうでん》 — sit inside the authentic band on both figures. This is drift, not a floor the language imposes, which is why the fix is an order of operations and not a number.

**Gate 2 does not move.** The beat sheet stays in English. What it tests is whether a story exists at all, English tests that perfectly well, and the beat sheets are the best artifact this repo has produced. Nothing above touches them — the September 2026 craft revision enlarged what Gate 2 produces, and it left the language it is produced in exactly where it was. What is inverted is only the sentence-level drafting that comes after the gate.

One consequence worth naming: the `>` lines stop being the thing the story was written in and become a translation of it. That is why § The English has to stand alone now sits in § The revision pass rather than up here — checking derived English is a check, and checking the English a story was planned in was mostly a restatement of the plan.

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
- **But a line may hold more than one sentence, and the toolchain accepts it.** This was claimed to be rigid, and it was rigid only because this document said so. `build.py:89` attaches an `en` to whichever line was appended last, and `build.py:93` appends every line with `en: ""`, so a second sentence on a line is simply a line, and a line with no `>` after it is simply unglossed. `stats.py`'s `prose_sentences()` already splits lines into sentences of its own accord, so no rhythm measure depends on the coupling. `reader.js:825` renders an unglossed line as a plain `s` rather than `s has-en`, which is the intended no-translation path and not a fallback. Nothing breaks. The coupling stays the default because a reader tapping a sentence wants that sentence's English, not a paragraph of it — but when two short sentences belong to one breath, put them on one line and translate the pair.
- **One quoted turn per line, however many sentences it holds.** 「」 brackets a turn — everything one speaker says before anybody else speaks or the narration resumes — not a sentence. Sentences inside a turn are divided by 。 as usual, and the last one drops its 。 before the 」. This is the only place the one-sentence-per-line rule yields, and it has to: the alternative is a closing 」 in the middle of somebody still talking.
- **Relaxing the coupling does not relax the brackets.** The two rules look alike and are not: a line holding two narration sentences is a formatting choice with nothing riding on it, while a 「」 boundary is the story's only speaker attribution. § 「」 is the speaker attribution stands unchanged, and the permission above is not a licence to merge or split a turn. One turn, one line, still — and 21 turns already shipped wrongly split under a rule that was only about narration in the first place.
- Blank line separates pages. Aim for four to five sentences a page.
- **This format once became a style rule by accident.** The 1:1 coupling made long multi-clause sentences awkward to keep aligned, so the first five stories were written almost entirely in short declaratives: mean 17 characters, standard deviation 4.6, and three of the five contained no sentence over 30 characters at all. Vary length deliberately. The stdev floor exists to catch exactly this.
- **The coupling is not a reason to write short.** Write the long sentence and translate it as one long sentence. What the coupling really discourages is **subordination** — 連用形 chaining, relative clauses, ので / のに / ながら — and those are the level ladder's own constructions, so writing around it works against the ladder. `stats.py` reports `subordinate_share` for this; it is measured and not yet gated.

### 「」 is the speaker attribution

Most quoted lines carry no dialogue tag, so a reader has nothing but the brackets to go on: a new 「 means the speaker changed, or the same speaker stopped and started again. Splitting a continuous turn across several 「」 therefore _says_ something false, and there is no other cue to contradict it.

```
✗ 「あの鐘は、私が四十の時に作った」        ✓ 「あの鐘は、私が四十の時に作った。当時の王の命令だ。戦争のための鐘だった」
  「当時の王の命令だ。戦争のための鐘だった」
```

The ✗ column is two people. It is one man telling one story, and it shipped that way — the September 2026 audit found 21 turns split like this across six of the seven stories, produced by reading the one-sentence-per-line rule as though it outranked the brackets.

**But a beat is a real reason to open a second 「.** A speaker who stops, is not answered, and starts again is two turns, and the brackets are how that silence is written. The silence has to be on the page, though, and a bare line break is not enough to write it: a new 「」 on a new line reads as a new speaker by default. ｜終電《しゅうでん》 is the case that proved it. Almost nothing is attributed, and the cue the story runs on is that her reply is always shorter than the question that prompted it (her first line in each run is four to six characters) — the narration hands the reader that key outright, 彼女の返事はいつも短い。私の質問は、どうしても長くなる。 Merging her runs inverts that cue at the merge point. Leaving them split, with nothing between, left his 「お母さんは、もう向こうですか」 readable as her asking about **his** mother, and both blind readers of the September 2026 second read flagged the runs. The repair keeps the reply short and puts the pause in narration: an action beat or a 続けた inside the block (彼女は小さく頷いた。 / それから、窓の外を見たまま続けた。), with what she volunteers after the beat merged into one turn, since it answers nothing.

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
- **A Japanese name in a `>` line takes the marker form, and takes the Japanese order.** The translation sheet renders ruby, so ｜青山《あおやま》 ｜梓《あずさ》 shows the reader the reading the story is teaching. Romaji was the old habit and it carried the western pronunciation the kana exist to replace. Surname first, matching the Japanese it translates — `Azusa Aoyama` was right as romaji precisely because that is English order, and in kanji it becomes 梓 青山, which no Japanese text writes. Three exceptions, each because the marker earns nothing: a katakana name (クロ) has no reading to carry; a settled English place name stays English, so Tokyo rather than ｜東京《とうきょう》; and Ms. / Mrs. are not names, they are what 様 and さん already say.
- Keep the domain narrow. That is what produces recycling, and it is the only honest way to hit the repeated-word share floor.

## The revision pass

Six failure modes, each found the expensive way. Run this against every draft.

| Failure                            | Evidence                                                                                                                                                                                         | Check                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| Closing thesis sentence            | 4 of 5 stories, near-identical shape                                                                                                                                                             | Does the last page state what it means? Cut it.                             |
| Flat short declaratives            | mean 17 chars, stdev 4.6; 3 of 5 had nothing over 30                                                                                                                                             | Is every sentence one clause?                                               |
| Variance bought long-only          | ｜猫《ねこ》 +24%, ｜城《しろ》の｜鐘《かね》 +14% over brief                                                                                                                                    | Are the long sentences long from structure, or more nouns?                  |
| Circumlocution to dodge unknowns   | 一緒に暮らしている人 for ｜飼《か》い｜主《ぬし》                                                                                                                                                | Is a phrase working around a word rather than using one?                    |
| One turn split across several 「」 | 21 turns, six of seven stories, Sept 2026                                                                                                                                                        | `stats.py --turns`; does a 」 close mid-breath, with no beat?               |
| Predicate monotony                 | Top-three ending share 25.0–54.5% against an authentic plain-form 18.6–28.6%; ending 3-gram entropy 3.97–5.34 against an authentic 5.10–5.85, seven of eight stories below the authentic minimum | What is the longest unbroken same-tense run? `scripts/voice.py` reports it. |

### On the sixth row

Of the six, this is the one most easily bought rather than fixed, so two things are ruled out in advance.

**It is not a length problem, and it must not be attached to one.** `CALIBRATION.md`'s headline finding is the 1.34x sentence-length gap, and the temptation is to treat flat endings as another face of short sentences. Measured inside these eight stories, mean sentence length correlates with ending entropy at **−0.475** — weakly _negative_. The story with the longest sentences is the second flattest. They are independent axes, and bundling them is exactly how "variance bought long-only" comes back: a draft lengthened in the name of ending variety fixes neither. Fix the endings by changing what the predicates are, at whatever length the sentence already is.

**Do not reach for 体言止め, ようだ, かもしれない or だろうか.** An earlier draft of the September 2026 audit listed all four as missing from the corpus and recommended more of them. The claim did not survive a register-controlled re-measurement: it had been taken against a reference band that is 87% ですます調 while every story here is 100% plain form, and once register is held constant all four already run at or above authentic rates. 私 density is the same story, and worse for the claim — ours 18.7–34.7 per 100 narration sentences against ｜花《はな》をうめる at 45.1. We are not at the authentic rate, we are below it. Sprinkling any of them raises the entropy figure and changes nothing a reader would feel.

`voice.py` prints and gates nothing, like `--turns`. The number to look at is the longest same-tense run, because it is the one figure on the sheet you can also find by eye: read the narration and watch for the stretch where every sentence lands on the same ending. That stretch is the defect. The entropy figure only tells you it is there.

### The English has to stand alone

Read only the `>` lines, top to bottom, ignoring the Japanese. **It must be a short story worth reading.** Not a gloss track, not a sequence of captions. This is half of what actually gets read, and it is the cheapest strong check available.

This check used to sit up with the craft rules, before drafting, where it was very nearly circular: the English being read back was the English the story had been planned in, so it confirmed the plan and little else. Under § Drafting the English is derived from finished Japanese, which makes this a real check on a translation — and the first place a gloss track shows up, because English that reads as captions is usually reporting Japanese that was never prose.

## Metrics are floors, not targets

**Every threshold catches a specific failure this corpus actually produced. None is a target to optimise.** A story can meet all of them and still be inert; a story can miss one and still be the right story, in which case say so and ship it.

This clause is load-bearing rather than decorative: two of the six failures above were _caused_ by optimising a metric. Sentence variance was bought by writing long, and driving the unknown-word count to zero is what produced the circumlocutions.

### The reference band is not a floor either

```bash
python3 reference.py --compare    # our numbers beside authentic 児童文学
```

Every floor in `corpus.json` is calibrated from this project's own output, and a corpus measured against itself can be no better than its own best member — so `reference.py` reads the same structural axes off public-domain 児童文学 and reports a band beside ours.

**It gates nothing, and it must not become a gate.** "Real authors score 21.2" is a far more persuasive argument for chasing a number than "our lowest story scored 6.7" ever was, and writing to the band would buy the same variance the same dishonest way. `reference.py` writes no threshold, never touches `corpus.json`, and exits zero regardless.

**Two findings to carry while drafting, and they are independent of each other.**

The first: **this corpus writes short.** 8.9 Ichiran tokens per sentence against an authentic 12.0, a 1.34x gap, every story below its own bin on `pct_over_30`. Close it with a genuine second clause, never with more nouns — "variance bought long-only" is failure mode three in the revision pass above.

The second: **its predicates repeat.** That is failure mode six, added September 2026 off the native-evaluator reading. It is the newer of the two only because nobody had measured it: until then the length gap was the only structural finding on record, which is why this section said "the one finding" for as long as it did.

They do not share a cause and they do not share a fix. Within these eight stories, mean sentence length correlates with ending entropy at **−0.475**, weakly _negative_: writing longer has, if anything, gone with flatter endings here, and the longest-sentence story is the second flattest. Treat them as one problem and the draft gets lengthened in the name of variety, which buys neither. The revision pass is the check on both, and neither is a number.

`CALIBRATION.md` has the rest: the full band, the four ways to misread it, why `subordinate_share` is measured and not gated, and five recorded corrections.

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
2. `scripts/corpus.json` `stories[]` — entry with `level`, `brief`, `_premise` (the whole Gate 2 sheet), `new_words`, in reading order
3. `stories/stories-index.md` `## Summaries` — one bullet. Without it `index.py` warns and the card ships with no blurb and no kana reading; nothing else in the pipeline checks
4. `stories/stories-index.md` `## Afterwords` — one bullet, written at Gate 2

Then rebuild twice, because the pitch table is read from the built data rather than from the source:

```bash
python3 rebuild.py
PITCH_PYTHON=/path/to/venv/bin/python3 python3 pitch.py --build
python3 rebuild.py
```

Two things now catch you if you skip or mis-order it, and neither existed at first. `rebuild.py` lists `pitch-table.json` as an input to every data file, so the second rebuild can no longer find nothing to do and report success. And `harness.py` compares the built payload against the current table directly — `pitch-table/every-word-the-table-can-answer-carries-its-guide` — rather than measuring the payload against itself, which is what a stale build passes.

That second one is the assertion that matters, because the failure mode here is silent by construction: a story with no accent guides looks exactly like a story whose words the rules declined to answer.

## Modes

- **new** — the default, all four steps above.
- **revise `<slug>`** — edit the `.txt` in place. The brief already exists; re-run `stats.py --strict` against it.
- **version `<slug>`** — archive the current text to `stories/versions/<slug>.vN.txt`, add `vN` to that entry's `versions[]`, then write the new current. **`rebuild.py` does not build the archive**, and this document said for a while that it did. `rebuild.py:200-202` skips every archived target unless `--versions` is passed, on purpose: an archive re-rendered with today's engine "preserves the story and not the reading it shipped with" (`rebuild.py:172-174`). Nothing is lost by that, because A/B comparison never needed a built archive — `stats.py --diff <old>.txt <new>.txt` reads the two source files and prints both columns.

## Committing

Two lanes.

**A story-only change** — a new or revised `.txt`, its `corpus.json` entry, its `stories-index.md` bullets, and the rebuilt files under `docs/` — goes straight to `main` once `stats.py --strict` and `check.py` pass. Those are the review: they are stricter about a story than reading the generated HTML would be.

**Anything touching the engine** — `scripts/*.py`, `reader.html`, `reader.css`, `reader.js` — goes on a branch, gets reviewed, and is merged. A change that touches both takes the engine lane.

Rebuilding after an engine change rewrites every story, so keep that commit separate from the change that caused it.

## Never

- Do not add to `approved-words.json` without asking. It is deliberately a short list.
- Do not edit `docs/index.html`. It is generated.
- Do not write the `brief` block programmatically. Edit `corpus.json` by hand.
