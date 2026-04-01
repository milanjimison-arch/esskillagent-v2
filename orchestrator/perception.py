"""Perception module — NC/NR marker detection and uncertainty heuristic scanner.

Provides functions for analysing stage output text to detect markers that
require clarification (NC) or research (NR), as well as heuristic signals
of uncertainty such as question density, TBD/TODO placeholders, and hedging
expressions.
"""

from __future__ import annotations


def detect_nc_markers(text: str) -> list[str]:
    """Stub — not yet implemented."""
    pass


def detect_nr_markers(text: str) -> list[str]:
    """Stub — not yet implemented."""
    pass


def question_density(text: str) -> float:
    """Stub — not yet implemented."""
    pass


def detect_tbd_todo(text: str) -> list[str]:
    """Stub — not yet implemented."""
    pass


def detect_hedging(text: str) -> list[str]:
    """Stub — not yet implemented."""
    pass


def analyse(text: str) -> dict:
    """Stub — not yet implemented."""
    pass
