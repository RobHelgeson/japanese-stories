#!/usr/bin/env python3
"""Which words Rob had to ask the reader about, ranked.

A tap that lights a word in the reader is a request for its reading, and a
double tap that opens the sheet is a request for its meaning. The reader counts
both per dictionary form and keeps them in the progress gist beside the reviews,
one record per device so that two devices' counts add rather than overwrite.
This is the only reader of that half: it sums the devices, joins each word to
the stories it was asked about in, and marks the ones Anki already calls 苦手 or
the corpus approved as 新出.

  python3 peeks.py                  # via gh, the same gist the phone writes
  python3 peeks.py --file exp.json  # a 書き出し export instead, no network
  python3 peeks.py --story shuden   # one story only
  python3 peeks.py --json           # the ranked records, for a tool

A word asked about in several stories is a word the known set counts as known
and reading does not, and it is what the next story's brief and story-vocab
should reach for first. A single peek is noise — a mis-tap, or a check on a
reading that was right — which is why the default floor is two.
"""

import argparse
import json
import sys
from pathlib import Path

import reviews

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))


def envelope(doc):
    if isinstance(doc, dict) and isinstance(doc.get("peeks"), dict):
        return doc["peeks"]
    return {}


def tally(peeks, only=None):
    """lemma → {r, m, stories: {slug: n}}, summed over every device."""
    out = {}
    for slug, devices in peeks.items():
        if only and slug != only or not isinstance(devices, dict):
            continue
        for rec in devices.values():
            words = rec.get("w") if isinstance(rec, dict) else None
            if not isinstance(words, dict):
                continue
            for lemma, c in words.items():
                if not isinstance(c, dict):
                    continue
                r, m = int(c.get("r") or 0), int(c.get("m") or 0)
                if r + m <= 0:
                    continue
                row = out.setdefault(lemma, {"lemma": lemma, "r": 0, "m": 0, "stories": {}})
                row["r"] += r
                row["m"] += m
                row["stories"][slug] = row["stories"].get(slug, 0) + r + m
    return out


def marks():
    """苦手 and 新出 sets, or empty ones when Anki is not running.

    The ranking is the point and it needs neither; the marks only say which of
    the ranked words Anki already knows to be a problem.
    """
    import vocab
    approved = set(vocab.approved_forms())
    try:
        weak = vocab.weak_forms()
    except Exception:
        print("(Anki not reachable — 苦手 marks omitted)", file=sys.stderr)
        weak = set()
    return weak, approved


def ranked(rows, floor):
    keep = [r for r in rows.values() if r["r"] + r["m"] >= floor]
    # Breadth first: a word asked about in three stories outranks one asked
    # about five times on a single page, because the second is one bad sentence.
    keep.sort(key=lambda r: (-len(r["stories"]), -(r["r"] + r["m"]), -r["m"], r["lemma"]))
    return keep


def report(rows, total_words):
    order = {e["slug"]: n for n, e in enumerate(CORPUS["stories"], 1)}
    print(f"見た読み — {total_words} words peeked, {len(rows)} shown")
    if not rows:
        return
    print(f"\n  {'word':<10}{'読':>4}{'意':>4}  {'mark':<5} stories")
    for r in rows:
        mark = r.get("mark") or ""
        where = ", ".join(f"{s}×{n}" if n > 1 else s
                          for s, n in sorted(r["stories"].items(), key=lambda kv: order.get(kv[0], 99)))
        # Full-width lemmas are two columns each, so pad by display width.
        pad = 10 - sum(2 if ord(ch) > 0x2E80 else 1 for ch in r["lemma"])
        print(f"  {r['lemma']}{' ' * max(1, pad)}{r['r']:>4}{r['m']:>4}  {mark:<5} {where}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", type=Path, help="a 書き出し export, instead of the gist")
    ap.add_argument("--story", help="one slug only")
    ap.add_argument("--min", type=int, default=2, help="drop words peeked fewer times (default 2)")
    ap.add_argument("--no-marks", action="store_true", help="skip the Anki lookup")
    ap.add_argument("--json", action="store_true", help="the ranked records, unformatted")
    args = ap.parse_args()

    doc = json.loads(args.file.read_text(encoding="utf-8")) if args.file else reviews.from_gist()
    rows = tally(envelope(doc), args.story)
    out = ranked(rows, args.min)
    if not args.no_marks and out:
        weak, approved = marks()
        for r in out:
            r["mark"] = "苦手" if r["lemma"] in weak else "新出" if r["lemma"] in approved else ""
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        report(out, len(rows))


if __name__ == "__main__":
    main()
