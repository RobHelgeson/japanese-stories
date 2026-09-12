"""Every inflected form of a known lemma, generated from its conjugation class.

The validator used to ask Ichiran what dictionary form an inflected token reduced
to, and Ichiran answers inconsistently: 打たれる reduces to 打つ, 叱られた reduces to
nothing. Forms that failed were written out of the stories, which is why the
corpus has almost no passive or causative. Generating the paradigm instead makes
the question moot — the inflected form is in the known set literally.

Deliberately not cached. It is pure, deterministic, and sub-second over the whole
known set; a cache would only add a staleness failure mode.
"""

import sys

# a-stem (未然), i-stem (連用), e-stem (仮定/命令), o-stem (意向), te-form, ta-form
GODAN = {
    "う": ("わ", "い", "え", "お", "って", "った"),
    "く": ("か", "き", "け", "こ", "いて", "いた"),
    "ぐ": ("が", "ぎ", "げ", "ご", "いで", "いだ"),
    "す": ("さ", "し", "せ", "そ", "して", "した"),
    "つ": ("た", "ち", "て", "と", "って", "った"),
    "ぬ": ("な", "に", "ね", "の", "んで", "んだ"),
    "ぶ": ("ば", "び", "べ", "ぼ", "んで", "んだ"),
    "む": ("ま", "み", "め", "も", "んで", "んだ"),
    "る": ("ら", "り", "れ", "ろ", "って", "った"),
}

TE_SUFFIXES = [
    "いる", "いた", "いて", "いない", "いなかった", "います", "いました",
    "る", "た", "て", "ない",          # colloquial 〜てる
    "おく", "おいた", "おこう", "く", "いた",  # 〜ておく / 〜とく
    "しまう", "しまった", "みる", "みた", "みたい",
    "くる", "きた", "いく", "いった", "ある", "あった",
    "から", "は", "も", "もいい",
]


def _verb_forms(lemma, a, i, e, o, te, ta, derived=False):
    """The paradigm shared by every verb class once its stems are known."""
    f = {lemma, i, te, ta, a + "ない", a + "なかった", a + "なく", a + "なくて",
         a + "ず", a + "ずに", a + "ぬ",
         a + "なければ", a + "なければならない", a + "なくては", a + "なくてはいけない",
         a + "なきゃ", a + "ないで", a + "ないでください", a + "ないように",
         i + "ます", i + "ません", i + "ました", i + "ませんでした", i + "まして",
         i + "ながら", i + "そう", i + "に", i + "方",
         ta + "ら", ta + "り", e + "ば"}

    for suffix in TE_SUFFIXES:
        f.add(te + suffix)

    # 〜たい inflects as an i-adjective.
    f |= _adj_i_forms(i + "たい")

    if derived:
        return f

    # Passive, causative, causative-passive and potential are themselves ichidan
    # verbs, so run the ichidan paradigm over each rather than listing forms.
    ichidan = lemma.endswith("る") and a == i == e
    if ichidan:
        stem = lemma[:-1]
        f |= {stem + "ろ", stem + "よ", stem + "よう"}
        derived_verbs = [stem + "られる", stem + "させる", stem + "させられる", stem + "れる"]
    else:
        f |= {e, o + "う"}
        derived_verbs = [a + "れる", a + "せる", a + "せられる", a + "される", e + "る"]

    for verb in derived_verbs:
        s = verb[:-1]
        f |= _verb_forms(verb, s, s, s, s, s + "て", s + "た", derived=True)
        f |= {s + "ろ", s + "よう"}
    return f


def _adj_i_forms(lemma):
    if not lemma.endswith("い"):
        return {lemma}
    s = lemma[:-1]
    return {lemma, s + "く", s + "くない", s + "くなかった", s + "かった", s + "くて",
            s + "ければ", s + "さ", s + "すぎる", s + "すぎた", s + "そう", s + "かろう",
            lemma + "です", s + "くないです", s + "かったです", s + "くありません",
            s + "かったら", s + "くなる", s + "くなった", s + "くして"}


def _adj_na_forms(lemma):
    return {lemma, lemma + "な", lemma + "に", lemma + "で", lemma + "だ", lemma + "だった",
            lemma + "です", lemma + "でした", lemma + "ではない", lemma + "じゃない",
            lemma + "ではなかった", lemma + "じゃなかった", lemma + "なら", lemma + "さ",
            lemma + "になる", lemma + "になった", lemma + "そう"}


def _derived(verb):
    """Full ichidan paradigm for a verb built by suffixing (passive, causative...)."""
    s = verb[:-1]
    return _verb_forms(verb, s, s, s, s, s + "て", s + "た", derived=True) | {s + "ろ", s + "よう"}


def _suru_paradigm():
    """する in full, including the derived verbs its stems cannot produce.

    する's a-stem is し but its e-stem is すれ, so the generic derived-verb rule in
    _verb_forms would build しれる / しせる. They are supplied explicitly instead.
    """
    f = _verb_forms("する", "し", "し", "すれ", "し", "して", "した") | {"しろ", "せよ", "しよう"}
    for verb in ("される", "させる", "させられる", "できる"):
        f |= _derived(verb)
    return f


SURU = _suru_paradigm()


def _suru_forms(noun):
    """A する-noun inflects by carrying the whole する paradigm."""
    return {noun} | {noun + f for f in SURU}


def _irregular():
    """する, 来る and くる — the only verbs whose stems cannot be derived.

    Built through the shared paradigm with explicit stems rather than hand-listed,
    so they pick up the same te-form and derived-verb coverage as everything else.
    A hand-list is what made 行かなければ go missing: 行く is a regular godan verb
    with an irregular te-form, and the v5k-s branch already handles it.
    """
    out = {"する": SURU}
    out["来る"] = (_verb_forms("来る", "来", "来", "来れ", "来", "来て", "来た")
                  | {"来い", "来よう"} | _derived("来られる") | _derived("来させる"))
    out["くる"] = (_verb_forms("くる", "こ", "き", "くれ", "こ", "きて", "きた")
                  | {"こい", "こよう"} | _derived("こられる") | _derived("こさせる"))
    return out


IRREGULAR = _irregular()

# ある is regular godan-る apart from its negative, which suppletes to ない.
ARU_NEGATIVES = {"ない", "なかった", "なく", "なくて", "ありません", "ありませんでした"}


def forms(lemma, codes):
    """Every inflected form of `lemma`, given its JMdict class codes."""
    codes = set(codes)
    if lemma in IRREGULAR:
        return IRREGULAR[lemma] | {lemma}

    if "adj-i" in codes or "adj-ix" in codes:
        return _adj_i_forms(lemma)
    if "adj-na" in codes:
        return _adj_na_forms(lemma)
    if codes & {"vs", "vs-i", "vs-s"} and not lemma.endswith("る"):
        return _suru_forms(lemma)

    if "v1" in codes or "v1-s" in codes:
        if not lemma.endswith("る"):
            return {lemma}
        s = lemma[:-1]
        return _verb_forms(lemma, s, s, s, s, s + "て", s + "た")

    if any(c.startswith("v5") for c in codes):
        tail = lemma[-1]
        if tail not in GODAN:
            return {lemma}
        a, i, e, o, te, ta = GODAN[tail]
        stem = lemma[:-1]
        # 行く and its compounds take って rather than the regular いて.
        if tail == "く" and ("v5k-s" in codes or lemma.endswith("行く")):
            te, ta = "って", "った"
        f = _verb_forms(lemma, stem + a, stem + i, stem + e, stem + o,
                        stem + te, stem + ta)
        if "v5r-i" in codes:
            f |= ARU_NEGATIVES if lemma == "ある" else {stem + n for n in ARU_NEGATIVES}
        return f

    return {lemma}


class Forms:
    """Membership test over every inflected form of the known set.

    する-nouns are held as a prefix rule rather than materialised. Each of the 843
    of them carries the identical 831-form する paradigm, so spelling the product
    out costs 700k strings to answer a question that is one split away.
    """

    def __init__(self, direct, suru_nouns, extra=()):
        self.direct = set(direct)
        for s in extra:
            self.direct |= set(s)
        self.suru_nouns = set(suru_nouns)
        self.suru_suffixes = SURU

    def __contains__(self, s):
        if s in self.direct:
            return True
        for k in range(1, len(s)):
            if s[:k] in self.suru_nouns and s[k:] in self.suru_suffixes:
                return True
        return False

    def __len__(self):
        return len(self.direct) + len(self.suru_nouns) * len(self.suru_suffixes)


def expand(known_lemmas=None, classes=None, extra=()):
    """Every inflected form of the known set, as a membership-testable object."""
    import pos

    if known_lemmas is None:
        import vocab

        known_lemmas, _ = vocab.known_forms()
    if classes is None:
        classes = pos.load(known_lemmas=known_lemmas)

    direct, suru_nouns = set(), set()
    for lemma in known_lemmas:
        codes = set(classes.get(lemma, []))
        if codes & {"vs", "vs-i", "vs-s"} and not lemma.endswith("る") and lemma != "する":
            suru_nouns.add(lemma)
            direct.add(lemma)
        else:
            direct |= forms(lemma, codes)
    return Forms(direct, suru_nouns, extra)


SELFTEST = [
    # The forms that failed under Ichiran lemmatisation and flattened the corpus.
    ("叱られた", "叱る"), ("叱られて", "叱る"), ("食べさせられた", "食べる"),
    ("打たれる", "打つ"), ("作らされた", "作る"), ("待たせて", "待つ"),
    ("立たされて", "立つ"), ("売られている", "売る"), ("読ませる", "読む"),
    # Conditionals, including the negative conditional the first draft missed.
    ("行かなければ", "行く"), ("研究しなければ", "研究"), ("泳げる", "泳ぐ"),
    ("高くなかった", "高い"), ("静かだった", "静か"),
    # Irregulars and the te-form chain.
    ("行ってしまった", "行く"), ("行かせた", "行く"), ("来られた", "来る"),
    ("来なかった", "来る"), ("勉強させられた", "勉強"), ("話しておいた", "話す"),
    ("死んでしまった", "死ぬ"), ("見せながら", "見せる"), ("聞こえなくて", "聞こえる"),
]


def selftest():
    import pos
    import vocab

    lemmas, _ = vocab.known_forms()
    classes = pos.load(known_lemmas=lemmas)
    allforms = expand(lemmas, classes)
    ok = True
    for form, lemma in SELFTEST:
        if lemma is None:
            continue
        here = form in allforms
        known_lemma = lemma in lemmas
        status = "ok " if here else ("MISS" if known_lemma else "skip (lemma unknown)")
        if not here and known_lemma:
            ok = False
            cls = classes.get(lemma, [])
            status += f"  [{lemma} class={cls or 'NONE'}]"
        print(f"  {status:<40} {form}  <- {lemma}")
    print(f"\ngenerated forms: {len(allforms)}")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    print(len(expand()))
