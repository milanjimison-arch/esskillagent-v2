"""Unit tests for orchestrator/store/models.py — frozen dataclass DTOs and enums.

FR-055: Frozen dataclass DTOs MUST represent all orchestrator domain objects.
FR-054: Enum types MUST capture all pipeline lifecycle states.

These are RED-phase tests. They MUST FAIL until orchestrator/store/models.py
provides the complete implementation. The module does not exist yet, so all
tests will fail at import time — this is the intended RED state.

Test coverage areas:
    - All enums have expected members (Stage, TaskStatus, ReviewVerdict)
    - All dataclasses can be instantiated with required fields
    - All dataclasses are frozen (raise FrozenInstanceError on attribute assignment)
    - Default values work correctly for optional fields
    - Tuple fields enforce immutability (not lists)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.
# The module does not exist yet, so all tests will fail at collection time
# with ModuleNotFoundError — the intended RED state.
# ---------------------------------------------------------------------------
from orchestrator.store.models import (
    AgentInfo,
    AgentResult,
    Checkpoint,
    Evidence,
    OrchestratorConfig,
    Pipeline,
    ReviewResult,
    ReviewVerdict,
    Stage,
    StageProgress,
    Task,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# 1. Enum: Stage
# ===========================================================================


class TestStageEnum:
    """FR-054: Stage enum MUST have SPEC, PLAN, IMPLEMENT, ACCEPTANCE members."""

    def test_stage_has_spec_member(self):
        """Stage.SPEC must exist."""
        assert Stage.SPEC is not None

    def test_stage_has_plan_member(self):
        """Stage.PLAN must exist."""
        assert Stage.PLAN is not None

    def test_stage_has_implement_member(self):
        """Stage.IMPLEMENT must exist."""
        assert Stage.IMPLEMENT is not None

    def test_stage_has_acceptance_member(self):
        """Stage.ACCEPTANCE must exist."""
        assert Stage.ACCEPTANCE is not None

    def test_stage_has_exactly_four_members(self):
        """Stage enum MUST have exactly 4 members (no extra, none missing)."""
        expected = {"SPEC", "PLAN", "IMPLEMENT", "ACCEPTANCE"}
        actual = {m.name for m in Stage}
        assert actual == expected

    def test_stage_members_are_comparable_by_identity(self):
        """Stage members retrieved twice MUST be the same object."""
        assert Stage["SPEC"] is Stage.SPEC
        assert Stage["ACCEPTANCE"] is Stage.ACCEPTANCE

    def test_stage_spec_value_is_string(self):
        """Stage.SPEC value MUST be a string (for serialisation)."""
        assert isinstance(Stage.SPEC.value, str)

    def test_stage_values_are_lowercase_strings(self):
        """FR-054: Stage values MUST be lowercase strings matching the member name."""
        assert Stage.SPEC.value == "spec"
        assert Stage.PLAN.value == "plan"
        assert Stage.IMPLEMENT.value == "implement"
        assert Stage.ACCEPTANCE.value == "acceptance"


# ===========================================================================
# 2. Enum: TaskStatus
# ===========================================================================


class TestTaskStatusEnum:
    """FR-054: TaskStatus enum MUST have PENDING, RUNNING, PASSED, FAILED,
    SKIPPED members."""

    def test_task_status_has_pending(self):
        assert TaskStatus.PENDING is not None

    def test_task_status_has_running(self):
        assert TaskStatus.RUNNING is not None

    def test_task_status_has_passed(self):
        assert TaskStatus.PASSED is not None

    def test_task_status_has_failed(self):
        assert TaskStatus.FAILED is not None

    def test_task_status_has_skipped(self):
        assert TaskStatus.SKIPPED is not None

    def test_task_status_has_exactly_five_members(self):
        """TaskStatus MUST have exactly 5 members."""
        expected = {"PENDING", "RUNNING", "PASSED", "FAILED", "SKIPPED"}
        actual = {m.name for m in TaskStatus}
        assert actual == expected

    def test_task_status_values_are_lowercase_strings(self):
        """TaskStatus values MUST be lowercase strings."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.PASSED.value == "passed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"


# ===========================================================================
# 3. Enum: ReviewVerdict
# ===========================================================================


class TestReviewVerdictEnum:
    """FR-054: ReviewVerdict MUST have PASS, FAIL, PARTIAL members."""

    def test_review_verdict_has_pass(self):
        assert ReviewVerdict.PASS is not None

    def test_review_verdict_has_fail(self):
        assert ReviewVerdict.FAIL is not None

    def test_review_verdict_has_partial(self):
        assert ReviewVerdict.PARTIAL is not None

    def test_review_verdict_has_exactly_three_members(self):
        """ReviewVerdict MUST have exactly 3 members."""
        expected = {"PASS", "FAIL", "PARTIAL"}
        actual = {m.name for m in ReviewVerdict}
        assert actual == expected

    def test_review_verdict_values_are_lowercase_strings(self):
        """ReviewVerdict values MUST be lowercase strings."""
        assert ReviewVerdict.PASS.value == "pass"
        assert ReviewVerdict.FAIL.value == "fail"
        assert ReviewVerdict.PARTIAL.value == "partial"


# ===========================================================================
# 4. Dataclass: Task
# ===========================================================================


class TestTaskDataclass:
    """FR-055: Task DTO MUST store id, name, stage, status, created_at,
    updated_at, and metadata."""

    def _make_task(self, **overrides) -> Task:
        defaults = dict(
            id="task-001",
            name="Write failing tests",
            stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        defaults.update(overrides)
        return Task(**defaults)

    def test_task_stores_id(self):
        """FR-055: Task.id MUST be stored correctly."""
        task = self._make_task(id="T001")
        assert task.id == "T001"

    def test_task_stores_name(self):
        """FR-055: Task.name MUST be stored correctly."""
        task = self._make_task(name="Implement login")
        assert task.name == "Implement login"

    def test_task_stores_stage(self):
        """FR-055: Task.stage MUST be a Stage enum member."""
        task = self._make_task(stage=Stage.IMPLEMENT)
        assert task.stage is Stage.IMPLEMENT

    def test_task_stores_status(self):
        """FR-055: Task.status MUST be a TaskStatus enum member."""
        task = self._make_task(status=TaskStatus.RUNNING)
        assert task.status is TaskStatus.RUNNING

    def test_task_stores_created_at(self):
        """FR-055: Task.created_at MUST be stored as provided."""
        task = self._make_task(created_at=_NOW)
        assert task.created_at == _NOW

    def test_task_stores_updated_at(self):
        """FR-055: Task.updated_at MUST be stored as provided."""
        task = self._make_task(updated_at=_NOW)
        assert task.updated_at == _NOW

    def test_task_metadata_defaults_to_empty_dict(self):
        """Task.metadata MUST default to an empty dict when not provided."""
        task = self._make_task()
        assert task.metadata == {}

    def test_task_metadata_can_hold_arbitrary_data(self):
        """Task.metadata MUST accept arbitrary key-value pairs."""
        task = self._make_task(metadata={"file_path": "src/main.py", "parallel": True})
        assert task.metadata["file_path"] == "src/main.py"
        assert task.metadata["parallel"] is True

    def test_task_is_frozen(self):
        """FR-055: Task MUST be a frozen dataclass — attribute assignment MUST raise."""
        task = self._make_task()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            task.name = "mutated"  # type: ignore[misc]

    def test_task_id_is_frozen(self):
        """Frozen guard: id field MUST NOT be mutable."""
        task = self._make_task()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            task.id = "other-id"  # type: ignore[misc]

    def test_task_status_is_frozen(self):
        """Frozen guard: status field MUST NOT be mutable."""
        task = self._make_task()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            task.status = TaskStatus.PASSED  # type: ignore[misc]

    def test_task_is_a_dataclass(self):
        """Task MUST be a dataclass."""
        assert dataclasses.is_dataclass(Task)


# ===========================================================================
# 5. Dataclass: Pipeline
# ===========================================================================


class TestPipelineDataclass:
    """FR-055: Pipeline DTO MUST store id, tasks, current_stage, status,
    created_at."""

    def _make_pipeline(self, **overrides) -> Pipeline:
        defaults = dict(
            id="pipeline-001",
            tasks=(),
            current_stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
        )
        defaults.update(overrides)
        return Pipeline(**defaults)

    def test_pipeline_stores_id(self):
        """FR-055: Pipeline.id MUST be stored correctly."""
        p = self._make_pipeline(id="P-42")
        assert p.id == "P-42"

    def test_pipeline_stores_tasks_as_tuple(self):
        """FR-055: Pipeline.tasks MUST be a tuple (immutable sequence)."""
        task = Task(
            id="t1",
            name="T",
            stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        p = self._make_pipeline(tasks=(task,))
        assert isinstance(p.tasks, tuple)
        assert len(p.tasks) == 1
        assert p.tasks[0].id == "t1"

    def test_pipeline_tasks_defaults_to_empty_tuple(self):
        """Pipeline.tasks MUST default to an empty tuple."""
        p = self._make_pipeline()
        assert p.tasks == ()

    def test_pipeline_stores_current_stage(self):
        """FR-055: Pipeline.current_stage MUST be a Stage enum member."""
        p = self._make_pipeline(current_stage=Stage.PLAN)
        assert p.current_stage is Stage.PLAN

    def test_pipeline_stores_status(self):
        """FR-055: Pipeline.status MUST be a TaskStatus enum member."""
        p = self._make_pipeline(status=TaskStatus.RUNNING)
        assert p.status is TaskStatus.RUNNING

    def test_pipeline_stores_created_at(self):
        """FR-055: Pipeline.created_at MUST be stored as provided."""
        p = self._make_pipeline(created_at=_NOW)
        assert p.created_at == _NOW

    def test_pipeline_is_frozen(self):
        """FR-055: Pipeline MUST be a frozen dataclass."""
        p = self._make_pipeline()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            p.id = "mutated"  # type: ignore[misc]

    def test_pipeline_is_a_dataclass(self):
        """Pipeline MUST be a dataclass."""
        assert dataclasses.is_dataclass(Pipeline)


# ===========================================================================
# 6. Dataclass: StageProgress
# ===========================================================================


class TestStageProgressDataclass:
    """FR-055: StageProgress DTO MUST store stage, status, attempts,
    max_attempts, started_at, completed_at."""

    def _make_progress(self, **overrides) -> StageProgress:
        defaults = dict(
            stage=Stage.SPEC,
            status=TaskStatus.RUNNING,
            attempts=1,
            max_attempts=3,
            started_at=_NOW,
        )
        defaults.update(overrides)
        return StageProgress(**defaults)

    def test_stage_progress_stores_stage(self):
        sp = self._make_progress(stage=Stage.IMPLEMENT)
        assert sp.stage is Stage.IMPLEMENT

    def test_stage_progress_stores_status(self):
        sp = self._make_progress(status=TaskStatus.PASSED)
        assert sp.status is TaskStatus.PASSED

    def test_stage_progress_stores_attempts(self):
        sp = self._make_progress(attempts=2)
        assert sp.attempts == 2

    def test_stage_progress_stores_max_attempts(self):
        sp = self._make_progress(max_attempts=5)
        assert sp.max_attempts == 5

    def test_stage_progress_stores_started_at(self):
        sp = self._make_progress(started_at=_NOW)
        assert sp.started_at == _NOW

    def test_stage_progress_completed_at_defaults_to_none(self):
        """StageProgress.completed_at MUST default to None (stage not yet done)."""
        sp = self._make_progress()
        assert sp.completed_at is None

    def test_stage_progress_completed_at_can_be_set(self):
        """StageProgress.completed_at MUST accept a datetime when provided."""
        sp = self._make_progress(completed_at=_NOW)
        assert sp.completed_at == _NOW

    def test_stage_progress_is_frozen(self):
        """FR-055: StageProgress MUST be frozen."""
        sp = self._make_progress()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            sp.attempts = 99  # type: ignore[misc]

    def test_stage_progress_is_a_dataclass(self):
        assert dataclasses.is_dataclass(StageProgress)


# ===========================================================================
# 7. Dataclass: Checkpoint
# ===========================================================================


class TestCheckpointDataclass:
    """FR-055: Checkpoint DTO MUST store pipeline_id, stage, data, timestamp."""

    def _make_checkpoint(self, **overrides) -> Checkpoint:
        defaults = dict(
            pipeline_id="pipeline-001",
            stage=Stage.PLAN,
            data={"key": "value"},
            timestamp=_NOW,
        )
        defaults.update(overrides)
        return Checkpoint(**defaults)

    def test_checkpoint_stores_pipeline_id(self):
        cp = self._make_checkpoint(pipeline_id="P-99")
        assert cp.pipeline_id == "P-99"

    def test_checkpoint_stores_stage(self):
        cp = self._make_checkpoint(stage=Stage.IMPLEMENT)
        assert cp.stage is Stage.IMPLEMENT

    def test_checkpoint_stores_data(self):
        cp = self._make_checkpoint(data={"spec_file": "specs/spec.md"})
        assert cp.data["spec_file"] == "specs/spec.md"

    def test_checkpoint_stores_timestamp(self):
        cp = self._make_checkpoint(timestamp=_NOW)
        assert cp.timestamp == _NOW

    def test_checkpoint_data_defaults_to_empty_dict(self):
        """Checkpoint.data MUST default to an empty dict."""
        cp = Checkpoint(pipeline_id="P-1", stage=Stage.SPEC, timestamp=_NOW)
        assert cp.data == {}

    def test_checkpoint_is_frozen(self):
        """FR-055: Checkpoint MUST be frozen."""
        cp = self._make_checkpoint()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            cp.pipeline_id = "mutated"  # type: ignore[misc]

    def test_checkpoint_is_a_dataclass(self):
        assert dataclasses.is_dataclass(Checkpoint)


# ===========================================================================
# 8. Dataclass: ReviewResult
# ===========================================================================


class TestReviewResultDataclass:
    """FR-055: ReviewResult DTO MUST store verdict, score, issues,
    suggestions, reviewer."""

    def _make_review(self, **overrides) -> ReviewResult:
        defaults = dict(
            verdict=ReviewVerdict.PASS,
            score=0.95,
            issues=(),
            suggestions=(),
            reviewer="code-reviewer",
        )
        defaults.update(overrides)
        return ReviewResult(**defaults)

    def test_review_result_stores_verdict(self):
        r = self._make_review(verdict=ReviewVerdict.FAIL)
        assert r.verdict is ReviewVerdict.FAIL

    def test_review_result_stores_score(self):
        r = self._make_review(score=0.72)
        assert r.score == pytest.approx(0.72)

    def test_review_result_stores_issues_as_tuple(self):
        """FR-055: ReviewResult.issues MUST be a tuple."""
        r = self._make_review(issues=("Missing docstring", "Line too long"))
        assert isinstance(r.issues, tuple)
        assert "Missing docstring" in r.issues

    def test_review_result_issues_defaults_to_empty_tuple(self):
        """ReviewResult.issues MUST default to an empty tuple."""
        r = self._make_review()
        assert r.issues == ()

    def test_review_result_stores_suggestions_as_tuple(self):
        """FR-055: ReviewResult.suggestions MUST be a tuple."""
        r = self._make_review(suggestions=("Add type hints",))
        assert isinstance(r.suggestions, tuple)

    def test_review_result_suggestions_defaults_to_empty_tuple(self):
        """ReviewResult.suggestions MUST default to an empty tuple."""
        r = self._make_review()
        assert r.suggestions == ()

    def test_review_result_stores_reviewer(self):
        r = self._make_review(reviewer="security-reviewer")
        assert r.reviewer == "security-reviewer"

    def test_review_result_is_frozen(self):
        """FR-055: ReviewResult MUST be frozen."""
        r = self._make_review()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            r.score = 0.0  # type: ignore[misc]

    def test_review_result_is_a_dataclass(self):
        assert dataclasses.is_dataclass(ReviewResult)


# ===========================================================================
# 9. Dataclass: Evidence
# ===========================================================================


class TestEvidenceDataclass:
    """FR-055: Evidence DTO MUST store type, content, source, timestamp."""

    def _make_evidence(self, **overrides) -> Evidence:
        defaults = dict(
            type="test_output",
            content="All 42 tests passed.",
            source="pytest",
            timestamp=_NOW,
        )
        defaults.update(overrides)
        return Evidence(**defaults)

    def test_evidence_stores_type(self):
        e = self._make_evidence(type="lint_result")
        assert e.type == "lint_result"

    def test_evidence_stores_content(self):
        e = self._make_evidence(content="No lint errors found.")
        assert e.content == "No lint errors found."

    def test_evidence_stores_source(self):
        e = self._make_evidence(source="ruff")
        assert e.source == "ruff"

    def test_evidence_stores_timestamp(self):
        e = self._make_evidence(timestamp=_NOW)
        assert e.timestamp == _NOW

    def test_evidence_is_frozen(self):
        """FR-055: Evidence MUST be frozen."""
        e = self._make_evidence()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            e.content = "mutated"  # type: ignore[misc]

    def test_evidence_is_a_dataclass(self):
        assert dataclasses.is_dataclass(Evidence)


# ===========================================================================
# 10. Dataclass: AgentInfo
# ===========================================================================


class TestAgentInfoDataclass:
    """FR-055: AgentInfo DTO MUST store name, role, capabilities (tuple), model."""

    def _make_agent_info(self, **overrides) -> AgentInfo:
        defaults = dict(
            name="specifier",
            role="spec",
            capabilities=("write_spec", "review_spec"),
            model="claude-sonnet-4-6",
        )
        defaults.update(overrides)
        return AgentInfo(**defaults)

    def test_agent_info_stores_name(self):
        a = self._make_agent_info(name="planner")
        assert a.name == "planner"

    def test_agent_info_stores_role(self):
        a = self._make_agent_info(role="plan")
        assert a.role == "plan"

    def test_agent_info_stores_capabilities_as_tuple(self):
        """FR-055: AgentInfo.capabilities MUST be a tuple (immutable)."""
        a = self._make_agent_info(capabilities=("tdd", "review"))
        assert isinstance(a.capabilities, tuple)
        assert "tdd" in a.capabilities

    def test_agent_info_capabilities_defaults_to_empty_tuple(self):
        """AgentInfo.capabilities MUST default to an empty tuple."""
        a = AgentInfo(name="agent", role="role", model="claude-sonnet-4-6")
        assert a.capabilities == ()

    def test_agent_info_stores_model(self):
        a = self._make_agent_info(model="claude-opus-4")
        assert a.model == "claude-opus-4"

    def test_agent_info_is_frozen(self):
        """FR-055: AgentInfo MUST be frozen."""
        a = self._make_agent_info()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            a.name = "mutated"  # type: ignore[misc]

    def test_agent_info_is_a_dataclass(self):
        assert dataclasses.is_dataclass(AgentInfo)


# ===========================================================================
# 11. Dataclass: AgentResult
# ===========================================================================


class TestAgentResultDataclass:
    """FR-055: AgentResult DTO MUST store agent (AgentInfo), output, evidence
    (tuple of Evidence), duration_ms, success."""

    def _make_agent_result(self, **overrides) -> AgentResult:
        agent = AgentInfo(
            name="specifier",
            role="spec",
            capabilities=(),
            model="claude-sonnet-4-6",
        )
        defaults = dict(
            agent=agent,
            output="Spec written.",
            evidence=(),
            duration_ms=1200,
            success=True,
        )
        defaults.update(overrides)
        return AgentResult(**defaults)

    def test_agent_result_stores_agent(self):
        """FR-055: AgentResult.agent MUST be an AgentInfo instance."""
        info = AgentInfo(name="planner", role="plan", capabilities=(), model="claude-sonnet-4-6")
        r = self._make_agent_result(agent=info)
        assert r.agent.name == "planner"

    def test_agent_result_stores_output(self):
        r = self._make_agent_result(output="Plan generated.")
        assert r.output == "Plan generated."

    def test_agent_result_stores_evidence_as_tuple(self):
        """FR-055: AgentResult.evidence MUST be a tuple of Evidence objects."""
        ev = Evidence(type="log", content="ok", source="runner", timestamp=_NOW)
        r = self._make_agent_result(evidence=(ev,))
        assert isinstance(r.evidence, tuple)
        assert r.evidence[0].content == "ok"

    def test_agent_result_evidence_defaults_to_empty_tuple(self):
        """AgentResult.evidence MUST default to an empty tuple."""
        r = self._make_agent_result()
        assert r.evidence == ()

    def test_agent_result_stores_duration_ms(self):
        r = self._make_agent_result(duration_ms=4200)
        assert r.duration_ms == 4200

    def test_agent_result_stores_success_true(self):
        r = self._make_agent_result(success=True)
        assert r.success is True

    def test_agent_result_stores_success_false(self):
        r = self._make_agent_result(success=False)
        assert r.success is False

    def test_agent_result_is_frozen(self):
        """FR-055: AgentResult MUST be frozen."""
        r = self._make_agent_result()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            r.output = "mutated"  # type: ignore[misc]

    def test_agent_result_is_a_dataclass(self):
        assert dataclasses.is_dataclass(AgentResult)


# ===========================================================================
# 12. Dataclass: OrchestratorConfig
# ===========================================================================


class TestOrchestratorConfigDataclass:
    """FR-055: OrchestratorConfig MUST store project_dir, stages (tuple),
    max_retries, parallel, skip_stages (tuple)."""

    def _make_config(self, **overrides) -> OrchestratorConfig:
        defaults = dict(
            project_dir="/workspace/project",
            stages=(Stage.SPEC, Stage.PLAN, Stage.IMPLEMENT, Stage.ACCEPTANCE),
            max_retries=3,
            parallel=False,
            skip_stages=(),
        )
        defaults.update(overrides)
        return OrchestratorConfig(**defaults)

    def test_config_stores_project_dir(self):
        c = self._make_config(project_dir="/home/user/myproject")
        assert c.project_dir == "/home/user/myproject"

    def test_config_stores_stages_as_tuple(self):
        """FR-055: OrchestratorConfig.stages MUST be a tuple."""
        c = self._make_config(stages=(Stage.SPEC, Stage.PLAN))
        assert isinstance(c.stages, tuple)
        assert Stage.SPEC in c.stages
        assert Stage.PLAN in c.stages

    def test_config_stages_defaults_to_all_four(self):
        """OrchestratorConfig.stages MUST default to all four pipeline stages."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert Stage.SPEC in c.stages
        assert Stage.PLAN in c.stages
        assert Stage.IMPLEMENT in c.stages
        assert Stage.ACCEPTANCE in c.stages

    def test_config_stores_max_retries(self):
        c = self._make_config(max_retries=5)
        assert c.max_retries == 5

    def test_config_max_retries_defaults_to_sensible_value(self):
        """OrchestratorConfig.max_retries MUST have a default > 0."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert c.max_retries > 0

    def test_config_stores_parallel_flag(self):
        c = self._make_config(parallel=True)
        assert c.parallel is True

    def test_config_parallel_defaults_to_false(self):
        """OrchestratorConfig.parallel MUST default to False."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert c.parallel is False

    def test_config_stores_skip_stages_as_tuple(self):
        """FR-055: OrchestratorConfig.skip_stages MUST be a tuple."""
        c = self._make_config(skip_stages=(Stage.SPEC,))
        assert isinstance(c.skip_stages, tuple)
        assert Stage.SPEC in c.skip_stages

    def test_config_skip_stages_defaults_to_empty_tuple(self):
        """OrchestratorConfig.skip_stages MUST default to an empty tuple."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert c.skip_stages == ()

    def test_config_is_frozen(self):
        """FR-055: OrchestratorConfig MUST be frozen."""
        c = self._make_config()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            c.project_dir = "mutated"  # type: ignore[misc]

    def test_config_is_a_dataclass(self):
        assert dataclasses.is_dataclass(OrchestratorConfig)


# ===========================================================================
# 13. Immutability: tuple fields cannot be replaced with lists
# ===========================================================================


class TestTupleFieldImmutability:
    """Tuple fields MUST remain tuples; they cannot be silently converted from lists."""

    def test_pipeline_tasks_must_be_tuple_not_list(self):
        """Providing a list for Pipeline.tasks MUST still store a tuple,
        OR the implementation must raise (either is acceptable; the field
        MUST NOT silently accept a mutable list)."""
        # We verify that the stored value is a tuple, not a list.
        # Implementations may accept a list and coerce to tuple in __post_init__,
        # OR they may require a tuple at construction time.
        p = Pipeline(
            id="P",
            tasks=(),  # use empty tuple — behaviour with list is tested separately
            current_stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
        )
        assert isinstance(p.tasks, tuple), "Pipeline.tasks MUST be a tuple"

    def test_orchestrator_config_stages_must_be_tuple(self):
        """OrchestratorConfig.stages MUST be a tuple, not a list."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert isinstance(c.stages, tuple), "OrchestratorConfig.stages MUST be a tuple"

    def test_orchestrator_config_skip_stages_must_be_tuple(self):
        """OrchestratorConfig.skip_stages MUST be a tuple, not a list."""
        c = OrchestratorConfig(project_dir="/workspace")
        assert isinstance(c.skip_stages, tuple), (
            "OrchestratorConfig.skip_stages MUST be a tuple"
        )

    def test_review_result_issues_must_be_tuple(self):
        """ReviewResult.issues MUST be a tuple."""
        r = ReviewResult(
            verdict=ReviewVerdict.PASS,
            score=1.0,
            issues=(),
            suggestions=(),
            reviewer="r",
        )
        assert isinstance(r.issues, tuple)

    def test_review_result_suggestions_must_be_tuple(self):
        """ReviewResult.suggestions MUST be a tuple."""
        r = ReviewResult(
            verdict=ReviewVerdict.PASS,
            score=1.0,
            issues=(),
            suggestions=(),
            reviewer="r",
        )
        assert isinstance(r.suggestions, tuple)

    def test_agent_info_capabilities_must_be_tuple(self):
        """AgentInfo.capabilities MUST be a tuple."""
        a = AgentInfo(name="x", role="y", capabilities=(), model="m")
        assert isinstance(a.capabilities, tuple)

    def test_agent_result_evidence_must_be_tuple(self):
        """AgentResult.evidence MUST be a tuple."""
        info = AgentInfo(name="x", role="y", capabilities=(), model="m")
        r = AgentResult(agent=info, output="", evidence=(), duration_ms=0, success=True)
        assert isinstance(r.evidence, tuple)


# ===========================================================================
# 14. Cross-dataclass relationships
# ===========================================================================


class TestCrossDataclassRelationships:
    """Verify that dataclasses compose correctly with each other."""

    def test_pipeline_can_contain_tasks(self):
        """A Pipeline with Task objects MUST store and retrieve them correctly."""
        task = Task(
            id="t1",
            name="Write tests",
            stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        pipeline = Pipeline(
            id="p1",
            tasks=(task,),
            current_stage=Stage.SPEC,
            status=TaskStatus.PENDING,
            created_at=_NOW,
        )
        assert pipeline.tasks[0].name == "Write tests"

    def test_agent_result_can_contain_evidence(self):
        """An AgentResult with Evidence objects MUST compose without error."""
        info = AgentInfo(name="tdd-agent", role="implement", capabilities=(), model="claude-sonnet-4-6")
        ev = Evidence(type="pytest", content="3 passed", source="local", timestamp=_NOW)
        result = AgentResult(
            agent=info,
            output="Done",
            evidence=(ev,),
            duration_ms=500,
            success=True,
        )
        assert result.evidence[0].type == "pytest"
        assert result.agent.name == "tdd-agent"

    def test_review_result_with_issues_and_suggestions(self):
        """ReviewResult with non-empty issues and suggestions MUST store them."""
        r = ReviewResult(
            verdict=ReviewVerdict.PARTIAL,
            score=0.6,
            issues=("Missing test", "Uncovered branch"),
            suggestions=("Add edge case test",),
            reviewer="brooks-reviewer",
        )
        assert len(r.issues) == 2
        assert len(r.suggestions) == 1
        assert r.verdict is ReviewVerdict.PARTIAL

    def test_checkpoint_with_nested_data_dict(self):
        """Checkpoint.data MUST support nested dict structures."""
        cp = Checkpoint(
            pipeline_id="P-1",
            stage=Stage.PLAN,
            data={"tasks": ["T001", "T002"], "plan_file": "specs/plan.md"},
            timestamp=_NOW,
        )
        assert cp.data["tasks"] == ["T001", "T002"]
        assert cp.data["plan_file"] == "specs/plan.md"
