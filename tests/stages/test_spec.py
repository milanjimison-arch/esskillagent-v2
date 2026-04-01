"""FR-010 / T010: SpecStage RED phase behavior tests.

All tests in this module are intentionally written to FAIL because
orchestrator/stages/spec.py is a stub (raises NotImplementedError).
They define the required behavior that must be implemented in the GREEN phase.

SpecStage._execute_steps must:
  1. Run constitution → specify → clarify → review in order.
  2. Invoke 'constitution-writer', 'spec-writer', 'clarifier' agents.
  3. Invoke self.ctx.review_pipeline for the review sub-step.
  4. Return an artifacts dict with all four sub-step outputs.
  5. NEVER skip any sub-step regardless of project size.
  6. Propagate exceptions raised by agents without swallowing them.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from orchestrator.stages.base import EngineContext, Stage
from orchestrator.stages.spec import SpecStage


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_agents(
    constitution_output: Any = "constitution text",
    specify_output: Any = "spec text",
    clarify_output: Any = "clarified spec text",
) -> MagicMock:
    """Return a mock agents object whose call_agent dispatches by agent name."""

    async def _call_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
        result = MagicMock()
        if agent_name == "constitution-writer":
            result.text = constitution_output
        elif agent_name == "spec-writer":
            result.text = specify_output
        elif agent_name == "clarifier":
            result.text = clarify_output
        else:
            raise ValueError(f"Unexpected agent: {agent_name!r}")
        return result

    mock_agents = MagicMock()
    mock_agents.call_agent = AsyncMock(side_effect=_call_agent)
    return mock_agents


def _make_ctx(
    *,
    agents: Any = None,
    review_pipeline: Any = None,
    review_output: Any = None,
) -> EngineContext:
    """Build a fully-mocked EngineContext for SpecStage tests."""
    mock_agents = agents if agents is not None else _make_agents()

    if review_pipeline is not None:
        mock_review = review_pipeline
    else:
        mock_review = MagicMock()
        rv = review_output if review_output is not None else {"verdict": "pass", "issues": []}
        mock_review.run_review = AsyncMock(return_value=rv)

    return EngineContext(
        project_path="/fake/project",
        config=MagicMock(),
        store=MagicMock(),
        agents=mock_agents,
        checker=MagicMock(),
        review_pipeline=mock_review,
    )


# ---------------------------------------------------------------------------
# T010-1: SpecStage MUST be a subclass of Stage
# ---------------------------------------------------------------------------

class TestSpecStageInheritance:
    """FR-010: SpecStage MUST extend the Stage base class."""

    def test_FR010_spec_stage_is_subclass_of_stage(self) -> None:
        """FR-010: SpecStage must be a subclass of Stage."""
        assert issubclass(SpecStage, Stage), "SpecStage must extend Stage"

    def test_FR010_spec_stage_instantiates_with_engine_context(self) -> None:
        """FR-010: SpecStage must accept EngineContext in __init__."""
        ctx = _make_ctx()
        stage = SpecStage(ctx)
        assert stage.ctx is ctx

    def test_FR010_spec_stage_has_execute_steps_method(self) -> None:
        """FR-010: _execute_steps must exist as an overridden async method."""
        ctx = _make_ctx()
        stage = SpecStage(ctx)
        assert hasattr(stage, "_execute_steps"), (
            "SpecStage must define _execute_steps"
        )
        assert asyncio.iscoroutinefunction(stage._execute_steps), (
            "_execute_steps must be an async method"
        )


# ---------------------------------------------------------------------------
# T010-2: constitution sub-step is called first
# ---------------------------------------------------------------------------

class TestConstitutionStep:
    """FR-010: The constitution sub-step must be run via 'constitution-writer' agent."""

    @pytest.mark.asyncio
    async def test_FR010_execute_steps_calls_constitution_writer_agent(self) -> None:
        """FR-010: _execute_steps must invoke the 'constitution-writer' agent."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names_called = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert "constitution-writer" in agent_names_called, (
            "_execute_steps must call the 'constitution-writer' agent"
        )

    @pytest.mark.asyncio
    async def test_FR010_constitution_output_included_in_artifacts(self) -> None:
        """FR-010: artifacts dict must contain 'constitution' key with agent output."""
        expected = "The constitution document content"
        mock_agents = _make_agents(constitution_output=expected)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        artifacts = await stage._execute_steps()

        assert "constitution" in artifacts, (
            "artifacts must contain 'constitution' key"
        )
        assert artifacts["constitution"] == expected, (
            "artifacts['constitution'] must equal the constitution-writer agent output"
        )


# ---------------------------------------------------------------------------
# T010-3: specify sub-step is called second
# ---------------------------------------------------------------------------

class TestSpecifyStep:
    """FR-010: The specify sub-step must be run via 'spec-writer' agent."""

    @pytest.mark.asyncio
    async def test_FR010_execute_steps_calls_spec_writer_agent(self) -> None:
        """FR-010: _execute_steps must invoke the 'spec-writer' agent."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names_called = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert "spec-writer" in agent_names_called, (
            "_execute_steps must call the 'spec-writer' agent"
        )

    @pytest.mark.asyncio
    async def test_FR010_specify_output_included_in_artifacts(self) -> None:
        """FR-010: artifacts dict must contain 'spec' key with agent output."""
        expected = "Full specification document"
        mock_agents = _make_agents(specify_output=expected)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        artifacts = await stage._execute_steps()

        assert "spec" in artifacts, "artifacts must contain 'spec' key"
        assert artifacts["spec"] == expected, (
            "artifacts['spec'] must equal the spec-writer agent output"
        )


# ---------------------------------------------------------------------------
# T010-4: clarify sub-step is called third
# ---------------------------------------------------------------------------

class TestClarifyStep:
    """FR-010: The clarify sub-step must be run via 'clarifier' agent."""

    @pytest.mark.asyncio
    async def test_FR010_execute_steps_calls_clarifier_agent(self) -> None:
        """FR-010: _execute_steps must invoke the 'clarifier' agent."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names_called = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert "clarifier" in agent_names_called, (
            "_execute_steps must call the 'clarifier' agent"
        )

    @pytest.mark.asyncio
    async def test_FR010_clarify_output_included_in_artifacts(self) -> None:
        """FR-010: artifacts dict must contain 'clarification' key with agent output."""
        expected = "Clarified and refined specification"
        mock_agents = _make_agents(clarify_output=expected)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        artifacts = await stage._execute_steps()

        assert "clarification" in artifacts, (
            "artifacts must contain 'clarification' key"
        )
        assert artifacts["clarification"] == expected, (
            "artifacts['clarification'] must equal the clarifier agent output"
        )


# ---------------------------------------------------------------------------
# T010-5: review sub-step is called fourth via review_pipeline
# ---------------------------------------------------------------------------

class TestReviewStep:
    """FR-010: The review sub-step must be run via self.ctx.review_pipeline."""

    @pytest.mark.asyncio
    async def test_FR010_execute_steps_calls_review_pipeline(self) -> None:
        """FR-010: _execute_steps must invoke self.ctx.review_pipeline.run_review."""
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(
            return_value={"verdict": "pass", "issues": []}
        )
        ctx = _make_ctx(review_pipeline=mock_review)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        mock_review.run_review.assert_called_once(), (
            "review_pipeline.run_review must be called exactly once"
        )

    @pytest.mark.asyncio
    async def test_FR010_review_output_included_in_artifacts(self) -> None:
        """FR-010: artifacts dict must contain 'review' key with review_pipeline output."""
        expected_review = {"verdict": "pass", "issues": [], "score": 98}
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(return_value=expected_review)
        ctx = _make_ctx(review_pipeline=mock_review)
        stage = SpecStage(ctx)

        artifacts = await stage._execute_steps()

        assert "review" in artifacts, "artifacts must contain 'review' key"
        assert artifacts["review"] == expected_review, (
            "artifacts['review'] must equal the review_pipeline.run_review output"
        )


# ---------------------------------------------------------------------------
# T010-6: sub-steps execute in strict order: constitution → specify → clarify → review
# ---------------------------------------------------------------------------

class TestSubStepOrdering:
    """FR-010: Sub-steps MUST run in order: constitution → specify → clarify → review."""

    @pytest.mark.asyncio
    async def test_FR010_constitution_called_before_specify(self) -> None:
        """FR-010: 'constitution-writer' must be called before 'spec-writer'."""
        call_order: list[str] = []

        async def _call_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            call_order.append(agent_name)
            result = MagicMock()
            result.text = f"{agent_name} output"
            return result

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_call_agent)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        assert "constitution-writer" in call_order, "constitution-writer must be called"
        assert "spec-writer" in call_order, "spec-writer must be called"
        assert call_order.index("constitution-writer") < call_order.index("spec-writer"), (
            "'constitution-writer' must be called before 'spec-writer'"
        )

    @pytest.mark.asyncio
    async def test_FR010_specify_called_before_clarify(self) -> None:
        """FR-010: 'spec-writer' must be called before 'clarifier'."""
        call_order: list[str] = []

        async def _call_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            call_order.append(agent_name)
            result = MagicMock()
            result.text = f"{agent_name} output"
            return result

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_call_agent)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        assert call_order.index("spec-writer") < call_order.index("clarifier"), (
            "'spec-writer' must be called before 'clarifier'"
        )

    @pytest.mark.asyncio
    async def test_FR010_clarify_called_before_review_pipeline(self) -> None:
        """FR-010: 'clarifier' agent must be called before review_pipeline.run_review."""
        call_order: list[str] = []

        async def _call_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            call_order.append(agent_name)
            result = MagicMock()
            result.text = f"{agent_name} output"
            return result

        async def _run_review(*args: Any, **kwargs: Any) -> dict:
            call_order.append("review_pipeline")
            return {"verdict": "pass", "issues": []}

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_call_agent)
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(side_effect=_run_review)
        ctx = _make_ctx(agents=mock_agents, review_pipeline=mock_review)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        assert "clarifier" in call_order, "clarifier must be called"
        assert "review_pipeline" in call_order, "review_pipeline must be called"
        assert call_order.index("clarifier") < call_order.index("review_pipeline"), (
            "'clarifier' must finish before review_pipeline.run_review is called"
        )

    @pytest.mark.asyncio
    async def test_FR010_all_four_sub_steps_called_in_full_sequence(self) -> None:
        """FR-010: all four sub-steps must appear in the exact sequence."""
        call_order: list[str] = []

        async def _call_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            call_order.append(agent_name)
            result = MagicMock()
            result.text = f"{agent_name} output"
            return result

        async def _run_review(*args: Any, **kwargs: Any) -> dict:
            call_order.append("review_pipeline")
            return {"verdict": "pass", "issues": []}

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_call_agent)
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(side_effect=_run_review)
        ctx = _make_ctx(agents=mock_agents, review_pipeline=mock_review)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        expected_sequence = [
            "constitution-writer",
            "spec-writer",
            "clarifier",
            "review_pipeline",
        ]
        assert call_order == expected_sequence, (
            f"Sub-steps must run in exact order {expected_sequence}, got {call_order}"
        )


# ---------------------------------------------------------------------------
# T010-7: artifacts dict structure
# ---------------------------------------------------------------------------

class TestArtifactsDict:
    """FR-010: _execute_steps must return a properly structured artifacts dict."""

    @pytest.mark.asyncio
    async def test_FR010_execute_steps_returns_dict(self) -> None:
        """FR-010: _execute_steps must return a dict."""
        ctx = _make_ctx()
        stage = SpecStage(ctx)

        result = await stage._execute_steps()

        assert isinstance(result, dict), "_execute_steps must return a dict"

    @pytest.mark.asyncio
    async def test_FR010_artifacts_contains_all_four_keys(self) -> None:
        """FR-010: artifacts dict must have constitution, spec, clarification, review."""
        ctx = _make_ctx()
        stage = SpecStage(ctx)

        result = await stage._execute_steps()

        required_keys = {"constitution", "spec", "clarification", "review"}
        missing = required_keys - result.keys()
        assert not missing, (
            f"artifacts dict is missing keys: {missing}"
        )

    @pytest.mark.asyncio
    async def test_FR010_artifacts_values_are_not_none(self) -> None:
        """FR-010: none of the four artifact values may be None."""
        ctx = _make_ctx()
        stage = SpecStage(ctx)

        result = await stage._execute_steps()

        for key in ("constitution", "spec", "clarification", "review"):
            assert result[key] is not None, (
                f"artifacts['{key}'] must not be None"
            )


# ---------------------------------------------------------------------------
# T010-8: No skip logic — all sub-steps always run
# ---------------------------------------------------------------------------

class TestNoSkipLogic:
    """FR-010: All four sub-steps MUST always execute; there is no skip logic."""

    @pytest.mark.asyncio
    async def test_FR010_constitution_always_called(self) -> None:
        """FR-010: constitution-writer must always be called with no conditions."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert agent_names.count("constitution-writer") == 1, (
            "'constitution-writer' must be called exactly once — no skip path"
        )

    @pytest.mark.asyncio
    async def test_FR010_spec_writer_always_called(self) -> None:
        """FR-010: spec-writer must always be called with no conditions."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert agent_names.count("spec-writer") == 1, (
            "'spec-writer' must be called exactly once — no skip path"
        )

    @pytest.mark.asyncio
    async def test_FR010_clarifier_always_called(self) -> None:
        """FR-010: clarifier must always be called with no conditions."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        agent_names = [
            c.kwargs.get("agent_name") or (c.args[1] if len(c.args) > 1 else None)
            for c in mock_agents.call_agent.call_args_list
        ]
        assert agent_names.count("clarifier") == 1, (
            "'clarifier' must be called exactly once — no skip path"
        )

    @pytest.mark.asyncio
    async def test_FR010_review_pipeline_always_called(self) -> None:
        """FR-010: review_pipeline.run_review must always be called with no conditions."""
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(
            return_value={"verdict": "pass", "issues": []}
        )
        ctx = _make_ctx(review_pipeline=mock_review)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        assert mock_review.run_review.call_count == 1, (
            "review_pipeline.run_review must be called exactly once — no skip path"
        )

    @pytest.mark.asyncio
    async def test_FR010_exactly_three_agent_calls_total(self) -> None:
        """FR-010: exactly three agent calls must be made (one per agent sub-step)."""
        mock_agents = _make_agents()
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        await stage._execute_steps()

        assert mock_agents.call_agent.call_count == 3, (
            f"Expected exactly 3 agent calls "
            f"(constitution-writer + spec-writer + clarifier), "
            f"got {mock_agents.call_agent.call_count}"
        )


# ---------------------------------------------------------------------------
# T010-9: Exception propagation
# ---------------------------------------------------------------------------

class TestExceptionPropagation:
    """FR-010: exceptions raised by agents must propagate, not be swallowed."""

    @pytest.mark.asyncio
    async def test_FR010_constitution_writer_failure_propagates(self) -> None:
        """FR-010: if 'constitution-writer' raises, _execute_steps must re-raise."""
        class ConstitutionError(RuntimeError):
            pass

        async def _failing_agent(prompt: str, agent_name: str, **kwargs: Any) -> None:
            if agent_name == "constitution-writer":
                raise ConstitutionError("constitution agent failed")
            result = MagicMock()
            result.text = "ok"
            return result

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_failing_agent)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        with pytest.raises(ConstitutionError):
            await stage._execute_steps()

    @pytest.mark.asyncio
    async def test_FR010_spec_writer_failure_propagates(self) -> None:
        """FR-010: if 'spec-writer' raises, _execute_steps must re-raise."""
        class SpecWriterError(RuntimeError):
            pass

        async def _failing_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            if agent_name == "spec-writer":
                raise SpecWriterError("spec-writer agent failed")
            result = MagicMock()
            result.text = "ok"
            return result

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_failing_agent)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        with pytest.raises(SpecWriterError):
            await stage._execute_steps()

    @pytest.mark.asyncio
    async def test_FR010_clarifier_failure_propagates(self) -> None:
        """FR-010: if 'clarifier' raises, _execute_steps must re-raise."""
        class ClarifierError(RuntimeError):
            pass

        async def _failing_agent(prompt: str, agent_name: str, **kwargs: Any) -> MagicMock:
            if agent_name == "clarifier":
                raise ClarifierError("clarifier agent failed")
            result = MagicMock()
            result.text = "ok"
            return result

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(side_effect=_failing_agent)
        ctx = _make_ctx(agents=mock_agents)
        stage = SpecStage(ctx)

        with pytest.raises(ClarifierError):
            await stage._execute_steps()

    @pytest.mark.asyncio
    async def test_FR010_review_pipeline_failure_propagates(self) -> None:
        """FR-010: if review_pipeline.run_review raises, _execute_steps must re-raise."""
        class ReviewError(RuntimeError):
            pass

        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(side_effect=ReviewError("review failed"))
        ctx = _make_ctx(review_pipeline=mock_review)
        stage = SpecStage(ctx)

        with pytest.raises(ReviewError):
            await stage._execute_steps()


