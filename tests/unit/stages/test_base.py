"""Unit tests for StageABC — Stage abstract base class.

FR-004: Stage MUST implement a review gate: the stage is only marked complete
        once the review gate passes.
FR-002: A checkpoint MUST be persisted to the store after a stage completes
        successfully.
SPEC-060: Auto-fix retry loop MUST retry up to max_retries times before
          marking the stage as failed.
SPEC-091: On review failure the auto-fix callback is invoked before the next
          review attempt.

All tests in this module are RED-phase tests -- they MUST FAIL until
orchestrator/stages/base.py provides concrete implementations of StageABC,
StageResult, and ReviewOutcome.

Test coverage areas:
    1.  StageABC is an ABC with required abstract methods.
    2.  StageResult stores passed/attempts/data/error and is immutable.
    3.  ReviewOutcome stores passed/issues/verdict and is immutable.
    4.  execute_with_gate: single-pass review gate (review passes first time).
    5.  execute_with_gate: persists checkpoint exactly once on success.
    6.  execute_with_gate: does NOT persist checkpoint on failure.
    7.  execute_with_gate: calls _do_fix when review fails.
    8.  execute_with_gate: retries up to max_retries and then returns failure.
    9.  execute_with_gate: succeeds after one failed + one passed review.
    10. execute_with_gate: passes review-outcome issues to _do_fix.
    11. execute_with_gate: increments attempts counter on each review.
    12. Concrete subclass instantiation enforces all abstract methods.
    13. _persist_checkpoint is invoked with the data returned by run().
    14. Edge cases: max_retries=0, empty issues tuple, zero attempts.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_passing_outcome() -> ReviewOutcome:
    """Return a ReviewOutcome that represents a passing review gate."""
    return ReviewOutcome(passed=True, issues=(), verdict="pass")


def _make_failing_outcome(issues: tuple[str, ...] = ("issue-1",)) -> ReviewOutcome:
    """Return a ReviewOutcome that represents a failing review gate."""
    return ReviewOutcome(passed=False, issues=issues, verdict="fail")


def _make_result(passed: bool = True, attempts: int = 1, data: dict | None = None) -> StageResult:
    """Return a StageResult."""
    return StageResult(passed=passed, attempts=attempts, data=data or {}, error=None)


# ---------------------------------------------------------------------------
# Concrete test double -- builds a minimal valid subclass for behaviour tests
# ---------------------------------------------------------------------------


def _build_concrete_stage(
    *,
    run_data: dict | None = None,
    review_outcomes: list[ReviewOutcome] | None = None,
    max_retries: int = 3,
    store: Any = None,
) -> "StageABC":
    """Return a concrete StageABC subclass pre-wired with mocked collaborators.

    Parameters
    ----------
    run_data:
        The dict that `run()` yields as stage output.
    review_outcomes:
        Ordered list of ReviewOutcome objects; each call to _do_review()
        pops and returns the next one. Defaults to [passing outcome].
    max_retries:
        Maximum fix attempts before hard failure.
    store:
        Optional mock store injected into the stage for checkpoint assertions.
    """
    outcomes = list(review_outcomes or [_make_passing_outcome()])
    stage_data = run_data or {"artifact": "spec.md"}

    class _ConcreteStage(StageABC):
        def __init__(self):
            self.max_retries = max_retries
            self._store = store or MagicMock()
            self._fix_call_args: list[ReviewOutcome] = []

        async def run(self) -> StageResult:
            return StageResult(passed=True, attempts=1, data=stage_data)

        async def _do_review(self) -> ReviewOutcome:
            if not outcomes:
                return _make_passing_outcome()
            return outcomes.pop(0)

        async def _do_fix(self, outcome: ReviewOutcome) -> None:
            self._fix_call_args.append(outcome)

        async def _persist_checkpoint(self, data: dict) -> None:
            self._store.save_checkpoint(data)

    return _ConcreteStage()


# ---------------------------------------------------------------------------
# 1. StageABC is an ABC with the required abstract methods
# ---------------------------------------------------------------------------


class TestStageABCIsABC:
    """FR-004: StageABC MUST be an abstract base class."""

    def test_stage_abc_inherits_from_abc(self):
        """StageABC must subclass abc.ABC."""
        import abc
        assert issubclass(StageABC, abc.ABC), "StageABC must subclass abc.ABC"

    def test_stage_abc_cannot_be_instantiated_directly(self):
        """Attempting to instantiate StageABC directly MUST raise TypeError."""
        with pytest.raises(TypeError):
            StageABC()  # type: ignore[abstract]

    def test_stage_abc_is_a_class(self):
        """StageABC must be a class, not a function or module."""
        assert inspect.isclass(StageABC)

    def test_run_is_abstract(self):
        """run() MUST be declared as an abstract method."""
        assert "run" in StageABC.__abstractmethods__, (
            "run must be listed in StageABC.__abstractmethods__"
        )

    def test_do_review_is_abstract(self):
        """_do_review() MUST be declared as an abstract method."""
        assert "_do_review" in StageABC.__abstractmethods__, (
            "_do_review must be listed in StageABC.__abstractmethods__"
        )

    def test_do_fix_is_abstract(self):
        """_do_fix() MUST be declared as an abstract method."""
        assert "_do_fix" in StageABC.__abstractmethods__, (
            "_do_fix must be listed in StageABC.__abstractmethods__"
        )

    def test_abstractmethods_contains_exactly_required_methods(self):
        """StageABC.__abstractmethods__ must contain exactly run, _do_review,
        and _do_fix (the three mandatory overrides)."""
        expected = {"run", "_do_review", "_do_fix"}
        declared = set(StageABC.__abstractmethods__)
        assert expected == declared, (
            f"Expected abstract methods {expected}, got {declared}"
        )

    def test_execute_with_gate_is_not_abstract(self):
        """execute_with_gate is the shared template method and must NOT be abstract
        (it is a concrete method defined on StageABC)."""
        assert "execute_with_gate" not in StageABC.__abstractmethods__

    def test_persist_checkpoint_is_not_abstract(self):
        """_persist_checkpoint is overridable but ships with a concrete default
        in StageABC, so it must NOT be listed as abstract."""
        assert "_persist_checkpoint" not in StageABC.__abstractmethods__


class TestStageABCConcreteSubclassInstantiation:
    """Concrete subclass enforcement at instantiation time."""

    def test_subclass_missing_run_cannot_be_instantiated(self):
        """A subclass that omits run() MUST still raise TypeError."""

        class _Partial(StageABC):
            async def _do_review(self) -> ReviewOutcome:
                return _make_passing_outcome()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                pass

        with pytest.raises(TypeError):
            _Partial()

    def test_subclass_missing_do_review_cannot_be_instantiated(self):
        """A subclass that omits _do_review() MUST raise TypeError."""

        class _Partial(StageABC):
            async def run(self) -> StageResult:
                return _make_result()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                pass

        with pytest.raises(TypeError):
            _Partial()

    def test_subclass_missing_do_fix_cannot_be_instantiated(self):
        """A subclass that omits _do_fix() MUST raise TypeError."""

        class _Partial(StageABC):
            async def run(self) -> StageResult:
                return _make_result()

            async def _do_review(self) -> ReviewOutcome:
                return _make_passing_outcome()

        with pytest.raises(TypeError):
            _Partial()

    def test_complete_subclass_can_be_instantiated(self):
        """A subclass implementing all three abstract methods MUST instantiate
        without raising TypeError."""
        stage = _build_concrete_stage()
        assert stage is not None
        assert isinstance(stage, StageABC)


class TestStageABCMethodSignatures:
    """Abstract methods must carry the expected callable signatures."""

    def test_run_is_callable(self):
        assert callable(StageABC.run)

    def test_do_review_is_callable(self):
        assert callable(StageABC._do_review)

    def test_do_fix_is_callable(self):
        assert callable(StageABC._do_fix)

    def test_do_fix_accepts_outcome_parameter(self):
        """_do_fix must accept an 'outcome' parameter."""
        sig = inspect.signature(StageABC._do_fix)
        assert "outcome" in sig.parameters, (
            "_do_fix must accept an 'outcome' parameter"
        )

    def test_execute_with_gate_is_callable(self):
        assert callable(StageABC.execute_with_gate)

    def test_persist_checkpoint_accepts_data_parameter(self):
        """_persist_checkpoint must accept a 'data' parameter."""
        sig = inspect.signature(StageABC._persist_checkpoint)
        assert "data" in sig.parameters, (
            "_persist_checkpoint must accept a 'data' parameter"
        )


# ---------------------------------------------------------------------------
# 2. StageResult stores fields and is immutable
# ---------------------------------------------------------------------------


class TestStageResult:
    """StageResult is the return type of execute_with_gate()."""

    def test_stage_result_passed_field_true(self):
        """StageResult MUST expose a 'passed' bool field."""
        result = StageResult(passed=True, attempts=1, data={}, error=None)
        assert result.passed is True

    def test_stage_result_passed_field_false(self):
        result = StageResult(passed=False, attempts=2, data={}, error="review failed")
        assert result.passed is False

    def test_stage_result_attempts_field(self):
        """StageResult MUST expose an 'attempts' int field."""
        result = StageResult(passed=True, attempts=3, data={}, error=None)
        assert result.attempts == 3

    def test_stage_result_data_field(self):
        """StageResult MUST expose a 'data' dict field."""
        payload = {"artifact": "spec.md", "token_count": 1200}
        result = StageResult(passed=True, attempts=1, data=payload, error=None)
        assert result.data == payload

    def test_stage_result_error_field_none_on_success(self):
        """error MUST be None when passed=True."""
        result = StageResult(passed=True, attempts=1, data={}, error=None)
        assert result.error is None

    def test_stage_result_error_field_set_on_failure(self):
        """error MUST carry the failure message when passed=False."""
        result = StageResult(
            passed=False, attempts=3, data={}, error="max retries exhausted"
        )
        assert result.error == "max retries exhausted"

    def test_stage_result_is_immutable(self):
        """StageResult MUST be immutable (frozen dataclass or __slots__ etc.)."""
        result = StageResult(passed=True, attempts=1, data={}, error=None)
        with pytest.raises((AttributeError, TypeError)):
            result.passed = False  # type: ignore[misc]

    def test_stage_result_data_defaults_to_empty_dict(self):
        """StageResult data field MUST accept an empty dict."""
        result = StageResult(passed=True, attempts=1, data={}, error=None)
        assert result.data == {}


# ---------------------------------------------------------------------------
# 3. ReviewOutcome stores fields and is immutable
# ---------------------------------------------------------------------------


class TestReviewOutcome:
    """ReviewOutcome is the return type of _do_review()."""

    def test_review_outcome_passed_true(self):
        """ReviewOutcome MUST expose a 'passed' bool field."""
        outcome = ReviewOutcome(passed=True, issues=(), verdict="pass")
        assert outcome.passed is True

    def test_review_outcome_passed_false(self):
        outcome = ReviewOutcome(passed=False, issues=("missing test",), verdict="fail")
        assert outcome.passed is False

    def test_review_outcome_issues_field(self):
        """ReviewOutcome MUST expose an 'issues' sequence field."""
        issues = ("doc missing", "coverage low")
        outcome = ReviewOutcome(passed=False, issues=issues, verdict="fail")
        assert set(outcome.issues) == set(issues)

    def test_review_outcome_empty_issues_on_pass(self):
        """A passing ReviewOutcome typically has no issues."""
        outcome = ReviewOutcome(passed=True, issues=(), verdict="pass")
        assert len(outcome.issues) == 0

    def test_review_outcome_verdict_pass(self):
        """ReviewOutcome MUST expose a 'verdict' string field."""
        outcome = ReviewOutcome(passed=True, issues=(), verdict="pass")
        assert outcome.verdict == "pass"

    def test_review_outcome_verdict_fail(self):
        outcome = ReviewOutcome(passed=False, issues=("x",), verdict="fail")
        assert outcome.verdict == "fail"

    def test_review_outcome_verdict_partial(self):
        """Verdict may be 'partial' (SPEC-091 auto-fix triggers on non-pass)."""
        outcome = ReviewOutcome(passed=False, issues=("minor",), verdict="partial")
        assert outcome.verdict == "partial"

    def test_review_outcome_is_immutable(self):
        """ReviewOutcome MUST be immutable."""
        outcome = ReviewOutcome(passed=True, issues=(), verdict="pass")
        with pytest.raises((AttributeError, TypeError)):
            outcome.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. execute_with_gate: review passes on first attempt
# ---------------------------------------------------------------------------


class TestExecuteWithGateHappyPath:
    """FR-004: Stage must pass review gate before being marked complete."""

    @pytest.mark.asyncio
    async def test_returns_stage_result_on_success(self):
        """execute_with_gate MUST return a StageResult."""
        stage = _build_concrete_stage(review_outcomes=[_make_passing_outcome()])
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_passed_is_true_when_review_passes(self):
        """T014 (FR-004): When review passes, StageResult.passed MUST be True."""
        stage = _build_concrete_stage(review_outcomes=[_make_passing_outcome()])
        result = await stage.execute_with_gate()
        assert result.passed is True, (
            "StageResult.passed must be True when review gate passes"
        )

    @pytest.mark.asyncio
    async def test_attempts_is_one_on_first_pass(self):
        """When review passes on the first attempt, attempts MUST equal 1."""
        stage = _build_concrete_stage(review_outcomes=[_make_passing_outcome()])
        result = await stage.execute_with_gate()
        assert result.attempts == 1, (
            f"Expected attempts=1 on first-pass review, got {result.attempts}"
        )

    @pytest.mark.asyncio
    async def test_error_is_none_on_success(self):
        """StageResult.error MUST be None when the stage succeeds."""
        stage = _build_concrete_stage(review_outcomes=[_make_passing_outcome()])
        result = await stage.execute_with_gate()
        assert result.error is None

    @pytest.mark.asyncio
    async def test_do_fix_not_called_when_review_passes(self):
        """_do_fix MUST NOT be called when the review gate passes immediately."""
        stage = _build_concrete_stage(review_outcomes=[_make_passing_outcome()])
        result = await stage.execute_with_gate()
        assert stage._fix_call_args == [], (
            "_do_fix must not be called when review passes on first attempt"
        )


# ---------------------------------------------------------------------------
# 5. execute_with_gate: checkpoint persistence on success
# ---------------------------------------------------------------------------


class TestExecuteWithGateCheckpointPersistence:
    """FR-002: Checkpoint MUST be persisted after stage completes successfully."""

    @pytest.mark.asyncio
    async def test_persist_checkpoint_called_on_success(self):
        """execute_with_gate MUST call _persist_checkpoint exactly once on success."""
        mock_store = MagicMock()
        stage = _build_concrete_stage(
            review_outcomes=[_make_passing_outcome()],
            store=mock_store,
        )
        await stage.execute_with_gate()
        assert mock_store.save_checkpoint.call_count == 1, (
            "_persist_checkpoint must be called exactly once on stage success"
        )

    @pytest.mark.asyncio
    async def test_persist_checkpoint_called_with_stage_data(self):
        """The data persisted in the checkpoint MUST match the output of run()."""
        mock_store = MagicMock()
        artifact_data = {"artifact": "spec.md", "lines": 200}
        stage = _build_concrete_stage(
            run_data=artifact_data,
            review_outcomes=[_make_passing_outcome()],
            store=mock_store,
        )
        await stage.execute_with_gate()
        mock_store.save_checkpoint.assert_called_once_with(artifact_data)

    @pytest.mark.asyncio
    async def test_persist_checkpoint_not_called_on_failure(self):
        """FR-002: Checkpoint MUST NOT be persisted when the stage fails (exhausted retries)."""
        mock_store = MagicMock()
        # All review attempts fail
        stage = _build_concrete_stage(
            review_outcomes=[
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),
            ],
            max_retries=3,
            store=mock_store,
        )
        result = await stage.execute_with_gate()
        assert result.passed is False
        assert mock_store.save_checkpoint.call_count == 0, (
            "_persist_checkpoint must not be called when stage fails"
        )


# ---------------------------------------------------------------------------
# 6. execute_with_gate: auto-fix retry loop
# ---------------------------------------------------------------------------


class TestExecuteWithGateAutoFixRetry:
    """SPEC-060: Auto-fix retry loop MUST retry up to max_retries on review failure."""

    @pytest.mark.asyncio
    async def test_do_fix_called_on_review_failure(self):
        """T014 (FR-004): _do_fix MUST be called when review fails."""
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome(), _make_passing_outcome()],
            max_retries=3,
        )
        await stage.execute_with_gate()
        assert len(stage._fix_call_args) == 1, (
            "_do_fix must be called exactly once after a single review failure"
        )

    @pytest.mark.asyncio
    async def test_do_fix_receives_failed_outcome(self):
        """_do_fix MUST receive the ReviewOutcome that failed (SPEC-091)."""
        failing_issues = ("missing docstring", "coverage < 80%")
        failing_outcome = ReviewOutcome(
            passed=False, issues=failing_issues, verdict="fail"
        )
        stage = _build_concrete_stage(
            review_outcomes=[failing_outcome, _make_passing_outcome()],
            max_retries=3,
        )
        await stage.execute_with_gate()
        assert len(stage._fix_call_args) == 1
        received_outcome = stage._fix_call_args[0]
        assert received_outcome.passed is False
        assert set(received_outcome.issues) == set(failing_issues)

    @pytest.mark.asyncio
    async def test_succeeds_after_one_failed_then_one_passed_review(self):
        """SPEC-091: If fix resolves issues, the next review pass => success."""
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome(), _make_passing_outcome()],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.passed is True, (
            "Stage must succeed after failed then passed review"
        )

    @pytest.mark.asyncio
    async def test_attempts_increments_per_review(self):
        """Attempts counter MUST reflect the total number of review evaluations."""
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome(), _make_passing_outcome()],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.attempts == 2, (
            f"Expected attempts=2 (1 fail + 1 pass), got {result.attempts}"
        )

    @pytest.mark.asyncio
    async def test_do_fix_called_twice_on_two_failures_then_pass(self):
        """_do_fix MUST be called once per failed review, not once total."""
        stage = _build_concrete_stage(
            review_outcomes=[
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_passing_outcome(),
            ],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.passed is True
        assert len(stage._fix_call_args) == 2, (
            "_do_fix must be called once per failed review attempt"
        )

    @pytest.mark.asyncio
    async def test_fails_when_max_retries_exhausted(self):
        """SPEC-060: Stage MUST fail once all retry attempts are exhausted."""
        stage = _build_concrete_stage(
            review_outcomes=[
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),  # extra: must not be consumed
            ],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.passed is False, (
            "Stage must fail after max_retries review failures"
        )

    @pytest.mark.asyncio
    async def test_error_set_when_max_retries_exhausted(self):
        """StageResult.error MUST be a non-empty string when retries exhausted."""
        stage = _build_concrete_stage(
            review_outcomes=[
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),
                _make_failing_outcome(),
            ],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.error is not None and result.error != "", (
            "StageResult.error must describe the failure when retries exhausted"
        )

    @pytest.mark.asyncio
    async def test_attempts_equals_max_retries_plus_one_on_failure(self):
        """When all attempts fail, attempts MUST equal max_retries+1 (initial
        attempt + max_retries fix-and-retry cycles)."""
        max_retries = 3
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome()] * (max_retries + 1),
            max_retries=max_retries,
        )
        result = await stage.execute_with_gate()
        assert result.passed is False
        assert result.attempts == max_retries + 1, (
            f"Expected attempts={max_retries + 1}, got {result.attempts}"
        )

    @pytest.mark.asyncio
    async def test_do_fix_called_max_retries_times_on_total_failure(self):
        """_do_fix MUST be called exactly max_retries times before giving up."""
        max_retries = 3
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome()] * (max_retries + 1),
            max_retries=max_retries,
        )
        await stage.execute_with_gate()
        assert len(stage._fix_call_args) == max_retries, (
            f"_do_fix must be called exactly {max_retries} times, "
            f"got {len(stage._fix_call_args)}"
        )


# ---------------------------------------------------------------------------
# 7. execute_with_gate: edge cases
# ---------------------------------------------------------------------------


class TestExecuteWithGateEdgeCases:
    """Edge cases for the review gate and retry loop."""

    @pytest.mark.asyncio
    async def test_max_retries_zero_fails_immediately_on_first_failure(self):
        """T014: With max_retries=0, a single failed review MUST produce failure
        (no fix attempt, no retry)."""
        stage = _build_concrete_stage(
            review_outcomes=[_make_failing_outcome()],
            max_retries=0,
        )
        result = await stage.execute_with_gate()
        assert result.passed is False
        assert len(stage._fix_call_args) == 0, (
            "_do_fix must not be called when max_retries=0"
        )

    @pytest.mark.asyncio
    async def test_max_retries_zero_succeeds_if_review_passes_immediately(self):
        """With max_retries=0 and a passing review, the stage MUST succeed."""
        stage = _build_concrete_stage(
            review_outcomes=[_make_passing_outcome()],
            max_retries=0,
        )
        result = await stage.execute_with_gate()
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_empty_issues_tuple_does_not_crash_fix_loop(self):
        """SPEC-091: A failing outcome with no issues MUST not crash _do_fix."""
        empty_issues_outcome = ReviewOutcome(
            passed=False, issues=(), verdict="fail"
        )
        stage = _build_concrete_stage(
            review_outcomes=[empty_issues_outcome, _make_passing_outcome()],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_stage_result_data_is_included_in_successful_result(self):
        """The data dict from run() MUST be available on the returned StageResult."""
        expected_data = {"spec_path": "specs/spec.md", "token_count": 4200}
        stage = _build_concrete_stage(
            run_data=expected_data,
            review_outcomes=[_make_passing_outcome()],
        )
        result = await stage.execute_with_gate()
        assert result.passed is True
        assert result.data == expected_data, (
            f"Expected result.data={expected_data}, got {result.data}"
        )

    @pytest.mark.asyncio
    async def test_partial_verdict_outcome_triggers_fix_loop(self):
        """A 'partial' verdict (not strictly 'pass') MUST trigger the fix loop,
        because only a 'pass' verdict completes the stage."""
        partial_outcome = ReviewOutcome(
            passed=False, issues=("minor comment style",), verdict="partial"
        )
        stage = _build_concrete_stage(
            review_outcomes=[partial_outcome, _make_passing_outcome()],
            max_retries=3,
        )
        result = await stage.execute_with_gate()
        assert result.passed is True
        assert len(stage._fix_call_args) == 1, (
            "A partial-verdict failure must trigger exactly one _do_fix call"
        )


# ---------------------------------------------------------------------------
# 8. Checkpoint persistence: correct ordering relative to gate
# ---------------------------------------------------------------------------


class TestCheckpointOrdering:
    """FR-002: Checkpoint MUST be persisted only AFTER the review gate passes,
    never before."""

    @pytest.mark.asyncio
    async def test_checkpoint_persisted_after_successful_gate_pass(self):
        """Checkpoint must come after the review, not before."""
        call_order: list[str] = []
        mock_store = MagicMock()

        class _OrderTrackedStage(StageABC):
            def __init__(self):
                self.max_retries = 3
                self._store = mock_store
                self._fix_call_args: list[ReviewOutcome] = []

            async def run(self) -> StageResult:
                call_order.append("run")
                return StageResult(passed=True, attempts=1, data={"k": "v"})

            async def _do_review(self) -> ReviewOutcome:
                call_order.append("review")
                return _make_passing_outcome()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                call_order.append("fix")
                self._fix_call_args.append(outcome)

            async def _persist_checkpoint(self, data: dict) -> None:
                call_order.append("checkpoint")
                self._store.save_checkpoint(data)

        stage = _OrderTrackedStage()
        await stage.execute_with_gate()

        # review must appear before checkpoint
        assert "review" in call_order
        assert "checkpoint" in call_order
        review_idx = call_order.index("review")
        checkpoint_idx = call_order.index("checkpoint")
        assert review_idx < checkpoint_idx, (
            f"Checkpoint must come after review. Order was: {call_order}"
        )
        assert "fix" not in call_order, "No fix should happen on a passing review"

    @pytest.mark.asyncio
    async def test_checkpoint_persisted_after_fix_and_successful_recheck(self):
        """Checkpoint must come only after the final passing review, even when
        a fix loop was needed."""
        call_order: list[str] = []
        outcomes = [_make_failing_outcome(), _make_passing_outcome()]
        mock_store = MagicMock()

        class _OrderTrackedStage(StageABC):
            def __init__(self):
                self.max_retries = 3
                self._store = mock_store
                self._fix_call_args: list[ReviewOutcome] = []

            async def run(self) -> StageResult:
                call_order.append("run")
                return StageResult(passed=True, attempts=1, data={})

            async def _do_review(self) -> ReviewOutcome:
                call_order.append("review")
                return outcomes.pop(0) if outcomes else _make_passing_outcome()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                call_order.append("fix")
                self._fix_call_args.append(outcome)

            async def _persist_checkpoint(self, data: dict) -> None:
                call_order.append("checkpoint")
                self._store.save_checkpoint(data)

        stage = _OrderTrackedStage()
        result = await stage.execute_with_gate()

        assert result.passed is True
        assert call_order.count("fix") == 1
        assert call_order.count("checkpoint") == 1

        # checkpoint must come after the last review
        last_review_idx = max(i for i, v in enumerate(call_order) if v == "review")
        checkpoint_idx = call_order.index("checkpoint")
        assert last_review_idx < checkpoint_idx, (
            f"Checkpoint must appear after the last (passing) review. "
            f"Call order was: {call_order}"
        )


# ---------------------------------------------------------------------------
# 9. run() is called exactly once per execute_with_gate invocation
# ---------------------------------------------------------------------------


class TestRunCalledOnce:
    """run() sets up the stage artifact; it MUST be called exactly once per
    execute_with_gate invocation regardless of how many review retries occur."""

    @pytest.mark.asyncio
    async def test_run_called_exactly_once_on_first_pass(self):
        """run() MUST be called exactly once when review passes immediately."""
        run_count = 0

        class _CountingStage(StageABC):
            def __init__(self):
                self.max_retries = 3
                self._store = MagicMock()
                self._fix_call_args: list[ReviewOutcome] = []

            async def run(self) -> StageResult:
                nonlocal run_count
                run_count += 1
                return StageResult(passed=True, attempts=1, data={})

            async def _do_review(self) -> ReviewOutcome:
                return _make_passing_outcome()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                self._fix_call_args.append(outcome)

            async def _persist_checkpoint(self, data: dict) -> None:
                self._store.save_checkpoint(data)

        stage = _CountingStage()
        await stage.execute_with_gate()
        assert run_count == 1, (
            f"run() must be called exactly once per execute_with_gate; called {run_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_called_exactly_once_even_with_retries(self):
        """run() MUST be called exactly once even when the fix-retry loop runs
        multiple times. Only the review and fix loop repeat, not the main stage body."""
        run_count = 0
        outcomes = [_make_failing_outcome(), _make_failing_outcome(), _make_passing_outcome()]

        class _CountingStage(StageABC):
            def __init__(self):
                self.max_retries = 3
                self._store = MagicMock()
                self._fix_call_args: list[ReviewOutcome] = []

            async def run(self) -> StageResult:
                nonlocal run_count
                run_count += 1
                return StageResult(passed=True, attempts=1, data={})

            async def _do_review(self) -> ReviewOutcome:
                return outcomes.pop(0) if outcomes else _make_passing_outcome()

            async def _do_fix(self, outcome: ReviewOutcome) -> None:
                self._fix_call_args.append(outcome)

            async def _persist_checkpoint(self, data: dict) -> None:
                self._store.save_checkpoint(data)

        stage = _CountingStage()
        result = await stage.execute_with_gate()
        assert result.passed is True
        assert run_count == 1, (
            f"run() must be called exactly once even with retries; called {run_count} times"
        )
