"""Pipeline engine stub — RED phase.

This module is intentionally minimal: it exports the symbols required by
the test suite so that imports succeed, but all behaviour is unimplemented,
causing assertion failures in every test.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# STAGE_NAMES — canonical four-stage order (stub returns wrong value so tests fail)
# ---------------------------------------------------------------------------

STAGE_NAMES: tuple[str, ...] = ()  # stub: empty tuple — tests expect 4 entries


# ---------------------------------------------------------------------------
# PipelineResult — frozen dataclass (stub fields present, values wrong)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineResult:
    """Result of a full pipeline run."""

    passed: bool = False
    stage_results: dict[str, Any] = field(default_factory=dict)
    skipped_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None


# ---------------------------------------------------------------------------
# PipelineEngine — stub class; run() is not implemented
# ---------------------------------------------------------------------------


class PipelineEngine:
    """Stub pipeline engine — does not implement any flow-control logic."""

    def __init__(self, stages: dict[str, Any], config: dict[str, Any]) -> None:
        self._stages = stages
        self._config = config
        self.lock = asyncio.Lock()

    async def run(self) -> PipelineResult:
        """Stub: raises NotImplementedError to make all behaviour tests fail."""
        raise NotImplementedError("PipelineEngine.run() is not yet implemented")
