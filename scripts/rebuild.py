#!/usr/bin/env python3
"""Rebuild every story in the manifest, then the contents page.

Replaces the hand-run per-story recipe, which does not scale and had two ways to
go wrong: globbing sorts alphabetically rather than in reading order, and
index.py must run last because it reads the built readers, so rebuilding a story
afterwards leaves the contents page stale with nothing to flag it. Both are
settled here.

Only stale outputs rebuild, and a live story is three of them: the shared engine
in docs/, its own data/<slug>.js, and a 2KB shell linking the two. They have
different inputs, so a CSS change now rewrites two files and re-segments nothing,
while a story edit rewrites one data file. Combined with the segmentation cache,
a no-op rebuild of the whole corpus is effectively free.

docs/versions/ stays out of all of this: archived drafts are self-contained and
frozen, and only --versions reaches them.
"""

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

import build
import indexmd
import stats

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))

# Sources and output are separate trees so that GitHub Pages serves docs/ and
# nothing else: publishing the whole flat directory would put the .txt sources
# and the engine on the public site alongside the readers.
SRC = HERE.parent / "stories"
OUT = HERE.parent / "docs"


def build_modules(root="build"):
    """Every local module build.py actually reaches, transitively.

    This used to be glob("*.py"), which swept in ten scripts the build never
    imports — stats, reviews, reference, progress, brief, have, icons, index,
    rebuild, readings — so editing any of them marked every data file stale and
    charged a full Ichiran re-segmentation for a change build.py cannot see. That
    is the same defect the reader/CSS split was made to fix, arriving by a
    different route, and a hand-kept list would drift the first time build.py
    grew an import. Walking the imports cannot drift.

    This covers the Python half only. The JSON inputs below are still listed by
    hand, so adding a new one to pitch.py or check.py invalidates nothing until
    someone adds it there too — the same silent under-invalidation, one file type
    over. Reading them off the AST would need every path literal to be reachable
    statically, which is a bigger claim than this walker makes.

    A module that will not parse is a hard error rather than a skip. Swallowing
    it would drop that module and its whole import subtree from the dependency
    set, so a story would report "up to date" against a stale data file — which
    is the failure this function exists to prevent, arriving through its own
    error handling.
    """
    local = {p.stem for p in HERE.glob("*.py")}
    seen, stack = set(), [root]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        tree = ast.parse((HERE / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                stack += [a.name for a in node.names if a.name in local]
            elif isinstance(node, ast.ImportFrom) and node.module in local:
                stack.append(node.module)
    return {HERE / f"{name}.py" for name in seen}


def targets(src_dir, out_dir):
    """(source, output, toc, archived) for every story and version, in order.

    toc is the contents page's href from the reader being written, and this is
    the only place that knows it: versions go one directory down, so their 目次
    link has to climb back out. The reader used to infer that from a dot in the
    slug, which read a filename convention as a layout.

    archived decides both the output form and whether the target is rebuilt at
    all: a live story is a shell linking the shared engine, an archived draft is
    one self-contained file and is left alone unless --versions asks for it.
    """
    out = []
    for story in CORPUS["stories"]:
        slug = story["slug"]
        out.append((src_dir / f"{slug}.txt", out_dir / f"{slug}.html", "index.html", False))
        for v in story.get("versions", []):
            src = src_dir / "versions" / f"{slug}.{v}.txt"
            if src.exists():
                out.append((src, out_dir / "versions" / f"{slug}.{v}.html", "../index.html", True))
    return out


# A live story is three outputs with three different inputs, and keeping them
# apart is the whole point of the linked form: the expensive one is the only one
# most edits touch.
#
# Comparing only the story source was wrong in a way nothing flagged — editing
# reader.js, or an afterword in stories-index.md, left every story reporting "up
# to date" with a stale engine baked in. The lists below still have to cover
# everything, they are just no longer one list: putting reader.css in the set
# that decides a re-segmentation is what made a CSS tweak cost an Ichiran run
# and a live Anki.
#
# Generated files are deliberately absent: .deck-words-cache.json, pos-table.json
# and .segcache/ are all rewritten on a schedule of their own and would force
# rebuilds that change nothing.
DATA_DEPS = sorted(build_modules()) + [
    HERE / "corpus.json",
    HERE / "approved-words.json",
    HERE / "readings-overrides.json",
    # build.py calls pitch.load(), so the table is a real input to every data
    # file. Without it here the documented rebuild -> pitch.py --build -> rebuild
    # sequence silently does nothing on its last step, and the story ships with
    # whatever accents the table happened to hold before it was regenerated.
    # It never showed because every run that regenerated the table had also
    # edited a .py, which made all eight stale by another route.
    HERE / "pitch-table.json",
]
SHELL_DEPS = [HERE / "reader.html", HERE / "build.py"]
ENGINE_DEPS = [HERE / "reader.css", HERE / "reader.js", HERE / "sync.js", HERE / "build.py"]
# An archived version is one self-contained file, so every input still collapses
# into a single set for it.
VERSION_DEPS = DATA_DEPS + sorted(HERE.glob("reader.*"))


def stale(dst, deps):
    """True when any build input is newer than the output derived from it.

    One input stays invisible to this: vocab.py reads ankimorphs.db live, so a
    card maturing past the 21-day threshold changes what the build marks with no
    mtime anywhere to notice. --all remains the escape hatch for that.
    """
    if not dst.exists():
        return True
    out = dst.stat().st_mtime
    return any(d.stat().st_mtime > out for d in deps if d.exists())


def afterword_changed(data, index_md):
    """True when this story's afterword differs from the one built into it.

    stories-index.md holds two sections and a story consumes one of them, so
    mtime cannot tell an afterword rewrite from a blurb typo — and it used to
    charge the same full re-segmentation for both, about a minute a story with
    Anki and Ichiran live. The 2026-09-16 pass that cut the file to its two
    machine-read sections was itself a pure-prose edit and re-segmented all
    eight. build.py stores the afterword it used, so the honest comparison was
    already sitting in the output.
    """
    if not data.exists() or not index_md.exists():
        return True
    built = stats.data_file(data)
    return indexmd.afterwords(index_md).get(built["title"], "") != built["afterword"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild even if up to date")
    ap.add_argument("--src", type=Path, default=SRC, help="story .txt sources")
    ap.add_argument("--out", type=Path, default=OUT, help="built readers (the published tree)")
    ap.add_argument("--strict", action="store_true", help="pass --strict to build.py")
    # Archived drafts are frozen on purpose: an archive that re-renders with
    # today's engine preserves the story and not the reading it shipped with.
    # They carry their own engine, so nothing reaches them unless asked.
    ap.add_argument("--versions", action="store_true",
                    help="also rebuild docs/versions/, which is otherwise left frozen")
    args = ap.parse_args()

    # The afterword comes from here via indexmd.py, so editing one has to make
    # the story it belongs to stale — by content, not by mtime. See
    # afterword_changed; a version build still compares the file, because an
    # archived draft carries its afterword inline and stats cannot read it back.
    index_md = args.src / "stories-index.md"

    # The shared engine, written before anything links to it. build.write_engine
    # owns the __STORY_DATA__ substitution; re-implementing the one-line replace
    # here would be a second copy of a build contract that could drift silently.
    engine = [args.out / n for n in ("reader.js", "reader.css", "sync.js")]
    if args.all or any(stale(p, ENGINE_DEPS) for p in engine):
        build.write_engine(args.out)
        print("  engine      reader.css · reader.js · sync.js", flush=True)
    else:
        print("  up to date  reader.css · reader.js · sync.js", flush=True)

    built = 0
    for src, dst, toc, archived in targets(args.src, args.out):
        if not src.exists():
            print(f"missing source: {src}", file=sys.stderr)
            continue
        if archived:
            if not args.versions:
                continue
            if not args.all and not stale(dst, [src, *VERSION_DEPS, index_md]):
                print(f"  up to date  {src.name}", flush=True)
                continue
        else:
            data = args.out / "data" / f"{dst.stem}.js"
            if not args.all and not stale(data, [src, *DATA_DEPS]) \
                    and not afterword_changed(data, index_md):
                # The data is current, so the expensive half is skipped; the
                # shell is 5KB of template and gets rewritten on its own terms.
                if stale(dst, SHELL_DEPS):
                    # From the data rather than from the shell being replaced:
                    # the shell may not exist yet, and the slug is not the title.
                    title = stats.data_file(data)["title"]
                    dst.write_text(
                        build.render_shell(title, f"data/{dst.stem}.js"), encoding="utf-8"
                    )
                    print(f"  shell       {dst.name}", flush=True)
                else:
                    # Flushed, so these interleave correctly with the subprocess
                    # output rather than all arriving after it.
                    print(f"  up to date  {src.name}", flush=True)
                continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(HERE / "build.py"), str(src), "-o", str(dst), "--toc", toc]
        if not archived:
            cmd.append("--linked")
        if args.strict:
            cmd.append("--strict")
        if subprocess.run(cmd, cwd=HERE).returncode:
            sys.exit(f"build failed: {src.name}")
        built += 1

    # Always last: it reads the built readers, so any story rebuilt after this
    # point would leave the contents page silently stale.
    cmd = [sys.executable, str(HERE / "index.py"), str(args.out), "--src", str(args.src)]
    if subprocess.run(cmd, cwd=HERE).returncode:
        sys.exit("index failed")
    print(f"\n{built} rebuilt")


if __name__ == "__main__":
    main()
