"""Tests for AcceptanceStage — TDD RED phase.

FR-014: The acceptance stage MUST produce a traceability matrix
        (FR to Task to Test) and complete a final review gate.
FR-015: Each stage MUST share common review, gate, and checkpoint logic
        via a Stage base class.

All tests in this file MUST FAIL before AcceptanceStage is implemented.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from orchestrator.stages.acceptance import AcceptanceStage
from orchestrator.stages.base import EngineContext, Stage


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_ctx(
    project_path: str | None = None,
    *,
    tmp_path: Path | None = None,
    tasks: list[dict] | None = None,
    config: Any = None,
    store: Any = None,
    agents: Any = None,
    checker: Any = None,
    review_pipeline: Any = None,
) -> EngineContext:
    """Build a minimal EngineContext with sane mock defaults."""
    _project_path = str(tmp_path) if tmp_path else (project_path or "/fake/project")

    mock_store = store or MagicMock()
    mock_store.get_all_tasks.return_value = tasks or []
    mock_store.get_task_status = MagicMock(side_effect=lambda tid: "green")

    mock_config = config or MagicMock()
    mock_config.max_fix_retries = 2

    mock_agents = agents or MagicMock()
    mock_checker = checker or MagicMock()
    mock_review = review_pipeline or MagicMock()
    mock_review.run_review = AsyncMock(return_value=MagicMock(passed=True))

    return EngineContext(
        project_path=_project_path,
        config=mock_config,
        store=mock_store,
        agents=mock_agents,
        checker=mock_checker,
        review_pipeline=mock_review,
    )


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal fake project tree used by traceability tests."""
    # Minimal spec.md with FR references
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "spec.md").write_text(
        "# Spec\n\n"
        "- **FR-001**: System MUST load configuration.\n"
        "- **FR-002**: System MUST support project-level config.\n"
        "- **FR-014**: Acceptance stage MUST produce traceability matrix.\n",
        encoding="utf-8",
    )
    # Minimal tasks.md
    (specs_dir / "tasks.md").write_text(
        "- [ ] T001 [US4] [FR-001][FR-002] Config system — orchestrator/config.py\n"
        "- [ ] T014 [US1] [FR-014] Acceptance stage — orchestrator/stages/acceptance.py\n",
        encoding="utf-8",
    )
    # A test file referencing FR-001
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_config.py").write_text(
        "# FR-001: test config loading\n\ndef test_defaults_loaded(): pass\n",
        encoding="utf-8",
    )
    # checklists dir
    (specs_dir / "checklists").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# T014-1: AcceptanceStage MUST extend Stage base class
# ---------------------------------------------------------------------------

class TestAcceptanceStageInheritance:
    """FR-015: AcceptanceStage MUST extend the Stage base class."""

    def test_FR014_acceptance_stage_is_subclass_of_stage(self) -> None:
        """FR-014/FR-015: AcceptanceStage must be a subclass of Stage."""
        assert issubclass(AcceptanceStage, Stage), (
            "AcceptanceStage must extend Stage"
        )

    def test_FR014_acceptance_stage_instantiates_with_engine_context(
        self, tmp_path: Path
    ) -> None:
        """FR-014: AcceptanceStage must accept EngineContext in __init__."""
        ctx = _make_ctx(tmp_path=tmp_path)
        stage = AcceptanceStage(ctx)
        assert stage.ctx is ctx

    def test_FR014_acceptance_stage_has_execute_steps_method(
        self, tmp_path: Path
    ) -> None:
        """FR-015: _execute_steps must exist as an overridden async method."""
        ctx = _make_ctx(tmp_path=tmp_path)
        stage = AcceptanceStage(ctx)
        assert hasattr(stage, "_execute_steps"), (
            "AcceptanceStage must define _execute_steps"
        )
        assert asyncio.iscoroutinefunction(stage._execute_steps), (
            "_execute_steps must be an async method"
        )

    def test_FR014_acceptance_stage_has_run_method_from_base(
        self, tmp_path: Path
    ) -> None:
        """FR-015: AcceptanceStage must inherit the run() template method."""
        ctx = _make_ctx(tmp_path=tmp_path)
        stage = AcceptanceStage(ctx)
        assert hasattr(stage, "run"), "run() must be inherited from Stage"
        assert asyncio.iscoroutinefunction(stage.run), "run() must be async"


# ---------------------------------------------------------------------------
# T014-2: _execute_steps MUST run the acceptor agent
# ---------------------------------------------------------------------------

class TestAcceptanceStageRunsAcceptorAgent:
    """FR-014: _execute_steps must invoke the acceptor agent."""

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_calls_acceptor_agent(
        self, tmp_path: Path
    ) -> None:
        """FR-014: _execute_steps must call the acceptor agent exactly once."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED\nAll checks passed.")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        mock_agents.call_agent.assert_called_once()
        call_kwargs = mock_agents.call_agent.call_args
        # acceptor agent must be identified by name
        agent_name = (
            call_kwargs.kwargs.get("agent_name")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        )
        assert agent_name == "acceptor", (
            f"_execute_steps must invoke the 'acceptor' agent, got {agent_name!r}"
        )

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_passes_project_path_to_agent(
        self, tmp_path: Path
    ) -> None:
        """FR-014: acceptor agent must receive the project path in its prompt."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        prompt_arg = (
            mock_agents.call_agent.call_args.args[0]
            if mock_agents.call_agent.call_args.args
            else mock_agents.call_agent.call_args.kwargs.get("prompt", "")
        )
        assert str(tmp_path) in prompt_arg, (
            "The acceptor agent prompt must include the project path"
        )

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_returns_artifacts_dict(
        self, tmp_path: Path
    ) -> None:
        """FR-014: _execute_steps must return a dict of artifacts."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        result = await stage._execute_steps()

        assert isinstance(result, dict), (
            "_execute_steps must return a dict of artifacts"
        )

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_includes_acceptor_output_in_artifacts(
        self, tmp_path: Path
    ) -> None:
        """FR-014: artifacts dict must include acceptor agent output."""
        expected_output = "VERDICT: APPROVED\nAll acceptance checks passed."
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text=expected_output)
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        artifacts = await stage._execute_steps()

        assert "acceptor_output" in artifacts, (
            "artifacts must contain 'acceptor_output' key"
        )
        assert artifacts["acceptor_output"] == expected_output


# ---------------------------------------------------------------------------
# T014-3: Traceability matrix generation (FR → Task → Test)
# ---------------------------------------------------------------------------

class TestTraceabilityMatrixGeneration:
    """FR-014: Generate traceability matrix mapping FR to Task to Test."""

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_generates_traceability_file(
        self, tmp_project: Path
    ) -> None:
        """FR-014: _execute_steps must create specs/checklists/traceability.md."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        traceability_path = tmp_project / "specs" / "checklists" / "traceability.md"
        assert traceability_path.exists(), (
            "specs/checklists/traceability.md must be created by _execute_steps"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_contains_fr_references(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must list FR identifiers from spec.md."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        assert "FR-001" in content, "traceability.md must reference FR-001 from spec.md"
        assert "FR-002" in content, "traceability.md must reference FR-002 from spec.md"
        assert "FR-014" in content, "traceability.md must reference FR-014 from spec.md"

    @pytest.mark.asyncio
    async def test_FR014_traceability_contains_task_references(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must map FRs to their implementing tasks."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        # T001 maps to FR-001/FR-002; T014 maps to FR-014
        assert "T001" in content, "traceability.md must reference task T001"
        assert "T014" in content, "traceability.md must reference task T014"

    @pytest.mark.asyncio
    async def test_FR014_traceability_contains_test_file_references(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must reference test files covering each FR."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        # test_config.py references FR-001
        assert "test_config.py" in content, (
            "traceability.md must include test files that reference each FR"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_is_markdown_table(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must use a markdown table format."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        # A markdown table must have at least one pipe-delimited row
        assert "|" in content, "traceability.md must use a markdown table with | separators"
        # Must have a header row separator (---|--- pattern)
        assert "---" in content, (
            "traceability.md markdown table must have a header separator row"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_has_title_header(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must start with a heading."""
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        assert content.startswith("# "), (
            "traceability.md must begin with a markdown H1 heading"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_creates_parent_directories(
        self, tmp_path: Path
    ) -> None:
        """FR-014: traceability.md parent dirs must be created if absent."""
        # Only create spec.md, no checklists/ dir, no tasks.md
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec.md").write_text(
            "# Spec\n- **FR-001**: load config.\n", encoding="utf-8"
        )
        (specs_dir / "tasks.md").write_text(
            "- [ ] T001 [FR-001] Config — orchestrator/config.py\n",
            encoding="utf-8",
        )
        # checklists/ dir deliberately NOT created

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        assert (tmp_path / "specs" / "checklists" / "traceability.md").exists(), (
            "specs/checklists/ must be created automatically if it does not exist"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_skipped_gracefully_when_spec_missing(
        self, tmp_path: Path
    ) -> None:
        """FR-014: when spec.md is absent, _execute_steps must not raise."""
        # No spec.md, no tasks.md created
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        # Must not raise even with missing spec.md
        try:
            await stage._execute_steps()
        except NotImplementedError:
            pytest.fail(
                "_execute_steps raised NotImplementedError — not yet implemented"
            )
        except Exception as exc:
            pytest.fail(
                f"_execute_steps raised unexpected {type(exc).__name__} when "
                f"spec.md is missing: {exc}"
            )

    @pytest.mark.asyncio
    async def test_FR014_traceability_includes_task_status(
        self, tmp_project: Path
    ) -> None:
        """FR-014: traceability.md must show the status of each mapped task."""
        mock_store = MagicMock()
        mock_store.get_all_tasks.return_value = []
        mock_store.get_task_status = MagicMock(side_effect=lambda tid: "green")

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(
            tmp_path=tmp_project, agents=mock_agents, store=mock_store
        )
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        # "green" status must appear for tasks that have been completed
        assert "green" in content.lower(), (
            "traceability.md must include task status (e.g. 'green') for each task"
        )


# ---------------------------------------------------------------------------
# T014-4: Final review gate
# ---------------------------------------------------------------------------

class TestFinalReviewGate:
    """FR-014: _execute_steps (or run()) must complete a final review gate."""

    @pytest.mark.asyncio
    async def test_FR014_run_invokes_review_pipeline(
        self, tmp_project: Path
    ) -> None:
        """FR-014/FR-015: run() must call the review pipeline."""
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(
            return_value=MagicMock(passed=True, findings=[])
        )
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(
            tmp_path=tmp_project,
            agents=mock_agents,
            review_pipeline=mock_review,
        )
        stage = AcceptanceStage(ctx)

        await stage.run()

        mock_review.run_review.assert_called_once(), (
            "run() must invoke review_pipeline.run_review exactly once"
        )

    @pytest.mark.asyncio
    async def test_FR014_run_passes_artifacts_to_review(
        self, tmp_project: Path
    ) -> None:
        """FR-014/FR-015: run() must pass the stage artifacts to the review pipeline."""
        captured_calls: list[Any] = []

        async def fake_run_review(stage_name: str, artifacts: dict) -> Any:
            captured_calls.append((stage_name, artifacts))
            return MagicMock(passed=True, findings=[])

        mock_review = MagicMock()
        mock_review.run_review = fake_run_review

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(
            tmp_path=tmp_project,
            agents=mock_agents,
            review_pipeline=mock_review,
        )
        stage = AcceptanceStage(ctx)

        await stage.run()

        assert len(captured_calls) == 1, "run_review must be called exactly once"
        stage_name, artifacts = captured_calls[0]
        assert stage_name == "acceptance", (
            f"stage name passed to run_review must be 'acceptance', got {stage_name!r}"
        )
        assert isinstance(artifacts, dict), (
            "artifacts passed to run_review must be a dict"
        )

    @pytest.mark.asyncio
    async def test_FR014_run_saves_checkpoint_on_gate_pass(
        self, tmp_project: Path
    ) -> None:
        """FR-014/FR-015: run() must save a checkpoint when review gate passes."""
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(
            return_value=MagicMock(passed=True, findings=[])
        )
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        mock_store = MagicMock()
        mock_store.get_all_tasks.return_value = []
        mock_store.get_task_status = MagicMock(return_value="green")
        mock_store.save_checkpoint = MagicMock()

        ctx = _make_ctx(
            tmp_path=tmp_project,
            agents=mock_agents,
            review_pipeline=mock_review,
            store=mock_store,
        )
        stage = AcceptanceStage(ctx)

        await stage.run()

        mock_store.save_checkpoint.assert_called_once(), (
            "run() must save a checkpoint to the store when the review gate passes"
        )

    @pytest.mark.asyncio
    async def test_FR014_run_gate_fail_does_not_save_checkpoint(
        self, tmp_project: Path
    ) -> None:
        """FR-014/FR-015: run() must NOT save a checkpoint when gate fails."""
        mock_review = MagicMock()
        mock_review.run_review = AsyncMock(
            return_value=MagicMock(passed=False, findings=["Critical issue found"])
        )
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: NEEDS_REVISION\nIssues: ...")
        )
        mock_store = MagicMock()
        mock_store.get_all_tasks.return_value = []
        mock_store.get_task_status = MagicMock(return_value="green")
        mock_store.save_checkpoint = MagicMock()

        ctx = _make_ctx(
            tmp_path=tmp_project,
            agents=mock_agents,
            review_pipeline=mock_review,
            store=mock_store,
        )
        stage = AcceptanceStage(ctx)

        # Gate failure should either raise or not save checkpoint
        try:
            await stage.run()
        except Exception:
            pass  # Gate failure may raise — that is acceptable

        mock_store.save_checkpoint.assert_not_called(), (
            "run() must NOT save a checkpoint when the review gate fails"
        )

    @pytest.mark.asyncio
    async def test_FR014_gate_passes_acceptance_stage_name(
        self, tmp_project: Path
    ) -> None:
        """FR-014: the gate check must identify the 'acceptance' stage."""
        recorded: list[str] = []

        async def fake_run_review(stage_name: str, artifacts: dict) -> Any:
            recorded.append(stage_name)
            return MagicMock(passed=True, findings=[])

        mock_review = MagicMock()
        mock_review.run_review = fake_run_review
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(
            tmp_path=tmp_project,
            agents=mock_agents,
            review_pipeline=mock_review,
        )
        stage = AcceptanceStage(ctx)

        await stage.run()

        assert "acceptance" in recorded, (
            "The review gate must be invoked with the stage name 'acceptance'"
        )


# ---------------------------------------------------------------------------
# T014-5: Edge cases
# ---------------------------------------------------------------------------

class TestAcceptanceStageEdgeCases:
    """Edge cases for AcceptanceStage."""

    @pytest.mark.asyncio
    async def test_FR014_traceability_no_frs_in_spec(
        self, tmp_path: Path
    ) -> None:
        """FR-014: when spec.md exists but has no FR-### references, skip matrix silently."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec.md").write_text(
            "# Spec\nNo functional requirements listed here.\n",
            encoding="utf-8",
        )
        (specs_dir / "tasks.md").write_text(
            "- [ ] T001 Description — orchestrator/config.py\n",
            encoding="utf-8",
        )
        (specs_dir / "checklists").mkdir()

        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_path, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        # Must not raise
        try:
            await stage._execute_steps()
        except NotImplementedError:
            pytest.fail("_execute_steps is not yet implemented")
        except Exception as exc:
            pytest.fail(
                f"_execute_steps raised unexpected {type(exc).__name__} "
                f"when no FR refs in spec: {exc}"
            )

    @pytest.mark.asyncio
    async def test_FR014_traceability_excludes_node_modules(
        self, tmp_project: Path
    ) -> None:
        """FR-014: test file scan must exclude node_modules/ directories."""
        # Create a test file inside node_modules that references FR-001
        node_mods = tmp_project / "node_modules" / "some-pkg"
        node_mods.mkdir(parents=True)
        (node_mods / "test_something.py").write_text(
            "# FR-001 reference inside node_modules\n", encoding="utf-8"
        )
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        assert "node_modules" not in content, (
            "traceability.md must not include test files from node_modules/"
        )

    @pytest.mark.asyncio
    async def test_FR014_traceability_excludes_workflow_dir(
        self, tmp_project: Path
    ) -> None:
        """FR-014: test file scan must exclude .workflow/ orchestrator-internal paths."""
        workflow_dir = tmp_project / ".workflow"
        workflow_dir.mkdir(exist_ok=True)
        (workflow_dir / "test_internal.py").write_text(
            "# FR-001 reference inside .workflow\n", encoding="utf-8"
        )
        mock_agents = MagicMock()
        mock_agents.call_agent = AsyncMock(
            return_value=MagicMock(text="VERDICT: APPROVED")
        )
        ctx = _make_ctx(tmp_path=tmp_project, agents=mock_agents)
        stage = AcceptanceStage(ctx)

        await stage._execute_steps()

        content = (
            tmp_project / "specs" / "checklists" / "traceability.md"
        ).read_text(encoding="utf-8")
        assert ".workflow" not in content, (
            "traceability.md must not reference .workflow/ internal paths"
        )

    @pytest.mark.asyncio
    async def test_FR014_execute_steps_not_implemented_raises_not_implemented_error(
        self, tmp_path: Path
    ) -> None:
        """Confirm the stub raises NotImplementedError (validates RED state)."""
        ctx = _make_ctx(tmp_path=tmp_path)
        stage = AcceptanceStage(ctx)

        with pytest.raises(NotImplementedError):
            await stage._execute_steps()

    @pytest.mark.asyncio
    async def test_FR014_run_not_implemented_raises_not_implemented_error(
        self, tmp_path: Path
    ) -> None:
        """Confirm run() stub raises NotImplementedError (validates RED state)."""
        ctx = _make_ctx(tmp_path=tmp_path)
        stage = AcceptanceStage(ctx)

        with pytest.raises(NotImplementedError):
            await stage.run()
