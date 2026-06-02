"""
Keyword relevance filtering.
Each item's title + summary is matched (case-insensitive) against the keyword list.
Returns a list of matched keywords.
"""

import re


def _build_patterns(keywords: list[str]) -> list[tuple[str, re.Pattern]]:
    patterns = []
    for kw in keywords:
        # Word-boundary match so "AI" doesn't match "TRAIN"
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        patterns.append((kw, pattern))
    return patterns


_COMPILED: list[tuple[str, re.Pattern]] = []
_LAST_KEYWORDS: list[str] = []


def match_keywords(item: dict, keywords: list[str]) -> list[str]:
    """Return list of keywords that appear in the item's title or summary."""
    global _COMPILED, _LAST_KEYWORDS
    if keywords != _LAST_KEYWORDS:
        _COMPILED = _build_patterns(keywords)
        _LAST_KEYWORDS = keywords[:]

    text = " ".join(filter(None, [item.get("title", ""), item.get("summary", "")]))
    matched = [kw for kw, pat in _COMPILED if pat.search(text)]
    return matched
