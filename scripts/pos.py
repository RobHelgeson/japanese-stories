"""Conjugation class for each known lemma, read from JMdict.

Ichiran is built on JMdict but only exposes its parse of a given string, and that
parse is unreliable for inflected forms: 打たれる reduces to 打つ, 叱られた does not
reduce at all. Reading JMdict directly gives the class outright, so inflected forms
can be generated (see inflect.py) instead of recovered.

The JMdict source is the jmdict-simplified JSON the kanji-of-the-day skill already
caches. Only the classes of the known lemmas are kept; the 115MB source is never
vendored.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JMDICT = os.path.expanduser("~/.cache/kanji-of-the-day/jmdict-eng.json")
TABLE = os.path.join(HERE, "pos-table.json")

# The JMdict part-of-speech codes that imply a conjugation paradigm. Everything
# else (nouns, adverbs, particles) has no inflection to generate.
VERB_CLASSES = {
    "v1", "v1-s", "vk", "vz", "vs-i", "vs-s",
    "v5u", "v5k", "v5g", "v5s", "v5t", "v5n", "v5b", "v5m", "v5r",
    "v5u-s", "v5k-s", "v5r-i", "v5aru",
}
ADJ_CLASSES = {"adj-i", "adj-ix", "adj-na"}
INFLECTING = VERB_CLASSES | ADJ_CLASSES | {"vs"}


def _load_jmdict(path=JMDICT):
    if not os.path.exists(path):
        sys.exit(
            f"JMdict not found at {path}\n"
            "It ships with the kanji-of-the-day skill; run that once, or point "
            "JMDICT at a jmdict-simplified JSON."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(known_lemmas, path=JMDICT):
    """{lemma: [pos codes]} for every known lemma JMdict says inflects."""
    data = _load_jmdict(path)
    want = set(known_lemmas)
    out = {}
    for entry in data["words"]:
        codes = set()
        for sense in entry["sense"]:
            codes |= {p for p in sense["partOfSpeech"] if p in INFLECTING}
        if not codes:
            continue
        surfaces = [k["text"] for k in entry["kanji"]] + [k["text"] for k in entry["kana"]]
        for s in surfaces:
            if s in want:
                out.setdefault(s, set()).update(codes)
    return {k: sorted(v) for k, v in sorted(out.items())}


def load(refresh=False, known_lemmas=None):
    """Cached lemma -> class table.

    Keyed on the size of the lemma set so a widened known set rebuilds the table
    rather than silently reusing one that is missing the new words.
    """
    if known_lemmas is None:
        import vocab

        known_lemmas, _ = vocab.known_forms()
    if not refresh and os.path.exists(TABLE):
        with open(TABLE, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("lemma_count") == len(known_lemmas):
            return cached["classes"]
    classes = build(known_lemmas)
    with open(TABLE, "w", encoding="utf-8") as f:
        json.dump(
            {"lemma_count": len(known_lemmas), "source": os.path.basename(JMDICT), "classes": classes},
            f,
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
    return classes


def _observed_class(lemma, inflections):
    """Godan or ichidan, inferred from an observed past form.

    A る-verb's past tense settles it: godan gives った, ichidan gives た on the
    bare stem. Used only to contradict JMdict, never to replace it.
    """
    if not lemma.endswith("る"):
        return None
    stem = lemma[:-1]
    for form in inflections:
        if form == stem + "った":
            return "godan"
        if form == stem + "た":
            return "ichidan"
    return None


def verify():
    """Cross-check JMdict classes against inflections AnkiMorphs actually saw."""
    import vocab

    lemmas, _ = vocab.known_forms()
    classes = load(known_lemmas=lemmas)
    by_lemma = vocab.morph_inflections() if hasattr(vocab, "morph_inflections") else {}

    verbs = sum(1 for c in classes.values() if set(c) & VERB_CLASSES)
    adjs = sum(1 for c in classes.values() if set(c) & ADJ_CLASSES)
    print(f"known lemmas        : {len(lemmas)}")
    print(f"with a class        : {len(classes)}  ({verbs} verbs, {adjs} adjectives)")
    print(f"no class (uninflecting or absent from JMdict): {len(lemmas) - len(classes)}")

    if not by_lemma:
        print("\nNo observed inflections available; skipping cross-check.")
        return
    conflicts = 0
    for lemma, forms in by_lemma.items():
        observed = _observed_class(lemma, forms)
        if not observed or lemma not in classes:
            continue
        codes = set(classes[lemma])
        jm = "ichidan" if "v1" in codes else ("godan" if any(c.startswith("v5") for c in codes) else None)
        if jm and jm != observed:
            conflicts += 1
            print(f"  CONFLICT {lemma}: JMdict={jm} observed={observed} ({sorted(forms)[:4]})")
    print(f"\ncross-checked against observed inflections, conflicts: {conflicts}")


if __name__ == "__main__":
    if "--verify" in sys.argv:
        verify()
    else:
        classes = load(refresh="--refresh" in sys.argv)
        print(f"{len(classes)} inflecting lemmas -> {TABLE}")
