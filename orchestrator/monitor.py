"""PipelineMonitor — rule-driven pipeline health monitor.

FR-063: Produces Observations with dimension, severity, message, and suggestion.
FR-064: Invoked at stage transitions and task batch completions.
FR-065: Monitors BLOCKED ratio anomalies, stale cascade depth, and convergence.
FR-066: Writes monitor observations to the lvl_events table.
FR-067: Module size MUST remain below 200 lines.
"""

from __future__ import annotations

from typing import Any


class PipelineMonitor:
    """Stub — returns empty list for all inputs until implemented.

    Constructor is functional so that import and instantiation do not fail.
    All behaviour-driving logic is absent; tests will fail with AssertionError
    because the returned observations list is always empty.
    """

    def __init__(self, blocked_threshold: float = 0.5) -> None:
        # Attribute stored so that attribute-access tests fail with AssertionError
        # rather than AttributeError.
        self.blocked_threshold = blocked_threshold

    def check(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return an empty list (stub — no detection logic implemented)."""
        return []
