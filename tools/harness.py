#!/usr/bin/env python3
"""Verification harness for the reader rewrite.

Every check here is an ASSERTION with a pass/fail verdict, never a counter, and
the never-scroll assertions read raw geometry off the live cell. The harness this
replaces asked `PageBox.overflows()` — the same predicate `split()` used to
choose the boundary — which made "0 overflowing" true by construction.

Two other things the first harness got wrong are structural here rather than
fixed in place. It injected a <style> that pinned #track and #measure to an
explicit box, which replaced the `position: fixed; inset: 0` / 100dvh /
env(safe-area-inset-*) layout root it was supposed to be testing; this drives
Chrome through CDP `Emulation.setDeviceMetricsOverride` instead, so the page is
byte-for-byte what build.py emits and the real root is the one measured. And it
loaded each story exactly once per configuration, which cannot express reload,
cross-story, or before-and-after checks; this holds one browser open and drives
navigation, so persistence and degradation are reachable.

  python3 harness.py                 # behaviour suites + the 28px table
  python3 harness.py --matrix        # ... and the full mode x viewport x size matrix
  python3 harness.py --table         # the screen-count table alone
"""

import base64
import http.server
import json
import os
import re
import socket
import shutil
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

CHROME = os.environ.get(
    "CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "scripts"
# Built fixtures go to a scratch dir, never into the repo: this harness runs
# against docs/ and must not add files next to what it is measuring.
HERE = Path(tempfile.mkdtemp(prefix="reader-harness-"))
ROW = re.compile(r"const DATA = (\{.*?\});\n", re.S)
PORT = 8917
DEVPORT = 9757

SLUGS = ["shuden", "tokei-no-oto", "neko-o-sagasu-tantei", "maigo-no-tegami",
         "shiro-no-kane", "entotsu-no-kemuri"]

PHONE = ("phone", 390, 844, True)
LAND = ("landscape", 844, 390, True)
DESK = ("desktop", 1440, 900, False)


# --------------------------------------------------------------------- build --
# build.py's substitution contracts, asserted rather than assumed: the reader
# ships by whole-block replacement, so a marker that stopped matching exactly
# once would be a silent build break rather than an error.
def build(slug, inject=False):
    src = (REPO / "docs" / f"{slug}.html").read_text(encoding="utf-8")
    d = json.loads(ROW.search(src).group(1))
    d["slug"] = slug
    if inject:
        # No corpus token is both 苦手 and 新出, and reader.css declares a
        # precedence for that case. Synthesise one on the first ruby token of
        # page 1 so the class the renderer emits is the one under test.
        mark_both(d)
    css = (SRC / "reader.css").read_text(encoding="utf-8")
    js = (SRC / "reader.js").read_text(encoding="utf-8")
    tpl = (SRC / "reader.html").read_text(encoding="utf-8")

    contracts = [
        ("    <style>\n__READER_CSS__\n    </style>\n", tpl, "reader.html"),
        ("    <script>\n__READER_JS__\n    </script>\n", tpl, "reader.html"),
        ("__TITLE__", tpl, "reader.html"),
        ('"__STORY_DATA__"', js, "reader.js"),
    ]
    for needle, hay, where in contracts:
        if hay.count(needle) != 1:
            raise SystemExit(f"build contract broken: {needle!r} matched {hay.count(needle)}x in {where}")
    if "__TITLE__" in css or "__TITLE__" in js:
        raise SystemExit("build contract broken: __TITLE__ must appear in reader.html only")
    if not js.startswith("      const DATA = "):
        raise SystemExit("build contract broken: reader.js line 1 is no longer the DATA line")

    h = tpl.replace("__READER_CSS__\n", css).replace("__READER_JS__\n", js)
    h = h.replace("__TITLE__", d["title"])
    h = h.replace('"__STORY_DATA__"', json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    name = f"{slug}-inj.html" if inject else f"{slug}.html"
    (HERE / name).write_text(h, encoding="utf-8")
    return d


def mark_both(d):
    for sent in d["pages"][0]:
        for tok in sent["toks"]:
            if tok.get("r") and any(pair[1] for pair in tok["r"]):
                tok["w"] = 1
                tok["n"] = 1
                return tok["t"]
    raise SystemExit("no ruby token on page 1 to mark")


def corpus_has_both():
    hits = []
    for slug in SLUGS:
        d = json.loads(ROW.search((REPO / "docs" / f"{slug}.html").read_text(encoding="utf-8")).group(1))
        for page in d["pages"]:
            for sent in page:
                for tok in sent["toks"]:
                    if tok.get("w") and tok.get("n"):
                        hits.append((slug, tok["t"]))
    return hits


# ----------------------------------------------------------------- websocket --
class WS:
    """Enough of RFC 6455 to speak CDP. No dependency is installable here."""

    def __init__(self, url):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=120)
        self.sock.settimeout(120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("devtools refused the upgrade")
            buf += chunk
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise IOError("devtools socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode("utf-8")
        n = len(data)
        hdr = bytearray([0x81])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        self.sock.sendall(bytes(hdr) + masked)

    def recv(self):
        out = b""
        while True:
            h = self._read(2)
            fin, op, n = h[0] & 0x80, h[0] & 0x0F, h[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n) if n else b""
            if op == 0x9:
                self.sock.sendall(b"\x8a\x80" + os.urandom(4))
                continue
            if op == 0x8:
                raise IOError("devtools closed the socket")
            if op == 0xA:
                continue
            out += payload
            if fin:
                return out.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Chrome:
    def __init__(self, port=DEVPORT):
        self.profile = tempfile.mkdtemp(prefix="reader-harness-")
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--remote-debugging-port={port}", f"--user-data-dir={self.profile}",
             "--no-first-run", "--no-default-browser-check",
             "--disable-background-timer-throttling",
             "--disable-renderer-backgrounding",
             "--disable-backgrounding-occluded-windows",
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        target = None
        for _ in range(120):
            try:
                pages = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/list", timeout=2).read())
                target = next((p for p in pages if p.get("type") == "page"), None)
                if target:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if not target:
            raise SystemExit("Chrome never opened a devtools page target")
        self.ws = WS(target["webSocketDebuggerUrl"])
        self.mid = 0
        self.call("Page.enable")
        self.call("Runtime.enable")

    def call(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                if "error" in msg:
                    raise RuntimeError(method + ": " + json.dumps(msg["error"]))
                return msg.get("result", {})

    def emulate(self, w, h, mobile):
        self.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
                  deviceScaleFactor=3 if mobile else 2, mobile=mobile,
                  screenOrientation={"type": "landscapePrimary" if w > h else "portraitPrimary",
                                     "angle": 90 if w > h else 0})
        self.call("Emulation.setTouchEmulationEnabled", enabled=mobile,
                  maxTouchPoints=5 if mobile else 1)

    def init_script(self, source):
        return self.call("Page.addScriptToEvaluateOnNewDocument", source=source)["identifier"]

    def drop_init_script(self, ident):
        self.call("Page.removeScriptToEvaluateOnNewDocument", identifier=ident)

    def goto(self, url):
        self.call("Page.navigate", url=url)
        self.settle()

    def reload(self):
        self.call("Page.reload", ignoreCache=False)
        self.settle()

    def settle(self):
        for _ in range(200):
            try:
                if self.eval("document.readyState === 'complete' && "
                             "typeof Paginator !== 'undefined' && "
                             "!!document.querySelector('#track .cell.is-current')"):
                    # Two frames, so the bootstrap's coalesced relayout has landed.
                    self.eval("new Promise(r => requestAnimationFrame(() => "
                              "requestAnimationFrame(() => r(1))))", await_promise=True)
                    return
            except RuntimeError:
                pass
            time.sleep(0.05)
        raise SystemExit("page never finished booting")

    def eval(self, expr, await_promise=False):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, userGesture=True)
        if "exceptionDetails" in r:
            ex = r["exceptionDetails"]
            desc = (ex.get("exception") or {}).get("description") or ex.get("text")
            raise RuntimeError(str(desc)[:600])
        return r["result"].get("value")

    def close(self):
        self.ws.close()
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


# ------------------------------------------------------------- probe library --
# Installed by Runtime.evaluate after load, never written into the page: the
# served HTML has to be exactly what build.py produces.
LIB = r"""
window.H = (() => {
  const EPS = 1;                       // sub-pixel; .page reserves 1px for it
  const track = () => document.getElementById("track");
  const cell = () => document.querySelector("#track .cell.is-current");
  const box = () => cell().firstElementChild;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const px = (v) => Math.round(v * 100) / 100;

  function contentBox(el) {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return {
      l: r.left + parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth),
      t: r.top + parseFloat(cs.paddingTop) + parseFloat(cs.borderTopWidth),
      r: r.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth),
      b: r.bottom - parseFloat(cs.paddingBottom) - parseFloat(cs.borderBottomWidth),
    };
  }

  const docState = () => {
    const d = document.documentElement;
    return { sw: d.scrollWidth, sh: d.scrollHeight, cw: d.clientWidth, ch: d.clientHeight,
             sl: d.scrollLeft, st: d.scrollTop,
             bl: document.body.scrollLeft, bt: document.body.scrollTop };
  };

  // ---- never-scroll, raw geometry, zero slack ----------------------------
  // The split predicate is deliberately not consulted. Both classes are
  // failures; the split is diagnostic, and 0.5em is the line it falls on
  // because that is both the furthest ruby or 傍点 ink can protrude and the
  // box's own overflow-clip-margin. At or below it the ink still paints, so the
  // reader loses nothing; above it the glyphs are shaved and gone.
  // The surface text of a rendered box, with the annotations taken out — the
  // same string a reader sees. Cloned rather than walked in place so nothing in
  // the live DOM is disturbed between screens.
  function surface(el, drop) {
    const c = el.cloneNode(true);
    for (const rt of c.querySelectorAll("rt, rp")) rt.remove();
    if (drop) for (const n of c.querySelectorAll(drop)) n.remove();
    return c.textContent;
  }

  // What the story's text screens must add up to, in order: every token of every
  // authored page. Splitting may move a boundary; it may never lose, duplicate
  // or reorder a character.
  function expectedText() {
    let s = "";
    for (const page of DATA.pages) {
      for (const sent of page) {
        for (const tok of sent.toks) s += tok.t;
      }
    }
    return s;
  }

  function expectedAfter() {
    if (!DATA.afterword) return "";
    const t = document.createElement("div");
    t.innerHTML = DATA.afterword;
    return surface(t);
  }

  // Two strings differ somewhere; say where, and show both sides of it. A raw
  // pair of 40k-character strings in a failure report is unreadable.
  function firstDiff(got, want) {
    let i = 0;
    while (i < got.length && i < want.length && got[i] === want[i]) i++;
    return { at: i, gotLen: got.length, wantLen: want.length,
             got: got.slice(Math.max(0, i - 20), i + 20),
             want: want.slice(Math.max(0, i - 20), i + 20) };
  }

  function walk(wantFs) {
    const fails = [];
    const base = docState();
    const counts = { text: 0, after: 0 };
    let a = Paginator.first(), seen = 0, tight = 0, worst = 0;
    let gotText = "", gotAfter = "", labels = 0;

    while (a && seen < 600) {
      const s = Paginator.screenAt(a);
      Track.goTo(a, false);
      const el = box(), c = cell();
      const cs = getComputedStyle(el);
      const fs = parseFloat(cs.fontSize);
      const ovW = el.scrollWidth - el.clientWidth;
      const ovH = el.scrollHeight - el.clientHeight;
      const ov = Math.max(ovW, ovH);
      if (ov > worst) worst = ov;
      if (ovW > EPS || ovH > EPS) {
        fails.push({ kind: "overflow", klass: ov <= fs * 0.5 ? "ink" : "column",
                     page: a.page + 1, sub: a.sub, screen: s.kind, cls: el.className,
                     ovW: px(ovW), ovH: px(ovH), fs: fs,
                     sw: el.scrollWidth, cw: el.clientWidth,
                     sh: el.scrollHeight, ch: el.clientHeight });
      }
      if (el.scrollLeft !== 0 || el.scrollTop !== 0) {
        fails.push({ kind: "cell-scrolled", page: a.page + 1, sub: a.sub,
                     sl: el.scrollLeft, st: el.scrollTop });
      }
      const r = el.getBoundingClientRect(), cb = contentBox(c);
      if (r.left < cb.l - EPS || r.top < cb.t - EPS || r.right > cb.r + EPS || r.bottom > cb.b + EPS) {
        fails.push({ kind: "escapes-cell", page: a.page + 1, sub: a.sub,
                     box: [px(r.left), px(r.top), px(r.right), px(r.bottom)],
                     cell: [px(cb.l), px(cb.t), px(cb.r), px(cb.b)] });
      }
      if (s.tight) {
        tight++;
        fails.push({ kind: "tight", page: a.page + 1, sub: a.sub });
      }
      if (s.kind === "text") {
        counts.text++;
        gotText += surface(el);
        if (Math.abs(fs - wantFs) > 0.01) {
          fails.push({ kind: "type-fidelity", page: a.page + 1, sub: a.sub, fs: fs, want: wantFs });
        }
      } else {
        counts.after++;
        // The reader prepends its own あとがき heading as atom 0, so it is not
        // part of the corpus text; it is asserted separately, as exactly one.
        labels += el.querySelectorAll(".after-label").length;
        gotAfter += surface(el, ".after-label");
      }
      seen++;
      a = Paginator.next(a);
    }

    // Geometry says nothing about what is ON the screens. Since a screen may now
    // open or close inside a sentence, the token slice is arithmetic that can be
    // off by one in either direction without moving a single pixel, and the
    // あとがき tolerance bug deleted whole lines while every box still measured
    // clean. Read the text back and compare it to the corpus.
    const wantText = expectedText();
    if (gotText !== wantText) {
      fails.push(Object.assign({ kind: "text-lost" }, firstDiff(gotText, wantText)));
    }
    const wantAfter = expectedAfter();
    if (gotAfter !== wantAfter) {
      fails.push(Object.assign({ kind: "afterword-lost" }, firstDiff(gotAfter, wantAfter)));
    }
    if (DATA.afterword && labels !== 1) {
      fails.push({ kind: "afterword-label", got: labels, want: 1 });
    }

    const now = docState();
    for (const k of ["sw", "sh"]) {
      if (now[k] !== base[k]) fails.push({ kind: "doc-scroll-grew", axis: k, was: base[k], now: now[k] });
    }
    for (const k of ["sl", "st", "bl", "bt"]) {
      if (now[k] !== 0) fails.push({ kind: "doc-scrolled", axis: k, now: now[k] });
    }
    const tally = {};
    for (const f of fails) {
      const k = f.kind === "overflow" ? "overflow-" + f.klass + "-" + f.screen : f.kind;
      tally[k] = (tally[k] || 0) + 1;
    }
    return { fails, tally, screens: seen, text: counts.text, after: counts.after, tight,
             worst: px(worst), pages: Paginator.total, doc: base };
  }

  // ---- the authored page is an atom -------------------------------------
  // A position in an authored page is (sentence, token), not (sentence): a
  // screen may open or close inside a sentence that is wider than the box. The
  // tiling assertion has to be written in the same units the paginator splits
  // in, or it reports a false gap at every such boundary — which is what a
  // sentence-only version of this check did, silently, because it only ever ran
  // at the one size where no sentence is ever cut.
  function atoms() {
    const bad = [];
    for (let i = 0; i < Paginator.total; i++) {
      const runs = Paginator.screensOf(i);
      const page = DATA.pages[i];
      const n = page.length;
      let curS = 0, curT = 0;
      for (const s of runs) {
        if (s.page !== i) bad.push({ kind: "wrong-page", page: i + 1, got: s.page + 1 });
        if (s.kind !== "text") continue;
        const head = s.head || 0;
        if (s.from !== curS || head !== curT) {
          bad.push({ kind: "gap-or-overlap", page: i + 1,
                     from: [s.from, head], want: [curS, curT] });
        }
        // tail < 0 means the run ends on a sentence boundary; otherwise it stops
        // at token `tail` of the last sentence and the next screen resumes there.
        if (s.tail >= 0) {
          curS = s.to - 1;
          curT = s.tail;
          if (curT >= page[curS].toks.length) { curS++; curT = 0; }
        } else {
          curS = s.to;
          curT = 0;
        }
      }
      if (curS !== n || curT !== 0) {
        bad.push({ kind: "page-not-covered", page: i + 1, covered: [curS, curT], want: [n, 0] });
      }
      for (let k = 1; k < runs.length; k++) {
        const lab = Paginator.screenLabel({ page: i, sub: k });
        if (runs[k].kind === "text" && lab.indexOf(String(i + 1) + "·") !== 0) {
          bad.push({ kind: "sub-lost-page-number", page: i + 1, sub: k, label: lab });
        }
      }
    }
    return bad;
  }

  // ---- the paint cache ---------------------------------------------------
  // A cell at either end of the story has no neighbour to hold, and the
  // rubber-band exposes part of it. Whether it was ever cleared is a question
  // about a cache key, so ask the DOM instead: the slot has to be empty.
  async function paintcache() {
    const out = [];
    const filled = () =>
      Array.from(track().children).map((c) => (c.textContent || "").trim().length);
    const add = (name, ok, detail) => out.push({ name: name, ok: ok, detail: detail });

    // Somewhere in the middle first, so every slot has been painted with real
    // text and an uncleared one has something stale to show.
    Track.goTo({ page: 5, sub: 0 }, false);
    await sleep(80);
    const mid = filled();
    Track.goTo(Paginator.first(), false);
    await sleep(80);
    let f = filled();
    add("paint/no-stale-cell-at-first", f.filter((n) => n === 0).length === 1,
        { cells: f, afterMidJump: mid });

    // final(), not last(): last() is the end of the STORY and the あとがき still
    // follows it, so all three slots are legitimately full there.
    Track.goTo(Paginator.final(), false);
    await sleep(80);
    f = filled();
    add("paint/no-stale-cell-at-last", f.filter((n) => n === 0).length === 1, { cells: f });

    // Flipping the binding re-rotates the cells, which is the other way a slot
    // with no screen behind it ends up holding the page that used to sit there.
    Track.goTo(Paginator.first(), false);
    await sleep(80);
    const was = Prefs.get().binding;
    Prefs.set("binding", was === "right" ? "left" : "right");
    await sleep(120);
    f = filled();
    add("paint/no-stale-cell-after-binding-flip", f.filter((n) => n === 0).length === 1,
        { cells: f, binding: Prefs.get().binding });
    Prefs.set("binding", was);
    await sleep(120);
    return out;
  }

  // ---- gestures ----------------------------------------------------------
  const tx = () => {
    const t = getComputedStyle(track()).transform;
    if (t === "none") return 0;
    return new DOMMatrixReadOnly(t).m41;
  };
  const inline = () => track().style.transform;

  function pev(type, x, y, kind) {
    const init = { pointerId: 1, pointerType: kind || "touch", isPrimary: true,
                   bubbles: true, cancelable: true, composed: true,
                   clientX: x, clientY: y, screenX: x, screenY: y,
                   button: 0, buttons: type === "pointerup" ? 0 : 1, width: 1, height: 1 };
    const e = new PointerEvent(type, init);
    if (type === "pointerdown") {
      const el = document.elementFromPoint(x, y) || track();
      el.dispatchEvent(e);
    } else {
      window.dispatchEvent(e);
    }
    return e;
  }

  // A release has to look stationary or velocity() turns the drag into a flick,
  // and the settle has to be given its 260ms plus the timer's margin.
  async function release(x, y, kind) {
    pev("pointermove", x, y, kind);
    await sleep(140);
    pev("pointerup", x, y, kind);
    await sleep(420);
  }

  async function drag(x0, y0, dx, kind, steps) {
    steps = steps || 6;
    pev("pointerdown", x0, y0, kind);
    await sleep(16);
    for (let i = 1; i <= steps; i++) {
      pev("pointermove", x0 + (dx * i) / steps, y0, kind);
      await sleep(24);
    }
  }

  const addr = () => Track.address();
  const same = (a, b) => Paginator.sameAddress(a, b);

  async function reset() {
    Sheet.dismiss();
    Track.goTo(Paginator.first(), false);
    await sleep(30);
  }

  function wordAt() {
    return document.querySelector("#track .cell.is-current .w");
  }
  function centre(el) {
    const r = el.getClientRects()[0] || el.getBoundingClientRect();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
  }

  async function gestures() {
    const out = [];
    const T = track();
    const W = T.clientWidth, Ht = T.clientHeight;
    const cx = Math.round(W / 2), cy = Math.round(Ht / 2);
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });

    // 1. live translate: the box follows the finger, slop subtracted, no turn.
    await reset();
    const a0 = addr();
    await drag(cx, cy, 30, "touch");
    const live = tx();
    add("gesture/live-translate", Math.abs(live - (-W + 22)) < 2 && same(addr(), a0),
        { x: px(live), want: px(-W + 22), addr: addr() });
    await release(cx + 30, cy, "touch");

    // 2. spring back under the 25% threshold.
    add("gesture/spring-back", same(addr(), a0) && inline() === "translateX(-100%)",
        { addr: addr(), transform: inline() });

    // 3. snap past it.
    await reset();
    const before3 = addr();
    await drag(cx - Math.round(W * 0.3), cy, Math.round(W * 0.6), "touch");
    await release(cx + Math.round(W * 0.3), cy, "touch");
    add("gesture/snap-past-threshold", same(addr(), Paginator.next(before3)),
        { addr: addr(), want: Paginator.next(before3) });

    // 4. rubber band at the first screen, and at the last.
    await reset();
    const backDx = -Math.round(W * 0.5);
    await drag(cx + Math.round(W * 0.25), cy, backDx, "touch");
    const banded = tx() - (-W);
    const rawBack = backDx + 8;
    add("gesture/band-at-first",
        Math.abs(banded - rawBack * 0.35) < 3 && Math.abs(banded) < Math.abs(rawBack),
        { offset: px(banded), want: px(rawBack * 0.35) });
    await release(cx + Math.round(W * 0.25) + backDx, cy, "touch");
    add("gesture/band-at-first-holds", same(addr(), Paginator.first()), { addr: addr() });

    Track.goTo(Paginator.final(), false);
    await sleep(30);
    const endAddr = addr();
    await drag(cx - Math.round(W * 0.25), cy, Math.round(W * 0.5), "touch");
    const banded2 = tx() - (-W);
    const rawFwd = Math.round(W * 0.5) - 8;
    add("gesture/band-at-last",
        Math.abs(banded2 - rawFwd * 0.35) < 3 && Math.abs(banded2) < Math.abs(rawFwd),
        { offset: px(banded2), want: px(rawFwd * 0.35) });
    await release(cx + Math.round(W * 0.25), cy, "touch");
    add("gesture/band-at-last-holds", same(addr(), endAddr), { addr: addr() });

    // 5. the 8px boundary. 7px is a tap and reaches disclosure; 9px is a drag
    //    and reaches nothing.
    await reset();
    let w = wordAt();
    let p = centre(w);
    pev("pointerdown", p.x, p.y, "touch");
    await sleep(20);
    pev("pointermove", p.x + 7, p.y, "touch");
    await sleep(20);
    pev("pointerup", p.x + 7, p.y, "touch");
    await sleep(40);
    add("gesture/7px-is-a-tap", Sheet.isOpen(), { open: Sheet.isOpen() });

    Sheet.dismiss();
    await sleep(300);
    await reset();
    w = wordAt();
    p = centre(w);
    const a5 = addr();
    pev("pointerdown", p.x, p.y, "touch");
    await sleep(20);
    pev("pointermove", p.x + 9, p.y, "touch");
    await sleep(20);
    await release(p.x + 9, p.y, "touch");
    add("gesture/9px-is-a-drag", !Sheet.isOpen() && same(addr(), a5),
        { open: Sheet.isOpen(), addr: addr() });

    // 6. a swipe must open no sheet, including via the click the engine
    //    synthesises after the pointer sequence.
    await reset();
    w = wordAt();
    p = centre(w);
    await drag(p.x, p.y, Math.round(W * 0.6), "touch");
    await release(p.x + Math.round(W * 0.6), p.y, "touch");
    w.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, composed: true,
                                              clientX: p.x, clientY: p.y }));
    await sleep(40);
    add("gesture/swipe-opens-no-sheet", !Sheet.isOpen(), { open: Sheet.isOpen() });

    // 7. a stationary press is a tap however long it is held. plan:78 caps a
    //    tap at 300ms, but the cap discriminates against nothing when the
    //    pointer never moved, and a considered press is the normal shape.
    Sheet.dismiss();
    await sleep(300);
    await reset();
    w = wordAt();
    p = centre(w);
    pev("pointerdown", p.x, p.y, "touch");
    await sleep(500);
    pev("pointerup", p.x, p.y, "touch");
    await sleep(60);
    add("gesture/long-press-still-reveals", Sheet.isOpen(), { open: Sheet.isOpen(), heldMs: 500 });

    // 8. two turns in quick succession are two turns.
    Sheet.dismiss();
    await sleep(300);
    await reset();
    const a8 = addr();
    Track.step(1);
    Track.step(1);
    await sleep(700);
    const want8 = Paginator.next(Paginator.next(a8));
    add("gesture/rapid-double-step", same(addr(), want8), { addr: addr(), want: want8 });

    // 9. mouse drag stays off; a mouse click still reaches disclosure.
    await reset();
    const a9 = addr();
    await drag(cx, cy, Math.round(W * 0.6), "mouse");
    await release(cx + Math.round(W * 0.6), cy, "mouse");
    add("gesture/mouse-drag-off-by-default", same(addr(), a9), { addr: addr(), want: a9 });

    Sheet.dismiss();
    await sleep(300);
    await reset();
    w = wordAt();
    p = centre(w);
    pev("pointerdown", p.x, p.y, "mouse");
    await sleep(30);
    pev("pointerup", p.x, p.y, "mouse");
    await sleep(60);
    add("gesture/mouse-click-reaches-disclosure", Sheet.isOpen(), { open: Sheet.isOpen() });
    Sheet.dismiss();
    await sleep(300);
    return out;
  }

  // ---- sheet -------------------------------------------------------------
  function glossWord() {
    for (const w of document.querySelectorAll("#track .cell.is-current .w")) {
      if (w.dataset.gloss) return w;
    }
    return null;
  }
  // A point inside a .s but outside every .w — punctuation carries no ruby, so
  // it is a bare text node and the sentence is what the tap lands on.
  function bareSpot(s) {
    for (const n of s.childNodes) {
      if (n.nodeType !== 3 || !n.data.trim()) continue;
      const r = document.createRange();
      r.selectNodeContents(n);
      const rect = r.getClientRects()[0];
      if (rect && rect.width > 2 && rect.height > 2) {
        return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) };
      }
    }
    return null;
  }
  async function tapAt(pt) {
    pev("pointerdown", pt.x, pt.y, "touch");
    await sleep(20);
    pev("pointerup", pt.x, pt.y, "touch");
    await sleep(60);
  }

  async function sheet() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const body = document.getElementById("sheet-body");
    const head = document.getElementById("sheet-head");

    // Walk forward until a screen carries a glossed word and a sentence with a
    // tappable bare spot.
    let a = Paginator.first(), w = null, s = null;
    for (let i = 0; i < 80 && a; i++) {
      Track.goTo(a, false);
      await sleep(10);
      w = w || glossWord();
      if (!s) {
        for (const cand of document.querySelectorAll("#track .cell.is-current .s[data-en]")) {
          if (bareSpot(cand)) { s = cand; break; }
        }
      }
      if (w && s && w.closest(".cell") === s.closest(".cell")) break;
      w = glossWord();
      a = Paginator.next(a);
    }
    if (!w || !s) return [{ name: "sheet/fixture", ok: false, detail: { w: !!w, s: !!s } }];

    Prefs.setAll({ meaning: false, trans: false });
    await sleep(30);
    await tapAt(centre(w));
    add("sheet/word-reading-with-意-off",
        Sheet.isOpen() && !head.hidden && body.hidden,
        { open: Sheet.isOpen(), head: !head.hidden, body: !body.hidden });

    Prefs.setAll({ meaning: true });
    await sleep(30);
    Sheet.dismiss();
    await sleep(300);
    w = glossWord() || w;
    await tapAt(centre(w));
    add("sheet/word-reading-and-gloss-with-意-on",
        Sheet.isOpen() && !head.hidden && !body.hidden && body.textContent === w.dataset.gloss,
        { open: Sheet.isOpen(), body: body.textContent, want: w.dataset.gloss });

    Sheet.dismiss();
    await sleep(300);
    Prefs.setAll({ trans: false, meaning: false });
    await sleep(30);
    for (const cand of document.querySelectorAll("#track .cell.is-current .s[data-en]")) {
      if (bareSpot(cand)) { s = cand; break; }
    }
    await tapAt(bareSpot(s));
    add("sheet/sentence-inert-with-訳-off", !Sheet.isOpen(), { open: Sheet.isOpen() });

    Prefs.setAll({ trans: true });
    await sleep(30);
    await tapAt(bareSpot(s));
    add("sheet/sentence-opens-with-訳-on",
        Sheet.isOpen() && body.textContent === s.dataset.en,
        { open: Sheet.isOpen(), body: body.textContent.slice(0, 60) });

    // Dismiss on a tap away — the top bar is outside both the track and the
    // sheet, and carries no data-keep-sheet.
    const topR = document.getElementById("title").getBoundingClientRect();
    pev("pointerdown", Math.round(topR.left + topR.width / 2), Math.round(topR.top + topR.height / 2), "touch");
    await sleep(320);
    add("sheet/dismiss-on-tap-away", !Sheet.isOpen(), { open: Sheet.isOpen() });

    await tapAt(bareSpot(s));
    const opened = Sheet.isOpen();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await sleep(320);
    add("sheet/dismiss-on-escape", opened && !Sheet.isOpen(), { opened, open: Sheet.isOpen() });

    // An untranslated sentence is inert even with 訳 armed.
    Sheet.dismiss();
    await sleep(300);
    const bare = s.cloneNode(true);
    bare.removeAttribute("data-en");
    s.parentNode.insertBefore(bare, s);
    s.style.display = "none";
    await sleep(20);
    const spot = bareSpot(bare);
    if (spot) await tapAt(spot);
    add("sheet/untranslated-sentence-inert", !!spot && !Sheet.isOpen(), { spot: !!spot, open: Sheet.isOpen() });
    s.style.display = "";
    bare.remove();

    // Chrome must refuse to auto-hide while 訳 or 意 is armed (kept on purpose).
    Sheet.dismiss();
    await sleep(300);
    Prefs.setAll({ trans: true, meaning: false });
    await sleep(20);
    Chrome.show();
    const T = track();
    await drag(Math.round(T.clientWidth / 2), Math.round(T.clientHeight / 2), 40, "touch");
    const stayed = Chrome.isShown();
    await release(Math.round(T.clientWidth / 2) + 40, Math.round(T.clientHeight / 2), "touch");
    add("chrome/refuses-to-hide-while-訳-armed", stayed, { shown: stayed });

    Prefs.setAll({ trans: false, meaning: false });
    await sleep(20);
    Chrome.show();
    await drag(Math.round(T.clientWidth / 2), Math.round(T.clientHeight / 2), 40, "touch");
    const hid = !Chrome.isShown();
    await release(Math.round(T.clientWidth / 2) + 40, Math.round(T.clientHeight / 2), "touch");
    add("chrome/hides-on-drag-with-no-gate-armed", hid, { hidden: hid });
    return out;
  }

  // ---- copy-out ----------------------------------------------------------
  // Copying a sentence must give the surface text. rt is user-select: none for
  // exactly this reason; the desktop rule that re-enables selection on the whole
  // track must not reach it.
  function selection() {
    let s = null;
    for (const cand of document.querySelectorAll("#track .cell.is-current .s")) {
      if (cand.querySelector(".w rt")) { s = cand; break; }
    }
    if (!s) return { ok: false, detail: { reason: "no ruby sentence on this screen" } };
    let want = "";
    for (const n of s.childNodes) {
      if (n.nodeType === 3) want += n.data;
      else if (n.dataset && n.dataset.t) want += n.dataset.t;
      else want += n.textContent;
    }
    const r = document.createRange();
    r.selectNodeContents(s);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
    const got = sel.toString();
    sel.removeAllRanges();
    return { ok: got === want, detail: { got, want } };
  }

  // ---- 傍点 vs ruby ------------------------------------------------------
  // Measured as opposite sides, not as a computed string: the declared value is
  // `under left`, and bare `under` computes to `under right`, which in a column
  // puts the sesame on top of the furigana. A control with text-emphasis: none
  // calibrates the reservation, so the side the line box grew on is the answer.
  function marks() {
    const live = document.querySelector("#track .cell.is-current .w.weak.new");
    const out = { rendered: !!live, vertical: document.body.classList.contains("vertical") };
    if (live) {
      const cs = getComputedStyle(live);
      out.emStyle = cs.textEmphasisStyle || cs.webkitTextEmphasisStyle;
      out.emPos = cs.textEmphasisPosition || cs.webkitTextEmphasisPosition;
      out.rtOpacity = live.querySelector("rt") ? getComputedStyle(live.querySelector("rt")).opacity : null;
    }

    const make = (cls, strip) => {
      const host = document.createElement("div");
      host.className = "page";
      host.style.cssText = "position:fixed;left:-10000px;top:0;inline-size:auto;" +
                           "block-size:auto;overflow:visible;line-height:1;";
      const p = document.createElement("p");
      p.style.margin = "0";
      const w = document.createElement("span");
      w.className = cls;
      if (strip) w.style.textEmphasis = "none";
      const ruby = document.createElement("ruby");
      const base = document.createTextNode("漢");
      ruby.append(base);
      const rt = document.createElement("rt");
      rt.textContent = "かん";
      ruby.append(rt);
      w.append(ruby);
      p.append(w);
      host.append(p);
      document.body.append(host);
      const pr = p.getBoundingClientRect();
      const range = document.createRange();
      range.selectNode(base);
      const br = range.getBoundingClientRect();
      const rtr = rt.getBoundingClientRect();
      const fs = parseFloat(getComputedStyle(w).fontSize);
      return { host, fs,
               gapL: br.left - pr.left, gapR: pr.right - br.right,
               gapT: br.top - pr.top, gapB: pr.bottom - br.bottom,
               rtLeft: rtr.left, rtRight: rtr.right, rtTop: rtr.top, rtBottom: rtr.bottom,
               bLeft: br.left, bRight: br.right, bTop: br.top, bBottom: br.bottom };
    };

    const em = make("w weak new", false);
    const ctrl = make("w weak new", true);
    const fs = em.fs;
    const grew = { L: em.gapL - ctrl.gapL, R: em.gapR - ctrl.gapR,
                   T: em.gapT - ctrl.gapT, B: em.gapB - ctrl.gapB };
    out.grew = { L: px(grew.L), R: px(grew.R), T: px(grew.T), B: px(grew.B) };
    out.fs = fs;
    const min = fs * 0.15;
    if (out.vertical) {
      out.rubySide = em.rtLeft >= em.bRight - 1 ? "right" : em.rtRight <= em.bLeft + 1 ? "left" : "?";
      out.markSide = grew.L > min ? "left" : grew.R > min ? "right" : "none";
      out.ok = out.rubySide === "right" && out.markSide === "left";
    } else {
      out.rubySide = em.rtBottom <= em.bTop + 1 ? "over" : em.rtTop >= em.bBottom - 1 ? "under" : "?";
      out.markSide = grew.B > min ? "under" : grew.T > min ? "over" : "none";
      out.ok = out.rubySide === "over" && out.markSide === "under";
    }
    em.host.remove();
    ctrl.host.remove();
    return out;
  }

  // ---- prefs / binding ---------------------------------------------------
  const snap = () => ({
    prefs: Prefs.get(),
    binding: Track.binding(),
    addr: Track.address(),
    label: Chrome && document.getElementById("count").textContent,
    store: Store.ok(),
    fs: getComputedStyle(box()).fontSize,
    wm: getComputedStyle(box()).writingMode,
    body: document.body.className,
    painted: !!box().textContent.trim(),
    media: matchMedia("(hover: hover) and (pointer: fine)").matches,
    vp: [innerWidth, innerHeight],
    boxReport: PageBox.report(),
  });

  function key(k) {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  }

  async function binding() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    Prefs.setAll({ binding: "auto", writingMode: "vertical" });
    await sleep(60);
    add("binding/auto-vertical-is-right", Track.binding() === "right", { got: Track.binding() });
    Track.goTo({ page: 3, sub: 0 }, false);
    const at = Track.address();
    key("ArrowRight");
    // An arrow turn animates, and the address only moves in settle().
    await sleep(450);
    add("binding/right-bound-ArrowRight-goes-back",
        Paginator.sameAddress(Track.address(), Paginator.prev(at)),
        { from: at, to: Track.address() });

    Prefs.setAll({ writingMode: "horizontal" });
    await sleep(120);
    add("binding/auto-horizontal-is-left", Track.binding() === "left", { got: Track.binding() });
    const at2 = Track.address();
    key("ArrowRight");
    await sleep(450);
    add("binding/left-bound-ArrowRight-goes-forward",
        Paginator.sameAddress(Track.address(), Paginator.next(at2)),
        { from: at2, to: Track.address() });

    Prefs.setAll({ writingMode: "vertical", binding: "left" });
    await sleep(120);
    add("binding/override-sticks-in-vertical", Track.binding() === "left", { got: Track.binding() });
    Prefs.setAll({ binding: "auto" });
    await sleep(60);
    return out;
  }

  // ---- hard invariants ---------------------------------------------------
  async function invariants() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

    // The bars are overlays over a permanent reserve, so hiding them must move
    // nothing. A box that grew when the chrome went away would repaginate under
    // the reader on the first drag.
    Prefs.setAll({ trans: false, meaning: false });
    Chrome.show();
    await frame();
    const shownM = PageBox.metrics(), shownR = box().getBoundingClientRect();
    Chrome.hide();
    await frame();
    const hiddenM = PageBox.metrics(), hiddenR = box().getBoundingClientRect();
    Chrome.show();
    add("invariants/page-box-unchanged-when-chrome-hides",
        shownM.measure === hiddenM.measure && shownM.extent === hiddenM.extent &&
        Math.abs(shownR.width - hiddenR.width) < 0.5 && Math.abs(shownR.height - hiddenR.height) < 0.5,
        { shown: [shownM.measure, shownM.extent, px(shownR.width), px(shownR.height)],
          hidden: [hiddenM.measure, hiddenM.extent, px(hiddenR.width), px(hiddenR.height)] });

    // Ruby is laid out whether or not it is shown, so arming ふ must change
    // opacity and nothing else — a reveal that reflowed would move a boundary.
    const rt = document.querySelector("#track .cell.is-current .w rt");
    if (!rt) return out.concat([{ name: "invariants/ruby-fixture", ok: false, detail: {} }]);
    const read = () => {
      const cs = getComputedStyle(rt);
      return { display: cs.display, visibility: cs.visibility, fontSize: cs.fontSize,
               lineHeight: cs.lineHeight, opacity: cs.opacity,
               sh: box().scrollHeight, sw: box().scrollWidth };
    };
    Prefs.setAll({ furigana: false });
    await frame();
    const off = read();
    Prefs.setAll({ furigana: true });
    await frame();
    const on = read();
    Prefs.setAll({ furigana: false });
    await frame();
    add("invariants/ruby-hidden-by-opacity-only",
        off.display === on.display && off.visibility === on.visibility &&
        off.fontSize === on.fontSize && off.lineHeight === on.lineHeight &&
        off.opacity !== on.opacity && off.sh === on.sh && off.sw === on.sw,
        { off, on });
    return out;
  }

  return { walk, atoms, paintcache, gestures, sheet, selection, marks, snap, binding, invariants, sleep,
           setPrefs: (p) => { Prefs.setAll(p); }, flush: () => Store.flush() };
})();
1
"""

THROW_STORE = r"""
(() => {
  const boom = function () { throw new DOMException("denied", "SecurityError"); };
  try {
    Object.defineProperty(Storage.prototype, "getItem", { value: boom, configurable: true });
    Object.defineProperty(Storage.prototype, "setItem", { value: boom, configurable: true });
    Object.defineProperty(Storage.prototype, "removeItem", { value: boom, configurable: true });
  } catch (e) {}
})();
"""


# ------------------------------------------------------------------ reporting --
class Report:
    def __init__(self):
        self.rows = []

    def add(self, suite, name, ok, detail=None):
        self.rows.append((suite, name, bool(ok), detail))
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {suite}/{name}" if suite else f"  [{mark}] {name}"
        print(line, flush=True)
        if not ok and detail is not None:
            text = json.dumps(detail, ensure_ascii=False)
            print("         " + (text if len(text) < 400 else text[:400] + " ..."), flush=True)

    def fails(self):
        return [r for r in self.rows if not r[2]]

    def summary(self):
        bad = self.fails()
        print("\n" + "=" * 78)
        print(f"{len(self.rows) - len(bad)} passed, {len(bad)} FAILED")
        if bad:
            print("\nFAILURES")
            for suite, name, _, _ in bad:
                print(f"  - {suite}/{name}" if suite else f"  - {name}")
        return len(bad)


def apply_prefs(br, wm, lb, fs, extra=None):
    patch = {"writingMode": wm, "fontSize": fs,
             "linebreaks": {"vertical": bool(lb), "horizontal": bool(lb)}}
    if extra:
        patch.update(extra)
    br.eval("H.setPrefs(" + json.dumps(patch) + ")")
    br.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(1))))",
            await_promise=True)


def walk(br, fs):
    return br.eval(f"H.walk({fs})")


# ------------------------------------------------------------------- suites --
def suite_table(br, rep, base):
    """The measured per-story screen count at 28px 縦書き 改行-off on 390x844."""
    expect = {"shuden": 28, "neko-o-sagasu-tantei": 32, "maigo-no-tegami": 18,
              "tokei-no-oto": 25, "shiro-no-kane": 41, "entotsu-no-kemuri": 27}
    br.emulate(*PHONE[1:])
    table = {}
    print("\n===== screen counts @ 28px 縦書き 改行-off, 390x844 (device emulation) =====")
    for slug in SLUGS:
        br.goto(f"{base}/{slug}.html")
        br.eval(LIB)
        apply_prefs(br, "vertical", False, 28)
        r = walk(br, 28)
        table[slug] = r
        print(f"  {slug:22} pages={r['pages']:3}  screens={r['screens']:3} "
              f"(text {r['text']}, あとがき {r['after']})  tight={r['tight']} "
              f"worst-overflow={r['worst']}px  expected={expect[slug]}")
        rep.add("never-scroll", f"{slug}/no-raw-overflow", not r["fails"], r["fails"][:6])
        # The settled table counts TEXT screens: the あとがき is appended to the
        # last authored page and is not one of the story's screens.
        rep.add("split", f"{slug}/screens-match-plan", r["text"] == expect[slug],
                {"text": r["text"], "want": expect[slug], "total": r["screens"]})
        bad = br.eval("H.atoms()")
        rep.add("split", f"{slug}/authored-page-is-an-atom", not bad, bad[:6])
    return table


def suite_matrix(br, rep):
    modes = [("vertical", False), ("vertical", True), ("horizontal", False), ("horizontal", True)]
    sizes = [22, 28, 36, 40]
    base = f"http://127.0.0.1:{PORT}"
    worst = {}
    for vp in (PHONE, LAND, DESK):
        br.emulate(*vp[1:])
        for slug in SLUGS:
            br.goto(f"{base}/{slug}.html")
            br.eval(LIB)
            for wm, lb in modes:
                for fs in sizes:
                    apply_prefs(br, wm, lb, fs)
                    r = walk(br, fs)
                    cell = f"{vp[0]}/{wm}/{'改行on' if lb else '改行off'}/{fs}px"
                    rep.add("matrix", f"{cell}/{slug}", not r["fails"],
                            {"screens": r["screens"], "worst": r["worst"],
                             "tally": r["tally"], "first": r["fails"][:1]})
                    # The atom rule has to hold in the cells that actually split
                    # inside a sentence, which the 28px reference never does.
                    bad = br.eval("H.atoms()")
                    rep.add("atom", f"{cell}/{slug}", not bad, bad[:4])
                    for f in r["fails"]:
                        k = (f["kind"] + "/" + f.get("klass", "") + "/" + f.get("screen", "")).strip("/")
                        cur = worst.setdefault(k, {"n": 0, "worst": 0, "where": None})
                        cur["n"] += 1
                        mag = max(f.get("ovW", 0), f.get("ovH", 0))
                        if cur["where"] is None or mag > cur["worst"]:
                            cur["worst"] = mag
                            cur["where"] = f"{cell}/{slug} p{f.get('page')}·{f.get('sub')}"
    print("\n  matrix defect tally (every screen of every cell):")
    for k, v in sorted(worst.items(), key=lambda kv: -kv[1]["n"]):
        mag = f"worst {v['worst']}px" if v["worst"] else "no magnitude"
        print(f"    {k:28} x{v['n']:<5} {mag:16} at {v['where']}")


def suite_behaviour(br, rep, base):
    slug = "tokei-no-oto"
    br.emulate(*PHONE[1:])
    br.goto(f"{base}/{slug}.html")
    br.eval(LIB)
    apply_prefs(br, "vertical", False, 28)

    for row in br.eval("H.gestures()", await_promise=True):
        rep.add("gesture", row["name"].split("/", 1)[1], row["ok"], row["detail"])
    for row in br.eval("H.sheet()", await_promise=True):
        suite, _, name = row["name"].partition("/")
        rep.add(suite, name, row["ok"], row["detail"])
    for row in br.eval("H.binding()", await_promise=True):
        rep.add("binding", row["name"].split("/", 1)[1], row["ok"], row["detail"])
    apply_prefs(br, "vertical", False, 28)
    for row in br.eval("H.invariants()", await_promise=True):
        rep.add("invariants", row["name"].split("/", 1)[1], row["ok"], row["detail"])

    # Every split in the book is decided by scrollWidth/scrollHeight on the
    # probe. An engine reporting the padding box would split nothing and show it
    # only as text shaved off long pages, so the probe says so about itself.
    probe_ok = br.eval('typeof PageBox.selfTest === "function" && PageBox.selfTest() === true')
    rep.add("measure", "probe-reports-overflow", probe_ok is True, {"selfTest": probe_ok})
    # The paint cache is keyed by a string, and the end-of-story neighbour has no
    # key at all. Any string sentinel for "empty" is a value a real key could
    # take, and the symptom is a stale page revealed by the rubber-band rather
    # than an error, so assert the cell is actually empty.
    for row in br.eval("H.paintcache()", await_promise=True):
        rep.add("paint", row["name"].split("/", 1)[1], row["ok"], row["detail"])

    # Copy-out belongs to the fine-pointer platform: it is the only one where a
    # selection can be started at all.
    br.emulate(*DESK[1:])
    br.goto(f"{base}/{slug}.html")
    br.eval(LIB)
    apply_prefs(br, "vertical", False, 28)
    snap = br.eval("H.snap()")
    rep.add("selection", "desktop-media-is-fine-pointer", snap["media"], {"media": snap["media"]})
    sel = br.eval("H.selection()")
    rep.add("selection", "copy-does-not-inline-furigana", sel["ok"], sel["detail"])


def suite_marks(br, rep, base):
    hits = corpus_has_both()
    rep.add("marks", "corpus-has-no-苦手-and-新出-token", not hits,
            {"note": "synthesised instead", "hits": hits[:4]})
    br.emulate(*PHONE[1:])
    br.goto(f"{base}/shuden-inj.html")
    br.eval(LIB)
    for wm in ("vertical", "horizontal"):
        apply_prefs(br, wm, False, 28)
        br.eval("Track.goTo(Paginator.first(), false)")
        m = br.eval("H.marks()")
        mode = "縦書き" if wm == "vertical" else "横書き"
        rep.add("marks", f"{mode}/synthesised-token-renders-w-weak-new", m["rendered"], m)
        # Chrome drops `filled` from the serialisation because it is the initial
        # fill, so the assertion is "sesame, and not the 新出 open circle".
        rep.add("marks", f"{mode}/苦手-wins-over-新出",
                (m.get("emStyle") or "").replace('"', "") in ("sesame", "filled sesame"), m)
        rep.add("marks", f"{mode}/傍点-and-ruby-on-opposite-sides", m.get("ok"),
                {"ruby": m.get("rubySide"), "mark": m.get("markSide"), "grew": m.get("grew"),
                 "position": m.get("emPos")})


def suite_persistence(br, rep, base):
    br.emulate(*PHONE[1:])
    a, b = "tokei-no-oto", "maigo-no-tegami"
    br.goto(f"{base}/{a}.html")
    # The never-scroll walk turns every page of every story, and every turn
    # writes progress. Per-slug tracking is only observable from a clean origin.
    br.eval("localStorage.clear()")
    br.reload()
    br.eval(LIB)
    want = {"writingMode": "horizontal", "binding": "left", "fontSize": 36,
            "theme": "dark", "furigana": True, "trans": True, "meaning": True,
            "linebreaks": {"vertical": True, "horizontal": True}}
    br.eval("H.setPrefs(" + json.dumps(want) + ")")
    br.eval("Track.goTo({page: 9, sub: 0}, false)")
    br.eval("H.flush()")
    time.sleep(0.3)

    br.reload()
    br.eval(LIB)
    got = br.eval("H.snap()")
    for k, v in want.items():
        rep.add("persistence", f"pref-{k}-survives-reload", got["prefs"][k] == v,
                {"got": got["prefs"][k], "want": v})
    rep.add("persistence", "progress-survives-reload", got["addr"]["page"] == 9,
            {"got": got["addr"]})
    rep.add("persistence", "binding-override-survives-reload", got["binding"] == "left",
            {"got": got["binding"]})

    # Progress is an authored page index, so a type-size change must not move it
    # even though it re-splits every screen.
    br.eval("H.setPrefs({fontSize: 22})")
    br.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(1))))",
            await_promise=True)
    after = br.eval("H.snap()")
    rep.add("persistence", "progress-survives-a-type-size-change", after["addr"]["page"] == 9,
            {"got": after["addr"], "fs": after["fs"]})

    br.eval("H.setPrefs({fontSize: 36}); H.flush()")
    time.sleep(0.3)
    br.goto(f"{base}/{b}.html")
    br.eval(LIB)
    crossed = br.eval("H.snap()")
    rep.add("persistence", "prefs-carry-across-stories-on-one-origin",
            crossed["prefs"]["writingMode"] == "horizontal" and crossed["prefs"]["fontSize"] == 36,
            {"got": crossed["prefs"]})
    rep.add("persistence", "progress-is-per-slug", crossed["addr"]["page"] == 0,
            {"got": crossed["addr"]})
    rec = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress') || '{}')")
    rep.add("persistence", "first-story-progress-still-recorded",
            (rec.get(a) or {}).get("page") == 10, {"stored": rec})


def suite_degradation(br, rep, base):
    ident = br.init_script(THROW_STORE)
    try:
        br.emulate(*PHONE[1:])
        br.goto(f"{base}/tokei-no-oto.html")
        br.eval(LIB)
        s = br.eval("H.snap()")
        rep.add("degradation", "reader-opens-with-localStorage-throwing", s["painted"], s["boxReport"])
        rep.add("degradation", "store-reports-itself-dead", s["store"] is False, {"ok": s["store"]})
        rep.add("degradation", "prefs-fall-back-to-defaults",
                s["prefs"]["writingMode"] == "vertical" and s["prefs"]["fontSize"] == 28,
                {"got": s["prefs"]})
        r = walk(br, 28)
        rep.add("degradation", "pagination-still-never-scrolls", not r["fails"], r["fails"][:4])
        br.eval("Track.step(1)")
        br.eval("H.flush()")
        s2 = br.eval("H.snap()")
        rep.add("degradation", "a-page-turn-does-not-throw", s2["addr"]["page"] >= 0, s2["addr"])
    finally:
        br.drop_init_script(ident)


# --------------------------------------------------------------------- main --
def serve():
    handler = http.server.SimpleHTTPRequestHandler
    os.chdir(HERE)

    class Quiet(handler):
        def log_message(self, *a):
            pass

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Quiet)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    args = set(sys.argv[1:])
    for slug in SLUGS:
        build(slug)
    build("shuden", inject=True)

    srv = serve()
    br = None
    rep = Report()
    base = f"http://127.0.0.1:{PORT}"
    try:
        br = Chrome()
        table = suite_table(br, rep, base)
        if "--table" not in args:
            print("\n===== behaviour =====")
            suite_behaviour(br, rep, base)
            print("\n===== 傍点 vs ruby =====")
            suite_marks(br, rep, base)
            print("\n===== persistence =====")
            suite_persistence(br, rep, base)
            print("\n===== degradation =====")
            suite_degradation(br, rep, base)
        if "--matrix" in args:
            print("\n===== matrix: 4 mode x density, 3 viewports, 22/28/36/40px =====")
            suite_matrix(br, rep)
        print("\n===== table (for the record) =====")
        print("  story                  text  あとがき  total")
        for slug, r in table.items():
            print(f"  {slug:22} {r['text']:4}  {r['after']:8}  {r['screens']:5}")
    finally:
        if br:
            br.close()
        srv.shutdown()
        srv.server_close()
    return 1 if rep.summary() else 0


if __name__ == "__main__":
    sys.exit(main())
