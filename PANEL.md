# The panel

Rob is the only reader, and every story is meant to be read fresh. Gate 2 used to hand him the whole English sheet to approve — climax, afterword, beats — which spent the story before he opened it. The panel replaces that read. **Rob is the reader and the taste signal; the panel is the gate.**

This is a change of who reads, not of what is checked. Every rule in AUTHORING.md § Gate 2 and § Craft still applies, still has no script behind it, and is still enforced by something reading the sheet and sending it back. What changes is that the something is no longer Rob. The repo already ran this experiment: the September 2026 audit's evaluators named the real ending of six of eight stories unprompted, and the 09-19 second blind read found the corpus's clearest tell, circumlocution around the obligatory noun. Independent readers with the rubric and no stake in the draft find what the author cannot. Rob's ratings and notes find what they cannot.

## Rules of the panel

- **Independence.** Each role is a fresh agent. It gets the artifact and the inputs listed for it below, never the author's reasoning, earlier drafts, or another role's opinion unless the role is defined as reading it. An agent that has watched the story being argued for will agree with it.
- **The author never grades its own work.** The English read-back was already "very nearly circular" when the author did it (AUTHORING § The English has to stand alone). The author runs the mechanical checks and revises. Every judgement below belongs to someone else.
- **Cite the rule.** A send-back names the AUTHORING rule it applies and the beat or line it applies to. "Feels flat" is not a verdict.
- **Blind means blind to the path too.** A blind role is given its input as a file with a neutral name (`a.txt`, `b.txt`) in a directory with a neutral name, and the prompt never carries the title or the slug. The first audit put the story's romaji name in every path, and one locator used it to guess the country.
- **A pass is a floor.** The panel does not rank stories and its verdicts are prose. Nothing here becomes a number to optimise (CALIBRATION.md, § The reference band; AUTHORING § Metrics are floors, not targets).

## Who sees what

Rob sees the **card** and nothing the card does not hold. Three levels, set by him per story, default 0:

| Level | Rob sees                                                                           |
| ----- | ---------------------------------------------------------------------------------- |
| 0     | the card only — the default                                                        |
| 1     | the card and the `## Summaries` blurb, which is the ceiling for any message to him |
| 2     | the card and the full sheet, as Gate 2 used to work                                |

He says so when he wants more, usually at Gate 1. Nothing in `brief.py` carries it and nothing should: it is a preference about Rob, not a property of the story.

**The `## Summaries` blurb states the situation and the want, never the turn.** It is what the contents page shows him before he picks a story, so a blurb that names the reveal spoils the story on the shelf. Write it as the premise sentence of the sheet, not the afterword in short.

## Gate 2, in order

1. **Author** writes the sheet (AUTHORING § Gate 2), in English, in a subagent.
2. **Guesser**, **locator** and **transplanter** run in parallel, each on its own cut of the sheet. They do not see one another.
3. **Sheet critic** reads the sheet, all three findings, the corpus, and Rob's notes, and returns a verdict.
4. Send back, revise, repeat from 2 (below). A pass records the sheet as `_premise` on the `corpus.json` entry.
5. The orchestrator posts the **card** and drafting begins. The card is not a stop unless it carries a question.

### Guesser

**Gets:** title, level, register, PREMISE, WANT, NEED. **Never gets:** CLIMAX, BEATS, AFTERWORD, SHAPE, any other story.

Asked: _Write three different endings for this story, one scene each, most likely first. Then say in a sentence what you expect it to be about._

This is the spoiler-free form of "do not write the obvious climax" (AUTHORING § Gate 2). A story composed front to back arrives at the ending it was always going to arrive at, and an agent that has only the premise will find that ending. If one of the three matches the sheet's CLIMAX in mechanism — not in detail — the climax is the obvious one, and the sheet is rebuilt from a new climax, not patched.

**The guesser also reports whether it was handed the answer.** Asked last: _Did anything you were given state, or all but state, how the story ends?_ The first audit showed why. On three of four sheets the input partly gave the ending away, mostly through the NEED line, and a guess made against a leaked input proves nothing in either direction. A yes or a partly voids the test and sends the sheet back at once to have the leaking line rewritten, and the critic does not weigh a guess made against it. The fix belongs to the author: NEED is the flaw and never its resolution (AUTHORING § Gate 2, want and need).

### Locator

**Gets:** CLIMAX, WANT, NEED and BEATS, with the CULTURE block removed, every parenthesised Japanese term removed, and every character's name (taken from VOICES) replaced by a letter. **Never gets:** the title, PREMISE, CULTURE, or anything else.

Asked: _Where and when is this set? What in it tells you? Could it be set anywhere else, and what would have to change?_

This is the test of whether the sheet's Japan is in its causes or only in its labels. If the locator says "a small town, anywhere" or places it somewhere else, the culture is a coat of paint on the plot. The Japanese terms in the beats are what the author wrote to make the culture structural, so taking them out is how you find out whether anything structural was underneath. A story whose sheet survives the stripping with Japan still legible has put the culture in what the characters want and cannot say.

### Transplanter

**Gets:** the full sheet. **Never gets:** the guesses or the locator's finding.

Asked: _Move this story to a small town in the American Midwest, present day, changing only what has to change. For each beat say SURVIVES, CHANGES or BREAKS, and why. Then: does the climax survive the move? Does the beat where the need is faced? In the moved version, would the character say the need aloud? Which specific pressure in the CULTURE block is the thing that is lost?_

The three words are defined in the prompt, because the first audit showed the transplanter will otherwise pick its own:

- **SURVIVES.** Works as written, with trivial changes.
- **CHANGES.** Names, foods, objects and places change. The cause and the cost of the beat do not.
- **BREAKS.** The cause or the cost of the beat is gone, **or the move can keep it only by inventing an equivalent institution, custom or obligation** that the new place does not have.

**The climax and the turn have to break, and the need has to stay unsaid.** The first audit used "breaks" to mean only "no longer exists", and zero of about 35 beats across four sheets did, the two strongest-culture stories among them. That is the wrong bar. The cause of a story (a debt, a pride, a promise) rarely disappears in another country. What Japan supplies is the institution that makes it binding and the pressure that keeps it unsaid, and that is what a move has to invent to keep the beat. A beat that merely changes is the cost of any move and proves nothing. So the climax and the turn each have to be BREAKS in this sense, and if the character would simply say the need aloud in the moved version, a Japanese pressure was not what held it, whatever the sheet names. Either failure sends the sheet back as garnish. The transplanter is also asked to name the PRESSURE that is lost, which checks that the pressure written on the sheet is the one doing the work.

### Sheet critic

**Gets:** the sheet, the guesser's endings, the locator's placement, the transplanter's report; AUTHORING.md § Gate 2, § The CULTURE block, § Craft, § Register; `AXES.md`; the `_note` of every story in `corpus.json`, for the reader's quoted reviews; the output of `python3 reviews.py`. **Never gets:** the author's notes, or the drafting conversation. On a repeat round it also gets the list of what it sent back last time, and nothing else from that round.

Asked, each answered PASS or SEND BACK with the rule, the beat, and one line of reason:

- **Climax.** A specific scene rather than a representative one? Something in it that the premise did not predict — and did any guess land on it? A cost the character actually pays?
- **Afterword.** A reading of this climax, or a statement of intent? Could it be written off the climax alone?
- **Want and need.** Want visible and sayable in one clause? Need distinct from it? Does the character have to face the need to get the want, and most often give the want up to get it?
- **Shape.** Declared, boundaries marked, and a story that fits it rather than a form being filled.
- **Every beat.** Yes-but or no-and. Write the honest join to the next beat: そして / それから is a list of events, だから / しかし is causality, and an all-だから sheet is the straight line the rule exists to break.
- **Plants.** Name each plant and its payoff. For each plant, what is it doing at the time, as a habit, scenery or an offhand line, that is not planting? A plant a reader would file as a plant is spent.
- **Characters.** Name every character who appears and say what each is for and where each leaves the story. One used for a beat and then dropped, rather than resolved, is a SEND BACK. No AUTHORING rule states this yet; cite this line.
- **Resolution choices.** Name the choice the ending turns on and the earlier beat that makes this character make it. A stock gesture with no such beat is a SEND BACK. Check the beats after the climax as well as the climax: say what each one adds and whether the sheet could end sooner.
- **Ending.** Does the last page state what it means? A claim-ending is permitted only if it corrects a fact about a person (the guard recorded on 廊下の鏡) and never concludes.
- **Dialogue.** Per scene: a secret each, misdirection, conflicting agendas.
- **The CULTURE block.** Each field against AUTHORING § The CULTURE block:
  - PRACTICE written as a procedure a Japanese reader would check step by step, and correct. Anything stated that you cannot confirm, flag; do not wave it through.
  - PRESSURE named in Japanese, and the need unspeakable because of it. Would an American character say the need in one line?
  - VOICES distinct for every speaker, right for their age, region and era, and every name right for its bearer's era and for the others'.
  - SEASON a subject and not a marker.
  - ABSENT accounted for. Name anything a Japanese writer on this subject would include that is neither in the sheet nor cut on purpose.
  - CARRIED honest: the practice's vocabulary is either inside the known set or paid for by a named `new_words` budget.
  - Beats carry the Japanese term for every culturally load-bearing noun and verb, rather than a paraphrase.
  - **The locator and transplanter findings are binding.** A locator that cannot place the story in Japan, a transplanter whose report has the climax or the turn short of BREAKS, or a need the character would simply say aloud in the moved version, is a SEND BACK for garnish whatever the rest of the block looks like.
- **Inside the culture, at the level of fact.** AUTHORING § Craft, "Write from inside the culture": speech, fact, absence. Check any institution, object or procedure the story leans on before it becomes the story's centre.
- **Against the corpus.** Fill the six axes of `AXES.md` for this sheet from its vocabulary (domain, object, relationship, climax, ending, and practice with pressure), then compare with the table by identity: an axis is shared with a story when the values match, and practice-and-pressure when both do. Name the nearest story on each axis and the value shared. **Three or more axes shared with one story is a send-back.** Do not judge similarity by reading the other stories' prose, and propose a new value by name where none fits rather than using OTHER. Apply the tie-breaks in `AXES.md` where two values both fit, and give PRESSURE the least weight, since it is the axis the two tabulators disagreed on most. Also check anything Rob's notes name as a tic.
- **Against Rob.** List every note from `reviews.py` that is a constraint on this brief and say whether the sheet respects it. A departure from a default parameter has to say which review it responds to.

The critic's overall word is PASS, SEND BACK, or DROP. Three SEND BACK rounds on the sheet is a DROP.

## The draft, in order

1. **Author** drafts in Japanese a page at a time (AUTHORING § Drafting), writes the English afterwards, and runs `stats.py --turns --strict`, `check.py` and `voice.py`. These are the mechanical checks and pass or fail as they always have.
2. **Japanese-only readers**, two independent agents, on the Japanese alone.
3. **English-only reader**, one agent, on the `>` lines alone.
4. **Reconciler** compares what the readers took from the story with the AFTERWORD.
5. Send back or pass, and the card.

Build the two inputs like this, in a UTF-8 locale or `sed` matches bytes and strips nothing:

```bash
export LC_ALL=C.UTF-8
grep -v '^>' stories/<slug>.txt | sed -E 's/｜([^《]*)《[^》]*》/\1/g' > ja.txt
grep    '^>' stories/<slug>.txt | sed -E 's/^> ?//; s/｜([^《]*)《([^》]*)》/\1（\2）/g' > en.txt
```

The two commands differ on purpose. A Japanese name in a `>` line takes the marker form (AUTHORING § Writing rules), and stripping it to bare kanji leaves the English reader a character it has no way to read. `en.txt` keeps the reading beside it, 梓（あずさ）, which is what the translation sheet shows.

### Japanese-only readers

**Get:** `ja.txt`. Furigana and English stripped, the repo unreachable, no corpus, no sheet, no brief. The September protocol exactly, which is the point: it is the only read that sees the story as a Japanese reader would, and it is the only one that returned a verdict nobody expected.

Asked:

1. Which sentence reads as the ending? Quote it.
2. What is the story doing, in two sentences?
3. How natural is the Japanese, out of ten? Quote the three lines that sound most like a translation.
4. Name the speaker of every 「」 line. List the ones you could not name, and every pair of adjacent turns you would give to the same speaker with no silence between them.
5. What is the longest stretch where every narration sentence ends the same way?
6. Is there anything a Japanese reader would not accept as fact: an era, an institution, a procedure?
7. Describe how each speaker talks: first person, how they address the others, politeness, endings. Do they sound like different people? Is anyone's speech wrong for their age, gender, region or era?
8. What in this could only have happened in Japan? Quote it. What reads as an English idea in Japanese, or as written for a reader who does not live there?

Two readers is the minimum, so that a disagreement is visible. Four is better for a first story in a new register.

### English-only reader

**Gets:** `en.txt`. Asked: _Is this a short story worth reading? What happens, in three sentences? Where does it read as captions rather than prose? Does it end on an image or on a claim?_ This is AUTHORING § The English has to stand alone, done by someone who did not write it.

Also asked, because the first calibration found a reader's complaints that no question here reached (CALIBRATION.md § The panel against six stories, 2026-10-25):

- _Where does it slow down, and what pulls you to the next page? What is the hook by the end of the first page?_
- _Does it lose energy after the climax? Say where, and whether what follows earns its length._
- _Which characters appear, do something, and leave without a resolution?_
- _Which choice does the ending turn on, and does the text give its reason? Does it read as a stock gesture rather than this character's choice?_

No AUTHORING rule states these four yet. A send-back on one cites this list.

It is told that names appear in script with their reading in parentheses, as the translation sheet shows them, and are not to be counted as untranslated text. **Any other Japanese script in the English is a finding**, and the reader is asked to say where. The first audit found a few such words, two characters each, in the English lines of two of six stories, which a native editor would want to know about whether or not they were meant.

### Reconciler

**Gets:** the AFTERWORD, and the PRACTICE and PRESSURE lines, from the sheet; the three readers' two-sentence readings, the ending line each one picked, and each Japanese-only reader's answer to question 8. **Never gets:** the story, or the beats.

Asked: _Does what the readers took from the story match the afterword: yes, partly, or no? Did they pick the intended ending, and if not what did they pick? Did the readers' "only in Japan" answers name the practice or the pressure, or something else?_ Then, without reference to the readers: _Read the afterword as prose. Quote nothing; name each stock phrase, each sentence that would fit any story, and each place it restates the climax in abstract nouns._ The afterword is the last page Rob reads and no other role reads it as writing. The panel shares the author's model family and may not see the author's own tics, so this check is untested and Rob's note on the afterword is what calibrates it.

Both failures are real and mean different things. If the readers disagree with the afterword, the story is not delivering it or the afterword is wrong, and the author has to say which. If the readers name something other than the practice and the pressure, the culture the draft delivers is not the culture the sheet planned, and one of the two has to move.

## Send-backs and escalation

- **Gate 2:** three rounds, then DROP.
- **Draft:** two rounds on the readers' findings, then DROP.
- A dropped story never reaches Rob. The next card carries one line: how many were dropped, and the rule that dropped them, by name.
- **Rob is asked only when** the panel splits on something only taste can settle; a rule collides with one of his own notes; or the story needs a Gate 1 parameter moved. The question has to be answerable without the plot, as an axis rather than a scene (quieter or more comic; closed or left open). A question that cannot be put that way is a DROP.

## The card

```
CARD  <title>   L<level>  <register>  <pages>p   shape: <name>
Domain      <noun phrase, at the Summaries ceiling>
Gate 2      passed on round <n> of 3; sent back for: <rule names only>
Draft       <n> Japanese-only reads, ending found <where intended | elsewhere>, naturalness <range>
Nearest     <existing story> on <axis>; differs by <axis-level difference, no plot>
Culture     <practice> run on <pressure>; transplant breaks the turn ✓; locator placed it ✓; readers named it ✓
Your notes  responds to <title ★n>: held | not held
Mechanical  stats --strict ✓  check.py ✓  turns ✓
Dropped     <n>: <rule names>
Needs you   none | <the question>
```

Naturalness is a range and it gates nothing. Nothing on the card is a scene, a name, a line or a turn.

## Containment

Rob follows sessions in the app, so anything that goes through the main thread is on his screen. The panel does not make a story spoiler-free if the story is printed beside it.

- **Authoring and the whole panel run in subagents, or in a child session.** The orchestrating thread posts the card and nothing else. It does not `Read` a story in flight, print `--turns` or `voice.py`, or quote a line. A subagent's final report is not shown to Rob; whether the app shows a subagent's inner tool calls, or a child session's transcript, is not something this repo controls, so keep the story's text out of any call you can.
- **Commit subjects name the title and the domain, never the want or the turn.** The existing history spoils: "a white number under a scratched sticker", "footprints on the evening round". A subject is `Add <title>, a <domain> story`.
- **The final message after a story is the card.** Not a summary of the story, not "what I did."
- `_premise`, the Afterwords bullet and the story file itself are in files Rob does not open. That holds only while nothing recites them.

## Calibration

The panel is the same model family as the author, so it has correlated blind spots, and it has no taste to disagree with. Rob's ratings are the only check on it.

- At ship time write `_gate` on the `corpus.json` entry, prose and no numbers: rounds, what was sent back and for which rule, where the readers found the ending. It sits beside `_premise`, `_feature` and `_note`, and nothing parses it.
- When Rob rates a story, read his note against `_gate`. **A note naming something the panel passed is a hole in this file**, so add the rule to the role that should have caught it. That is how his feedback compounds without his reading anything in advance.
- After every five rated stories gated this way, set the panel's verdicts beside the ratings in CALIBRATION.md. n is tiny and will stay tiny for a long time. Read the notes, not the mean, as `reviews.py` already says.

## Existing stories

Stories that shipped before the CULTURE block are audited at **the draft stage only**: the Japanese-only pair, the English-only reader and the reconciler. Their sheets are not re-gated. Five have no stored sheet, five more predate the sheet format, and the first audit showed the sheet-stage roles measure the plan and not what Rob reads, so a retrofit of the sheet stage would mostly grade documents that no longer drive anything. The reconciler runs without PRACTICE and PRESSURE and compares the readers with each other and with the afterword.

## What the panel cannot do

It cannot tell whether a story will move Rob. It can tell that the climax is not the one a stranger would guess, that the ending does not explain itself, that a Japanese reader would not trip on the facts, and that the story does what its afterword says. "Unexpected to a model" is not "unexpected to Rob."

**Nor can it certify the culture is right.** The locator and transplanter find culture that is decoration, and the readers find English in Japanese dress, which are the failures the corpus actually has. An agent's account of a custom, though, can be confidently wrong in a way that reads fine, and a regional or era detail that is slightly off is the hardest thing for it to see. Two things narrow this and neither closes it. The author has to be able to write the PRACTICE as a procedure from a source, not from recall, and the critic flags what it cannot confirm. And a Japanese-only reader who says a procedure is wrong has found a fact error, which is a send-back whatever else passed. Rob's notes remain the only ground truth, and when one says a detail is wrong, add the check that would have caught it to the role that passed it.
