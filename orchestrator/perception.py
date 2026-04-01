"""Perception module — NC/NR marker detection and uncertainty heuristic scanner.

Provides functions for analysing stage output text to detect markers that
require clarification (NC) or research (NR), as well as heuristic signals
of uncertainty such as question density, TBD/TODO placeholders, and hedging
expressions.
"""

from __future__ import annotations

import re

# Hedging expressions to detect (case-insensitive)
_HEDGING_PATTERNS: list[str] = [
    "not sure",
    "it seems",
    "could be",
    "might",
    "perhaps",
    "possibly",
    "maybe",
    "unclear",
]

# Sentence terminator pattern
_SENTENCE_SPLIT_RE = re.compile(r'[.?!]+')

# TBD/TODO/FIXME pattern — uppercase only, word boundary
_TBD_TODO_RE = re.compile(r'\b(TBD|TODO|FIXME)\b')


def detect_nc_markers(text: str) -> list[str]:
    """Return list of [NC: ...] marker strings found in text (case-sensitive)."""
    if not text:
        return []
    return re.findall(r'\[NC:[^\]]*\]', text)


def detect_nr_markers(text: str) -> list[str]:
    """Return list of [NR: ...] marker strings found in text (case-sensitive)."""
    if not text:
        return []
    return re.findall(r'\[NR:[^\]]*\]', text)


def question_density(text: str) -> float:
    """Return ratio of sentences ending with '?' to total non-empty sentences."""
    if not text:
        return 0.0

    # Split keeping terminators so we can tell which ended each sentence chunk
    parts = re.split(r'([.?!]+)', text)

    # Build (content, terminator) pairs; parts alternates: content, delim, content, delim...
    sentence_is_question: list[bool] = []
    for i in range(0, len(parts), 2):
        content = parts[i].strip()
        terminator = parts[i + 1] if i + 1 < len(parts) else ""
        # Count this as a sentence if it has content or a non-empty terminator
        if content or terminator.strip():
            sentence_is_question.append('?' in terminator)

    total = len(sentence_is_question)
    if total == 0:
        return 1.0 if '?' in text else 0.0

    question_count = sum(1 for is_q in sentence_is_question if is_q)
    return float(question_count) / float(total)


def detect_tbd_todo(text: str) -> list[str]:
    """Return list of matched TBD/TODO/FIXME keywords found in text (uppercase only)."""
    if not text:
        return []
    return _TBD_TODO_RE.findall(text)


def detect_hedging(text: str) -> list[str]:
    """Return list of hedging expressions found in text (case-insensitive)."""
    if not text:
        return []

    found: list[str] = []
    lower_text = text.lower()

    for pattern in _HEDGING_PATTERNS:
        if pattern in lower_text:
            found.append(pattern)

    return found


def analyse(text: str) -> dict:
    """Aggregate all perception signals into a single result dict."""
    nc_markers = detect_nc_markers(text)
    nr_markers = detect_nr_markers(text)

    return {
        "nc_markers": nc_markers,
        "nr_markers": nr_markers,
        "question_density": question_density(text),
        "tbd_todo": detect_tbd_todo(text),
        "hedging": detect_hedging(text),
        "needs_clarification": bool(nc_markers),
        "needs_research": bool(nr_markers),
    }
