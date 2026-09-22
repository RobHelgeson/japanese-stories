#!/usr/bin/env python3
"""Resolve a story brief and print what the run will actually use.

The skill used to take no parameters at all: level, length and subject were
settled in conversation and hand-written into corpus.json afterwards, so nothing
was declared before drafting and nothing was checkable after. That is why two
stories could run 24% and 14% over brief without anything noticing.

Resolution order is explicit argument, then corpus.json's `defaults` block. Every
parameter has a default, so a bare `python3 brief.py` is a complete brief.

This prints; it does not write. `--json` emits the block to paste into the
story's corpus.json entry — by hand, because that file is hand-maintained and
carries comment keys and one-line arrays that json.dump would reformat.
"""

import argparse
import json
import unicodedata
from pathlib import Path

import stats

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
D = CORPUS["defaults"]
B = CORPUS["budgets"]
RULE = "─" * 66

LEVELS = [k for k in CORPUS["levels"] if not k.startswith("_")]
REGISTERS = [k for k in CORPUS["registers"] if not k.startswith("_")]


def _pad(s, n):
    """Left-justify by display width, not code points — half this table is CJK."""
    s = str(s)
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    return s + " " * max(1, n - w)


def resolve(args):
    """The brief, plus where each value came from."""
    src = {}

    def take(name, given, default):
        src[name] = "explicit" if given is not None else "default"
        return default if given is None else given

    level = take("level", args.level, D["level"])
    pages = take("pages", args.pages, D["pages"])
    register = take("register", args.register, D["register"])
    page_slack = take("page_slack", args.page_slack, None)
    tokens = pages * D["tokens_per_page"]

    def rate(name, given, per100):
        if given is not None:
            src[name] = "explicit"
            return given
        src[name] = "derived"
        return round(tokens * per100 / 100)

    new_words = rate("new_words", args.new_words, B["new_words_per_100_tokens"])
    leech_seeds = rate("leech_seeds", args.leech_seeds, B["leech_seeds_per_100_tokens"])

    repeats = take("repeats", args.repeats, B["min_repeated_share"])
    focus = [c.strip() for c in (args.grammar_focus or "").split(",") if c.strip()]
    src["grammar_focus"] = "explicit" if focus else "default"

    dialogue = None
    if args.dialogue:
        parts = [p.strip() for p in args.dialogue.split(",")]
        dialogue = {"pct": int(parts[0]), "untagged": "untagged" in parts[1:]}
    src["dialogue"] = "explicit" if dialogue else "default"
    src["topic"] = "explicit" if args.topic else "unset"

    return {
        "level": level,
        "pages": pages,
        "page_slack": page_slack,
        "tokens": tokens,
        "register": register,
        "new_words": new_words,
        "leech_seeds": leech_seeds,
        "min_occurrences": max(2, round(tokens / 150)),
        "repeats": repeats,
        "grammar_focus": focus,
        "dialogue": dialogue,
        "topic": args.topic,
    }, src


def validate(b):
    """Reject a brief the rest of the toolchain could not honour."""
    bad = []
    if str(b["level"]) not in LEVELS:
        bad.append(f"level {b['level']} is not a rung ({LEVELS[0]}-{LEVELS[-1]})")
    if b["page_slack"] is not None and b["page_slack"] < 0:
        bad.append(f"page slack {b['page_slack']} is negative; it is a ± width in pages")
    if b["register"] not in REGISTERS:
        bad.append(f"register '{b['register']}' unknown; have {', '.join(REGISTERS)}")
    unknown = [c for c in b["grammar_focus"] if c not in stats.GRAMMAR_PATTERNS]
    if unknown:
        bad.append(f"grammar focus not a measured construction: {', '.join(unknown)}")
    return bad


def leech_pool():
    """Size of the weak-word pool, or None when Anki is not reachable."""
    try:
        import vocab

        return len(vocab.weak_forms())
    except Exception:
        return None


def show(b, src):
    lo, hi, tol_label = stats.page_bounds(b["pages"], b["page_slack"])
    pool = leech_pool()
    spec = CORPUS["levels"][str(b["level"])]

    rows = [
        ("level", b["level"], src["level"], spec["name"]),
        ("pages", f"{b['pages']} ±{tol_label}", src["pages"], f"{lo}-{hi} pages"),
        ("tokens", f"~{b['tokens']}", "derived", f"{b['pages']} × {D['tokens_per_page']}"),
        ("register", b["register"], src["register"],
         CORPUS["registers"][b["register"]].split(":")[0]),
        ("new words", b["new_words"], src["new_words"],
         f"{B['new_words_per_100_tokens']} / 100 tokens"),
        ("  min occurrences", b["min_occurrences"], "derived",
         f"max(2, {b['tokens']}/150)"),
        ("leech seeds", b["leech_seeds"], src["leech_seeds"],
         f"{B['leech_seeds_per_100_tokens']} / 100 tokens"
         + (f"  (pool: {pool})" if pool else "  (pool: Anki unreachable)")),
        ("repeats", f"≥{b['repeats']:.0%}", src["repeats"], "repeated-word share"),
        ("grammar focus", ", ".join(b["grammar_focus"]) or "—", src["grammar_focus"],
         "level ladder decides" if not b["grammar_focus"] else "must all be present"),
        ("dialogue",
         "—" if not b["dialogue"] else
         f"{b['dialogue']['pct']}%" + (" untagged" if b["dialogue"]["untagged"] else ""),
         src["dialogue"], "unconstrained" if not b["dialogue"] else "±10"),
        ("topic", b["topic"] or "—", src["topic"],
         "" if b["topic"] else "pick a domain the corpus has not used"),
    ]

    print(f"\nResolved brief\n{RULE}")
    for name, value, source, note in rows:
        tag = source.upper() if source == "explicit" else source
        print(f"{_pad(name, 18)}{_pad(value, 22)}{_pad(tag, 10)}{note}".rstrip())
    print(RULE)


def block(b):
    """The `brief` object for the story's corpus.json entry."""
    out = {"pages": b["pages"], "register": b["register"], "new_words": b["new_words"],
           "leech_seeds": b["leech_seeds"]}
    if b["page_slack"] is not None:
        out["page_slack"] = b["page_slack"]
    if b["grammar_focus"]:
        out["grammar_focus"] = b["grammar_focus"]
    if b["dialogue"]:
        out["dialogue"] = b["dialogue"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--level", type=int)
    ap.add_argument("--pages", type=int)
    ap.add_argument("--register")
    ap.add_argument("--page-slack", type=int, dest="page_slack",
                    help="allow ±N pages instead of the default ±page_tolerance")
    ap.add_argument("--new-words", type=int, dest="new_words")
    ap.add_argument("--leech-seeds", type=int, dest="leech_seeds")
    ap.add_argument("--repeats", type=float, help="repeated-word share floor, 0-1")
    ap.add_argument("--grammar-focus", dest="grammar_focus",
                    help="comma-separated construction names, as in corpus.json levels")
    ap.add_argument("--dialogue", help="PCT or PCT,untagged")
    ap.add_argument("--topic")
    ap.add_argument("--json", action="store_true", help="emit the brief block only")
    args = ap.parse_args()

    b, src = resolve(args)
    bad = validate(b)
    if bad:
        raise SystemExit("\n".join(f"brief: {m}" for m in bad))

    if args.json:
        print(json.dumps(block(b), ensure_ascii=False, indent=2))
        return

    show(b, src)
    print("Proceed, or adjust anything?")


if __name__ == "__main__":
    main()
