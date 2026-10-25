"""Numeric extractors — the part of a pyramid pitch that keywords miss.

«Вложи 5000 тг — через неделю получишь 10 000» has no scary words; the signal is
the arithmetic (×2 in a week). Same for «3% в день» (≈ 1 000% годовых) versus a
legitimate «депозит 14% годовых». All functions take FOLDED text (normalize.fold).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_NUM = r"\d{1,3}(?:[ \u00a0.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_MULT = r"(?:к\b|k\b|тыс\w*|мын\w*|млн|миллион\w*)"
_CUR = r"(?:тг|тенге|тнг|₸|kzt|руб\w*|₽|\$|usd|долл\w*|usdt|бакс\w*)"
_AMOUNT = re.compile(rf"(?P<num>{_NUM})\s?(?P<mult>{_MULT})?\s?(?P<cur>{_CUR})?", re.I)

_INVEST = re.compile(
    r"(?:влож\w*|вкладыва\w*|инвестир\w*|внеси\w*|внес\w*|внос\w*|закин\w*|положи\w*|депозит\w*|вход\w*|"
    r"\bсал(?:ыныз|сан\w*|саныз|ып|асыз|асын|ган|дым|дык|сак)?\b|салым\w*|старт\w* с)", re.I)
_RECEIVE = re.compile(
    r"(?:получ(?!ил[оа]?с[ья])\w*|верн\w*|вывед\w*|выводи\w*|вывож\w*|вывел\w*|выплачива\w*|начисля\w*|приход\w*|пришл\w*|"
    r"заработа\w*|станет|превратит\w*|будет\w*|забер\w*|забира\w*|снял\w*|сняла|капа\w*|"
    r"\bал(?:асын|асыз|ыныз|ып|дым|дык)\b|табасы\w*|табыныз|табыс\w*|кайтар\w*|аласы\w*|тусед\w*|на выходе|итого)", re.I)
# «за 2 месяца», «за 14 дней», «2 аптада», «3 айда» — a multi-unit period
_PERIOD_N = re.compile(
    r"(?:(?:за|через)\s(?P<n1>\d+)\s(?P<u1>дн\w*|день|сут\w*|недел\w*|месяц\w*|мес\b)|"
    r"(?P<n2>\d+)\s(?P<u2>кунде|кунге|аптада|аптага|айда|айга))")
_UNIT = {"дн": "day", "де": "day", "су": "day", "не": "week", "ме": "month",
         "ку": "day", "ап": "week", "ай": "month"}

_PERIODS = {
    "day": re.compile(r"(?:в день|за день|в сутки|за сутки|/\s?день|ежедневн\w*|каждый день|кунине|тауликтине|кун сайын|\bкунде\b|кунделикти|через день|через сутки)"),
    "week": re.compile(r"(?:в неделю|за неделю|/\s?нед\w*|еженедельн\w*|аптасына|апта сайын|через неделю|каждую неделю|\bаптада\b)"),
    "month": re.compile(r"(?:в месяц|за месяц|/\s?мес\w*|ежемесячн\w*|айына|ай сайын|через месяц|\bайда\b)"),
    "year": re.compile(r"(?:годовых|в год|за год|/\s?год|ежегодн\w*|жылдык\w*|жылына)"),
}
# Above these per-period rates a promise is unrealistic for the KZ market
# (bank deposits ≈ 13–16% годовых; anything ≥ 40% годовых needs a human look).
UNREALISTIC_RATE = {"day": 0.5, "week": 2.0, "month": 8.0, "year": 40.0}
_PERIOD_RU = {"day": "в день", "week": "в неделю", "month": "в месяц", "year": "годовых"}

_PERCENT = re.compile(r"(?P<pct>\d+(?:[.,]\d+)?)\s?%")
_MULTIPLIER = re.compile(r"(?<![\w])(?:[xх×]\s?(?P<a>\d{1,3})|(?P<b>\d{1,3})\s?[xх×])(?![\w])")
_MONEY_CTX = re.compile(r"(?:влож|депозит|доход|прибыл|ден[еь]г|инвест|\bсал|акша|табыс|вклад|капитал|"
                        r"\bплат|выплат|начисл|пайда)", re.I)
# Regulated-banking phrasing: a rate quoted this way is a bank product, not a promise.
_BANK_CTX = re.compile(r"(?:капитализ\w*|кфгд|кгфд|кдкк|ставк\w* вознагражд\w*)", re.I)
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ \-]?){3}\d{4}(?!\d)")


@dataclass
class NumericHit:
    signal: str
    strength: float
    note: str
    span: tuple[int, int]


def parse_amount(num: str, mult: str | None) -> float | None:
    raw = num.replace("\u00a0", " ").strip()
    # «10 000», «10.000», «10,000» -> thousands separators; «2,5» -> decimal.
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", raw):
        raw = re.sub(r"[ .,]", "", raw)
    else:
        raw = raw.replace(" ", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    m = (mult or "").lower()
    if m.startswith(("к", "k", "тыс", "мын")):
        value *= 1_000
    elif m.startswith(("млн", "миллион")):
        value *= 1_000_000
    return value


def _amounts(text: str) -> list[tuple[float, int, int, bool]]:
    """(value, start, end, has_currency) for every number that looks like money."""
    out = []
    for m in _AMOUNT.finditer(text):
        val = parse_amount(m.group("num"), m.group("mult"))
        if val is None or val < 50:          # «3 места», «2 дня» — not money
            continue
        # skip years / phone-like / percent numbers
        tail = text[m.end():m.end() + 2]
        if tail.startswith("%"):
            continue
        out.append((val, m.start(), m.end(), bool(m.group("cur") or m.group("mult"))))
    return out


def _near(rx: re.Pattern, text: str, start: int, end: int, radius: int = 22) -> bool:
    return bool(rx.search(text[max(0, start - radius):min(len(text), end + radius)]))


def _period_after(text: str, pos: int, radius: int = 40) -> str | None:
    return _period_n_after(text, pos, radius)[0]


def _period_n_after(text: str, pos: int, radius: int = 40) -> tuple[str | None, int]:
    """Nearest period after `pos` -> (day|week|month|year, number of units)."""
    window = text[pos:pos + radius]
    best, best_at, count = None, radius + 1, 1
    for name, rx in _PERIODS.items():
        m = rx.search(window)
        if m and m.start() < best_at:
            best, best_at, count = name, m.start(), 1
    m = _PERIOD_N.search(window)
    if m and m.start() <= best_at:
        n = int(m.group("n1") or m.group("n2"))
        unit = (m.group("u1") or m.group("u2"))[:2]
        if n > 0 and unit in _UNIT:
            best, count = _UNIT[unit], n
    return best, count


def return_ratio(text: str) -> list[NumericHit]:
    """«вложи 5000 → получи 10 000»: invest-amount followed by a larger receive-amount."""
    hits: list[NumericHit] = []
    amounts = _amounts(text)
    for i, (a1, s1, e1, cur1) in enumerate(amounts):
        if not _near(_INVEST, text, s1, e1):
            continue
        for a2, s2, e2, cur2 in amounts[i + 1:]:
            if s2 - e1 > 80:
                break
            between = text[e1:s2]
            if not (_RECEIVE.search(between) or _near(_RECEIVE, text, s2, e2, 18)):
                continue
            if not (cur1 or cur2) and a1 < 1000:     # «вложи 3, получи 5» — not money
                continue
            ratio = a2 / a1 if a1 else 0
            if ratio <= 0 or ratio > 1000:
                continue
            period, units = _period_n_after(text, e2)
            if period is None:
                period, units = _period_n_after(text, e1)
            if ratio >= 1.3:
                strength = 1.0 if ratio >= 2 or period in ("day", "week") else 0.75
                when = f", {_PERIOD_RU.get(period, '')}".rstrip(", ") if period else ""
                hits.append(NumericHit(
                    "pyramid.return_ratio", strength,
                    f"обещано ×{ratio:.1f} к вложению{when}", (s1, e2)))
                break
            if period is None:
                continue
            # «вложила 5000, вывожу по 1500 каждую неделю» (payout < stake) or
            # «вложи 10 000 — через неделю 12 000» (small multiple over a short period)
            rate = 100 * (ratio if ratio < 1 else ratio - 1) / max(1, units)
            if rate >= UNREALISTIC_RATE[period]:
                annual = {"day": 365, "week": 52, "month": 12, "year": 1}[period] * rate
                hits.append(NumericHit(
                    "pyramid.return_rate", 1.0,
                    f"доход {rate:g}% от вложения {_PERIOD_RU[period]} (≈{annual:,.0f}% годовых)".replace(",", " "),
                    (s1, e2)))
                break
    return hits


def return_rate(text: str) -> list[NumericHit]:
    """«3% в день», «30% в месяц» above the unrealistic threshold for that period."""
    hits: list[NumericHit] = []
    for m in _PERCENT.finditer(text):
        try:
            pct = float(m.group("pct").replace(",", "."))
        except ValueError:
            continue
        period, units = _period_n_after(text, m.end(), 30)
        if period is None:
            before = text[max(0, m.start() - 25):m.start()]
            for name, rx in _PERIODS.items():
                if rx.search(before):
                    period = name
                    break
        pct = pct / max(1, units)            # «120% за 2 месяца» -> 60% в месяц
        context = text[max(0, m.start() - 40):m.end() + 40]
        if _BANK_CTX.search(text[max(0, m.start() - 60):m.end() + 60]) or \
                text[max(0, m.start() - 4):m.start()].endswith("под "):
            continue                         # «депозит под 16%, капитализация ежемесячно»
        if period is None:
            if pct >= 100 and _MONEY_CTX.search(context):
                hits.append(NumericHit("pyramid.return_rate", 0.7,
                                       f"обещано {pct:g}% дохода", (m.start(), m.end())))
            continue
        if pct >= UNREALISTIC_RATE[period] and _MONEY_CTX.search(context):
            annual = {"day": 365, "week": 52, "month": 12, "year": 1}[period] * pct
            hits.append(NumericHit(
                "pyramid.return_rate", 1.0,
                f"{pct:g}% {_PERIOD_RU[period]} (≈{annual:,.0f}% годовых; вклад в банке РК ≈ 14–16%)"
                .replace(",", " "),
                (m.start(), m.end())))
    return hits


def multipliers(text: str) -> list[NumericHit]:
    """«x2», «2х» next to an investment context."""
    hits: list[NumericHit] = []
    for m in _MULTIPLIER.finditer(text):
        n = int(m.group("a") or m.group("b"))
        if n < 2 or n > 100:
            continue
        ctx = text[max(0, m.start() - 40):m.end() + 40]
        if _MONEY_CTX.search(ctx) and not re.search(r"казин|слот|занос|lucky|авиатор|aviator|ставк", ctx):
            hits.append(NumericHit("pyramid.return_ratio", 0.8,
                                   f"обещано умножение вложения ×{n}", (m.start(), m.end())))
    return hits


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def card_numbers(text: str) -> list[tuple[str, tuple[int, int]]]:
    """Bank card numbers (16 digits, Luhn-valid) — a personal-card payment channel."""
    out = []
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 16 and luhn_ok(digits) and len(set(digits)) > 2:
            out.append((digits, (m.start(), m.end())))
    return out


def mask_card(digits: str) -> str:
    """Personal data minimisation: show only BIN + last 4 («4400 43•• •••• 1234»)."""
    return f"{digits[:4]} {digits[4:6]}•• •••• {digits[-4:]}"
