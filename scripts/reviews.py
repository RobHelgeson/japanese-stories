#!/usr/bin/env python3
"""What Rob thought of each story, read back for the next brief.

Ratings and notes are written on the contents page and travel in the same
secret gist as reading progress. This is the only reader of that half: it joins
the reviews to `corpus.json`, so a rating arrives next to the level, register
and length it was a verdict on, and prints the aggregates a brief is actually
chosen from.

  python3 reviews.py                 # via gh, the same gist the phone writes
  python3 reviews.py --file exp.json # a 書き出し export instead, no network
  python3 reviews.py --json          # the joined records, for a tool

A rating is one number and every warning about one number applies. Four stars
on a folktale is not evidence that folktales are better; the note underneath it
is where the reason lives, which is why the notes are printed in full and the
averages are printed with their counts.
"""

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import stats

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
FILE = "japanese-stories-progress.json"


def gh(path):
    """One `gh api` call, parsed. gh already holds a token with the gist scope,
    so this needs no secret of its own and nothing to keep in sync with the
    phone."""
    if not shutil.which("gh"):
        sys.exit("gh not found — install it, or pass --file with a 書き出し export")
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"gh api {path} failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def from_gist():
    hit = next((g for g in gh("/gists?per_page=100") if FILE in (g.get("files") or {})), None)
    if not hit:
        sys.exit(f"No gist holding {FILE}. Connect a device on the contents page first.")
    # The list endpoint omits file contents, so the gist has to be fetched by id.
    full = gh(f"/gists/{hit['id']}")
    return json.loads(full["files"][FILE]["content"])


def envelope(doc):
    """Accept the gist envelope or a bare progress map, the way import does."""
    if not isinstance(doc, dict):
        return {}
    if isinstance(doc.get("reviews"), dict):
        return doc["reviews"]
    return {}


def pages(slug, entry):
    built = HERE.parent / "docs" / f"{slug}.html"
    if built.exists():
        return stats.read(built)["pages"]
    return (entry.get("brief") or {}).get("pages")


def join(reviews):
    default_reg = (CORPUS.get("defaults") or {}).get("register")
    rows = []
    for n, entry in enumerate(CORPUS["stories"], 1):
        slug = entry["slug"]
        rec = reviews.get(slug) if isinstance(reviews.get(slug), dict) else {}
        raw = rec.get("stars")
        stars = int(raw) if isinstance(raw, (int, float)) and 1 <= raw <= 5 else None
        note = rec.get("note") if isinstance(rec.get("note"), str) else ""
        rows.append({
            "n": n,
            "slug": slug,
            "title": entry["title"],
            "level": entry.get("level"),
            "register": (entry.get("brief") or {}).get("register") or default_reg,
            "pages": pages(slug, entry),
            "stars": stars,
            "note": note.strip(),
        })
    return rows


def group(rows, key):
    """Mean rating per value of `key`, with the count that produced it."""
    buckets = {}
    for r in rows:
        if r["stars"] is None:
            continue
        buckets.setdefault(r[key], []).append(r["stars"])
    return {k: (sum(v) / len(v), len(v)) for k, v in sorted(buckets.items(), key=lambda kv: str(kv[0]))}


def report(rows):
    rated = [r for r in rows if r["stars"] is not None]
    print(f"評価 — {len(rows)} stories, {len(rated)} rated")
    if rated:
        print(f"  overall ★{sum(r['stars'] for r in rated) / len(rated):.1f}")
    print()
    print(f"  {'#':>2}  {'slug':<26}{'lvl':<5}{'register':<16}{'pg':>4}  評価")
    for r in rows:
        mark = ("★" * r["stars"] + "☆" * (5 - r["stars"])) if r["stars"] else "—"
        note = "  ✎" if r["note"] else ""
        print(f"  {r['n']:>2}  {r['slug']:<26}{str(r['level'] or '?'):<5}"
              f"{str(r['register'] or '?'):<16}{str(r['pages'] or '?'):>4}  {mark}{note}")

    for label, key in (("level", "level"), ("register", "register")):
        g = group(rows, key)
        if not g:
            continue
        cells = "   ".join(f"{k} ★{avg:.1f} ({n})" for k, (avg, n) in g.items())
        print(f"\n  by {label:<9}{cells}")

    notes = [r for r in rows if r["note"]]
    if notes:
        print("\n感想")
        for r in notes:
            head = f"★{r['stars']}" if r["stars"] else "未評価"
            print(f"\n  {r['title']} — {head}")
            for line in r["note"].splitlines():
                for wrapped in textwrap.wrap(line, 74) or [""]:
                    print(f"    {wrapped}")
    unrated = [r["slug"] for r in rows if r["stars"] is None]
    if unrated:
        print(f"\n  未評価  {', '.join(unrated)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", type=Path, help="a 書き出し export, instead of the gist")
    ap.add_argument("--json", action="store_true", help="the joined records, unformatted")
    args = ap.parse_args()

    doc = json.loads(args.file.read_text(encoding="utf-8")) if args.file else from_gist()
    rows = join(envelope(doc))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        report(rows)


if __name__ == "__main__":
    main()
