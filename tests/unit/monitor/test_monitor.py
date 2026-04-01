"""Unit tests for orchestrator/monitor.py — PipelineMonitor.

Feature: Rule-driven pipeline health monitor that produces Observations
         and writes them to the LVL event system.

FR-063: Produces Observations with dimension, severity, message, and suggestion.
FR-064: Invoked at stage transitions and task batch completions.
FR-065: Monitors BLOCKED ratio anomalies (threshold: 50%), stale cascade depth,
        and convergence/divergence tracking.
FR-066: Writes monitor observations to the lvl_events table.
FR-067: Module size MUST remain below 200 lines.

Test coverage areas:
  1.  FR-063: PipelineMonitor is importable and instantiable with default threshold.
  2.  FR-063: PipelineMonitor accepts a custom blocked_threshold parameter.
  3.  FR-063: Observation structure has required keys: type, severity, message,
              timestamp, and details.
  4.  FR-065: BLOCKED ratio detection — emits blocked_ratio_exceeded when ratio > threshold.
  5.  FR-065: BLOCKED ratio detection — no observation when ratio is at or below threshold.
  6.  FR-065: BLOCKED ratio is calculated as blocked_count / total_tasks.
  7.  FR-065: BLOCKED ratio uses 0.5 as the default threshold.
  8.  FR-065: Custom threshold is respected.
  9.  FR-065: Stale cascade detection — detects when a parent task is stale and
              its children are also stale.
  10. FR-065: Stale cascade detection — reports root cause task ID in details.
  11. FR-065: Stale cascade detection — no cascade observation when only one stale task.
  12. FR-065: Stale cascade detection — cascade observation includes all affected task IDs.
  13. FR-065: Convergence tracking — reports "converging" when completed tasks are
              increasing and blocked tasks are decreasing across check intervals.
  14. FR-065: Convergence tracking — reports "diverging" when completed tasks are
              not increasing.
  15. FR-065: Convergence tracking — reports "diverging" when blocked tasks are
              increasing.
  16. FR-065: Convergence tracking — first check with no history returns no
              convergence observation.
  17. FR-066: check() output observations contain a type field set to a known
              event type string usable for LVL writes.
  18. check() returns a list (possibly empty) of observation dicts.
  19. check() returns all observations found in one check cycle (can be multiple).
  20. Edge: empty task list produces no observations.
  21. Edge: single task BLOCKED does not trigger BLOCKED ratio (1/1 = 100%, > 50%).
  22. Edge: tasks with no dependencies do not produce stale cascade.
  23. Edge: all tasks DONE produces no BLOCKED ratio observation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from orchestrator.monitor import PipelineMonitor


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _task(
    task_id: str,
    status: str,
    parent_id: str | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    """Build a minimal task dict for monitor input."""
    t: dict[str, Any] = {"id": task_id, "status": status, "stale": stale}
    if parent_id is not None:
        t["parent_id"] = parent_id
    return t


def _make_tasks_with_blocked_ratio(total: int, blocked: int) -> list[dict[str, Any]]:
    """Return a task list where `blocked` of `total` tasks have BLOCKED status."""
    tasks = []
    for i in range(total):
        status = "BLOCKED" if i < blocked else "PENDING"
        tasks.append(_task(f"T{i+1:03d}", status))
    return tasks


# ---------------------------------------------------------------------------
# 1. Importable and instantiable
# ---------------------------------------------------------------------------


class TestPipelineMonitorInstantiation:
    """FR-063: PipelineMonitor is importable and instantiable."""

    def test_instantiable_with_defaults(self) -> None:
        """FR-063: PipelineMonitor can be created with no arguments."""
        monitor = PipelineMonitor()
        assert monitor is not None

    def test_instantiable_with_custom_threshold(self) -> None:
        """FR-063: PipelineMonitor accepts a custom blocked_threshold."""
        monitor = PipelineMonitor(blocked_threshold=0.3)
        assert monitor is not None

    def test_default_blocked_threshold_is_0_5(self) -> None:
        """FR-065: Default BLOCKED ratio threshold is 50%."""
        monitor = PipelineMonitor()
        assert monitor.blocked_threshold == 0.5

    def test_custom_blocked_threshold_stored(self) -> None:
        """FR-065: Custom threshold is stored on the instance."""
        monitor = PipelineMonitor(blocked_threshold=0.7)
        assert monitor.blocked_threshold == 0.7


# ---------------------------------------------------------------------------
# 2. check() return type contract
# ---------------------------------------------------------------------------


class TestCheckReturnType:
    """check() MUST return a list of observation dicts."""

    def test_check_returns_list(self) -> None:
        """check() always returns a list."""
        monitor = PipelineMonitor()
        result = monitor.check([])
        assert isinstance(result, list)

    def test_check_empty_tasks_returns_empty_list(self) -> None:
        """Edge: empty task list produces no observations."""
        monitor = PipelineMonitor()
        result = monitor.check([])
        assert result == []

    def test_check_all_done_returns_empty_list(self) -> None:
        """Edge: all tasks DONE produces no BLOCKED ratio observation."""
        tasks = [_task("T001", "DONE"), _task("T002", "DONE"), _task("T003", "DONE")]
        monitor = PipelineMonitor()
        result = monitor.check(tasks)
        # No BLOCKED ratio exceeded when no tasks are BLOCKED
        types = [obs["type"] for obs in result]
        assert "blocked_ratio_exceeded" not in types


# ---------------------------------------------------------------------------
# 3. Observation structure
# ---------------------------------------------------------------------------


class TestObservationStructure:
    """FR-063: Every observation emitted MUST have the required keys."""

    def _get_any_observation(self) -> dict[str, Any]:
        """Return at least one observation by triggering BLOCKED ratio."""
        # 3 BLOCKED out of 4 = 75%, triggers 0.5 threshold
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        assert len(observations) >= 1, "Expected at least one observation"
        return observations[0]

    def test_observation_has_type_key(self) -> None:
        """FR-063: Observation dict contains 'type' key."""
        obs = self._get_any_observation()
        assert "type" in obs

    def test_observation_has_severity_key(self) -> None:
        """FR-063: Observation dict contains 'severity' key."""
        obs = self._get_any_observation()
        assert "severity" in obs

    def test_observation_has_message_key(self) -> None:
        """FR-063: Observation dict contains 'message' key."""
        obs = self._get_any_observation()
        assert "message" in obs

    def test_observation_has_timestamp_key(self) -> None:
        """FR-063: Observation dict contains 'timestamp' key."""
        obs = self._get_any_observation()
        assert "timestamp" in obs

    def test_observation_has_details_key(self) -> None:
        """FR-063: Observation dict contains 'details' key."""
        obs = self._get_any_observation()
        assert "details" in obs

    def test_observation_type_is_string(self) -> None:
        """FR-063: Observation 'type' is a non-empty string."""
        obs = self._get_any_observation()
        assert isinstance(obs["type"], str)
        assert len(obs["type"]) > 0

    def test_observation_severity_is_non_empty_string(self) -> None:
        """FR-063: Observation 'severity' is a non-empty string."""
        obs = self._get_any_observation()
        assert isinstance(obs["severity"], str)
        assert len(obs["severity"]) > 0

    def test_observation_message_is_non_empty_string(self) -> None:
        """FR-063: Observation 'message' is a non-empty string."""
        obs = self._get_any_observation()
        assert isinstance(obs["message"], str)
        assert len(obs["message"]) > 0

    def test_observation_timestamp_is_string_or_datetime(self) -> None:
        """FR-063: Observation 'timestamp' is a string or datetime."""
        obs = self._get_any_observation()
        assert isinstance(obs["timestamp"], (str, datetime))

    def test_observation_details_is_dict(self) -> None:
        """FR-063: Observation 'details' is a dict."""
        obs = self._get_any_observation()
        assert isinstance(obs["details"], dict)


# ---------------------------------------------------------------------------
# 4. BLOCKED ratio detection
# ---------------------------------------------------------------------------


class TestBlockedRatioDetection:
    """FR-065: BLOCKED ratio anomaly detection."""

    def test_blocked_ratio_exceeded_emitted_when_above_threshold(self) -> None:
        """FR-065: blocked_ratio_exceeded emitted when ratio > 0.5."""
        # 3 out of 4 tasks BLOCKED = 75%
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" in types

    def test_blocked_ratio_not_emitted_when_at_threshold(self) -> None:
        """FR-065: No blocked_ratio_exceeded when ratio == threshold (not strictly greater)."""
        # 2 out of 4 tasks BLOCKED = exactly 50%
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=2)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" not in types

    def test_blocked_ratio_not_emitted_when_below_threshold(self) -> None:
        """FR-065: No blocked_ratio_exceeded when ratio < threshold."""
        # 1 out of 4 tasks BLOCKED = 25%
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=1)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" not in types

    def test_blocked_ratio_calculation_uses_all_tasks(self) -> None:
        """FR-065: Ratio denominator is total task count."""
        # 6 out of 10 = 60%, exceeds 0.5
        tasks = _make_tasks_with_blocked_ratio(total=10, blocked=6)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" in types

    def test_blocked_ratio_details_contain_ratio_value(self) -> None:
        """FR-065: blocked_ratio_exceeded observation includes the actual ratio in details."""
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        exceeded = [obs for obs in observations if obs["type"] == "blocked_ratio_exceeded"]
        assert len(exceeded) == 1
        details = exceeded[0]["details"]
        assert "ratio" in details
        assert details["ratio"] == pytest.approx(0.75)

    def test_blocked_ratio_details_contain_blocked_count(self) -> None:
        """FR-065: blocked_ratio_exceeded observation includes blocked_count in details."""
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        exceeded = [obs for obs in observations if obs["type"] == "blocked_ratio_exceeded"]
        details = exceeded[0]["details"]
        assert "blocked_count" in details
        assert details["blocked_count"] == 3

    def test_blocked_ratio_details_contain_total_count(self) -> None:
        """FR-065: blocked_ratio_exceeded observation includes total_count in details."""
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        exceeded = [obs for obs in observations if obs["type"] == "blocked_ratio_exceeded"]
        details = exceeded[0]["details"]
        assert "total_count" in details
        assert details["total_count"] == 4

    def test_single_blocked_task_triggers_ratio_when_only_task(self) -> None:
        """Edge: 1 BLOCKED out of 1 total = 100%, exceeds 0.5 threshold."""
        tasks = [_task("T001", "BLOCKED")]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" in types

    def test_custom_threshold_respected(self) -> None:
        """FR-065: Custom threshold of 0.3 triggers on 2/5 = 40% blocked."""
        # 2 out of 5 = 40%, exceeds 0.3 but not 0.5
        tasks = _make_tasks_with_blocked_ratio(total=5, blocked=2)
        monitor_default = PipelineMonitor(blocked_threshold=0.5)
        monitor_custom = PipelineMonitor(blocked_threshold=0.3)

        default_types = [obs["type"] for obs in monitor_default.check(tasks)]
        custom_types = [obs["type"] for obs in monitor_custom.check(tasks)]

        assert "blocked_ratio_exceeded" not in default_types
        assert "blocked_ratio_exceeded" in custom_types


# ---------------------------------------------------------------------------
# 5. Stale cascade detection
# ---------------------------------------------------------------------------


class TestStaleCascadeDetection:
    """FR-065: Stale cascade detection."""

    def test_stale_cascade_detected_when_parent_and_child_both_stale(self) -> None:
        """FR-065: Cascade observed when parent task is stale and child is also stale."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING", parent_id="T001", stale=True),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "stale_cascade_detected" in types

    def test_stale_cascade_not_detected_with_only_one_stale_task(self) -> None:
        """FR-065: No cascade when only one isolated stale task (no stale children)."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING"),  # not stale
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "stale_cascade_detected" not in types

    def test_stale_cascade_no_observation_when_no_stale_tasks(self) -> None:
        """Edge: No stale tasks means no stale cascade observation."""
        tasks = [
            _task("T001", "PENDING"),
            _task("T002", "PENDING", parent_id="T001"),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "stale_cascade_detected" not in types

    def test_stale_cascade_root_cause_in_details(self) -> None:
        """FR-065: stale_cascade_detected details include root_task_id."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING", parent_id="T001", stale=True),
            _task("T003", "PENDING", parent_id="T002", stale=True),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        cascade_obs = [obs for obs in observations if obs["type"] == "stale_cascade_detected"]
        assert len(cascade_obs) >= 1
        details = cascade_obs[0]["details"]
        assert "root_task_id" in details
        assert details["root_task_id"] == "T001"

    def test_stale_cascade_affected_task_ids_in_details(self) -> None:
        """FR-065: stale_cascade_detected details include affected_task_ids."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING", parent_id="T001", stale=True),
            _task("T003", "PENDING", parent_id="T001", stale=True),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        cascade_obs = [obs for obs in observations if obs["type"] == "stale_cascade_detected"]
        assert len(cascade_obs) >= 1
        details = cascade_obs[0]["details"]
        assert "affected_task_ids" in details
        affected = set(details["affected_task_ids"])
        assert "T002" in affected
        assert "T003" in affected

    def test_no_stale_cascade_when_parent_stale_but_children_not_stale(self) -> None:
        """FR-065: No cascade when parent is stale but children are fresh."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING", parent_id="T001", stale=False),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "stale_cascade_detected" not in types

    def test_no_stale_cascade_without_dependencies(self) -> None:
        """Edge: Tasks with no parent_id relationships do not produce stale cascade."""
        tasks = [
            _task("T001", "PENDING", stale=True),
            _task("T002", "PENDING", stale=True),  # stale but no dependency relationship
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "stale_cascade_detected" not in types


# ---------------------------------------------------------------------------
# 6. Convergence tracking
# ---------------------------------------------------------------------------


class TestConvergenceTracking:
    """FR-065: Convergence tracking across multiple check intervals."""

    def test_no_convergence_observation_on_first_check(self) -> None:
        """FR-065: First check with no history returns no convergence observation."""
        tasks = [
            _task("T001", "DONE"),
            _task("T002", "PENDING"),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "pipeline_converging" not in types
        assert "pipeline_diverging" not in types

    def test_converging_when_completed_increasing_and_blocked_decreasing(self) -> None:
        """FR-065: Reports 'pipeline_converging' when DONE count up and BLOCKED count down."""
        monitor = PipelineMonitor()

        # First check: 1 DONE, 2 BLOCKED, 2 PENDING
        tasks_first = [
            _task("T001", "DONE"),
            _task("T002", "BLOCKED"),
            _task("T003", "BLOCKED"),
            _task("T004", "PENDING"),
            _task("T005", "PENDING"),
        ]
        monitor.check(tasks_first)

        # Second check: 3 DONE, 0 BLOCKED, 2 PENDING — more DONE, fewer BLOCKED
        tasks_second = [
            _task("T001", "DONE"),
            _task("T002", "DONE"),
            _task("T003", "DONE"),
            _task("T004", "PENDING"),
            _task("T005", "PENDING"),
        ]
        observations = monitor.check(tasks_second)
        types = [obs["type"] for obs in observations]
        assert "pipeline_converging" in types

    def test_diverging_when_completed_not_increasing(self) -> None:
        """FR-065: Reports 'pipeline_diverging' when DONE count does not increase."""
        monitor = PipelineMonitor()

        # First check: 2 DONE
        tasks_first = [
            _task("T001", "DONE"),
            _task("T002", "DONE"),
            _task("T003", "PENDING"),
        ]
        monitor.check(tasks_first)

        # Second check: still 2 DONE (no progress)
        tasks_second = [
            _task("T001", "DONE"),
            _task("T002", "DONE"),
            _task("T003", "BLOCKED"),
        ]
        observations = monitor.check(tasks_second)
        types = [obs["type"] for obs in observations]
        assert "pipeline_diverging" in types

    def test_diverging_when_blocked_count_increasing(self) -> None:
        """FR-065: Reports 'pipeline_diverging' when BLOCKED count increases."""
        monitor = PipelineMonitor()

        # First check: 1 DONE, 0 BLOCKED
        tasks_first = [
            _task("T001", "DONE"),
            _task("T002", "PENDING"),
            _task("T003", "PENDING"),
        ]
        monitor.check(tasks_first)

        # Second check: 2 DONE but 2 BLOCKED (blocked went up)
        tasks_second = [
            _task("T001", "DONE"),
            _task("T002", "DONE"),
            _task("T003", "BLOCKED"),
            _task("T004", "BLOCKED"),
        ]
        observations = monitor.check(tasks_second)
        types = [obs["type"] for obs in observations]
        assert "pipeline_diverging" in types

    def test_convergence_observation_includes_done_count_in_details(self) -> None:
        """FR-065: Convergence observation details include current done_count."""
        monitor = PipelineMonitor()

        tasks_first = [_task("T001", "DONE"), _task("T002", "BLOCKED"), _task("T003", "PENDING")]
        monitor.check(tasks_first)

        tasks_second = [_task("T001", "DONE"), _task("T002", "DONE"), _task("T003", "DONE")]
        observations = monitor.check(tasks_second)
        converging = [obs for obs in observations if obs["type"] == "pipeline_converging"]
        assert len(converging) == 1
        details = converging[0]["details"]
        assert "done_count" in details
        assert details["done_count"] == 3

    def test_convergence_observation_includes_blocked_count_in_details(self) -> None:
        """FR-065: Convergence observation details include current blocked_count."""
        monitor = PipelineMonitor()

        tasks_first = [_task("T001", "DONE"), _task("T002", "BLOCKED"), _task("T003", "PENDING")]
        monitor.check(tasks_first)

        tasks_second = [_task("T001", "DONE"), _task("T002", "DONE"), _task("T003", "DONE")]
        observations = monitor.check(tasks_second)
        converging = [obs for obs in observations if obs["type"] == "pipeline_converging"]
        assert len(converging) == 1
        details = converging[0]["details"]
        assert "blocked_count" in details
        assert details["blocked_count"] == 0

    def test_multiple_checks_history_accumulated(self) -> None:
        """FR-065: Monitor accumulates state across multiple check() calls."""
        monitor = PipelineMonitor()

        # Three progressive checks
        monitor.check([_task("T001", "PENDING"), _task("T002", "PENDING")])
        monitor.check([_task("T001", "DONE"), _task("T002", "PENDING")])
        # Third check: improvement continues — DONE went from 1 to 2
        observations = monitor.check([_task("T001", "DONE"), _task("T002", "DONE")])

        types = [obs["type"] for obs in observations]
        assert "pipeline_converging" in types


# ---------------------------------------------------------------------------
# 7. LVL output format (FR-066)
# ---------------------------------------------------------------------------


class TestLvlOutputFormat:
    """FR-066: Observation types must be LVL-compatible event type strings."""

    def test_blocked_ratio_observation_type_is_lvl_compatible(self) -> None:
        """FR-066: blocked_ratio_exceeded type string can be used as lvl event type."""
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        exceeded = [obs for obs in observations if obs["type"] == "blocked_ratio_exceeded"]
        assert len(exceeded) == 1
        # Type must be a lowercase_underscore string (LVL compatible)
        obs_type = exceeded[0]["type"]
        assert obs_type == obs_type.lower()
        assert " " not in obs_type

    def test_all_observations_have_lvl_compatible_types(self) -> None:
        """FR-066: All observation types are lowercase snake_case (LVL compatible)."""
        tasks = [
            _task("T001", "BLOCKED"),
            _task("T002", "BLOCKED"),
            _task("T003", "BLOCKED"),
            _task("T004", "PENDING", stale=True),
            _task("T005", "PENDING", parent_id="T004", stale=True),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        for obs in observations:
            obs_type = obs["type"]
            assert obs_type == obs_type.lower(), f"Type '{obs_type}' is not lowercase"
            assert " " not in obs_type, f"Type '{obs_type}' contains spaces"

    def test_observation_severity_is_known_value(self) -> None:
        """FR-063: severity field is one of 'info', 'warning', 'error', 'critical'."""
        tasks = _make_tasks_with_blocked_ratio(total=4, blocked=3)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        valid_severities = {"info", "warning", "error", "critical"}
        for obs in observations:
            assert obs["severity"] in valid_severities, (
                f"Unexpected severity '{obs['severity']}'"
            )


# ---------------------------------------------------------------------------
# 8. check() returns all observations in one cycle (multiple observations)
# ---------------------------------------------------------------------------


class TestCheckReturnAllObservations:
    """check() MUST return ALL observations found in one cycle."""

    def test_check_can_return_multiple_observations(self) -> None:
        """check() returns a list that may contain more than one observation."""
        # Trigger both blocked_ratio_exceeded AND stale_cascade_detected
        tasks = [
            _task("T001", "BLOCKED"),
            _task("T002", "BLOCKED"),
            _task("T003", "BLOCKED"),  # 3/4 = 75% blocked, exceeds 0.5
            _task("T004", "PENDING", stale=True),
            _task("T005", "PENDING", parent_id="T004", stale=True),
        ]
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = {obs["type"] for obs in observations}
        assert "blocked_ratio_exceeded" in types
        assert "stale_cascade_detected" in types
        assert len(observations) >= 2

    def test_check_returns_only_relevant_observations(self) -> None:
        """check() does not emit observations for conditions that are not triggered."""
        # Only 1 BLOCKED out of 5 = 20%, below 0.5 threshold, no stale tasks
        tasks = _make_tasks_with_blocked_ratio(total=5, blocked=1)
        monitor = PipelineMonitor()
        observations = monitor.check(tasks)
        types = [obs["type"] for obs in observations]
        assert "blocked_ratio_exceeded" not in types
        assert "stale_cascade_detected" not in types
