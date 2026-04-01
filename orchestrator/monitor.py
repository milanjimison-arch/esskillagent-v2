"""PipelineMonitor — rule-driven pipeline health monitor.

FR-063: Produces Observations with dimension, severity, message, and suggestion.
FR-064: Invoked at stage transitions and task batch completions.
FR-065: Monitors BLOCKED ratio anomalies, stale cascade depth, and convergence.
FR-066: Writes monitor observations to the lvl_events table.
FR-067: Module size MUST remain below 200 lines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_observation(
    obs_type: str,
    severity: str,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": obs_type,
        "severity": severity,
        "message": message,
        "timestamp": _now_iso(),
        "details": details,
    }


class PipelineMonitor:
    """Rule-driven pipeline health monitor producing structured observations."""

    def __init__(self, blocked_threshold: float = 0.5) -> None:
        self.blocked_threshold = blocked_threshold
        self._prev_done_count: int | None = None
        self._prev_blocked_count: int | None = None

    def check(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyze tasks and return a list of observation dicts."""
        if not tasks:
            return []

        observations: list[dict[str, Any]] = []

        blocked_obs = self._check_blocked_ratio(tasks)
        if blocked_obs is not None:
            observations.append(blocked_obs)

        cascade_obs = self._check_stale_cascade(tasks)
        if cascade_obs is not None:
            observations.append(cascade_obs)

        convergence_obs = self._check_convergence(tasks)
        if convergence_obs is not None:
            observations.append(convergence_obs)

        return observations

    def _check_blocked_ratio(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        total = len(tasks)
        blocked_count = sum(1 for t in tasks if t.get("status") == "BLOCKED")
        ratio = blocked_count / total

        if ratio <= self.blocked_threshold:
            return None

        return _make_observation(
            obs_type="blocked_ratio_exceeded",
            severity="warning",
            message=(
                f"BLOCKED ratio {ratio:.0%} exceeds threshold "
                f"{self.blocked_threshold:.0%} "
                f"({blocked_count}/{total} tasks blocked)."
            ),
            details={
                "ratio": ratio,
                "blocked_count": blocked_count,
                "total_count": total,
            },
        )

    def _check_stale_cascade(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        stale_ids = {t["id"] for t in tasks if t.get("stale")}
        if not stale_ids:
            return None

        # Build map of task_id -> task for quick lookup
        task_map = {t["id"]: t for t in tasks}

        # Find stale tasks that have a stale parent (cascade children)
        cascade_children: list[str] = []
        cascade_roots: set[str] = set()

        for t in tasks:
            if not t.get("stale"):
                continue
            parent_id = t.get("parent_id")
            if parent_id and parent_id in stale_ids:
                cascade_children.append(t["id"])
                # Find root: walk up until parent is not stale
                root = _find_cascade_root(t["id"], task_map, stale_ids)
                cascade_roots.add(root)

        if not cascade_children:
            return None

        # Use first root found (deterministic: lowest in sort order)
        root_task_id = sorted(cascade_roots)[0]

        # Collect all stale children that belong to this root's cascade
        affected = [c for c in cascade_children if _find_cascade_root(c, task_map, stale_ids) == root_task_id]

        return _make_observation(
            obs_type="stale_cascade_detected",
            severity="warning",
            message=(
                f"Stale cascade detected rooted at task '{root_task_id}' "
                f"affecting {len(affected)} child task(s)."
            ),
            details={
                "root_task_id": root_task_id,
                "affected_task_ids": affected,
            },
        )

    def _check_convergence(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        done_count = sum(1 for t in tasks if t.get("status") == "DONE")
        blocked_count = sum(1 for t in tasks if t.get("status") == "BLOCKED")

        if self._prev_done_count is None:
            # First call: store baseline, no observation
            self._prev_done_count = done_count
            self._prev_blocked_count = blocked_count
            return None

        prev_done = self._prev_done_count
        prev_blocked = self._prev_blocked_count or 0

        self._prev_done_count = done_count
        self._prev_blocked_count = blocked_count

        details = {"done_count": done_count, "blocked_count": blocked_count}

        done_increased = done_count > prev_done
        blocked_decreased_or_zero = blocked_count <= prev_blocked

        if done_increased and blocked_decreased_or_zero:
            return _make_observation(
                obs_type="pipeline_converging",
                severity="info",
                message=(
                    f"Pipeline converging: DONE tasks increased to {done_count}, "
                    f"BLOCKED tasks at {blocked_count}."
                ),
                details=details,
            )

        return _make_observation(
            obs_type="pipeline_diverging",
            severity="warning",
            message=(
                f"Pipeline diverging: DONE={done_count} (prev={prev_done}), "
                f"BLOCKED={blocked_count} (prev={prev_blocked})."
            ),
            details=details,
        )


def _find_cascade_root(
    task_id: str,
    task_map: dict[str, Any],
    stale_ids: set[str],
) -> str:
    """Walk up parent chain to find the stale root (no stale parent)."""
    current_id = task_id
    visited: set[str] = set()

    while True:
        if current_id in visited:
            break
        visited.add(current_id)

        task = task_map.get(current_id)
        if task is None:
            break

        parent_id = task.get("parent_id")
        if parent_id and parent_id in stale_ids:
            current_id = parent_id
        else:
            break

    return current_id
