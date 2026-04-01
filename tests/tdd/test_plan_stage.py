"""RED-phase tests for PlanStage._execute_steps.

All tests in this module are expected to FAIL until PlanStage is implemented.

Design contract under test
--------------------------
PlanStage._execute_steps must:
  1. Call agents for the "plan" sub-step and capture the returned document.
  2. Call agents for the "research" sub-step and capture the returned document.
  3. Call agents for the "tasks" sub-step to obtain a tasks markdown string,
     then call parser.parse_tasks(tasks_md) to parse it, then call
     store.upsert_tasks(parsed_tasks) to persist the result.
  4. Call agents for the "review" sub-step and capture the returned document.
  5. Return a dict containing keys: plan_doc, research_doc, tasks_md, review_doc.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.stages.base import EngineContext, Stage
from orchestrator.stages.plan import PlanStage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    *,
    plan_doc: str = "PLAN DOC",
    research_doc: str = "RESEARCH DOC",
    tasks_md: str = "- [ ] T001 — Write tests `src/foo.py`",
    review_doc: str = "REVIEW DOC",
    parsed_tasks: object = None,
) -> tuple[EngineContext, MagicMock, MagicMock]:
    """Build a minimal EngineContext with mocked agents and store.

    Returns (ctx, agents_mock, store_mock).
    The agents mock routes four sequential calls to the four expected docs.
    """
    if parsed_tasks is None:
        parsed_tasks = [MagicMock(id="T001")]

    agents = MagicMock()
    # Each call() returns the corresponding document in order.
    agents.call = AsyncMock(side_effect=[plan_doc, research_doc, tasks_md, review_doc])

    store = MagicMock()
    store.upsert_tasks = MagicMock(return_value=None)

    ctx = EngineContext(
        project_path="/tmp/project",
        config=MagicMock(),
        store=store,
        agents=agents,
        checker=MagicMock(),
        review_pipeline=MagicMock(),
    )
    return ctx, agents, store


# ---------------------------------------------------------------------------
# 1. Inheritance — verified by instantiation and behavioral call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_plan_stage_inherits_stage():
    """PlanStage must be a subclass of Stage AND expose _execute_steps behavior.

    The stub raises NotImplementedError, so we confirm the class hierarchy is
    correct (issubclass) but also exercise _execute_steps to force a FAIL
    while the business logic is absent.
    """
    assert issubclass(PlanStage, Stage), "PlanStage does not inherit from Stage"

    # Instantiate and call — stub must raise NotImplementedError,
    # so the following assertion on the return value forces a failure.
    ctx, _, _ = _make_ctx()
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    # This assertion fails because the stub raises NotImplementedError
    # before returning a dict.
    assert isinstance(artifacts, dict) and "plan_doc" in artifacts, (
        "PlanStage._execute_steps must return a dict with plan_doc "
        "(not yet implemented)"
    )


# ---------------------------------------------------------------------------
# 2. Return value shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_steps_returns_artifacts():
    """_execute_steps must return a dict with the four expected keys."""
    ctx, _, _ = _make_ctx()
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    assert isinstance(artifacts, dict), (
        "_execute_steps must return a dict"
    )
    for key in ("plan_doc", "research_doc", "tasks_md", "review_doc"):
        assert key in artifacts, (
            f"artifacts dict is missing required key '{key}'"
        )


# ---------------------------------------------------------------------------
# 3. plan sub-step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_steps_calls_plan_substep():
    """_execute_steps must call agents for the 'plan' sub-step."""
    ctx, agents, _ = _make_ctx(plan_doc="MY PLAN")
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    # agents.call must have been invoked at least once
    agents.call.assert_called()

    # The plan_doc in artifacts must match the first agents.call return value
    assert artifacts["plan_doc"] == "MY PLAN", (
        "plan_doc in artifacts does not match the value returned by the plan sub-step"
    )


# ---------------------------------------------------------------------------
# 4. research sub-step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_steps_calls_research_substep():
    """_execute_steps must call agents for the 'research' sub-step."""
    ctx, agents, _ = _make_ctx(research_doc="MY RESEARCH")
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    # At least two calls must have been made (plan + research)
    assert agents.call.call_count >= 2, (
        "agents.call was not invoked enough times to cover the research sub-step"
    )
    assert artifacts["research_doc"] == "MY RESEARCH", (
        "research_doc in artifacts does not match the value returned by the research sub-step"
    )


# ---------------------------------------------------------------------------
# 5. tasks sub-step — agents call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_steps_calls_tasks_substep():
    """_execute_steps must call agents for the 'tasks' sub-step to get tasks_md."""
    tasks_markdown = "- [ ] T001 — implement foo `src/foo.py`"
    ctx, agents, _ = _make_ctx(tasks_md=tasks_markdown)
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    assert agents.call.call_count >= 3, (
        "agents.call was not invoked enough times to cover the tasks sub-step"
    )
    assert artifacts["tasks_md"] == tasks_markdown, (
        "tasks_md in artifacts does not match the value returned by the tasks sub-step"
    )


# ---------------------------------------------------------------------------
# 6. tasks sub-step — parser.parse_tasks invocation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tasks_substep_calls_parser():
    """tasks sub-step must call parser.parse_tasks with the tasks markdown."""
    tasks_markdown = "- [ ] T001 — implement foo `src/foo.py`"
    ctx, _, _ = _make_ctx(tasks_md=tasks_markdown)
    stage = PlanStage(ctx)

    with patch(
        "orchestrator.tdd.parser.parse_tasks",
        return_value=[],
    ) as mock_parse:
        await stage._execute_steps()

    mock_parse.assert_called_once_with(tasks_markdown), (
        "parser.parse_tasks was not called with the tasks markdown string"
    )


# ---------------------------------------------------------------------------
# 7. tasks sub-step — store.upsert_tasks invocation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tasks_substep_writes_to_store():
    """tasks sub-step must call store.upsert_tasks with the parsed task list."""
    parsed = [MagicMock(id="T001"), MagicMock(id="T002")]
    ctx, _, store = _make_ctx()
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=parsed):
        await stage._execute_steps()

    store.upsert_tasks.assert_called_once_with(parsed), (
        "store.upsert_tasks was not called with the list returned by parse_tasks"
    )


# ---------------------------------------------------------------------------
# 8. review sub-step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_steps_calls_review_substep():
    """_execute_steps must call agents for the 'review' sub-step."""
    ctx, agents, _ = _make_ctx(review_doc="MY REVIEW")
    stage = PlanStage(ctx)

    with patch("orchestrator.tdd.parser.parse_tasks", return_value=[]):
        artifacts = await stage._execute_steps()

    # All four sub-steps require at least four calls
    assert agents.call.call_count >= 4, (
        "agents.call was not invoked enough times to cover the review sub-step"
    )
    assert artifacts["review_doc"] == "MY REVIEW", (
        "review_doc in artifacts does not match the value returned by the review sub-step"
    )
