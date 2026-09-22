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
import functools
import http.server
import json
import math
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
# build.py and stats.py are imported rather than re-implemented: the whole point
# of this file is to assert what build.py emits, and a second copy of render()'s
# substitutions here would drift from it silently — a placeholder added to
# reader.html would ship in every reader and in none of these fixtures.
sys.path.insert(0, str(SRC))
import build  # noqa: E402
import index  # noqa: E402
import rebuild  # noqa: E402
import stats  # noqa: E402

# Built fixtures go to a scratch dir, never into the repo: this harness runs
# against docs/ and must not add files next to what it is measuring. main()
# removes it; nothing else in the process may chdir into it.
HERE = Path(tempfile.mkdtemp(prefix="reader-harness-"))
PORT = 8917
DEVPORT = 9757

# Read from corpus.json rather than maintained beside it. A hand-written list is
# how 行かなかった人の地図 joined the corpus on 2026-09-13 and was still unmeasured
# by the table, matrix, atom and never-scroll suites two days later: adding a
# story to the corpus did not add it here, and nothing anywhere reported the gap.
# In reading order, so the printed table checks against the contents page.
ORDER_SLUGS = [x["slug"] for x in json.loads(
    (REPO / "scripts" / "corpus.json").read_text(encoding="utf-8"))["stories"]]
SLUGS = ORDER_SLUGS

PHONE = ("phone", 390, 844, True)
LAND = ("landscape", 844, 390, True)
DESK = ("desktop", 1440, 900, False)


# --------------------------------------------------------------------- build --


def check_contracts():
    """build.py's substitution contracts, asserted rather than assumed.

    The reader ships by whole-block replacement, so a marker that stopped
    matching exactly once would be a silent build break rather than an error.
    Asserted here and then handed to build.render() to do the substituting — the
    harness must never own a second copy of it, or it measures a page build.py
    does not produce.
    """
    css = build.READER_CSS.read_text(encoding="utf-8")
    js = build.READER_JS.read_text(encoding="utf-8")
    tpl = build.TEMPLATE.read_text(encoding="utf-8")

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

    # The linked form is what docs/ ships, and its one load-bearing property is
    # invisible in the markup: classic scripts run in document order, so the
    # story has to be written out BEFORE the engine that reads it. Swap the two
    # lines and every story fails at boot with DATA undefined, which nothing
    # else here would catch — the fixtures are rendered inline.
    shell = build.render_shell("x", "data/x.js")
    data_at = shell.find('<script src="data/x.js">')
    engine_at = shell.find('<script src="reader.js">')
    if data_at < 0 or engine_at < 0:
        raise SystemExit("build contract broken: render_shell emitted no linked scripts")
    if data_at > engine_at:
        raise SystemExit("build contract broken: the engine loads before the story data")
    if "__READER_CSS__" in shell or "__READER_JS__" in shell:
        raise SystemExit("build contract broken: render_shell left a placeholder behind")

    # The contents page has the same shape and the same exposure since the
    # 2026-09-16 split, and none of the browser suites would catch a lost marker:
    # they exercise behaviour, and a dropped __CONTENTS_CSS__ ships a page that
    # works and is completely unstyled.
    chtml = (index.HERE / "contents.html").read_text(encoding="utf-8")
    ccss = (index.HERE / "contents.css").read_text(encoding="utf-8")
    cjs = (index.HERE / "contents.js").read_text(encoding="utf-8")

    for needle in ("    <style>\n__CONTENTS_CSS__\n    </style>\n",
                   "    <script>\n__CONTENTS_JS__\n    </script>\n",
                   "__CARDS__", "__TOTALS__"):
        if chtml.count(needle) != 1:
            raise SystemExit(
                f"build contract broken: {needle!r} matched {chtml.count(needle)}x in contents.html")

    # main() substitutes the cards after template() has already folded these two
    # in, so a marker appearing in either file would be expanded into story
    # markup. Nothing else looks, and the tokens are no longer visible in the
    # file that consumes them.
    for name, body in (("contents.css", ccss), ("contents.js", cjs)):
        stray = [m for m in ("__CARDS__", "__TOTALS__",
                             "__CONTENTS_CSS__", "__CONTENTS_JS__") if m in body]
        if stray:
            raise SystemExit(
                f"build contract broken: {name} contains substitution marker(s) {stray}")

    folded = index.template()
    left = [m for m in ("__CONTENTS_CSS__", "__CONTENTS_JS__") if m in folded]
    if left:
        raise SystemExit(f"build contract broken: template() left {left} behind")

    # DATA_DEPS is computed by walking build.py's imports rather than globbing,
    # so the walker is now the thing that decides whether a story re-segments.
    # A module it misses is a story that reports "up to date" against a stale
    # data file, which is the failure the walk was added to prevent.
    # The walker returns files, because editing any file of a package changes
    # what the build produces. This assertion is about modules, so a package's
    # files collapse back to its name: ichiran is six files to the walker and
    # one import to build.py, and it is the import that this contract is about.
    def module_of(path):
        return path.parent.name if (path.parent / "__init__.py").exists() else path.stem

    walked = {module_of(p) for p in rebuild.build_modules()}
    expected = {"build", "check", "furigana", "ichiran",
                "indexmd", "inflect", "pitch", "pos", "vocab"}
    if walked != expected:
        raise SystemExit(
            f"build contract broken: build_modules() walked {sorted(walked)}, "
            f"expected {sorted(expected)}")


def check_no_summary(rep):
    """A story with no Summaries bullet ships a card, and says so on stderr.

    The old behaviour was a hard exit, which was its own test — the build
    stopped. Its replacement is a warning and a placeholder, so nothing fails
    if either one regresses. This is not a browser case: it is index.py's
    output against a doctored stories-index.md, run the way rebuild.py runs it.
    """
    gone = "終電"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "stories").mkdir()
        (tmp / "docs").mkdir()
        for f in (REPO / "docs").glob("*.html"):
            shutil.copy(f, tmp / "docs" / f.name)
        # stats.read follows each shell to its linked blob, so the data goes too.
        shutil.copytree(REPO / "docs" / "data", tmp / "docs" / "data")
        src = (REPO / "stories" / "stories-index.md").read_text(encoding="utf-8")
        # Scoped to the Summaries section: the same story has a bullet under
        # Afterwords, and dropping both would test a different thing.
        kept, inside = [], False
        for ln in src.splitlines(True):
            if ln.startswith("## "):
                inside = ln.strip() == "## Summaries"
            if inside and ln.startswith("- **") and gone in ln:
                continue
            kept.append(ln)
        rep.add("no-summary", "the-doctored-index-really-did-lose-a-bullet",
                len(kept) == len(src.splitlines(True)) - 1, len(src.splitlines(True)) - len(kept))
        (tmp / "stories" / "stories-index.md").write_text("".join(kept), encoding="utf-8")

        r = subprocess.run(
            [sys.executable, "index.py", str(tmp / "docs"), "--src", str(tmp / "stories")],
            cwd=REPO / "scripts", capture_output=True, text=True)
        rep.add("no-summary", "the-build-still-succeeds", r.returncode == 0, r.stderr)
        rep.add("no-summary", "and-names-the-story-on-stderr",
                "warning" in r.stderr and gone in r.stderr, r.stderr.strip())
        out = (tmp / "docs" / "index.html").read_text(encoding="utf-8")
        rep.add("no-summary", "the-card-is-still-rendered",
                'data-slug="shuden"' in out, None)
        rep.add("no-summary", "with-a-visible-gap-where-the-blurb-goes",
                '<p class="sum none">—</p>' in out, None)
        # Same bullet, so the kana line goes with it. Documented, not incidental.
        rep.add("no-summary", "and-no-kana-line-either",
                out.count('class="rt"') == len(ORDER_SLUGS) - 1, out.count('class="rt"'))
        rep.add("no-summary", "every-other-blurb-survives",
                out.count('<p class="sum">') == len(ORDER_SLUGS) - 1,
                out.count('<p class="sum">'))


def build_fixture(slug, inject=False):
    """Re-render a shipped reader against the working-tree engine."""
    # data_of, not a regex here: a live story links its blob from data/<slug>.js
    # while docs/versions/ still carries one inline, and stats owns that fork.
    d = stats.data_of(REPO / "docs" / f"{slug}.html")
    d["slug"] = slug
    if inject:
        # No corpus token is both 苦手 and 新出, and reader.css declares a
        # precedence for that case. Synthesise one on the first ruby token of
        # page 1 so the class the renderer emits is the one under test.
        mark_both(d)
    name = f"{slug}-inj.html" if inject else f"{slug}.html"
    (HERE / name).write_text(build.render(d["title"], d), encoding="utf-8")
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
        d = stats.data_of(REPO / "docs" / f"{slug}.html")
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

    # The contents page and the blank reset fixture have no Paginator and no
    # #track, so the reader-shaped wait above never returns for them.
    def settle_plain(self):
        for _ in range(200):
            try:
                if self.eval("document.readyState === 'complete'"):
                    self.eval("new Promise(r => requestAnimationFrame(() => "
                              "requestAnimationFrame(() => r(1))))", await_promise=True)
                    return
            except RuntimeError:
                pass
            time.sleep(0.05)
        raise SystemExit("plain page never finished booting")

    def goto_plain(self, url):
        self.call("Page.navigate", url=url)
        self.settle_plain()

    def reload_plain(self):
        self.call("Page.reload", ignoreCache=False)
        self.settle_plain()

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

    // 5. the 8px boundary. 7px is a tap and lights the word; 9px is a drag and
    //    reaches nothing.
    await reset();
    let w = wordAt();
    let p = centre(w);
    pev("pointerdown", p.x, p.y, "touch");
    await sleep(20);
    pev("pointermove", p.x + 7, p.y, "touch");
    await sleep(20);
    pev("pointerup", p.x + 7, p.y, "touch");
    await sleep(40);
    // A single tap lights and opens nothing — both halves matter, because the
    // panel appearing here would mean the double tap had collapsed into one.
    add("gesture/7px-is-a-tap", isLit(w) && !Sheet.isOpen(),
        { lit: isLit(w), open: Sheet.isOpen() });

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
    add("gesture/9px-is-a-drag", !isLit(w) && !Sheet.isOpen() && same(addr(), a5),
        { lit: isLit(w), open: Sheet.isOpen(), addr: addr() });

    // 6. a swipe must light nothing and open nothing, including via the click
    //    the engine synthesises after the pointer sequence.
    await reset();
    w = wordAt();
    p = centre(w);
    await drag(p.x, p.y, Math.round(W * 0.6), "touch");
    await release(p.x + Math.round(W * 0.6), p.y, "touch");
    w.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, composed: true,
                                              clientX: p.x, clientY: p.y }));
    await sleep(40);
    add("gesture/swipe-reveals-nothing", !isLit(w) && !Sheet.isOpen(),
        { lit: isLit(w), open: Sheet.isOpen() });

    // 7. a stationary press is a tap however long it is held. A duration cap
    //    was considered and dropped: TAP_SLOP is the whole of the tap/drag
    //    discrimination, so a cap discriminates against nothing when the
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
    add("gesture/long-press-still-reveals", isLit(w), { lit: isLit(w), heldMs: 500 });

    // And the window runs from pointerup, not pointerdown: a considered press
    // followed by a quick second tap is still a double tap. Measuring from the
    // down would have let the 500ms hold above eat the whole window.
    await tapAt(p, DOUBLE_MS + 80);
    const heldOpen = Sheet.isOpen();
    add("gesture/held-press-then-tap-is-a-double", heldOpen, { open: heldOpen });

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
    // The mouse reaches the same grammar through the same door — one click
    // lights, two inside the window open — so nothing in the detector keys on
    // pointerType.
    pev("pointerdown", p.x, p.y, "mouse");
    await sleep(30);
    pev("pointerup", p.x, p.y, "mouse");
    await sleep(60);
    const mouseLit = isLit(w) && !Sheet.isOpen();
    pev("pointerdown", p.x, p.y, "mouse");
    await sleep(30);
    pev("pointerup", p.x, p.y, "mouse");
    await sleep(60);
    add("gesture/mouse-click-lights-double-click-opens", mouseLit && Sheet.isOpen(),
        { lit: mouseLit, open: Sheet.isOpen() });
    Sheet.dismiss();
    await sleep(300);

    // 10. a live drag dragged back through its own start point is continuous.
    //     The slop is subtracted so the page starts from the finger, and it has
    //     to be the slop the gesture went live with: recomputing it from the
    //     current dx flips it by 2 * TAP_SLOP as dx crosses zero, which jumped
    //     the page 16px in one frame and swapped the neighbour being revealed.
    //     Driven from a middle screen so neither side rubber-bands.
    await reset();
    Track.goTo({ page: 5, sub: 0 }, false);
    await sleep(60);
    const rest10 = -track().clientWidth;
    const off = () => tx() - rest10;
    pev("pointerdown", cx, cy, "touch");
    await sleep(16);
    pev("pointermove", cx + 20, cy, "touch");
    await sleep(24);
    const live10 = off();
    pev("pointermove", cx + 1, cy, "touch");
    await sleep(24);
    const plus1 = off();
    pev("pointermove", cx - 1, cy, "touch");
    await sleep(24);
    const minus1 = off();
    pev("pointermove", cx - 20, cy, "touch");
    await sleep(24);
    const far10 = off();
    await release(cx, cy, "touch");
    // 2px of real travel separates dx = +1 from dx = -1. The defect put
    // 2 * TAP_SLOP = 16px there, so 4px is slack rather than a tuned bound.
    add("gesture/drag-is-continuous-through-its-origin",
        Math.abs(plus1 - minus1) < 4 && plus1 > minus1 && minus1 > far10,
        { live: px(live10), plus1: px(plus1), minus1: px(minus1), far: px(far10),
          jump: px(Math.abs(plus1 - minus1)) });
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
  // it is a bare text node and the sentence is what the tap lands on. A node
  // that has been recycled out of the track has no client rects, so this
  // returns null for it rather than throwing.
  function bareSpot(s) {
    if (!s || !s.isConnected) return null;
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
  // The track recycles cells and every Prefs change re-splits the screen, so a
  // sentence found before one can be gone after it. Resolve against the live
  // screen at the moment of the tap rather than carrying a node across.
  function liveSentence() {
    for (const cand of document.querySelectorAll("#track .cell.is-current .s[data-en]")) {
      const pt = bareSpot(cand);
      if (pt) return { s: cand, pt };
    }
    return null;
  }

  // liveSentence(), narrowed to one whose translation carries a reading. Same
  // resolve-against-the-live-screen contract: the track recycles cells, so this
  // is called again at the moment of the tap rather than carried out of a walk.
  function liveAnnotated() {
    for (const cand of document.querySelectorAll("#track .cell.is-current .s[data-en]")) {
      if (!cand.dataset.en.includes("<ruby")) continue;
      const pt = bareSpot(cand);
      if (pt) return { s: cand, pt };
    }
    return null;
  }
  const isLit = (node) => !!node && node.classList.contains("lit");
  // An HTML string parsed inert, so a test can ask what it means rather than
  // what it says. <template> and not innerHTML on a live node: nothing here
  // should be able to run a script or load an image by being asserted about.
  function parsed(htmlText) {
    const t = document.createElement("template");
    t.innerHTML = htmlText || "";
    return t.content;
  }

  // DOUBLE_MS in reader.js. A tap lands 20ms after its pointerdown, so two bare
  // tapAt calls would be ~80ms apart and EVERY consecutive pair would read as a
  // double tap. The trailing settle is therefore longer than the window by
  // default, and a test that wants a double tap asks for it by name.
  const DOUBLE_MS = 300;

  async function tapAt(pt, settleMs) {
    if (!pt) return false;
    pev("pointerdown", pt.x, pt.y, "touch");
    await sleep(20);
    pev("pointerup", pt.x, pt.y, "touch");
    await sleep(settleMs === undefined ? DOUBLE_MS + 80 : settleMs);
    return true;
  }

  // Two taps well inside the window. The gap is the interval between the two
  // pointerups, which is what the engine measures.
  async function doubleTapAt(pt, second) {
    if (!pt) return false;
    await tapAt(pt, 60);
    return await tapAt(second || pt, DOUBLE_MS + 80);
  }

  async function sheet() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const body = document.getElementById("sheet-body");
    const head = document.getElementById("sheet-head");
    const panel = document.getElementById("sheet");

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

    // One tap is the reading and nothing else: the word lights, so its ruby is
    // showing, and the panel stays shut.
    await tapAt(centre(w));
    add("sheet/one-tap-lights-a-word",
        isLit(w) && !Sheet.isOpen(),
        { lit: isLit(w), open: Sheet.isOpen() });

    // A slow repeat tap is the toggle: it puts the light out rather than
    // opening anything, which is the only way back to a bare page.
    await tapAt(centre(w));
    add("sheet/slow-repeat-tap-unlights",
        !isLit(w) && !Sheet.isOpen(),
        { lit: isLit(w), open: Sheet.isOpen() });

    // Two taps inside the window open the panel, with the gloss unconditional —
    // there is no 意 gate left to withhold it.
    await doubleTapAt(centre(w));
    add("sheet/double-tap-opens-reading-and-gloss",
        Sheet.isOpen() && isLit(w) && !head.hidden && !body.hidden &&
          body.textContent === w.dataset.gloss,
        { open: Sheet.isOpen(), lit: isLit(w), body: body.textContent, want: w.dataset.gloss });

    // The light outlives the panel: reading the gloss must not cost the reading
    // attached to the kanji.
    Sheet.dismiss();
    await sleep(300);
    await doubleTapAt(centre(w));
    const beforeAway = isLit(w) && Sheet.isOpen();
    // A first tap on a DIFFERENT word moves the light and takes the stale panel
    // with it — the invariant that the panel never describes an unlit node.
    let other = null;
    for (const cand of document.querySelectorAll("#track .cell.is-current .w")) {
      if (cand !== w) { other = cand; break; }
    }
    if (other) await tapAt(centre(other));
    add("sheet/light-moves-and-closes-a-stale-panel",
        beforeAway && !!other && isLit(other) && !isLit(w) && !Sheet.isOpen(),
        { before: beforeAway, moved: isLit(other), stale: isLit(w), open: Sheet.isOpen() });

    // The subject is the resolved word, not the node the finger hit: a double
    // tap whose contacts land on the <ruby> and then on the bare kanji beside it
    // is one gesture on one word. This is why the detector cannot live in Track.
    Sheet.dismiss();
    await sleep(300);
    let split = null;
    for (const cand of document.querySelectorAll("#track .cell.is-current .w")) {
      if (cand.dataset.gloss && cand.querySelector("ruby") && bareSpot(cand)) { split = cand; break; }
    }
    if (split) {
      const r = split.querySelector("ruby").getClientRects()[0];
      const onRuby = { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
      await doubleTapAt(onRuby, bareSpot(split) || onRuby);
    }
    add("sheet/double-tap-across-two-nodes-of-one-word",
        !!split && Sheet.isOpen() && isLit(split),
        { found: !!split, open: Sheet.isOpen() });

    Sheet.dismiss();
    await sleep(300);
    w = glossWord() || w;

    // The sheet clears the button bar while the bars are up and drops into the
    // space they occupied once they fade. Both are read off the used value, so
    // a change to --bar-h cannot quietly decouple them.
    Chrome.show();
    await sleep(260);
    const upWith = parseFloat(getComputedStyle(panel).bottom);
    document.body.classList.add("chrome-off");
    await sleep(260);
    const upWithout = parseFloat(getComputedStyle(panel).bottom);
    document.body.classList.toggle("chrome-off", !Chrome.isShown());
    add("sheet/sits-lower-with-the-chrome-hidden",
        upWith > upWithout + 8,
        { shown: upWith, hidden: upWithout });

    Sheet.dismiss();
    await sleep(300);
    // A fixture that has gone missing is a failed row, never a thrown
    // exception: this runs inside an awaited eval, and throwing here aborts the
    // whole harness before marks, persistence and degradation ever run.
    let hit = liveSentence();
    if (!hit) return out.concat([{ name: "sheet/sentence-fixture", ok: false, detail: { at: "one-tap" } }]);
    s = hit.s;
    // A tap on the kana and punctuation between words scopes to the sentence:
    // one tap lights the whole of it, ruby and all, and opens nothing.
    await tapAt(hit.pt);
    add("sheet/one-tap-lights-a-sentence",
        isLit(s) && !Sheet.isOpen(),
        { lit: isLit(s), open: Sheet.isOpen() });

    await tapAt(hit.pt);
    add("sheet/slow-repeat-tap-unlights-a-sentence",
        !isLit(s) && !Sheet.isOpen(),
        { lit: isLit(s), open: Sheet.isOpen() });

    hit = liveSentence();
    if (!hit) return out.concat([{ name: "sheet/sentence-fixture", ok: false, detail: { at: "double-tap" } }]);
    s = hit.s;
    await doubleTapAt(hit.pt);
    // data-en is an HTML string, so the two sides are compared as rendered text
    // rather than as source: a translation carrying an apostrophe ships &#x27;
    // and a name ships <ruby>, and neither is what the panel is asked to show.
    add("sheet/double-tap-opens-a-translation",
        Sheet.isOpen() && isLit(s) && body.textContent === parsed(s.dataset.en).textContent,
        { open: Sheet.isOpen(), lit: isLit(s), body: body.textContent.slice(0, 60) });

    // With the headword and the pitch row both away, the translation is the only
    // thing in the panel, and #sheet-body's top margin — which exists to hold a
    // gloss off the headword — has nothing above it to clear. Left in, it stacks
    // on the panel's own top padding and the line sits low in its box. Measured
    // rather than asserted in the cascade, because a margin that collapses is
    // indistinguishable from one that is overridden until it is on screen.
    {
      const pr = panel.getBoundingClientRect(), br = body.getBoundingClientRect();
      const top = br.top - pr.top, bottom = pr.bottom - br.bottom;
      add("sheet/a-translation-sits-centred", Math.abs(top - bottom) <= 1,
          { top: Math.round(top * 100) / 100, bottom: Math.round(bottom * 100) / 100 });
    }

    // A word inside a lit sentence takes the light off it. Single-slot lighting
    // is what keeps the page from drifting into full-page ふりがな a tap at a
    // time.
    const inner = s.querySelector(".w");
    if (inner) await tapAt(centre(inner));
    add("sheet/a-word-takes-the-light-from-its-sentence",
        !!inner && isLit(inner) && !isLit(s) && !Sheet.isOpen(),
        { found: !!inner, word: isLit(inner), sentence: isLit(s), open: Sheet.isOpen() });

    Sheet.dismiss();
    await sleep(300);
    hit = liveSentence();
    if (!hit) return out.concat([{ name: "sheet/sentence-fixture", ok: false, detail: { at: "tap-away" } }]);
    s = hit.s;
    await doubleTapAt(hit.pt);

    // Dismiss on a tap away — the top bar is outside both the track and the
    // sheet. Chrome.show() first: the bars ship hidden, and a hidden bar is
    // pointer-events: none, so elementFromPoint would hand the tap to the cell
    // behind it and the tap-away handler would correctly decline to fire.
    Chrome.show();
    await sleep(20);
    const topR = document.getElementById("title").getBoundingClientRect();
    pev("pointerdown", Math.round(topR.left + topR.width / 2), Math.round(topR.top + topR.height / 2), "touch");
    await sleep(320);
    add("sheet/dismiss-on-tap-away", !Sheet.isOpen(), { open: Sheet.isOpen() });

    hit = liveSentence();
    if (!hit) return out.concat([{ name: "sheet/sentence-fixture", ok: false, detail: { at: "escape" } }]);
    s = hit.s;
    await doubleTapAt(hit.pt);
    const opened = Sheet.isOpen();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    await sleep(320);
    add("sheet/dismiss-on-escape", opened && !Sheet.isOpen() && !isLit(s),
        { opened, open: Sheet.isOpen(), lit: isLit(s) });

    // An untranslated sentence still lights — the reading is owed whether or not
    // a translation was ever written — but its double tap has nothing to open.
    Sheet.dismiss();
    await sleep(300);
    const bare = s.cloneNode(true);
    bare.removeAttribute("data-en");
    s.parentNode.insertBefore(bare, s);
    s.style.display = "none";
    await sleep(20);
    const spot = bareSpot(bare);
    if (spot) await doubleTapAt(spot);
    add("sheet/untranslated-sentence-lights-but-opens-nothing",
        !!spot && isLit(bare) && !Sheet.isOpen(),
        { spot: !!spot, lit: isLit(bare), open: Sheet.isOpen() });
    // The clone now leaves the DOM under a live light, which is exactly what a
    // recycled cell does to one. The MutationObserver has to notice and call
    // light(null), and the CLONE is where that shows: a "#track .lit" query
    // could not fail here, because a detached node is not inside #track whether
    // the observer ran or not.
    s.style.display = "";
    bare.remove();
    await sleep(120);
    add("sheet/light-drops-when-its-node-is-recycled",
        !bare.classList.contains("lit"),
        { stillLit: bare.classList.contains("lit") });

    // The bars now auto-hide unconditionally. The refusal they used to make
    // while 訳 or 意 was armed went with the gates: there is no armed state left
    // for the bar to be the only cue for.
    Sheet.dismiss();
    await sleep(300);
    const T = track();
    Chrome.show();
    await drag(Math.round(T.clientWidth / 2), Math.round(T.clientHeight / 2), 40, "touch");
    const hid = !Chrome.isShown();
    await release(Math.round(T.clientWidth / 2) + 40, Math.round(T.clientHeight / 2), "touch");
    add("chrome/hides-on-a-live-drag", hid, { hidden: hid });

    // And a tap in the cell's chrome reserve brings them back. That strip is the
    // primary way to summon the bars now that every tap on the text is consumed
    // by the reading gesture, so it is asserted rather than assumed.
    //
    // Chrome.hide() AFTER reset(), never before: reset() goes through
    // Track.goTo, which calls Chrome.show() unconditionally, so a tap dispatched
    // straight after it would find the bars already up and the row could not
    // fail. The precondition is asserted with the result for the same reason.
    await reset();
    Chrome.hide();
    await sleep(30);
    const wasHidden = !Chrome.isShown();
    const cellR = document.querySelector("#track .cell.is-current").getBoundingClientRect();
    const topH = parseFloat(getComputedStyle(document.getElementById("top")).height) || 44;
    await tapAt({ x: Math.round(cellR.left + cellR.width / 2), y: Math.round(cellR.top + topH / 2) });
    add("chrome/a-tap-in-the-reserve-summons-the-bars",
        wasHidden && Chrome.isShown(),
        { hiddenFirst: wasHidden, shown: Chrome.isShown() });
    return out;
  }

  // ---- ふりがな in a translation -------------------------------------------
  // A translation that names someone annotates the name the way the story does,
  // ｜梓《あずさ》, and the panel used to print that markup at the reader because
  // it set textContent. Driven from its own suite because it needs a story whose
  // translations carry furigana; suite_en_ruby runs it once on each of them,
  // because the shapes differ story by story — a name mid-sentence and a
  // possessive ｜松田《まつだ》's are 迷子の手紙's and nowhere else.
  async function enRuby() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const body = document.getElementById("sheet-body");
    const raw = /[｜《》]/;

    // The build converts the markup, so none of it may reach the browser at all.
    // Whole-story, not just the sentence tapped below: an escaper that missed a
    // shape would ship it silently everywhere else.
    const sents = DATA.pages.flat();
    const leaked = sents.filter((s) => raw.test(s.en || ""));
    add("en-ruby/no-translation-ships-raw-markup", leaked.length === 0,
        { leaked: leaked.length, first: (leaked[0] || {}).en });
    const annotated = sents.filter((s) => (s.en || "").includes("<ruby"));
    add("en-ruby/the-story-still-has-annotated-translations", annotated.length > 0,
        { count: annotated.length });

    // Same forward walk as sheet(): turn pages until a screen carries one.
    let a = Paginator.first(), found = false;
    for (let i = 0; i < 80 && a && !found; i++) {
      Track.goTo(a, false);
      await sleep(10);
      found = !!liveAnnotated();
      if (!found) a = Paginator.next(a);
    }
    if (!found) return out.concat([{ name: "en-ruby/fixture", ok: false, detail: { at: "walk" } }]);

    // Resolved again here rather than carried out of the walk above, for the
    // reason liveSentence() states: the track recycles cells, so the node that
    // matched is not necessarily the node now on screen.
    const hit = liveAnnotated();
    if (!hit) return out.concat([{ name: "en-ruby/fixture", ok: false, detail: { at: "tap" } }]);
    await doubleTapAt(hit.pt);
    const rt = body.querySelector("rt");
    // The reading is a real <rt> the browser lays out over the name, and none of
    // the markup that produced it is left anywhere on screen.
    add("en-ruby/the-sheet-renders-a-reading-rather-than-its-markup",
        Sheet.isOpen() && !!rt && !raw.test(body.textContent),
        { open: Sheet.isOpen(), rt: rt && rt.textContent,
          body: body.textContent.slice(0, 60) });

    // And it is visible. rt is opacity 0 globally until the ふ gate, which
    // apply_prefs leaves off, so #sheet-body's opt-out is the only thing showing
    // the panel's reading — and deleting it breaks nothing above, because !!rt
    // is still true and textContent does not care about opacity. The page's own
    // reading is the control: without it "opacity 1" would pass just as well
    // with the gate on, and the row would not be about the opt-out at all.
    let pageRt = null;
    for (const cand of document.querySelectorAll("#track .cell.is-current rt")) {
      if (!cand.closest(".lit, .w.new, .after")) { pageRt = cand; break; }
    }
    const opacityOf = (n) => (n ? getComputedStyle(n).opacity : null);
    add("en-ruby/the-reading-is-visible-while-the-page's-is-not",
        !!rt && !!pageRt && opacityOf(rt) === "1" && opacityOf(pageRt) === "0",
        { panel: opacityOf(rt), page: opacityOf(pageRt), control: !!pageRt });

    // What the panel says out loud is the sentence with the readings taken back
    // out: 梓, never ｜梓《あずさ》 and never 梓あずさ. Read off #live, the live
    // region Chrome.announce writes, so this is the string a screen reader gets
    // and not a restatement of how it was built.
    const want = parsed(hit.s.dataset.en);
    for (const n of want.querySelectorAll("rt, rp")) n.remove();
    const said = document.getElementById("live").textContent;
    add("en-ruby/the-panel-speaks-the-name-without-its-reading",
        said === want.textContent && !raw.test(said) && !!rt && !said.includes(rt.textContent),
        { said: said.slice(0, 60), want: want.textContent.slice(0, 60) });
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

    // The bar is down to four tap targets from seven, which is the whole point
    // of moving ふ/訳/意 into the gesture — but the assertion stays, because
    // nothing about one target too many looks wrong in the source. The symptom
    // is 次 sitting half off the screen edge, which only shows at the narrowest
    // width anyone reads at. scrollWidth is the only honest reading: a flex row
    // that cannot fit overflows its padding box silently and html's
    // overflow: hidden eats the evidence. Checked at every viewport this suite
    // runs at.
    const bar = document.getElementById("bar");
    Chrome.show();
    await frame();
    const spill = bar.scrollWidth - bar.clientWidth;
    add("invariants/button-bar-fits-its-width",
        spill <= 0,
        { spill, width: bar.clientWidth, viewport: innerWidth });

    // The title is centred on the bar, not on the space left over beside the
    // count — it has to carry the count's width AND the flex gap as start
    // padding, and dropping either term slides it off centre by a few pixels.
    const t = document.getElementById("title");
    const tr = t.getBoundingClientRect();
    const inner = tr.left + parseFloat(getComputedStyle(t).paddingLeft);
    const drift = Math.abs((inner + tr.right) / 2 - innerWidth / 2);
    add("invariants/title-is-centred-on-the-bar", drift < 1.5,
        { drift: Math.round(drift * 10) / 10 });
    return out;
  }

  // ---- pitch ------------------------------------------------------------
  // Everything here is read off the rendered page rather than off DATA: the
  // table and the rules are already asserted in Python, and what this cannot
  // know from there is whether any of it reaches the glass.
  function pitchWord(wantBase) {
    for (const w of document.querySelectorAll("#track .cell.is-current .w")) {
      if (w.dataset.pitch === undefined) continue;
      const e = DATA.pitch[Number(w.dataset.pitch)];
      if (!e) continue;
      if (wantBase === undefined || wantBase === ("a" in e ? false : true)) return w;
    }
    return null;
  }

  async function pitch() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const box = document.getElementById("sheet-pitch");

    // Stop on the first screen that has a word with a surface accent, and stay
    // there — walking on would recycle the node out of the track.
    let a = Paginator.first(), w = null;
    for (let i = 0; i < 80 && a; i++) {
      Track.goTo(a, false);
      await sleep(10);
      w = pitchWord(false);
      if (w) break;
      a = Paginator.next(a);
    }
    if (!w) return [{ name: "pitch/fixture", ok: false, detail: { found: false } }];

    const hue = [...w.classList].find((c) => c.startsWith("pitch-"));
    add("pitch/a-marked-word-carries-its-pattern-class", !!hue, { cls: [...w.classList] });

    // Colour is gated on BOTH the setting and the light. Painting it always
    // would bury the 苦手 and 新出 marks under a second colour system.
    Prefs.setAll({ pitch: true });
    await sleep(10);
    const unlit = getComputedStyle(w).color;

    // The guide lives in the sheet, and the sheet is the second tap. The first
    // is the reading, which is a different question with a different answer.
    await doubleTapAt(centre(w));
    const lit = getComputedStyle(w).color;
    add("pitch/lit-word-takes-the-hue-only-when-lit", lit !== unlit, { unlit, lit });

    const line = box.querySelector("svg polyline");
    add("pitch/the-sheet-draws-a-contour", !box.hidden && !!line,
        { hidden: box.hidden, html: box.innerHTML.slice(0, 160) });
    if (!line) return out;

    // One node per mora plus the trailing particle slot, and the polyline has to
    // agree with them: the drop between two of those points IS the diagram.
    const morae = [...(w.dataset.kana || "").replace(/[\u200b-\u200d\u2060\ufeff]/g, "")]
      .reduce((acc, ch) => {
        if ("ャュョァィゥェォゃゅょぁぃぅぇぉ".includes(ch) && acc.length) acc[acc.length - 1] += ch;
        else acc.push(ch);
        return acc;
      }, []);
    const circles = box.querySelectorAll("circle");
    const points = (line.getAttribute("points") || "").trim().split(/\s+/).length;
    add("pitch/one-node-per-mora-plus-the-particle",
        circles.length === morae.length + 1 && points === circles.length,
        { morae: morae.length, nodes: circles.length, points });

    // Read off the diagram rather than recomputed: the count above re-implements
    // the engine's splitter, so the two can agree on a wrong answer. A blank
    // label is what a zero-width character in the reading actually looks like.
    const labels = [...box.querySelectorAll("text.mora")].map(t => t.textContent);
    add("pitch/no-mora-is-blank", labels.length > 0 && labels.every(t => t.trim()),
        { labels });

    // The trailing slot is hollow, because it is not a mora of this word.
    const last = circles[circles.length - 1];
    add("pitch/the-particle-slot-is-drawn-hollow", last && last.classList.contains("ghost"),
        { cls: last ? [...last.classList] : null });

    // The diagram has to answer the reader's theme, not the OS's. That is the
    // defect a self-contained prefers-color-scheme block carries, so an explicit
    // choice is asserted to move the stroke in both directions.
    Prefs.setAll({ theme: "light" });
    await sleep(10);
    const light = getComputedStyle(line).stroke;
    Prefs.setAll({ theme: "dark" });
    await sleep(10);
    const dark = getComputedStyle(line).stroke;
    add("pitch/an-explicit-theme-repaints-the-contour", light !== dark && !!light && !!dark,
        { light, dark });
    Prefs.setAll({ theme: "system" });
    await sleep(10);

    // Turning the setting off leaves the guide in the sheet and takes it off the
    // page: the sheet is where it was asked for, the page is where it intrudes.
    //
    // Compared against the LIT colour, not the pre-tap one. A build that painted
    // the hue unconditionally would have coloured the word before the tap too,
    // so "unchanged since before the tap" is a test that such a build passes.
    Prefs.setAll({ pitch: false });
    await sleep(10);
    const off = getComputedStyle(w).color;
    add("pitch/the-setting-off-keeps-the-sheet-and-clears-the-page",
        !box.hidden && off !== lit && off === unlit,
        { hidden: box.hidden, off, lit, unlit });
    Prefs.setAll({ pitch: true });

    // A word that only resolved through its dictionary form must say so. Without
    // the label the diagram for 食べた silently reads タベル.
    const fb = pitchWord(true);
    if (fb) {
      await doubleTapAt(centre(fb));
      const note = box.querySelector(".base");
      add("pitch/a-辞書形-fallback-names-the-word-it-drew",
          !!note && note.textContent.indexOf("辞書形") === 0,
          { text: note ? note.textContent : null, word: fb.dataset.t });
    }
    return out;
  }

  // ---- lit-sentence colour, and the 墨 session -----------------------------
  async function highlight() {
    const out = [];
    const add = (name, ok, detail) => out.push({ name, ok: !!ok, detail });
    const hue = (w) => getComputedStyle(w).color;
    const pitched = (s) => [...s.querySelectorAll(".w")]
      .filter(w => [...w.classList].some(c => c.startsWith("pitch-")));

    // A sentence carrying several pitched words AND a bare spot to tap.
    let a = Paginator.first(), sent = null, spot = null;
    for (let i = 0; i < 80 && a; i++) {
      Track.goTo(a, false); await sleep(10);
      for (const cand of document.querySelectorAll("#track .cell.is-current .s[data-en]")) {
        if (pitched(cand).length < 3) continue;
        const pt = bareSpot(cand);
        if (pt) { sent = cand; spot = pt; break; }
      }
      if (sent) break;
      a = Paginator.next(a);
    }
    if (!sent) return [{ name: "highlight/fixture", ok: false, detail: { found: false } }];

    Prefs.setAll({ pitch: true, ink: false });
    await sleep(10);
    const words = pitched(sent);
    const before = words.map(hue);

    // Tapping a bare spot lights the whole sentence. That is the one gesture
    // that shows more than one hue at once.
    await tapAt(spot);
    const after = words.map(hue);
    const moved = words.filter((w, i) => after[i] !== before[i]).length;
    add("highlight/a-lit-sentence-colours-its-words", isLit(sent) && moved >= 3,
        { lit: isLit(sent), words: words.length, moved });

    // And it really is multicolour: a sentence of one hue would pass the above.
    const distinct = new Set(after).size;
    add("highlight/and-shows-more-than-one-hue", distinct >= 2,
        { distinct, colours: [...new Set(after)] });

    // Unlighting puts every one of them back, not just the last.
    await tapAt(spot);
    const reverted = words.filter((w, i) => hue(w) === before[i]).length;
    add("highlight/unlighting-reverts-every-word", !isLit(sent) && reverted === words.length,
        { lit: isLit(sent), reverted, of: words.length });

    // 高低 off is the whole gate: the same tap must colour nothing.
    Prefs.setAll({ pitch: false });
    await sleep(10);
    await tapAt(spot);
    const off = words.filter((w, i) => hue(w) !== before[i]).length;
    add("highlight/the-setting-off-leaves-a-lit-sentence-plain", isLit(sent) && off === 0,
        { lit: isLit(sent), changed: off });
    await tapAt(spot);
    Prefs.setAll({ pitch: true });
    await sleep(10);

    // ---- 墨 ---------------------------------------------------------------
    const mark = document.querySelector("#track .cell.is-current .w.weak")
              || document.querySelector("#track .w.weak");
    const fresh = document.querySelector("#track .cell.is-current .w.new")
               || document.querySelector("#track .w.new");
    const emColour = (el) => {
      const cs = getComputedStyle(el);
      return cs.webkitTextEmphasisColor || cs.textEmphasisColor;
    };
    const emStyle = (el) => {
      const cs = getComputedStyle(el);
      return (cs.webkitTextEmphasisStyle || cs.textEmphasisStyle || "").replace(/"/g, "");
    };
    const inkColour = getComputedStyle(document.querySelector("#track .cell.is-current .s")).color;

    if (mark) {
      const colourOn = emColour(mark), styleOn = emStyle(mark);
      Prefs.setAll({ ink: true });
      await sleep(10);
      add("highlight/墨-takes-the-colour-off-苦手",
          emColour(mark) !== colourOn && emColour(mark) === inkColour,
          { before: colourOn, after: emColour(mark), ink: inkColour });
      // The mark itself has to survive: 苦手 and 新出 are told apart by shape.
      add("highlight/墨-keeps-the-sesame", emStyle(mark) === styleOn && /sesame/.test(emStyle(mark)),
          { before: styleOn, after: emStyle(mark) });
      Prefs.setAll({ ink: false });
      await sleep(10);
      add("highlight/墨-off-puts-the-colour-back", emColour(mark) === colourOn,
          { restored: emColour(mark), want: colourOn });
    }
    if (fresh) {
      const rt = fresh.querySelector("rt");
      const rubyOn = rt && getComputedStyle(rt).color;
      Prefs.setAll({ ink: true });
      await sleep(10);
      add("highlight/墨-takes-the-colour-off-新出-ruby",
          !!rt && getComputedStyle(rt).color !== rubyOn,
          { before: rubyOn, after: rt && getComputedStyle(rt).color });
      // The reading stays SHOWN, which is the promise 新出 carries.
      add("highlight/墨-leaves-the-新出-reading-showing",
          !!rt && parseFloat(getComputedStyle(rt).opacity) === 1,
          { opacity: rt && getComputedStyle(rt).opacity });
      Prefs.setAll({ ink: false });
      await sleep(10);
    }

    // The two settings are independent: 墨 quiets the page, 高低 answers a tap.
    const w = pitched(sent)[0];
    const plain = hue(w);
    Prefs.setAll({ ink: true, pitch: true });
    await sleep(10);
    await tapAt(centre(w));
    add("highlight/墨-does-not-suppress-高低-on-a-tap", hue(w) !== plain,
        { plain, lit: hue(w) });
    await tapAt(centre(w));
    Prefs.setAll({ ink: false });
    return out;
  }

  return { walk, atoms, paintcache, gestures, sheet, enRuby, pitch, highlight, selection, marks, snap, binding, invariants, sleep,
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


# A fake GitHub gist API, installed before any document script runs, so sync.js
# exercises its real request and merge paths with no network. The reader
# fixtures are built by build.render(), which inlines the engine and links
# nothing — so sync.js is injected here too, ahead of the stub's own consumers.
#
# window.GIST is the server's state and its log. Tests drive `doc` (what the
# remote holds), `status` (force one failure) and `delay` (hold a response open
# long enough to turn a page underneath it), and read `calls` back.
GIST_STUB = r"""
(() => {
  const FILE = "japanese-stories-progress.json";
  // sessionStorage, not a plain object: the init script re-runs on every
  // document, so a fresh reload would otherwise reset the server the test just
  // configured — and half these cases are about what happens ACROSS a reload.
  // sessionStorage also survives the localStorage.clear() the tests lean on.
  const KEY = "harness:gist";
  const load = () => {
    try { return JSON.parse(sessionStorage.getItem(KEY)) || null; } catch (e) { return null; }
  };
  // `doc` is the progress half and `revs` the reviews half, kept as two fields
  // so every existing test that drives `doc` still means what it meant.
  const G = load() || { id: "g1", doc: null, revs: null, calls: [], status: 0, delay: 0, rev: 1 };
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(G)); } catch (e) {} };
  // Which document made a call. The outgoing document gets a pagehide flush on
  // every reload, and that flush pushes — so a log cleared before a reload still
  // acquires one request from the page that is leaving. Tests that care which
  // request came first filter on this rather than on position.
  const DOC = Math.random().toString(36).slice(2);
  window.GIST = G;
  window.GISTsave = save;
  window.GISTdoc = DOC;
  save();

  // Only what sync.js actually touches. A real Response would drag in body
  // stream semantics that have nothing to do with what is under test.
  const reply = (status, bodyObj, etag) => {
    const res = {
      status: status,
      ok: status >= 200 && status < 300,
      headers: { get: (k) => (String(k).toLowerCase() === "etag" ? etag || null : null) },
      json: () => Promise.resolve(bodyObj),
    };
    return G.delay ? new Promise((r) => setTimeout(() => r(res), G.delay)) : Promise.resolve(res);
  };

  const wrap = (map, revs) => ({
    id: G.id,
    files: {
      [FILE]: {
        content: JSON.stringify(
          { v: 1, progress: map || {}, reviews: revs || {} }, null, 2),
      },
    },
  });

  window.fetch = (url, opts) => {
    opts = opts || {};
    const m = opts.method || "GET";
    const h = opts.headers || {};
    const sent = opts.body ? JSON.parse(opts.body) : null;
    G.calls.push({ method: m, url: String(url), doc: DOC,
                   inm: h["If-None-Match"] || null, body: sent });
    if (G.status) { const st = G.status; G.status = 0; save(); return reply(st, {}, null); }
    const etag = 'W/"' + G.rev + '"';
    if (m === "GET" && String(url).indexOf("/gists?") >= 0) {
      save();
      return reply(200, G.doc === null ? [] : [{ id: G.id, files: { [FILE]: {} } }], null);
    }
    if (m === "GET") {
      save();
      if (h["If-None-Match"] && h["If-None-Match"] === etag) return reply(304, null, etag);
      return reply(200, wrap(G.doc, G.revs), etag);
    }
    if (m === "POST" || m === "PATCH") {
      const doc = JSON.parse(sent.files[FILE].content);
      G.doc = doc.progress;
      G.revs = doc.reviews;
      G.rev++;
      save();
      return reply(m === "POST" ? 201 : 200, wrap(G.doc, G.revs), 'W/"' + G.rev + '"');
    }
    save();
    return reply(404, {}, null);
  };
})();
"""


def sync_stub():
    """The stub and the real sync.js, as one init script in that order."""
    return GIST_STUB + "\n" + (REPO / "scripts" / "sync.js").read_text(encoding="utf-8")


def gist(br, **fields):
    """Configure the fake server and persist it across the next reload."""
    for k, v in fields.items():
        br.eval(f"window.GIST.{k} = " + json.dumps(v))
    br.eval("window.GISTsave()")


def connect(br, doc=None, revs=None):
    """Put the device in the connected state without going through the UI."""
    gist(br, doc=doc, revs=revs, calls=[], rev=1)
    br.eval(
        "localStorage.setItem('japanese-stories:sync',"
        " JSON.stringify({token: 't', gist: 'g1', etag: ''}))"
    )


SYNC_SLUG = "tokei-no-oto"


@functools.lru_cache(maxsize=None)
def built_pages(slug):
    """How many pages `slug` has, derived from its source rather than written down.

    From the source and not from docs/, because docs/ is what these suites are
    testing: a count read off the artifact agrees with the artifact even when the
    artifact is wrong.
    """
    _, pages = build.parse_story(stats.STORIES / f"{slug}.txt")
    return len(pages)


def rec(page, at, slug=SYNC_SLUG, **kw):
    """A stored progress record, with `of` matching the story it is for.

    `of` was the literal 25 for a long time — 時計の音's count before the
    revisions took it to 24. reader.js restores which screen of a page you were
    on only `if (saved.of === of)`, on the argument that a different page count
    means the story changed underneath the record. A hardcoded count the story
    has left behind can never satisfy that, so the branch was dead for every
    record this factory built, in the sync, manage, index and review suites at
    once. It went quiet rather than red because every rec() sets sub: 0, so the
    restore it skipped had nothing to restore.

    Pass `of=` explicitly where a mismatch is the point — a record from a device
    that read an older build is a real thing to test, and it is then stated
    rather than inherited.
    """
    r = {"page": page, "sub": 0, "of": built_pages(slug), "done": False, "at": at}
    r.update(kw)
    return r


def suite_sync(br, rep, base):
    ident = br.init_script(sync_stub())
    try:
        br.emulate(*PHONE[1:])
        slug = "tokei-no-oto"
        br.goto(f"{base}/{slug}.html")
        br.eval("localStorage.clear()")

        # ---- the merge rule, as a pure function -----------------------------
        M = "Sync.merge(%s, %s)"
        older, newer = rec(3, 1000), rec(9, 2000)
        got = br.eval(M % (json.dumps({slug: older}), json.dumps({slug: newer})))
        rep.add("sync", "merge-takes-the-later-stamp", got[slug]["page"] == 9, got)
        got = br.eval(M % (json.dumps({slug: newer}), json.dumps({slug: older})))
        rep.add("sync", "merge-is-order-independent", got[slug]["page"] == 9, got)

        # Reading only ever turns `done` on, so an unstamped pair ORs: a device
        # that has not been told a story was finished must not un-finish it.
        got = br.eval(M % (json.dumps({slug: rec(3, 3000)}),
                           json.dumps({slug: rec(9, 1000, done=True)})))
        rep.add("sync", "done-survives-a-newer-unfinished-record",
                got[slug]["done"] is True and got[slug]["page"] == 3, got)

        # A hand correction carries doneAt, and the later doneAt then decides in
        # BOTH directions — which is the only thing that can take a 読了 away.
        got = br.eval(M % (json.dumps({slug: rec(9, 1000, done=True, doneAt=1000)}),
                           json.dumps({slug: rec(3, 3000, done=False, doneAt=4000)})))
        rep.add("sync", "a-later-hand-unmark-beats-an-earlier-done",
                got[slug]["done"] is False, got)
        got = br.eval(M % (json.dumps({slug: rec(3, 3000, done=False, doneAt=4000)}),
                           json.dumps({slug: rec(9, 5000, done=True, doneAt=5000)})))
        rep.add("sync", "a-later-hand-mark-beats-an-earlier-unmark",
                got[slug]["done"] is True, got)

        got = br.eval(M % (json.dumps({slug: rec(3, 1000)}), json.dumps({"v": 1})))
        rep.add("sync", "merge-drops-a-non-record-key", "v" not in got, got)

        # ---- boot: the remote is ahead and nothing has been touched ---------
        connect(br, {slug: rec(9, int(time.time() * 1000) + 60000)})
        br.reload()
        br.eval(LIB)
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        s = br.eval("H.snap()")
        rep.add("sync", "boot-adopts-a-newer-remote-position", s["addr"]["page"] == 8,
                {"addr": s["addr"]})

        # ---- boot: the reader moved first, so local intent wins -------------
        # Seeded from the story's length rather than at a literal 20. reader.js
        # clamps a stored page to of - 1 on the entry path, so a seed past the
        # end lands on the last page instead, and the assertion below stops being
        # able to fail: it would be asserting the reader is not at an index the
        # clamp has made unreachable. Four from the end is inside any story the
        # corpus holds and leaves room for the step.
        seeded = built_pages(slug) - 4
        connect(br, {slug: rec(seeded, int(time.time() * 1000) + 60000)})
        gist(br, delay=1200)
        br.reload()
        br.eval(LIB)
        br.eval("Track.step(1)")
        br.eval("new Promise(r => setTimeout(r, 1800))", await_promise=True)
        s = br.eval("H.snap()")
        rep.add("sync", "a-turned-page-is-not-yanked-by-a-late-pull",
                s["addr"]["page"] != seeded - 1, {"addr": s["addr"], "seeded": seeded})
        gist(br, delay=0)

        # ---- a no-op push writes nothing ------------------------------------
        br.eval("localStorage.clear()")
        connect(br, None)
        mine = {slug: rec(4, 1000)}
        br.eval("localStorage.setItem('japanese-stories:progress'," + json.dumps(json.dumps(mine)) + ")")
        gist(br, doc=mine, calls=[])
        br.eval("Sync.push()", await_promise=True)
        calls = br.eval("window.GIST.calls")
        rep.add("sync", "an-identical-map-fires-no-PATCH",
                not any(c["method"] == "PATCH" for c in calls), calls)

        # ---- a push that has something to say does write ---------------------
        gist(br, calls=[])
        ahead = {slug: rec(12, 9000)}
        br.eval("localStorage.setItem('japanese-stories:progress'," + json.dumps(json.dumps(ahead)) + ")")
        br.eval("Sync.push()", await_promise=True)
        calls = br.eval("window.GIST.calls")
        remote = br.eval("window.GIST.doc")
        rep.add("sync", "a-changed-map-is-PATCHed",
                any(c["method"] == "PATCH" for c in calls) and remote[slug]["page"] == 12,
                {"calls": [c["method"] for c in calls], "remote": remote})

        # ---- a stored ETag with a cold cache must not wedge the device ------
        # The ETag outlives the page and the body it describes does not, so a
        # conditional first request would 304 into "unchanged from nothing" and,
        # because the ETag survives that, never sync again.
        br.eval(
            "localStorage.setItem('japanese-stories:sync',"
            " JSON.stringify({token: 't', gist: 'g1', etag: 'W/\"1\"'}))"
        )
        br.eval("localStorage.removeItem('japanese-stories:progress')")
        gist(br, calls=[])
        br.reload()
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)
        first = br.eval(
            "window.GIST.calls.filter(c => c.method === 'GET' && c.doc === window.GISTdoc)[0] || null")
        r = br.eval("Sync.pull()", await_promise=True)
        rep.add("sync", "a-cold-cache-does-not-send-a-stored-ETag",
                bool(first) and first["inm"] is None, first)
        rep.add("sync", "and-so-the-remote-still-arrives", r["ok"] is True and bool(r["map"]), r)

        # ---- failure leaves a working reader --------------------------------
        # The clear has to happen in a document that is then reloaded from a
        # known position: reloading fires pagehide, and Progress flushes the
        # OUTGOING page back into the store the line above just emptied.
        br.goto_plain(f"{base}/blank.html")
        br.eval("localStorage.clear()")
        connect(br, {slug: rec(9, 9_000_000_000_000)})
        gist(br, status=401)
        br.goto(f"{base}/{slug}.html")
        br.eval(LIB)
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        s = br.eval("H.snap()")
        rep.add("sync", "a-401-still-paints-the-reader", s["painted"], s["boxReport"])
        rep.add("sync", "a-401-does-not-move-the-page", s["addr"]["page"] == 0, {"addr": s["addr"]})
        br.eval("Track.step(1)")
        # The turn animates, so the address is still the old one until the snap
        # settles; reading it straight back tests the scheduler, not the turn.
        br.eval("new Promise(r => setTimeout(r, 600))", await_promise=True)
        s2 = br.eval("H.snap()")
        rep.add("sync", "a-401-does-not-stop-a-page-turn", s2["addr"]["page"] == 1, {"addr": s2["addr"]})
        rep.add("sync", "a-401-is-reported-as-rejected",
                br.eval("Sync.status().state") == "rejected", br.eval("Sync.status()"))

        # ---- ?nosync is a reproducible disconnection ------------------------
        br.goto_plain(f"{base}/blank.html")
        br.eval("localStorage.clear()")
        connect(br, {slug: rec(9, 9_000_000_000_000)})
        gist(br, calls=[])
        br.goto(f"{base}/{slug}.html?nosync")
        br.eval(LIB)
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        s = br.eval("H.snap()")
        rep.add("sync", "nosync-makes-no-requests", br.eval("window.GIST.calls.length") == 0,
                br.eval("window.GIST.calls"))
        rep.add("sync", "nosync-leaves-the-position-local", s["addr"]["page"] == 0, {"addr": s["addr"]})
    finally:
        br.drop_init_script(ident)


def suite_manage(br, rep, base):
    """The contents page's 編集 controls, against the same fake gist."""
    ident = br.init_script(sync_stub())
    try:
        br.emulate(*PHONE[1:])
        slug = "tokei-no-oto"
        br.goto_plain(f"{base}/blank.html")
        br.eval("localStorage.clear()")
        connect(br, None)
        br.goto_plain(f"{base}/index.html")
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)

        cell = f"document.querySelector('.cell[data-slug=\"{slug}\"]')"
        # Read off the row rather than written down here. contents.js clamps
        # every stepper move against `data-pages`, which index.py emits from the
        # built story, so a revision that repaginates a story moves the expected
        # values with it. Three cases below carried 25's last-page-minus-one as
        # a literal 24 and went stale the moment 時計の音 lost a page.
        pages = int(br.eval(f"{cell}.dataset.pages"))
        rep.add("manage", "controls-start-hidden", br.eval(f"{cell}.querySelector('.manage').hidden"),
                None)
        br.eval("document.getElementById('edit').click()")
        rep.add("manage", "the-edit-toggle-reveals-them",
                br.eval(f"{cell}.querySelector('.manage').hidden") is False, None)

        # A story with no record at all must be markable, which is the case a
        # record-patching implementation gets wrong.
        br.eval(f"{cell}.querySelector('[data-act=\"done\"]').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        rep.add("manage", "marking-read-writes-done-and-a-doneAt",
                got[slug]["done"] is True and got[slug].get("doneAt", 0) > 0, got)
        rep.add("manage", "marking-read-sends-the-position-to-the-end",
                got[slug]["page"] == pages, got)
        rep.add("manage", "the-row-repaints-as-read",
                br.eval(f"{cell}.classList.contains('done')"), None)

        br.eval(f"{cell}.querySelector('[data-act=\"done\"]').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        rep.add("manage", "un-marking-is-possible-at-all", got[slug]["done"] is False, got)

        br.eval(f"{cell}.querySelector('[data-act=\"dec\"]').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        # One tap back from 読了's end position, which the case above pinned at
        # `pages`.
        rep.add("manage", "the-stepper-moves-the-page", got[slug]["page"] == pages - 1, got)
        rep.add("manage", "the-stepper-resets-the-screen-index", got[slug]["sub"] == 0, got)

        # Import is a merge, not a replace: pasting yesterday's export must not
        # pull a story backwards.
        stale = {slug: rec(2, 1)}
        # The box is revealed first, deliberately. 読み込み on a hidden box only
        # opens and clears it, so the two-click idiom parses an empty string and
        # the import under test never happens.
        br.eval("document.getElementById('box').hidden = false")
        br.eval("document.getElementById('box').value = " + json.dumps(json.dumps(stale)))
        br.eval("document.getElementById('imp').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        # Unmoved from the stepper's result: the stale record loses the merge.
        rep.add("manage", "import-merges-rather-than-replaces", got[slug]["page"] == pages - 1, got)

        br.eval(f"{cell}.querySelector('[data-act=\"clear\"]').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        # A deletion cannot travel — an absent slug merges to whatever the gist
        # still holds — so a clear leaves a dated, page-less tombstone instead.
        rep.add("manage", "clearing-one-story-leaves-an-unread-tombstone",
                slug in got and got[slug].get("page") is None and got[slug]["done"] is False, got)
        rep.add("manage", "and-the-cleared-row-paints-as-unread",
                br.eval(f"{cell}.querySelector('.prog').hidden") is True
                and br.eval(f"{cell}.classList.contains('done')") is False, None)
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)
        remote = br.eval("window.GIST.doc") or {}
        rep.add("manage", "and-the-tombstone-reaches-the-gist",
                slug in remote and remote[slug].get("page") is None, remote)

        # The store has to be openable. A gist was chosen over a KV namespace
        # precisely so the record could be read and corrected by hand, and an id
        # that only ever lives in localStorage cannot be.
        br.eval("document.getElementById('disc').click()")
        rep.add("manage", "disconnecting-withdraws-the-gist-link",
                br.eval("document.getElementById('glink').hidden") is True, None)
        br.eval("document.getElementById('tok').value = 't'")
        br.eval("document.getElementById('conn').click()")
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        rep.add("manage", "connecting-surfaces-a-link-to-the-gist",
                br.eval("document.getElementById('glink').hidden") is False
                and br.eval("document.getElementById('glink').href")
                == "https://gist.github.com/g1",
                br.eval("document.getElementById('glink').href"))
        rep.add("manage", "and-the-token-does-not-stay-in-the-field",
                br.eval("document.getElementById('tok').value") == "", None)

        # Two taps inside one millisecond used to carry the same `at`, and the
        # merge gives a tie to the remote — so the second tap lost to the gist's
        # copy of the first and silently undid itself. The clock is frozen
        # rather than raced: a defect that reproduces half the time is not a
        # test, and this is exactly the condition, not an approximation of it.
        br.eval("window.__now = Date.now; Date.now = function () { return 4e12; };")
        try:
            br.eval(f"{cell}.querySelector('[data-act=\"dec\"]').click()")
            br.eval(f"{cell}.querySelector('[data-act=\"dec\"]').click()")
            br.eval("new Promise(r => setTimeout(r, 500))", await_promise=True)
            got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
            # From the clear's page-less tombstone, the first tap lands on
            # `pages` and the second one back. `pages - 1` is what distinguishes
            # two taps from one; a lost second tap leaves `pages`.
            rep.add("manage", "two-taps-in-one-millisecond-both-count",
                    got[slug]["page"] == pages - 1, got)
        finally:
            br.eval("Date.now = window.__now")
    finally:
        br.drop_init_script(ident)



def suite_index(br, rep, base):
    """The contents page's own shape: 続き, the 詳細 disclosure, and auto-open."""
    ident = br.init_script(sync_stub())
    try:
        br.emulate(*PHONE[1:])
        first, mid, late = "tokei-no-oto", "maigo-no-tegami", "shuden"

        def load(progress=None, reviews=None):
            br.goto_plain(f"{base}/blank.html")
            br.eval("localStorage.clear()")
            for key, val in (("progress", progress), ("reviews", reviews)):
                if val is not None:
                    br.eval("localStorage.setItem('japanese-stories:%s', %s)"
                            % (key, json.dumps(json.dumps(val))))
            br.goto_plain(f"{base}/index.html")
            br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)

        res = "document.getElementById('resume')"
        label = f"{res}.querySelector('.rlabel').textContent"
        title = f"{res}.querySelector('.rtitle').textContent"
        pct = f"{res}.querySelector('.rpct').textContent"
        cell = lambda slug: f"document.querySelector('.cell[data-slug=\"{slug}\"]')"

        # ---- 続き ------------------------------------------------------------
        load()
        rep.add("index", "an-unread-corpus-points-at-the-first-story",
                br.eval(f"{res}.hidden") is False and br.eval(label) == "次へ"
                and br.eval(title) == "時計の音", br.eval(title))
        rep.add("index", "and-links-to-it",
                br.eval(f"{res}.getAttribute('href')") == "tokei-no-oto.html",
                br.eval(f"{res}.getAttribute('href')"))

        # `of` is deliberately NOT the built count here, and the two were the
        # same number until 2026-09-19: the record said 16, 迷子の手紙 is 16
        # pages, and a row printing either one passed. The case names the built
        # count as the thing it checks, so the record has to disagree with it for
        # the check to mean anything.
        mid_pages = built_pages(mid)
        load({mid: rec(7, 1000, of=mid_pages + 83)})
        rep.add("index", "a-story-in-hand-becomes-the-continue-row",
                br.eval(label) == "続き" and br.eval(title) == "迷子の手紙", br.eval(title))
        # The one thing the row exists to do. Everything else about it is a
        # label, and a label can be right while the link points anywhere.
        rep.add("index", "and-links-back-into-that-story",
                br.eval(f"{res}.getAttribute('href')") == "maigo-no-tegami.html",
                br.eval(f"{res}.getAttribute('href')"))
        # The built page count on the card, not the `of` the record carries —
        # that is only what some device believed when it last read.
        rep.add("index", "with-the-position-against-the-built-page-count",
                br.eval(pct) == f"7 / {mid_pages}", br.eval(pct))

        # Two open at once is the two-device case, and the later stamp is the
        # one you are actually in the middle of.
        load({mid: rec(7, 1000, of=16), late: rec(3, 9000, of=23)})
        rep.add("index", "the-later-of-two-open-stories-wins",
                br.eval(title) == "終電", br.eval(title))

        # An unfinished story with no page at all — a 消去 tombstone — is not
        # something to continue, but it is still something to read next.
        load({mid: {"sub": 0, "of": 16, "done": False, "doneAt": 1000, "at": 1000}})
        rep.add("index", "a-tombstoned-story-is-next-rather-than-continued",
                br.eval(label) == "次へ", br.eval(label))

        load()
        every = br.eval("[].map.call(document.querySelectorAll('.cell[data-slug]'),"
                        " function (c) { return c.dataset.slug; })")
        rep.add("index", "the-page-renders-every-story-in-the-corpus",
                len(every) == len(json.loads((REPO / "scripts" / "corpus.json")
                                             .read_text(encoding="utf-8"))["stories"]), every)
        # The footer that used to be asserted here repeated those same titles,
        # generated, under a list made of them. It is gone rather than fixed.

        # ---- 案内 --------------------------------------------------------------
        # The help and the sync setup are a panel now, not two blocks at the foot
        # of the reading column. Containment rather than visibility: markup that
        # merely sits in the list with display:none would pass a hidden check and
        # still be in the list.
        disp = "getComputedStyle(document.getElementById('guide')).display"
        keys = "getComputedStyle(document.querySelector('#guide .keys')).display"
        rep.add("index", "the-help-and-the-sync-setup-live-in-the-panel",
                br.eval("!!document.querySelector('#guide .keys')")
                and br.eval("!!document.querySelector('#guide #sync')"), None)
        rep.add("index", "which-is-shut-on-arrival",
                br.eval("document.getElementById('guide').hasAttribute('open')") is False
                and br.eval(disp) == "none", br.eval(disp))
        br.eval("document.getElementById('guide-open').click()")
        rep.add("index", "the-guide-button-opens-it",
                br.eval("document.getElementById('guide').hasAttribute('open')")
                and br.eval(keys) != "none", br.eval(keys))
        br.eval("document.getElementById('guide-close').click()")
        rep.add("index", "and-the-close-button-shuts-it",
                br.eval("document.getElementById('guide').hasAttribute('open')") is False
                and br.eval(disp) == "none", br.eval(disp))
        load({slug: rec(1, 1000, done=True, doneAt=1000) for slug in every})
        rep.add("index", "a-finished-corpus-withdraws-the-row",
                br.eval(f"{res}.hidden") is True, None)

        # ---- 詳細 ------------------------------------------------------------
        load()
        c = cell(first)
        vis = lambda sel: f"getComputedStyle({c}.querySelector('{sel}')).display !== 'none'"
        rep.add("index", "a-row-starts-collapsed",
                br.eval(f"{c}.classList.contains('open')") is False, None)
        rep.add("index", "and-the-stars-and-chips-are-not-rendered",
                br.eval(vis(".rate")) is False and br.eval(vis(".chips")) is False, None)
        rep.add("index", "the-blurb-and-the-title-stay",
                br.eval(vis(".sum")) and br.eval(vis("h2")), None)
        br.eval(f"{c}.querySelector('.disc').click()")
        rep.add("index", "the-disclosure-opens-the-row",
                br.eval(vis(".rate")) and br.eval(vis(".chips")), None)
        rep.add("index", "and-says-so",
                br.eval(f"{c}.querySelector('.disc').getAttribute('aria-expanded')") == "true",
                None)
        # data-act is read by one delegated listener whose last branch is the
        # page stepper, so an action it does not know turns a page.
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress') || '{}')")
        rep.add("index", "and-does-not-touch-the-progress-record", got == {}, got)
        br.eval(f"{c}.querySelector('.disc').click()")
        rep.add("index", "and-closes-again", br.eval(vis(".rate")) is False, None)

        # The box cannot take focus inside a display:none subtree, so paintR's
        # focused-box guard would not hold and a pull would overwrite a note
        # being typed. Revealing the box has to open the row that holds it.
        load()
        br.eval(f"{c}.querySelector('.notebtn').click()")
        rep.add("index", "the-note-button-opens-the-row-it-needs",
                br.eval(f"{c}.classList.contains('open')"), None)
        rep.add("index", "and-the-box-really-does-hold-focus",
                br.eval(f"document.activeElement === {c}.querySelector('textarea.note')"), None)

        # ---- 読了 -------------------------------------------------------------
        # Measured against the same row unread, on the same viewport, because
        # the claim is about what a finished story costs the scroll — not about
        # which elements happen to be display:none.
        load()
        tall = br.eval(f"{c}.getBoundingClientRect().height")
        load({first: rec(25, 1000, done=True, doneAt=1000)},
             {first: {"stars": 4, "at": 1000}})
        short = br.eval(f"{c}.getBoundingClientRect().height")
        rep.add("index", "a-finished-row-drops-the-blurb-the-reading-and-the-bar",
                br.eval(vis(".sum")) is False and br.eval(vis(".prog")) is False
                and br.eval(vis(".rt")) is False, None)
        rep.add("index", "and-is-flagged-read",
                br.eval(vis(".disc .fin"))
                and br.eval(f"{c}.querySelector('.disc .fin').textContent") == "了", None)
        rep.add("index", "and-costs-less-than-half-the-scroll",
                short < tall / 2, [short, tall])
        # Finishing a story is not being done with it, and the flag sits in a
        # button while the title sits in the anchor precisely so both survive.
        rep.add("index", "with-the-title-still-linking-into-the-story",
                br.eval(f"{c}.querySelector('a.card').getAttribute('href')")
                == "tokei-no-oto.html", None)
        rep.add("index", "and-44px-of-disclosure-to-open-it-with",
                br.eval(f"{c}.querySelector('.disc').getBoundingClientRect().height") >= 44,
                br.eval(f"{c}.querySelector('.disc').getBoundingClientRect().height"))
        br.eval(f"{c}.querySelector('.disc').click()")
        rep.add("index", "the-disclosure-restores-the-whole-card",
                br.eval(vis(".sum")) and br.eval(vis(".prog")) and br.eval(vis(".rate")),
                None)
        rep.add("index", "and-withdraws-the-flag-with-it",
                br.eval(vis(".disc .fin")) is False, None)
        load({first: rec(7, 1000)})
        rep.add("index", "an-unfinished-row-keeps-its-blurb-and-its-bar",
                br.eval(vis(".sum")) and br.eval(vis(".prog"))
                and br.eval(vis(".disc .fin")) is False, None)

        # ---- auto-open -------------------------------------------------------
        # The stars do not sit behind 編集 because a rating is given on the way
        # out of a story. A collapsed row would put them back behind a tap.
        load({first: rec(25, 1000, done=True, doneAt=1000)})
        rep.add("index", "a-finished-unrated-story-opens-itself",
                br.eval(f"{c}.classList.contains('open')"), None)
        load({first: rec(25, 1000, done=True, doneAt=1000)},
             {first: {"stars": 4, "at": 1000}})
        rep.add("index", "a-rated-one-does-not",
                br.eval(f"{c}.classList.contains('open')") is False, None)
        load({first: rec(7, 1000)})
        rep.add("index", "nor-does-one-still-being-read",
                br.eval(f"{c}.classList.contains('open')") is False, None)

        # A default that reasserts itself is not a default. The repaint is
        # driven by the stepper rather than by a star, deliberately: rating the
        # story would also remove the condition under test, and the assertion
        # would pass with the guard deleted.
        load({first: rec(25, 1000, done=True, doneAt=1000)})
        br.eval(f"{c}.querySelector('.disc').click()")
        rep.add("index", "the-disclosure-closes-an-auto-opened-row",
                br.eval(f"{c}.classList.contains('open')") is False, None)
        br.eval(f"{c}.querySelector('[data-act=\"dec\"]').click()")
        br.eval("new Promise(r => setTimeout(r, 200))", await_promise=True)
        rep.add("index", "and-it-stays-closed-through-a-repaint",
                br.eval(f"{c}.classList.contains('open')") is False, None)
        rep.add("index", "with-the-story-still-finished-and-unrated",
                br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
                [first]["done"] is True
                and not br.eval("JSON.parse(localStorage.getItem('japanese-stories:reviews') || '{}')"),
                None)
        br.goto_plain(f"{base}/index.html")
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)
        rep.add("index", "and-stays-closed-across-a-reload",
                br.eval(f"{c}.classList.contains('open')") is False, None)
        # Re-opening it by hand has to clear the flag, or the row can never be
        # auto-opened again for any later story-finished event.
        br.eval(f"{c}.querySelector('.disc').click()")
        br.goto_plain(f"{base}/index.html")
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)
        rep.add("index", "and-re-opening-by-hand-clears-the-flag",
                br.eval(f"{c}.classList.contains('open')"), None)
    finally:
        br.drop_init_script(ident)


def suite_review(br, rep, base):
    """Star ratings and notes on the contents page, and their own merge."""
    ident = br.init_script(sync_stub())
    try:
        br.emulate(*PHONE[1:])
        slug = "tokei-no-oto"
        br.goto_plain(f"{base}/blank.html")
        br.eval("localStorage.clear()")
        connect(br)
        br.goto_plain(f"{base}/index.html")
        br.eval("new Promise(r => setTimeout(r, 300))", await_promise=True)

        cell = f"document.querySelector('.cell[data-slug=\"{slug}\"]')"
        star = lambda n: f"{cell}.querySelector('[data-act=\"star\"][data-n=\"{n}\"]')"
        lit = f"{cell}.querySelectorAll('[data-act=\"star\"][aria-pressed=\"true\"]').length"
        revs = "JSON.parse(localStorage.getItem('japanese-stories:reviews'))"

        # ---- the merge rule, as a pure function -----------------------------
        M = "Sync.mergeReviews(%s, %s)"
        a, b = {slug: {"stars": 5, "note": "a", "at": 1000}}, {slug: {"stars": 2, "note": "b", "at": 2000}}
        got = br.eval(M % (json.dumps(a), json.dumps(b)))
        rep.add("review", "merge-takes-the-later-stamp", got[slug]["stars"] == 2, got)
        got = br.eval(M % (json.dumps(b), json.dumps(a)))
        rep.add("review", "merge-is-order-independent", got[slug]["stars"] == 2, got)
        # A rating and a position have nothing to say to each other, so the
        # `done` resolution must not leak into a map that has no `done`.
        rep.add("review", "merge-adds-no-done-field", "done" not in got[slug], got)
        got = br.eval(M % (json.dumps({slug: {"stars": 5, "at": 1}}), json.dumps({"v": 1})))
        rep.add("review", "merge-drops-a-non-record-key", "v" not in got, got)

        # ---- rating, by hand -------------------------------------------------
        br.eval(f"{star(4)}.click()")
        got = br.eval(revs)
        rep.add("review", "a-star-writes-a-rating-and-a-stamp",
                got[slug]["stars"] == 4 and got[slug].get("at", 0) > 0, got)
        rep.add("review", "and-lights-that-many-stars", br.eval(lit) == 4, br.eval(lit))

        # Nothing else can undo a mis-tap: the lit star is the only way back.
        br.eval(f"{star(4)}.click()")
        got = br.eval(revs)
        rep.add("review", "tapping-the-lit-star-clears-the-rating", got[slug]["stars"] == 0, got)
        rep.add("review", "and-unlights-the-row", br.eval(lit) == 0, br.eval(lit))
        br.eval(f"{star(3)}.click()")
        rep.add("review", "re-rating-after-a-clear-works", br.eval(lit) == 3, br.eval(revs))

        # ---- the rating reaches the gist ------------------------------------
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        remote = br.eval("window.GIST.revs") or {}
        rep.add("review", "a-rating-reaches-the-gist",
                (remote.get(slug) or {}).get("stars") == 3, remote)
        # Progress never moved here, so a no-op skip that only compared the
        # progress half would have thrown this PATCH away.
        rep.add("review", "and-does-so-with-the-position-unchanged",
                not (br.eval("window.GIST.doc") or {}).get(slug, {}).get("page"),
                br.eval("window.GIST.doc"))

        # ---- the note --------------------------------------------------------
        note = "Page 12 needed a re-read."
        ta = f"{cell}.querySelector('textarea.note')"
        br.eval(f"{cell}.querySelector('.notebtn').click()")
        rep.add("review", "the-note-button-reveals-the-box", br.eval(f"{ta}.hidden") is False, None)
        br.eval(f"{ta}.value = " + json.dumps(note))
        br.eval(f"{ta}.dispatchEvent(new Event('input', {{bubbles: true}}))")
        got = br.eval(revs)
        rep.add("review", "typing-writes-the-note-locally-at-once",
                got[slug]["note"] == note, got)
        rep.add("review", "and-does-not-disturb-the-rating", got[slug]["stars"] == 3, got)
        # Debounced, so the box is flushed by the blur rather than by waiting.
        # blur() alone does not deliver focusout to a window that does not have
        # focus, which is what headless is, so the event is dispatched too.
        br.eval(f"{ta}.blur(); {ta}.dispatchEvent(new FocusEvent('focusout', {{bubbles: true}}))")
        br.eval("new Promise(r => setTimeout(r, 400))", await_promise=True)
        remote = br.eval("window.GIST.revs") or {}
        rep.add("review", "and-the-note-reaches-the-gist",
                (remote.get(slug) or {}).get("note") == note, remote)
        rep.add("review", "a-written-note-is-marked-on-the-button",
                br.eval(f"{cell}.querySelector('.notebtn').classList.contains('has')"), None)

        # ---- the whole reason the two maps are separate ----------------------
        # A progress record is replaced whole by whichever side carries the
        # later `at`, and every page turn bumps it. On one record, this pull
        # would take the rating with it.
        ahead = int(time.time() * 1000) + 60000
        # Re-connecting rather than moving GIST.doc under a live ETag: the stub
        # answers 304 to a matching conditional request, so a remote changed in
        # place would never be fetched and the case would pass vacuously.
        connect(br, {slug: rec(9, ahead)})
        r = br.eval("Sync.pull()", await_promise=True)
        got = br.eval(revs)
        rep.add("review", "a-newer-remote-position-does-not-erase-a-rating",
                got[slug]["stars"] == 3 and got[slug]["note"] == note, got)
        rep.add("review", "and-the-position-is-still-adopted",
                r["map"][slug]["page"] == 9, r["map"][slug])

        # ---- a rating arriving from elsewhere paints -------------------------
        landed = {slug: {"stars": 5, "note": "from the laptop", "at": ahead}}
        gist(br, revs=landed, calls=[])
        br.reload_plain()
        br.eval("new Promise(r => setTimeout(r, 500))", await_promise=True)
        rep.add("review", "a-rating-made-elsewhere-paints-on-arrival",
                br.eval(lit) == 5, br.eval(revs))
        rep.add("review", "and-so-does-its-note",
                br.eval(f"{ta}.value") == "from the laptop", br.eval(f"{ta}.value"))

        # ---- export and import carry both halves -----------------------------
        br.eval("document.getElementById('exp').click()")
        dump = json.loads(br.eval("document.getElementById('box').value"))
        rep.add("review", "export-carries-progress-and-reviews",
                dump.get("reviews", {}).get(slug, {}).get("stars") == 5
                and slug in dump.get("progress", {}), list(dump.keys()))

        pasted = {"progress": {}, "reviews": {slug: {"stars": 1, "note": "pasted", "at": ahead + 1}}}
        br.eval("document.getElementById('box').hidden = false")
        br.eval("document.getElementById('box').value = " + json.dumps(json.dumps(pasted)))
        br.eval("document.getElementById('imp').click()")
        rep.add("review", "import-merges-reviews-too", br.eval(lit) == 1, br.eval(revs))

        # A bare progress map is what an export looked like before reviews
        # existed, and it must still import as progress rather than as nothing.
        br.eval("document.getElementById('box').hidden = false")
        br.eval("document.getElementById('box').value = "
                + json.dumps(json.dumps({slug: rec(20, ahead + 2)})))
        br.eval("document.getElementById('imp').click()")
        got = br.eval("JSON.parse(localStorage.getItem('japanese-stories:progress'))")
        rep.add("review", "a-pre-reviews-export-still-imports", got[slug]["page"] == 20, got)
        rep.add("review", "and-leaves-the-rating-alone",
                br.eval(revs)[slug]["stars"] == 1, br.eval(revs))

        # ---- 全消去 clears the opinion as well as the place -------------------
        # From a clean remote. Every stamp above is deliberately a minute in the
        # future so the "arrived from elsewhere" cases have something to win
        # with, and a tombstone written now cannot beat a clock that has not
        # happened yet — which is the merge rule working, not the wipe failing.
        connect(br)
        br.eval("document.getElementById('wipe').click()")
        br.eval("document.getElementById('wipe').click()")
        got = br.eval(revs)
        rep.add("review", "a-wipe-tombstones-the-rating",
                got[slug]["stars"] == 0 and got[slug]["note"] == "" and got[slug]["at"] > 0, got)
        rep.add("review", "and-the-row-repaints-unrated", br.eval(lit) == 0, None)

        # ---- 消去 on one row is about the place, not the verdict --------------
        br.eval(f"{star(4)}.click()")
        br.eval("document.getElementById('edit').click()")
        br.eval(f"{cell}.querySelector('[data-act=\"clear\"]').click()")
        rep.add("review", "clearing-one-story-leaves-its-rating-standing",
                br.eval(lit) == 4 and br.eval(revs)[slug]["stars"] == 4, br.eval(revs))

        # ---- a note typed while a push is open is not rolled back -------------
        # push() reads the store after its GET rather than before it. Reading
        # first and merging against that snapshot writes the pre-keystroke copy
        # back over the box, one keystroke at a time, and PATCHes the loss.
        connect(br, None, {"shuden": {"stars": 5, "at": ahead + 20}})
        gist(br, delay=1200)
        br.eval(f"{cell}.querySelector('.notebtn').click()") if br.eval(f"{ta}.hidden") else None
        br.eval(f"{ta}.focus()")
        br.eval(f"{ta}.value = 'first'")
        br.eval(f"{ta}.dispatchEvent(new Event('input', {{bubbles: true}}))")
        br.eval("window.__p = Sync.push()")
        br.eval(f"{ta}.value = 'first and second'")
        br.eval(f"{ta}.dispatchEvent(new Event('input', {{bubbles: true}}))")
        br.eval("window.__p", await_promise=True)
        rep.add("review", "a-keystroke-during-an-open-push-is-not-rolled-back",
                br.eval(revs)[slug]["note"] == "first and second", br.eval(revs)[slug])
        gist(br, delay=0)

        # ---- a note arriving while the box sits empty and focused --------------
        # The box is skipped by the repaint while it holds focus, so without a
        # repaint on the way out the next keystroke would send the empty box —
        # and the merged note with it — straight back to the gist.
        br.eval(f"{ta}.focus()")
        br.eval(f"{ta}.value = ''")
        connect(br, None, {slug: {"stars": 4, "note": "typed on the laptop", "at": ahead + 30}})
        br.eval("Sync.pull()", await_promise=True)
        rep.add("review", "a-focused-box-is-left-alone-while-it-is-focused",
                br.eval(f"{ta}.value") == "", br.eval(f"{ta}.value"))
        br.eval(f"{ta}.blur(); {ta}.dispatchEvent(new FocusEvent('focusout', {{bubbles: true}}))")
        rep.add("review", "the-box-really-did-give-up-focus",
                br.eval(f"document.activeElement !== {ta}"), None)
        rep.add("review", "and-the-blur-brings-the-merged-note-in",
                br.eval(f"{ta}.value") == "typed on the laptop", br.eval(f"{ta}.value"))

        # ---- a repaint must not take a half-typed sentence away ---------------
        br.eval(f"{ta}.focus()")
        br.eval(f"{ta}.value = 'half a sen'")
        connect(br, None, {slug: {"stars": 2, "note": "overwritten", "at": ahead + 40}})
        r = br.eval("Sync.pull()", await_promise=True)
        rep.add("review", "the-pull-under-test-really-did-deliver-a-note",
                (r["reviews"].get(slug) or {}).get("note") == "overwritten", r["reviews"])
        br.eval("new Promise(r => setTimeout(r, 200))", await_promise=True)
        rep.add("review", "a-focused-note-is-not-stomped-by-a-pull",
                br.eval(f"{ta}.value") == "half a sen", br.eval(f"{ta}.value"))
    finally:
        br.drop_init_script(ident)


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
    """Put the reader in a fully known state, not a partly inherited one.

    Every field is written, not just the three a cell is named after. Prefs
    persist across navigations on one origin, so writing only writingMode,
    fontSize and linebreaks let suite_persistence's dark theme, left binding and
    armed ふりがな leak into every later suite — including all 288 matrix cells,
    where a forced left binding meant the 縦書き turn direction, half the matrix,
    was never exercised at all. The cell label has to name the whole state it ran
    under.
    """
    patch = {"writingMode": wm, "fontSize": fs,
             "linebreaks": {"vertical": bool(lb), "horizontal": bool(lb)},
             "binding": "auto", "theme": "system", "furigana": False,
             "pitch": True, "ink": False}
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
    # These are MEASURED, not designed: a text edit that changes how a page fills
    # moves them, and the only honest response is to re-measure. 猫を探す探偵 was
    # 32 until the quote-turn merge (4654b56) put four split turns back onto one
    # line each; the sentence blocks that went with them were enough for one
    # authored page to stop needing a second screen.
    #
    # Re-measured 2026-09-19 after the eight-story revision. Five moved: 終電
    # 28->27, 猫を探す探偵 31->30, 城の鐘 41->42, 煙突の煙 27->28, and
    # 行かなかった人の地図 55->49, which is the big one — it lost four authored
    # pages (48->44) and two more screens' worth of over-explanation on top.
    # 迷子の手紙, 時計の音 and 廊下の鏡 re-measured to their recorded values
    # unchanged, which is the evidence that the measurement itself is stable.
    #
    # 縁台の将棋 (23) and 三番の乾燥機 (37) recorded 2026-09-19, both first
    # measurements. 縁台の将棋 shipped in 1dbc8b7 without a row, so the
    # corpus-coverage assertion below was already failing before 三番の乾燥機
    # was written; the two were recorded together off one harness run.
    # 三番の乾燥機 is 34 authored pages against 37 text screens, so three pages
    # take two screens each at 28px — tight=0 and worst-overflow=0px, meaning
    # nothing overflows, they simply fill.
    expect = {"shuden": 27, "neko-o-sagasu-tantei": 30, "maigo-no-tegami": 18,
              "tokei-no-oto": 25, "shiro-no-kane": 42, "entotsu-no-kemuri": 28,
              "ikanakatta-hito-no-chizu": 49, "rouka-no-kagami": 25,
              "endai-no-shougi": 23, "sanban-no-kansouki": 37,
              "juugonichi-no-shichifuda": 30}
    br.emulate(*PHONE[1:])
    table = {}
    print("\n===== screen counts @ 28px 縦書き 改行-off, 390x844 (device emulation) =====")
    for slug in SLUGS:
        br.goto(f"{base}/{slug}.html")
        br.eval(LIB)
        apply_prefs(br, "vertical", False, 28)
        r = walk(br, 28)
        table[slug] = r
        want = expect.get(slug)
        print(f"  {slug:22} pages={r['pages']:3}  screens={r['screens']:3} "
              f"(text {r['text']}, あとがき {r['after']})  tight={r['tight']} "
              f"worst-overflow={r['worst']}px  "
              f"expected={want if want is not None else 'NOT RECORDED'}")
        rep.add("never-scroll", f"{slug}/no-raw-overflow", not r["fails"], r["fails"][:6])
        # The settled table counts TEXT screens: the あとがき is appended to the
        # last authored page and is not one of the story's screens.
        #
        # want is .get, not [slug]: a story added to corpus.json before anyone
        # measured it must FAIL here, naming the number to record. Indexing
        # would raise instead, aborting the run and reporting nothing at all
        # about the other six — which is how this went unnoticed.
        rep.add("split", f"{slug}/screens-match-plan", want is not None and r["text"] == want,
                {"text": r["text"], "want": want, "total": r["screens"]})
        bad = br.eval("H.atoms()")
        rep.add("split", f"{slug}/authored-page-is-an-atom", not bad, bad[:6])
    # The gap that let a story go unmeasured is now two gaps narrower: SLUGS
    # follows the corpus, and this says so out loud if the table falls behind it.
    missing = [x for x in SLUGS if x not in expect]
    rep.add("split", "the-table-covers-the-whole-corpus", not missing, missing)
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


def _tok(kana, pos="動詞", atype=None, contype=None, modtype=None, lemma=None, ctype=None):
    return {"kana": kana, "pos": pos, "atype": atype, "contype": contype,
            "modtype": modtype, "lemma": lemma, "ctype": ctype}


def suite_pitch_rules(rep):
    """The accent rules, exercised directly. No fugashi, no browser, no corpus.

    Every case here is a rule from tables 9-12 of the UniDic manual, chosen so
    that it fails if the rule's two branches are swapped: a rule is only ever
    wrong in one column, and a case that uses the other column passes either way.
    """
    import pitch

    cases = [
        # F1 — keep the host accent, whichever column it is in
        ("F1/keeps-an-accented-host", [_tok("タベ", atype=2), _tok("テ", contype="動詞%F1")], 2),
        ("F1/keeps-a-heiban-host", [_tok("カッ", atype=0), _tok("テ", contype="動詞%F1")], 0),
        # F2 — N1+M for a 平板 host, the host's own accent otherwise
        ("F2/heiban-host-takes-the-offset",
         [_tok("ガクセイ", "名詞", 0), _tok("デス", "助動詞", contype="名詞%F2@1")], 5),
        ("F2/accented-host-keeps-its-own",
         [_tok("ホン", "名詞", 1), _tok("デス", "助動詞", contype="名詞%F2@1")], 1),
        # F3 — the mirror of F2, and the reason both are tested in both columns
        ("F3/heiban-host-stays-flat",
         [_tok("イカ", atype=0), _tok("ナイ", "助動詞", contype="動詞%F3@0")], 0),
        ("F3/accented-host-takes-the-offset",
         [_tok("タベ", atype=2), _tok("ナイ", "助動詞", contype="動詞%F3@0")], 2),
        # F4 — N1+M regardless, which is why ます accents ま either way
        ("F4/heiban-host", [_tok("イキ", atype=0), _tok("マス", "助動詞", contype="動詞%F4@1")], 3),
        ("F4/accented-host", [_tok("タベ", atype=2), _tok("マス", "助動詞", contype="動詞%F4@1")], 3),
        ("F5/always-flat", [_tok("タベ", atype=2), _tok("ダケ", "助詞", contype="動詞%F5")], 0),
        # Both offsets land inside the 4-mora phrase on purpose: an accent past
        # the end is refused by the invariant, which would mask the branch.
        ("F6/heiban-host-takes-M", [_tok("ヨミ", atype=0), _tok("タリ", "助詞", contype="動詞%F6@2,1")], 4),
        ("F6/accented-host-takes-L", [_tok("ヨミ", atype=1), _tok("タリ", "助詞", contype="動詞%F6@2,1")], 3),
        # C — 表10, where the rear element's own accent can matter
        ("C1/adds-the-rear-accent",
         [_tok("テ", "名詞", 0), _tok("ツヅキ", "名詞", 2, contype="C1")], 3),
        ("C2/accents-the-first-rear-mora",
         [_tok("セイ", "名詞", 0), _tok("カツ", "名詞", 0, contype="C2")], 3),
        ("C3/accents-the-last-front-mora",
         [_tok("トウ", "名詞", 0), _tok("ワン", "名詞", 0, contype="C3")], 2),
        ("C4/flattens", [_tok("ナカ", "名詞", 1), _tok("シマ", "名詞", 2, contype="C4")], 0),
        ("C5/keeps-the-front-accent",
         [_tok("トノ", "名詞", 1), _tok("ドノ", "接尾辞", 0, contype="C5")], 1),
        # M — 表9, a conjugated form shifting its own base accent
        ("M1/always-counts-back-from-the-end", [_tok("タベヨウ", atype=2, modtype="M1@1")], 3),
        ("M2/heiban-base-counts-back", [_tok("タベロ", atype=0, modtype="M2@1")], 2),
        ("M2/accented-base-is-left-alone", [_tok("タベロ", atype=2, modtype="M2@1")], 2),
        ("M4/atamadaka-base-is-left-alone", [_tok("タベ", atype=1, modtype="M4@1")], 1),
        ("M4/deeper-base-shifts-back", [_tok("タベサセ", atype=3, modtype="M4@1")], 2),
    ]
    for name, toks, want in cases:
        got, _ = pitch.phrase_accent(toks)
        rep.add("pitch-rules", name, got == want, {"want": want, "got": got})

    # 表11, reachable only through a 接頭辞 head — the one case where the FRONT
    # element owns the rule. Unreachable and untested until the review found it.
    prefix = [
        ("P1/flat-rear-goes-flat",
         [_tok("ゴ", "接頭辞", 0, contype="P1"), _tok("ハン", "名詞", 0)], 0),
        ("P1/accented-rear-is-offset",
         [_tok("ゴ", "接頭辞", 0, contype="P1"), _tok("シュジン", "名詞", 2)], 3),
        ("P2/flat-rear-accents-the-first-rear-mora",
         [_tok("ソウ", "接頭辞", 0, contype="P2"), _tok("カイ", "名詞", 0)], 3),
        ("P13/keeps-the-prefix-accent",
         [_tok("ゲン", "接頭辞", 1, contype="P13"), _tok("ジュウショ", "名詞", 1)], 1),
    ]
    for name, toks, want in prefix:
        got, _ = pitch.phrase_accent(toks)
        rep.add("pitch-rules", name, got == want, {"want": want, "got": got})
    rep.add("pitch-rules", "接頭辞-head-without-a-P-rule-declines",
            pitch.phrase_accent(
                [_tok("ゴ", "接頭辞", 0, contype="C3"), _tok("ハン", "名詞", 0)])[0] is None, {})

    # 表9 on an auxiliary, which was read and discarded before the review.
    volitional = [_tok("アゲ", atype=0),
                  _tok("マショウ", "助動詞", contype="動詞%F4@1", modtype="M1@1")]
    got, _ = pitch.phrase_accent(volitional)
    rep.add("pitch-rules", "表9-on-an-auxiliary-moves-the-combined-accent", got == 4,
            {"want": 4, "got": got, "note": "F4@1 alone would give 3"})

    # The host class follows the chain: たい inflects as an i-adjective, so the
    # た after it wants the 形容詞 branch and not the phrase head's 動詞 one.
    adj = [_tok("タベ", atype=2),
           _tok("タカッ", "助動詞", 0, contype="動詞%F2@1", ctype="助動詞-タイ"),
           _tok("タ", "助動詞", contype="動詞%F2@1,形容詞%F4@-2", lemma="た")]
    got, _ = pitch.phrase_accent(adj)
    rep.add("pitch-rules", "an-adjectival-auxiliary-reclasses-the-host", got == 3,
            {"got": got, "note": "形容詞%F4@-2 over 5 morae; the 動詞 branch would keep 2"})

    # The one place this repo overrides UniDic's own data. F2@1 and F1 agree on an
    # accented host, so only the 平板 case can catch a regression here.
    fix = [_tok("イッ", atype=0), _tok("タ", "助動詞", contype="動詞%F2@1", lemma="た")]
    got, _ = pitch.phrase_accent(fix)
    rep.add("pitch-rules", "た-correction/heiban-verb-stays-flat", got == 0,
            {"got": got, "note": "F2@1 unpatched would give 3"})
    keep = [_tok("タベ", atype=2), _tok("タ", "助動詞", contype="動詞%F2@1", lemma="た")]
    got, _ = pitch.phrase_accent(keep)
    rep.add("pitch-rules", "た-correction/accented-verb-unaffected", got == 2, {"got": got})

    # Refusing to answer is the whole safety mechanism, so it is asserted rather
    # than assumed: an unknown rule and an impossible result both come back None,
    # and the reader falls back to the 辞書形 on either.
    unknown = [_tok("タベ", atype=2), _tok("ホゲ", "助詞", contype="動詞%F9@1")]
    rep.add("pitch-rules", "unknown-rule-declines",
            pitch.phrase_accent(unknown)[0] is None, {})
    rep.add("pitch-rules", "no-accent-on-the-host-declines",
            pitch.phrase_accent([_tok("タベ", atype=None)])[0] is None, {})
    overrun = [_tok("ア", "名詞", 0), _tok("イ", "助詞", contype="名詞%F2@9")]
    rep.add("pitch-rules", "unpronounceable-result-declines",
            pitch.phrase_accent(overrun)[0] is None, {})


# CIEDE2000, so that "these two colours are too close" is a number rather than an
# opinion. Small enough to inline; the alternative is a dependency for one check.
def _lab(hex6):
    r, g, b = [int(hex6[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = f(r), f(g), f(b)
    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    k = lambda t: t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29
    fx, fy, fz = k(X / 0.95047), k(Y), k(Z / 1.08883)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _de2000(p, q):
    L1, a1, b1 = p
    L2, a2, b2 = q
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7))) if Cb else 0
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1 = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0
    h2 = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dh = 0
    elif h2 - h1 > 180:
        dh = h2 - h1 - 360
    elif h2 - h1 < -180:
        dh = h2 - h1 + 360
    else:
        dh = h2 - h1
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dh) / 2)
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1 + h2
    elif abs(h1 - h2) <= 180:
        hbp = (h1 + h2) / 2
    elif h1 + h2 < 360:
        hbp = (h1 + h2 + 360) / 2
    else:
        hbp = (h1 + h2 - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    Rc = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7)) if Cbp else 0
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * (30 * math.exp(-(((hbp - 275) / 25) ** 2))))) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


# Below this two colours on the same glyph stop being reliably separable at the
# size a 傍点 is drawn. 19.4 is what the shipped palette achieves, and the pair
# that sets it is 平板 against 起伏 — both Migaku's, and so not ours to move.
MIN_ON_GLYPH_DE = 18.0


def suite_defaults(rep):
    """The shipped defaults, read out of reader.js.

    高低 defaults on and 墨 defaults off, which is a product decision rather than
    an implementation detail — a reader who never opens 設定 gets the accent
    colours and the marks. Asserted here because nothing else would notice it
    changing.
    """
    js = (REPO / "scripts" / "reader.js").read_text(encoding="utf-8")
    block = re.search(r"const defaults = \(\) => \(\{(.*?)\}\)", js, re.S)
    if not block:
        block = re.search(r"defaults\s*=\s*\(\)\s*=>\s*\(\{(.*?)\}\)", js, re.S)
    body = block.group(1) if block else js
    for field, want in (("pitch", "true"), ("ink", "false")):
        m = re.search(rf"\b{field}:\s*(true|false)", body)
        rep.add("defaults", f"{field}-defaults-{want}", bool(m) and m.group(1) == want,
                {"found": m.group(1) if m else None, "want": want})


def suite_palette(rep):
    """The marker hues and the pitch hues are one palette, and it has to stay legible.

    They are separate concerns everywhere except on a word, where 苦手's sesame is
    drawn beside the character its pitch hue has just coloured. That is the only
    place they compete, and it is invisible in review: 起伏 appears only on a 辞書形
    fallback, so the closest pair in the whole system is also the one least likely
    to turn up on any page someone happens to look at.

    Read out of reader.css rather than restated here — a copy would go stale
    against the file it is meant to be protecting.
    """
    css = (REPO / "scripts" / "reader.css").read_text(encoding="utf-8")
    names = ["--pitch-heiban", "--pitch-atamadaka", "--pitch-nakadaka",
             "--pitch-odaka", "--pitch-kifuku", "--weak", "--new", "--ink"]
    # Declarations appear light-first, then twice for dark (media query and
    # data-theme), and the two dark copies must agree — which is itself worth
    # asserting, since they are maintained by hand.
    found = {n: re.findall(rf"{n}:\s*(#[0-9a-fA-F]{{6}})\s*;", css) for n in names}
    missing = [n for n, v in found.items() if len(v) < 2]
    rep.add("palette", "every-colour-is-declared-light-and-dark", not missing,
            {"missing": missing, "counts": {n: len(v) for n, v in found.items()}})
    if missing:
        return
    disagree = [n for n, v in found.items() if len(v) > 2 and len(set(v[1:])) != 1]
    rep.add("palette", "the-two-dark-declarations-agree", not disagree,
            {"disagree": {n: found[n] for n in disagree}})

    for theme, pick in (("light", lambda v: v[0]), ("dark", lambda v: v[-1])):
        pal = {n.replace("--pitch-", "").replace("--", ""): pick(v) for n, v in found.items()}
        labs = {k: _lab(v) for k, v in pal.items()}
        keys = sorted(pal)
        pairs = sorted(
            (_de2000(labs[a], labs[b]), a, b)
            for i, a in enumerate(keys) for b in keys[i + 1:]
        )
        worst, x, y = pairs[0]
        rep.add("palette", f"{theme}/no-two-on-glyph-colours-collide", worst >= MIN_ON_GLYPH_DE,
                {"worst": round(worst, 1), "pair": f"{x} vs {y}", "floor": MIN_ON_GLYPH_DE,
                 "next": [f"{a}/{b} {d:.1f}" for d, a, b in pairs[1:3]]})
        # The one that actually bit: 苦手's sesame sits on a 起伏 word whenever a
        # leech verb falls back to its dictionary form.
        d = _de2000(labs["weak"], labs["kifuku"])
        rep.add("palette", f"{theme}/苦手-sesame-reads-on-a-起伏-word", d >= MIN_ON_GLYPH_DE,
                {"de": round(d, 1), "weak": pal["weak"], "kifuku": pal["kifuku"]})


def suite_pitch_table(rep):
    """The shipped table and the built data, against the gold set.

    suite_pitch_rules can pass with a table nobody rebuilt. This is the half that
    notices, and it needs neither fugashi nor a browser to do it.
    """
    import pitch

    table = pitch.load()
    by_surface = {}
    for k, v in table.items():
        by_surface.setdefault(k.split("\t")[0], []).append(v)

    checked = 0
    for word, want in sorted(pitch.GOLD.items()):
        for entry in by_surface.get(word, []):
            if "a" not in entry:
                continue
            checked += 1
            rep.add("pitch-table", f"gold/{word}", entry["a"] == want,
                    {"want": want, "got": entry["a"], "kana": entry.get("k")})
    rep.add("pitch-table", "gold-overlaps-the-corpus", checked >= 8, {"checked": checked})

    # A surface is not a word. 空 is ソラ and から, 他 is ホカ and タ — keyed on the
    # surface alone the last one written wins and build.py then hands it to every
    # occurrence, which is the very agreement analyse()'s reading guard checked.
    rep.add("pitch-table", "the-key-carries-the-reading", all("\t" in k for k in table),
            {"sample": sorted(table)[:2]})

    # The 辞書形 may only ever name the whole printed word. Asserted as the named
    # regressions rather than structurally, because a dictionary form legitimately
    # differs from its inflected surface — 作られて really does reduce to 作る — so
    # there is no shape that separates 食べた → 食べる from 一本 → 一. These are the
    # surfaces that shipped a fragment before the review found them.
    FRAGMENTS = ["一本", "九時", "四日", "二日目", "十分", "三本",
                 "口にした", "匂いがして", "年を取った", "会社を辞めた"]
    named = []
    for surface in FRAGMENTS:
        for e in by_surface.get(surface, []):
            if "lemma" in e:
                named.append(f"{surface} -> {e['lemma']}")
    rep.add("pitch-table", "no-辞書形-names-a-word-the-page-does-not-print",
            not named, {"bad": named})

    # Zero-width characters are not morae. 時には ships as とき\u200bには.
    ZW = "\u200b\u200c\u200d\u2060\ufeff"
    bad_zw = [k for k, e in table.items() if any(c in (e.get("k") or "") for c in ZW)]
    rep.add("pitch-table", "no-reading-carries-a-zero-width-char", not bad_zw,
            {"readings_with_zw": bad_zw[:3]})

    # Every entry has to be drawable: an accent past the end of the word puts the
    # downstep off the diagram, and the reader has no way to notice.
    bad = [w for w, e in table.items()
           if "a" in e and not (0 <= e["a"] <= len(pitch.morae(e.get("k") or "")))]
    rep.add("pitch-table", "every-accent-lands-inside-its-word", not bad, {"bad": bad[:5]})

    total = marked = surface = 0
    mismatched = []
    for path in sorted((REPO / "docs" / "data").glob("*.js")):
        blob = json.loads(re.search(r"=\s*(\{.*\})\s*;?\s*$", path.read_text(encoding="utf-8"), re.S).group(1))
        entries = blob.get("pitch") or []
        rep.add("pitch-table", f"{path.stem}/ships-a-table", bool(entries), {"entries": len(entries)})
        # An index the table cannot answer renders nothing and says nothing.
        stray = []

        def walk(node):
            nonlocal total, marked, surface
            if isinstance(node, dict):
                if node.get("r"):
                    total += 1
                    if "p" in node:
                        marked += 1
                        if not (0 <= node["p"] < len(entries)):
                            stray.append(node.get("t"))
                        elif "a" in entries[node["p"]]:
                            surface += 1
                            # The keying bug's actual symptom: a token wearing
                            # another reading's accent. 空/から wore ソラ's.
                            want = table.get(pitch.key(node["t"], node.get("k") or ""))
                            if want and want.get("k") and want["k"] != pitch.katakana(node.get("k") or ""):
                                mismatched.append(f"{node['t']} {node.get('k')} got {want['k']}")
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(blob)
        rep.add("pitch-table", f"{path.stem}/no-index-points-past-the-table",
                not stray, {"stray": stray[:5]})

    # The built data has to agree with the table it was built from.
    #
    # Everything above this reads the payload and reports what it finds, so a
    # build that never reran measures its own stale output and passes. That is
    # not hypothetical: pitch-table.json was missing from rebuild.py's DATA_DEPS
    # until da2d159, which made the last step of the documented rebuild ->
    # pitch.py --build -> rebuild sequence a silent no-op. On 廊下の鏡 it cost 157
    # of 463 marked words their accent, and nothing said so.
    #
    # This is the assertion that would have caught it directly, and it is the
    # only one here that compares the payload against something outside itself.
    stale, wrong = [], []
    for path in sorted((REPO / "docs" / "data").glob("*.js")):
        blob = json.loads(re.search(r"=\s*(\{.*\})\s*;?\s*$", path.read_text(encoding="utf-8"), re.S).group(1))
        entries = blob.get("pitch") or []

        def check(node):
            if isinstance(node, dict):
                if node.get("r"):
                    want = pitch.shipped(table.get(pitch.key(node["t"], node.get("k") or "")))
                    got = entries[node["p"]] if "p" in node and node["p"] < len(entries) else None
                    if want and got is None:
                        stale.append(f"{path.stem}: {node['t']}")
                    elif want and got != want:
                        wrong.append(f"{path.stem}: {node['t']} has {got}, table says {want}")
                for v in node.values():
                    check(v)
            elif isinstance(node, list):
                for v in node:
                    check(v)

        check(blob)
    rep.add("pitch-table", "every-word-the-table-can-answer-carries-its-guide",
            not stale, {"count": len(stale), "sample": stale[:6],
                        "hint": "docs/ is older than pitch-table.json; rebuild"})
    rep.add("pitch-table", "and-the-guide-it-carries-is-the-current-one",
            not wrong, {"count": len(wrong), "sample": wrong[:4]})

    # Coverage is a fact about the corpus, not a rule, so it is pinned loosely —
    # low enough not to fail on a new story, high enough to catch a table that
    # silently stopped being rebuilt. It fell from 99.4% when the reading guard
    # started applying to the whole entry rather than only to the surface accent:
    # what it gave up was 116 surfaces where UniDic and Ichiran disagree about the
    # reading, or where Ichiran grouped several words into one token, and those
    # were previously answered with a 辞書形 naming a fragment.
    rep.add("pitch-table", "most-marked-tokens-carry-a-guide",
            total and marked / total > 0.85, {"marked": marked, "total": total})
    # This is what the drop bought, and it is the number worth watching.
    rep.add("pitch-table", "nearly-every-guide-is-the-printed-surface",
            marked and surface / marked > 0.95, {"surface": surface, "marked": marked})
    rep.add("pitch-table", "no-token-gets-another-reading's-accent",
            not mismatched, {"bad": mismatched[:6]})


def suite_pitch_reader(br, rep, base):
    """The guide as rendered. Python proves the numbers; this proves they land."""
    br.emulate(*PHONE[1:])
    br.goto(f"{base}/shiro-no-kane.html")
    br.eval(LIB)
    apply_prefs(br, "vertical", False, 28)
    for row in br.eval("H.pitch()", await_promise=True):
        suite, _, name = row["name"].partition("/")
        rep.add("pitch", name, row["ok"], row["detail"])
    # A fresh load, because H.pitch() leaves a word lit and prefs moved around.
    br.goto(f"{base}/shiro-no-kane.html")
    br.eval(LIB)
    apply_prefs(br, "vertical", False, 28)
    for row in br.eval("H.highlight()", await_promise=True):
        suite, _, name = row["name"].partition("/")
        rep.add("highlight", name, row["ok"], row["detail"])


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


def annotated_stories():
    """Slugs whose translations carry ｜漢字《かな》, read from the sources.

    Not a hand list. It was one, naming 行かなかった人の地図 as "the one story
    whose translations annotate the names they use" — true when it was written
    and false one commit later, once the name conversion put annotations into
    迷子の手紙 and 猫を探す探偵. A leak scan that walks the story it was told
    about rather than the stories that exist is the shape of gap this whole
    branch is closing.
    """
    out = []
    for s in stats.CORPUS["stories"]:
        src = stats.STORIES / f"{s['slug']}.txt"
        lines = src.read_text(encoding="utf-8").splitlines()
        if any(l.startswith(">") and "｜" in l for l in lines):
            out.append(s["slug"])
    return out


def suite_en_ruby(br, rep, base):
    """Every story whose translations annotate the names they use.

    The ｜漢字《かな》 English lines are the whole reason the panel renders HTML
    rather than setting textContent, so this runs where the fixtures are rather
    than folding into suite_behaviour, which reads 時計の音 and has none.

    It runs once per story because the shapes differ: 行かなかった人の地図 has a
    name opening a sentence, 迷子の手紙 has one mid-clause and a possessive
    ｜松田《まつだ》's, and an escaper that mishandled either would ship raw
    markup with a single-story scan entirely green.
    """
    for slug in annotated_stories():
        br.emulate(*PHONE[1:])
        br.goto(f"{base}/{slug}.html")
        br.eval(LIB)
        apply_prefs(br, "vertical", False, 28)
        for row in br.eval("H.enRuby()", await_promise=True):
            rep.add("en-ruby", f"{slug}/{row['name'].split('/', 1)[1]}",
                    row["ok"], row["detail"])


def suite_title_kana(br, rep, base):
    """The title flips to its authored reading on tap, and back.

    Runs over every story in the corpus rather than one, because the reading is
    looked up by title against stories-index.md and a lookup that misses fails
    silently — the title simply stays put, which is what it did before this
    existed. One story passing says nothing about the other seven.
    """
    for slug in [s["slug"] for s in stats.CORPUS["stories"]]:
        br.emulate(*PHONE[1:])
        br.goto(f"{base}/{slug}.html")
        br.eval(LIB)
        surface = br.eval("DATA.title")
        kana = br.eval("DATA.titleKana")
        rep.add("title-kana", f"{slug}/carries-a-reading", bool(kana), kana)
        rep.add("title-kana", f"{slug}/starts-on-the-surface",
                br.eval("document.getElementById('title').textContent") == surface,
                br.eval("document.getElementById('title').textContent"))
        rep.add("title-kana", f"{slug}/is-marked-tappable",
                br.eval("document.getElementById('title').classList.contains('has-kana')"), None)
        br.eval("document.getElementById('title').click()")
        rep.add("title-kana", f"{slug}/tapping-shows-the-reading",
                br.eval("document.getElementById('title').textContent") == kana,
                br.eval("document.getElementById('title').textContent"))
        # Back, not stuck: the reading is the detour and the title is the place
        # the header returns to.
        br.eval("document.getElementById('title').click()")
        rep.add("title-kana", f"{slug}/and-tapping-again-restores-it",
                br.eval("document.getElementById('title').textContent") == surface,
                br.eval("document.getElementById('title').textContent"))
        # No markup may reach the heading. It is the one string in the reader set
        # by textContent on both sides of the flip, so a reading that arrived as
        # ruby would show its tags rather than render them.
        rep.add("title-kana", f"{slug}/neither-side-carries-markup",
                "<" not in surface and "<" not in kana and "｜" not in kana, {"t": surface, "k": kana})


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
            "theme": "dark", "furigana": True,
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
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    # directory=, not os.chdir: the handler is the only thing that needs to be
    # rooted at the fixtures, and a chdir moves the whole interpreter — build.py
    # and stats.py are imported here and resolve paths of their own.
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(
        ("127.0.0.1", PORT), functools.partial(Quiet, directory=str(HERE)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    args = set(sys.argv[1:])
    check_contracts()
    rep = Report()
    print("===== no-summary =====")
    check_no_summary(rep)
    # Both run before Chrome starts: neither needs a browser, and a bad rule or a
    # stale table should fail in a second rather than after the fixture build.
    print("\n===== pitch rules =====")
    suite_pitch_rules(rep)
    print("\n===== pitch table =====")
    suite_pitch_table(rep)
    print("\n===== palette =====")
    suite_palette(rep)
    print("\n===== defaults =====")
    suite_defaults(rep)
    for slug in SLUGS:
        build_fixture(slug)
    build_fixture("shuden", inject=True)
    # The contents page as shipped, so suite_manage tests the real markup rather
    # than a copy of it. Its <script src="sync.js"> 404s in the fixture tree on
    # purpose — the init script has already defined window.Sync, and letting the
    # tag resolve would leave two instances of the module racing one store.
    shutil.copy(REPO / "docs" / "index.html", HERE / "index.html")
    # Somewhere on the origin with no Progress module. Reloading a reader fires
    # pagehide, which flushes the outgoing page's position back into the store —
    # so localStorage.clear() followed by a reload does not clear anything. This
    # is where a test stands to wipe the store between cases.
    (HERE / "blank.html").write_text(
        "<!doctype html><meta charset=utf-8><title>blank</title>\n", encoding="utf-8")

    srv = serve()
    br = None
    base = f"http://127.0.0.1:{PORT}"
    try:
        br = Chrome()
        table = suite_table(br, rep, base)
        if "--table" not in args:
            print("\n===== behaviour =====")
            suite_behaviour(br, rep, base)
            print("\n===== pitch in the reader =====")
            suite_pitch_reader(br, rep, base)
            print("\n===== 傍点 vs ruby =====")
            suite_marks(br, rep, base)
            print("\n===== ふりがな in a translation =====")
            suite_en_ruby(br, rep, base)
            print("\n===== 題名の読み =====")
            suite_title_kana(br, rep, base)
            print("\n===== persistence =====")
            suite_persistence(br, rep, base)
            print("\n===== degradation =====")
            suite_degradation(br, rep, base)
            print("\n===== sync =====")
            suite_sync(br, rep, base)
            print("\n===== index =====")
            suite_index(br, rep, base)
            print("\n===== manage =====")
            suite_manage(br, rep, base)
            print("\n===== review =====")
            suite_review(br, rep, base)
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
        # Chrome.close() already cleans its own profile; the fixtures are the
        # other ~1.7MB this run leaves behind, once per --table/--matrix
        # invocation during a tuning session.
        shutil.rmtree(HERE, ignore_errors=True)
    return 1 if rep.summary() else 0


if __name__ == "__main__":
    sys.exit(main())
