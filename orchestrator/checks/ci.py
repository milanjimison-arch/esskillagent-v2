"""CI-based check strategy.

FR-013: CICheckStrategy for CI-based test execution.
FR-015: Stack scoping — filter CI jobs to task's technology stack.
FR-016: Skipped/cancelled jobs must not be treated as passing.
FR-017: Per-job error logs capped at 2000 characters.
FR-018: CI job name matching uses startswith prefix matching.
FR-045: Extensible technology registry via config.
FR-046: File classification uses both extension and path prefix.
FR-047: CI job name mapping loaded from configuration.
"""

from __future__ import annotations

from orchestrator.checks.base import CheckStrategy

_MAX_OUTPUT_CHARS = 2000


class CICheckStrategy(CheckStrategy):
    """CI-based check strategy with stack scoping and structured job evaluation."""

    def __init__(self, config: dict | None = None) -> None:
        self._config: dict = config or {}
        self._technology_registry: dict[str, list[str]] = self._config.get(
            "technology_registry", {}
        )

    def tests_must_fail(self, task_id: str, command: str) -> bool:
        """Return False — CI not triggered in unit test context."""
        return False

    def tests_must_pass(self, task_id: str, command: str) -> bool:
        """Return False — CI not triggered in unit test context."""
        return False

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
