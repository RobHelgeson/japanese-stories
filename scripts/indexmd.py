"""Read the prose sections of stories-index.md.

Both index.py (contents page) and build.py (per-story afterword) need the same
`- **Title** — text` bullets out of the same file, so the parser lives here
rather than being written twice and drifting.
"""

import html
import re
from pathlib import Path

# ｜kanji《かな》 — the furigana markup used in the story sources (see AUTHORING.md).
RUBY = re.compile(r"｜([^《｜]+)《([^》]+)》")
BULLET = re.compile(r"^- \*\*(.+?)\*\*\s*[—-]\s*(.+)$")


def strip_ruby(text):
    return RUBY.sub(r"\1", text)


def ruby_html(text):
    """｜漢字《かな》 rendered as <ruby>, everything else HTML-escaped.

    Afterwords quote Japanese inside English prose, and the reader is for someone
    who wants the reading available. Escaping happens per-segment so the markup
    survives while the surrounding prose cannot inject tags.
    """
    out, last = [], 0
    for m in RUBY.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        out.append(f"<ruby>{html.escape(m.group(1))}<rt>{html.escape(m.group(2))}</rt></ruby>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def section(index_md, heading):
    """Map plain story title -> (title reading, raw bullet text) for one `## ` section."""
    out = {}
    inside = False
    for line in Path(index_md).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == f"## {heading}"
            continue
        if not inside:
            continue
        m = BULLET.match(line.strip())
        if m:
            marked, text = m.group(1), m.group(2)
            out[strip_ruby(marked)] = ("".join(r for _, r in RUBY.findall(marked)), text)
    return out


def summaries(index_md):
    """Spoiler-light blurbs for the contents page, with ruby stripped."""
    return {k: (r, strip_ruby(t)) for k, (r, t) in section(index_md, "Summaries").items()}


def afterwords(index_md):
    """Full-spoiler notes, as HTML with furigana preserved."""
    return {k: ruby_html(t) for k, (_, t) in section(index_md, "Afterwords").items()}
