#!/usr/bin/env python3
"""Snapshot the progress gist, and put a snapshot back.

The gist's own revision history is the everyday undo, and correcting one record
by hand in the gist editor is what it was chosen for. This is for the other
case: taking a known-good copy before something is going to churn the store —
a device test that swipes every story to its last page — and putting that copy
back afterwards.

  python3 progress.py                       # save, to ~/Documents/Code/.japanese-stories-backups
  python3 progress.py --restore <file>      # put that snapshot back
  python3 progress.py --restore <file> -n   # print what it would write, change nothing

**A restore is not a paste.** Two things stand in the way and this handles both:

Every record's `at` is bumped to now, because the merge rule gives the later
stamp the record and a device that read while the snapshot sat on disk holds
newer stamps than the file does. Pasting the file into the gist editor unchanged
restores nothing — the next device to sync merges its own newer records back
over it and the restore undoes itself. `doneAt` is bumped for the same reason:
it is the only thing that can take a 読了 away.

And a slug the gist holds but the snapshot does not gets a tombstone rather than
being dropped, because an absent key merges to whatever the other side still
has. That is the same dated, page-less record 消去 writes, and it is what lets a
deletion travel at all.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

FILE = "japanese-stories-progress.json"
DESC = "japanese-stories reading progress"
BACKUPS = Path.home() / "Documents/Code/.japanese-stories-backups"


def gh(path, method=None, body=None):
    if not shutil.which("gh"):
        sys.exit("gh not found — it holds the token with the gist scope this needs")
    cmd = ["gh", "api", path]
    if method:
        cmd += ["-X", method]
    if body is not None:
        cmd += ["--input", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         input=json.dumps(body) if body is not None else None)
    if out.returncode:
        sys.exit(f"gh api {path} failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def find():
    hit = next((g for g in gh("/gists?per_page=100") if FILE in (g.get("files") or {})), None)
    if not hit:
        sys.exit(f"No gist holding {FILE}. Connect a device on the contents page first.")
    return hit["id"]


def fetch(gid):
    full = gh(f"/gists/{gid}")
    doc = json.loads(full["files"][FILE]["content"])
    return doc, full["history"][0]


def maps(doc):
    """The two halves, whatever shape the file is in."""
    if not isinstance(doc, dict):
        return {}, {}
    prog = doc.get("progress") if isinstance(doc.get("progress"), dict) else {}
    revs = doc.get("reviews") if isinstance(doc.get("reviews"), dict) else {}
    return prog, revs


def save(gid):
    doc, rev = fetch(gid)
    prog, revs = maps(doc)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    path = BACKUPS / f"progress-{stamp}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (BACKUPS / f"progress-{stamp}.revision.txt").write_text(
        f"gist {gid}\nrevision {rev['version']}\ncommitted {rev['committed_at']}\n"
        f"url https://gist.github.com/{gid}/{rev['version']}\n", encoding="utf-8")
    print(f"saved  {path}")
    print(f"       revision {rev['version'][:12]}  {rev['committed_at']}")
    print(f"       {len(prog)} stories with progress, {len(revs)} rated")


def restore(gid, path, dry):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    prog, revs = maps(doc)
    if not prog and not revs:
        sys.exit(f"{path} holds neither a progress nor a reviews map")

    live, _ = fetch(gid)
    live_prog, live_revs = maps(live)
    now = int(time.time() * 1000)

    out_prog = {}
    for slug, rec in prog.items():
        if not isinstance(rec, dict):
            continue
        r = dict(rec)
        r["at"] = now
        if "doneAt" in r:
            r["doneAt"] = now
        out_prog[slug] = r
    for slug in live_prog:
        if slug not in out_prog:
            out_prog[slug] = {"sub": 0, "done": False, "doneAt": now, "at": now}

    out_revs = {}
    for slug, rec in revs.items():
        if not isinstance(rec, dict):
            continue
        r = dict(rec)
        r["at"] = now
        out_revs[slug] = r
    for slug in live_revs:
        if slug not in out_revs:
            out_revs[slug] = {"stars": 0, "note": "", "at": now}

    added = [s for s in out_prog if s not in prog]
    cleared = [s for s in out_revs if s not in revs]
    story_word = "story" if len(prog) == 1 else "stories"
    rating_word = "rating" if len(revs) == 1 else "ratings"
    print(f"restoring {len(prog)} {story_word} and {len(revs)} {rating_word} from {path}")
    if added:
        print(f"  tombstoned (in the gist, not in the snapshot): {', '.join(added)}")
    if cleared:
        print(f"  ratings cleared for: {', '.join(cleared)}")
    print(f"  every stamp set to {now}, so the restore outranks every device")

    if dry:
        print("\n--dry-run, nothing written:\n")
        print(json.dumps({"v": 1, "progress": out_prog, "reviews": out_revs},
                         ensure_ascii=False, indent=1))
        return

    body = {"description": DESC, "files": {FILE: {"content": json.dumps(
        {"v": 1, "progress": out_prog, "reviews": out_revs}, indent=2) + "\n"}}}
    gh(f"/gists/{gid}", method="PATCH", body=body)
    print(f"\nwritten. https://gist.github.com/{gid}")
    print("Each device adopts it on its next sync — open the contents page to pull it in.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--restore", metavar="FILE", help="put this snapshot back")
    ap.add_argument("-n", "--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    gid = find()
    if args.restore:
        restore(gid, args.restore, args.dry_run)
    else:
        save(gid)


if __name__ == "__main__":
    main()
