#!/usr/bin/env python3
"""Rebuild every story in the manifest, then the contents page.

Replaces the hand-run per-story recipe, which does not scale and had two ways to
go wrong: globbing sorts alphabetically rather than in reading order, and
index.py must run last because it reads the built readers, so rebuilding a story
afterwards leaves the contents page stale with nothing to flag it. Both are
settled here.

Only stale stories rebuild. Combined with the segmentation cache, a no-op
rebuild of the whole corpus is effectively free.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))

# Sources and output are separate trees so that GitHub Pages serves docs/ and
# nothing else: publishing the whole flat directory would put the .txt sources
# and the engine on the public site alongside the readers.
SRC = HERE.parent / "stories"
OUT = HERE.parent / "docs"


def targets(src_dir, out_dir):
    """(source, output, toc) for every current story and archived version, in order.

    toc is the contents page's href from the reader being written, and this is
    the only place that knows it: versions go one directory down, so their 目次
    link has to climb back out. The reader used to infer that from a dot in the
    slug, which read a filename convention as a layout.
    """
    out = []
    for story in CORPUS["stories"]:
        slug = story["slug"]
        out.append((src_dir / f"{slug}.txt", out_dir / f"{slug}.html", "index.html"))
        for v in story.get("versions", []):
            src = src_dir / "versions" / f"{slug}.{v}.txt"
            if src.exists():
                out.append((src, out_dir / "versions" / f"{slug}.{v}.html", "../index.html"))
    return out


# Everything the output is derived from. Comparing only the story source was
# wrong in a way nothing flagged: editing reader.js, or an afterword in
# stories-index.md, left every story reporting "up to date" with a stale engine
# baked in, and the fix was to remember --all. Adding the 目次 link to the
# header is the recorded instance — all five had to be rebuilt by hand.
#
# Generated files are deliberately absent: .deck-words-cache.json, pos-table.json
# and .segcache/ are all rewritten on a schedule of their own and would force
# rebuilds that change nothing.
DEPS = sorted(HERE.glob("*.py")) + sorted(HERE.glob("reader.*")) + [
    HERE / "corpus.json",
    HERE / "approved-words.json",
    HERE / "readings-overrides.json",
]


def stale(src, dst, extra=()):
    """True when any build input is newer than the built reader.

    One input stays invisible to this: vocab.py reads ankimorphs.db live, so a
    card maturing past the 21-day threshold changes what the build marks with no
    mtime anywhere to notice. --all remains the escape hatch for that.
    """
    if not dst.exists():
        return True
    out = dst.stat().st_mtime
    return any(d.stat().st_mtime > out for d in (src, *DEPS, *extra) if d.exists())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild even if up to date")
    ap.add_argument("--src", type=Path, default=SRC, help="story .txt sources")
    ap.add_argument("--out", type=Path, default=OUT, help="built readers (the published tree)")
    ap.add_argument("--strict", action="store_true", help="pass --strict to build.py")
    args = ap.parse_args()

    # The afterword comes from here via indexmd.py, so editing one has to make
    # the story it belongs to stale.
    index_md = (args.src / "stories-index.md",)

    built = 0
    for src, dst, toc in targets(args.src, args.out):
        if not src.exists():
            print(f"missing source: {src}", file=sys.stderr)
            continue
        if not args.all and not stale(src, dst, index_md):
            # Flushed, so these interleave correctly with the subprocess output
            # rather than all arriving after it.
            print(f"  up to date  {src.name}", flush=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(HERE / "build.py"), str(src), "-o", str(dst), "--toc", toc]
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
