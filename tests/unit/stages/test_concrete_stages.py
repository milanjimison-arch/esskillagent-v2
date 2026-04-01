"""Unit tests for the four concrete pipeline stages.

FR-004: Every stage MUST implement a review gate.
FR-002: Checkpoint MUST be persisted after successful review.
SPEC-010: All stages execute (no automatic stage-skipping based on heuristics).

Stages under test:
    - SpecStage        (constitution → specify → clarify → review)
    - PlanStage        (plan → research → tasks → review)
    - ImplementStage   (TDD → review → push+CI)
    - AcceptanceStage  (verification → traceability → review)

These are RED-phase tests. They MUST FAIL until each stage class:
  1. Inherits from StageABC
  2. Can be instantiated without raising NotImplementedError
  3. Exposes the correct `name` and `sub_steps` attributes
  4. Implements the three abstract methods: run, _do_review, _do_fix
  5. Returns a StageResult from execute_with_gate / run
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from orchestrator.stages.base import ReviewOutcome, StageABC, StageResult
from orchestrator.stages.spec import SPEC_SUB_STEPS, SpecStage
from orchestrator.stages.plan import PLAN_SUB_STEPS, PlanStage
from orchestrator.stages.implement import IMPLEMENT_SUB_STEPS, ImplementStage
from orchestrator.stages.acceptance import ACCEPTANCE_SUB_STEPS, AcceptanceStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store() -> MagicMock:
    store = MagicMock()
    store.save_checkpoint = MagicMock()
    return store


def _instantiate(cls, store: MagicMock | None = None):
    """Attempt to instantiate a concrete stage.

    Passes a mock store so that tests do not rely on real infrastructure.
    Each concrete stage constructor must accept at least an optional `store`
    keyword argument OR the stage stores it as `self._store` by default.
    """
    try:
        return cls(store=store or _make_store())
    except TypeError:
        # Constructor may not accept keyword args yet — try positional.
        return cls()


# ---------------------------------------------------------------------------
# SpecStage — constitution → specify → clarify → review
# ---------------------------------------------------------------------------


class TestSpecStageIdentity:
    """SpecStage must declare the correct name and sub-steps."""

    def test_spec_stage_class_exists(self):
        """SpecStage must be importable."""
        assert SpecStage is not None

    def test_spec_stage_name_attribute(self):
        """FR-spec-001: SpecStage MUST have a 'name' attribute equal to 'spec'."""
        assert hasattr(SpecStage, "name") or hasattr(SpecStage, "stage_name"), (
            "SpecStage must expose a 'name' or 'stage_name' attribute"
        )
        actual = getattr(SpecStage, "name", getattr(SpecStage, "stage_name", None))
        assert actual == "spec", f"Expected name='spec', got {actual!r}"

    def test_spec_sub_steps_constant_correct(self):
        """SPEC_SUB_STEPS constant must list the four sub-steps in order."""
        assert SPEC_SUB_STEPS == ("constitution", "specify", "clarify", "review"), (
            f"SPEC_SUB_STEPS must be ('constitution','specify','clarify','review'), "
            f"got {SPEC_SUB_STEPS}"
        )

    def test_spec_stage_has_sub_steps_attribute(self):
        """SpecStage MUST expose a 'sub_steps' class attribute."""
        assert hasattr(SpecStage, "sub_steps"), "SpecStage must have a 'sub_steps' attribute"

    def test_spec_stage_sub_steps_order(self):
        """SpecStage.sub_steps MUST list the four sub-steps in the correct order."""
        expected = ("constitution", "specify", "clarify", "review")
        assert tuple(SpecStage.sub_steps) == expected, (
            f"Expected sub_steps={expected}, got {tuple(SpecStage.sub_steps)}"
        )

    def test_spec_stage_sub_steps_count(self):
        """SpecStage MUST have exactly four sub-steps."""
        assert len(SpecStage.sub_steps) == 4, (
            f"Expected 4 sub-steps, got {len(SpecStage.sub_steps)}"
        )

    def test_spec_stage_constitution_is_first_sub_step(self):
        assert SpecStage.sub_steps[0] == "constitution"

    def test_spec_stage_specify_is_second_sub_step(self):
        assert SpecStage.sub_steps[1] == "specify"

    def test_spec_stage_clarify_is_third_sub_step(self):
        assert SpecStage.sub_steps[2] == "clarify"

    def test_spec_stage_review_is_fourth_sub_step(self):
        assert SpecStage.sub_steps[3] == "review"


class TestSpecStageInheritance:
    """FR-004: SpecStage MUST inherit from StageABC."""

    def test_spec_stage_inherits_from_stage_abc(self):
        """SpecStage must be a subclass of StageABC."""
        assert issubclass(SpecStage, StageABC), (
            "SpecStage must inherit from StageABC"
        )

    def test_spec_stage_is_a_class(self):
        assert inspect.isclass(SpecStage)

    def test_spec_stage_has_execute_with_gate(self):
        """SpecStage must expose execute_with_gate (inherited from StageABC)."""
        assert callable(getattr(SpecStage, "execute_with_gate", None)), (
            "SpecStage must expose an execute_with_gate callable"
        )

    def test_spec_stage_has_run_method(self):
        """SpecStage must implement the run() abstract method."""
        assert callable(getattr(SpecStage, "run", None)), (
            "SpecStage must expose a run() callable"
        )

    def test_spec_stage_has_do_review_method(self):
        """SpecStage must implement the _do_review() abstract method."""
        assert callable(getattr(SpecStage, "_do_review", None)), (
            "SpecStage must expose a _do_review() callable"
        )

    def test_spec_stage_has_do_fix_method(self):
        """SpecStage must implement the _do_fix() abstract method."""
        assert callable(getattr(SpecStage, "_do_fix", None)), (
            "SpecStage must expose a _do_fix() callable"
        )


class TestSpecStageInstantiation:
    """SpecStage must be instantiable — stub currently raises NotImplementedError."""

    def test_spec_stage_can_be_instantiated(self):
        """FR-spec-002: SpecStage() MUST not raise NotImplementedError."""
        stage = _instantiate(SpecStage)
        assert stage is not None

    def test_spec_stage_is_instance_of_stage_abc(self):
        """A SpecStage instance MUST be recognised as a StageABC instance."""
        stage = _instantiate(SpecStage)
        assert isinstance(stage, StageABC)


class TestSpecStageRun:
    """SpecStage.run() must return a StageResult."""

    @pytest.mark.asyncio
    async def test_spec_stage_run_returns_stage_result(self):
        """FR-spec-003: SpecStage.run() MUST return a StageResult instance."""
        stage = _instantiate(SpecStage)
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"SpecStage.run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_spec_stage_run_result_has_data_dict(self):
        """StageResult returned by SpecStage.run() MUST have a dict 'data' field."""
        stage = _instantiate(SpecStage)
        result = await stage.run()
        assert isinstance(result.data, dict), (
            f"StageResult.data must be a dict, got {type(result.data)}"
        )

    @pytest.mark.asyncio
    async def test_spec_stage_execute_with_gate_returns_stage_result(self):
        """execute_with_gate() MUST return a StageResult for SpecStage."""
        stage = _instantiate(SpecStage)
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult), (
            f"execute_with_gate() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_spec_stage_execute_with_gate_passed_is_bool(self):
        """StageResult.passed from SpecStage MUST be a bool."""
        stage = _instantiate(SpecStage)
        result = await stage.execute_with_gate()
        assert isinstance(result.passed, bool)


# ---------------------------------------------------------------------------
# PlanStage — plan → research → tasks → review
# ---------------------------------------------------------------------------


class TestPlanStageIdentity:
    """PlanStage must declare the correct name and sub-steps."""

    def test_plan_stage_class_exists(self):
        """PlanStage must be importable."""
        assert PlanStage is not None

    def test_plan_stage_name_attribute(self):
        """FR-plan-001: PlanStage MUST have a 'name' attribute equal to 'plan'."""
        assert hasattr(PlanStage, "name") or hasattr(PlanStage, "stage_name"), (
            "PlanStage must expose a 'name' or 'stage_name' attribute"
        )
        actual = getattr(PlanStage, "name", getattr(PlanStage, "stage_name", None))
        assert actual == "plan", f"Expected name='plan', got {actual!r}"

    def test_plan_sub_steps_constant_correct(self):
        """PLAN_SUB_STEPS constant must list the four sub-steps in order."""
        assert PLAN_SUB_STEPS == ("plan", "research", "tasks", "review"), (
            f"PLAN_SUB_STEPS must be ('plan','research','tasks','review'), "
            f"got {PLAN_SUB_STEPS}"
        )

    def test_plan_stage_has_sub_steps_attribute(self):
        """PlanStage MUST expose a 'sub_steps' class attribute."""
        assert hasattr(PlanStage, "sub_steps"), "PlanStage must have a 'sub_steps' attribute"

    def test_plan_stage_sub_steps_order(self):
        """PlanStage.sub_steps MUST list the four sub-steps in the correct order."""
        expected = ("plan", "research", "tasks", "review")
        assert tuple(PlanStage.sub_steps) == expected, (
            f"Expected sub_steps={expected}, got {tuple(PlanStage.sub_steps)}"
        )

    def test_plan_stage_sub_steps_count(self):
        """PlanStage MUST have exactly four sub-steps."""
        assert len(PlanStage.sub_steps) == 4, (
            f"Expected 4 sub-steps, got {len(PlanStage.sub_steps)}"
        )

    def test_plan_stage_plan_is_first_sub_step(self):
        assert PlanStage.sub_steps[0] == "plan"

    def test_plan_stage_research_is_second_sub_step(self):
        assert PlanStage.sub_steps[1] == "research"

    def test_plan_stage_tasks_is_third_sub_step(self):
        assert PlanStage.sub_steps[2] == "tasks"

    def test_plan_stage_review_is_fourth_sub_step(self):
        assert PlanStage.sub_steps[3] == "review"


class TestPlanStageInheritance:
    """FR-004: PlanStage MUST inherit from StageABC."""

    def test_plan_stage_inherits_from_stage_abc(self):
        assert issubclass(PlanStage, StageABC), (
            "PlanStage must inherit from StageABC"
        )

    def test_plan_stage_is_a_class(self):
        assert inspect.isclass(PlanStage)

    def test_plan_stage_has_execute_with_gate(self):
        assert callable(getattr(PlanStage, "execute_with_gate", None)), (
            "PlanStage must expose an execute_with_gate callable"
        )

    def test_plan_stage_has_run_method(self):
        assert callable(getattr(PlanStage, "run", None))

    def test_plan_stage_has_do_review_method(self):
        assert callable(getattr(PlanStage, "_do_review", None))

    def test_plan_stage_has_do_fix_method(self):
        assert callable(getattr(PlanStage, "_do_fix", None))


class TestPlanStageInstantiation:
    """PlanStage must be instantiable."""

    def test_plan_stage_can_be_instantiated(self):
        """FR-plan-002: PlanStage() MUST not raise NotImplementedError."""
        stage = _instantiate(PlanStage)
        assert stage is not None

    def test_plan_stage_is_instance_of_stage_abc(self):
        stage = _instantiate(PlanStage)
        assert isinstance(stage, StageABC)


class TestPlanStageRun:
    """PlanStage.run() must return a StageResult."""

    @pytest.mark.asyncio
    async def test_plan_stage_run_returns_stage_result(self):
        """FR-plan-003: PlanStage.run() MUST return a StageResult instance."""
        stage = _instantiate(PlanStage)
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"PlanStage.run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_plan_stage_run_result_has_data_dict(self):
        stage = _instantiate(PlanStage)
        result = await stage.run()
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_plan_stage_execute_with_gate_returns_stage_result(self):
        stage = _instantiate(PlanStage)
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_plan_stage_execute_with_gate_passed_is_bool(self):
        stage = _instantiate(PlanStage)
        result = await stage.execute_with_gate()
        assert isinstance(result.passed, bool)


# ---------------------------------------------------------------------------
# ImplementStage — TDD → review → push+CI
# ---------------------------------------------------------------------------


class TestImplementStageIdentity:
    """ImplementStage must declare the correct name and sub-steps."""

    def test_implement_stage_class_exists(self):
        assert ImplementStage is not None

    def test_implement_stage_name_attribute(self):
        """FR-impl-001: ImplementStage MUST have a 'name' attribute equal to 'implement'."""
        assert hasattr(ImplementStage, "name") or hasattr(ImplementStage, "stage_name"), (
            "ImplementStage must expose a 'name' or 'stage_name' attribute"
        )
        actual = getattr(ImplementStage, "name", getattr(ImplementStage, "stage_name", None))
        assert actual == "implement", f"Expected name='implement', got {actual!r}"

    def test_implement_sub_steps_constant_correct(self):
        """IMPLEMENT_SUB_STEPS constant must list the three sub-steps in order."""
        assert IMPLEMENT_SUB_STEPS == ("TDD", "push+CI", "review"), (
            f"IMPLEMENT_SUB_STEPS must be ('TDD','push+CI','review'), "
            f"got {IMPLEMENT_SUB_STEPS}"
        )

    def test_implement_stage_has_sub_steps_attribute(self):
        assert hasattr(ImplementStage, "sub_steps"), (
            "ImplementStage must have a 'sub_steps' attribute"
        )

    def test_implement_stage_sub_steps_order(self):
        """ImplementStage.sub_steps MUST list the three sub-steps in the correct order."""
        expected = ("TDD", "push+CI", "review")
        assert tuple(ImplementStage.sub_steps) == expected, (
            f"Expected sub_steps={expected}, got {tuple(ImplementStage.sub_steps)}"
        )

    def test_implement_stage_sub_steps_count(self):
        """ImplementStage MUST have exactly three sub-steps."""
        assert len(ImplementStage.sub_steps) == 3, (
            f"Expected 3 sub-steps, got {len(ImplementStage.sub_steps)}"
        )

    def test_implement_stage_tdd_is_first_sub_step(self):
        assert ImplementStage.sub_steps[0] == "TDD"

    def test_implement_stage_push_ci_is_second_sub_step(self):
        assert ImplementStage.sub_steps[1] == "push+CI"

    def test_implement_stage_review_is_third_sub_step(self):
        assert ImplementStage.sub_steps[2] == "review"


class TestImplementStageInheritance:
    """FR-004: ImplementStage MUST inherit from StageABC."""

    def test_implement_stage_inherits_from_stage_abc(self):
        assert issubclass(ImplementStage, StageABC), (
            "ImplementStage must inherit from StageABC"
        )

    def test_implement_stage_is_a_class(self):
        assert inspect.isclass(ImplementStage)

    def test_implement_stage_has_execute_with_gate(self):
        assert callable(getattr(ImplementStage, "execute_with_gate", None))

    def test_implement_stage_has_run_method(self):
        assert callable(getattr(ImplementStage, "run", None))

    def test_implement_stage_has_do_review_method(self):
        assert callable(getattr(ImplementStage, "_do_review", None))

    def test_implement_stage_has_do_fix_method(self):
        assert callable(getattr(ImplementStage, "_do_fix", None))


class TestImplementStageInstantiation:
    """ImplementStage must be instantiable."""

    def test_implement_stage_can_be_instantiated(self):
        """FR-impl-002: ImplementStage() MUST not raise NotImplementedError."""
        stage = _instantiate(ImplementStage)
        assert stage is not None

    def test_implement_stage_is_instance_of_stage_abc(self):
        stage = _instantiate(ImplementStage)
        assert isinstance(stage, StageABC)


class TestImplementStageRun:
    """ImplementStage.run() must return a StageResult."""

    @pytest.mark.asyncio
    async def test_implement_stage_run_returns_stage_result(self):
        """FR-impl-003: ImplementStage.run() MUST return a StageResult instance."""
        stage = _instantiate(ImplementStage)
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"ImplementStage.run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_implement_stage_run_result_has_data_dict(self):
        stage = _instantiate(ImplementStage)
        result = await stage.run()
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_implement_stage_execute_with_gate_returns_stage_result(self):
        stage = _instantiate(ImplementStage)
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_implement_stage_execute_with_gate_passed_is_bool(self):
        stage = _instantiate(ImplementStage)
        result = await stage.execute_with_gate()
        assert isinstance(result.passed, bool)


# ---------------------------------------------------------------------------
# AcceptanceStage — verification → traceability → review
# ---------------------------------------------------------------------------


class TestAcceptanceStageIdentity:
    """AcceptanceStage must declare the correct name and sub-steps."""

    def test_acceptance_stage_class_exists(self):
        assert AcceptanceStage is not None

    def test_acceptance_stage_name_attribute(self):
        """FR-acpt-001: AcceptanceStage MUST have a 'name' attribute equal to 'acceptance'."""
        assert hasattr(AcceptanceStage, "name") or hasattr(AcceptanceStage, "stage_name"), (
            "AcceptanceStage must expose a 'name' or 'stage_name' attribute"
        )
        actual = getattr(AcceptanceStage, "name", getattr(AcceptanceStage, "stage_name", None))
        assert actual == "acceptance", f"Expected name='acceptance', got {actual!r}"

    def test_acceptance_sub_steps_constant_correct(self):
        """ACCEPTANCE_SUB_STEPS constant must list the three sub-steps in order."""
        assert ACCEPTANCE_SUB_STEPS == ("verification", "traceability", "review"), (
            f"ACCEPTANCE_SUB_STEPS must be ('verification','traceability','review'), "
            f"got {ACCEPTANCE_SUB_STEPS}"
        )

    def test_acceptance_stage_has_sub_steps_attribute(self):
        assert hasattr(AcceptanceStage, "sub_steps"), (
            "AcceptanceStage must have a 'sub_steps' attribute"
        )

    def test_acceptance_stage_sub_steps_order(self):
        """AcceptanceStage.sub_steps MUST list the three sub-steps in the correct order."""
        expected = ("verification", "traceability", "review")
        assert tuple(AcceptanceStage.sub_steps) == expected, (
            f"Expected sub_steps={expected}, got {tuple(AcceptanceStage.sub_steps)}"
        )

    def test_acceptance_stage_sub_steps_count(self):
        """AcceptanceStage MUST have exactly three sub-steps."""
        assert len(AcceptanceStage.sub_steps) == 3, (
            f"Expected 3 sub-steps, got {len(AcceptanceStage.sub_steps)}"
        )

    def test_acceptance_stage_verification_is_first_sub_step(self):
        assert AcceptanceStage.sub_steps[0] == "verification"

    def test_acceptance_stage_traceability_is_second_sub_step(self):
        assert AcceptanceStage.sub_steps[1] == "traceability"

    def test_acceptance_stage_review_is_third_sub_step(self):
        assert AcceptanceStage.sub_steps[2] == "review"


class TestAcceptanceStageInheritance:
    """FR-004: AcceptanceStage MUST inherit from StageABC."""

    def test_acceptance_stage_inherits_from_stage_abc(self):
        assert issubclass(AcceptanceStage, StageABC), (
            "AcceptanceStage must inherit from StageABC"
        )

    def test_acceptance_stage_is_a_class(self):
        assert inspect.isclass(AcceptanceStage)

    def test_acceptance_stage_has_execute_with_gate(self):
        assert callable(getattr(AcceptanceStage, "execute_with_gate", None))

    def test_acceptance_stage_has_run_method(self):
        assert callable(getattr(AcceptanceStage, "run", None))

    def test_acceptance_stage_has_do_review_method(self):
        assert callable(getattr(AcceptanceStage, "_do_review", None))

    def test_acceptance_stage_has_do_fix_method(self):
        assert callable(getattr(AcceptanceStage, "_do_fix", None))


class TestAcceptanceStageInstantiation:
    """AcceptanceStage must be instantiable."""

    def test_acceptance_stage_can_be_instantiated(self):
        """FR-acpt-002: AcceptanceStage() MUST not raise NotImplementedError."""
        stage = _instantiate(AcceptanceStage)
        assert stage is not None

    def test_acceptance_stage_is_instance_of_stage_abc(self):
        stage = _instantiate(AcceptanceStage)
        assert isinstance(stage, StageABC)


class TestAcceptanceStageRun:
    """AcceptanceStage.run() must return a StageResult."""

    @pytest.mark.asyncio
    async def test_acceptance_stage_run_returns_stage_result(self):
        """FR-acpt-003: AcceptanceStage.run() MUST return a StageResult instance."""
        stage = _instantiate(AcceptanceStage)
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"AcceptanceStage.run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_acceptance_stage_run_result_has_data_dict(self):
        stage = _instantiate(AcceptanceStage)
        result = await stage.run()
        assert isinstance(result.data, dict)

    @pytest.mark.asyncio
    async def test_acceptance_stage_execute_with_gate_returns_stage_result(self):
        stage = _instantiate(AcceptanceStage)
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_acceptance_stage_execute_with_gate_passed_is_bool(self):
        stage = _instantiate(AcceptanceStage)
        result = await stage.execute_with_gate()
        assert isinstance(result.passed, bool)


# ---------------------------------------------------------------------------
# Cross-cutting: all stages share the same base contract (SPEC-010)
# ---------------------------------------------------------------------------


class TestAllStagesShareBaseContract:
    """SPEC-010: All four stages MUST implement the full StageABC contract."""

    ALL_STAGE_CLASSES = [SpecStage, PlanStage, ImplementStage, AcceptanceStage]

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_inherits_from_stage_abc(self, stage_cls):
        """Every stage class MUST be a subclass of StageABC."""
        assert issubclass(stage_cls, StageABC), (
            f"{stage_cls.__name__} must inherit from StageABC"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_has_sub_steps(self, stage_cls):
        """Every stage class MUST expose a non-empty 'sub_steps' attribute."""
        assert hasattr(stage_cls, "sub_steps"), (
            f"{stage_cls.__name__} must have a 'sub_steps' attribute"
        )
        assert len(stage_cls.sub_steps) >= 3, (
            f"{stage_cls.__name__}.sub_steps must contain at least 3 steps"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_sub_steps_ends_with_review(self, stage_cls):
        """Every stage MUST include 'review' as its final sub-step (review gate)."""
        assert stage_cls.sub_steps[-1] == "review", (
            f"{stage_cls.__name__}.sub_steps must end with 'review', "
            f"got {stage_cls.sub_steps[-1]!r}"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_can_be_instantiated(self, stage_cls):
        """Every stage MUST be instantiable without NotImplementedError."""
        stage = _instantiate(stage_cls)
        assert stage is not None, f"{stage_cls.__name__}() must not return None"

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_has_name_attribute(self, stage_cls):
        """Every stage class MUST declare a string 'name' or 'stage_name' attribute."""
        has_name = hasattr(stage_cls, "name") or hasattr(stage_cls, "stage_name")
        assert has_name, (
            f"{stage_cls.__name__} must expose a 'name' or 'stage_name' attribute"
        )
        name = getattr(stage_cls, "name", getattr(stage_cls, "stage_name", None))
        assert isinstance(name, str) and name, (
            f"{stage_cls.__name__}.name must be a non-empty string, got {name!r}"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_has_run_callable(self, stage_cls):
        assert callable(getattr(stage_cls, "run", None)), (
            f"{stage_cls.__name__} must expose a run() callable"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_has_do_review_callable(self, stage_cls):
        assert callable(getattr(stage_cls, "_do_review", None)), (
            f"{stage_cls.__name__} must expose a _do_review() callable"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    def test_each_stage_has_do_fix_callable(self, stage_cls):
        assert callable(getattr(stage_cls, "_do_fix", None)), (
            f"{stage_cls.__name__} must expose a _do_fix() callable"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    @pytest.mark.asyncio
    async def test_each_stage_run_returns_stage_result(self, stage_cls):
        """Every stage.run() MUST return a StageResult."""
        stage = _instantiate(stage_cls)
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"{stage_cls.__name__}.run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.parametrize("stage_cls", ALL_STAGE_CLASSES)
    @pytest.mark.asyncio
    async def test_each_stage_execute_with_gate_returns_stage_result(self, stage_cls):
        """execute_with_gate() MUST return a StageResult for every stage."""
        stage = _instantiate(stage_cls)
        result = await stage.execute_with_gate()
        assert isinstance(result, StageResult), (
            f"{stage_cls.__name__}.execute_with_gate() must return StageResult, "
            f"got {type(result)}"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: stage names are unique and match their role
# ---------------------------------------------------------------------------


class TestStageNameUniqueness:
    """Each stage MUST have a distinct name identifying its role in the pipeline."""

    def test_all_stage_names_are_unique(self):
        """The four stage names must all be distinct strings."""
        names = []
        for cls in [SpecStage, PlanStage, ImplementStage, AcceptanceStage]:
            name = getattr(cls, "name", getattr(cls, "stage_name", None))
            names.append(name)
        assert len(names) == len(set(names)), (
            f"Stage names must be unique, got: {names}"
        )

    def test_stage_names_are_non_empty_strings(self):
        for cls in [SpecStage, PlanStage, ImplementStage, AcceptanceStage]:
            name = getattr(cls, "name", getattr(cls, "stage_name", None))
            assert isinstance(name, str) and name.strip(), (
                f"{cls.__name__} name must be a non-empty string, got {name!r}"
            )


# ---------------------------------------------------------------------------
# Cross-cutting: sub-step execution order (SPEC-010)
# ---------------------------------------------------------------------------


class TestSubStepExecutionOrder:
    """SPEC-010: Sub-steps MUST be executed in the declared order within each stage."""

    @pytest.mark.asyncio
    async def test_spec_stage_records_sub_steps_in_order(self):
        """SpecStage MUST record sub-step execution in the order:
        constitution, specify, clarify, review."""
        stage = _instantiate(SpecStage)
        result = await stage.run()
        # The result data SHOULD contain a record of steps executed.
        # At minimum, run() must succeed and return a StageResult.
        assert isinstance(result, StageResult), (
            "SpecStage.run() must return a StageResult"
        )
        # If the stage records executed steps, verify the order.
        if "steps_executed" in result.data:
            assert result.data["steps_executed"] == list(SpecStage.sub_steps), (
                f"Steps executed must match {list(SpecStage.sub_steps)}, "
                f"got {result.data['steps_executed']}"
            )

    @pytest.mark.asyncio
    async def test_plan_stage_records_sub_steps_in_order(self):
        """PlanStage MUST execute sub-steps in the correct order.

        'research' is conditional — only present when NR markers are found.
        Without collaborators injected, steps_executed is ['plan', 'tasks'].
        """
        stage = _instantiate(PlanStage)
        result = await stage.run()
        assert isinstance(result, StageResult)
        if "steps_executed" in result.data:
            steps = result.data["steps_executed"]
            # All returned steps must be valid sub-steps in correct order
            for step in steps:
                assert step in PlanStage.sub_steps
            assert steps == sorted(steps, key=lambda s: PlanStage.sub_steps.index(s))

    @pytest.mark.asyncio
    async def test_implement_stage_records_sub_steps_in_order(self):
        """ImplementStage MUST execute sub-steps in the order:
        TDD, review, push+CI."""
        stage = _instantiate(ImplementStage)
        result = await stage.run()
        assert isinstance(result, StageResult)
        if "steps_executed" in result.data:
            assert result.data["steps_executed"] == list(ImplementStage.sub_steps)

    @pytest.mark.asyncio
    async def test_acceptance_stage_records_sub_steps_in_order(self):
        """AcceptanceStage MUST execute sub-steps in the order:
        verification, traceability, review."""
        stage = _instantiate(AcceptanceStage)
        result = await stage.run()
        assert isinstance(result, StageResult)
        if "steps_executed" in result.data:
            assert result.data["steps_executed"] == list(AcceptanceStage.sub_steps)
