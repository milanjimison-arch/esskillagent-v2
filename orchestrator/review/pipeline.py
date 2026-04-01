"""Review pipeline implementation.

Three-way parallel review pipeline (code, security, brooks),
auto-fix loop on failure, and feature-gap detection with supplemental
task creation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewerResult:
    """Result returned by a single reviewer."""

    reviewer: str
    passed: bool
    issues: tuple[str, ...]
    verdict: str


@dataclass(frozen=True)
class PipelineReviewResult:
    """Aggregated result from all three parallel reviewers."""

    passed: bool
    reviewer_results: dict[str, ReviewerResult]
    attempts: int
    gaps: list[str]
    supplemental_tasks: list[str]


@dataclass(frozen=True)
class FeatureGap:
    """A single detected gap between spec and implementation."""

    description: str
    supplemental_task: str


# ---------------------------------------------------------------------------
# Reviewer callables (stubs — kept as NotImplementedError per test contract)
# ---------------------------------------------------------------------------


async def run_code_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the code quality reviewer."""
    raise NotImplementedError("run_code_reviewer not implemented")


async def run_security_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the security reviewer."""
    raise NotImplementedError("run_security_reviewer not implemented")


async def run_brooks_reviewer(context: dict[str, Any]) -> ReviewerResult:
    """Run the Brooks (architectural/design) reviewer."""
    raise NotImplementedError("run_brooks_reviewer not implemented")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _invoke_reviewer(
    fn: Callable[..., Any], context: dict[str, Any]
) -> ReviewerResult:
    """Call a reviewer function and unwrap nested coroutines (mock compatibility).

    When tests patch reviewer functions using side_effect that returns a
    coroutine, AsyncMock returns the inner coroutine as the value rather than
    running it.  This wrapper detects and awaits such nested coroutines.
    """
    result = await fn(context)
    if asyncio.iscoroutine(result):
        result = await result
    return result


def _get_reviewer_map() -> dict[str, Callable[..., Any]]:
    """Return current module-level reviewer functions (resolved at call time)."""
    return {
        "code": run_code_reviewer,
        "security": run_security_reviewer,
        "brooks": run_brooks_reviewer,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class ReviewPipeline:
    """Three-way parallel review pipeline with auto-fix loop and gap detection."""

    DEFAULT_MAX_RETRIES: int = 3

    def __init__(self, *, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        self.max_retries = max_retries

    async def run(self, context: dict[str, Any]) -> PipelineReviewResult:
        """Execute the full review pipeline."""
        reviewer_results = await self.run_parallel_reviews(context)
        attempts = 1

        failed = {k: v for k, v in reviewer_results.items() if not v.passed}

        if failed and self.max_retries > 0:
            fixed_results, retry_count = await self._auto_fix_loop_with_count(
                context, failed
            )
            reviewer_results = {**reviewer_results, **fixed_results}
            attempts += retry_count

        gaps = await self.detect_feature_gaps(context)
        supplemental_tasks = await self.create_supplemental_tasks(gaps)
        all_passed = all(r.passed for r in reviewer_results.values())

        return PipelineReviewResult(
            passed=all_passed,
            reviewer_results=reviewer_results,
            attempts=attempts,
            gaps=[g.description for g in gaps],
            supplemental_tasks=supplemental_tasks,
        )

    async def run_parallel_reviews(
        self, context: dict[str, Any]
    ) -> dict[str, ReviewerResult]:
        """Run all three reviewers concurrently and return their results."""
        code_result, security_result, brooks_result = await asyncio.gather(
            _invoke_reviewer(run_code_reviewer, context),
            _invoke_reviewer(run_security_reviewer, context),
            _invoke_reviewer(run_brooks_reviewer, context),
        )
        return {
            "code": code_result,
            "security": security_result,
            "brooks": brooks_result,
        }

    async def auto_fix_loop(
        self,
        context: dict[str, Any],
        failed_results: dict[str, ReviewerResult],
    ) -> dict[str, ReviewerResult]:
        """Trigger fixer and re-run failed reviewers until pass or retry limit."""
        updated, _ = await self._auto_fix_loop_with_count(context, failed_results)
        return updated

    async def _auto_fix_loop_with_count(
        self,
        context: dict[str, Any],
        failed_results: dict[str, ReviewerResult],
    ) -> tuple[dict[str, ReviewerResult], int]:
        """Internal: run fix loop and return (updated_results, retry_count)."""
        still_failed = dict(failed_results)
        all_updated: dict[str, ReviewerResult] = {}
        retry_count = 0

        for _ in range(self.max_retries):
            fix_result = await self._apply_fix(context, still_failed)
            if asyncio.iscoroutine(fix_result):
                await fix_result
            retry_count += 1

            re_run_results = await self._rerun_reviewers(context, still_failed)
            all_updated.update(re_run_results)

            still_failed = {k: v for k, v in re_run_results.items() if not v.passed}
            if not still_failed:
                break

        return all_updated, retry_count

    async def _rerun_reviewers(
        self,
        context: dict[str, Any],
        failed_results: dict[str, ReviewerResult],
    ) -> dict[str, ReviewerResult]:
        """Re-run only the reviewers listed in failed_results."""
        reviewer_map = _get_reviewer_map()
        keys = list(failed_results.keys())
        fns = [reviewer_map[k] for k in keys]
        results = await asyncio.gather(
            *[_invoke_reviewer(fn, context) for fn in fns]
        )
        return dict(zip(keys, results))

    async def _apply_fix(
        self,
        context: dict[str, Any],
        failures: dict[str, ReviewerResult],
    ) -> None:
        """Placeholder for triggering the actual fixer agent."""

    async def detect_feature_gaps(
        self, context: dict[str, Any]
    ) -> list[FeatureGap]:
        """Detect gaps between spec and implementation."""
        spec_features = context.get("spec_features", [])
        implemented_features = set(context.get("implemented_features", []))

        gaps = []
        for feature in spec_features:
            if feature not in implemented_features:
                gaps.append(
                    FeatureGap(
                        description=f"Missing feature: {feature}",
                        supplemental_task=f"Implement missing feature: {feature}",
                    )
                )
        return gaps

    async def create_supplemental_tasks(
        self, gaps: list[FeatureGap]
    ) -> list[str]:
        """Create supplemental tasks for each detected feature gap."""
        return [gap.supplemental_task for gap in gaps]
