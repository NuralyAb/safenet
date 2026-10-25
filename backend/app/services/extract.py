"""Extract hard identifiers from free text (captions, descriptions, subtitles).

Pure + regex-based -> unit-tested without network. Collectors call this so every
source feeds the same wallet/telegram/domain signals into the Fraud Graph.
"""
from __future__ import annotations

import re

# Telegram handle via @mention or a t.me/telegram.me link. Case-insensitive so
# "T.ME/BETBOT" (uppercase, no @) is caught — common in casino/betting posts.
_TELEGRAM = re.compile(r"(?:t\.me/|telegram\.me/|@)([A-Za-z][A-Za-z0-9_]{3,31})", re.I)

# Crypto wallets, precise patterns to avoid false positives (base58 excludes 0/O/I/l):
#   ETH/EVM   0x + 40 hex
#   TRON      T + 33 base58 (34 chars total) — the USDT-TRC20 rail scammers love
#   BTC bech32 bc1 + 25..87
#   BTC legacy [13] + 25..34 base58 (P2PKH / P2SH)
_WALLET = re.compile(
    r"\b(0x[a-fA-F0-9]{40}"
    r"|T[1-9A-HJ-NP-Za-km-z]{33}"
    r"|bc1[a-z0-9]{25,87}"
    r"|[13][1-9A-HJ-NP-Za-km-z]{25,34})\b"
)

_DOMAIN = re.compile(
    r"\b([a-z0-9][a-z0-9-]*\.(?:com|net|io|ru|org|biz|app|me|kz|xyz|club|bet|win|site|top|online|pro|vip|"
    r"fun|live|link|casino|cc|info|shop|games|best|space|store))\b", re.I)
# Hosts that are really messaging links, not standalone "infrastructure" domains —
# the handle is already captured under telegram.
_TELEGRAM_HOSTS = {"t.me", "telegram.me"}

# Phone numbers — a contact channel scammers drop in captions/on-screen ("звоните",
# WhatsApp). Candidate = optional + then digits with spaces/dashes/parens; we then keep
# only those with 10–15 digits total (E.164 range) so wallets/dates aren't caught. The
# lookbehind/lookahead exclude digit runs that sit inside an alphanumeric token (e.g.
# a hex wallet), which would otherwise leak a fake "phone".
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().\-]{8,16}\d(?![\w])")


_CARD_LIKE = re.compile(r"(?<!\d)(?:\d{4}[ \-]?){3}\d{4}(?!\d)")


def _normalize_phones(text: str) -> list[str]:
    out: set[str] = set()
    for cand in _PHONE.findall(text):
        digits = re.sub(r"\D", "", cand)
        # KZ local 8XXXXXXXXXX -> +7XXXXXXXXXX (leading 8 is the trunk prefix).
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        if 10 <= len(digits) <= 15:
            out.add("+" + digits)
    return sorted(out)


def extract_identifiers(text: str) -> dict:
    text = text or ""
    domains = {d.lower() for d in _DOMAIN.findall(text)} - _TELEGRAM_HOSTS
    return {
        "telegram": sorted({m.lower() for m in _TELEGRAM.findall(text)}),
        "wallets": sorted(set(_WALLET.findall(text))),
        "domains": sorted(domains),
        # a 16-digit bank card is not a phone number — blank cards out first
        "phones": _normalize_phones(_CARD_LIKE.sub(" ", text)),
    }
