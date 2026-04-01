"""EngineContext — immutable shared runtime context for the pipeline.

FR-003: Provides an immutable container holding all shared runtime dependencies
        (store, config, adapter, and related fields).
FR-004: This module MUST remain under 50 lines.
"""

from __future__ import annotations


class EngineContext:
    """Stub — frozen dataclass not yet implemented."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)
