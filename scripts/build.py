#!/usr/bin/env python3
"""Build a hover-furigana reader from a story text file.

Three output forms, one story pipeline: --linked for the published tree (a small
shell beside a shared engine and its own data file), --split for a scratch
directory while working on the engine, and the default inline single file for
docs/versions/, where an archived draft has to keep its engine frozen.

Story format: `# Title` on the first line, then pages separated by blank lines,
one sentence per line. A line starting with `> ` is an English translation of
the sentence above it — kept inline rather than in a parallel file so the two
cannot drift apart. Translations are optional, per sentence.

Every page is re-checked against the known-word set at build time, so a story
that drifted out of vocabulary range fails loudly instead of shipping.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import check
import furigana
import ichiran
import indexmd
import pitch
import vocab

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "reader.html"
READER_CSS = HERE / "reader.css"
READER_JS = HERE / "reader.js"
SYNC_JS = HERE / "sync.js"
OVERRIDES = {
    k: v
    for k, v in json.loads((HERE / "readings-overrides.json").read_text(encoding="utf-8")).items()
    if not k.startswith("_")
}
applied = Counter()


CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))


def corpus_new_words(slug):
    """Per-story teaching words declared in the manifest.

    A version build (`tokei-no-oto.v1`) inherits the current story's list, so an
    archived draft is marked the same way and the A/B comparison is like for like.
    """
    base = slug.split(".")[0]
    for story in CORPUS["stories"]:
        if story["slug"] == base:
            return set(story.get("new_words", {}))
    return set()


def strip_ruby(line):
    """Plain text plus the readings the author annotated, by offset.

    The story source is authored, not found, text: whoever wrote the line knew
    which reading was meant. Re-deriving it from the bare kanji is what produced
    31 wrong furigana in the 2026-09-07 audit (下 as もと, 中 as ちゅう, 空 as から),
    and `readings-overrides.json` patches those by global surface replacement,
    which cannot be right for a genuinely ambiguous token. An annotation is
    per-occurrence, so it can be.
    """
    return furigana.parse(line)


def parse_story(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    title = path.stem
    if lines and lines[0].startswith("#"):
        title = strip_ruby(lines.pop(0).lstrip("# ").strip())[0]
    pages, current = [], []
    for line in lines:
        line = line.strip()
        if line.startswith(">"):
            if current:
                # A translation names Japanese people and places, and it annotates
                # them with the same ｜漢字《かな》 the story uses — Rob reads kana,
                # not romaji. So it ships as HTML, exactly as the afterword does,
                # and by the same escaper: the reader renders it and never sees
                # the markup. The plain form for speech is recovered at the panel.
                current[-1]["en"] = indexmd.ruby_html(line.lstrip("> ").strip())
            continue
        if line:
            ja, authored = strip_ruby(line)
            current.append({"ja": ja, "en": "", "ruby": authored})
        elif current:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return title, pages


KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヺー]*$")


def authored_reading(authored, surface):
    """The author's reading for this token, if the annotation covers it.

    An annotation marks a kanji run (｜行《い》った), but Ichiran's token is the
    inflected whole (行った). So an exact match is not enough: where the annotated
    run is a prefix and the rest of the token is okurigana, the reading is the
    annotation plus that tail.
    """
    if not authored:
        return None
    marked, reading = authored
    if marked == surface:
        return reading
    if surface.startswith(marked) and KANA_ONLY.match(surface[len(marked):]):
        return reading + surface[len(marked):]
    return None


def to_token(tok, known, weak, approved, authored=None, accents=None):
    if isinstance(tok, ichiran.Raw):
        return {"t": tok.text}
    word = tok.word
    surface = tok.text
    if not ichiran.has_kanji(surface):
        return {"t": surface}
    kana = word.kana
    # Two ways Ichiran's reading describes something other than the text printed
    # here, and they are answered differently. See ichiran.offsets.Placed.
    #
    # `part_of` - this is one component of a compound, and the compound carries
    # both the printed surface and the reading of all of it. Align that and take
    # the slice; nothing has to be cut down or guessed.
    part_of = tok.part_of
    # `canonical` - a surface carried into a gap, where there is no longer text to
    # align against and the reading on hand covers more than is written. Rare
    # enough that the eight stories contain none, but reachable.
    lemma = tok.canonical
    # An author annotation wins over both Ichiran and the global override table:
    # it is per-occurrence, so it is the only one of the three that can be right
    # about a token whose reading genuinely varies by context.
    reading = authored_reading(authored, surface)
    if reading:
        if reading != kana:
            applied[f"{surface} {kana}→{reading} (authored)"] += 1
        kana, lemma, part_of = reading, None, ()
    elif surface in OVERRIDES and OVERRIDES[surface] != kana:
        applied[f"{surface} {kana}→{OVERRIDES[surface]}"] += 1
        kana, lemma, part_of = OVERRIDES[surface], None, ()
    # Both of those state a reading for the text that is actually here, so they
    # settle the question and neither branch below is wanted. Only Ichiran's own
    # reading needs one, because only it describes something other than this span.
    if part_of:
        whole, whole_kana, at = part_of
        cut = furigana.portion(furigana.align(whole, whole_kana), at, at + len(surface))
        if cut is None:
            return {"t": surface}  # no honest reading for this span; say nothing
        pairs, kana = cut
    elif lemma:
        cut = furigana.truncate(furigana.align(lemma, kana), surface)
        if cut is None:
            return {"t": surface}
        pairs, kana = cut
    else:
        pairs = furigana.align(surface, kana)
    entry = {
        "t": surface,
        "r": pairs,
        "k": kana,
        "g": word.gloss(),
    }
    hit = next((f for f in (surface, *word.dictionary_forms) if f in weak), None)
    if hit:
        entry["w"] = hit  # the dictionary form, so the index lists 焦る not 焦って
    new = next((f for f in (surface, *word.dictionary_forms) if f in approved), None)
    if new:
        entry["n"] = new  # approved but not yet known — reader shows its reading
    if not check.is_known(word, known):
        entry["u"] = 1
    if accents is not None:
        hit = accents.key(surface, kana)
        if hit is not None:
            entry["p"] = hit
    return entry


class Pitch:
    """Accent entries for a story, deduped into one table the tokens index into.

    Inlining the triple on every token measured 12% on docs/data/<slug>.js against
    7-9% for a table plus an index, and the corpus repeats itself heavily enough
    that the gap is real: the stories run 175-328 distinct entries against 700-odd
    marked tokens.

    A surface absent from the table is not an error. pitch.py declines to guess,
    so a miss here is a word whose accent nobody has asserted, and the reader
    simply shows no guide for it.
    """

    # Only what the reader cannot derive. The mora count and the pattern name
    # both fall out of the accent and the kana, and the kana is already on the
    # token — so a surface the engine vouched for ships as one integer, and the
    # 辞書形 triple rides along only when there is no surface accent to show.
    # Deduping then collapses nearly every surface entry onto the same handful of
    # records, which is why the table costs almost nothing.

    def __init__(self):
        self.table = pitch.load()
        self.entries = []
        self.index = {}
        self.hits = 0
        self.lemma_only = 0

    def key(self, surface, kana):
        raw = self.table.get(pitch.key(surface, kana))
        if not raw:
            return None
        entry = pitch.shipped(raw)
        if entry is None:
            return None
        token = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        if token not in self.index:
            self.index[token] = len(self.entries)
            self.entries.append(entry)
        if "a" in entry:
            self.hits += 1
        else:
            self.lemma_only += 1
        return self.index[token]


def blob(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def render(title, data):
    """One self-contained file: engine, styling and story in a single document.

    This is what docs/versions/ ships, and what the harness renders its fixtures
    from. It is no longer the form the live stories take — see render_shell —
    but an archived draft has to keep rendering the way it did the day it was
    published, which means carrying its own engine rather than linking whatever
    the current one has become.

    The placeholders sit alone on their own lines, so replacing the line
    reproduces the original template byte for byte. The JS is inlined before
    __STORY_DATA__ is substituted, because the engine is what contains that
    placeholder.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__READER_CSS__\n", READER_CSS.read_text(encoding="utf-8"))
    html = html.replace("__READER_JS__\n", READER_JS.read_text(encoding="utf-8"))
    html = html.replace("__TITLE__", title)
    return html.replace('"__STORY_DATA__"', blob(data))


def render_shell(title, data_href, css_href="reader.css", js_href="reader.js",
                 sync_href="sync.js"):
    """The linked form: a ~2KB document that pulls in the engine and one story.

    Classic <link> and <script src> only. fetch() and type="module" are both
    blocked on file://, and these are still opened from the filesystem during
    story work; classic scripts also run in document order, which is what
    guarantees window.STORY exists before the engine reads it.

    The story's 目次 href is not in here. It rides in the data as DATA.toc and
    is applied at runtime, so one shell serves every story in a tree.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace(
        "    <style>\n__READER_CSS__\n    </style>\n",
        f'    <link rel="stylesheet" href="{css_href}" />\n',
    )
    # sync.js first, and classic rather than deferred, because reader.js reads
    # window.Sync during its own bootstrap. Document order is the guarantee —
    # the same one that already puts the story data ahead of the engine.
    html = html.replace(
        "    <script>\n__READER_JS__\n    </script>\n",
        f'    <script src="{sync_href}"></script>\n'
        f'    <script src="{data_href}"></script>\n'
        f'    <script src="{js_href}"></script>\n',
    )
    return html.replace("__TITLE__", title)


def write_engine(out_dir):
    """The two shared assets, written once for a whole published tree.

    The substitution lives here and nowhere else. rebuild.py imports this rather
    than re-implementing the one-line replace, for the same reason the harness
    imports render() — a second copy of a build contract is a contract that can
    drift without anything failing.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reader.css").write_text(READER_CSS.read_text(encoding="utf-8"), encoding="utf-8")
    # The engine reads the same name either way; only where it comes from differs.
    (out_dir / "reader.js").write_text(
        READER_JS.read_text(encoding="utf-8").replace('"__STORY_DATA__"', "window.STORY"),
        encoding="utf-8",
    )
    # sync.js is written only here, never inlined by render(). That is what
    # keeps docs/versions/ frozen AND sync-free: an archived draft carries its
    # own engine and writes progress under its own slug, and pushing a draft's
    # position to the gist would put a slug on every device that only one of
    # them has a story for.
    (out_dir / "sync.js").write_text(SYNC_JS.read_text(encoding="utf-8"), encoding="utf-8")


def write_data(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("window.STORY = " + blob(data) + ";\n", encoding="utf-8")


def render_split(title, data, outdir):
    """Loose form in a scratch directory, for working on the engine.

    Same shape the published tree uses, with the flat filenames a one-story
    directory can afford. Editing reader.css or reader.js and reloading is the
    whole dev loop; nothing here needs a rebuild.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(render_shell(title, "data.js"), encoding="utf-8")
    write_engine(outdir)
    write_data(outdir / "data.js", data)
    return outdir / "index.html"


def render_linked(title, data, out, slug):
    """A story in the published tree: shell beside the shared engine, data apart.

    The data is the 200KB half and changes only when the story or its vocabulary
    marking does; the shell is 2KB and changes only with the template. Splitting
    them is what lets an engine edit rebuild nothing at all.
    """
    write_engine(out.parent)
    write_data(out.parent / "data" / f"{slug}.js", data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_shell(title, f"data/{slug}.js"), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--allow-unknown", action="store_true",
                    help="deprecated; unknown words no longer block a build")
    ap.add_argument("--strict", action="store_true",
                    help="fail the build on any word outside the known set")
    ap.add_argument("--split", type=Path, metavar="DIR",
                    help="write the loose engine+data form to DIR for UI work, not a story")
    # The live tree's form. Inline stays the default because docs/versions/ is
    # built through the same script and has to keep carrying its own engine.
    ap.add_argument("--linked", action="store_true",
                    help="write a shell beside the shared engine and data/<slug>.js")
    # Where the contents page sits relative to the file being written. Whoever
    # chooses the output path owns this: rebuild.py puts archived versions in
    # docs/versions/ and passes ../index.html for them. The reader must not
    # re-infer it from the slug — a dot in a story name is not a layout.
    ap.add_argument("--toc", default="index.html", metavar="HREF",
                    help="href of the contents page from this reader (default: index.html)")
    args = ap.parse_args()

    title, pages = parse_story(args.story)
    known = check.load()
    weak = vocab.weak_forms()
    # Per-story teaching words get the same marking as the global approved list.
    # They have to be declared: the particle-splitting fallback in check.py reads
    # 部品 as 部 + 品, so the unknown detector never sees them.
    approved = vocab.approved_forms() | corpus_new_words(args.story.stem)
    accents = Pitch()

    # One segmentation pass over the whole story, then sliced back apart by
    # offset — Ichiran costs seconds per request regardless of input size.
    spans, cursor, doc_ruby = [], 0, {}
    for page in pages:
        page_spans = []
        for sentence in page:
            page_spans.append((cursor, cursor + len(sentence["ja"])))
            for off, pair in sentence.get("ruby", {}).items():
                doc_ruby[cursor + off] = pair
            cursor += len(sentence["ja"]) + 1
        spans.append(page_spans)
    joined = "\n".join(s["ja"] for page in pages for s in page)

    aligned = ichiran.align(joined)

    def slice_span(start, end):
        """Tokens overlapping [start, end), with punctuation kept.

        A raw chunk straddles the newline that joins two sentences ("。\n「"),
        so raws are intersected with the span rather than assigned whole to one
        side — otherwise sentences lose their trailing 。 or leading 「.
        """
        out = []
        for tok in aligned:
            if tok.end <= start or tok.start >= end:
                continue
            if isinstance(tok, ichiran.Raw):
                text = joined[max(tok.start, start) : min(tok.end, end)]
                text = text.strip("\n")
                if text:
                    out.append({"t": text})
            elif start <= tok.start < end:
                out.append(
                    to_token(tok, known, weak, approved, doc_ruby.get(tok.start), accents)
                )
        return out

    built = [
        [
            {"toks": slice_span(start, end), "en": sentence["en"]}
            for (start, end), sentence in zip(page_spans, page)
        ]
        for page_spans, page in zip(spans, pages)
    ]

    unknown = sorted({t["t"] for p in built for s in p for t in s["toks"] if t.get("u")})
    # A report, not a gate. Blocking on a single unknown word enforced something
    # stricter than the goal: a handful of new words per story, marked and
    # derivable from context, is the design, and pushing the count to zero is
    # what produced the circumlocutions (一緒に暮らしている人 for 飼い主).
    # --strict restores the old behaviour.
    if unknown:
        if args.strict:
            sys.exit(f"Outside the known-word set: {', '.join(unknown)}")
        print(f"  note: {len(unknown)} outside the known set: {', '.join(unknown)}", file=sys.stderr)

    # Full-spoiler note, folded away until the last page. Restores the handhold
    # the 2026-09-08 pass removed without putting the theme statement back into
    # the Japanese.
    index_md = args.story.parent / "stories-index.md"
    afterword = indexmd.afterwords(index_md).get(title, "") if index_md.exists() else ""
    # The title's own reading, which the contents card has always shown and the
    # reader dropped. `title` is the ruby-stripped surface, because the <h1> is
    # set by textContent and no markup may reach it, so the reading travels
    # beside it as plain text rather than inside it as markup. Only four of the
    # eight story files annotate their own # line; stories-index.md annotates
    # all eight, so it is the source here as it is for the card.
    title_kana = (
        indexmd.summaries(index_md).get(title, ("", ""))[0] if index_md.exists() else ""
    )

    data = {
        "title": title,
        "titleKana": title_kana,
        # Read tracking keys on this. The title is not stable enough — a version
        # build shares its parent's title, which would merge their progress.
        "slug": args.story.stem,
        "toc": args.toc,
        "afterword": afterword,
        "pages": built,
        "pitch": accents.entries,
        "stats": {
            "words": sum(1 for p in built for s in p for t in s["toks"] if t.get("r")),
            "translated": sum(1 for p in built for s in p if s["en"]),
            "units": sum(len(p) for p in built),
            "weak": sorted({t["w"] for p in built for s in p for t in s["toks"] if t.get("w")}),
            "approved": sorted({t["n"] for p in built for s in p for t in s["toks"] if t.get("n")}),
            "unknown": unknown,
            "knownVocab": len(vocab.known_forms()[0]),
        },
    }

    if args.split:
        out = render_split(title, data, args.split)
    elif args.linked:
        out = render_linked(
            title, data, args.out or args.story.with_suffix(".html"), args.story.stem
        )
    else:
        out = args.out or args.story.with_suffix(".html")
        out.write_text(render(title, data), encoding="utf-8")
    print(
        f"{out}\n  {len(built)} pages · {data['stats']['words']} kanji words · "
        f"{accents.hits} accented ({len(accents.entries)} distinct) · "
        f"{len(data['stats']['weak'])} weak · "
        f"{len(data['stats']['approved'])} approved-new · {len(unknown)} unknown · "
        f"{data['stats']['translated']}/{data['stats']['units']} translated"
    )
    for fix, n in sorted(applied.items()):
        print(f"  reading override: {fix} ({n}x)")


if __name__ == "__main__":
    main()
