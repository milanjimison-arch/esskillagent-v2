"""EngineContext — immutable shared runtime context for the pipeline.

FR-003: Provides an immutable container holding all shared runtime dependencies
        (store, config, adapter, and related fields).
FR-004: This module MUST remain under 50 lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineContext:
    """Frozen dataclass holding all shared runtime dependencies."""

    run_id: str
    db_path: Path
    adapter: Any
    store: Any
    stages: tuple[str, ...] = ("spec", "plan", "implement", "acceptance")
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not isinstance(self.db_path, Path):
            raise TypeError("db_path must be a Path")
