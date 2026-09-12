"""Validate a story draft: every content word must be in the known-word set."""

import re
import sys
from collections import Counter
from functools import lru_cache

import furigana
import ichiran
import inflect
import vocab

# Tokens accepted only by the particle-splitting fallback, not by the paradigm.
# Each one is a form inflect.py should have generated, so the list is a to-do.
FALLBACKS = Counter()

# Function words and inflectional tails. AnkiMorphs tracks vocabulary, not
# grammar, so these never appear in the known set but are fair game in prose.
GRAMMAR = set(
    """は が を に で と も の へ や か ね よ な さ ぞ ぜ わ ら し て だ で です ます から まで
    より ので のに けど けれど けれども ば たら なら という といった ため ながら つつ たり ずつ
    こそ しか だけ ほど くらい ぐらい など なんて でも ても とも ものの もの こと そう よう ように
    ような らしい みたい みたいな でしょう ましょう ください ない ぬ ず た って る れ られ せ させ
    い う え お く ぐ す ず つ ぬ ふ む ゆ る を ん っ ー
    、 。 「 」 『 』 ？ ！ ・ … ー 　""".split()
)


def load():
    """Known lemmas, their full generated paradigms, and grammar tails.

    The paradigm comes from inflect.expand rather than from Ichiran's conj chain.
    Ichiran reduces 打たれる to 打つ but leaves 叱られた unreduced, and forms that
    failed validation were written out of the stories — which is why the corpus
    had almost no passive or causative until this changed.
    """
    lemmas, forms = vocab.known_forms()
    return inflect.expand(lemmas, extra=[forms, GRAMMAR])


def _segmentable(form, known):
    """True if `form` splits entirely into known words and grammar particles.

    Ichiran hands back words fused to their particles (静かに, 誰も, というのは)
    and occasionally fuses two content words (長い間). Rather than enumerate
    those shapes, accept any form whose every piece is separately accounted for.
    """

    @lru_cache(maxsize=None)
    def walk(i):
        if i == len(form):
            return True
        return any(
            form[i:j] in known and walk(j) for j in range(len(form), i, -1)
        )

    return walk(0)


def is_known(tok, known):
    for form in (tok["surface"], *tok["bases"]):
        if form in known:
            return True
    for form in (tok["surface"], *tok["bases"]):
        if _segmentable(form, known):
            FALLBACKS[form] += 1
            return True
    return False


def check(text, known=None):
    known = known or load()
    unknown = Counter()
    total = 0
    for tok in ichiran.tokens(text):
        if not re.search(r"[ぁ-ゟ゠-ヿ㐀-䶿一-鿿]", tok["surface"]):
            continue
        total += 1
        if not is_known(tok, known):
            unknown[f"{tok['surface']} ({'/'.join(tok['bases'])}) 【{tok['kana']}】"] += 1
    return total, unknown




def strip_translations(text):
    """Story text only: no `> ` gloss lines, no authored ruby.

    Ruby has to go before segmentation or Ichiran is handed ｜下《した》 and parses
    the reading as though it were part of the sentence.
    """
    lines = [l for l in text.splitlines() if not l.lstrip().startswith(">")]
    return furigana.strip("\n".join(lines))


if __name__ == "__main__":
    raw = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    total, unknown = check(strip_translations(raw))
    print(f"tokens: {total}   unknown: {sum(unknown.values())}   distinct: {len(unknown)}")
    for word, n in unknown.most_common():
        print(f"  {n}x  {word}")
    if FALLBACKS and "-v" in sys.argv:
        print(f"\naccepted only by particle-splitting: {sum(FALLBACKS.values())}")
        for word, n in FALLBACKS.most_common(20):
            print(f"  {n}x  {word}")
