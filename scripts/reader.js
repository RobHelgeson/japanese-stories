      const DATA = "__STORY_DATA__";
      const $ = (id) => document.getElementById(id);

      // ------------------------------------------------------------ storage --
      // Both keys live in the device's localStorage, so neither can be reached
      // from file:// — a mailed copy and the --split harness both run there, and
      // Safari throws on the accessor itself rather than on the call. Nothing
      // below dereferences localStorage outside a try, and once it has thrown
      // the reader carries on with the session's values held in memory.
      const Store = (() => {
        const PREFIX = "japanese-stories:";
        // ?nostore makes the degradation check reproducible on any browser and
        // any origin, rather than depending on file:// throwing on the one being
        // tested. Nobody types it by accident.
        let dead = location.search.indexOf("nostore") >= 0;
        const flushes = [];

        const plain = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

        const readJSON = (key) => {
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

        const writeJSON = (key, value) => {
          if (dead) return false;
          try {
            localStorage.setItem(PREFIX + key, JSON.stringify(value));
            return true;
          } catch (e) {
            // Safari in private browsing reads normally and throws on the first
            // write, so this is the only place the flag can be raised.
            dead = true;
            return false;
          }
        };

        // A write deferred past the turn that caused it. Progress is written on
        // every page turn and localStorage is synchronous; writing inside the
        // snap animation is a dropped frame on the one interaction that has to
        // feel smooth.
        const defer = (fn, ms) => {
          let timer = 0;
          const run = () => {
            if (!timer) return;
            clearTimeout(timer);
            timer = 0;
            fn();
          };
          flushes.push(run);
          return () => {
            if (timer) clearTimeout(timer);
            timer = setTimeout(run, ms);
          };
        };

        const flush = () => {
          for (const run of flushes) run();
        };
        // pagehide and visibilitychange rather than unload: iOS Safari fires
        // neither unload nor beforeunload when the app is swiped away or the
        // page enters the back/forward cache.
        addEventListener("pagehide", flush);
        addEventListener("visibilitychange", () => {
          if (document.visibilityState === "hidden") flush();
        });

        // Fires only in the other tabs, never in the one that wrote. A null key
        // is localStorage.clear(), which counts as a change to everything.
        const listen = (key, fn) => {
          addEventListener("storage", (e) => {
            if (e.key === null || e.key === PREFIX + key) fn();
          });
        };

        return {
          plain,
          readJSON,
          writeJSON,
          defer,
          flush,
          listen,
          ok: () => !dead,
          disable: () => {
            dead = true;
          },
        };
      })();

      // -------------------------------------------------------------- prefs --
      const Prefs = (() => {
        const V = 1;
        const WRITING = ["vertical", "horizontal"];
        const BINDING = ["auto", "right", "left"];
        const THEME = ["system", "light", "dark"];
        const FONT_STEPS = [22, 25, 28, 32, 36, 40];
        // Not the range the settings panel offers — a guard, so a hand-edited or
        // half-migrated value cannot hand the paginator a size at which a single
        // sentence does not fit the box and the fill loop has nothing to place.
        const FONT_MIN = 14;
        const FONT_MAX = 48;

        const defaults = () => ({
          writingMode: "vertical",
          // 改行 is stored per writing mode because the right answer differs by
          // mode rather than by taste: 縦書き on a phone reaches a 26-character
          // measure and reads as prose, 横書き reaches 12 and only works one
          // sentence to the line.
          linebreaks: { vertical: false, horizontal: true },
          binding: "auto",
          fontSize: 28,
          theme: "system",
          furigana: false,
          trans: false,
          meaning: false,
        });

        const oneOf = (list) => (v) => (list.indexOf(v) >= 0 ? v : undefined);
        const bool = (v) => (typeof v === "boolean" ? v : undefined);
        const size = (v) =>
          typeof v === "number" && isFinite(v)
            ? Math.min(FONT_MAX, Math.max(FONT_MIN, Math.round(v)))
            : undefined;
        const marks = (v) => {
          if (!Store.plain(v)) return undefined;
          const d = defaults().linebreaks;
          return {
            vertical: typeof v.vertical === "boolean" ? v.vertical : d.vertical,
            horizontal: typeof v.horizontal === "boolean" ? v.horizontal : d.horizontal,
          };
        };

        // fx is what a change to the field actually costs, and it is the whole
        // reason this layer notifies instead of letting callers poll:
        //   layout  — screens must be rebuilt from DATA and re-split
        //   binding — the turn direction may have flipped; nothing reflows
        //   theme   — custom properties only
        //   gates   — ふ/訳/意. Ruby is always laid out and only its opacity
        //             moves, so arming furigana must never repaginate: the
        //             paginator measures overflow, and a reflow here would move
        //             sub-screen boundaries under the reader's finger.
        const FIELDS = {
          writingMode: { ok: oneOf(WRITING), fx: ["layout", "binding"] },
          linebreaks: { ok: marks, fx: ["layout"] },
          binding: { ok: oneOf(BINDING), fx: ["binding"] },
          fontSize: { ok: size, fx: ["layout"] },
          theme: { ok: oneOf(THEME), fx: ["theme"] },
          furigana: { ok: bool, fx: ["gates"] },
          trans: { ok: bool, fx: ["gates"] },
          meaning: { ok: bool, fx: ["gates"] },
        };

        let state = defaults();
        let snapshot = null;
        let rest = {};
        const subs = [];

        // Adding and removing fields is free, because each one is validated on
        // its own against the default: a record written by a newer build loads
        // field by field rather than all or nothing. So v only has to cover what
        // that cannot absorb — a field whose meaning changes under a stable
        // name. Rename the field instead and this stays empty. A step added here
        // must only fill in what is absent: an older engine re-stamps v on every
        // write, so 1 -> 2 can meet a record that has already been through it.
        const MIGRATE = {};

        // Unrecognised keys are carried through untouched, so an older engine —
        // docs/versions/ ships five, on the same origin — cannot strand a newer
        // build's settings the next time it writes one of its own.
        const load = () => {
          const out = defaults();
          rest = {};
          let raw = Store.readJSON("prefs");
          if (!raw) return out;
          for (let v = typeof raw.v === "number" ? raw.v : V; MIGRATE[v]; v++) raw = MIGRATE[v](raw);
          for (const key of Object.keys(raw)) {
            if (key === "v") continue;
            if (!FIELDS[key]) {
              rest[key] = raw[key];
              continue;
            }
            const value = FIELDS[key].ok(raw[key]);
            if (value !== undefined) out[key] = value;
          }
          return out;
        };

        const save = Store.defer(() => {
          Store.writeJSON("prefs", Object.assign({}, rest, state, { v: V }));
        }, 150);

        const vertical = () => state.writingMode === "vertical";
        const linebreaks = () => state.linebreaks[state.writingMode];
        const density = () => (linebreaks() ? "broken" : "flowing");
        // 自動: 縦書き is bound on the right and turns leftward like a Japanese
        // book, 横書き on the left and turns rightward like a Western one. Every
        // consumer that needs a direction derives it from here rather than from
        // the writing mode, or the drag, the arrows and the nav will disagree
        // under an override.
        const bindingEdge = () =>
          state.binding === "auto" ? (vertical() ? "right" : "left") : state.binding;

        const apply = () => {
          const c = document.body.classList;
          c.toggle("vertical", vertical());
          c.toggle("horizontal", !vertical());
          c.toggle("broken", linebreaks());
          c.toggle("flowing", !linebreaks());
          c.toggle("bind-right", bindingEdge() === "right");
          c.toggle("bind-left", bindingEdge() === "left");
          for (const key of ["furigana", "trans", "meaning"]) c.toggle(key, state[key]);
          const root = document.documentElement;
          // The dark palette is a media query, so an explicit choice has to
          // out-specify it rather than replace it. No attribute means follow the
          // OS, which is what the query alone already did.
          if (state.theme === "system") root.removeAttribute("data-theme");
          else root.setAttribute("data-theme", state.theme);
          // px, not rem: the setting has to be what the type measures, which is
          // what the type-fidelity check asserts. The cost is that the browser's
          // own text-size setting no longer scales the story — this control
          // replaces it, and unlike the browser's it is one tap away.
          root.style.setProperty("--fs", state.fontSize + "px");
        };

        const freeze = () =>
          Object.freeze(
            Object.assign({}, state, {
              linebreaks: Object.freeze(Object.assign({}, state.linebreaks)),
            })
          );

        const commit = (keys, external) => {
          if (!keys.length) return;
          snapshot = freeze();
          const effects = { layout: false, binding: false, theme: false, gates: false };
          for (const key of keys) for (const fx of FIELDS[key].fx) effects[fx] = true;
          // Classes and custom properties land before anyone is told, because a
          // subscriber that hears "layout" measures the box immediately and has
          // to measure it in the new writing mode, not the old one.
          apply();
          if (!external) save();
          const change = { keys: keys, effects: effects, prefs: snapshot, external: !!external };
          for (const fn of subs.slice()) {
            try {
              fn(change);
            } catch (e) {
              // One dead subscriber must not leave the rest of the reader
              // showing the previous state. Rethrow out of band so the failure
              // still reaches the console.
              setTimeout(() => {
                throw e;
              });
            }
          }
        };

        // linebreaks is the only field that is not a scalar.
        const same = (key, a, b) =>
          key === "linebreaks" ? a.vertical === b.vertical && a.horizontal === b.horizontal : a === b;

        const stage = (key, value) => {
          const field = FIELDS[key];
          if (!field) return false;
          const next = field.ok(value);
          // A settings control re-emits the value it already holds on every
          // interaction, and repaginating for that shows as a stutter.
          if (next === undefined || same(key, state[key], next)) return false;
          state[key] = next;
          return true;
        };

        const set = (key, value) => {
          if (!stage(key, value)) return false;
          commit([key]);
          return true;
        };

        const setAll = (patch) => {
          const keys = [];
          for (const key of Object.keys(patch)) if (stage(key, patch[key])) keys.push(key);
          commit(keys);
          return keys.length;
        };

        const toggle = (key) => set(key, !state[key]);

        const setLinebreaks = (on) => {
          const next = Object.assign({}, state.linebreaks);
          next[state.writingMode] = !!on;
          return set("linebreaks", next);
        };

        // The panel offers discrete steps rather than a slider: every accepted
        // write notifies synchronously and repaginates, and a slider would do
        // that once per pixel.
        const stepFont = (d) => {
          // Take the next rung on the side pressed rather than stepping from an
          // index: a size off the ladder — a hand-edited store, or one the
          // FONT_MIN clamp produced — has no index, and a guessed one walks the
          // wrong way or skips the rung the reader was asking for.
          const cur = state.fontSize;
          const side = FONT_STEPS.filter((s) => (d > 0 ? s > cur : s < cur));
          const next = side.length
            ? (d > 0 ? side[0] : side[side.length - 1])
            : FONT_STEPS[d > 0 ? FONT_STEPS.length - 1 : 0];
          return set("fontSize", next);
        };

        const reset = () => {
          rest = {};
          setAll(defaults());
          save();
        };

        const subscribe = (fn) => {
          subs.push(fn);
          return () => {
            const i = subs.indexOf(fn);
            if (i >= 0) subs.splice(i, 1);
          };
        };

        const adopt = () => {
          const before = state;
          state = load();
          const keys = [];
          for (const key of Object.keys(FIELDS)) if (!same(key, before[key], state[key])) keys.push(key);
          commit(keys, true);
        };

        const boot = () => {
          state = load();
          snapshot = freeze();
          apply();
          // Two stories in two tabs share one prefs key; without this the second
          // tab keeps rendering at the old size until it is reloaded.
          Store.listen("prefs", adopt);
          return snapshot;
        };

        snapshot = freeze();

        return {
          V,
          FONT_STEPS,
          FONT_MIN,
          FONT_MAX,
          boot,
          subscribe,
          reset,
          get: () => snapshot,
          set,
          setAll,
          toggle,
          vertical,
          linebreaks,
          setLinebreaks,
          stepFont,
          density,
          bindingEdge,
        };
      })();

      // ----------------------------------------------------------- progress --
      const Progress = (() => {
        // page is 1-based — the number the reader shows — so done reduces to
        // page >= of and the record reads correctly in devtools. The contents
        // page emitted by index.py reads the same record, and this comment and
        // the one in index.py's TEMPLATE are the two places that convention is
        // written down. sub stays 0-based: it indexes the screens a page was
        // split into, and 0 is its value on every page that did not split.
        let slug = "";
        let of = 0;
        let done = false;
        let rec = null;

        const flush = Store.defer(() => {
          if (!rec) return;
          // Re-read rather than hold the map: another tab may be reading another
          // story into the same key, and every write rewrites the whole object.
          // Nothing is ever pruned — this reader cannot know which of the other
          // slugs are live stories, and one of them is its own archived version.
          const all = Store.readJSON("progress") || {};
          all[slug] = rec;
          Store.writeJSON("progress", all);
        }, 400);

        // No slug means no tracking. A build made before build.py started
        // emitting one has no stable identity, and falling back to the title
        // would merge an archived version's progress into the current story,
        // whose page count is different.
        const open = (storySlug, pageCount) => {
          slug = storySlug || "";
          of = Math.max(1, Math.round(pageCount) || 1);
          const all = slug ? Store.readJSON("progress") || {} : {};
          const saved = Store.plain(all[slug]) ? all[slug] : null;
          done = !!(saved && saved.done === true);
          let pageIndex = 0;
          let sub = 0;
          if (saved && typeof saved.page === "number" && isFinite(saved.page)) {
            // Clamped here because this is the entry path, and nothing else on
            // it range-checks: a stored index against a story that has been
            // rewritten since would index past DATA.pages and throw before the
            // first screen renders.
            pageIndex = Math.min(of - 1, Math.max(0, Math.round(saved.page) - 1));
            // A different page count means the story changed, so which screen of
            // that page the reader was on no longer refers to anything.
            if (saved.of === of && typeof saved.sub === "number" && isFinite(saved.sub)) {
              sub = Math.max(0, Math.round(saved.sub));
            }
          }
          return { pageIndex: pageIndex, sub: sub, done: done, restored: pageIndex > 0 || sub > 0 };
        };

        // subCount is how many screens the authored page's own content produced.
        // あとがき screens carry the last page's index and continue sub past that
        // count, so arriving at one reads as done without needing a second flag.
        const mark = (pageIndex, sub, subCount) => {
          if (!slug) return;
          const idx = isFinite(pageIndex) ? Math.max(0, Math.round(pageIndex)) : 0;
          const s = isFinite(sub) ? Math.max(0, Math.round(sub)) : 0;
          if (idx >= of - 1 && s >= (subCount || 1) - 1) done = true;
          rec = {
            page: Math.min(of, idx + 1),
            sub: s,
            of: of,
            // Sticky: finishing a story is a fact about the story, and a re-read
            // resumes where it is without erasing it.
            done: done,
            at: Date.now(),
          };
          flush();
        };

        const clear = () => {
          done = false;
          rec = null;
          if (!slug) return;
          const all = Store.readJSON("progress") || {};
          delete all[slug];
          Store.writeJSON("progress", all);
        };

        return { open, mark, clear, done: () => done };
      })();

      // ------------------------------------------------------------ pagebox --
      // The page box is constant in CELLS, not in pixels: a measure (characters
      // per column in 縦書き, per line in 横書き) floored by what the viewport
      // allows and capped at the Japanese typographic 45, and an extent (columns
      // / lines) capped so the median 88-character authored page fills it around
      // 70%. That is why a 1440 laptop and a 390 phone show the same page with
      // different margins rather than a wider page.
      const PageBox = (() => {
        const MEASURE_CAP = 45; // upper end of the 35-45 Japanese measure
        const MEASURE_FLOOR = 6; // below this nothing is readable anyway
        const TARGET_CELLS = 170; // median page is 88 chars -> ~70% column fill
        const EXTENT_MIN = 3;
        const EXTENT_MAX = 12; // without it, phone 横書き is a 12x15 wall

        const root = document.documentElement;
        const listeners = new Set();

        let track = null;
        let host = null;
        let probe = null;
        let suspended = false;
        let pending = false;
        let raf = 0;

        let m = {
          measure: 30, extent: 6, cells: 180, room: 6, cap: 6,
          fs: 28, advance: 56, vertical: true, cellW: 0, cellH: 0,
        };

        // The measuring cell's content box is the available area: viewport minus
        // the chrome reserve minus the safe-area insets, all resolved by CSS. No
        // JS here needs to know a safe area exists.
        const contentBox = (el) => {
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return {
            w: Math.max(0, r.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)),
            h: Math.max(0, r.height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)),
          };
        };

        // Read the USED font-size and line-height off the probe rather than the
        // pref number, so the arithmetic cannot drift from what the browser laid
        // out and the per-mode --lh is picked up for free.
        function compute() {
          const cs = getComputedStyle(probe);
          const fs = parseFloat(cs.fontSize) || 16;
          let advance = parseFloat(cs.lineHeight);
          if (!(advance > 0)) advance = fs * 2;
          const vertical = cs.writingMode.indexOf("vertical") === 0;

          const a = contentBox(probe.parentNode);
          const inlineRoom = vertical ? a.h : a.w;
          const blockRoom = vertical ? a.w : a.h;

          const measure = Math.max(
            MEASURE_FLOOR,
            Math.min(MEASURE_CAP, Math.floor(inlineRoom / fs))
          );
          const room = Math.max(1, Math.floor(blockRoom / advance));
          const cap = Math.max(
            EXTENT_MIN,
            Math.min(EXTENT_MAX, Math.ceil(TARGET_CELLS / measure))
          );
          const extent = Math.min(room, cap);

          return {
            measure, extent, cells: measure * extent, room, cap,
            fs, advance, vertical, cellW: a.w, cellH: a.h,
          };
        }

        // Only the integer tuple and the cell size matter to anyone else, so the
        // change test is the debounce — there is no timer, because a stale box
        // after a rotation would race the gesture layer.
        function refresh(force) {
          if (!probe) return m;
          if (suspended) { pending = true; return m; }

          // Recompute against the values already written, so a measure the CSS
          // clamped to 100% is re-derived from the clamp rather than compounding.
          const next = compute();
          root.style.setProperty("--measure", String(next.measure));
          root.style.setProperty("--extent", String(next.extent));

          const changed =
            force === true ||
            next.measure !== m.measure ||
            next.extent !== m.extent ||
            next.vertical !== m.vertical ||
            Math.abs(next.fs - m.fs) > 0.01 ||
            Math.abs(next.cellW - m.cellW) > 0.5 ||
            Math.abs(next.cellH - m.cellH) > 0.5;

          const prev = m;
          m = next;
          if (changed) {
            for (const fn of listeners) {
              try { fn(m, prev); } catch (e) { /* a bad listener must not stop layout */ }
            }
          }
          return m;
        }

        function schedule() {
          if (raf) return;
          raf = requestAnimationFrame(() => {
            raf = 0;
            refresh(false);
          });
        }

        // How far a box may overrun and still count as fitting. On the block axis
        // that is what can protrude past the last line box, never the pitch of a
        // line: ruby (0.44em) and 傍点 (0.5em) sit inside the half-leading at
        // every line-height this design permits — the whole argument for the 1.94
        // floor — so the allowance is a rounding guard of one pixel, and it grows
        // only if someone drops --lh below that floor. Half a line advance, the
        // number this replaces, licensed 1.0em in 縦書き and 1.3em in 横書き:
        // enough to lay a broken-横書き page two paragraph margins over the box
        // and let the clip shave the line beneath them, and enough to swallow a
        // whole あとがき line. The clip margin stays what it was for — ink on the
        // box edge — rather than being spent on layout.
        //
        // On the inline axis 禁則処理 can push a 約物 one character past the end of
        // a line, and moving that line to another screen does not cure it, so one
        // character it stays.
        //
        // The allowance belongs to the BOX, never to the page: .after lays out
        // horizontal-tb at 1rem/1.7 whatever the story is set to, and the page's
        // 56px line accepted an あとがき prefix a full line over the box — which
        // overflow: clip then deleted for good.
        //
        // scrollWidth/scrollHeight/clientWidth/clientHeight are unsigned and
        // interoperable in both writing modes; scrollLeft's sign is not, and is
        // never read anywhere in this file.
        function boxSlack(el) {
          const cs = getComputedStyle(el);
          const fs = parseFloat(cs.fontSize) || 16;
          let advance = parseFloat(cs.lineHeight);
          if (!(advance > 0)) advance = fs * 1.2;
          const ink = Math.max(1, (0.5 - (advance / fs - 1) / 2) * fs);
          return cs.writingMode.indexOf("vertical") === 0
            ? { w: ink, h: fs }
            : { w: fs, h: ink };
        }

        function overflows(el, slack) {
          const s = slack || boxSlack(el);
          return (
            el.scrollWidth - el.clientWidth > s.w ||
            el.scrollHeight - el.clientHeight > s.h
          );
        }

        // Every page break in the book is decided by scrollWidth/scrollHeight on
        // the probe. If an engine reports the padding box instead, nothing ever
        // overflows, nothing ever splits, and the only symptom is text quietly
        // shaved off the bottom of every long page. Say so at boot instead.
        function selfTest() {
          if (!probe) return false;
          probe.className = "page";
          probe.textContent = "";
          const p = document.createElement("p");
          p.textContent = "あ".repeat(Math.max(m.cells, 40) * 3);
          probe.append(p);
          const ok = overflows(probe);
          probe.textContent = "";
          return ok;
        }

        function init() {
          track = $("track");
          if (!track) throw new Error("PageBox: #track missing");

          // Built here rather than in reader.html: build.py's render_split
          // matches reader.html by whole indented block, and every node added
          // there is one more chance to break the harness silently. It is a body
          // child, never a descendant of the track — the track carries a live
          // transform, which would make it the containing block for a fixed
          // descendant.
          host = document.createElement("div");
          host.id = "measure";
          host.setAttribute("aria-hidden", "true");
          if ("inert" in host) host.inert = true;
          const cell = document.createElement("div");
          cell.className = "cell";
          probe = document.createElement("div");
          probe.className = "page";
          cell.append(probe);
          host.append(cell);
          document.body.append(host);

          // #measure is fixed at inset 0 and its .cell is absolute at inset 0, so
          // both resolve to exactly the box a live cell resolves to. Nothing is
          // pinned from JS; one set of CSS rules sizes both.
          new ResizeObserver(schedule).observe(track);
          if (window.visualViewport) {
            window.visualViewport.addEventListener("resize", schedule);
          }
          window.addEventListener("orientationchange", schedule);
          // System fonts resolve synchronously, but a platform that substitutes
          // late would change the metrics the first pagination was measured
          // against, and a boundary would move under the reader.
          if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(schedule, () => {});
          }
          return refresh(true);
        }

        return {
          init,
          refresh: () => refresh(false),
          metrics: () => m,
          measureBox: () => probe,
          clearMeasure: () => { if (probe) probe.textContent = ""; },
          overflows,
          boxSlack,
          selfTest,
          onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },

          // iOS fires viewport resizes mid-gesture (toolbar, rubber-band). A
          // geometry change there would repaginate under the reader's finger, so
          // the track freezes this for the length of a drag; anything that
          // arrived meanwhile is coalesced into one notification.
          suspend() { suspended = true; },
          resume() {
            suspended = false;
            if (pending) { pending = false; refresh(false); }
          },

          // For the verification pass: one line per geometry, console-readable.
          report() {
            return (
              (m.vertical ? "縦" : "横") + " " + m.fs + "px/" + (m.advance / m.fs).toFixed(2) +
              " cell " + Math.round(m.cellW) + "x" + Math.round(m.cellH) +
              " measure " + m.measure + " extent " + m.extent +
              " (room " + m.room + ", cap " + m.cap + ") = " + m.cells + " cells"
            );
          },
        };
      })();

      // ---------------------------------------------------------- paginator --
      // The authored page is an atom: it may split across screens, it is never
      // merged with another, and nothing ever crosses an authored break. The page
      // count is validated against the brief by stats.py and the afterwords cite
      // pages by number in published prose, so the number has to keep meaning
      // what it meant.
      const Paginator = (() => {
        const SEP = "·";
        const AFTER_MARK = "後";
        // Carried verbatim from the reader this replaces.
        const AFTER_LABEL = "あとがき — what this was doing (spoilers)";

        const total = DATA.pages.length;

        let mpage = null;
        let dirty = true;
        let key = "";
        let flowing = false;

        const cache = new Map(); // authored page index -> Screen[]
        const plans = new Map(); // authored page index -> block plan
        let atomList = null; // afterword atoms, geometry-independent
        let afterRuns = null; // afterword screen ranges, geometry-dependent
        let pageSlack = null; // each box's own overflow tolerance, read from it
        let afterSlack = null;

        // Everything that can change where a page breaks. Furigana is absent on
        // purpose: ruby is always laid out and only its opacity changes, so
        // arming ふりがな must not move a single boundary.
        function ensure() {
          if (!mpage) mpage = PageBox.measureBox();
          if (!dirty) return false;
          dirty = false;
          const g = PageBox.metrics();
          const k = [
            g.measure, g.extent, g.vertical ? "v" : "h",
            Prefs.density(), g.fs,
          ].join("/");
          if (k === key) return false;
          key = k;
          flowing = Prefs.density() === "flowing";
          cache.clear();
          afterRuns = null;
          pageSlack = null;
          afterSlack = null;
          return true;
        }

        // ------------------------------------------------------------ markup

        function isDialogue(sent) {
          const t = (sent.toks[0] && sent.toks[0].t) || "";
          const c = t.charAt(0);
          return c === "「" || c === "『";
        }

        // Each quoted utterance is its own paragraph; narration runs merge.
        // Grouping a run of 「 lines into one block would erase the speaker
        // alternation that is the only attribution 終電 has — 40 of its 41 quoted
        // lines carry none, and six of its pages are one unbroken run.
        function blockPlan(sents) {
          const kinds = [], owner = [];
          let block = -1, prevNarration = false;
          for (let i = 0; i < sents.length; i++) {
            const d = isDialogue(sents[i]);
            if (d || !prevNarration) {
              block++;
              kinds.push(d ? "dialogue" : "narration");
            }
            owner.push(block);
            prevNarration = !d;
          }
          return { kinds: kinds, owner: owner };
        }

        function planOf(i) {
          let p = plans.get(i);
          if (!p) {
            p = blockPlan(DATA.pages[i]);
            plans.set(i, p);
          }
          return p;
        }

        // tokFrom/tokTo are a whole sentence except on the two screens either side
        // of a sentence the box could not hold in one piece.
        function sentenceEl(sent, tokFrom, tokTo) {
          const s = document.createElement("span");
          s.className = sent.en ? "s has-en" : "s";
          if (sent.en) s.dataset.en = sent.en;
          for (let ti = tokFrom; ti < tokTo; ti++) {
            const tok = sent.toks[ti];
            if (!tok.r) {
              // A raw chunk can be a lone kanji Ichiran did not tokenise, or a
              // single ASCII space inside a name. Both go through verbatim.
              s.append(document.createTextNode(tok.t));
              continue;
            }
            const w = document.createElement("span");
            w.className = "w" + (tok.w ? " weak" : "") + (tok.n ? " new" : "");
            // The sheet reads the headword from here. textContent would
            // concatenate the <rt> kana into it and print 私わたし【わたし】.
            w.dataset.t = tok.t;
            w.dataset.kana = tok.k || "";
            w.dataset.gloss = tok.g || "";
            for (const pair of tok.r) {
              const text = pair[0], ruby = pair[1];
              if (!ruby) {
                w.append(document.createTextNode(text));
                continue;
              }
              const r = document.createElement("ruby");
              r.append(document.createTextNode(text));
              const rt = document.createElement("rt");
              rt.textContent = ruby;
              r.append(rt);
              w.append(r);
            }
            s.append(w);
          }
          return s;
        }

        // Narration blocks stay block-level <p> in both densities: text-indent
        // applies to block containers only, so a narration run turned into a span
        // would lose its 全角 indent with no error and no visual cue.
        function buildText(i, from, to, flow, head, tail) {
          const frag = document.createDocumentFragment();
          const sents = DATA.pages[i];
          const lo = (k) => (k === from ? head : 0);
          const hi = (k) => (k === to - 1 && tail >= 0 ? tail : sents[k].toks.length);
          if (!flow) {
            for (let k = from; k < to; k++) {
              const p = document.createElement("p");
              p.className = isDialogue(sents[k]) ? "dialogue" : "narration";
              p.append(sentenceEl(sents[k], lo(k), hi(k)));
              frag.append(p);
            }
            return frag;
          }
          const plan = planOf(i);
          // A screen may open in the middle of a narration block. That block is a
          // continuation, not a new paragraph, so it must not be indented — and a
          // screen opening inside a sentence is a continuation whatever the block
          // plan says.
          const cont = head > 0 || (from > 0 && plan.owner[from - 1] === plan.owner[from]);
          let p = null, owner = -1;
          for (let k = from; k < to; k++) {
            if (plan.owner[k] !== owner) {
              owner = plan.owner[k];
              p = document.createElement("p");
              p.className = plan.kinds[owner] + (k === from && cont ? " cont" : "");
              frag.append(p);
            }
            p.append(sentenceEl(sents[k], lo(k), hi(k)));
          }
          return frag;
        }

        // The afterword is one HTML string with no sentence structure exposed, so
        // it splits at word granularity instead. <template> parses it inert; the
        // markup is build-time output of indexmd.ruby_html and carries only
        // <ruby>/<rt>, everything else escaped. This is the reader's only
        // innerHTML site; en and gloss strings never go near it.
        function atoms() {
          if (atomList) return atomList;
          atomList = [];
          if (!DATA.afterword) return atomList;
          const label = document.createElement("p");
          label.className = "after-label";
          label.textContent = AFTER_LABEL;
          atomList.push(label);
          const t = document.createElement("template");
          t.innerHTML = DATA.afterword;
          for (const node of Array.from(t.content.childNodes)) {
            if (node.nodeType === 3) {
              const parts = node.data.match(/\S+\s*|\s+/g) || [];
              for (const part of parts) atomList.push(document.createTextNode(part));
            } else {
              atomList.push(node.cloneNode(true));
            }
          }
          return atomList;
        }

        function buildAfter(from, to) {
          const frag = document.createDocumentFragment();
          const list = atoms();
          for (let i = from; i < to; i++) frag.append(list[i].cloneNode(true));
          return frag;
        }

        // ---------------------------------------------------------- splitting

        function fitsText(i, from, to, head, tail) {
          mpage.className = "page";
          mpage.textContent = "";
          mpage.append(buildText(i, from, to, flowing, head, tail));
          // Read with the class on, so the tolerance is this box's own.
          if (!pageSlack) pageSlack = PageBox.boxSlack(mpage);
          return !PageBox.overflows(mpage, pageSlack);
        }

        function fitsAfter(from, to) {
          mpage.className = "after";
          mpage.textContent = "";
          mpage.append(buildAfter(from, to));
          if (!afterSlack) afterSlack = PageBox.boxSlack(mpage);
          return !PageBox.overflows(mpage, afterSlack);
        }

        // Fill until overflow, measured from the whole remainder down rather than
        // from one sentence up: at the default size most authored pages fit whole,
        // and that case then costs exactly one forced layout. Only when it fails
        // does this binary-search the longest prefix that fits, which is sound
        // because the fit is monotone in the prefix length — text only ever grows.
        //
        // The afterword's units are words, so one of them failing to fit is a
        // 34rem box narrower than a single word and there is nothing finer to
        // fall back to. The story's units are sentences, which is why splitText
        // below has one more level.
        function split(fits, count) {
          const runs = [];
          let from = 0;
          while (from < count) {
            if (fits(from, count)) {
              runs.push({ from: from, to: count, tight: false });
              break;
            }
            // At least one unit is always placed. A unit too long for the box is
            // laid down anyway and marked tight; testing and skipping would be a
            // loop that cannot make progress.
            let lo = 1, hi = count - from - 1, best = 1, ok = false;
            while (lo <= hi) {
              const mid = (lo + hi) >> 1;
              if (fits(from, from + mid)) {
                best = mid;
                ok = true;
                lo = mid + 1;
              } else {
                hi = mid - 1;
              }
            }
            runs.push({ from: from, to: from + best, tight: !ok });
            from += best;
          }
          return runs;
        }

        // Sentences are the unit, and a screen breaks between them wherever it
        // can. Where it cannot — one sentence longer than the whole box, which a
        // 390x844 phone in landscape 横書き at 40px reaches on sixteen sentences
        // across the six stories — it breaks inside the sentence at a token
        // boundary instead. Laying the sentence down over the box was the
        // alternative: measured there, the worst ran 103px past a two-line box
        // and overflow: clip deleted twenty-one line boxes of 猫を探す探偵 outright, on
        // screens with nothing to say they were incomplete. The tail keeps the
        // sentence's own <span class="s"> and its data-en, so 訳 reaches it from
        // either half.
        //
        // A position is (sentence s, token t). t is 0 except directly after such
        // a break, so a corpus with no oversized sentence paginates exactly as it
        // did when sentences were the only unit.
        function splitText(i, count) {
          const sents = DATA.pages[i];
          const runs = [];
          let s = 0, t = 0;
          while (s < count) {
            if (fitsText(i, s, count, t, -1)) {
              runs.push({ from: s, to: count, head: t, tail: -1, tight: false });
              break;
            }
            let lo = s + 1, hi = count - 1, end = 0;
            while (lo <= hi) {
              const mid = (lo + hi) >> 1;
              if (fitsText(i, s, mid, t, -1)) { end = mid; lo = mid + 1; }
              else hi = mid - 1;
            }
            if (end) {
              runs.push({ from: s, to: end, head: t, tail: -1, tight: false });
              s = end;
              t = 0;
              continue;
            }
            // Not even this one sentence fits from here. Longest run of its
            // tokens that does; one token is always placed, so t or s advances.
            const n = sents[s].toks.length;
            let a = t + 1, b = n - 1, cut = t + 1, ok = false;
            while (a <= b) {
              const mid = (a + b) >> 1;
              if (fitsText(i, s, s + 1, t, mid)) { cut = mid; ok = true; a = mid + 1; }
              else b = mid - 1;
            }
            runs.push({ from: s, to: s + 1, head: t, tail: cut, tight: !ok });
            if (cut >= n) { s++; t = 0; } else t = cut;
          }
          return runs;
        }

        function splitAfter() {
          if (afterRuns) return afterRuns;
          const n = atoms().length;
          afterRuns = n ? split(fitsAfter, n) : [];
          return afterRuns;
        }

        function computePage(i) {
          const n = DATA.pages[i].length;
          const runs = n
            ? splitText(i, n)
            : [{ from: 0, to: 0, head: 0, tail: -1, tight: false }];
          const out = runs.map((r, sub) => ({
            page: i, sub: sub, kind: "text", flowing: flowing,
            from: r.from, to: r.to, head: r.head, tail: r.tail,
            tight: r.tight, afterSub: -1,
          }));
          // An empty afterword appends zero screens. Every docs/versions build
          // ships one, and a blank trailing screen there would put the screen
          // count out of step with the page count.
          if (i === total - 1 && DATA.afterword) {
            const after = splitAfter();
            for (let k = 0; k < after.length; k++) {
              out.push({
                page: i, sub: out.length, kind: "after", flowing: flowing,
                from: after[k].from, to: after[k].to, tight: after[k].tight, afterSub: k,
              });
            }
          }
          mpage.textContent = "";
          mpage.className = "page";
          return out;
        }

        function screensOf(i) {
          if (i < 0 || i >= total) return [];
          ensure();
          let s = cache.get(i);
          if (!s) {
            s = computePage(i);
            cache.set(i, s);
          }
          return s;
        }

        function screenAt(addr) {
          if (!addr) return null;
          return screensOf(addr.page)[addr.sub] || null;
        }

        const screenCount = (i) => screensOf(i).length;

        function textCount(i) {
          const s = screensOf(i);
          let n = 0;
          for (let k = 0; k < s.length; k++) if (s[k].kind === "text") n++;
          return n;
        }

        // ------------------------------------------------------- address math

        const whole = (v) => (isFinite(v) ? Math.floor(v) : 0);

        // The only range guard in the file, and the restore path goes through it:
        // a stored position against a story whose page count has changed would
        // otherwise index past DATA.pages and throw before anything paints.
        function clamp(addr) {
          const page = Math.min(
            Math.max(whole(addr ? Number(addr.page) : 0), 0),
            total - 1
          );
          const n = Math.max(screenCount(page), 1);
          const sub = Math.min(Math.max(whole(addr ? Number(addr.sub) : 0), 0), n - 1);
          return { page: page, sub: sub };
        }

        function next(addr) {
          if (!addr) return null;
          if (addr.sub + 1 < screenCount(addr.page)) {
            return { page: addr.page, sub: addr.sub + 1 };
          }
          if (addr.page + 1 < total) return { page: addr.page + 1, sub: 0 };
          return null;
        }

        function prev(addr) {
          if (!addr) return null;
          if (addr.sub > 0) return { page: addr.page, sub: addr.sub - 1 };
          if (addr.page > 0) {
            const p = addr.page - 1;
            return { page: p, sub: Math.max(screenCount(p) - 1, 0) };
          }
          return null;
        }

        const first = () => ({ page: 0, sub: 0 });

        // End belongs to the story, not to the spoilers: the あとがき is only
        // reachable by turning past the last page.
        const last = () => ({
          page: total - 1,
          sub: Math.max(textCount(total - 1) - 1, 0),
        });

        const final = () => ({
          page: total - 1,
          sub: Math.max(screenCount(total - 1) - 1, 0),
        });

        const sameAddress = (a, b) => !!a && !!b && a.page === b.page && a.sub === b.sub;
        const isFirst = (addr) => prev(addr) === null;
        const isLast = (addr) => next(addr) === null;
        const isAfter = (addr) => {
          const s = screenAt(addr);
          return !!s && s.kind !== "text";
        };

        // A split page's first screen keeps the bare number; only the second and
        // later carry the dot, so a page that did not split reads exactly as it
        // did before.
        function screenLabel(addr) {
          const s = screenAt(addr);
          if (!s) return "";
          if (s.kind === "text") {
            return String(s.page + 1) + (s.sub ? SEP + (s.sub + 1) : "");
          }
          return AFTER_MARK + (s.afterSub ? SEP + (s.afterSub + 1) : "");
        }

        // The denominator stays the authored page count — the number cited in the
        // afterwords and stored as progress. It is meaningless on an あとがき
        // screen, so it is not shown there.
        function countLabel(addr) {
          const s = screenAt(addr);
          if (!s) return "";
          const left = screenLabel(addr);
          return s.kind === "text" ? left + " / " + total : left;
        }

        // ------------------------------------------------------------- render

        function renderScreen(pageEl, addr) {
          const s = screenAt(addr);
          pageEl.textContent = "";
          pageEl.className = "page";
          if (!s) return;
          if (s.kind === "text") {
            if (s.tight) pageEl.classList.add("tight");
            pageEl.append(buildText(s.page, s.from, s.to, s.flowing, s.head, s.tail));
            return;
          }
          // A sibling class, not a modifier: body.flowing .page p (0,2,2) would
          // otherwise beat .page.after p (0,2,1) and put a 全角 indent into
          // English prose.
          pageEl.className = "after";
          pageEl.append(buildAfter(s.from, s.to));
        }

        // 1-based on the way out, so done reduces to page >= of and index.py's
        // contents-page script reads the same convention.
        const addressFromProgress = (p) => clamp({ page: p.pageIndex, sub: p.sub });

        const idle = window.requestIdleCallback
          ? (fn) => requestIdleCallback(fn, { timeout: 500 })
          : (fn) => setTimeout(fn, 1);

        function warm(i) {
          if (i < 0 || i >= total || cache.has(i)) return;
          idle(() => { if (!cache.has(i)) screensOf(i); });
        }

        function invalidate() {
          dirty = true;
          ensure();
        }

        // VERIFICATION ENTRY POINT ONLY — forces pagination of the whole story.
        function screenCounts() {
          const out = [];
          for (let i = 0; i < total; i++) out.push(textCount(i));
          return out;
        }

        return {
          invalidate, screensOf, screenAt, screenCount, textCount, screenCounts,
          clamp, next, prev, first, last, final, isFirst, isLast, isAfter,
          sameAddress, screenLabel, countLabel, renderScreen, addressFromProgress,
          warm, total,
        };
      })();

      // -------------------------------------------------------------- sheet --
      // Two gates, one surface, and they stay separate on purpose: a word tap
      // always answers "how is this read", 意味 adds "what does it mean", 訳
      // answers "what does this sentence say". Collapsing them into one
      // tap-for-everything would hand over the whole page at once, which is the
      // one thing this reader is built not to do.
      //
      // The track is the sole input router for the text surface: it owns
      // setPointerCapture and the tap/drag discrimination, and it suppresses the
      // synthesised click that follows every gesture. So nothing here binds click
      // on the track.
      const Sheet = (() => {
        const OUT_MS = 220; // outlasts the 0.16s CSS fade
        const KEEP = "[data-keep-sheet]";

        const el = $("sheet");
        const head = $("sheet-head");
        const word = $("sheet-word");
        const kana = $("sheet-kana");
        const tags = $("sheet-tags");
        const body = $("sheet-body");
        const hint = $("sheet-hint");
        let track = null;

        let subject = null; // {kind, el, t, kana, gloss, weak, fresh, en}
        let sticky = false;
        let lit = null;
        let hoverW = null;
        let timer = 0;
        let redecorate = 0;

        const armed = (gate) => !!Prefs.get()[gate];

        // textContent on a .w concatenates the <rt> text, so 私 reads back as
        // 私わたし — which is what every gloss in every shipped story has said.
        function surfaceOf(w) {
          if (w.dataset.t) return w.dataset.t;
          let out = "";
          for (const n of w.childNodes) {
            if (n.nodeType === 3) out += n.data;
            else if (n.nodeName === "RUBY" && n.firstChild) out += n.firstChild.textContent;
          }
          return out;
        }

        function chip(cls, text) {
          const c = document.createElement("span");
          c.className = "tag " + cls;
          c.textContent = text;
          return c;
        }

        function paint() {
          if (!subject) return;
          const isWord = subject.kind === "word";
          const meaning = armed("meaning");
          head.hidden = !isWord;
          let spoken;
          if (isWord) {
            word.textContent = subject.t;
            kana.textContent = subject.kana ? "【" + subject.kana + "】" : "";
            tags.textContent = "";
            if (subject.weak) tags.append(chip("weak", "苦手"));
            if (subject.fresh) tags.append(chip("new", "新出"));
            tags.hidden = !tags.firstChild;
            const gloss = meaning ? subject.gloss : "";
            body.hidden = !gloss;
            body.textContent = gloss;
            // Never advertise a gate that would show nothing: 42 tokens ship with
            // an empty gloss.
            hint.hidden = meaning || !subject.gloss;
            spoken =
              subject.t + " " + subject.kana +
              (subject.weak ? "、苦手" : "") +
              (subject.fresh ? "、新出" : "") +
              (gloss ? "。" + gloss : "");
          } else {
            body.hidden = false;
            body.textContent = subject.en;
            hint.hidden = true;
            spoken = subject.en;
          }
          Chrome.announce(spoken);
        }

        function show() {
          clearTimeout(timer);
          paint();
          if (el.hidden) {
            el.hidden = false;
            void el.offsetHeight; // gives the .on transition a start value
          }
          el.classList.add("on");
        }

        function light(target) {
          if (lit === target) return;
          if (lit) lit.classList.remove("lit");
          lit = target;
          if (target) target.classList.add("lit");
        }

        function dismiss() {
          light(null);
          subject = null;
          sticky = false;
          hoverW = null;
          if (el.hidden) return;
          el.classList.remove("on");
          clearTimeout(timer);
          timer = setTimeout(() => { el.hidden = true; }, OUT_MS);
        }

        function showWord(w, held) {
          subject = {
            kind: "word", el: w,
            t: surfaceOf(w),
            kana: w.dataset.kana || "",
            gloss: w.dataset.gloss || "",
            weak: w.classList.contains("weak"),
            fresh: w.classList.contains("new"),
          };
          sticky = held;
          light(held ? w : null);
          show();
        }

        function showSentence(s) {
          subject = { kind: "sentence", el: s, en: s.dataset.en };
          sticky = true;
          light(s);
          show();
        }

        // Flowing mode hangs the line boxes off the <p>, not off the sentence
        // spans, so a tap in the leading between two columns lands on the block —
        // and at the vertical line-height floor of 2 that is a full em between
        // every pair of columns, roughly half the page.
        function nearestSentence(p, x, y) {
          const limit = (parseFloat(getComputedStyle(p).fontSize) || 24) * 1.5;
          let best = null;
          let bestD = limit * limit;
          for (const s of p.querySelectorAll(":scope > .s")) {
            for (const r of s.getClientRects()) {
              const dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
              const dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
              const d = dx * dx + dy * dy;
              if (d < bestD) { bestD = d; best = s; }
            }
          }
          return best;
        }

        function sentenceAt(target, x, y) {
          const s = target.closest(".s");
          if (s) return s;
          const p = typeof x === "number" ? target.closest("p") : null;
          return p ? nearestSentence(p, x, y) : null;
        }

        // A .w always wins over the sentence around it, exactly as the old click
        // handler did: the reading is owed unconditionally, the translation is
        // not. Returns true when the tap was consumed.
        function route(target, x, y) {
          if (!target || !target.closest) { dismiss(); return false; }
          if (el.contains(target)) return true;
          if (!track.contains(target)) { dismiss(); return false; }
          const w = target.closest(".w");
          if (w) { showWord(w, true); return true; }
          const s = sentenceAt(target, x, y);
          // A sentence with no translation is inert — no data-en, nothing opens.
          if (s && s.dataset.en && armed("trans")) { showSentence(s); return true; }
          dismiss();
          return false;
        }

        // A word or sentence is a tab stop only while its gate is armed: the
        // densest page carries 39 ruby tokens, and three live cells of permanently
        // focusable spans would bury every real control on the page.
        function setStop(node, on) {
          if (on) {
            node.tabIndex = 0;
            node.setAttribute("role", "button");
          } else {
            node.removeAttribute("tabindex");
            node.removeAttribute("role");
          }
        }

        function decorate(root) {
          const meaning = armed("meaning");
          const trans = armed("trans");
          for (const w of root.querySelectorAll(".w")) setStop(w, meaning);
          for (const s of root.querySelectorAll(".s[data-en]")) setStop(s, trans);
        }

        function refresh() {
          decorate(track);
          if (!subject) return;
          // Disarming 意味 with a word open drops the gloss line in place;
          // disarming 訳 with a sentence open leaves nothing to show.
          if (subject.kind === "sentence" && !armed("trans")) return dismiss();
          paint();
        }

        function start() {
          track = $("track");

          // Tap-away. The track's own taps are routed by the track, so this only
          // has to cover everything else on the page.
          document.addEventListener("pointerdown", (e) => {
            if (el.hidden) return;
            if (el.contains(e.target) || track.contains(e.target)) return;
            // 意 and 訳 stay live while the sheet is up: arming a gate with a word
            // already open is the shortest route to its meaning.
            if (e.target.closest && e.target.closest(KEEP)) return;
            dismiss();
          }, true);

          // Hover previews only with 意味 armed — :hover already reveals the ruby,
          // so without a gloss the sheet would pop up on every sweep and add
          // nothing.
          track.addEventListener("pointerover", (e) => {
            if (e.pointerType !== "mouse") return;
            const w = e.target.closest ? e.target.closest(".w") : null;
            // Unchanged means the pointer crossed into a word's own <ruby>/<rt>,
            // which is what made the old gloss flicker on every hover.
            if (w === hoverW) return;
            hoverW = w;
            if (!armed("meaning")) return;
            if (w) {
              if (!subject || subject.el !== w) showWord(w, false);
            } else if (!sticky) {
              dismiss();
            }
          });
          track.addEventListener("pointerleave", (e) => {
            if (e.pointerType !== "mouse" || sticky) return;
            dismiss();
          });

          // A span with role="button" gets no activation for free. Enter only:
          // Space is page-forward everywhere else in the reader.
          track.addEventListener("keydown", (e) => {
            if (e.key !== "Enter") return;
            const node = e.target.closest && e.target.closest(".w[tabindex], .s[tabindex]");
            if (!node) return;
            e.preventDefault();
            route(node);
          });

          // The track recycles cells, so the element the sheet is describing can
          // be rebuilt under it and a fresh cell arrives with no tab stops.
          // childList only — decorate() writes attributes, and observing those
          // would make this retrigger itself.
          new MutationObserver(() => {
            if (redecorate) return;
            redecorate = requestAnimationFrame(() => {
              redecorate = 0;
              decorate(track);
              if (subject && subject.el && !subject.el.isConnected) dismiss();
            });
          }).observe(track, { childList: true, subtree: true });

          decorate(track);
        }

        return {
          start,
          tap: route,
          dismiss,
          refresh,
          decorate,
          isOpen: () => !el.hidden,
        };
      })();

      // ------------------------------------------------------------ copy-out --
      // Dragging a sentence out of the page and into Anki or a dictionary is a
      // real thing a learner does, and the reading must not ride along: 私, never
      // 私わたし. `user-select: none` on rt is only half of that — Chrome honours
      // it in the copy string and WebKit does not — so the plain-text flavour is
      // rebuilt from the range with the annotations taken out.
      document.addEventListener("copy", (e) => {
        const sel = document.getSelection();
        if (!sel || sel.isCollapsed || !e.clipboardData) return;
        const frag = document.createDocumentFragment();
        for (let i = 0; i < sel.rangeCount; i++) frag.append(sel.getRangeAt(i).cloneContents());
        // Nothing annotated in range — a gloss, a translation, the stats — so the
        // engine's own serialisation is already right, block structure and all.
        if (!frag.querySelector("rt")) return;
        for (const rt of frag.querySelectorAll("rt, rp")) rt.remove();
        // textContent alone would run two paragraphs together.
        for (const p of frag.querySelectorAll("p")) p.after(document.createTextNode("\n"));
        e.clipboardData.setData("text/plain", frag.textContent.replace(/\n+$/, ""));
        e.preventDefault();
      });

      // ------------------------------------------------------------- chrome --
      // Two fixed overlay bars and the settings panel. Both bars keep a permanent
      // height reserve that the page box subtracts unconditionally, so the box is
      // the same size whether chrome is shown or hidden and can be measured once:
      // hiding changes opacity and inertness, never a box.
      const Chrome = (() => {
        const FOCUSABLE =
          'a[href], button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])';

        const els = {};
        let MODAL = false;
        let shown = true;
        let painted = false;
        let lastFocus = null;
        let closeHandled = true;

        function cache() {
          const ids = [
            "top", "toc", "title", "count", "bar", "prev", "next",
            "furi", "trans", "mean", "set", "veil", "settings",
            "settings-close", "stats", "live",
            "sw-lb", "sw-furi", "sw-trans", "sw-mean",
            "fs-dec", "fs-inc", "fs-val",
          ];
          for (const id of ids) els[id] = $(id);
          els.wm = els.settings.querySelectorAll('input[name="wm"]');
          els.bind = els.settings.querySelectorAll('input[name="bind"]');
          els.theme = els.settings.querySelectorAll('input[name="theme"]');
          MODAL = typeof els.settings.showModal === "function";
        }

        // inert keeps the faded bars out of the tab order and the accessibility
        // tree without taking their boxes away — the page box subtracts --top-h
        // and --bar-h unconditionally, so the bars must keep occupying them.
        function setInert(el, on) {
          if ("inert" in el) el.inert = on;
          else if (on) el.setAttribute("inert", "");
          else el.removeAttribute("inert");
        }

        function show() {
          if (shown) return;
          shown = true;
          document.body.classList.remove("chrome-off");
          setInert(els.top, false);
          setInert(els.bar, false);
        }

        function hide() {
          if (!shown || isSettingsOpen()) return;
          const p = Prefs.get();
          // An armed 訳/意 changes nothing on the page until something is tapped,
          // so the lit glyph is the only cue that the tap will do anything. The
          // bar stays up for as long as it carries that state. (Deviation from
          // plan:67, settled in review: kept deliberately — do not delete it.)
          if (p.trans || p.meaning) return;
          // inert on an element holding focus is undefined territory; drop it
          // first. A keypress brings the bars back, so nothing is stranded.
          const a = document.activeElement;
          if (a && (els.top.contains(a) || els.bar.contains(a))) a.blur();
          shown = false;
          document.body.classList.add("chrome-off");
          setInert(els.top, true);
          setInert(els.bar, true);
        }

        const announce = (text) => { if (els.live) els.live.textContent = text || ""; };

        // Called after every settled turn and on boot. The label is the
        // paginator's, because it is what knows about あとがき screens.
        function update(addr) {
          els.count.textContent = Paginator.countLabel(addr);
          els.prev.disabled = Paginator.isFirst(addr);
          els.next.disabled = Paginator.isLast(addr);
          // The first paint is the reader arriving, not a turn; announcing it
          // would talk over the page title.
          if (!painted) { painted = true; return; }
          announce(
            Paginator.isAfter(addr)
              ? "あとがき"
              : Paginator.screenLabel(addr) + "ページ 全" + Paginator.total + "ページ"
          );
        }

        function syncGates(p) {
          els.furi.setAttribute("aria-pressed", String(!!p.furigana));
          els.trans.setAttribute("aria-pressed", String(!!p.trans));
          els.mean.setAttribute("aria-pressed", String(!!p.meaning));
          els["sw-furi"].checked = !!p.furigana;
          els["sw-trans"].checked = !!p.trans;
          els["sw-mean"].checked = !!p.meaning;
        }

        function syncControls() {
          const p = Prefs.get();
          syncGates(p);
          for (const r of els.wm) r.checked = r.value === p.writingMode;
          for (const r of els.bind) r.checked = r.value === p.binding;
          for (const r of els.theme) r.checked = r.value === p.theme;
          els["sw-lb"].checked = Prefs.linebreaks();
          els["fs-val"].textContent = p.fontSize + "px";
          const steps = Prefs.FONT_STEPS;
          els["fs-dec"].disabled = p.fontSize <= steps[0];
          els["fs-inc"].disabled = p.fontSize >= steps[steps.length - 1];
          // A button that disables itself under the finger drops focus to <body>;
          // hand it to the other end of the stepper instead.
          if (els["fs-dec"].disabled && document.activeElement === els["fs-dec"]) els["fs-inc"].focus();
          if (els["fs-inc"].disabled && document.activeElement === els["fs-inc"]) els["fs-dec"].focus();
        }

        // iOS tints its own toolbar from the page, so an explicit theme has to
        // reach the meta or the toolbar keeps following the OS.
        function syncThemeColor() {
          const meta = $("theme-color");
          if (!meta) return;
          const bg = getComputedStyle(document.body).backgroundColor;
          if (bg) meta.setAttribute("content", bg);
        }

        // The attribute, not .open: it is correct on both the showModal path and
        // on an element where .open does not exist.
        const isSettingsOpen = () => els.settings.hasAttribute("open");

        function openSettings() {
          if (isSettingsOpen()) return;
          const was = document.activeElement;
          lastFocus = was && was !== document.body && was !== document.documentElement ? was : els.set;
          closeHandled = false;
          show();
          Sheet.dismiss();
          syncControls();
          els.set.setAttribute("aria-expanded", "true");
          if (MODAL) els.settings.showModal();
          else { els.veil.hidden = false; els.settings.setAttribute("open", ""); }
          // The panel itself, not its first control: a programmatic focus on a
          // tabindex="-1" element does not match :focus-visible, so a thumb never
          // opens the panel onto a keyboard ring.
          els.settings.focus();
        }

        // close() queues its event, so closeSettings() restores focus itself and
        // this guard keeps the later event from stealing it back.
        function afterClose() {
          if (closeHandled) return;
          closeHandled = true;
          els.set.setAttribute("aria-expanded", "false");
          els.veil.hidden = true;
          const back = lastFocus && lastFocus.isConnected ? lastFocus : els.set;
          lastFocus = null;
          if (back) { try { back.focus(); } catch (e) {} }
        }

        function closeSettings() {
          if (!isSettingsOpen()) return false;
          if (MODAL) els.settings.close();
          else els.settings.removeAttribute("open");
          afterClose();
          return true;
        }

        function focusables() {
          return Array.prototype.filter.call(
            els.settings.querySelectorAll(FOCUSABLE),
            (el) => el.offsetParent !== null || el === document.activeElement
          );
        }

        function trapTab(e) {
          if (e.key !== "Tab") return;
          const f = focusables();
          if (!f.length) return;
          const first = f[0];
          const last = f[f.length - 1];
          const a = document.activeElement;
          if (e.shiftKey && (a === first || a === els.settings)) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && a === last) { e.preventDefault(); first.focus(); }
        }

        // The old #note string, moved out of the reading view. Built as nodes
        // rather than markup: the 新出 list is dictionary text from the build, and
        // the あとがき is the reader's only legitimate innerHTML.
        function fillStats() {
          const s = (DATA && DATA.stats) || {};
          const approved = s.approved || [];
          els.stats.textContent = "";
          const row = (k, v) => {
            const d = document.createElement("div");
            d.className = "srow";
            const a = document.createElement("span");
            a.textContent = k;
            const b = document.createElement("b");
            b.textContent = v;
            d.append(a, b);
            els.stats.append(d);
          };
          row("漢字語", String(s.words || 0));
          row("既知語彙", String(s.knownVocab || 0));
          if (s.weak && s.weak.length) row("苦手", String(s.weak.length));
          if (approved.length) row("新出", approved.join("、"));
          if (s.translated) row("訳", s.translated + " / " + s.sentences);
        }

        function onRadio(nodes, key) {
          for (const r of nodes) {
            r.addEventListener("change", () => { if (r.checked) Prefs.set(key, r.value); });
          }
        }

        function bind() {
          els.prev.addEventListener("click", () => { show(); Track.step(-1); });
          els.next.addEventListener("click", () => { show(); Track.step(1); });
          els.furi.addEventListener("click", () => Prefs.toggle("furigana"));
          els.trans.addEventListener("click", () => Prefs.toggle("trans"));
          els.mean.addEventListener("click", () => Prefs.toggle("meaning"));
          els.set.addEventListener("click", openSettings);
          els["settings-close"].addEventListener("click", closeSettings);

          onRadio(els.wm, "writingMode");
          onRadio(els.bind, "binding");
          onRadio(els.theme, "theme");

          // 改行 is stored per writing mode, so the switch always writes the slot
          // belonging to the mode currently on screen.
          els["sw-lb"].addEventListener("change", () => Prefs.setLinebreaks(els["sw-lb"].checked));
          els["sw-furi"].addEventListener("change", () => Prefs.set("furigana", els["sw-furi"].checked));
          els["sw-trans"].addEventListener("change", () => Prefs.set("trans", els["sw-trans"].checked));
          els["sw-mean"].addEventListener("change", () => Prefs.set("meaning", els["sw-mean"].checked));

          els["fs-dec"].addEventListener("click", () => Prefs.stepFont(-1));
          els["fs-inc"].addEventListener("click", () => Prefs.stepFont(1));

          // A click whose target is the dialog itself landed on ::backdrop — the
          // panel's own content is always a descendant.
          els.settings.addEventListener("click", (e) => {
            if (e.target === els.settings) closeSettings();
          });
          els.veil.addEventListener("click", closeSettings);
          els.settings.addEventListener("close", afterClose);

          // The panel owns every key while it is open. Stopping propagation here
          // is what keeps f/t/m and the arrows out of a form, and it means the
          // track's keyboard handler needs no guard of its own.
          els.settings.addEventListener("keydown", (e) => {
            e.stopPropagation();
            if (e.key === "Escape") { e.preventDefault(); closeSettings(); return; }
            if (!MODAL) trapTab(e);
          });

          // Capture, so the bars are back before anything else acts on the key.
          document.addEventListener("keydown", show, true);

          const dark = matchMedia("(prefers-color-scheme: dark)");
          if (dark.addEventListener) {
            dark.addEventListener("change", () => requestAnimationFrame(syncThemeColor));
          }
        }

        function init() {
          cache();
          els.title.textContent = DATA.title || "";
          // docs/versions/ has no contents page of its own; the version builds are
          // the only slugs carrying a dot.
          if (DATA.slug && DATA.slug.indexOf(".") !== -1) {
            els.toc.setAttribute("href", "../index.html");
          }
          fillStats();
          bind();
          syncControls();
          syncThemeColor();
        }

        return {
          init, show, hide, update, announce, syncGates, syncControls,
          syncThemeColor, openSettings, closeSettings, isSettingsOpen,
          isShown: () => shown,
        };
      })();

      // -------------------------------------------------------------- track --
      // Three cells — previous, current, next — in one horizontal flex row that
      // translates under the finger and snaps. The cells recycle rather than
      // re-render: a turn moves one node and repaints only the screen that just
      // came into range, so the cell the reader dragged into is the same DOM they
      // were already looking at.
      //
      // Chrome must stay OUTSIDE this element. A transform makes an ancestor the
      // containing block for position:fixed descendants, so #top, #bar, #sheet and
      // #settings are siblings of #track, never children — and #track must never
      // acquire will-change: transform, a non-none filter, backdrop-filter or
      // contain: paint, each of which does the same thing on its own.
      const Track = (() => {
        const TAP_SLOP = 8; // px of travel that still counts as a tap
        const BAND = 0.35; // rubber-band resistance past the first/last screen
        const COMMIT = 0.25; // fraction of a cell width that commits a turn
        const FLICK = 0.5; // px/ms — a throw commits regardless of distance
        const SNAP_MS = 260;
        const VELOCITY_WINDOW = 100; // ms of samples behind the release
        const VELOCITY_FLOOR = 8; // ms — shorter than this is not a measurement
        // Anything here keeps its own click; everything else in the track is text
        // and belongs to disclosure.
        const INTERACTIVE = "a,button,summary,input,select,textarea,label";
        const TYPING = "input,select,textarea,[contenteditable]";

        const track = $("track");
        const reduced = matchMedia("(prefers-reduced-motion: reduce)");

        let addr = { page: 0, sub: 0 };
        let width = 1;
        let bound = null; // "right" | "left", resolved from 綴じ + writing mode
        let advanceSign = 1; // sign of a drag dx that means "next"
        let tx = null; // inline translate in px; null means resting at -width
        let drag = null;
        let pending = null; // the settle waiting on a running snap
        let settleToken = 0;
        let settleTimer = 0;
        let suppressClick = false;
        let mouseDrag = false;
        let snapMs = reduced.matches ? 0 : SNAP_MS;

        // Reduce Motion is a Control Centre toggle on iOS, so it moves mid-read.
        reduced.addEventListener("change", (e) => { snapMs = e.matches ? 0 : SNAP_MS; });

        // Slot 1 is always the screen on view. Which side holds "next" is the
        // whole of the binding difference, so it is one sign and nothing else: a
        // right-bound book has its spine on the right, so the next page arrives
        // from the left and the content travels right.
        const relOf = (slot) => -advanceSign * (slot - 1);
        const restX = () => -width;
        const snapX = (rel) => -width + advanceSign * rel * width;
        const at = (rel) => (rel === 0 ? addr : rel > 0 ? Paginator.next(addr) : Paginator.prev(addr));
        const keyOf = (a) => (a ? a.page + ":" + a.sub : "");

        function setX(x) {
          tx = x;
          track.style.transform = "translate3d(" + x + "px,0,0)";
        }

        function rest() {
          tx = null;
          // Per cent, not pixels, so a resize while idle needs no recalculation.
          track.style.transform = "translateX(-100%)";
        }

        // dataset.screen is the paint cache key. After a rotation two cells
        // already carry the right one and are skipped; after a jump, a binding
        // flip or a re-pagination none of them do and all three repaint. One code
        // path for turn, jump, flip and relayout.
        function paint() {
          const slots = track.children;
          for (let s = 0; s < 3; s++) {
            const cell = slots[s];
            const target = at(relOf(s));
            const key = keyOf(target);
            if (cell.dataset.screen !== key) {
              cell.dataset.screen = key;
              Paginator.renderScreen(cell.firstElementChild, target);
            }
            const current = s === 1;
            cell.classList.toggle("is-current", current);
            if (current) {
              cell.removeAttribute("aria-hidden");
              cell.removeAttribute("inert");
            } else {
              cell.setAttribute("aria-hidden", "true");
              cell.setAttribute("inert", "");
            }
          }
        }

        // Removed, never blanked: keyOf(null) is a string too, so any string
        // sentinel is a value a real key could collide with, and the collision is
        // silent — the end-of-story cell keeps its last render and the rubber-band
        // slides a stale page into view. An absent attribute reads as undefined,
        // which no key can ever equal.
        function invalidate() {
          for (const cell of track.children) delete cell.dataset.screen;
        }

        function rotate(rel) {
          if (advanceSign * rel === -1) track.append(track.firstElementChild);
          else if (advanceSign * rel === 1) track.prepend(track.lastElementChild);
        }

        function announce() {
          Progress.mark(addr.page, addr.sub, Paginator.textCount(addr.page));
          Chrome.update(addr);
          Paginator.warm(addr.page + 1);
          Paginator.warm(addr.page - 1);
        }

        function settle(rel) {
          settleToken++;
          clearTimeout(settleTimer);
          pending = null;
          // Clearing the transition before the transform is what stops the reset
          // from animating backwards over the turn we just made.
          track.style.transition = "";
          if (rel) {
            const target = at(rel);
            if (target) { rotate(rel); addr = target; }
          }
          rest();
          track.style.willChange = "";
          paint();
          announce();
          PageBox.resume();
        }

        function animateTo(x, rel) {
          const from = tx === null ? restX() : tx;
          // A delta the compositor rounds away fires no transitionend, and a
          // zero-length spring-back is the common case, so settle it outright.
          if (snapMs <= 0 || Math.abs(x - from) < 0.5) { settle(rel); return; }
          const token = ++settleToken;
          clearTimeout(settleTimer);
          pending = { rel: rel };
          track.style.transition = "transform " + snapMs + "ms cubic-bezier(.22,.61,.36,1)";
          setX(x);
          track.addEventListener("transitionend", function done(e) {
            if (e.target !== track || e.propertyName !== "transform") return;
            track.removeEventListener("transitionend", done);
            if (token === settleToken) settle(rel);
          });
          // A backgrounded tab never fires the event at all; the timer is the one
          // guarantee that the track does not stop mid-page.
          settleTimer = setTimeout(() => {
            if (token === settleToken) settle(rel);
          }, snapMs + 80);
        }

        function settleNow() {
          if (pending) settle(pending.rel);
        }

        // Walks back to the oldest sample still inside the window that is also old
        // enough to divide by. Coalesced moves flushed in one task span almost no
        // time, and dividing by that invents a flick out of a nudge.
        function velocity(d) {
          const s = d.samples;
          const last = s[s.length - 1];
          for (let i = s.length - 2; i >= 0; i--) {
            const dt = last.t - s[i].t;
            if (dt > VELOCITY_WINDOW) break;
            if (dt >= VELOCITY_FLOOR) return (last.x - s[i].x) / dt;
          }
          return 0;
        }

        function tap(d) {
          // A control inside the track keeps its own click; text does not.
          if (d.down && d.down.closest && d.down.closest(INTERACTIVE)) return;
          suppressClick = true;
          if (!Sheet.tap(d.down, d.x0, d.y0)) Chrome.show();
        }

        function onDown(e) {
          if (e.pointerType === "mouse" && e.button !== 0) return;
          // A second contact is a pinch, never a turn.
          if (!e.isPrimary || drag) {
            if (drag) end(null);
            return;
          }
          settleNow();
          width = track.clientWidth || 1;
          drag = {
            id: e.pointerId,
            // Pointer capture retargets every later event to the track, so the
            // element the finger actually landed on has to be caught here.
            down: e.target,
            x0: e.clientX,
            y0: e.clientY,
            t0: performance.now(),
            paging: mouseDrag || e.pointerType !== "mouse",
            live: false, dead: false, banded: false, rel: 0, eff: 0,
            samples: [{ x: e.clientX, t: performance.now() }],
          };
          // Correct on Chrome, and WebKit has a defect where capture claimed on an
          // ancestor stops routing once the contact leaves the child it started on
          // — which is exactly this shape — so the tail is bound to window.
          try { track.setPointerCapture(e.pointerId); } catch (err) {}
          window.addEventListener("pointermove", onMove, { passive: false });
          window.addEventListener("pointerup", onUp);
          window.addEventListener("pointercancel", onCancel);
        }

        function onMove(e) {
          if (!drag || e.pointerId !== drag.id) return;
          const dx = e.clientX - drag.x0;
          const dy = e.clientY - drag.y0;
          drag.samples.push({ x: e.clientX, t: performance.now() });
          if (drag.samples.length > 8) drag.samples.shift();

          if (drag.dead) return;
          if (!drag.live) {
            if (Math.abs(dx) < TAP_SLOP && Math.abs(dy) < TAP_SLOP) return;
            // Axis lock happens once, at the moment the gesture stops being a tap,
            // and the wrong axis abandons rather than waits.
            if (!drag.paging || Math.abs(dy) > Math.abs(dx)) { drag.dead = true; return; }
            drag.live = true;
            Sheet.dismiss();
            Chrome.hide();
            // iOS fires viewport resizes during a drag; a repagination here would
            // move the split under the finger.
            PageBox.suspend();
            track.style.willChange = "transform";
          }
          e.preventDefault();
          // The slop is subtracted so the page starts from the finger rather than
          // jumping the 8px that proved it was a drag.
          const raw = dx - Math.sign(dx) * TAP_SLOP;
          const rel = Math.sign(raw) * advanceSign;
          drag.rel = rel;
          drag.banded = rel !== 0 && !at(rel);
          drag.eff = drag.banded ? raw * BAND : raw;
          setX(-width + drag.eff);
        }

        function onUp(e) {
          if (!drag || e.pointerId !== drag.id) return;
          end(e);
        }

        function onCancel(e) {
          if (!drag || e.pointerId !== drag.id) return;
          end(null);
        }

        function end(e) {
          const d = drag;
          drag = null;
          window.removeEventListener("pointermove", onMove);
          window.removeEventListener("pointerup", onUp);
          window.removeEventListener("pointercancel", onCancel);
          try { track.releasePointerCapture(d.id); } catch (err) {}

          if (!d.live) {
            track.style.willChange = "";
            // Movement past the slop is not a tap however it ended, and the
            // synthesised click that follows it has to be swallowed either way.
            if (d.dead) suppressClick = true;
            // TAP_SLOP is the whole of the tap/drag discrimination: reaching here
            // means the pointer never crossed it, so the gesture is provably not a
            // drag and there is nothing left for a duration bound to decide. A
            // held 400ms press on a kanji is the commonest way this reader is
            // asked for a reading, and the old click handler always answered it.
            else if (e) tap(d);
            return;
          }
          suppressClick = true;
          const v = velocity(d);
          const past = Math.abs(d.eff) > width * COMMIT;
          const flick = Math.abs(v) > FLICK && Math.sign(v) === Math.sign(d.eff);
          const commit = !!e && !d.banded && d.rel !== 0 && (past || flick);
          animateTo(commit ? snapX(d.rel) : restX(), commit ? d.rel : 0);
        }

        function applyBinding() {
          const b = Prefs.bindingEdge();
          if (b === bound) return false;
          bound = b;
          advanceSign = bound === "right" ? 1 : -1;
          return true;
        }

        // Called when 綴じ or the writing mode changes. The slot each screen lives
        // in is a function of the binding, so a flip makes all three cells stale.
        function retune() {
          if (applyBinding()) { invalidate(); paint(); }
        }

        function goTo(target, animate) {
          Sheet.dismiss();
          settleNow();
          Chrome.show();
          if (!target || Paginator.sameAddress(target, addr)) return;
          const fwd = Paginator.next(addr);
          const back = Paginator.prev(addr);
          if (animate !== false && Paginator.sameAddress(target, fwd)) {
            width = track.clientWidth || 1;
            PageBox.suspend();
            animateTo(snapX(1), 1);
          } else if (animate !== false && Paginator.sameAddress(target, back)) {
            width = track.clientWidth || 1;
            PageBox.suspend();
            animateTo(snapX(-1), -1);
          } else {
            addr = Paginator.clamp(target);
            invalidate();
            paint();
            announce();
          }
        }

        // The snap in flight has to land before the neighbour is looked up. goTo
        // settles first and then compares, so a target resolved against the
        // address the running turn is still leaving is the address goTo arrives
        // at — and the identity guard drops it. That is every second turn of a
        // fast reader, and the whole of a held arrow key.
        function step(d) {
          settleNow();
          goTo(d > 0 ? Paginator.next(addr) : Paginator.prev(addr));
        }

        // Called after the paginator has re-split. Position is restored by
        // authored page rather than by a screen index that no longer means the
        // same thing — which is the whole reason progress is an authored index.
        function relayout() {
          if (drag) end(null);
          settleNow();
          width = track.clientWidth || 1;
          addr = Paginator.clamp(addr);
          invalidate();
          paint();
          announce();
        }

        function start() {
          applyBinding();
          width = track.clientWidth || 1;
          const p = Progress.open(DATA.slug || "", DATA.pages.length);
          // Progress.open clamps the page; Paginator.clamp clamps the sub against
          // the split this geometry actually produces, which storage cannot know.
          addr = Paginator.addressFromProgress(p);
          invalidate();
          rest();
          paint();
          announce();
        }

        track.addEventListener("pointerdown", onDown);
        // Insurance for iOS builds where the scroll directional lock steals a
        // near-horizontal drag despite touch-action. One finger only, so
        // pinch-zoom survives.
        track.addEventListener("touchmove", (e) => {
          if (drag && drag.live && e.touches.length === 1) e.preventDefault();
        }, { passive: false });

        // click is synthesised after the pointer sequence and no engine suppresses
        // it for movement, so without this every swipe would also open the sheet
        // on whatever word was under the finger. stopPropagation is the
        // load-bearing call; preventDefault alone stops nothing of ours.
        document.addEventListener("click", (e) => {
          if (!suppressClick) return;
          suppressClick = false;
          e.stopPropagation();
          e.preventDefault();
        }, true);
        // Cleared here rather than on our own pointerdown, so a swipe that
        // produced no click cannot swallow the next tap on a chrome button.
        document.addEventListener("pointerdown", () => { suppressClick = false; }, true);

        addEventListener("resize", () => {
          if (drag) end(null);
          settleNow();
          width = track.clientWidth || 1;
        });

        const focusedIn = (sel) => {
          const el = document.activeElement;
          return !!(el && el.closest && el.closest(sel));
        };

        addEventListener("keydown", (e) => {
          if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
          suppressClick = false;

          if (e.key === "Escape") {
            e.preventDefault();
            if (!Chrome.closeSettings()) Sheet.dismiss();
            return;
          }
          if (focusedIn(TYPING)) return;
          // Space and Enter belong to whatever is focused. Taking them
          // unconditionally is why the old reader could not toggle a gate from the
          // keyboard.
          if ((e.key === " " || e.key === "Enter") && focusedIn(INTERACTIVE)) return;

          const fwd = () => step(1);
          const back = () => step(-1);
          Chrome.show();

          switch (e.key) {
            case "ArrowRight": e.preventDefault(); (bound === "right" ? back : fwd)(); break;
            case "ArrowLeft": e.preventDefault(); (bound === "right" ? fwd : back)(); break;
            case " ":
            case "PageDown": e.preventDefault(); fwd(); break;
            case "PageUp": e.preventDefault(); back(); break;
            case "Home": e.preventDefault(); goTo(Paginator.first(), false); break;
            // End belongs to the story, not to the spoilers.
            case "End": e.preventDefault(); goTo(Paginator.last(), false); break;
            case "f": case "F": e.preventDefault(); Prefs.toggle("furigana"); break;
            case "t": case "T": e.preventDefault(); Prefs.toggle("trans"); break;
            case "m": case "M": e.preventDefault(); Prefs.toggle("meaning"); break;
          }
        });

        return {
          start, goTo, step, relayout, retune, invalidate, paint,
          address: () => addr,
          binding: () => bound,
          busy: () => !!drag || !!pending,
          // Desktop keeps text selection, which a mouse drag would fight; the keys
          // and 前/次 are the mouse's page turn. Flip it for a synthesised gesture
          // test that dispatches pointerType "mouse".
          setMouseDrag: (on) => { mouseDrag = !!on; },
        };
      })();

      // ----------------------------------------------------------- bootstrap --
      Prefs.boot();      // body classes, data-theme and --fs before anything measures
      PageBox.init();    // #measure, --measure/--extent, the geometry observers
      // Pagination is only as good as the probe's scrollWidth/scrollHeight. An
      // engine that reports the padding box would split nothing at all and show
      // it as text shaved off long pages, so it says so here instead.
      if (!PageBox.selfTest() && window.console) {
        console.warn("reader: the measure probe reports no overflow; pages will not split");
      }
      Chrome.init();     // title, stats, controls, listeners
      Sheet.start();     // tap-away, hover, tab stops
      Track.start();     // restore position, paint, bind input

      // Two paths reach a relayout — a pref change and a geometry change — and a
      // pref change reaches it through both, because PageBox.refresh() notifies
      // synchronously. Coalescing to one frame means the expensive half runs once
      // whichever way it was triggered.
      let relayoutPending = 0;
      function scheduleRelayout() {
        if (relayoutPending) return;
        relayoutPending = requestAnimationFrame(() => {
          relayoutPending = 0;
          Paginator.invalidate();
          Track.relayout();
        });
      }

      // One subscriber, so the cost of a pref change is declared in exactly one
      // place. Prefs applies the DOM state before this runs, so measuring here
      // sees the new writing mode and the new --fs.
      Prefs.subscribe((change) => {
        if (change.effects.layout) {
          PageBox.refresh();
          scheduleRelayout();
        }
        if (change.effects.binding) Track.retune();
        if (change.effects.theme) Chrome.syncThemeColor();
        if (change.effects.gates) { Chrome.syncGates(change.prefs); Sheet.refresh(); }
        Chrome.syncControls();
      });

      // Viewport, rotation, safe-area and font substitution all invalidate
      // pagination too, and none of them is a pref — this is the other half of
      // the relayout path.
      PageBox.onChange(scheduleRelayout);
