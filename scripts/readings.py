#!/usr/bin/env python3
"""List every distinct surface→reading pair in built readers, for eyeballing.

Ichiran picks one parse; when a word is ambiguous (空 そら vs から, 表 おもて vs
ひょう) it can pick the wrong one and the reader will show a wrong furigana with
no warning. Nothing detects that automatically — this just makes it scannable.
"""

import sys
from collections import defaultdict

import stats
import json, re
from pathlib import Path


def pairs(path):
    d = json.loads(stats.ROW.search(Path(path).read_text(encoding="utf-8")).group(1))
    out = defaultdict(lambda: defaultdict(int))
    for page in d["pages"]:
        for sentence in page:
            for t in sentence["toks"]:
                if t.get("r"):
                    out[t["t"]][t["k"]] += 1
    return out


if __name__ == "__main__":
    merged = defaultdict(lambda: defaultdict(int))
    for p in sys.argv[1:]:
        for surface, kanas in pairs(p).items():
            for k, n in kanas.items():
                merged[surface][k] += n
    for surface in sorted(merged, key=lambda s: (-len(merged[s]), s)):
        kanas = merged[surface]
        flag = "  <-- MULTIPLE" if len(kanas) > 1 else ""
        print(f"{surface}\t" + "  ".join(f"{k}({n})" for k, n in kanas.items()) + flag)
