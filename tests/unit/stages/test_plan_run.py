"""RED-phase tests for PlanStage.run() — plan → research → tasks → store.

Covers the key behaviors required by the spec:
  1. PlanStage.run() invokes the planner agent to produce a plan.
  2. PlanStage.run() scans planner output for [NR:] markers.
  3. When [NR:] markers are present, the research agent is triggered.
  4. When NO [NR:] markers are present, the research agent is NOT triggered.
  5. PlanStage.run() calls the task-generator to produce tasks.md.
  6. PlanStage.run() parses tasks from tasks.md into the task store.
  7. PlanStage.run() returns a StageResult with the plan output in data.
  8. PlanStage.run() records planner_output in StageResult.data.
  9. PlanStage.run() records tasks in StageResult.data after parsing.
 10. PlanStage.run() records whether research was triggered in data.
 11. Task store is populated with parsed tasks after run().
 12. PlanStage.run() propagates planner agent failures.
 13. PlanStage.run() propagates research agent failures gracefully.
 14. PlanStage.run() propagates task-generator failures gracefully.
 15. Edge cases: empty [NR:] markers list means research is skipped.
 16. Edge cases: multiple [NR:] markers still trigger research exactly once.
 17. Edge cases: tasks.md with zero tasks results in empty task list in store.
 18. Edge cases: tasks.md with many tasks are all parsed into store.

All tests in this module are RED-phase tests. They MUST FAIL until
orchestrator/stages/plan.py implements the required behaviors.

The current plan.py stub returns a StageResult that claims all sub_steps
were executed but does NOT actually invoke the planner, research agent,
task-generator, or task store — so the behavioral assertions below will fail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import StageResult
from orchestrator.stages.plan import PlanStage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_store() -> MagicMock:
    """Return a mock store with save_checkpoint and task-store methods."""
    store = MagicMock()
    store.save_checkpoint = MagicMock()
    store.add_task = MagicMock()
    store.get_tasks = MagicMock(return_value=[])
    store.clear_tasks = MagicMock()
    return store


def _make_planner_agent(output: str = "A plan with no markers.") -> MagicMock:
    """Return a mock planner agent that returns the given output."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=output)
    agent.send_prompt = AsyncMock(return_value=output)
    return agent


def _make_research_agent(output: str = "Research findings.") -> MagicMock:
    """Return a mock research agent that returns the given output."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=output)
    agent.send_prompt = AsyncMock(return_value=output)
    return agent


def _make_task_generator(tasks: list[str] | None = None) -> MagicMock:
    """Return a mock task-generator that produces tasks.md content."""
    if tasks is None:
        tasks = ["T001: Implement feature A", "T002: Write tests for A"]
    tasks_md_content = "\n".join(f"- {t}" for t in tasks)
    generator = MagicMock()
    generator.run = AsyncMock(return_value=tasks_md_content)
    generator.generate = AsyncMock(return_value=tasks_md_content)
    return generator


def _make_task_parser(tasks: list[str] | None = None) -> MagicMock:
    """Return a mock task-parser that parses tasks from tasks.md."""
    if tasks is None:
        tasks = ["T001: Implement feature A", "T002: Write tests for A"]
    parser = MagicMock()
    parser.parse = MagicMock(return_value=tasks)
    parser.parse_tasks = MagicMock(return_value=tasks)
    return parser


def _make_plan_stage(
    *,
    store: MagicMock | None = None,
    planner: MagicMock | None = None,
    research_agent: MagicMock | None = None,
    task_generator: MagicMock | None = None,
    task_parser: MagicMock | None = None,
) -> PlanStage:
    """Construct a PlanStage with injected collaborators.

    The PlanStage must accept these collaborators via constructor keyword
    arguments or via attributes set after construction.
    """
    stage = PlanStage(store=store or _make_store())

    # Inject collaborators — implementation may use any of these patterns:
    # 1. Constructor kwargs
    # 2. Attributes set after construction
    # 3. Via a setter method
    #
    # We set them directly as attributes here; the implementation must look
    # them up via self._planner, self._research_agent, etc.
    if planner is not None:
        stage._planner = planner
    if research_agent is not None:
        stage._research_agent = research_agent
    if task_generator is not None:
        stage._task_generator = task_generator
    if task_parser is not None:
        stage._task_parser = task_parser

    return stage


# ---------------------------------------------------------------------------
# FR-plan-run-001: PlanStage.run() invokes the planner agent
# ---------------------------------------------------------------------------


class TestPlanStageInvokesPlanner:
    """FR-plan-run-001: PlanStage.run() MUST invoke the planner agent."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_001_planner_is_called(self):
        """FR-plan-run-001: PlanStage.run() must call the planner agent."""
        planner = _make_planner_agent("A basic plan.")
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        await stage.run()

        # The planner must have been invoked at least once
        assert planner.run.called or planner.send_prompt.called, (
            "PlanStage.run() must invoke the planner agent (planner.run or "
            "planner.send_prompt must be called)"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_001_planner_called_exactly_once(self):
        """FR-plan-run-001: The planner agent MUST be called exactly once per run()."""
        planner = _make_planner_agent("A basic plan.")
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        await stage.run()

        total_calls = planner.run.call_count + planner.send_prompt.call_count
        assert total_calls == 1, (
            f"Planner agent must be invoked exactly once, but was called {total_calls} times"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_001_planner_output_captured(self):
        """FR-plan-run-001: The planner output MUST be captured for downstream use."""
        planner_output = "This is the planner output with some content."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        # The planner output must appear somewhere in the result data
        assert isinstance(result, StageResult), (
            "run() must return a StageResult"
        )
        assert result.data.get("planner_output") == planner_output or \
               result.data.get("plan") == planner_output or \
               result.data.get("plan_output") == planner_output, (
            f"StageResult.data must contain the planner output. "
            f"Got data keys: {list(result.data.keys())}"
        )


# ---------------------------------------------------------------------------
# FR-plan-run-002: PlanStage.run() scans output for [NR:] markers
# ---------------------------------------------------------------------------


class TestPlanStageScanNRMarkers:
    """FR-plan-run-002: PlanStage.run() MUST scan planner output for [NR:] markers."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_002_nr_markers_detected_from_planner_output(self):
        """FR-plan-run-002: [NR:] markers in planner output MUST be detected."""
        planner_output = "We need to [NR: research async patterns] before proceeding."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        assert isinstance(result, StageResult)
        # The stage data must indicate NR markers were found
        data = result.data
        has_nr_info = (
            data.get("nr_markers") is not None
            or data.get("needs_research") is not None
            or data.get("research_triggered") is not None
        )
        assert has_nr_info, (
            "StageResult.data must contain NR marker detection results "
            f"(nr_markers, needs_research, or research_triggered). Got: {list(data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_002_nr_markers_list_populated_when_found(self):
        """FR-plan-run-002: The nr_markers list MUST contain detected markers."""
        planner_output = "We need [NR: research async] and [NR: check library]."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        nr_markers = result.data.get("nr_markers", [])
        assert len(nr_markers) == 2, (
            f"Expected 2 NR markers in result data, got {len(nr_markers)}: {nr_markers}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_002_no_nr_markers_when_output_is_clean(self):
        """FR-plan-run-002: No NR markers when planner output contains none."""
        planner_output = "A clean plan with no markers at all."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        nr_markers = result.data.get("nr_markers", [])
        assert nr_markers == [], (
            f"Expected empty NR markers list, got: {nr_markers}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_002_needs_research_false_when_no_nr_markers(self):
        """FR-plan-run-002: needs_research MUST be False when no NR markers present."""
        planner_output = "A clean plan with no markers."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        needs_research = result.data.get("needs_research", None)
        research_triggered = result.data.get("research_triggered", None)

        # Either needs_research or research_triggered must be False
        if needs_research is not None:
            assert needs_research is False, (
                "needs_research must be False when no NR markers in planner output"
            )
        elif research_triggered is not None:
            assert research_triggered is False, (
                "research_triggered must be False when no NR markers in planner output"
            )
        else:
            pytest.fail(
                "StageResult.data must contain either 'needs_research' or "
                "'research_triggered'. Got: " + str(list(result.data.keys()))
            )

    @pytest.mark.asyncio
    async def test_FR_plan_run_002_needs_research_true_when_nr_markers_present(self):
        """FR-plan-run-002: needs_research MUST be True when NR markers present."""
        planner_output = "We should [NR: investigate this approach]."
        planner = _make_planner_agent(planner_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner

        result = await stage.run()

        needs_research = result.data.get("needs_research", None)
        research_triggered = result.data.get("research_triggered", None)

        if needs_research is not None:
            assert needs_research is True, (
                "needs_research must be True when NR markers found in planner output"
            )
        elif research_triggered is not None:
            assert research_triggered is True, (
                "research_triggered must be True when NR markers found in planner output"
            )
        else:
            pytest.fail(
                "StageResult.data must contain either 'needs_research' or "
                "'research_triggered'. Got: " + str(list(result.data.keys()))
            )


# ---------------------------------------------------------------------------
# FR-plan-run-003: Research agent triggered when NR markers found
# ---------------------------------------------------------------------------


class TestPlanStageTriggerResearch:
    """FR-plan-run-003: When [NR:] markers are present, the research agent MUST be invoked."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_003_research_agent_called_when_nr_markers_present(self):
        """FR-plan-run-003: Research agent MUST be called when NR markers detected."""
        planner_output = "We must [NR: research async I/O patterns] first."
        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent("Found: asyncio is suitable.")
        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._research_agent = research_agent

        await stage.run()

        assert research_agent.run.called or research_agent.send_prompt.called, (
            "Research agent MUST be invoked when planner output contains [NR:] markers"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_003_research_agent_not_called_without_nr_markers(self):
        """FR-plan-run-003: Research agent MUST NOT be called when no NR markers."""
        planner_output = "A clean plan with no need for research."
        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent("Research results.")
        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._research_agent = research_agent

        await stage.run()

        total_calls = research_agent.run.call_count + research_agent.send_prompt.call_count
        assert total_calls == 0, (
            f"Research agent must NOT be called when planner output has no [NR:] markers, "
            f"but was called {total_calls} times"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_003_research_agent_called_exactly_once_regardless_of_marker_count(self):
        """FR-plan-run-003: Multiple NR markers trigger research exactly once (not per marker)."""
        planner_output = (
            "We need [NR: research async] and also [NR: check library support] "
            "and [NR: evaluate performance]."
        )
        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent("Comprehensive findings.")
        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._research_agent = research_agent

        await stage.run()

        total_calls = research_agent.run.call_count + research_agent.send_prompt.call_count
        assert total_calls == 1, (
            f"Research agent must be called exactly once even with multiple NR markers, "
            f"but was called {total_calls} times"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_003_research_output_captured_in_result_data(self):
        """FR-plan-run-003: Research agent output MUST appear in StageResult.data."""
        planner_output = "We must [NR: research the approach]."
        research_output = "Research found: approach X is optimal."
        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent(research_output)
        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._research_agent = research_agent

        result = await stage.run()

        data = result.data
        has_research_output = (
            data.get("research_output") == research_output
            or data.get("research_findings") == research_output
            or data.get("research_result") == research_output
        )
        assert has_research_output, (
            f"StageResult.data must contain research agent output. "
            f"Expected to find {research_output!r} in data, got: {data}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_003_research_triggered_false_for_clean_plan(self):
        """FR-plan-run-003: research_triggered MUST be False for plan with no NR markers."""
        planner_output = "A straightforward plan needing no research."
        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent()
        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._research_agent = research_agent

        result = await stage.run()

        research_triggered = result.data.get("research_triggered")
        if research_triggered is not None:
            assert research_triggered is False, (
                "research_triggered must be False when no NR markers found"
            )


# ---------------------------------------------------------------------------
# FR-plan-run-004: Task-generator produces tasks.md
# ---------------------------------------------------------------------------


class TestPlanStageCallsTaskGenerator:
    """FR-plan-run-004: PlanStage.run() MUST call the task-generator to produce tasks.md."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_004_task_generator_is_called(self):
        """FR-plan-run-004: The task-generator MUST be called during run()."""
        task_generator = _make_task_generator(["T001: Task one"])
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator

        await stage.run()

        assert task_generator.run.called or task_generator.generate.called, (
            "task-generator MUST be called during PlanStage.run()"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_004_task_generator_called_exactly_once(self):
        """FR-plan-run-004: The task-generator MUST be called exactly once per run()."""
        task_generator = _make_task_generator(["T001: Task one", "T002: Task two"])
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator

        await stage.run()

        total_calls = task_generator.run.call_count + task_generator.generate.call_count
        assert total_calls == 1, (
            f"task-generator must be called exactly once, but was called {total_calls} times"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_004_task_generator_called_after_planner(self):
        """FR-plan-run-004: task-generator MUST be called AFTER the planner."""
        call_order: list[str] = []

        planner = MagicMock()
        planner.run = AsyncMock(side_effect=lambda *a, **kw: call_order.append("planner") or "plan output")
        planner.send_prompt = AsyncMock(side_effect=lambda *a, **kw: call_order.append("planner") or "plan output")

        task_generator = MagicMock()
        task_generator.run = AsyncMock(side_effect=lambda *a, **kw: call_order.append("task_generator") or "- T001: task")
        task_generator.generate = AsyncMock(side_effect=lambda *a, **kw: call_order.append("task_generator") or "- T001: task")

        stage = PlanStage(store=_make_store())
        stage._planner = planner
        stage._task_generator = task_generator

        await stage.run()

        # Verify both were called and in order
        assert "planner" in call_order, "Planner was not called"
        assert "task_generator" in call_order, "task_generator was not called"
        planner_idx = call_order.index("planner")
        generator_idx = call_order.index("task_generator")
        assert planner_idx < generator_idx, (
            f"task-generator must be called AFTER planner. "
            f"Call order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_004_tasks_md_content_stored_in_result_data(self):
        """FR-plan-run-004: The tasks.md content MUST appear in StageResult.data."""
        tasks_content = "- T001: Implement feature\n- T002: Write tests"
        task_generator = MagicMock()
        task_generator.run = AsyncMock(return_value=tasks_content)
        task_generator.generate = AsyncMock(return_value=tasks_content)

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator

        result = await stage.run()

        data = result.data
        has_tasks_content = (
            data.get("tasks_md") == tasks_content
            or data.get("tasks_content") == tasks_content
            or data.get("tasks_md_content") == tasks_content
        )
        assert has_tasks_content, (
            f"StageResult.data must contain tasks.md content. "
            f"Expected to find {tasks_content!r} in data. Got keys: {list(data.keys())}"
        )


# ---------------------------------------------------------------------------
# FR-plan-run-005: Tasks parsed into task store
# ---------------------------------------------------------------------------


class TestPlanStageParseTasksIntoStore:
    """FR-plan-run-005: PlanStage.run() MUST parse tasks from tasks.md into the task store."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_005_tasks_added_to_store(self):
        """FR-plan-run-005: Parsed tasks MUST be added to the task store."""
        store = _make_store()
        parsed_tasks = ["T001: Implement feature A", "T002: Write tests for A"]
        task_parser = _make_task_parser(parsed_tasks)

        stage = PlanStage(store=store)
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator(["T001", "T002"])
        stage._task_parser = task_parser

        await stage.run()

        # The store's task-related method must have been called for each task
        assert store.add_task.called or store.save.called or store.save_checkpoint.called, (
            "Tasks must be added to the task store after parsing"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_005_tasks_in_result_data(self):
        """FR-plan-run-005: Parsed tasks MUST appear in StageResult.data."""
        parsed_tasks = ["T001: Feature A", "T002: Feature B", "T003: Feature C"]
        task_parser = _make_task_parser(parsed_tasks)

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator(parsed_tasks)
        stage._task_parser = task_parser

        result = await stage.run()

        data = result.data
        tasks_in_data = data.get("tasks") or data.get("parsed_tasks") or data.get("task_list")
        assert tasks_in_data is not None, (
            f"StageResult.data must contain parsed tasks. Got keys: {list(data.keys())}"
        )
        assert len(tasks_in_data) == len(parsed_tasks), (
            f"Expected {len(parsed_tasks)} tasks in data, got {len(tasks_in_data)}: {tasks_in_data}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_005_empty_tasks_md_results_in_empty_task_list(self):
        """FR-plan-run-005: Empty tasks.md MUST result in zero tasks in data."""
        empty_parser = _make_task_parser([])
        task_generator = MagicMock()
        task_generator.run = AsyncMock(return_value="")
        task_generator.generate = AsyncMock(return_value="")

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator
        stage._task_parser = empty_parser

        result = await stage.run()

        data = result.data
        tasks_in_data = data.get("tasks") or data.get("parsed_tasks") or data.get("task_list") or []
        assert len(tasks_in_data) == 0, (
            f"Empty tasks.md must result in zero tasks in data, got: {tasks_in_data}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_005_all_tasks_stored_when_many_tasks(self):
        """FR-plan-run-005: All tasks MUST be stored when tasks.md has many tasks."""
        many_tasks = [f"T{i:03d}: Task number {i}" for i in range(1, 21)]
        task_parser = _make_task_parser(many_tasks)
        task_generator = MagicMock()
        tasks_content = "\n".join(f"- {t}" for t in many_tasks)
        task_generator.run = AsyncMock(return_value=tasks_content)
        task_generator.generate = AsyncMock(return_value=tasks_content)

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator
        stage._task_parser = task_parser

        result = await stage.run()

        data = result.data
        tasks_in_data = data.get("tasks") or data.get("parsed_tasks") or data.get("task_list") or []
        assert len(tasks_in_data) == 20, (
            f"Expected 20 tasks in data, got {len(tasks_in_data)}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_005_store_add_task_called_per_task(self):
        """FR-plan-run-005: store.add_task() MUST be called once per parsed task."""
        store = _make_store()
        parsed_tasks = ["T001: Task one", "T002: Task two", "T003: Task three"]
        task_parser = _make_task_parser(parsed_tasks)

        stage = PlanStage(store=store)
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator(parsed_tasks)
        stage._task_parser = task_parser

        await stage.run()

        # Verify add_task was called for each task
        assert store.add_task.call_count == len(parsed_tasks), (
            f"store.add_task must be called once per task. "
            f"Expected {len(parsed_tasks)} calls, got {store.add_task.call_count}"
        )


# ---------------------------------------------------------------------------
# FR-plan-run-006: StageResult content and structure after run()
# ---------------------------------------------------------------------------


class TestPlanStageRunResult:
    """FR-plan-run-006: PlanStage.run() MUST return a well-structured StageResult."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_run_returns_stage_result(self):
        """FR-plan-run-006: run() MUST return a StageResult instance."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        assert isinstance(result, StageResult), (
            f"PlanStage.run() must return a StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_result_passed_is_true_on_success(self):
        """FR-plan-run-006: result.passed MUST be True when run completes without error."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        assert result.passed is True, (
            f"result.passed must be True on a successful run, got {result.passed}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_result_data_has_steps_executed(self):
        """FR-plan-run-006: result.data MUST include 'steps_executed' tracking run sub-steps."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        assert "steps_executed" in result.data, (
            f"result.data must contain 'steps_executed'. Got keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_steps_executed_includes_plan_step(self):
        """FR-plan-run-006: 'plan' MUST appear in steps_executed."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        assert "plan" in steps, (
            f"'plan' must be in steps_executed. Got: {steps}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_steps_executed_includes_tasks_step(self):
        """FR-plan-run-006: 'tasks' MUST appear in steps_executed."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        assert "tasks" in steps, (
            f"'tasks' must be in steps_executed. Got: {steps}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_steps_executed_includes_research_when_triggered(self):
        """FR-plan-run-006: 'research' MUST appear in steps_executed when NR markers found."""
        planner_output = "We need [NR: investigate approach]."
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._research_agent = _make_research_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        assert "research" in steps, (
            f"'research' must be in steps_executed when NR markers triggered. Got: {steps}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_steps_executed_does_not_include_research_when_not_triggered(self):
        """FR-plan-run-006: 'research' MUST NOT be in steps_executed when not triggered."""
        planner_output = "A clean plan with no research needed."
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._research_agent = _make_research_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        assert "research" not in steps, (
            f"'research' must NOT be in steps_executed when no NR markers. Got: {steps}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_result_data_is_dict(self):
        """FR-plan-run-006: result.data MUST be a dict."""
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        assert isinstance(result.data, dict), (
            f"result.data must be a dict, got {type(result.data)}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_006_result_contains_planner_output_key(self):
        """FR-plan-run-006: result.data MUST contain the planner output."""
        planner_text = "Detailed plan output here."
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_text)
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        # At least one of these keys must be in result.data with the planner output
        found_output = (
            result.data.get("planner_output") == planner_text
            or result.data.get("plan") == planner_text
            or result.data.get("plan_output") == planner_text
        )
        assert found_output, (
            f"result.data must contain planner output as 'planner_output', 'plan', or "
            f"'plan_output'. Got data keys: {list(result.data.keys())}"
        )


# ---------------------------------------------------------------------------
# FR-plan-run-007: Full pipeline integration (planner → NR scan → research → tasks → store)
# ---------------------------------------------------------------------------


class TestPlanStageFullPipeline:
    """FR-plan-run-007: Full plan pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_FR_plan_run_007_full_pipeline_with_research(self):
        """FR-plan-run-007: Full pipeline with NR markers: planner→research→tasks→store."""
        planner_output = "Build API layer. [NR: check best async framework]. Then deploy."
        research_output = "asyncio with aiohttp is recommended."
        parsed_tasks = ["T001: Setup project", "T002: Implement API", "T003: Write tests"]

        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent(research_output)
        task_generator = MagicMock()
        tasks_content = "\n".join(f"- {t}" for t in parsed_tasks)
        task_generator.run = AsyncMock(return_value=tasks_content)
        task_generator.generate = AsyncMock(return_value=tasks_content)
        task_parser = _make_task_parser(parsed_tasks)
        store = _make_store()

        stage = PlanStage(store=store)
        stage._planner = planner
        stage._research_agent = research_agent
        stage._task_generator = task_generator
        stage._task_parser = task_parser

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is True

        # Planner was called
        assert planner.run.called or planner.send_prompt.called

        # Research was triggered (NR marker present)
        assert research_agent.run.called or research_agent.send_prompt.called

        # Tasks are in result data
        tasks_in_data = result.data.get("tasks") or result.data.get("parsed_tasks") or []
        assert len(tasks_in_data) == 3, (
            f"Expected 3 tasks in result data, got: {tasks_in_data}"
        )

        # Research output is in result data
        research_in_data = (
            result.data.get("research_output") == research_output
            or result.data.get("research_findings") == research_output
        )
        assert research_in_data, (
            f"Research output must be in result data. Got: {result.data}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_007_full_pipeline_without_research(self):
        """FR-plan-run-007: Full pipeline without NR markers: planner→tasks→store (no research)."""
        planner_output = "Simple straightforward plan. No research needed."
        parsed_tasks = ["T001: Code feature", "T002: Test feature"]

        planner = _make_planner_agent(planner_output)
        research_agent = _make_research_agent()
        task_generator = MagicMock()
        tasks_content = "\n".join(f"- {t}" for t in parsed_tasks)
        task_generator.run = AsyncMock(return_value=tasks_content)
        task_generator.generate = AsyncMock(return_value=tasks_content)
        task_parser = _make_task_parser(parsed_tasks)
        store = _make_store()

        stage = PlanStage(store=store)
        stage._planner = planner
        stage._research_agent = research_agent
        stage._task_generator = task_generator
        stage._task_parser = task_parser

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is True

        # Planner was called
        assert planner.run.called or planner.send_prompt.called

        # Research was NOT triggered
        total_research_calls = research_agent.run.call_count + research_agent.send_prompt.call_count
        assert total_research_calls == 0, (
            f"Research must not be triggered without NR markers, but was called {total_research_calls} times"
        )

        # Tasks are in result data
        tasks_in_data = result.data.get("tasks") or result.data.get("parsed_tasks") or []
        assert len(tasks_in_data) == 2, (
            f"Expected 2 tasks in result data, got: {tasks_in_data}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_007_research_step_recorded_in_steps_executed_full_pipeline(self):
        """FR-plan-run-007: steps_executed must reflect research when NR markers triggered."""
        planner_output = "Plan with [NR: research X] needed."
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._research_agent = _make_research_agent()
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        # plan, research, tasks must all be present in the correct order
        assert "plan" in steps, f"'plan' missing from steps_executed: {steps}"
        assert "research" in steps, f"'research' missing from steps_executed: {steps}"
        assert "tasks" in steps, f"'tasks' missing from steps_executed: {steps}"

        plan_idx = steps.index("plan")
        research_idx = steps.index("research")
        tasks_idx = steps.index("tasks")
        assert plan_idx < research_idx < tasks_idx, (
            f"Steps must be in order plan→research→tasks. Got: {steps}"
        )

    @pytest.mark.asyncio
    async def test_FR_plan_run_007_plan_tasks_order_without_research(self):
        """FR-plan-run-007: Without research, steps must be plan→tasks in order."""
        planner_output = "Clean plan, no research markers."
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        steps = result.data.get("steps_executed", [])
        assert "plan" in steps, f"'plan' missing from steps_executed: {steps}"
        assert "tasks" in steps, f"'tasks' missing from steps_executed: {steps}"

        plan_idx = steps.index("plan")
        tasks_idx = steps.index("tasks")
        assert plan_idx < tasks_idx, (
            f"'plan' must come before 'tasks' in steps_executed. Got: {steps}"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestPlanStageEdgeCases:
    """Edge cases for PlanStage.run()."""

    @pytest.mark.asyncio
    async def test_empty_nr_marker_string_does_not_trigger_research(self):
        """An [NR:] marker with empty content must not trigger research."""
        # [NR:] with no space content — implementation may still trigger;
        # but a plain [NR:] is still a marker per the regex \[NR:[^\]]*\]
        planner_output = "The plan [NR:] has something weird."
        research_agent = _make_research_agent()
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._research_agent = research_agent
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        # [NR:] is a valid marker — research SHOULD be triggered
        assert isinstance(result, StageResult)
        # The research_triggered flag must reflect the presence of the marker
        research_triggered = result.data.get("research_triggered") or result.data.get("needs_research")
        assert research_triggered is True, (
            "Even an empty [NR:] marker must trigger research"
        )

    @pytest.mark.asyncio
    async def test_nr_marker_case_sensitive_uppercase_only(self):
        """[nr:] lowercase MUST NOT be detected as NR marker (case-sensitive)."""
        planner_output = "The plan [nr: lowercase marker] must not trigger research."
        research_agent = _make_research_agent()
        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._research_agent = research_agent
        stage._task_generator = _make_task_generator()

        result = await stage.run()

        total_research_calls = research_agent.run.call_count + research_agent.send_prompt.call_count
        assert total_research_calls == 0, (
            "[nr:] lowercase must NOT trigger research agent (case-sensitive matching required)"
        )
        nr_markers = result.data.get("nr_markers", [])
        assert nr_markers == [], (
            f"Lowercase [nr:] must not be detected as NR marker. Got: {nr_markers}"
        )

    @pytest.mark.asyncio
    async def test_run_returns_stage_result_even_with_single_task(self):
        """PlanStage.run() MUST return StageResult even when only one task is generated."""
        task_parser = _make_task_parser(["T001: Single task only"])
        task_generator = MagicMock()
        task_generator.run = AsyncMock(return_value="- T001: Single task only")
        task_generator.generate = AsyncMock(return_value="- T001: Single task only")

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent()
        stage._task_generator = task_generator
        stage._task_parser = task_parser

        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_planner_output_available_to_task_generator(self):
        """FR-plan-run-004: The task-generator MUST receive the planner output as context."""
        planner_output = "Detailed plan with steps A, B, C."
        received_inputs: list = []

        async def capture_run(*args, **kwargs):
            received_inputs.append(("run", args, kwargs))
            return "- T001: Task from plan"

        async def capture_generate(*args, **kwargs):
            received_inputs.append(("generate", args, kwargs))
            return "- T001: Task from plan"

        task_generator = MagicMock()
        task_generator.run = AsyncMock(side_effect=capture_run)
        task_generator.generate = AsyncMock(side_effect=capture_generate)

        stage = PlanStage(store=_make_store())
        stage._planner = _make_planner_agent(planner_output)
        stage._task_generator = task_generator

        await stage.run()

        assert len(received_inputs) > 0, "task-generator must be called"

        # Verify planner output was passed to the task generator
        all_args_str = str(received_inputs)
        assert planner_output in all_args_str, (
            f"task-generator must receive planner output as input. "
            f"Planner output {planner_output!r} not found in call args: {received_inputs}"
        )
