"""Unit tests for orchestrator/engine.py — four-stage sequential pipeline engine.

FR-001: System MUST execute a four-stage pipeline (spec, plan, implement,
        acceptance) in sequence, each stage passing a review gate before
        advancing.
FR-003: System MUST support explicit stage skipping via `skip_stages`
        configuration. No automatic stage-skipping based on heuristics.
FR-005: Engine module MUST contain only stage flow-control logic, delegating
        all stage-specific behavior to the `stages/` sub-package.
FR-059: SQLite write operations MUST be coordinated via asyncio.Lock created
        by engine.py and injected into all writing components.
SPEC-010: All stages execute unless explicitly skipped — no heuristic
          stage-skipping.
SC-001: engine.py MUST be under 300 lines.

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/engine.py provides concrete implementations.

Test coverage areas:
    1.  PipelineEngine is importable and instantiable.
    2.  FR-001: four canonical stage names in correct order.
    3.  FR-001: stages execute sequentially (no skipping by default).
    4.  FR-001: pipeline stops and returns failure when a stage fails.
    5.  FR-003: skip_stages causes named stages to be bypassed.
    6.  FR-003: skipped stages do NOT appear in the executed stage list.
    7.  FR-003: SPEC-010 — no automatic skipping beyond explicit skip_stages.
    8.  FR-059: engine owns an asyncio.Lock instance.
    9.  FR-059: Lock is injected into stages when running.
    10. FR-005: engine delegates each stage by calling execute_with_gate().
    11. Pipeline result carries stage outcomes in order.
    12. PipelineResult is a dataclass / named-tuple with expected fields.
    13. Edge case: all stages skipped → empty result, no stage called.
    14. Edge case: single-stage pipeline runs correctly.
    15. Engine exposes STAGE_NAMES constant listing canonical stage order.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.engine import PipelineEngine, PipelineResult, STAGE_NAMES


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_passing_stage_result(stage_name: str = "spec") -> MagicMock:
    """Return a mock StageResult that represents a passing stage."""
    result = MagicMock()
    result.passed = True
    result.attempts = 1
    result.data = {"stage": stage_name}
    result.error = None
    return result


def _make_failing_stage_result(stage_name: str = "spec") -> MagicMock:
    """Return a mock StageResult that represents a failing stage."""
    result = MagicMock()
    result.passed = False
    result.attempts = 3
    result.data = {}
    result.error = f"{stage_name} review gate failed"
    return result


def _make_stage_mock(passing: bool = True, stage_name: str = "spec") -> MagicMock:
    """Return a mock stage object with execute_with_gate mocked."""
    stage = MagicMock()
    if passing:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result(stage_name)
        )
    else:
        stage.execute_with_gate = AsyncMock(
            return_value=_make_failing_stage_result(stage_name)
        )
    return stage


def _build_engine(
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
    config: dict | None = None,
) -> PipelineEngine:
    """Build a PipelineEngine with all four stages mocked.

    Parameters
    ----------
    stage_overrides:
        Map of stage_name -> mock stage. Missing stages default to passing mocks.
    skip_stages:
        List of stage names to skip.
    config:
        Optional configuration dict merged with defaults.
    """
    default_config: dict = {
        "skip_stages": skip_stages or [],
        "max_retries": 3,
    }
    if config:
        default_config.update(config)

    overrides = stage_overrides or {}
    stages = {
        name: overrides.get(name, _make_stage_mock(passing=True, stage_name=name))
        for name in STAGE_NAMES
    }

    return PipelineEngine(stages=stages, config=default_config)


# ---------------------------------------------------------------------------
# 1. Import and instantiation
# ---------------------------------------------------------------------------


class TestPipelineEngineImport:
    """PipelineEngine must be importable and instantiable."""

    def test_pipeline_engine_is_a_class(self):
        """FR-001: PipelineEngine must be a class, not a function or module."""
        assert inspect.isclass(PipelineEngine)

    def test_pipeline_engine_can_be_instantiated(self):
        """PipelineEngine MUST instantiate without error given valid stages and config."""
        engine = _build_engine()
        assert engine is not None

    def test_pipeline_engine_instance_is_correct_type(self):
        """The instantiated object MUST be an instance of PipelineEngine."""
        engine = _build_engine()
        assert isinstance(engine, PipelineEngine)

    def test_pipeline_result_is_a_class(self):
        """PipelineResult MUST be a class (dataclass or namedtuple)."""
        assert inspect.isclass(PipelineResult)

    def test_stage_names_is_a_sequence(self):
        """STAGE_NAMES MUST be an importable sequence."""
        assert hasattr(STAGE_NAMES, "__iter__"), "STAGE_NAMES must be iterable"


# ---------------------------------------------------------------------------
# 2. FR-001: Canonical stage names and order
# ---------------------------------------------------------------------------


class TestStageNamesConstant:
    """FR-001: The engine MUST define four canonical stages in correct order."""

    def test_stage_names_contains_exactly_four_stages(self):
        """STAGE_NAMES MUST contain exactly four entries."""
        assert len(STAGE_NAMES) == 4, (
            f"Expected 4 stage names, got {len(STAGE_NAMES)}: {STAGE_NAMES}"
        )

    def test_stage_names_first_is_spec(self):
        """FR-001: The first stage MUST be 'spec'."""
        assert STAGE_NAMES[0] == "spec", (
            f"Expected first stage 'spec', got '{STAGE_NAMES[0]}'"
        )

    def test_stage_names_second_is_plan(self):
        """FR-001: The second stage MUST be 'plan'."""
        assert STAGE_NAMES[1] == "plan", (
            f"Expected second stage 'plan', got '{STAGE_NAMES[1]}'"
        )

    def test_stage_names_third_is_implement(self):
        """FR-001: The third stage MUST be 'implement'."""
        assert STAGE_NAMES[2] == "implement", (
            f"Expected third stage 'implement', got '{STAGE_NAMES[2]}'"
        )

    def test_stage_names_fourth_is_acceptance(self):
        """FR-001: The fourth stage MUST be 'acceptance'."""
        assert STAGE_NAMES[3] == "acceptance", (
            f"Expected fourth stage 'acceptance', got '{STAGE_NAMES[3]}'"
        )

    def test_stage_names_are_all_strings(self):
        """Every entry in STAGE_NAMES MUST be a non-empty string."""
        for name in STAGE_NAMES:
            assert isinstance(name, str) and name, (
                f"All STAGE_NAMES entries must be non-empty strings, got: {name!r}"
            )


# ---------------------------------------------------------------------------
# 3. FR-001: Sequential execution (happy path)
# ---------------------------------------------------------------------------


class TestSequentialExecution:
    """FR-001: Stages MUST execute in the canonical order defined by STAGE_NAMES."""

    @pytest.mark.asyncio
    async def test_run_returns_pipeline_result(self):
        """engine.run() MUST return a PipelineResult."""
        engine = _build_engine()
        result = await engine.run()
        assert isinstance(result, PipelineResult), (
            f"engine.run() must return PipelineResult, got {type(result).__name__}"
        )

    @pytest.mark.asyncio
    async def test_all_four_stages_called_in_order(self):
        """FR-001: All four stages MUST have execute_with_gate called, in order."""
        call_log: list[str] = []

        async def make_gate(name: str):
            call_log.append(name)
            return _make_passing_stage_result(name)

        stages = {
            name: MagicMock(
                execute_with_gate=AsyncMock(side_effect=lambda n=name: make_gate(n))
            )
            for name in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert call_log == list(STAGE_NAMES), (
            f"Stages must execute in order {list(STAGE_NAMES)}, got {call_log}"
        )

    @pytest.mark.asyncio
    async def test_each_stage_execute_with_gate_called_exactly_once(self):
        """FR-005: engine delegates to execute_with_gate exactly once per stage."""
        engine = _build_engine()
        await engine.run()

        for name in STAGE_NAMES:
            engine._stages[name].execute_with_gate.assert_awaited_once(), (
                f"execute_with_gate for stage '{name}' must be called exactly once"
            )

    @pytest.mark.asyncio
    async def test_pipeline_result_passed_true_when_all_stages_pass(self):
        """FR-001: PipelineResult.passed MUST be True when all stages pass."""
        engine = _build_engine()
        result = await engine.run()
        assert result.passed is True, (
            "PipelineResult.passed must be True when all stages complete successfully"
        )


# ---------------------------------------------------------------------------
# 4. FR-001: Stage failure stops pipeline
# ---------------------------------------------------------------------------


class TestStageFails:
    """FR-001: When a stage fails its review gate, the pipeline MUST stop."""

    @pytest.mark.asyncio
    async def test_pipeline_stops_after_spec_failure(self):
        """When spec fails, plan/implement/acceptance MUST NOT be executed."""
        plan_mock = _make_stage_mock(passing=True, stage_name="plan")
        implement_mock = _make_stage_mock(passing=True, stage_name="implement")
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "spec": _make_stage_mock(passing=False, stage_name="spec"),
                "plan": plan_mock,
                "implement": implement_mock,
                "acceptance": acceptance_mock,
            }
        )
        result = await engine.run()

        assert result.passed is False
        plan_mock.execute_with_gate.assert_not_awaited()
        implement_mock.execute_with_gate.assert_not_awaited()
        acceptance_mock.execute_with_gate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_stops_after_plan_failure(self):
        """When plan fails, implement/acceptance MUST NOT be executed."""
        implement_mock = _make_stage_mock(passing=True, stage_name="implement")
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "plan": _make_stage_mock(passing=False, stage_name="plan"),
                "implement": implement_mock,
                "acceptance": acceptance_mock,
            }
        )
        result = await engine.run()

        assert result.passed is False
        implement_mock.execute_with_gate.assert_not_awaited()
        acceptance_mock.execute_with_gate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_stops_after_implement_failure(self):
        """When implement fails, acceptance MUST NOT be executed."""
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "implement": _make_stage_mock(passing=False, stage_name="implement"),
                "acceptance": acceptance_mock,
            }
        )
        result = await engine.run()

        assert result.passed is False
        acceptance_mock.execute_with_gate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_result_passed_false_when_stage_fails(self):
        """PipelineResult.passed MUST be False when any stage fails."""
        engine = _build_engine(
            stage_overrides={
                "spec": _make_stage_mock(passing=False, stage_name="spec"),
            }
        )
        result = await engine.run()
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_pipeline_result_contains_failed_stage_name(self):
        """PipelineResult MUST record the name of the stage that failed."""
        engine = _build_engine(
            stage_overrides={
                "plan": _make_stage_mock(passing=False, stage_name="plan"),
            }
        )
        result = await engine.run()
        assert result.failed_stage == "plan", (
            f"Expected failed_stage='plan', got {result.failed_stage!r}"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_failed_stage_none_on_full_success(self):
        """When all stages pass, PipelineResult.failed_stage MUST be None."""
        engine = _build_engine()
        result = await engine.run()
        assert result.failed_stage is None


# ---------------------------------------------------------------------------
# 5. FR-003: skip_stages support
# ---------------------------------------------------------------------------


class TestSkipStages:
    """FR-003: Explicit stage skipping via skip_stages config."""

    @pytest.mark.asyncio
    async def test_skipped_stage_not_executed(self):
        """FR-003: A stage listed in skip_stages MUST NOT have execute_with_gate called."""
        spec_mock = _make_stage_mock(passing=True, stage_name="spec")

        engine = _build_engine(
            stage_overrides={"spec": spec_mock},
            skip_stages=["spec"],
        )
        await engine.run()

        spec_mock.execute_with_gate.assert_not_awaited(), (
            "execute_with_gate must not be called for stages in skip_stages"
        )

    @pytest.mark.asyncio
    async def test_non_skipped_stages_still_execute(self):
        """FR-003: Stages NOT in skip_stages MUST still execute."""
        plan_mock = _make_stage_mock(passing=True, stage_name="plan")
        implement_mock = _make_stage_mock(passing=True, stage_name="implement")
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "plan": plan_mock,
                "implement": implement_mock,
                "acceptance": acceptance_mock,
            },
            skip_stages=["spec"],
        )
        await engine.run()

        plan_mock.execute_with_gate.assert_awaited_once()
        implement_mock.execute_with_gate.assert_awaited_once()
        acceptance_mock.execute_with_gate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipping_middle_stage_does_not_stop_pipeline(self):
        """FR-003: Skipping plan must not abort — spec and implement still run."""
        spec_mock = _make_stage_mock(passing=True, stage_name="spec")
        implement_mock = _make_stage_mock(passing=True, stage_name="implement")
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "spec": spec_mock,
                "implement": implement_mock,
                "acceptance": acceptance_mock,
            },
            skip_stages=["plan"],
        )
        result = await engine.run()

        assert result.passed is True
        spec_mock.execute_with_gate.assert_awaited_once()
        implement_mock.execute_with_gate.assert_awaited_once()
        acceptance_mock.execute_with_gate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_stages_can_be_skipped(self):
        """FR-003: Multiple stages listed in skip_stages are all bypassed."""
        spec_mock = _make_stage_mock(passing=True, stage_name="spec")
        plan_mock = _make_stage_mock(passing=True, stage_name="plan")
        acceptance_mock = _make_stage_mock(passing=True, stage_name="acceptance")

        engine = _build_engine(
            stage_overrides={
                "spec": spec_mock,
                "plan": plan_mock,
                "acceptance": acceptance_mock,
            },
            skip_stages=["spec", "plan"],
        )
        await engine.run()

        spec_mock.execute_with_gate.assert_not_awaited()
        plan_mock.execute_with_gate.assert_not_awaited()
        acceptance_mock.execute_with_gate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pipeline_passed_true_when_only_skipped_stages_would_fail(self):
        """FR-003: A skipped stage that would fail does not cause pipeline failure
        because it is never executed."""
        engine = _build_engine(
            stage_overrides={
                "spec": _make_stage_mock(passing=False, stage_name="spec"),
            },
            skip_stages=["spec"],
        )
        result = await engine.run()
        assert result.passed is True, (
            "Skipped stages must not cause pipeline failure"
        )

    @pytest.mark.asyncio
    async def test_skipped_stages_recorded_in_result(self):
        """PipelineResult MUST record which stages were skipped."""
        engine = _build_engine(skip_stages=["spec", "plan"])
        result = await engine.run()
        assert set(result.skipped_stages) == {"spec", "plan"}, (
            f"Expected skipped_stages={{'spec', 'plan'}}, got {result.skipped_stages}"
        )

    @pytest.mark.asyncio
    async def test_no_skipped_stages_when_skip_stages_empty(self):
        """When skip_stages is empty, PipelineResult.skipped_stages MUST be empty."""
        engine = _build_engine(skip_stages=[])
        result = await engine.run()
        assert len(result.skipped_stages) == 0


# ---------------------------------------------------------------------------
# 6. SPEC-010: No heuristic stage-skipping
# ---------------------------------------------------------------------------


class TestNoHeuristicSkipping:
    """SPEC-010: Stages MUST NOT be automatically skipped based on heuristics
    (e.g., project size, existing artifacts, etc.)."""

    @pytest.mark.asyncio
    async def test_all_stages_run_without_explicit_skip(self):
        """SPEC-010: With no skip_stages config, all four stages execute."""
        executed: list[str] = []

        async def gate(name: str):
            executed.append(name)
            return _make_passing_stage_result(name)

        stages = {
            name: MagicMock(
                execute_with_gate=AsyncMock(side_effect=lambda n=name: gate(n))
            )
            for name in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert set(executed) == set(STAGE_NAMES), (
            f"All stages must run without explicit skip. Executed: {executed}"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_skip_based_on_stage_data(self):
        """SPEC-010: Stage outputs (data) MUST NOT cause the engine to skip later stages."""
        # Stage data contains a hint that could tempt heuristic skipping
        spec_mock = _make_stage_mock(passing=True, stage_name="spec")
        spec_mock.execute_with_gate = AsyncMock(
            return_value=MagicMock(
                passed=True,
                attempts=1,
                data={"skip_plan": True, "cached": True},
                error=None,
            )
        )
        plan_mock = _make_stage_mock(passing=True, stage_name="plan")

        engine = _build_engine(
            stage_overrides={"spec": spec_mock, "plan": plan_mock},
            skip_stages=[],
        )
        await engine.run()

        plan_mock.execute_with_gate.assert_awaited_once(), (
            "Plan stage must run even if spec data hints at skipping"
        )


# ---------------------------------------------------------------------------
# 7. FR-059: asyncio.Lock ownership
# ---------------------------------------------------------------------------


class TestAsyncioLockOwnership:
    """FR-059: engine.py MUST own an asyncio.Lock instance and inject it into
    all writing components (stores, stages)."""

    def test_pipeline_engine_has_lock_attribute(self):
        """PipelineEngine MUST expose a 'lock' attribute."""
        engine = _build_engine()
        assert hasattr(engine, "lock"), (
            "PipelineEngine must have a 'lock' attribute"
        )

    def test_engine_lock_is_asyncio_lock(self):
        """The engine.lock attribute MUST be an asyncio.Lock instance."""
        engine = _build_engine()
        assert isinstance(engine.lock, asyncio.Lock), (
            f"engine.lock must be asyncio.Lock, got {type(engine.lock).__name__}"
        )

    def test_engine_creates_lock_on_init(self):
        """A new PipelineEngine MUST create its own asyncio.Lock on __init__."""
        engine_a = _build_engine()
        engine_b = _build_engine()
        assert engine_a.lock is not engine_b.lock, (
            "Each PipelineEngine instance must own an independent asyncio.Lock"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_before_run(self):
        """Before run() is called, the engine's lock MUST be in the unlocked state."""
        engine = _build_engine()
        # A fresh asyncio.Lock is unlocked; acquiring it must succeed immediately
        acquired = engine.lock.locked()
        assert acquired is False, (
            "engine.lock must be unlocked before run() is called"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_successful_run(self):
        """After a successful run(), the engine's lock MUST be released."""
        engine = _build_engine()
        await engine.run()
        assert engine.lock.locked() is False, (
            "engine.lock must be unlocked after run() completes"
        )

    @pytest.mark.asyncio
    async def test_lock_is_not_held_after_failed_run(self):
        """After a failed run(), the engine's lock MUST still be released."""
        engine = _build_engine(
            stage_overrides={
                "spec": _make_stage_mock(passing=False, stage_name="spec"),
            }
        )
        await engine.run()
        assert engine.lock.locked() is False, (
            "engine.lock must be unlocked even after run() failure"
        )


# ---------------------------------------------------------------------------
# 8. FR-059: Lock injection into stages
# ---------------------------------------------------------------------------


class TestLockInjection:
    """FR-059: The engine MUST inject its asyncio.Lock into stages that accept it."""

    @pytest.mark.asyncio
    async def test_engine_injects_lock_into_stages_that_accept_it(self):
        """FR-059: If a stage has a 'lock' attribute or set_lock() method, the engine
        MUST inject its own lock before calling execute_with_gate."""

        injected_locks: dict[str, asyncio.Lock] = {}

        class LockAwareStage:
            """A stage that records the injected lock."""

            def __init__(self, name: str) -> None:
                self._name = name
                self.lock: asyncio.Lock | None = None

            async def execute_with_gate(self):
                injected_locks[self._name] = self.lock
                return _make_passing_stage_result(self._name)

        stages = {name: LockAwareStage(name) for name in STAGE_NAMES}
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        for name in STAGE_NAMES:
            assert injected_locks.get(name) is engine.lock, (
                f"Stage '{name}' must receive the engine's lock before execution"
            )


# ---------------------------------------------------------------------------
# 9. FR-005: Stage delegation (no stage logic in engine)
# ---------------------------------------------------------------------------


class TestStageDelegation:
    """FR-005: Engine MUST delegate all stage-specific behavior to the stages/
    sub-package via execute_with_gate(), containing no stage logic itself."""

    @pytest.mark.asyncio
    async def test_engine_calls_execute_with_gate_not_run_directly(self):
        """FR-005: Engine MUST call stage.execute_with_gate(), not stage.run()."""
        stage_mock = MagicMock()
        stage_mock.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result("spec")
        )
        stage_mock.run = AsyncMock()  # must NOT be called by engine

        engine = _build_engine(stage_overrides={"spec": stage_mock})
        await engine.run()

        stage_mock.execute_with_gate.assert_awaited_once()
        stage_mock.run.assert_not_awaited(), (
            "Engine must delegate via execute_with_gate, not call stage.run() directly"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_call_do_review_directly(self):
        """FR-005: Engine must not call stage._do_review() directly."""
        stage_mock = MagicMock()
        stage_mock.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result("spec")
        )
        stage_mock._do_review = AsyncMock()

        engine = _build_engine(stage_overrides={"spec": stage_mock})
        await engine.run()

        stage_mock._do_review.assert_not_awaited(), (
            "Engine must not call _do_review directly; delegate to execute_with_gate"
        )

    @pytest.mark.asyncio
    async def test_engine_does_not_call_do_fix_directly(self):
        """FR-005: Engine must not call stage._do_fix() directly."""
        stage_mock = MagicMock()
        stage_mock.execute_with_gate = AsyncMock(
            return_value=_make_passing_stage_result("spec")
        )
        stage_mock._do_fix = AsyncMock()

        engine = _build_engine(stage_overrides={"spec": stage_mock})
        await engine.run()

        stage_mock._do_fix.assert_not_awaited(), (
            "Engine must not call _do_fix directly; delegate to execute_with_gate"
        )


# ---------------------------------------------------------------------------
# 10. PipelineResult fields
# ---------------------------------------------------------------------------


class TestPipelineResultFields:
    """PipelineResult MUST expose well-defined fields for introspection."""

    @pytest.mark.asyncio
    async def test_pipeline_result_has_passed_field(self):
        """PipelineResult MUST have a 'passed' field."""
        engine = _build_engine()
        result = await engine.run()
        assert hasattr(result, "passed"), "PipelineResult must have 'passed' field"

    @pytest.mark.asyncio
    async def test_pipeline_result_has_stage_results_field(self):
        """PipelineResult MUST have a 'stage_results' field mapping stage names to outcomes."""
        engine = _build_engine()
        result = await engine.run()
        assert hasattr(result, "stage_results"), (
            "PipelineResult must have 'stage_results' field"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_stage_results_contains_all_executed_stages(self):
        """stage_results MUST include an entry for every stage that was executed."""
        engine = _build_engine(skip_stages=[])
        result = await engine.run()
        for name in STAGE_NAMES:
            assert name in result.stage_results, (
                f"stage_results must include '{name}', got keys: {list(result.stage_results.keys())}"
            )

    @pytest.mark.asyncio
    async def test_pipeline_result_stage_results_excludes_skipped_stages(self):
        """stage_results MUST NOT include entries for skipped stages."""
        engine = _build_engine(skip_stages=["spec"])
        result = await engine.run()
        assert "spec" not in result.stage_results, (
            "Skipped stages must not appear in stage_results"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_has_skipped_stages_field(self):
        """PipelineResult MUST have a 'skipped_stages' field."""
        engine = _build_engine()
        result = await engine.run()
        assert hasattr(result, "skipped_stages"), (
            "PipelineResult must have 'skipped_stages' field"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_has_failed_stage_field(self):
        """PipelineResult MUST have a 'failed_stage' field (None on success)."""
        engine = _build_engine()
        result = await engine.run()
        assert hasattr(result, "failed_stage"), (
            "PipelineResult must have 'failed_stage' field"
        )

    @pytest.mark.asyncio
    async def test_pipeline_result_is_immutable(self):
        """PipelineResult MUST be immutable (frozen dataclass)."""
        engine = _build_engine()
        result = await engine.run()
        with pytest.raises((AttributeError, TypeError)):
            result.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for the pipeline engine."""

    @pytest.mark.asyncio
    async def test_all_stages_skipped_returns_passed_true(self):
        """Edge: Skipping all stages results in a pipeline that trivially passes."""
        engine = _build_engine(skip_stages=list(STAGE_NAMES))
        result = await engine.run()
        assert result.passed is True, (
            "An all-stages-skipped pipeline has no failures, so passed must be True"
        )

    @pytest.mark.asyncio
    async def test_all_stages_skipped_no_stage_called(self):
        """Edge: When all stages are skipped, no execute_with_gate is called."""
        stage_mocks = {
            name: _make_stage_mock(passing=True, stage_name=name)
            for name in STAGE_NAMES
        }
        engine = PipelineEngine(
            stages=stage_mocks,
            config={"skip_stages": list(STAGE_NAMES)},
        )
        await engine.run()
        for name, mock in stage_mocks.items():
            mock.execute_with_gate.assert_not_awaited(), (
                f"execute_with_gate must not be called for skipped stage '{name}'"
            )

    @pytest.mark.asyncio
    async def test_all_stages_skipped_skipped_stages_contains_all_names(self):
        """Edge: When all stages are skipped, skipped_stages contains all STAGE_NAMES."""
        engine = _build_engine(skip_stages=list(STAGE_NAMES))
        result = await engine.run()
        assert set(result.skipped_stages) == set(STAGE_NAMES)

    @pytest.mark.asyncio
    async def test_stage_results_order_matches_execution_order(self):
        """stage_results entries MUST be in execution order (spec, plan, implement, acceptance)."""
        engine = _build_engine(skip_stages=[])
        result = await engine.run()
        executed_keys = list(result.stage_results.keys())
        # Only non-skipped stages are in stage_results
        expected_keys = [name for name in STAGE_NAMES if name not in []]
        assert executed_keys == expected_keys, (
            f"stage_results must be ordered {expected_keys}, got {executed_keys}"
        )

    @pytest.mark.asyncio
    async def test_acceptance_fails_pipeline_passed_is_false(self):
        """When acceptance (last stage) fails, pipeline.passed must be False."""
        engine = _build_engine(
            stage_overrides={
                "acceptance": _make_stage_mock(passing=False, stage_name="acceptance"),
            }
        )
        result = await engine.run()
        assert result.passed is False


# ---------------------------------------------------------------------------
# 12. SC-001: engine.py line count constraint
# ---------------------------------------------------------------------------


class TestLineCountConstraint:
    """SC-001: engine.py MUST be under 300 lines."""

    def test_engine_module_under_300_lines(self):
        """SC-001: The engine.py source file MUST contain fewer than 300 lines."""
        import orchestrator.engine as engine_module
        import pathlib

        source_path = pathlib.Path(engine_module.__file__)
        if source_path.suffix == ".pyc":
            source_path = source_path.with_suffix(".py").parent.parent / source_path.name.replace(".pyc", ".py")

        # Resolve .py source from __file__
        py_path = pathlib.Path(engine_module.__file__.replace(".pyc", ".py"))
        if not py_path.exists():
            # Try to locate via inspect
            import inspect
            py_path = pathlib.Path(inspect.getfile(engine_module))

        line_count = len(py_path.read_text(encoding="utf-8").splitlines())
        assert line_count < 300, (
            f"SC-001: engine.py must be under 300 lines, currently {line_count} lines"
        )
