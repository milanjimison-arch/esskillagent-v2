"""RED-phase behavioral tests for ReviewPipeline.

Each test references the originating functional requirement and asserts on
concrete return values / side effects. The stub raises NotImplementedError,
so every test must fail during the RED phase.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.review.pipeline import ReviewPipeline, ReviewResult
from orchestrator.store.models import Configuration, Review


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(max_fix_retries: int = 2) -> Configuration:
    """Return a real Configuration instance with test-appropriate values."""
    return Configuration(
        model_default="test-model",
        model_spec="test-model",
        model_reviewer="test-model",
        test_command="pytest",
        local_test=True,
        ci_timeout=60,
        max_retries=3,
        max_green_retries=2,
        max_fix_retries=max_fix_retries,
        stage_timeout=300,
        skip_stages=[],
    )


def _make_review(reviewer: str, verdict: str, issues: list[dict] | None = None) -> Review:
    """Return a Review dataclass with sensible defaults."""
    return Review(
        id=1,
        phase="implement",
        stage="implement",
        reviewer=reviewer,
        verdict=verdict,
        critical=0,
        high=0,
        medium=0,
        low=0,
        issues=issues,
        superseded=False,
        created_at=None,
    )


def _make_agents(reviewer_verdicts: dict[str, str], issues_map: dict[str, list[dict]] | None = None) -> MagicMock:
    """
    Build a mock agents object whose get_agent(name).run() returns a structured
    review response for 'code', 'security', and 'brooks' reviewers.

    reviewer_verdicts: {"code": "pass", "security": "pass", "brooks": "pass"}
    issues_map:        {"code": [{"description": "missing handler"}], ...}
    """
    issues_map = issues_map or {}
    agents = MagicMock()

    def _get_agent(name: str) -> MagicMock:
        agent = MagicMock()
        verdict = reviewer_verdicts.get(name, "pass")
        issues = issues_map.get(name, [])
        # Each agent.run() is a coroutine returning a dict the pipeline must parse.
        agent.run = AsyncMock(return_value={
            "reviewer": name,
            "verdict": verdict,
            "issues": issues,
        })
        return agent

    agents.get_agent = MagicMock(side_effect=_get_agent)
    return agents


def _make_store() -> MagicMock:
    """Return a mock store with save_review and create_task."""
    store = MagicMock()
    store.save_review = AsyncMock(return_value=None)
    store.create_task = AsyncMock(return_value="T-supplementary-001")
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_review_fr032_all_pass() -> None:
    """FR-032: 三路并行审查 — all reviewers pass returns a pass verdict.

    Verifies:
    - code, security, and brooks reviewers are all invoked.
    - ReviewResult.verdict is 'pass' when all three return 'pass'.
    - ReviewResult.reviews contains exactly three Review entries.
    """
    config = _make_config()
    agents = _make_agents({"code": "pass", "security": "pass", "brooks": "pass"})
    store = _make_store()

    pipeline = ReviewPipeline(agents=agents, store=store, config=config)
    result = await pipeline.run_review(
        stage="implement",
        artifacts={"files": ["src/main.py"]},
    )

    # All three reviewers must have been called.
    called_names = {c.args[0] for c in agents.get_agent.call_args_list}
    assert "code" in called_names, "code reviewer was not called"
    assert "security" in called_names, "security reviewer was not called"
    assert "brooks" in called_names, "brooks reviewer was not called"

    # Merged verdict must be 'pass'.
    assert isinstance(result, ReviewResult), f"expected ReviewResult, got {type(result)}"
    assert result.verdict == "pass", f"expected verdict='pass', got {result.verdict!r}"

    # Three review records must be returned.
    assert len(result.reviews) == 3, f"expected 3 reviews, got {len(result.reviews)}"
    reviewer_names = {r.reviewer for r in result.reviews}
    assert reviewer_names == {"code", "security", "brooks"}, (
        f"unexpected reviewer names: {reviewer_names}"
    )


@pytest.mark.asyncio
async def test_auto_fix_cycle_fr033_fix_then_pass() -> None:
    """FR-033: 自动修复循环 — fixer is called on failure; only failed reviewers re-run.

    Scenario:
    - security reviewer initially fails; code and brooks pass.
    - fixer agent is invoked and fixes the issue.
    - On re-review only security runs again and returns 'pass'.
    - Final verdict is 'pass'.
    """
    config = _make_config(max_fix_retries=2)

    # First call: security fails. Subsequent calls after fix: all pass.
    security_agent = MagicMock()
    security_agent.run = AsyncMock(side_effect=[
        {"reviewer": "security", "verdict": "fail", "issues": [{"description": "sql injection"}]},
        {"reviewer": "security", "verdict": "pass", "issues": []},
    ])
    code_agent = MagicMock()
    code_agent.run = AsyncMock(return_value={"reviewer": "code", "verdict": "pass", "issues": []})
    brooks_agent = MagicMock()
    brooks_agent.run = AsyncMock(return_value={"reviewer": "brooks", "verdict": "pass", "issues": []})

    fixer_agent = MagicMock()
    fixer_agent.run = AsyncMock(return_value={"status": "fixed", "changes": ["patched query"]})

    def _get_agent(name: str) -> MagicMock:
        return {"code": code_agent, "security": security_agent, "brooks": brooks_agent, "fixer": fixer_agent}[name]

    agents = MagicMock()
    agents.get_agent = MagicMock(side_effect=_get_agent)
    store = _make_store()

    pipeline = ReviewPipeline(agents=agents, store=store, config=config)
    result = await pipeline.run_review(
        stage="implement",
        artifacts={"files": ["src/db.py"]},
    )

    # Fixer must have been called at least once.
    fixer_agent.run.assert_called(), "fixer agent was never called after security fail"

    # code and brooks must each be called exactly once (no redundant re-run).
    assert code_agent.run.call_count == 1, (
        f"code reviewer called {code_agent.run.call_count} times; expected 1"
    )
    assert brooks_agent.run.call_count == 1, (
        f"brooks reviewer called {brooks_agent.run.call_count} times; expected 1"
    )

    # security must be called twice (initial + re-review).
    assert security_agent.run.call_count == 2, (
        f"security reviewer called {security_agent.run.call_count} times; expected 2"
    )

    # Final verdict must be 'pass' after successful fix.
    assert result.verdict == "pass", f"expected verdict='pass' after fix, got {result.verdict!r}"


@pytest.mark.asyncio
async def test_feature_gap_detection_fr034_creates_task() -> None:
    """FR-034: 功能缺口检测 — 'missing' / 'unimplemented' keywords trigger supplementary task.

    Verifies:
    - A review issue containing the word 'missing' triggers task creation.
    - store.create_task is called.
    - ReviewResult.supplementary_tasks is non-empty and follows expected format.
    """
    config = _make_config()
    issues_with_gap = [{"description": "missing authentication handler for /admin"}]
    agents = _make_agents(
        {"code": "fail", "security": "pass", "brooks": "pass"},
        issues_map={"code": issues_with_gap},
    )
    store = _make_store()

    pipeline = ReviewPipeline(agents=agents, store=store, config=config)
    result = await pipeline.run_review(
        stage="implement",
        artifacts={"files": ["src/auth.py"]},
    )

    # store.create_task must have been called to register the supplementary task.
    store.create_task.assert_called(), "store.create_task was not called for feature gap"

    # ReviewResult must expose the supplementary tasks.
    assert len(result.supplementary_tasks) >= 1, (
        "expected at least one supplementary task from feature-gap detection"
    )

    # Each supplementary task must be a non-empty string (task ID or description).
    for task in result.supplementary_tasks:
        assert isinstance(task, str) and task.strip(), (
            f"supplementary task must be a non-empty string, got {task!r}"
        )


@pytest.mark.asyncio
async def test_max_retries_stop_fr033_returns_fail() -> None:
    """FR-033: 达到最大重试次数后停止 — pipeline stops after max_fix_retries.

    Scenario:
    - code reviewer always fails; max_fix_retries=2.
    - Fixer is called exactly max_fix_retries times.
    - Final verdict is 'fail' (no more retries available).
    """
    max_fix_retries = 2
    config = _make_config(max_fix_retries=max_fix_retries)

    code_agent = MagicMock()
    # Always fails regardless of how many times it is called.
    code_agent.run = AsyncMock(return_value={"reviewer": "code", "verdict": "fail", "issues": [{"description": "bad logic"}]})
    security_agent = MagicMock()
    security_agent.run = AsyncMock(return_value={"reviewer": "security", "verdict": "pass", "issues": []})
    brooks_agent = MagicMock()
    brooks_agent.run = AsyncMock(return_value={"reviewer": "brooks", "verdict": "pass", "issues": []})

    fixer_agent = MagicMock()
    fixer_agent.run = AsyncMock(return_value={"status": "attempted", "changes": []})

    def _get_agent(name: str) -> MagicMock:
        return {"code": code_agent, "security": security_agent, "brooks": brooks_agent, "fixer": fixer_agent}[name]

    agents = MagicMock()
    agents.get_agent = MagicMock(side_effect=_get_agent)
    store = _make_store()

    pipeline = ReviewPipeline(agents=agents, store=store, config=config)
    result = await pipeline.run_review(
        stage="implement",
        artifacts={"files": ["src/logic.py"]},
    )

    # Fixer must have been called exactly max_fix_retries times.
    assert fixer_agent.run.call_count == max_fix_retries, (
        f"expected fixer called {max_fix_retries} times, "
        f"got {fixer_agent.run.call_count}"
    )

    # After exhausting retries the verdict must be 'fail'.
    assert result.verdict == "fail", (
        f"expected verdict='fail' after max retries, got {result.verdict!r}"
    )
