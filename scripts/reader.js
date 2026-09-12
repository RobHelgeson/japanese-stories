      const DATA = "__STORY_DATA__";
      const $ = (id) => document.getElementById(id);
      let page = 0;
      let showMeaning = false;

      $("title").textContent = DATA.title;
      const approved = DATA.stats.approved || [];
      $("note").textContent =
        `${DATA.stats.words} 漢字語 · 既知語彙 ${DATA.stats.knownVocab}` +
        (DATA.stats.weak.length ? ` · 苦手 ${DATA.stats.weak.length}` : "") +
        (approved.length ? ` · 新出 ${approved.join("、")}` : "") +
        (DATA.stats.translated ? ` · 訳 ${DATA.stats.translated}/${DATA.stats.sentences}` : "");

      function render() {
        const el = $("page");
        el.textContent = "";
        for (const sentence of DATA.pages[page]) {
          const p = document.createElement("p");
          if (sentence.en) p.className = "has-en";
          for (const tok of sentence.toks) {
            if (!tok.r) {
              p.append(document.createTextNode(tok.t));
              continue;
            }
            const span = document.createElement("span");
            span.className =
              "w" + (tok.w ? " weak" : "") + (tok.n ? " new" : "");
            span.dataset.kana = tok.k || "";
            span.dataset.gloss = tok.g || "";
            for (const [text, ruby] of tok.r) {
              if (ruby) {
                const r = document.createElement("ruby");
                r.append(document.createTextNode(text));
                const rt = document.createElement("rt");
                rt.textContent = ruby;
                r.append(rt);
                span.append(r);
              } else {
                span.append(document.createTextNode(text));
              }
            }
            p.append(span);
          }
          if (sentence.en) {
            const en = document.createElement("span");
            en.className = "en";
            en.textContent = sentence.en;
            p.append(en);
          }
          el.append(p);
        }
        const last = page === DATA.pages.length - 1;
        const after = $("after");
        after.hidden = !(last && DATA.afterword);
        if (!after.hidden && !after.dataset.filled) {
          after.dataset.filled = "1";
          const sum = document.createElement("summary");
          sum.textContent = "あとがき — what this was doing (spoilers)";
          const body = document.createElement("p");
          body.innerHTML = DATA.afterword;
          after.append(sum, body);
        }
        $("count").textContent = `${page + 1} / ${DATA.pages.length}`;
        $("prev").disabled = page === 0;
        $("next").disabled = page === DATA.pages.length - 1;
        $("bar").firstElementChild.style.width =
          `${((page + 1) / DATA.pages.length) * 100}%`;
        hideGloss();
      }

      function go(n) {
        const next = Math.min(Math.max(n, 0), DATA.pages.length - 1);
        if (next === page) return;
        page = next;
        render();
        // <main> is the scroll container now, not the window.
        document.querySelector("main").scrollTop = 0;
      }

      function hideGloss() { $("gloss").classList.remove("on"); }

      $("prev").onclick = () => go(page - 1);
      $("next").onclick = () => go(page + 1);
      $("trans").onclick = (e) => {
        const on = document.body.classList.toggle("all-en");
        e.currentTarget.setAttribute("aria-pressed", String(on));
      };
      $("furi").onclick = (e) => {
        const on = document.body.classList.toggle("all");
        e.currentTarget.setAttribute("aria-pressed", String(on));
      };
      $("mean").onclick = (e) => {
        showMeaning = !showMeaning;
        e.currentTarget.setAttribute("aria-pressed", String(showMeaning));
        if (!showMeaning) hideGloss();
      };

      // Every navigation key here is also a native scroll key, and <main> is a
      // scroll container, so each one has to preventDefault or it both flips the
      // page and scrolls. Space and PageDown read to the bottom of a long page
      // before advancing; on a page that fits, which is most of them, there is
      // nothing to scroll and they flip immediately.
      document.addEventListener("keydown", (e) => {
        const m = document.querySelector("main");
        const room = m.scrollHeight - m.clientHeight - m.scrollTop;
        const nav = (fn) => { e.preventDefault(); fn(); };

        if (e.key === "ArrowLeft") nav(() => go(page - 1));
        else if (e.key === "ArrowRight") nav(() => go(page + 1));
        else if (e.key === " " || e.key === "PageDown") {
          nav(() => (room > 4 ? (m.scrollTop += m.clientHeight * 0.85) : go(page + 1)));
        } else if (e.key === "PageUp") {
          nav(() => (m.scrollTop > 4 ? (m.scrollTop -= m.clientHeight * 0.85) : go(page - 1)));
        } else if (e.key === "Home") nav(() => go(0));
        else if (e.key === "End") nav(() => go(DATA.pages.length - 1));
        else if (e.key === "f") $("furi").click();
        else if (e.key === "t") $("trans").click();
      });

      // Clicking a kanji word pins its reading; clicking the rest of the line
      // reveals that one sentence's translation.
      $("page").addEventListener("click", (e) => {
        const w = e.target.closest(".w");
        if (w) {
          w.classList.toggle("pin");
          return;
        }
        const p = e.target.closest("p.has-en");
        if (p) p.classList.toggle("show-en");
      });

      $("page").addEventListener("mouseover", (e) => {
        const w = e.target.closest(".w");
        if (!w || !showMeaning) return;
        const g = $("gloss");
        g.textContent = `${w.textContent}【${w.dataset.kana}】${
          w.dataset.gloss ? " — " + w.dataset.gloss : ""
        }`;
        g.classList.add("on");
      });
      $("page").addEventListener("mouseout", (e) => {
        if (e.target.closest(".w")) hideGloss();
      });

      render();
