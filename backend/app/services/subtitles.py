"""Subtitle cleaning — turn a .vtt/.srt file into plain text for analysis.

Subtitles often carry the actual pitch («вложи и получай 30% в день») that isn't
in the caption. Pure + unit-tested; the yt-dlp fetch that produces the file is
integration.
"""
from __future__ import annotations

import re

_TIMESTAMP = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*")
_TAG = re.compile(r"<[^>]+>")
_CUE_SETTINGS = re.compile(r"^\d+$")   # SRT cue numbers


def clean_subtitles(raw: str) -> str:
    """Strip WEBVTT/SRT headers, timestamps, tags and numbering -> deduped text."""
    lines: list[str] = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.startswith("Kind:") or s.startswith("Language:"):
            continue
        if _TIMESTAMP.match(s) or _CUE_SETTINGS.match(s):
            continue
        s = _TAG.sub("", s).strip()
        if not s or s in seen:        # dedupe (auto-subs repeat lines a lot)
            continue
        seen.add(s)
        lines.append(s)
    return " ".join(lines)
