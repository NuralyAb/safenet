"""Numbers written as words -> digits (RU + KZ + money slang), on FOLDED text.

Streams and chats rarely write «20 000 тг»; they say «двадцать тысяч», «он мың
теңге», «пятихатка», «косарь», «в два раза». The numeric extractors need digits,
so this builds an extra text view where such phrases become numbers:

    «вложил двадцать тысяч получил сорок»  -> «вложил 20000 получил 40»
    «бес мың теңге салып он мың алдым»     -> «5000 теңге салып 10000 алдым»

Words that collide with ordinary Russian (KZ «он»=10 vs «он»=he, «торт»=4 vs
cake) only count when next to another number word, a currency or «раз/есе».
"""
from __future__ import annotations

import re

_UNITS = {
    # Russian (folded: ё→е) with common inflections
    "ноль": 0, "один": 1, "одна": 1, "одну": 1, "одного": 1, "два": 2, "две": 2, "двух": 2,
    "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9, "десять": 10, "десяти": 10,
    "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40, "сорока": 40,
    "пятьдесят": 50, "пятидесяти": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80,
    "девяносто": 90, "сто": 100, "ста": 100, "двести": 200, "двухсот": 200, "триста": 300,
    "трехсот": 300, "четыреста": 400, "пятьсот": 500, "пятисот": 500, "шестьсот": 600,
    "семьсот": 700, "восемьсот": 800, "девятьсот": 900, "полторы": 1.5, "полтора": 1.5,
    # Kazakh (folded: қ→к, ң→н, ү/ұ→у, ө→о, і→и, ғ→г)
    "бир": 1, "еки": 2, "уш": 3, "торт": 4, "бес": 5, "алты": 6, "жети": 7, "сегиз": 8, "тогыз": 9,
    "он": 10, "жиырма": 20, "отыз": 30, "кырык": 40, "елу": 50, "алпыс": 60, "жетпис": 70,
    "сексен": 80, "токсан": 90,
}
# Multipliers: thousand / million (flush into the total) and KZ «жүз» (×100, local).
_THOUSAND = re.compile(r"^(?:тысяч\w*|тыщ\w*|тыс|мын\w*)$")
_MILLION = re.compile(r"^(?:миллион\w*|млн|лям\w*|лимон\w*)$")
_HUNDRED_KZ = re.compile(r"^жуз\w*$")
# Stand-alone money slang
_SLANG = {"косарь": 1000, "косаря": 1000, "косарей": 1000, "косарик": 1000, "пятихатка": 500,
          "пятихатку": 500, "пятихаты": 500, "двадцатку": 20000, "двадцатка": 20000,
          "сотку": 100000, "сотка": 100000}

_AMBIGUOUS = {"он", "бес", "уш", "торт", "бир", "алты", "жети", "сегиз", "тогыз", "еки", "ста", "три"}
_UNIT_AFTER = re.compile(r"^(?:тенге|тнг|тг|т|₸|kzt|руб\w*|долл\w*|\$|процент\w*|%|раз|раза|есе\w*|"
                         r"адам\w*|орын\w*|номер\w*|мест\w*|дн\w*|кун\w*|недел\w*|апта\w*|ай\w*|месяц\w*)$")
_TOKEN = re.compile(r"\S+")
_WORD = re.compile(r"^([а-я]+)([^а-я]*)$")


def _value_kind(word: str):
    if word in _UNITS:
        return "unit", _UNITS[word]
    if _THOUSAND.match(word):
        return "mult", 1000
    if _MILLION.match(word):
        return "mult", 1_000_000
    if _HUNDRED_KZ.match(word):
        return "hundred", 100
    if word in _SLANG:
        return "slang", _SLANG[word]
    return None, 0


def _evaluate(parts: list[tuple[str, float]]) -> float:
    total, current = 0.0, 0.0
    for kind, v in parts:
        if kind == "unit":
            current += v
        elif kind == "hundred":
            current = (current or 1) * v
        elif kind == "mult":
            total += (current or 1) * v
            current = 0.0
        elif kind == "slang":
            current += v
    return total + current


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def words_to_digits(text: str) -> str:
    """Replace number-word phrases with digits. Returns the text unchanged when none."""
    tokens = list(_TOKEN.finditer(text))
    if not tokens:
        return text
    out: list[str] = []
    last = 0
    i = 0
    changed = False
    while i < len(tokens):
        m = _WORD.match(tokens[i].group(0))
        kind = _value_kind(m.group(1))[0] if m else None
        if not kind:
            i += 1
            continue
        j, parts, tail = i, [], ""
        while j < len(tokens):
            mj = _WORD.match(tokens[j].group(0))
            if not mj:
                break
            k, v = _value_kind(mj.group(1))
            if not k:
                break
            parts.append((k, v))
            tail = mj.group(2)
            j += 1
            if tail:                       # punctuation ends the phrase («двадцать,»)
                break
        nxt = ""
        if j < len(tokens):
            mn = re.match(r"^[а-я%₸$]+", tokens[j].group(0))
            nxt = mn.group(0) if mn else tokens[j].group(0)
        words = [_WORD.match(tokens[t].group(0)).group(1) for t in range(i, j)]
        strong = (len(parts) >= 2 or any(k in ("mult", "slang", "hundred") for k, _ in parts)
                  or bool(_UNIT_AFTER.match(nxt)) or (len(words) == 1 and words[0] not in _AMBIGUOUS))
        if strong:
            out.append(text[last:tokens[i].start()])
            out.append(_fmt(_evaluate(parts)) + tail)
            last = tokens[j - 1].end()
            changed = True
        i = j
    if not changed:
        return text
    out.append(text[last:])
    return "".join(out)
