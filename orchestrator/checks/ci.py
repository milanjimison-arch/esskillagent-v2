"""CI-based check strategy.

FR-013: CICheckStrategy for CI-based test execution.
FR-015: Stack scoping — filter CI jobs to task's technology stack.
FR-016: Skipped/cancelled jobs must not be treated as passing.
FR-017: Per-job error logs capped at 2000 characters.
FR-018: CI job name matching uses startswith prefix matching.
FR-045: Extensible technology registry via config.
FR-046: File classification uses both extension and path prefix.
FR-047: CI job name mapping loaded from configuration.

T015 stubs (not yet implemented):
FR-008: Complete tests_must_fail / tests_must_pass implementations.
FR-009: _commit_and_push with 3-retry logic.
FR-010: auto-detect project stack.
FR-011: configurable job name mapping.
FR-080: Python stack detection.
FR-090: async thread delegation.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.checks.base import CheckStrategy

_MAX_OUTPUT_CHARS = 2000


class CICheckStrategy(CheckStrategy):
    """CI-based check strategy with stack scoping and structured job evaluation."""

    def __init__(self, config: dict | None = None) -> None:
        self._config: dict = config or {}
        self._technology_registry: dict[str, list[str]] = self._config.get(
            "technology_registry", {}
        )

    # ------------------------------------------------------------------
    # CheckStrategy ABC — stub implementations (T015: to be completed)
    # ------------------------------------------------------------------

    def tests_must_fail(self, task_id: str, command: str) -> bool:
        """Return False — CI not triggered in unit test context (stub)."""
        return False

    def tests_must_pass(self, task_id: str, command: str) -> bool:
        """Return False — CI not triggered in unit test context (stub)."""
        return False

    # ------------------------------------------------------------------
    # evaluate() — stack-scoped job evaluation
    # ------------------------------------------------------------------

    def evaluate(self, ci_results: list[dict], stack: str | None = None) -> dict:
        """Evaluate CI job results, optionally filtered by technology stack.

        Args:
            ci_results: List of job dicts with 'name', 'status', 'output' keys.
            stack: Technology stack name to filter jobs, or None for all jobs.

        Returns:
            Dict with 'passed' (bool) and 'evaluated_jobs' (list of job dicts).
        """
        matched_jobs = self._filter_jobs(ci_results, stack)
        evaluated_jobs = [self._process_job(job) for job in matched_jobs]
        passed = all(job["status"] == "success" for job in evaluated_jobs)
        return {"passed": passed, "evaluated_jobs": evaluated_jobs}

    def _filter_jobs(
        self, ci_results: list[dict], stack: str | None
    ) -> list[dict]:
        """Filter jobs by stack using startswith prefix matching."""
        if stack is None:
            return list(ci_results)

        patterns = self._technology_registry.get(stack, [])
        if not patterns:
            return []

        return [
            job for job in ci_results
            if any(job["name"].startswith(pattern) for pattern in patterns)
        ]

    def _process_job(self, job: dict) -> dict:
        """Return a new job dict with output capped at 2000 characters."""
        output = job.get("output", "")
        return {
            "name": job["name"],
            "status": job["status"],
            "output": output[:_MAX_OUTPUT_CHARS],
        }

    # ------------------------------------------------------------------
    # T015 stubs — return minimal/empty values so tests fail on
    # AssertionError (not NotImplementedError).
    # ------------------------------------------------------------------

    def _run_ci_and_wait(self, task_id: str, command: str) -> list[dict]:
        """Trigger CI and wait for job results.

        Stub: not yet implemented. Returns empty list.
        """
        return []

    def _commit_and_push(self, message: str, files: list[str]) -> None:
        """Commit the given files and push to remote with 3-retry logic.

        Stub: not yet implemented. Does nothing.
        """
        pass

    def detect_stack(self, project_dir: Path | None = None) -> str:
        """Auto-detect the project stack from marker files.

        Stub: not yet implemented. Always returns 'unknown'.
        """
        return "unknown"

    def get_job_name_mapping(self) -> dict[str, list[str]]:
        """Return the configured CI job name mapping.

        Stub: not yet implemented. Returns empty dict.
        """
        return {}

    def tests_must_fail_async(self, task_id: str, command: str):
        """Async variant of tests_must_fail via thread delegation.

        Stub: not yet implemented. Returns None (not awaitable).
        """
        return None

    def tests_must_pass_async(self, task_id: str, command: str):
        """Async variant of tests_must_pass via thread delegation.

        Stub: not yet implemented. Returns None (not awaitable).
        """
        return None

    def run_in_thread(self, fn, *args, **kwargs):
        """Execute fn in a background thread and return a Future.

        Stub: not yet implemented. Returns None.
        """
        return None
