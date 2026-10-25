"""Text normalisation against obfuscation — the «главная сложность» of track 2/3.

Schemes hide their keywords: «к@зино», «К А З И Н О», «kazino», mixed Latin/Cyrillic
homoglyphs («KAЗИНО»), styled Unicode letters («𝓴𝓪𝔃𝓲𝓷𝓸»), emoji instead of words,
and Kazakh written with or without its own letters («тегін» / «тегин»).

Instead of one lossy normalised string we build several VIEWS of the same text and
let every pattern run on each of them. The detector reports which view matched, so
the analyst sees *how* a signal was hidden («обфускация: к@зино → казино»).

All patterns in the lexicon are written for the folded form: lowercase, ё→е and
Kazakh letters folded to their Russian look-alikes (қ→к, ұ/ү→у, ө→о, ә→а, ғ→г,
ң→н, і→и, һ→х). Folding is 1:1 per character, so quotes can be cut from the
original text at the same offsets.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Zero-width / invisible characters used to break keywords («ка​зино»).
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)

# Kazakh -> Russian look-alike (1:1). Lets one pattern match «тегін» and «тегин».
_KZ_FOLD = str.maketrans("әғқңөұүһіӘҒҚҢӨҰҮҺІ", "агкноуухиагкноуухи")

KAZAKH_LETTERS = set("әғқңөұүһі")

# Latin homoglyphs of Cyrillic letters (after lowercasing).
_HOMOGLYPH = {"a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у",
              "k": "к", "m": "м", "t": "т", "b": "в", "h": "н", "i": "і", "u": "и"}
# Digits / symbols standing in for letters inside a word («к@зин0», «3аработок»).
_LEET_CYR = {"0": "о", "@": "а", "3": "з", "4": "ч", "6": "б", "1": "і", "$": "s"}
_LEET_LAT = {"0": "o", "@": "a", "3": "e", "1": "i", "$": "s", "4": "a", "5": "s", "7": "t"}

_CYR = re.compile(r"[а-яёәғқңөұүһі]")
_LAT = re.compile(r"[a-z]")
_TOKEN = re.compile(r"[^\s]+")

# Emoji -> words. Emoji are a common way to say «казино»/«деньги» without the word.
_EMOJI_WORDS = {
    "🎰": "казино слоты", "🎲": "ставки кости", "🃏": "казино карты", "♠": "казино покер",
    "♣": "казино", "♥": "", "♦": "казино", "🎱": "ставки", "🎡": "колесо фортуны",
    "💸": "деньги", "💰": "деньги", "🤑": "деньги заработок", "💵": "деньги", "💴": "деньги",
    "💶": "деньги", "💲": "деньги", "🏦": "банк", "📈": "доход рост", "🚀": "рост",
    "🎁": "подарок розыгрыш", "🏆": "приз", "🎫": "билет", "🎟": "билет",
    "🔗": "ссылка", "👇": "ссылка ниже", "⬇": "ссылка ниже", "👉": "переходи",
    "⏳": "срочно", "⌛": "срочно", "⏰": "срочно", "🔥": "", "💳": "карта перевод",
}

# Russian transliteration (Latin -> Cyrillic), longest keys first.
_TRANSLIT = [
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"),
    ("ya", "я"), ("yu", "ю"), ("yo", "е"), ("ts", "ц"), ("ye", "е"), ("ai", "ай"),
    ("ei", "ей"), ("oi", "ой"), ("yy", "ый"), ("yi", "ый"), ("iy", "ий"), ("ii", "ий"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("w", "в"), ("g", "г"), ("d", "д"), ("e", "е"),
    ("z", "з"), ("i", "и"), ("y", "ы"), ("j", "ж"), ("k", "к"), ("q", "к"), ("l", "л"),
    ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"),
    ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "к"), ("x", "кс"),
]
# Kazakh Latin (2021) diacritics -> Cyrillic before generic translit.
_KZ_LATIN = str.maketrans({"á": "а", "ǵ": "г", "ń": "н", "ó": "о", "ú": "у", "ı": "и",
                           "ü": "у", "ö": "о", "ş": "ш", "ç": "ч", "ğ": "г"})

# Latin words that must stay Latin (brands / platforms matched in Latin by the lexicon).
_KEEP_LATIN = re.compile(
    r"^(?:https?|www|t\.me|wa\.me|bit\.ly|kaspi|gold|halyk|jusan|telegram|whatsapp|"
    r"instagram|tiktok|youtube|bet|casino|slot|slots|jackpot|promo|bonus|vip|live|"
    r"stream|free|win|ref|usdt|crypto|lucky|jet|aviator|mines|crash|plinko)$"
)
# URLs, @handles and e-mails are left untouched (but «к@зино» is a word, not a handle).
_URLISH = re.compile(r"(?:https?://|www\.|\.[a-z]{2,4}(?:/|$)|^@|@[\w-]+\.[a-z]{2,})")

# «к а з и н о», «к.а.з.и.н.о», «к-а-з-и-н-о», «к а з и н ода» (Kazakh suffix): 4+ single letters.
_SPACED = re.compile(r"(?<!\w)(?:\w[\s.\-_*·|/\\]{1,2}){3,}\w+(?!\w)")

# Translit drops the soft sign: restore it in the words the lexicon relies on.
_TRANSLIT_FIX = {"денги": "деньги", "толко": "только", "ден": "день", "болше": "больше",
                 "болшой": "большой", "сегоднйа": "сегодня", "участиа": "участия", "наш": "наш"}


@dataclass(frozen=True)
class TextViews:
    original: str          # NFKC + invisibles removed (quotes are cut from here)
    base: str              # folded; same length as `original` when `aligned`
    deobf: str             # base with homoglyphs / leet fixed (same length as base)
    collapsed: str         # spaced letters joined («к а з и н о» -> «казино»)
    translit: str          # Latin words transliterated to Cyrillic
    emoji: str             # words that the emoji in the text stand for
    aligned: bool          # original/base/deobf share offsets

    def items(self) -> list[tuple[str, str]]:
        """(view name, text) in priority order — a pattern hit on the first view wins."""
        out = [("base", self.base)]
        if self.deobf != self.base:
            out.append(("deobf", self.deobf))
        if self.collapsed != self.base:
            out.append(("collapsed", self.collapsed))
        if self.translit and self.translit != self.base:
            out.append(("translit", self.translit))
        if self.emoji:
            out.append(("emoji", self.emoji))
        return out


def fold(text: str) -> str:
    """Lowercase + ё→е + Kazakh letters folded (1:1 per char when lower() is)."""
    return text.lower().replace("ё", "е").translate(_KZ_FOLD)


def _deobfuscate_token(tok: str) -> str:
    """Fix a token that mixes scripts or hides letters behind digits/symbols."""
    letters = sum(ch.isalpha() for ch in tok)
    if letters < 3:
        return tok
    has_cyr = bool(_CYR.search(tok))
    has_lat = bool(_LAT.search(tok))
    chars = list(tok)
    if has_cyr and has_lat:                         # «kaзино» -> «казино»
        chars = [_HOMOGLYPH.get(c, c) for c in chars]
    leet = _LEET_CYR if has_cyr else _LEET_LAT
    digits = sum(ch.isdigit() for ch in tok)
    if digits and digits >= letters:               # «5000тг», «x100» — numbers, not leet
        return "".join(chars)
    for i, c in enumerate(chars):
        if c in leet:
            prev_alpha = i > 0 and chars[i - 1].isalpha()
            next_alpha = i + 1 < len(chars) and chars[i + 1].isalpha()
            if prev_alpha or next_alpha:
                chars[i] = leet[c]
    return "".join(chars)


def _deobfuscate(base: str) -> str:
    """Token-wise de-obfuscation preserving length (all replacements are 1:1)."""
    def fix(m: re.Match) -> str:
        tok = m.group(0)
        if _URLISH.search(tok):
            return tok
        out = _deobfuscate_token(tok)
        return out if len(out) == len(tok) else tok
    return fold(_TOKEN.sub(fix, base))


def _collapse_spaced(text: str) -> str:
    def join(m: re.Match) -> str:
        return re.sub(r"[\s.\-_*·|/\\]", "", m.group(0))
    return _SPACED.sub(join, text)


def _translit_word(word: str) -> str:
    w = word.translate(_KZ_LATIN)
    out, i = [], 0
    while i < len(w):
        for lat, cyr in _TRANSLIT:
            if w.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            out.append(w[i])
            i += 1
    return "".join(out)


def _translit(base: str) -> str:
    if not _LAT.search(base):
        return ""

    def conv(m: re.Match) -> str:
        tok = m.group(0)
        if _URLISH.search(tok) or any(ch.isdigit() for ch in tok):
            return tok
        core = re.sub(r"[^a-záǵńóúıüöşçğ]", "", tok)
        if not core or _KEEP_LATIN.match(core) or _CYR.search(tok):
            return tok
        return re.sub(r"[a-záǵńóúıüöşçğ]+", lambda w: _translit_word(w.group(0)), tok)

    out = fold(_TOKEN.sub(conv, base))
    return re.sub(r"[а-я]+", lambda w: _TRANSLIT_FIX.get(w.group(0), w.group(0)), out)


def _emoji_words(text: str) -> str:
    words = [w for ch, w in _EMOJI_WORDS.items() if ch in text and w]
    return " ".join(words)


def build_views(text: str) -> TextViews:
    original = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE)
    base = fold(original)
    aligned = len(base) == len(original)
    deobf = _deobfuscate(base)
    if len(deobf) != len(base):
        deobf = base
    collapsed = _collapse_spaced(deobf)
    return TextViews(
        original=original, base=base, deobf=deobf, collapsed=collapsed,
        translit=_translit(collapsed), emoji=_emoji_words(original), aligned=aligned,
    )


def detect_language(text: str) -> str:
    """Rough language tag for reporting: kk | ru | mixed | translit | unknown."""
    t = (text or "").lower()
    cyr = len(_CYR.findall(t))
    lat = len(_LAT.findall(t))
    kz_letters = sum(t.count(ch) for ch in KAZAKH_LETTERS)
    kz_words = len(re.findall(
        r"\b(?:және|бар|жоқ|үшін|мен|сен|біз|сіз|ақша|тегін|қатыс\w*|ұтыс\w*|салым\w*|"
        r"табыс\w*|бүгін|керек|емес|осы|бұл|жеңімпаз\w*|сыйлық\w*|ойын\w*|жазыл\w*)\b", t))
    if cyr == 0 and lat == 0:
        return "unknown"
    if lat > cyr * 2:
        return "translit"
    kz = kz_letters >= 2 or kz_words >= 2
    ru = bool(re.search(r"\b(?:и|в|на|не|что|это|за|для|как|по|от|получи\w*|участ\w*)\b", t))
    if kz and ru:
        return "mixed"
    return "kk" if kz else "ru"
