#!/usr/bin/env python3
"""Write docs/sw.js, the service worker that keeps the stories readable offline.

The file list is everything in the published tree rather than a list kept by
hand, so a new story, a new archived version or a new icon is offline the
moment it is built. The version is a hash of those files' bytes, which is the
only thing that makes a browser fetch the tree again: sw.js has to change
whenever anything it caches does, or a device goes on reading the old text.

index.py calls this as its last act, because index.html is the last file a
rebuild writes and the hash has to cover it.
"""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "sw.js"


def files(out_dir):
    # Dotfiles are .nojekyll and editor litter; sw.js cannot cache itself.
    return sorted(
        p.relative_to(out_dir).as_posix()
        for p in out_dir.rglob("*")
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(out_dir).parts)
        and p.relative_to(out_dir).as_posix() != "sw.js"
    )


def version(out_dir, names):
    h = hashlib.sha256()
    for name in names:
        h.update(name.encode("utf-8") + b"\0")
        h.update((out_dir / name).read_bytes())
    return h.hexdigest()[:12]


def render(out_dir):
    names = files(out_dir)
    return TEMPLATE.read_text(encoding="utf-8") \
        .replace("__VERSION__", version(out_dir, names)) \
        .replace("__FILES__", json.dumps(names, indent=2))


def write(out_dir):
    out = out_dir / "sw.js"
    out.write_text(render(out_dir), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "docs"))
