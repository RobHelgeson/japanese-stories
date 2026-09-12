"""Known/weak vocabulary, merged from AnkiMorphs and the decks it does not read.

AnkiMorphs only indexes note types whose filter has `read: true` — here that is
just the `Morphs::*` media decks (4,839 lemmas). Japanese Core, Jlab and
Duolingo are all `read: false`, so roughly 900 matured kanji words are
invisible to it. This module unions them back in.

If those filters are ever flipped to `read: true` in AnkiMorphs, this stays
correct — the extra sources just stop contributing anything new.
"""

import html
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

ANKI_SUPPORT = Path.home() / "Library/Application Support/Anki2/User 1"
MORPHS_DB = ANKI_SUPPORT / "ankimorphs.db"
ANKI_CONNECT = "http://localhost:8765"
KNOWN_INTERVAL = 21  # AnkiMorphs' own "known" threshold

HERE = Path(__file__).resolve().parent
APPROVED = HERE / "approved-words.json"
CACHE = HERE / ".deck-words-cache.json"
CACHE_MAX_AGE = 12 * 3600  # a study session's worth; --refresh forces a re-read

# Note types AnkiMorphs is configured not to read, and the field holding the
# vocabulary. `split` marks a field with several space-separated lemmas.
DECK_SOURCES = [
    {"note_type": "Japanese Vocabulary", "field": "Word", "split": False},
    {"note_type": "Duolingo Vocab", "field": "Front", "split": False},
    {"note_type": "JlabNote-JlabConverted-1", "field": "Jlab-Lemma", "split": True},
]

HTML = re.compile(r"<[^>]+>")
RUBY = re.compile(r"\[[ぁ-ゟァ-ヺー]+\]")  # Core/Duolingo write furigana as 寿[す]司[し]
JAPANESE = re.compile(r"[ぁ-ゟ゠-ヿ㐀-䶿一-鿿々]")


def _connect():
    return sqlite3.connect(f"file:{MORPHS_DB}?immutable=1", uri=True)


def anki(action, **params):
    req = urllib.request.Request(
        ANKI_CONNECT,
        data=json.dumps({"action": action, "version": 6, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.load(r)
    if body.get("error"):
        raise RuntimeError(f"AnkiConnect: {body['error']}")
    return body["result"]


def approved_forms():
    """Words signed off by hand that Anki does not yet call known.

    Kept separate from `known_forms` on purpose: the reader marks these so they
    read as deliberate stretch vocabulary rather than disappearing into the set.
    """
    data = json.loads(APPROVED.read_text(encoding="utf-8"))
    return {
        word
        for story, words in data.items()
        if not story.startswith("_")
        for word in words
    }


def morph_forms(interval=KNOWN_INTERVAL):
    """AnkiMorphs lemmas, and lemmas plus inflections, at or above `interval`."""
    con = _connect()
    rows = con.execute(
        "SELECT lemma, inflection FROM Morphs WHERE highest_lemma_learning_interval >= ?",
        (interval,),
    ).fetchall()
    con.close()
    lemmas = {r[0] for r in rows}
    return lemmas, lemmas | {r[1] for r in rows}


def morph_inflections(interval=KNOWN_INTERVAL):
    """{lemma: {inflections seen}} — the per-lemma view morph_forms flattens.

    Used to cross-check the conjugation classes pos.py reads out of JMdict: an
    observed past form settles godan vs. ichidan without asking a parser.
    """
    con = _connect()
    rows = con.execute(
        "SELECT lemma, inflection FROM Morphs WHERE highest_lemma_learning_interval >= ?",
        (interval,),
    ).fetchall()
    con.close()
    out = {}
    for lemma, inflection in rows:
        out.setdefault(lemma, set()).add(inflection)
    return out


def _clean(text):
    # Entities are unescaped before tags are stripped, or a field written as
    # "&nbsp;卓球" keeps the entity and becomes its own bogus vocabulary entry.
    text = RUBY.sub("", HTML.sub("", html.unescape(text)))
    return text.replace(" ", " ").replace("​", "").strip()


def deck_words(interval=KNOWN_INTERVAL, refresh=False):
    """Mature vocabulary from the note types AnkiMorphs does not read.

    Cached, because this is thousands of `notesInfo` rows and a build re-reads
    it once per story.
    """
    if not refresh and CACHE.exists():
        cached = json.loads(CACHE.read_text(encoding="utf-8"))
        if cached.get("interval") == interval and time.time() - cached["at"] < CACHE_MAX_AGE:
            return set(cached["words"])

    words = set()
    for src in DECK_SOURCES:
        nids = anki("findNotes", query=f'note:"{src["note_type"]}" prop:ivl>={interval}')
        for i in range(0, len(nids), 800):
            for note in anki("notesInfo", notes=nids[i : i + 800]):
                raw = _clean(note["fields"].get(src["field"], {}).get("value", ""))
                if not raw:
                    continue
                parts = raw.split() if src["split"] else [raw.replace(" ", "")]
                words.update(p for p in parts if JAPANESE.search(p) and len(p) <= 12)

    CACHE.write_text(
        json.dumps({"at": time.time(), "interval": interval, "words": sorted(words)},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return words


def known_forms(interval=KNOWN_INTERVAL, refresh=False):
    """(lemmas, all forms) across every source, including approved stretch words."""
    lemmas, forms = morph_forms(interval)
    extra = deck_words(interval, refresh) | approved_forms()
    return lemmas | extra, forms | extra


def weak_forms():
    """Known words that also sit on a leech card — worth extra exposure.

    Two sources, for the same reason `known_forms` needs two. `Card_Morph_Map`
    only covers the decks AnkiMorphs indexes, so reading it alone found 35 words
    out of 876 unsuspended leech cards: every leech in Japanese Core, Jlab and
    Duolingo was invisible. The note-field pass below recovers those.
    """
    leech_cards = anki("findCards", query="tag:leech -is:suspended")
    if not leech_cards:
        return set()
    lemmas, _ = known_forms()

    con = _connect()
    out = set()
    for i in range(0, len(leech_cards), 500):
        chunk = leech_cards[i : i + 500]
        q = ",".join("?" * len(chunk))
        out |= {
            r[0]
            for r in con.execute(
                f"SELECT DISTINCT morph_lemma FROM Card_Morph_Map WHERE card_id IN ({q})",
                chunk,
            )
        }
    con.close()

    out |= _leech_deck_words(leech_cards)
    return out & lemmas


def _leech_deck_words(leech_cards):
    """Vocabulary on leech cards belonging to the note types AnkiMorphs skips."""
    fields = {src["note_type"]: src for src in DECK_SOURCES}
    words = set()
    for i in range(0, len(leech_cards), 500):
        infos = anki("cardsInfo", cards=leech_cards[i : i + 500])
        for info in infos:
            src = fields.get(info.get("modelName", ""))
            if not src:
                continue
            raw = _clean(info.get("fields", {}).get(src["field"], {}).get("value", ""))
            if not raw:
                continue
            parts = raw.split() if src["split"] else [raw.replace(" ", "")]
            words.update(p for p in parts if JAPANESE.search(p) and len(p) <= 12)
    return words


if __name__ == "__main__":
    import sys

    refresh = "--refresh" in sys.argv
    morph_lemmas, morph_all = morph_forms()
    extra = deck_words(refresh=refresh)
    lemmas, forms = known_forms(refresh=refresh)
    print(f"AnkiMorphs (Morphs decks only) : {len(morph_lemmas)} lemmas, {len(morph_all)} forms")
    print(f"Core + Duolingo + Jlab         : {len(extra)} words")
    print(f"  of which new to AnkiMorphs   : {len(extra - morph_all)}")
    print(f"Hand-approved (not yet known)   : {len(approved_forms())} words")
    print(f"MERGED known                   : {len(lemmas)} lemmas, {len(forms)} forms")
    print(f"weak (leech ∩ known)           : {len(weak_forms())}")
