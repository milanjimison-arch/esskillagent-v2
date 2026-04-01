"""Unit tests for the three-way parallel review pipeline.

Feature: Three-way parallel review pipeline (code, security, brooks),
auto-fix loop on failure, and feature-gap detection with supplemental
task creation.

Test coverage areas:
  1. ReviewerResult and PipelineReviewResult data-transfer objects
  2. Three-way parallel execution (code, security, brooks run concurrently)
  3. Results aggregation from all three reviewers
  4. Overall pass when all reviewers pass
  5. Overall fail when any reviewer fails
  6. Auto-fix loop triggering on review failure
  7. Auto-fix loop respecting retry limits (does not exceed max_retries)
  8. Auto-fix loop stops as soon as all reviews pass
  9. Auto-fix loop exhaustion returns passed=False
  10. Feature-gap detection identifying missing features
  11. Supplemental task creation for detected gaps
  12. Pipeline returns overall pass/fail via PipelineReviewResult.passed
  13. Edge cases: all pass, all fail, partial failure, retry exhaustion

All tests are RED-phase — they MUST FAIL until ReviewPipeline and
its helpers are fully implemented (stubs raise NotImplementedError).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from orchestrator.review.pipeline import (
    FeatureGap,
    PipelineReviewResult,
    ReviewPipeline,
    ReviewerResult,
    run_brooks_reviewer,
    run_code_reviewer,
    run_security_reviewer,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _passing_result(reviewer: str) -> ReviewerResult:
    return ReviewerResult(
        reviewer=reviewer,
        passed=True,
        issues=(),
        verdict="pass",
    )


def _failing_result(reviewer: str, issues: tuple[str, ...] = ("issue-1",)) -> ReviewerResult:
    return ReviewerResult(
        reviewer=reviewer,
        passed=False,
        issues=issues,
        verdict="fail",
    )


def _all_passing() -> dict[str, ReviewerResult]:
    return {
        "code": _passing_result("code"),
        "security": _passing_result("security"),
        "brooks": _passing_result("brooks"),
    }


def _all_failing() -> dict[str, ReviewerResult]:
    return {
        "code": _failing_result("code"),
        "security": _failing_result("security"),
        "brooks": _failing_result("brooks"),
    }


@pytest.fixture
def pipeline() -> ReviewPipeline:
    return ReviewPipeline(max_retries=3)


@pytest.fixture
def pipeline_no_retries() -> ReviewPipeline:
    return ReviewPipeline(max_retries=0)


@pytest.fixture
def context() -> dict[str, Any]:
    return {"project_dir": "/tmp/project", "spec": "Feature spec text"}


# ---------------------------------------------------------------------------
# 1. ReviewerResult DTO
# ---------------------------------------------------------------------------


class TestReviewerResult:
    """ReviewerResult must be a frozen dataclass with expected fields."""

    def test_reviewer_result_has_reviewer_field(self):
        """ReviewerResult MUST expose a 'reviewer' field with the reviewer name."""
        result = _passing_result("code")
        assert result.reviewer == "code"

    def test_reviewer_result_has_passed_field(self):
        """ReviewerResult MUST expose a boolean 'passed' field."""
        passing = _passing_result("security")
        failing = _failing_result("security")
        assert passing.passed is True
        assert failing.passed is False

    def test_reviewer_result_has_issues_field(self):
        """ReviewerResult MUST expose an 'issues' tuple."""
        result = _failing_result("brooks", issues=("missing auth check", "unsafe eval"))
        assert "missing auth check" in result.issues
        assert "unsafe eval" in result.issues

    def test_reviewer_result_issues_is_empty_tuple_on_pass(self):
        """A passing ReviewerResult MUST have an empty issues tuple."""
        result = _passing_result("code")
        assert result.issues == ()

    def test_reviewer_result_has_verdict_field(self):
        """ReviewerResult MUST expose a 'verdict' string field."""
        result = _passing_result("code")
        assert result.verdict == "pass"

    def test_reviewer_result_is_immutable(self):
        """ReviewerResult MUST be frozen (immutable)."""
        result = _passing_result("code")
        with pytest.raises((AttributeError, TypeError)):
            result.passed = False  # type: ignore[misc]

    def test_reviewer_result_reviewer_names_are_strings(self):
        """reviewer field MUST be a non-empty string."""
        for name in ("code", "security", "brooks"):
            result = _passing_result(name)
            assert isinstance(result.reviewer, str) and result.reviewer


# ---------------------------------------------------------------------------
# 2. PipelineReviewResult DTO
# ---------------------------------------------------------------------------


class TestPipelineReviewResult:
    """PipelineReviewResult must aggregate results from all three reviewers."""

    def test_pipeline_review_result_has_passed_field(self):
        """PipelineReviewResult MUST expose a boolean 'passed' field."""
        result = PipelineReviewResult(
            passed=True,
            reviewer_results=_all_passing(),
            attempts=1,
            gaps=[],
            supplemental_tasks=[],
        )
        assert result.passed is True

    def test_pipeline_review_result_has_reviewer_results_dict(self):
        """PipelineReviewResult MUST contain a 'reviewer_results' dict keyed by reviewer name."""
        rr = _all_passing()
        result = PipelineReviewResult(
            passed=True,
            reviewer_results=rr,
            attempts=1,
            gaps=[],
            supplemental_tasks=[],
        )
        assert isinstance(result.reviewer_results, dict)
        assert "code" in result.reviewer_results
        assert "security" in result.reviewer_results
        assert "brooks" in result.reviewer_results

    def test_pipeline_review_result_has_attempts_field(self):
        """PipelineReviewResult MUST expose an 'attempts' integer field."""
        result = PipelineReviewResult(
            passed=False,
            reviewer_results=_all_failing(),
            attempts=4,
            gaps=[],
            supplemental_tasks=[],
        )
        assert result.attempts == 4

    def test_pipeline_review_result_has_gaps_list(self):
        """PipelineReviewResult MUST expose a 'gaps' list."""
        result = PipelineReviewResult(
            passed=True,
            reviewer_results=_all_passing(),
            attempts=1,
            gaps=["gap-A", "gap-B"],
            supplemental_tasks=[],
        )
        assert result.gaps == ["gap-A", "gap-B"]

    def test_pipeline_review_result_has_supplemental_tasks_list(self):
        """PipelineReviewResult MUST expose a 'supplemental_tasks' list."""
        result = PipelineReviewResult(
            passed=True,
            reviewer_results=_all_passing(),
            attempts=1,
            gaps=[],
            supplemental_tasks=["task-1", "task-2"],
        )
        assert result.supplemental_tasks == ["task-1", "task-2"]

    def test_pipeline_review_result_is_immutable(self):
        """PipelineReviewResult MUST be frozen (immutable)."""
        result = PipelineReviewResult(
            passed=True,
            reviewer_results=_all_passing(),
            attempts=1,
            gaps=[],
            supplemental_tasks=[],
        )
        with pytest.raises((AttributeError, TypeError)):
            result.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. FeatureGap DTO
# ---------------------------------------------------------------------------


class TestFeatureGap:
    """FeatureGap describes a spec-vs-implementation discrepancy."""

    def test_feature_gap_has_description_field(self):
        """FeatureGap MUST expose a 'description' string."""
        gap = FeatureGap(description="Missing rate-limiting", supplemental_task="T-099")
        assert gap.description == "Missing rate-limiting"

    def test_feature_gap_has_supplemental_task_field(self):
        """FeatureGap MUST expose a 'supplemental_task' string."""
        gap = FeatureGap(description="No logging", supplemental_task="T-100")
        assert gap.supplemental_task == "T-100"

    def test_feature_gap_is_immutable(self):
        """FeatureGap MUST be frozen."""
        gap = FeatureGap(description="gap", supplemental_task="task")
        with pytest.raises((AttributeError, TypeError)):
            gap.description = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. ReviewPipeline instantiation
# ---------------------------------------------------------------------------


class TestReviewPipelineInstantiation:
    """ReviewPipeline MUST be instantiable and expose expected attributes."""

    def test_pipeline_can_be_instantiated(self, pipeline: ReviewPipeline):
        """ReviewPipeline() MUST construct without error."""
        assert pipeline is not None

    def test_pipeline_default_max_retries(self):
        """ReviewPipeline default max_retries MUST be a positive integer."""
        p = ReviewPipeline()
        assert isinstance(p.max_retries, int)
        assert p.max_retries > 0

    def test_pipeline_custom_max_retries(self):
        """ReviewPipeline MUST accept a custom max_retries value."""
        p = ReviewPipeline(max_retries=7)
        assert p.max_retries == 7

    def test_pipeline_has_run_method(self, pipeline: ReviewPipeline):
        """ReviewPipeline MUST expose a callable 'run' method."""
        assert callable(getattr(pipeline, "run", None))

    def test_pipeline_has_run_parallel_reviews_method(self, pipeline: ReviewPipeline):
        """ReviewPipeline MUST expose a callable 'run_parallel_reviews' method."""
        assert callable(getattr(pipeline, "run_parallel_reviews", None))

    def test_pipeline_has_auto_fix_loop_method(self, pipeline: ReviewPipeline):
        """ReviewPipeline MUST expose a callable 'auto_fix_loop' method."""
        assert callable(getattr(pipeline, "auto_fix_loop", None))

    def test_pipeline_has_detect_feature_gaps_method(self, pipeline: ReviewPipeline):
        """ReviewPipeline MUST expose a callable 'detect_feature_gaps' method."""
        assert callable(getattr(pipeline, "detect_feature_gaps", None))

    def test_pipeline_has_create_supplemental_tasks_method(self, pipeline: ReviewPipeline):
        """ReviewPipeline MUST expose a callable 'create_supplemental_tasks' method."""
        assert callable(getattr(pipeline, "create_supplemental_tasks", None))


# ---------------------------------------------------------------------------
# 5. Three-way parallel review execution
# ---------------------------------------------------------------------------


class TestParallelReviewExecution:
    """The three reviewers (code, security, brooks) MUST run concurrently."""

    @pytest.mark.asyncio
    async def test_run_parallel_reviews_returns_dict_with_all_three_keys(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """run_parallel_reviews MUST return a dict with keys 'code', 'security', 'brooks'."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            results = await pipeline.run_parallel_reviews(context)

        assert "code" in results, "Expected 'code' key in reviewer results"
        assert "security" in results, "Expected 'security' key in reviewer results"
        assert "brooks" in results, "Expected 'brooks' key in reviewer results"

    @pytest.mark.asyncio
    async def test_run_parallel_reviews_all_three_reviewers_called(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """run_parallel_reviews MUST call all three reviewer functions."""
        mock_code = AsyncMock(return_value=_passing_result("code"))
        mock_security = AsyncMock(return_value=_passing_result("security"))
        mock_brooks = AsyncMock(return_value=_passing_result("brooks"))

        with (
            patch("orchestrator.review.pipeline.run_code_reviewer", mock_code),
            patch("orchestrator.review.pipeline.run_security_reviewer", mock_security),
            patch("orchestrator.review.pipeline.run_brooks_reviewer", mock_brooks),
        ):
            await pipeline.run_parallel_reviews(context)

        mock_code.assert_awaited_once()
        mock_security.assert_awaited_once()
        mock_brooks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_parallel_reviews_runs_concurrently(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """The three reviewers MUST be launched concurrently (asyncio.gather or
        equivalent), not sequentially. Verified by checking they all overlap in time."""
        call_order: list[str] = []
        start_events: dict[str, asyncio.Event] = {
            name: asyncio.Event() for name in ("code", "security", "brooks")
        }

        async def slow_reviewer(name: str, _ctx: dict[str, Any]) -> ReviewerResult:
            call_order.append(f"start:{name}")
            # Signal that this reviewer has started
            start_events[name].set()
            # Wait a tiny bit — if sequential, others won't have started yet
            await asyncio.sleep(0.01)
            call_order.append(f"end:{name}")
            return _passing_result(name)

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                side_effect=lambda ctx: slow_reviewer("code", ctx),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                side_effect=lambda ctx: slow_reviewer("security", ctx),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                side_effect=lambda ctx: slow_reviewer("brooks", ctx),
            ),
        ):
            await pipeline.run_parallel_reviews(context)

        # All three reviewers must have started before any one of them finished.
        # In a parallel run, all "start:X" entries appear before any "end:X".
        starts = [e for e in call_order if e.startswith("start:")]
        assert len(starts) == 3, "All three reviewers must start"
        # If they ran in parallel, the first end should come after all starts
        first_end_idx = next(i for i, e in enumerate(call_order) if e.startswith("end:"))
        starts_before_first_end = [
            e for e in call_order[:first_end_idx] if e.startswith("start:")
        ]
        assert len(starts_before_first_end) == 3, (
            "All three reviewers MUST start before any finishes (concurrent execution). "
            f"Execution order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_run_parallel_reviews_returns_reviewer_result_instances(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """Each value in the returned dict MUST be a ReviewerResult instance."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            results = await pipeline.run_parallel_reviews(context)

        for name, result in results.items():
            assert isinstance(result, ReviewerResult), (
                f"Expected ReviewerResult for reviewer '{name}', got {type(result)}"
            )


# ---------------------------------------------------------------------------
# 6. Results aggregation — pass/fail logic
# ---------------------------------------------------------------------------


class TestResultsAggregation:
    """The pipeline MUST aggregate all three reviewer results correctly."""

    @pytest.mark.asyncio
    async def test_pipeline_passes_when_all_three_reviewers_pass(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return passed=True when all three reviewers pass."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(context)

        assert isinstance(result, PipelineReviewResult)
        assert result.passed is True, (
            "Pipeline MUST pass when all three reviewers pass"
        )

    @pytest.mark.asyncio
    async def test_pipeline_fails_when_code_reviewer_fails(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return passed=False when the code reviewer fails (no retries)."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run(context)

        assert result.passed is False, (
            "Pipeline MUST fail when the code reviewer fails and retries are exhausted"
        )

    @pytest.mark.asyncio
    async def test_pipeline_fails_when_security_reviewer_fails(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return passed=False when the security reviewer fails (no retries)."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run(context)

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_pipeline_fails_when_brooks_reviewer_fails(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return passed=False when the brooks reviewer fails (no retries)."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run(context)

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_pipeline_fails_when_all_reviewers_fail(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return passed=False when all three reviewers fail (no retries)."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run(context)

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_pipeline_result_includes_all_three_reviewer_results(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """PipelineReviewResult.reviewer_results MUST contain entries for all three reviewers."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(context)

        assert set(result.reviewer_results.keys()) == {"code", "security", "brooks"}, (
            "reviewer_results must contain exactly 'code', 'security', and 'brooks'"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_attempts_is_one_on_first_pass(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When all reviewers pass on the first attempt, attempts MUST equal 1."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(context)

        assert result.attempts == 1, (
            f"Expected attempts=1 on immediate pass, got {result.attempts}"
        )


# ---------------------------------------------------------------------------
# 7. Auto-fix loop — triggering on failure
# ---------------------------------------------------------------------------


class TestAutoFixLoopTriggerOnFailure:
    """The auto-fix loop MUST trigger a fixer when any reviewer reports failure."""

    @pytest.mark.asyncio
    async def test_auto_fix_loop_triggers_fixer_on_single_failure(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """auto_fix_loop MUST invoke a fixer at least once when failures are provided."""
        failed_results = {"code": _failing_result("code")}

        with patch.object(
            pipeline, "_apply_fix", new_callable=AsyncMock
        ) as mock_fixer:
            mock_fixer.return_value = None
            # After fix, the re-review should pass
            with patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ):
                await pipeline.auto_fix_loop(context, failed_results)

        mock_fixer.assert_awaited()

    @pytest.mark.asyncio
    async def test_run_triggers_auto_fix_loop_on_initial_failure(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When run_parallel_reviews returns failures, run() MUST call auto_fix_loop."""
        first_call = True

        async def code_reviewer_side_effect(ctx: dict[str, Any]) -> ReviewerResult:
            nonlocal first_call
            if first_call:
                first_call = False
                return _failing_result("code")
            return _passing_result("code")

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                side_effect=code_reviewer_side_effect,
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock) as mock_fix,
        ):
            result = await pipeline.run(context)

        mock_fix.assert_awaited()

    @pytest.mark.asyncio
    async def test_auto_fix_loop_re_runs_failed_reviewers(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """auto_fix_loop MUST re-run the reviewers that initially failed."""
        mock_code = AsyncMock(return_value=_passing_result("code"))
        failed_results = {"code": _failing_result("code")}

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                mock_code,
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock),
        ):
            await pipeline.auto_fix_loop(context, failed_results)

        mock_code.assert_awaited()

    @pytest.mark.asyncio
    async def test_auto_fix_loop_does_not_re_run_passing_reviewers(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """auto_fix_loop MUST NOT re-run reviewers that already passed."""
        mock_brooks = AsyncMock(return_value=_passing_result("brooks"))
        failed_results = {"code": _failing_result("code")}

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                mock_brooks,
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock),
        ):
            await pipeline.auto_fix_loop(context, failed_results)

        mock_brooks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auto_fix_loop_returns_updated_results_dict(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """auto_fix_loop MUST return a dict of ReviewerResult after re-review."""
        failed_results = {"code": _failing_result("code")}

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock),
        ):
            updated = await pipeline.auto_fix_loop(context, failed_results)

        assert isinstance(updated, dict), "auto_fix_loop MUST return a dict"
        assert "code" in updated
        assert isinstance(updated["code"], ReviewerResult)


# ---------------------------------------------------------------------------
# 8. Auto-fix loop — retry limit enforcement
# ---------------------------------------------------------------------------


class TestAutoFixLoopRetryLimit:
    """The auto-fix loop MUST respect the configured max_retries."""

    @pytest.mark.asyncio
    async def test_auto_fix_loop_stops_after_max_retries(self, context: dict[str, Any]):
        """The fix loop MUST stop after max_retries even if reviews still fail."""
        pipeline = ReviewPipeline(max_retries=2)
        fixer_call_count = 0

        async def always_fails(ctx: dict[str, Any]) -> ReviewerResult:
            return _failing_result("code")

        async def counting_fixer(ctx: dict[str, Any], failures: dict) -> None:
            nonlocal fixer_call_count
            fixer_call_count += 1

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                side_effect=always_fails,
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(
                pipeline,
                "_apply_fix",
                side_effect=lambda ctx, failures: counting_fixer(ctx, failures),
            ),
        ):
            result = await pipeline.run(context)

        assert result.passed is False, (
            "Pipeline MUST return passed=False when max_retries are exhausted"
        )
        assert fixer_call_count <= pipeline.max_retries, (
            f"Fixer MUST NOT be called more than max_retries={pipeline.max_retries} times, "
            f"but was called {fixer_call_count} times"
        )

    @pytest.mark.asyncio
    async def test_auto_fix_loop_does_not_fix_when_max_retries_is_zero(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """When max_retries=0, the fixer MUST never be called."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(
                pipeline_no_retries, "_apply_fix", new_callable=AsyncMock
            ) as mock_fix,
        ):
            result = await pipeline_no_retries.run(context)

        mock_fix.assert_not_awaited()
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_pipeline_attempts_reflects_total_review_rounds(
        self, context: dict[str, Any]
    ):
        """PipelineReviewResult.attempts MUST count the total number of review rounds."""
        pipeline = ReviewPipeline(max_retries=2)
        call_count = 0

        async def fails_twice_then_passes(ctx: dict[str, Any]) -> ReviewerResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return _failing_result("code")
            return _passing_result("code")

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                side_effect=fails_twice_then_passes,
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock),
        ):
            result = await pipeline.run(context)

        assert result.passed is True
        assert result.attempts == 3, (
            f"Expected attempts=3 (failed twice, passed on third), got {result.attempts}"
        )


# ---------------------------------------------------------------------------
# 9. Auto-fix loop — stops when all reviews pass
# ---------------------------------------------------------------------------


class TestAutoFixLoopStopsOnPass:
    """The auto-fix loop MUST stop as soon as all reviewers pass."""

    @pytest.mark.asyncio
    async def test_auto_fix_loop_stops_after_first_successful_fix(
        self, context: dict[str, Any]
    ):
        """Once all reviewers pass after a fix, no further fixes MUST be applied."""
        pipeline = ReviewPipeline(max_retries=5)
        fixer_call_count = 0
        code_call_count = 0

        async def code_reviewer(ctx: dict[str, Any]) -> ReviewerResult:
            nonlocal code_call_count
            code_call_count += 1
            if code_call_count == 1:
                return _failing_result("code")
            return _passing_result("code")

        async def counting_fixer(ctx: dict[str, Any], failures: dict) -> None:
            nonlocal fixer_call_count
            fixer_call_count += 1

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                side_effect=code_reviewer,
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(
                pipeline,
                "_apply_fix",
                side_effect=lambda ctx, failures: counting_fixer(ctx, failures),
            ),
        ):
            result = await pipeline.run(context)

        assert result.passed is True
        assert fixer_call_count == 1, (
            f"Fixer MUST only be called once (pass after first fix), "
            f"but was called {fixer_call_count} times"
        )


# ---------------------------------------------------------------------------
# 10. Feature-gap detection
# ---------------------------------------------------------------------------


class TestFeatureGapDetection:
    """detect_feature_gaps MUST identify missing features between spec and implementation."""

    @pytest.mark.asyncio
    async def test_detect_feature_gaps_returns_list_of_feature_gaps(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """detect_feature_gaps MUST return a list of FeatureGap instances."""
        ctx_with_gaps = {
            **context,
            "spec_features": ["auth", "rate-limiting", "logging"],
            "implemented_features": ["auth"],
        }
        gaps = await pipeline.detect_feature_gaps(ctx_with_gaps)

        assert isinstance(gaps, list), f"Expected list, got {type(gaps)}"
        for gap in gaps:
            assert isinstance(gap, FeatureGap), (
                f"Each gap MUST be a FeatureGap instance, got {type(gap)}"
            )

    @pytest.mark.asyncio
    async def test_detect_feature_gaps_returns_empty_list_when_no_gaps(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """detect_feature_gaps MUST return an empty list when spec and implementation match."""
        ctx_no_gaps = {
            **context,
            "spec_features": ["auth", "rate-limiting"],
            "implemented_features": ["auth", "rate-limiting"],
        }
        gaps = await pipeline.detect_feature_gaps(ctx_no_gaps)

        assert gaps == [], (
            f"Expected empty list when all features are implemented, got {gaps}"
        )

    @pytest.mark.asyncio
    async def test_detect_feature_gaps_identifies_missing_features(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """detect_feature_gaps MUST return a FeatureGap for each missing feature."""
        ctx = {
            **context,
            "spec_features": ["auth", "rate-limiting", "logging"],
            "implemented_features": ["auth"],
        }
        gaps = await pipeline.detect_feature_gaps(ctx)

        gap_descriptions = [g.description for g in gaps]
        assert any("rate-limiting" in d for d in gap_descriptions), (
            "Expected a gap for 'rate-limiting'"
        )
        assert any("logging" in d for d in gap_descriptions), (
            "Expected a gap for 'logging'"
        )

    @pytest.mark.asyncio
    async def test_detect_feature_gaps_does_not_report_implemented_features(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """detect_feature_gaps MUST NOT report features that are already implemented."""
        ctx = {
            **context,
            "spec_features": ["auth", "rate-limiting"],
            "implemented_features": ["auth"],
        }
        gaps = await pipeline.detect_feature_gaps(ctx)

        gap_descriptions = [g.description for g in gaps]
        assert not any("auth" in d for d in gap_descriptions), (
            "Must NOT report 'auth' as a gap since it is implemented"
        )

    @pytest.mark.asyncio
    async def test_each_feature_gap_has_a_supplemental_task(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """Each FeatureGap MUST carry a non-empty supplemental_task string."""
        ctx = {
            **context,
            "spec_features": ["auth", "rate-limiting", "logging"],
            "implemented_features": ["auth"],
        }
        gaps = await pipeline.detect_feature_gaps(ctx)

        for gap in gaps:
            assert isinstance(gap.supplemental_task, str) and gap.supplemental_task.strip(), (
                f"FeatureGap '{gap.description}' MUST have a non-empty supplemental_task"
            )


# ---------------------------------------------------------------------------
# 11. Supplemental task creation
# ---------------------------------------------------------------------------


class TestSupplementalTaskCreation:
    """create_supplemental_tasks MUST produce one task string per FeatureGap."""

    @pytest.mark.asyncio
    async def test_create_supplemental_tasks_returns_list_of_strings(
        self, pipeline: ReviewPipeline
    ):
        """create_supplemental_tasks MUST return a list of strings."""
        gaps = [
            FeatureGap(description="Missing rate-limiting", supplemental_task="T-001"),
            FeatureGap(description="Missing logging", supplemental_task="T-002"),
        ]
        tasks = await pipeline.create_supplemental_tasks(gaps)

        assert isinstance(tasks, list), f"Expected list, got {type(tasks)}"
        for task in tasks:
            assert isinstance(task, str), f"Each task MUST be a string, got {type(task)}"

    @pytest.mark.asyncio
    async def test_create_supplemental_tasks_returns_empty_list_for_no_gaps(
        self, pipeline: ReviewPipeline
    ):
        """create_supplemental_tasks with no gaps MUST return an empty list."""
        tasks = await pipeline.create_supplemental_tasks([])
        assert tasks == [], f"Expected [], got {tasks}"

    @pytest.mark.asyncio
    async def test_create_supplemental_tasks_one_task_per_gap(
        self, pipeline: ReviewPipeline
    ):
        """create_supplemental_tasks MUST produce exactly one task per FeatureGap."""
        gaps = [
            FeatureGap(description="Gap A", supplemental_task="T-010"),
            FeatureGap(description="Gap B", supplemental_task="T-011"),
            FeatureGap(description="Gap C", supplemental_task="T-012"),
        ]
        tasks = await pipeline.create_supplemental_tasks(gaps)

        assert len(tasks) == 3, (
            f"Expected 3 tasks for 3 gaps, got {len(tasks)}"
        )

    @pytest.mark.asyncio
    async def test_create_supplemental_tasks_all_tasks_are_non_empty(
        self, pipeline: ReviewPipeline
    ):
        """Each created task string MUST be non-empty."""
        gaps = [
            FeatureGap(description="Missing auth", supplemental_task="T-020"),
        ]
        tasks = await pipeline.create_supplemental_tasks(gaps)

        for task in tasks:
            assert task.strip(), "Each supplemental task string MUST be non-empty"

    @pytest.mark.asyncio
    async def test_pipeline_run_includes_supplemental_tasks_in_result(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When gaps are detected, pipeline.run() MUST populate supplemental_tasks
        in the PipelineReviewResult."""
        ctx = {
            **context,
            "spec_features": ["auth", "rate-limiting"],
            "implemented_features": ["auth"],
        }

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(ctx)

        assert isinstance(result.supplemental_tasks, list)
        assert len(result.supplemental_tasks) >= 1, (
            "run() MUST include at least one supplemental task when gaps exist"
        )

    @pytest.mark.asyncio
    async def test_pipeline_run_includes_gaps_in_result(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When gaps are detected, pipeline.run() MUST populate gaps in the result."""
        ctx = {
            **context,
            "spec_features": ["auth", "rate-limiting"],
            "implemented_features": ["auth"],
        }

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(ctx)

        assert isinstance(result.gaps, list)
        assert len(result.gaps) >= 1, (
            "run() MUST include at least one gap description when gaps exist"
        )

    @pytest.mark.asyncio
    async def test_pipeline_run_has_empty_gaps_when_fully_implemented(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When spec and implementation match, run() MUST return empty gaps and tasks."""
        ctx = {
            **context,
            "spec_features": ["auth"],
            "implemented_features": ["auth"],
        }

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(ctx)

        assert result.gaps == [], (
            f"Expected no gaps when all features are implemented, got {result.gaps}"
        )
        assert result.supplemental_tasks == [], (
            "Expected no supplemental tasks when implementation is complete"
        )


# ---------------------------------------------------------------------------
# 12. PipelineReviewResult — overall pass/fail
# ---------------------------------------------------------------------------


class TestPipelineOverallPassFail:
    """run() MUST return a PipelineReviewResult with correct passed field."""

    @pytest.mark.asyncio
    async def test_run_returns_pipeline_review_result(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """run() MUST return a PipelineReviewResult instance."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(context)

        assert isinstance(result, PipelineReviewResult), (
            f"run() MUST return PipelineReviewResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_run_passed_is_bool(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """PipelineReviewResult.passed MUST be a boolean."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline.run(context)

        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_partial_failure_returns_passed_false(
        self, pipeline_no_retries: ReviewPipeline, context: dict[str, Any]
    ):
        """Even a single failing reviewer (partial failure) MUST produce passed=False."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run(context)

        assert result.passed is False, (
            "Partial failure (one of three fails) MUST produce passed=False"
        )


# ---------------------------------------------------------------------------
# 13. Module-level reviewer callables
# ---------------------------------------------------------------------------


class TestModuleLevelReviewers:
    """The three reviewer coroutine functions MUST be importable and async."""

    def test_run_code_reviewer_is_callable(self):
        """run_code_reviewer MUST be a callable."""
        assert callable(run_code_reviewer)

    def test_run_security_reviewer_is_callable(self):
        """run_security_reviewer MUST be a callable."""
        assert callable(run_security_reviewer)

    def test_run_brooks_reviewer_is_callable(self):
        """run_brooks_reviewer MUST be a callable."""
        assert callable(run_brooks_reviewer)

    @pytest.mark.asyncio
    async def test_run_code_reviewer_returns_reviewer_result_when_implemented(
        self, context: dict[str, Any]
    ):
        """run_code_reviewer MUST return a ReviewerResult (not raise once implemented).
        Currently expected to raise NotImplementedError (RED state)."""
        with pytest.raises(NotImplementedError):
            await run_code_reviewer(context)

    @pytest.mark.asyncio
    async def test_run_security_reviewer_returns_reviewer_result_when_implemented(
        self, context: dict[str, Any]
    ):
        """run_security_reviewer MUST return a ReviewerResult (not raise once implemented).
        Currently expected to raise NotImplementedError (RED state)."""
        with pytest.raises(NotImplementedError):
            await run_security_reviewer(context)

    @pytest.mark.asyncio
    async def test_run_brooks_reviewer_returns_reviewer_result_when_implemented(
        self, context: dict[str, Any]
    ):
        """run_brooks_reviewer MUST return a ReviewerResult (not raise once implemented).
        Currently expected to raise NotImplementedError (RED state)."""
        with pytest.raises(NotImplementedError):
            await run_brooks_reviewer(context)


# ---------------------------------------------------------------------------
# 14. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty context, retry exhaustion, all combinations."""

    @pytest.mark.asyncio
    async def test_run_with_empty_context_does_not_raise(
        self, pipeline_no_retries: ReviewPipeline
    ):
        """run() MUST not raise when context is an empty dict."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
        ):
            result = await pipeline_no_retries.run({})

        assert isinstance(result, PipelineReviewResult)

    @pytest.mark.asyncio
    async def test_retry_exhaustion_sets_passed_false_and_max_attempts(
        self, context: dict[str, Any]
    ):
        """After retries are exhausted, passed MUST be False and
        attempts MUST equal max_retries + 1."""
        pipeline = ReviewPipeline(max_retries=2)

        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_failing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock),
        ):
            result = await pipeline.run(context)

        assert result.passed is False
        assert result.attempts == pipeline.max_retries + 1, (
            f"Expected attempts={pipeline.max_retries + 1} after retry exhaustion, "
            f"got {result.attempts}"
        )

    @pytest.mark.asyncio
    async def test_all_reviewers_pass_immediately_no_fix_called(
        self, pipeline: ReviewPipeline, context: dict[str, Any]
    ):
        """When all reviewers pass on the first attempt, _apply_fix MUST NOT be called."""
        with (
            patch(
                "orchestrator.review.pipeline.run_code_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("code"),
            ),
            patch(
                "orchestrator.review.pipeline.run_security_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("security"),
            ),
            patch(
                "orchestrator.review.pipeline.run_brooks_reviewer",
                new_callable=AsyncMock,
                return_value=_passing_result("brooks"),
            ),
            patch.object(pipeline, "_apply_fix", new_callable=AsyncMock) as mock_fix,
        ):
            result = await pipeline.run(context)

        mock_fix.assert_not_awaited()
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_large_number_of_gaps_all_get_supplemental_tasks(
        self, pipeline: ReviewPipeline
    ):
        """create_supplemental_tasks MUST handle a large number of gaps without errors."""
        gaps = [
            FeatureGap(description=f"Gap {i}", supplemental_task=f"T-{i:03d}")
            for i in range(50)
        ]
        tasks = await pipeline.create_supplemental_tasks(gaps)

        assert len(tasks) == 50, (
            f"Expected 50 tasks for 50 gaps, got {len(tasks)}"
        )
