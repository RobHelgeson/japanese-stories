"""Read the prose sections of stories-index.md.

Both index.py (contents page) and build.py (per-story afterword) need the same
`- **Title** — text` bullets out of the same file, so the parser lives here
rather than being written twice and drifting.
"""

import html
import re
from pathlib import Path

import furigana

BULLET = re.compile(r"^- \*\*(.+?)\*\*\s*[—-]\s*(.+)$")


def strip_ruby(text):
    return furigana.strip(text)


def ruby_html(text):
    """｜漢字《かな》 rendered as <ruby>, everything else HTML-escaped.

    English prose quotes Japanese in two places — the afterwords here, and the
    `> ` translation lines of the stories — and the reader is for someone who
    wants the reading available in both. Escaping happens per-segment so the
    markup survives while the surrounding prose cannot inject tags; this is the
    only string in the build that the reader hands to innerHTML.

    The grammar is furigana.MARKUP, the same one the Japanese lines are parsed
    with, so an annotation cannot mean one thing in a story line and another in
    the English beside it.
    """
    out, last = [], 0
    for m in furigana.MARKUP.finditer(text):
        surface, reading = furigana.pair(m)
        out.append(html.escape(text[last : m.start()]))
        out.append(f"<ruby>{html.escape(surface)}<rt>{html.escape(reading)}</rt></ruby>")
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
            plain, authored = furigana.parse(marked)
            out[plain] = ("".join(authored[at][1] for at in sorted(authored)), text)
    return out


def summaries(index_md):
    """Spoiler-light blurbs for the contents page, with ruby stripped."""
    return {k: (r, strip_ruby(t)) for k, (r, t) in section(index_md, "Summaries").items()}


def afterwords(index_md):
    """Full-spoiler notes, as HTML with furigana preserved."""
    return {k: ruby_html(t) for k, (_, t) in section(index_md, "Afterwords").items()}
