// Reading progress, story reviews and peeks, kept in a secret gist so they survive
// the device.
//
// localStorage alone loses this three ways, and only one of them is "no sync":
// iOS Safari deletes all script-writable storage after seven days of Safari use
// without a first-party interaction here, a Home Screen web app gets its own
// storage container that starts empty, and two devices diverge with nothing to
// show that they have. A gist fixes all three and costs no server, no port and
// no account that isn't already open — and because the store is a JSON file on
// github.com with revision history, correcting a bad record by hand is a thing
// the platform already does rather than UI that has to be built.
//
// Loaded by every reader and by the contents page, which is why it owns its own
// localStorage access rather than borrowing the reader's Store: index.html has
// no Store. The dead-latch semantics below are deliberately the same as
// reader.js's, quota case included.
window.Sync = (() => {
  const PREFIX = "japanese-stories:";
  const FILE = "japanese-stories-progress.json";
  const DESC = "japanese-stories reading progress";
  const API = "https://api.github.com";
  const V = 1;

  // ?nosync makes the disconnected path reproducible on any browser and any
  // origin, the same way ?nostore does for a throwing store. Nobody types it by
  // accident, and the harness needs one that does not require a network.
  const off = location.search.indexOf("nosync") >= 0;

  let dead = location.search.indexOf("nostore") >= 0;
  let state = off ? "off" : "idle";
  let message = "";
  let stamp = 0;
  let inflight = null;
  // The last remote we saw, held so a 304 has something to be a no-change
  // answer *about*. Without it every conditional request would have to be
  // followed by an unconditional one to learn what it matched.
  let cached = null;
  const listeners = new Set();

  const plain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

  // What a remote with nothing in it looks like. Frozen because it is handed
  // straight to merge() and cached, and a caller that mutated it would be
  // editing every later "the gist is empty" answer.
  const EMPTY = Object.freeze({ progress: {}, reviews: {}, peeks: {} });

  // ------------------------------------------------------------- storage --
  const read = (key) => {
    if (dead) return null;
    let text;
    try {
      text = localStorage.getItem(PREFIX + key);
    } catch (e) {
      dead = true;
      return null;
    }
    if (!text) return null;
    try {
      const value = JSON.parse(text);
      return plain(value) ? value : null;
    } catch (e) {
      return null; // hand-edited or half-written; the defaults are right
    }
  };

  // Firefox names a full quota NS_ERROR_DOM_QUOTA_REACHED rather than
  // QuotaExceededError, so both names are matched and the code is not read. A
  // full store is not a dead one: this value did not fit, the next may.
  const isFull = (e) =>
    !!e && (e.name === "QuotaExceededError" || e.name === "NS_ERROR_DOM_QUOTA_REACHED");

  const write = (key, value) => {
    if (dead) return false;
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value));
      return true;
    } catch (e) {
      if (!isFull(e)) dead = true;
      return false;
    }
  };

  const creds = () => read("sync") || {};
  const saveCreds = (patch) => write("sync", Object.assign(creds(), patch));

  const local = () => read("progress") || {};
  const saveLocal = (map) => write("progress", map);

  // Reviews are a second map rather than fields on the progress record, and the
  // merge rule is why. A progress record is replaced whole by whichever side
  // carries the later `at`, and `at` is bumped by every page turn — so a rating
  // typed on the phone would be erased the next time the laptop turned a page
  // in that story. Separate maps means separate stamps, and a rating and a
  // position can move independently without either having to win.
  const reviews = () => read("reviews") || {};
  const saveReviews = (map) => write("reviews", map);

  // Peeks are what the reader learns from a tap: this word's reading had to be
  // asked for. A third map, keyed slug → device → record, because it is the one
  // half that accumulates rather than being authored. Two devices each counting
  // 時計 three times have seen it six times, and a later-stamp-wins merge over
  // one shared record would report three. Giving every device a record only it
  // ever writes turns the count into a grow-only sum: each record is replaced
  // whole by its own newer copy, and the totals are added up at read time.
  const peeks = () => read("peeks") || {};
  const savePeeks = (map) => write("peeks", map);

  // Random rather than derived, since nothing about a browser is both stable and
  // private. A Home Screen install starts with empty storage and so becomes a
  // new device, which costs nothing: its counts are added to the others'.
  const device = () => {
    const d = read("device");
    if (d && typeof d.id === "string" && d.id) return d.id;
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    // An unwritable store gets a fresh id per load, and every one of those is a
    // record the next merge sums correctly — nothing is lost, only fragmented.
    write("device", { id: id });
    return id;
  };

  // --------------------------------------------------------------- merge --
  // Per slug, the record with the later `at` wins outright — except `done`,
  // which resolves on its own.
  //
  // `done` set by *reading* is sticky and OR'd. Finishing a story is a fact
  // about the story rather than about the visit that finished it — the reader
  // already treats it that way so a re-read resumes without erasing it — and a
  // device that re-opened a finished story and turned one page would otherwise
  // un-finish it everywhere on the strength of a newer timestamp.
  //
  // `done` set by *hand* on the contents page carries `doneAt`, and the later
  // `doneAt` then decides outright, in both directions. Without that exception
  // un-marking a story could not travel at all: the OR would restore it from
  // whichever device had not been told. Reading never writes `doneAt`, so the
  // sticky rule is still what governs everything the reader does on its own —
  // an explicit correction is the only thing that can take a 読了 away, which
  // is the distinction worth having.
  //
  // A record with no usable `at` loses to any record that has one, which is
  // what makes a hand-edited gist behave: add a page number, leave the stamp
  // alone, and the edit still loses to a live device. Bump or delete `at` to
  // make it win. Both halves being absent falls back to b, so the remote wins a
  // tie and two devices converge rather than oscillating.
  const when = (r) => {
    const t = r && Number(r.at);
    return isFinite(t) ? t : -Infinity;
  };

  // The union walk both maps share: a slug is visited once, anything that is
  // not a record is dropped rather than carried — a version field added at the
  // top level later would otherwise read as a slug — and the later `at` wins.
  // What a collision *means* is the only part that differs, so it is passed in.
  const fold = (a, b, resolve) => {
    const out = {};
    const seen = Object.keys(plain(a) ? a : {}).concat(Object.keys(plain(b) ? b : {}));
    for (const slug of seen) {
      if (Object.prototype.hasOwnProperty.call(out, slug)) continue;
      const ra = plain(a) && plain(a[slug]) ? a[slug] : null;
      const rb = plain(b) && plain(b[slug]) ? b[slug] : null;
      if (!ra && !rb) continue;
      const win = !ra ? rb : !rb ? ra : when(ra) > when(rb) ? ra : rb;
      out[slug] = resolve ? resolve(ra, rb, win) : win;
    }
    return out;
  };

  const merge = (a, b) =>
    fold(a, b, (ra, rb, win) => {
      const da = ra ? Number(ra.doneAt) : NaN;
      const db = rb ? Number(rb.doneAt) : NaN;
      let done;
      let doneAt;
      if (isFinite(da) || isFinite(db)) {
        const hand = (isFinite(da) ? da : -Infinity) >= (isFinite(db) ? db : -Infinity) ? ra : rb;
        done = hand.done === true;
        doneAt = Number(hand.doneAt);
      } else {
        done = !!((ra && ra.done === true) || (rb && rb.done === true));
      }
      // NaN never equals itself, so "neither side has a stamp" has to compare as
      // equal explicitly or the clone below fires on every untouched record.
      const stamped = (x) => (isFinite(x) ? x : null);
      if (done === win.done && stamped(Number(win.doneAt)) === stamped(doneAt)) return win;
      const rec = Object.assign({}, win, { done: done });
      if (isFinite(doneAt)) rec.doneAt = doneAt;
      else delete rec.doneAt;
      return rec;
    });

  // A rating and a note are authored rather than accumulated, so the later edit
  // is simply the right one and there is nothing to resolve the way `done` has
  // to be resolved. Clearing a rating writes `stars: 0` with a fresh stamp for
  // the same reason a cleared story writes a tombstone: an absent key merges to
  // whatever the other side still holds, so a deletion cannot travel.
  const mergeReviews = (a, b) => fold(a, b, null);

  // One level deeper than the other two: per slug, the same union walk over
  // device ids. A slug is a map of records rather than a record, so the outer
  // fold's `at` is meaningless and the winner it picks is discarded.
  const mergePeeks = (a, b) =>
    fold(a, b, (ra, rb) => fold(ra, rb, null));

  // Key order is not data. merge() emits slugs in the order it happened to see
  // them, so a plain JSON.stringify comparison would call an identical map
  // different and fire a PATCH that writes nothing — which is the one thing the
  // no-op skip exists to prevent. Sorted at both levels, so record fields
  // arriving in a different order from the gist than from localStorage also
  // compare equal.
  const canon = (v) => {
    if (!plain(v)) return JSON.stringify(v === undefined ? null : v);
    return (
      "{" +
      Object.keys(v)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + canon(v[k]))
        .join(",") +
      "}"
    );
  };

  const same = (a, b) => canon(a) === canon(b);

  // -------------------------------------------------------------- status --
  const notify = () => {
    for (const fn of listeners) {
      try {
        fn(status());
      } catch (e) {
        /* a broken listener must not take the sync down with it */
      }
    }
  };

  const set = (next, msg) => {
    state = next;
    message = msg || "";
    if (next === "ok") stamp = Date.now();
    notify();
  };

  // `gist` is here so the UI can link to the store. Being able to open the
  // thing and read it is half of why a gist was chosen over a KV namespace, and
  // an id that only ever exists in localStorage is not openable.
  const status = () => ({
    state: state,
    at: stamp,
    message: message,
    gist: creds().gist || "",
    connected: !off && !!(creds().token && creds().gist),
  });

  // ----------------------------------------------------------- transport --
  const headers = (token, extra) =>
    Object.assign(
      {
        Authorization: "Bearer " + token,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      extra || {}
    );

  // Every failure is a status and a rejected promise carrying a reason, never a
  // throw that escapes and never a retry. The reader has to keep working
  // exactly as it does today when this is unreachable, so a dead network is a
  // line of text on the contents page and nothing else.
  const call = (method, path, token, body, extra) =>
    fetch(API + path, {
      method: method,
      headers: headers(token, body ? { "Content-Type": "application/json" } : extra),
      body: body ? JSON.stringify(body) : undefined,
    }).then((res) => {
      if (res.status === 304) return { code: 304, etag: res.headers.get("ETag"), json: null };
      if (res.status === 401 || res.status === 403) {
        set("rejected", res.status === 401 ? "トークンが拒否されました" : "権限がありません");
        return Promise.reject(new Error("auth " + res.status));
      }
      if (!res.ok) {
        set("error", "GitHub " + res.status);
        return Promise.reject(new Error("http " + res.status));
      }
      return res.json().then((json) => ({ code: res.status, etag: res.headers.get("ETag"), json: json }));
    });

  // The ETag is persisted but the body it describes is not, so a conditional
  // request is only honest while both are in hand. Sending a stored ETag on a
  // fresh page load earns a 304 whose "unchanged from what you have" refers to
  // nothing — and because the ETag would survive that, every later pull would
  // 304 as well and the device would never sync again.
  const cond = (c) => (cached && c.etag ? { "If-None-Match": c.etag } : null);

  // `v` stays 1: `reviews` is additive and nothing has ever read the version,
  // so bumping it would only mean a number two code paths have to agree about.
  const body = (map, revs, pk) => ({
    description: DESC,
    files: {
      [FILE]: {
        content: JSON.stringify({ v: V, progress: map, reviews: revs, peeks: pk }, null, 2) + "\n",
      },
    },
  });

  // The gist is the only shape we accept, so a file that is missing, truncated
  // or not our envelope reads as an empty remote rather than as corruption to
  // be merged. Truncation cannot happen below 1MB and this map is kilobytes;
  // it is checked because a silent half-file merged into progress is the one
  // failure that would be indistinguishable from real data loss.
  const unwrap = (gist) => {
    const f = gist && gist.files && gist.files[FILE];
    if (!f) return EMPTY;
    if (f.truncated) {
      set("error", "gist が大きすぎます");
      return null;
    }
    let doc;
    try {
      doc = JSON.parse(f.content);
    } catch (e) {
      set("error", "gist の JSON が壊れています");
      return null;
    }
    if (!plain(doc)) return EMPTY;
    return {
      progress: plain(doc.progress) ? doc.progress : {},
      reviews: plain(doc.reviews) ? doc.reviews : {},
      peeks: plain(doc.peeks) ? doc.peeks : {},
    };
  };

  // ------------------------------------------------------------ commands --
  // One flight at a time. Progress pushes on pagehide and pulls on boot, and a
  // reader opened from the contents page can do both within a frame of each
  // other; two overlapping read-modify-writes against the same gist is exactly
  // the race the merge rule exists to avoid having to think about.
  //
  // Everything queued calls the unqueued core below it, never the queued
  // wrapper — connect() finishes by pulling, and a queued pull chained onto the
  // flight connect is itself still holding would wait for a promise that cannot
  // resolve until it returns.
  const queue = (fn) => {
    const run = () => fn();
    inflight = (inflight || Promise.resolve()).then(run, run);
    return inflight;
  };

  // A device is connected by pasting a token and nothing else. The gist is
  // found by its filename across the account's gists before one is created, so
  // the second device joins the first rather than starting a rival store — a
  // gist id would be a second thing to carry between devices, and carrying it
  // is precisely what makes people give up on a sync.
  const connect = (token) =>
    queue(() => {
      if (off) return Promise.reject(new Error("nosync"));
      const t = String(token || "").trim();
      if (!t) return Promise.reject(new Error("no token"));
      set("busy", "接続中…");
      return call("GET", "/gists?per_page=100", t)
        .then((r) => {
          const hit = (r.json || []).find((g) => g && g.files && g.files[FILE]);
          if (hit) return hit.id;
          return call(
            "POST",
            "/gists",
            t,
            Object.assign({ public: false }, body(local(), reviews(), peeks()))
          ).then((c) => c.json.id);
        })
        .then((id) => {
          saveCreds({ token: t, gist: id, etag: "" });
          cached = null;
          set("ok", "");
          return corePull();
        });
    });

  // Resolves with { ok, map, moved } and never rejects into the caller's boot
  // path: a reader that cannot reach GitHub is a reader that reads.
  const corePull = () => {
    const c = creds();
    const still = () => ({ ok: false, map: local(), reviews: reviews(), moved: false });
    if (off || !c.token || !c.gist) return Promise.resolve(still());
    return call("GET", "/gists/" + c.gist, c.token, null, cond(c))
      .then((r) => {
        const remote = r.code === 304 ? cached : unwrap(r.json);
        if (remote === null) return still();
        // After the round trip, for the reason push() gives.
        const before = local();
        const beforeR = reviews();
        const beforeP = peeks();
        cached = remote;
        if (r.etag) saveCreds({ etag: r.etag });
        const merged = merge(before, cached.progress);
        const mergedR = mergeReviews(beforeR, cached.reviews);
        const mergedP = mergePeeks(beforeP, cached.peeks);
        const grew = !same(merged, before);
        const grewR = !same(mergedR, beforeR);
        if (grew) saveLocal(merged);
        if (grewR) saveReviews(mergedR);
        if (!same(mergedP, beforeP)) savePeeks(mergedP);
        set("ok", "");
        // `moved` is what the reader keys its adopt-the-remote-position path
        // on, so a review arriving alone must not read as a position change.
        return { ok: true, map: merged, reviews: mergedR, moved: grew };
      })
      .catch(() => still());
  };

  const pull = () => queue(corePull);

  // Pull-merge-push, so two devices cannot clobber each other without a lock,
  // and a PATCH that would write what is already there is skipped. That skip is
  // what keeps the gist's revision list usable as an undo history: one or two
  // entries per reading session rather than one per page turn.
  const push = () =>
    queue(() => {
      const c = creds();
      if (off || !c.token || !c.gist)
        return Promise.resolve({ ok: false, wrote: false, map: local(), reviews: reviews() });
      return call("GET", "/gists/" + c.gist, c.token, null, cond(c))
        .then((r) => {
          const remote = r.code === 304 ? cached : unwrap(r.json);
          // Read after the round trip, never before it. A page turned or a note
          // typed while the GET was open is newer than anything this push set
          // out to send, and merging against a snapshot taken beforehand writes
          // the stale copy straight back over it — for a note, one keystroke at
          // a time, with the loss PATCHed to the gist behind it.
          const mine = local();
          const mineR = reviews();
          const mineP = peeks();
          if (remote === null) return { ok: false, wrote: false, map: mine, reviews: mineR };
          if (r.etag) saveCreds({ etag: r.etag });
          const merged = merge(mine, remote.progress);
          const mergedR = mergeReviews(mineR, remote.reviews);
          const mergedP = mergePeeks(mineP, remote.peeks);
          if (!same(merged, mine)) saveLocal(merged);
          if (!same(mergedR, mineR)) saveReviews(mergedR);
          if (!same(mergedP, mineP)) savePeeks(mergedP);
          const next = { progress: merged, reviews: mergedR, peeks: mergedP };
          // Every half has to match before the PATCH is skipped: a rating
          // added while the position stood still is still something to say.
          if (same(merged, remote.progress) && same(mergedR, remote.reviews) &&
              same(mergedP, remote.peeks)) {
            cached = next;
            set("ok", "");
            return { ok: true, wrote: false, map: merged, reviews: mergedR };
          }
          return call("PATCH", "/gists/" + c.gist, c.token, body(merged, mergedR, mergedP)).then((w) => {
            cached = next;
            // The PATCH response carries the new ETag; keeping it is what stops
            // the next pull from being handed a 200 for a change we just made.
            if (w.etag) saveCreds({ etag: w.etag });
            set("ok", "");
            return { ok: true, wrote: true, map: merged, reviews: mergedR };
          });
        })
        .catch(() => ({ ok: false, wrote: false, map: local(), reviews: reviews() }));
    });

  // Drops the credentials and leaves progress alone. Disconnecting a device is
  // not a reason to forget what was read on it, and the local map is still the
  // thing every reader on this device reads.
  const forget = () => {
    saveCreds({ token: "", gist: "", etag: "" });
    cached = null;
    set("idle", "");
  };

  return {
    plain,
    local,
    saveLocal,
    reviews,
    saveReviews,
    peeks,
    savePeeks,
    device,
    merge,
    mergeReviews,
    mergePeeks,
    connect,
    pull,
    push,
    forget,
    status,
    onChange: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    ok: () => !dead,
    off: () => off,
    // The filename is part of the contract between devices, so the UI names it
    // from here rather than repeating the string.
    file: FILE,
  };
})();
