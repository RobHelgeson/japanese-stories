// Progress is written by the readers into this device's localStorage, so
// it cannot be baked in here. Pages serves this page and every reader from
// one origin, so the store they write is the store this reads. Everything
// is wrapped because a mailed or file:// copy throws on the accessor
// itself, and because this page must stay readable with no Sync at all.
(function () {
  var S = window.Sync;
  var $ = function (id) { return document.getElementById(id); };
  var cells = [].slice.call(document.querySelectorAll(".cell[data-slug]"));
  // Date.now() is the clock; this is the order. Two edits inside one
  // millisecond carry the same `at`, the merge gives a tie to the remote,
  // and the second edit then loses to the copy of the first that its own
  // push has already put in the gist — a stepper tap that silently undoes
  // itself. Only this page edits fast enough to tie with itself, so the
  // monotonic stamp lives here rather than in the merge rule, which still
  // gives the remote a genuine tie so two devices converge.
  var last = 0;
  var now = function () {
    var t = Date.now();
    last = t > last ? t : last + 1;
    return last;
  };

  // A note long enough to be a document is a note that belongs in the
  // vault, not in a gist every reader on every device pulls on boot.
  var NOTE_MAX = 2000;

  var slot = function (key) {
    try { return JSON.parse(localStorage.getItem("japanese-stories:" + key)) || {}; }
    catch (e) { return {}; }
  };

  var read = function () { return S ? S.local() : slot("progress"); };
  var readR = function () { return S ? S.reviews() : slot("reviews"); };

  var put = function (key, map) {
    if (S) { if (key === "progress") S.saveLocal(map); else S.saveReviews(map); return; }
    try { localStorage.setItem("japanese-stories:" + key, JSON.stringify(map)); } catch (e) {}
  };

  // One push, debounced or not, and it repaints both halves. Typing in a
  // note must not fire a pull-merge-push per keystroke, and a star must
  // not wait a second and a half to leave the device.
  var flush = null;
  var pushNow = function () {
    if (flush) { clearTimeout(flush); flush = null; }
    if (!S) return;
    S.push().then(function (r) { paint(r.map); paintR(r.reviews); });
  };
  var pushSoon = function () {
    if (!S) return;
    if (flush) clearTimeout(flush);
    flush = setTimeout(pushNow, 1500);
  };

  // Every mutation goes through one of these, so the push and the repaint
  // cannot be forgotten at one call site and not another.
  var save = function (map) { put("progress", map); paint(map); pushNow(); };
  var saveR = function (map, soon) {
    put("reviews", map);
    paintR(map);
    if (soon) pushSoon(); else pushNow();
  };

  var total = function (cell) { return Number(cell.dataset.pages) || 1; };

  function paint(all) {
    if (!all || typeof all !== "object") all = {};
    var done = 0;
    // The row the 続き block will point at: whichever unfinished story was
    // touched last, falling back to the first one not yet finished.
    var open = null, openAt = -1, openPage = 0, next = null;
    for (var i = 0; i < cells.length; i++) {
      var cell = cells[i], rec = all[cell.dataset.slug];
      var prog = cell.querySelector(".prog");
      var out = cell.querySelector('[data-out="page"]');
      var mark = cell.querySelector('[data-act="done"]');
      // Anything that is not a record is skipped rather than trusted: a
      // version field added at the top level later would read as a slug.
      var ok = rec && typeof rec === "object" && !Array.isArray(rec);
      var n = total(cell);
      // rec.of is ignored — it is only what the device believed the last
      // time it read this story.
      var page = ok ? Number(rec.page) : NaN;
      if (!isFinite(page) || page < 1) page = NaN;
      else if (page > n) page = n;
      // Whether the story is finished is the reader's verdict, read back,
      // never re-derived here. Reaching the last authored page is not the
      // same thing: that page is usually split across screens on a phone,
      // and `page >= total` painted 読了 with a screen still to go.
      var fin = ok && rec.done === true;
      if (isFinite(page) || fin) {
        // Floored, because page 1 of 41 rounds to under a pixel and an
        // empty bar reads as "not started".
        var pct = fin ? 100 : Math.max(4, Math.round((page / n) * 100));
        prog.querySelector("i").style.width = pct + "%";
        prog.querySelector(".pct").textContent =
          fin ? "読了" : page + " / " + n;
        prog.hidden = false;
      } else {
        prog.hidden = true;
      }
      cell.classList.toggle("done", !!fin);
      if (fin) done++;
      else {
        if (!next) next = cell;
        var at = ok ? Number(rec.at) : NaN;
        if (isFinite(page) && isFinite(at) && at > openAt) {
          open = cell; openAt = at; openPage = page;
        }
      }
      if (out) out.textContent = isFinite(page) ? page + " / " + n : "—";
      if (mark) mark.textContent = fin ? "未読" : "読了";
    }
    $("readtot").textContent = done ? " · 読了 " + done + "/" + cells.length : "";
    resume(open, openPage, next);
    autoOpen(all, null);
  }

  // 続き on the story already in hand, 次へ on the first one not yet
  // finished — first in reading order, not first after the last one
  // finished, so skipping ahead leaves the skipped story offered.
  // Gone entirely once the corpus is read out.
  function resume(open, page, next) {
    var el = $("resume");
    if (!el) return;
    var cell = open || next;
    if (!cell) { el.hidden = true; return; }
    var a = cell.querySelector("a.card");
    el.setAttribute("href", a ? a.getAttribute("href") : "#");
    el.querySelector(".rlabel").textContent = open ? "続き" : "次へ";
    el.querySelector(".rtitle").textContent = cell.dataset.title || "";
    el.querySelector(".rpct").textContent =
      open ? page + " / " + total(cell) : total(cell) + " ページ";
    el.hidden = false;
  }

  // A story you have finished and not yet rated opens itself, so the
  // stars are still in front of you on the way out — which is the whole
  // reason they do not sit behind 編集. A row the reader has opened or
  // closed by hand is left alone; a preference beats a default.
  // Both callers already hold the map they painted from, and a push or a
  // pull paints from the merged result rather than from the store — so
  // going back to localStorage here can disagree with what is on screen.
  // A write that silently failed on quota is enough to produce it.
  function autoOpen(prog, revs) {
    prog = prog || read();
    revs = revs || readR();
    for (var i = 0; i < cells.length; i++) {
      var cell = cells[i];
      if (shut[cell.dataset.slug] || cell.classList.contains("open")) continue;
      var p = prog[cell.dataset.slug], r = revs[cell.dataset.slug];
      var fin = p && typeof p === "object" && p.done === true;
      var rated = r && typeof r === "object" && Number(r.stars) >= 1;
      if (fin && !rated) disclose(cell, true);
    }
  }

  function disclose(cell, on) {
    cell.classList.toggle("open", on);
    var btn = cell.querySelector(".disc");
    if (btn) btn.setAttribute("aria-expanded", on ? "true" : "false");
  }

  // Which rows have been shut by hand, so the auto-open does not undo the
  // correction on the next load. A Home Screen install relaunches on
  // every visit, so an in-memory flag would mean it never held at all.
  // Device-local and out of the gist deliberately: this is where this
  // screen is scrolled to, not anything about the reading.
  var shut = slot("shut");
  function remember(slug, on) {
    if (on) delete shut[slug]; else shut[slug] = 1;
    try {
      localStorage.setItem("japanese-stories:shut", JSON.stringify(shut));
    } catch (e) {}
  }

  function paintR(all) {
    if (!all || typeof all !== "object") all = {};
    for (var i = 0; i < cells.length; i++) {
      var cell = cells[i], rec = all[cell.dataset.slug];
      var ok = rec && typeof rec === "object" && !Array.isArray(rec);
      var stars = ok ? Math.round(Number(rec.stars)) : NaN;
      if (!isFinite(stars) || stars < 1) stars = 0;
      else if (stars > 5) stars = 5;
      var buttons = cell.querySelectorAll('[data-act="star"]');
      for (var j = 0; j < buttons.length; j++) {
        buttons[j].setAttribute(
          "aria-pressed", Number(buttons[j].dataset.n) <= stars ? "true" : "false");
      }
      var note = ok && typeof rec.note === "string" ? rec.note : "";
      var ta = cell.querySelector("textarea.note");
      // A pull landing mid-sentence must not take the sentence away, so a
      // focused box is left exactly as it is. The blur repaints it, which
      // is what stops a note merged in while it sat focused-and-empty
      // from being overwritten by the next keystroke.
      if (ta && ta !== document.activeElement && ta.value !== note) ta.value = note;
      var btn = cell.querySelector(".notebtn");
      if (btn) btn.classList.toggle("has", !!note);
    }
    autoOpen(null, all);
  }

  // A hand-set review carries `at` for the same reason a hand-set record
  // does: it is what outranks a stale device on the merge.
  function review(slug, fn, soon) {
    var all = readR();
    var rec = all[slug] && typeof all[slug] === "object" && !Array.isArray(all[slug])
      ? all[slug] : {};
    var next = fn(Object.assign({}, rec));
    if (typeof next.note === "string" && next.note.length > NOTE_MAX) {
      next.note = next.note.slice(0, NOTE_MAX);
    }
    next.at = now();
    all[slug] = next;
    saveR(all, soon);
  }

  function star(cell, n) {
    if (!(n >= 1 && n <= 5)) return;
    var slug = cell.dataset.slug;
    var rec = readR()[slug];
    var cur = rec && typeof rec === "object" ? Number(rec.stars) : 0;
    // Tapping the star that is already lit takes the rating back off.
    // Nothing else can undo a mis-tap, and a star nobody meant is a
    // verdict the generator would read as real.
    review(slug, function (r) { r.stars = cur === n ? 0 : n; return r; }, false);
  }

  // A hand-set record carries `at` so it outranks a stale device on the
  // merge, and `doneAt` whenever it touches 読了 — that stamp is the only
  // thing that can take a 読了 away, since reading alone only ever ORs it
  // on. Fields the reader owns (`sub`, `of`) are left where they are.
  function edit(slug, fn) {
    var all = read();
    var rec = all[slug] && typeof all[slug] === "object" ? all[slug] : {};
    var next = fn(Object.assign({}, rec));
    next.at = now();
    all[slug] = next;
    save(all);
  }

  function act(cell, what) {
    var slug = cell.dataset.slug, n = total(cell);
    if (what === "clear") {
      // Position only. Losing your place in a story is not withdrawing
      // what you thought of it; the lit star is its own undo.
      // A tombstone, not a deletion. An absent slug merges to whatever the
      // gist still holds, so deleting the key would undo itself on the very
      // next pull. A dated record with no page is what actually travels,
      // and it paints as unread because paint() keys the bar on `page`.
      edit(slug, function () {
        return { sub: 0, of: n, done: false, doneAt: now() };
      });
      return;
    }
    if (what === "done") {
      edit(slug, function (r) {
        var fin = r.done !== true;
        r.done = fin;
        r.doneAt = now();
        // Marking 読了 by hand means the story is behind you, so the
        // position goes with it rather than being left mid-book.
        if (fin) { r.page = n; r.sub = 0; }
        else if (!isFinite(Number(r.page))) { r.page = 1; r.sub = 0; }
        r.of = n;
        return r;
      });
      return;
    }
    var d = what === "inc" ? 1 : -1;
    edit(slug, function (r) {
      var p = Number(r.page);
      if (!isFinite(p)) p = d > 0 ? 1 : n;
      else p = Math.min(n, Math.max(1, p + d));
      r.page = p;
      // The screen index within a page cannot survive a page change, and
      // the reader clamps it against a split this page cannot know.
      r.sub = 0;
      r.of = n;
      return r;
    });
  }

  // One delegated listener rather than a handler per row, so adding a
  // story adds no wiring.
  var main = document.querySelector("main");

  main.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest("button[data-act]") : null;
    if (!btn) return;
    var cell = btn.closest(".cell[data-slug]");
    if (!cell) return;
    var what = btn.dataset.act;
    // Ahead of act(): an unrecognised action falls through to its
    // stepper branch, so a disclosure tap would turn a page.
    if (what === "more") {
      var on = !cell.classList.contains("open");
      disclose(cell, on);
      remember(cell.dataset.slug, on);
      return;
    }
    if (what === "star") { star(cell, Number(btn.dataset.n)); return; }
    if (what === "note") {
      var ta = cell.querySelector("textarea.note");
      if (!ta) return;
      var show = ta.hidden;
      // A collapsed row puts the box in a display:none subtree, where it
      // cannot take focus and so is not skipped by paintR's focused-box
      // guard — the next pull would overwrite what was being typed.
      // Revealing the box opens the row that holds it.
      if (show) disclose(cell, true);
      ta.hidden = !show;
      btn.setAttribute("aria-expanded", show ? "true" : "false");
      if (show) ta.focus();
      return;
    }
    act(cell, what);
  });

  // Typed straight into localStorage and pushed on a debounce: the local
  // write is what makes a lost push harmless, since the page pushes again
  // on its next load anyway.
  main.addEventListener("input", function (e) {
    var ta = e.target.closest ? e.target.closest("textarea.note") : null;
    if (!ta) return;
    var cell = ta.closest(".cell[data-slug]");
    if (cell) review(cell.dataset.slug, function (r) { r.note = ta.value; return r; }, true);
  });

  main.addEventListener("focusout", function (e) {
    if (!e.target.closest || !e.target.closest("textarea.note")) return;
    if (flush) pushNow();
    paintR(readR());
  });

  // The tab away, the app switch and the Home Screen swipe all land here,
  // and only this one is reliable on iOS.
  window.addEventListener("pagehide", function () { if (flush) pushNow(); });

  $("edit").addEventListener("click", function () {
    var on = $("edit").getAttribute("aria-pressed") !== "true";
    $("edit").setAttribute("aria-pressed", on ? "true" : "false");
    for (var i = 0; i < cells.length; i++) {
      var row = cells[i].querySelector(".manage");
      if (row) row.hidden = !on;
    }
  });

  paint(read());
  paintR(readR());

  // ------------------------------------------------------------ sync --
  if (!S) return;

  var stat = $("sstat"), box = $("box");
  var WORDS = { idle: "未接続", busy: "同期中…", ok: "同期済み",
                error: "同期できません", rejected: "トークンが拒否されました",
                off: "同期は無効です" };

  function showStatus(s) {
    var text = s.message || WORDS[s.state] || s.state;
    if (s.state === "ok" && s.at) {
      text += " · " + new Date(s.at).toLocaleTimeString();
    }
    if (s.state === "idle" && !s.connected) text = WORDS.idle;
    stat.textContent = text;
    stat.className = "sstat" + (s.state === "ok" ? " good"
      : s.state === "error" || s.state === "rejected" ? " bad" : "");
    $("conn").textContent = s.connected ? "再接続" : "接続";
    $("disc").hidden = !s.connected;
    // The store, openable. gist.github.com/<id> resolves without the owner
    // in the path, so no username has to be stored to build this.
    var link = $("glink");
    link.hidden = !s.gist;
    if (s.gist) link.href = "https://gist.github.com/" + s.gist;
  }

  S.onChange(showStatus);
  showStatus(S.status());

  $("conn").addEventListener("click", function () {
    var t = $("tok").value;
    if (!t) { $("tok").focus(); return; }
    S.connect(t).then(function (r) {
      // The token is in localStorage now; leaving it in a form field as
      // well only widens where it can be read off a shoulder.
      $("tok").value = "";
      paint((r && r.map) || read());
      paintR((r && r.reviews) || readR());
    }, function () { $("tok").value = ""; });
  });

  $("disc").addEventListener("click", function () { S.forget(); });

  $("exp").addEventListener("click", function () {
    box.hidden = false;
    // The envelope the gist holds, so an export and the store read the
    // same. A bare progress map still imports, for anything exported
    // before reviews existed.
    box.value = JSON.stringify({ v: 1, progress: read(), reviews: readR() }, null, 2);
    box.focus();
    box.select();
    if (navigator.clipboard) navigator.clipboard.writeText(box.value).catch(function () {});
  });

  // Import merges by the same rule the gist does, so pasting an older
  // export cannot pull a story backwards. Replacing outright is what the
  // per-row controls and 全消去 are for.
  $("imp").addEventListener("click", function () {
    if (box.hidden) { box.hidden = false; box.value = ""; box.focus(); return; }
    var incoming;
    try { incoming = JSON.parse(box.value); } catch (e) {
      stat.textContent = "JSON が読めません";
      stat.className = "sstat bad";
      return;
    }
    if (!S.plain(incoming)) {
      stat.textContent = "JSON がオブジェクトではありません";
      stat.className = "sstat bad";
      return;
    }
    var enveloped = S.plain(incoming.progress) || S.plain(incoming.reviews);
    var prog = enveloped
      ? (S.plain(incoming.progress) ? incoming.progress : {})
      : incoming;
    var revs = enveloped && S.plain(incoming.reviews) ? incoming.reviews : {};
    // Written together and pushed once: two saves would each pull, merge
    // and PATCH, and the first PATCH would be a revision saying half of
    // what the paste meant.
    var mergedP = S.merge(read(), prog);
    var mergedR = S.mergeReviews(readR(), revs);
    put("progress", mergedP);
    put("reviews", mergedR);
    paint(mergedP);
    paintR(mergedR);
    pushNow();
    box.hidden = true;
  });

  $("wipe").addEventListener("click", function () {
    // No confirm(): a modal dialog blocks the extension driving this page
    // in the harness, and the gist's revision history is the real undo.
    // Two deliberate taps behind a closed <details> is the guard.
    if ($("wipe").dataset.armed !== "1") {
      $("wipe").dataset.armed = "1";
      $("wipe").textContent = "本当に全消去";
      setTimeout(function () {
        $("wipe").dataset.armed = "";
        $("wipe").textContent = "全消去";
      }, 4000);
      return;
    }
    $("wipe").dataset.armed = "";
    $("wipe").textContent = "全消去";
    // Tombstones rather than an empty map: an empty map merges to whatever
    // the gist still holds and the wipe would undo itself on the next
    // pull. A dated, page-less record is what actually travels.
    var all = read(), out = {};
    for (var k in all) {
      if (Object.prototype.hasOwnProperty.call(all, k)) {
        out[k] = { sub: 0, done: false, doneAt: now(), at: now() };
      }
    }
    var allR = readR(), outR = {};
    for (var j in allR) {
      if (Object.prototype.hasOwnProperty.call(allR, j)) {
        outR[j] = { stars: 0, note: "", at: now() };
      }
    }
    put("progress", out);
    put("reviews", outR);
    paint(out);
    paintR(outR);
    pushNow();
  });

  // Asking is free where it is honoured and a no-op where it is not.
  if (navigator.storage && navigator.storage.persist) {
    navigator.storage.persist().catch(function () {});
  }

  S.push().then(function (r) { paint(r.map); paintR(r.reviews); });
})();
