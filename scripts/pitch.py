"""Pitch accent for every surface the stories use, computed from UniDic.

Two things are wanted on the page and they are not the same number. The accent of
the dictionary form (食べる ②) is what Anki drills and what a learner has stored.
The accent of the surface actually printed (食べた) is what the sentence sounds
like. A reader that shows only the first is teaching a word the page does not
contain; one that shows only the second never connects to the card.

So both are computed and both are shipped, and the sheet decides which to show.

UniDic ships the combination rules as data rather than leaving them to be guessed:
every auxiliary carries an `aConType` naming the rule and its offset, so 食べ +
た(動詞%F2@1) is arithmetic, not judgement. The rules themselves are tables 9-12 of
the UniDic 1.3.9 manual (clrd.ninjal.ac.jp/unidic/UNIDIC_manual.pdf §6.6-6.7),
transcribed below. Anything this module cannot evaluate with certainty emits no
surface accent at all, and the reader falls back to the labelled 辞書形 — a wrong
contour is worse than an absent one, because it is indistinguishable from a right
one.

fugashi + unidic-lite is a 262MB install with no business in a normal rebuild, so
this follows pos.py: read the heavy source once, commit the distilled table, never
vendor the source. build.py reads pitch-table.json and imports nothing from here.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "pitch-table.json")

# The venv that carries fugashi. Only --build and --selftest need it; every other
# consumer of this module reads the committed table and needs no interpreter but
# the one it is already running under.
PITCH_PYTHON = os.environ.get("PITCH_PYTHON")

SMALL_KANA = set("ャュョァィゥェォ")

_KATA = {chr(c): chr(c + 0x60) for c in range(0x3041, 0x3097)}

# Ichiran writes word-internal breaks into its readings — 時には arrives as
# とき\u200bには. They are invisible, they are not morae, and a contour drawn over
# them gains a blank node and misclassifies against the inflated count.
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def katakana(s):
    """Ichiran reads in hiragana, UniDic answers in katakana."""
    return "".join(_KATA.get(c, c) for c in (s or "").translate(ZERO_WIDTH))


def key(surface, kana):
    """Table key. A surface alone is not one word.

    空 is ソラ and から, 他 is ホカ and タ, 年月 is としつき and ねんげつ — seven
    surfaces in this corpus carry more than one reading. Keyed by surface alone
    the last one written wins and build.py then hands it to every occurrence,
    which is exactly the mistake analyse()'s reading guard exists to prevent:
    the guard checks that UniDic and Ichiran agree, and then a lookup keyed on
    less than it verified throws the agreement away.
    """
    return surface + "\t" + katakana(kana)

# aType 0 is 平板; anything else is a downstep after that mora. The four shapes a
# noun can take, plus the collapsed verb/adjective pair — see classify().
PATTERNS = ("heiban", "atamadaka", "nakadaka", "odaka", "kifuku")


def morae(kana):
    """Split katakana into morae. Small kana bind to the preceding character."""
    out = []
    for ch in kana:
        if ch in SMALL_KANA and out:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def classify(atype, count, pos=""):
    """The Migaku pattern name for a downstep position.

    For 動詞 and 形容詞 the four-way split does not survive conjugation — the
    downstep moves across the paradigm — so the dictionary distinguishes only
    平板 from 起伏, and this collapses to match. Callers that want the shape of a
    specific surface read its computed accent instead of its pattern name.
    """
    if atype is None or count <= 0:
        return "unknown"
    if pos in ("動詞", "形容詞", "形状詞"):
        return "heiban" if atype == 0 else "kifuku"
    if atype == 0:
        return "heiban"
    if atype == 1:
        return "atamadaka"
    if atype >= count:
        return "odaka"
    return "nakadaka"


# --------------------------------------------------------------------------
# The rule engine — UniDic manual tables 9, 10, 11 and 12.
#
# Every rule answers one question: given a front element of N1 morae carrying
# accent M1, and a rear element attaching to it, where does the combined accent
# fall? M2 is the rear element's own accent type, M and L its rule offsets.
# --------------------------------------------------------------------------

RULE = re.compile(r"^([A-Z])(\d+)(?:@(-?\d+)(?:,(-?\d+))?)?$")


def _combine(code, n1, m1, m2, n2):
    """One rule application. Returns the combined accent, or None if unhandled.

    None is the whole safety mechanism: an unrecognised code, a rule that needs an
    offset it was not given, or a rear accent that is not known all return it, and
    one None anywhere in a chain suppresses the surface accent for that token.
    """
    m = RULE.match(code)
    if not m:
        return None
    kind, num = m.group(1), int(m.group(2))
    a = int(m.group(3)) if m.group(3) is not None else None
    b = int(m.group(4)) if m.group(4) is not None else None
    flat = m1 == 0

    # Every rule below that reads an offset is written assuming it has one. A
    # malformed code reaching arithmetic would raise rather than decline, which
    # is the one failure mode this module is built not to have.
    need = {("F", 2): 1, ("F", 3): 1, ("F", 4): 1, ("F", 6): 2}.get((kind, num), 0)
    if need >= 1 and a is None:
        return None
    if need >= 2 and b is None:
        return None

    if kind == "F":  # 表12 助詞・助動詞
        if num == 1:
            return m1
        if num == 2:
            return (n1 + a) if flat else m1
        if num == 3:
            return m1 if flat else (n1 + a)
        if num == 4:
            return n1 + a
        if num == 5:
            return 0
        if num == 6:
            return n1 + (a if flat else b)
        return None

    if kind == "C":  # 表10 普通名詞・接尾辞
        if num == 1:
            return None if m2 is None else n1 + m2
        if num == 2:
            return n1 + 1
        if num == 3:
            return n1
        if num == 4:
            return 0
        if num == 5:
            return m1
        return None

    if kind == "P":  # 表11 接頭辞 — the front element is the prefix
        rear_flat = m2 == 0 or (n2 is not None and m2 == n2)
        if num == 1:
            return 0 if rear_flat else (None if m2 is None else n1 + m2)
        if num == 2:
            return (n1 + 1) if rear_flat else (None if m2 is None else n1 + m2)
        if num == 4:
            return (n1 + 1) if rear_flat else m1
        if num == 6:
            return 0
        if num == 13:
            return m1
        if num == 14:
            return m1 if rear_flat else (None if m2 is None else n1 + m2)
        return None

    return None


def _modify(code, base, count):
    """表9 アクセント修飾型 — a conjugated form shifting its own base accent.

    N0 is the mora count of this form, M0 the base form's accent, M the offset.
    """
    m = RULE.match(code)
    if not m or m.group(1) != "M" or m.group(3) is None:
        return None
    num, off = int(m.group(2)), int(m.group(3))
    if num == 1:
        return count - off
    if num == 2:
        return (count - off) if base == 0 else base
    if num == 4:
        return base if base in (0, 1) else base - off
    return None


# The host part of speech that a dependent's aConType keys on. UniDic writes the
# rule as 動詞%F2@1,形容詞%F4@-2 — one rule per possible host class — and falls
# back to a bare code when the rule does not vary.
HOST_CLASS = {"動詞": "動詞", "形容詞": "形容詞", "形状詞": "形容詞", "名詞": "名詞", "代名詞": "名詞"}

# An auxiliary can change what the NEXT auxiliary is attaching to. 食べたかった is
# 食べ + たかっ + た, and that final た attaches to たい, which inflects as an
# i-adjective — so it wants the 形容詞 branch of its aConType, not the 動詞 branch
# the phrase head would select. UniDic says so in cType; anything not listed here
# leaves the class alone, which is the old behaviour and the safe direction.
CTYPE_CLASS = {"助動詞-タイ": "形容詞", "助動詞-ナイ": "形容詞", "助動詞-ラシイ": "形容詞"}


def _reclass(tok, current):
    ct = tok.get("ctype") or ""
    if ct in CTYPE_CLASS:
        return CTYPE_CLASS[ct]
    if ct.startswith("形容詞"):
        return "形容詞"
    return current


# One documented correction to UniDic's own data.
#
# unidic-lite tags the past auxiliary た as 動詞%F2@1. F2's 平板 branch is N1+M, so
# a heiban verb comes out 尾高: 行った → イッタ↓, 買った → カッタ↓. Both are flat in
# Tokyo Japanese. Three things agree against the data and nothing agrees with it:
# the UniDic manual's own 表12 lists た（助動詞）under F1; unidic-lite tags て — which
# must behave identically — as 動詞%F1; and the standard pedagogical rule is that
# 平板 verbs stay 平板 through て形, ない形 and タ形 (TUFS 発音モジュール 2.8.1,
# 行く・行って・行かない・行きます).
#
# F1 and F2@1 are the same rule for an accented host (both yield M1), so this
# changes only the heiban cases. Pinned by suite_pitch_gold in tools/harness.py.
CONTYPE_FIX = {("た", "動詞"): "F1"}


def _rule_for(contype, host_pos, lemma=None):
    """Pick the branch of an aConType that applies to this host, if any."""
    fix = CONTYPE_FIX.get((lemma, host_pos))
    if fix:
        return fix
    if not contype or contype == "*":
        return None
    if "%" not in contype:
        return contype.strip()
    want = HOST_CLASS.get(host_pos, host_pos)
    fallback = None
    # Split on the commas that separate 品詞%RULE branches, not on the one inside
    # F6's own @M,L offset pair. A branch always starts with a 品詞 name, so a
    # comma followed by a bare number belongs to the rule before it.
    for part in re.split(r",(?!\s*-?\d)", contype):
        part = part.strip()
        if "%" not in part:
            fallback = fallback or part
            continue
        cls, code = part.split("%", 1)
        if cls.strip() == want:
            return code.strip()
    return fallback


def _atype(raw):
    """UniDic writes alternatives comma-separated, most likely first."""
    if not raw or raw == "*":
        return None
    head = raw.split(",")[0].strip()
    return int(head) if head.lstrip("-").isdigit() else None


def phrase_accent(tokens):
    """Fold a run of UniDic tokens into one accent phrase.

    tokens: [{kana, pos, atype, contype, modtype}], head first.
    Returns (accent, mora_count); accent is None whenever any step was unhandled,
    and the count is always the full phrase so callers can still size a diagram.
    """
    total = sum(len(morae(t["kana"])) for t in tokens)
    if not tokens:
        return None, 0

    head = tokens[0]
    count = len(morae(head["kana"]))
    accent = head["atype"]
    if accent is None:
        return None, total

    if head.get("modtype") and head["modtype"] != "*":
        accent = _modify(head["modtype"], accent, count)
        if accent is None:
            return None, total

    # A 接頭辞 head is the one case where the FRONT element owns the rule: 表11 is
    # keyed on the prefix, not on what follows it. Everywhere else the head has
    # nothing before it and its own aConType is irrelevant.
    if head["pos"] == "接頭辞":
        code = (head.get("contype") or "").strip()
        if len(tokens) < 2 or not code.startswith("P"):
            return None, total
        rear = tokens[1]
        nxt = _combine(code, count, accent, rear["atype"], len(morae(rear["kana"])))
        if nxt is None:
            return None, total
        accent, count = nxt, count + len(morae(rear["kana"]))
        tokens = [head] + tokens[2:]

    host_pos = HOST_CLASS.get(head["pos"], head["pos"])
    for tok in tokens[1:]:
        code = _rule_for(tok.get("contype"), host_pos, tok.get("lemma"))
        if not code:
            return None, total
        nxt = _combine(code, count, accent, tok["atype"], len(morae(tok["kana"])))
        if nxt is None:
            return None, total
        accent, count = nxt, count + len(morae(tok["kana"]))
        # 表9 was collected for every token and applied only to the head, so a
        # modification carried by an auxiliary was read and thrown away:
        # 上げましょう shipped a downstep after マ where the form is アゲマショ↓ー.
        #
        # N0 is "この活用形のモーラ数", and the conjugated form here is the phrase
        # so far — ましょう is 意志推量形 of ます, and what is in 意志推量形 is
        # 上げましょう entire. So it applies to the running accent and the running
        # count, which is exactly how the head's own modification is applied a
        # few lines above; the head was simply the case where the phrase was one
        # token long.
        if tok.get("modtype") and tok["modtype"] != "*":
            accent = _modify(tok["modtype"], accent, count)
            if accent is None:
                return None, total
        host_pos = _reclass(tok, host_pos)

    if accent < 0 or accent > count:
        return None, total  # the rules produced something unpronounceable
    return accent, count


# --------------------------------------------------------------------------
# UniDic access — the only part that needs fugashi.
# --------------------------------------------------------------------------

_tagger = None


def _reexec():
    """Hand the whole invocation to the venv named by PITCH_PYTHON, once.

    Re-exec rather than ask the caller to type the venv's path: the documented
    command is the one that should work, and a second interpreter in the middle
    of a build is a thing to get out of the way rather than to explain. The guard
    variable stops a venv without fugashi from re-execing itself forever.
    """
    if not PITCH_PYTHON or os.environ.get("PITCH_REEXEC"):
        return
    env = dict(os.environ, PITCH_REEXEC="1")
    os.execve(PITCH_PYTHON, [PITCH_PYTHON, os.path.abspath(__file__)] + sys.argv[1:], env)


def _tag(text):
    global _tagger
    if _tagger is None:
        try:
            import fugashi
        except ImportError:
            _reexec()
            sys.exit(
                "fugashi is not importable.\n"
                "pitch.py --build and --selftest need fugashi + unidic-lite; every "
                "other consumer reads pitch-table.json and needs neither.\n"
                "Point PITCH_PYTHON at a venv that has them:\n"
                "  PITCH_PYTHON=/path/to/venv/bin/python3 python3 scripts/pitch.py --build"
            )
        _tagger = fugashi.Tagger()
    out = []
    for w in _tagger(text):
        f = w.feature
        out.append(
            {
                "surface": w.surface,
                "kana": (f.kana or f.pron or "").translate(ZERO_WIDTH),
                "pos": f.pos1,
                "lemma": f.lemma,
                "lemma_kana": f.kanaBase or f.lForm or "",
                "cform": f.cForm,
                "ctype": f.cType,
                "atype": _atype(f.aType),
                "contype": f.aConType,
                "modtype": f.aModeType,
            }
        )
    return out


def analyse(surface, expect_kana=None):
    """Accent for one printed surface, plus the accent of its dictionary form.

    The surface accent is suppressed unless UniDic's own reading of the string
    matches `expect_kana`. The reader draws the contour against the kana it is
    displaying, which comes from Ichiran; if the two disagree about the reading
    they disagree about the morae, and a contour drawn on the wrong morae points
    at the wrong syllable rather than merely looking odd.
    """
    toks = [t for t in _tag(surface) if t["kana"]]
    if not toks:
        return None

    out = {}
    head = toks[0]
    joined = "".join(t["kana"] for t in toks)
    agrees = expect_kana is None or joined == expect_kana
    if not agrees:
        # UniDic is reading a different word than the page is printing, so
        # nothing it says about this surface can be trusted — including which
        # lemma it belongs to. 空いて is あいて to fugashi and すいて on the page.
        return None

    accent, count = phrase_accent(toks)
    if accent is not None:
        out["a"] = accent
        out["m"] = count
        out["p"] = classify(accent, count)
        out["k"] = joined

    # The 辞書形 fallback may only ever name the whole printed word. It exists to
    # say "this is 食べた's dictionary form", and the head of an inflecting phrase
    # is the only token that can honestly claim that.
    #
    # The first cut took the last 用言 anywhere in the surface, or a nominal head.
    # Both name fragments: 一本 came out as 辞書形 一, 七日 as 七, 口にした as
    # 為る with a スル diagram, 会社を辞めた as 止める. 90 tokens shipped that way.
    # A noun compound has no dictionary form distinct from itself, so there is
    # nothing to fall back TO, and it now emits nothing rather than a piece of
    # its own first character.
    if head["pos"] in ("動詞", "形容詞", "形状詞") and head["lemma_kana"] and head["atype"] is not None:
        out["lemma"] = head["lemma"]
        out["lk"] = head["lemma_kana"]
        out["la"] = head["atype"]
        out["lp"] = classify(head["atype"], len(morae(head["lemma_kana"])), head["pos"])
    return out or None


def load(path=TABLE):
    if not os.path.exists(path):
        sys.exit(f"pitch table not found at {path}; run scripts/pitch.py --build")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Gold set. Verified by hand against the UniDic manual's rules and the standard
# pedagogical descriptions; a few entries follow UniDic where the dictionaries
# list two accents (花 ②尾高 and 心 ② are both UniDic's first-listed reading).
#
# Its job is to fail the build when a rule changes meaning, so it leans on the
# cases the rules actually disagree about: 平板 against 起伏 hosts for every
# auxiliary the corpus uses, rather than a broad sample of easy nouns.
# --------------------------------------------------------------------------

GOLD = {
    # 起伏 ichidan and godan verbs through the paradigm
    "食べる": 2, "食べた": 2, "食べて": 2, "食べない": 2, "食べます": 3,
    "見る": 1, "見た": 1, "見ます": 2,
    "読む": 1, "読んだ": 1, "読みます": 3,
    "書く": 1, "書いた": 1, "書きます": 3,
    "話す": 2, "話した": 2, "話します": 4,
    "走る": 2, "走った": 2,
    "泳ぐ": 2, "泳いだ": 2,
    # 平板 verbs — flat through て形, ない形 and タ形, accented on ま in ます形
    "行く": 0, "行った": 0, "行って": 0, "行かない": 0, "行きます": 3,
    "買う": 0, "買った": 0, "買って": 0,
    "遊ぶ": 0, "遊んだ": 0,
    # adjectives
    "高い": 2, "高かった": 2, "面白い": 4,
    # nouns, including the two UniDic reads differently from the commoner gloss
    "雨": 1, "山": 2, "鼻": 0, "花": 2, "心": 2, "先生": 3, "静か": 1,
}


def selftest():
    """Run GOLD through the full fugashi path. Needs the venv; --build runs it."""
    bad = []
    for word, want in GOLD.items():
        got = (analyse(word) or {}).get("a")
        if got != want:
            bad.append(f"  {word}: expected {want}, got {got}")
    if bad:
        print(f"pitch selftest FAILED ({len(bad)}/{len(GOLD)})")
        print("\n".join(bad))
        return False
    print(f"pitch selftest ok ({len(GOLD)} forms)")
    return True


def build(surfaces, path=TABLE):
    """Distil a surface -> accent table. `surfaces` is [(surface, kana)]."""
    table, hit, lemma_only = {}, 0, 0
    for surface, kana in sorted(set(surfaces)):
        entry = analyse(surface, katakana(kana))
        if not entry:
            continue
        table[key(surface, kana)] = entry
        if "a" in entry:
            hit += 1
        elif "la" in entry:
            lemma_only += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False, sort_keys=True, indent=0)
        f.write("\n")
    total = len(set(surfaces))
    print(
        f"{len(table)} of {total} surfaces -> {path}\n"
        f"  {hit} with a surface accent, {lemma_only} 辞書形 only, "
        f"{total - len(table)} neither"
    )
    return table


def _story_surfaces():
    """Every kanji-bearing surface the built readers contain, with its reading.

    Read from docs/data/ rather than re-segmented: those files are exactly what
    the reader renders, so a surface present there is a surface that needs an
    entry, and the kana beside it is the one the contour must be drawn against —
    including the author's per-occurrence reading overrides, which a fresh
    segmentation would not reproduce.
    """
    import re as _re

    out = []
    data_dir = os.path.join(os.path.dirname(HERE), "docs", "data")
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".js"):
            continue
        src = open(os.path.join(data_dir, name), encoding="utf-8").read()
        m = _re.search(r"=\s*(\{.*\})\s*;?\s*$", src, _re.S)
        if not m:
            continue

        def walk(node):
            if isinstance(node, dict):
                if "t" in node and "k" in node:
                    out.append((node["t"], node["k"]))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(json.loads(m.group(1)))
    return out


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if "--build" in sys.argv:
        if not selftest():
            sys.exit("refusing to write a table the gold set does not agree with")
        build(_story_surfaces())
    else:
        table = load()
        words = [a for a in sys.argv[1:] if not a.startswith("--")]
        for w in words or sorted(table)[:10]:
            for k, v in table.items():
                if k.split("\t")[0] == w.split("\t")[0]:
                    print(f"{k.replace(chr(9), ' ')}: {v}")
