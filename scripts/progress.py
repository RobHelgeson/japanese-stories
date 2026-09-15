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


def envelope(prog, revs):
    r"""The file's bytes, exactly as sync.js writes them.

    ensure_ascii off because sync.js emits raw UTF-8 and a note is Japanese as
    often as not: \uXXXX escapes would leave the gist unreadable in the editor,
    which is half of why a gist was chosen, and would rewrite every record on
    the first restore. One encoder, so --dry-run prints what gets written.
    """
    return json.dumps({"v": 1, "progress": prog, "reviews": revs},
                      ensure_ascii=False, indent=2) + "\n"


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
    f = full["files"][FILE]
    # sync.js refuses a truncated file rather than merging half of one, and a
    # half-file read as a snapshot is the one failure indistinguishable from
    # real data loss. It cannot happen under 1MB and this is kilobytes.
    if f.get("truncated"):
        sys.exit(f"{FILE} came back truncated — refusing to read half a store")
    try:
        doc = json.loads(f["content"])
    except json.JSONDecodeError as e:
        sys.exit(f"{FILE} is not valid JSON: {e}")
    return doc, full["history"][0]


def maps(doc):
    """The two halves, or None for a half the document does not speak about.

    The distinction decides whether a restore clears anything. `"reviews": {}`
    says there were no ratings and the gist's should go; no `reviews` key at all
    says this snapshot has no opinion, and tombstoning every rating on the
    strength of a key that was never there is how a backup destroys data.
    """
    if not isinstance(doc, dict):
        return None, None
    prog = doc.get("progress") if isinstance(doc.get("progress"), dict) else None
    revs = doc.get("reviews") if isinstance(doc.get("reviews"), dict) else None
    return prog, revs


def save(gid, dry):
    doc, rev = fetch(gid)
    prog, revs = maps(doc)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    path = BACKUPS / f"progress-{stamp}.json"
    body = envelope(prog or {}, revs or {})
    note = (f"gist {gid}\nrevision {rev['version']}\ncommitted {rev['committed_at']}\n"
            f"url https://gist.github.com/{gid}/{rev['version']}\n")
    if dry:
        print(f"--dry-run, nothing written. Would save {path}:\n")
        print(note)
        print(body)
        return
    BACKUPS.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    (BACKUPS / f"progress-{stamp}.revision.txt").write_text(note, encoding="utf-8")
    print(f"saved  {path}")
    print(f"       revision {rev['version'][:12]}  {rev['committed_at']}")
    print(f"       {len(prog or {})} stories with progress, {len(revs or {})} rated")


def restore(gid, path, dry):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    prog, revs = maps(doc)
    if prog is None and revs is None:
        sys.exit(f"{path} holds neither a progress nor a reviews map")

    live, _ = fetch(gid)
    live_prog, live_revs = maps(live)
    live_prog = live_prog or {}
    live_revs = live_revs or {}
    now = int(time.time() * 1000)

    def stamped(rec, done_too):
        r = dict(rec)
        r["at"] = now
        # Unconditionally, not only where the key already sits. A restored
        # record with no doneAt loses the field to whatever the device has, and
        # doneAt is the only thing that can take a 読了 away — so without this
        # every story read during the test stays 読了 even though the restore
        # wins on `at`, which is precisely the case this script exists for.
        if done_too:
            r["doneAt"] = now
        return r

    out_prog = {s: stamped(r, True) for s, r in (prog or {}).items() if isinstance(r, dict)}
    out_revs = {s: stamped(r, False) for s, r in (revs or {}).items() if isinstance(r, dict)}

    # A map the snapshot does not declare is passed through untouched; only a
    # declared one can clear anything.
    if prog is None:
        out_prog = live_prog
    else:
        for slug in live_prog:
            out_prog.setdefault(slug, {"sub": 0, "done": False, "doneAt": now, "at": now})
    if revs is None:
        out_revs = live_revs
    else:
        for slug in live_revs:
            out_revs.setdefault(slug, {"stars": 0, "note": "", "at": now})

    added = [s for s in out_prog if s not in (prog or {})] if prog is not None else []
    cleared = [s for s in out_revs if s not in (revs or {})] if revs is not None else []
    print(f"restoring from {path}")
    if prog is None:
        print("  progress: not in this snapshot, left as the gist has it")
    else:
        print(f"  progress: {len(prog)} " + ("story" if len(prog) == 1 else "stories"))
    if revs is None:
        print("  reviews: not in this snapshot, left as the gist has it")
    else:
        print(f"  reviews: {len(revs)} " + ("rating" if len(revs) == 1 else "ratings"))
    if added:
        print(f"  tombstoned (in the gist, not in the snapshot): {', '.join(added)}")
    if cleared:
        print(f"  ratings cleared for: {', '.join(cleared)}")
    print(f"  every restored stamp set to {now}, so it outranks every device")

    content = envelope(out_prog, out_revs)
    if dry:
        print("\n--dry-run, nothing written. The gist would hold:\n")
        print(content)
        return

    gh(f"/gists/{gid}", method="PATCH",
       body={"description": DESC, "files": {FILE: {"content": content}}})
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
        save(gid, args.dry_run)


if __name__ == "__main__":
    main()
