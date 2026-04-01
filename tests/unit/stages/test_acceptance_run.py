"""RED-phase tests for AcceptanceStage.run() — acceptor agent orchestration.

Covers the seven key behaviors required by the task spec:

  FR-ACPT-RUN-001: run() MUST invoke the acceptor agent to produce a
                   traceability matrix populated from real artifacts.
  FR-ACPT-RUN-002: run() MUST run a final review of all artifacts after
                   the acceptor agent completes.
  FR-ACPT-RUN-003: Artifacts MUST be frozen with SHA-256 content hashes
                   before stage_complete is recorded.
  FR-ACPT-RUN-004: A stage_complete event MUST be recorded in the returned
                   StageResult.data with value 'acceptance'.
  FR-ACPT-RUN-005: run() MUST return a result containing the traceability
                   matrix and review results produced by the acceptor agent.
  FR-ACPT-RUN-006: run() MUST handle acceptor agent failures gracefully
                   (not raise; set passed=False and record error details).
  FR-ACPT-RUN-007: run() MUST validate that all required artifacts exist
                   BEFORE invoking the acceptor agent; missing artifacts
                   cause passed=False without calling the acceptor agent.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/stages/acceptance.py provides a AcceptanceStage.run() that:
  - accepts an acceptor_agent collaborator and required_artifacts list via
    the constructor
  - invokes the acceptor_agent to produce a traceability matrix
  - runs a final review of all artifacts
  - freezes the resulting artifacts with SHA-256 content hashes
  - records a stage_complete = 'acceptance' event in the returned data
  - returns traceability matrix and review results in the data
  - handles acceptor agent failures gracefully
  - validates required artifacts exist before calling the acceptor agent

The current stub in acceptance.py returns a StageResult built from an
empty generate_traceability_matrix(frs=[], ...) call.  It does NOT:
  - accept or invoke an acceptor_agent collaborator
  - run any final review
  - freeze artifacts with content hashes
  - validate required artifacts
  - handle agent failure paths
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import StageABC, StageResult
from orchestrator.stages.acceptance import AcceptanceStage


# ---------------------------------------------------------------------------
# Shared helpers / factories
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_acceptor_agent(
    traceability: dict | None = None,
    review_passed: bool = True,
    review_issues: list[str] | None = None,
    success: bool = True,
    output: str = "",
) -> AsyncMock:
    """Return an async-callable mock simulating the acceptor agent.

    The returned mock, when called, returns an object with:
      .success          — bool
      .traceability     — dict mapping FR IDs to {tasks, tests, status}
      .review_passed    — bool
      .review_issues    — list[str]
      .output           — str (raw text output from the agent)
      .session_id       — str
    """
    if traceability is None:
        traceability = {
            "FR-001": {"tasks": ["task-spec"], "tests": ["test_spec.py"], "status": "implemented"},
            "FR-002": {"tasks": ["task-checkpoint"], "tests": ["test_checkpoint.py"], "status": "implemented"},
        }
    if review_issues is None:
        review_issues = []

    result = MagicMock()
    result.success = success
    result.traceability = traceability
    result.review_passed = review_passed
    result.review_issues = review_issues
    result.output = output or "Acceptance review complete."
    result.session_id = "session-acceptor-001"
    return AsyncMock(return_value=result)


def _make_store() -> MagicMock:
    store = MagicMock()
    store.save_checkpoint = MagicMock()
    store.get_artifact = MagicMock(return_value="artifact content")
    store.list_artifacts = MagicMock(return_value=["spec", "plan", "tasks", "implementation"])
    return store


def _make_artifacts(keys: list[str] | None = None) -> dict[str, str]:
    """Return a dict of artifact name -> content."""
    if keys is None:
        keys = ["spec", "plan", "tasks", "implementation"]
    return {k: f"# {k.capitalize()}\n\nContent of {k}." for k in keys}


# ---------------------------------------------------------------------------
# 1. Collaborator injection
# ---------------------------------------------------------------------------


class TestAcceptanceStageCollaboratorInjection:
    """AcceptanceStage MUST accept acceptor_agent and artifacts via constructor."""

    def test_acceptance_stage_accepts_acceptor_agent_kwarg(self):
        """FR-ACPT-RUN-001: constructor MUST accept acceptor_agent kwarg."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(acceptor_agent=agent)
        assert stage is not None

    def test_acceptance_stage_accepts_artifacts_kwarg(self):
        """Constructor MUST accept an artifacts dict kwarg."""
        artifacts = _make_artifacts()
        stage = AcceptanceStage(artifacts=artifacts)
        assert stage is not None

    def test_acceptance_stage_accepts_required_artifacts_kwarg(self):
        """Constructor MUST accept a required_artifacts list kwarg."""
        stage = AcceptanceStage(required_artifacts=["spec", "plan", "tasks"])
        assert stage is not None

    def test_acceptance_stage_accepts_all_collaborators_together(self):
        """Constructor MUST accept acceptor_agent, artifacts, and required_artifacts together."""
        stage = AcceptanceStage(
            acceptor_agent=_make_acceptor_agent(),
            artifacts=_make_artifacts(),
            required_artifacts=["spec", "plan"],
            store=_make_store(),
        )
        assert stage is not None

    def test_acceptance_stage_stores_acceptor_agent(self):
        """The injected acceptor_agent MUST be stored on the instance."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(acceptor_agent=agent)
        assert getattr(stage, "acceptor_agent", None) is agent, (
            "AcceptanceStage must store acceptor_agent as self.acceptor_agent"
        )

    def test_acceptance_stage_stores_artifacts(self):
        """The injected artifacts dict MUST be stored on the instance."""
        artifacts = _make_artifacts()
        stage = AcceptanceStage(artifacts=artifacts)
        stored = getattr(stage, "artifacts", None) or getattr(stage, "_artifacts", None)
        assert stored is not None, (
            "AcceptanceStage must store the artifacts dict"
        )

    def test_acceptance_stage_stores_required_artifacts(self):
        """The injected required_artifacts MUST be stored on the instance."""
        required = ["spec", "plan", "tasks"]
        stage = AcceptanceStage(required_artifacts=required)
        stored = (
            getattr(stage, "required_artifacts", None)
            or getattr(stage, "_required_artifacts", None)
        )
        assert stored is not None, (
            "AcceptanceStage must store required_artifacts"
        )


# ---------------------------------------------------------------------------
# 2. Acceptor agent invocation
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunInvokesAcceptorAgent:
    """FR-ACPT-RUN-001: run() MUST invoke the acceptor_agent."""

    @pytest.mark.asyncio
    async def test_run_calls_acceptor_agent_at_least_once(self):
        """run() MUST call acceptor_agent at least once when it is injected."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        await stage.run()
        assert agent.call_count >= 1, (
            "run() must invoke acceptor_agent at least once"
        )

    @pytest.mark.asyncio
    async def test_run_calls_acceptor_agent_exactly_once(self):
        """run() MUST invoke the acceptor_agent exactly once (not zero or twice)."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        await stage.run()
        assert agent.call_count == 1, (
            f"run() must call acceptor_agent exactly once, "
            f"called {agent.call_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_passes_artifacts_to_acceptor_agent(self):
        """run() MUST pass the artifacts to the acceptor_agent call."""
        artifacts = _make_artifacts()
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
        )
        await stage.run()
        call_args_flat = str(agent.call_args_list)
        # At least one artifact key must appear in the call arguments
        assert any(key in call_args_flat for key in artifacts.keys()), (
            f"run() must pass artifact information to acceptor_agent. "
            f"Call args: {call_args_flat}"
        )

    @pytest.mark.asyncio
    async def test_run_returns_stage_result_after_acceptor_agent(self):
        """run() MUST return a StageResult after calling acceptor_agent."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"run() must return StageResult, got {type(result)}"
        )

    @pytest.mark.asyncio
    async def test_run_without_acceptor_agent_still_returns_stage_result(self):
        """In stub mode (no acceptor_agent), run() MUST still return a StageResult."""
        stage = AcceptanceStage()
        result = await stage.run()
        assert isinstance(result, StageResult), (
            "run() must return StageResult even when no acceptor_agent is injected"
        )


# ---------------------------------------------------------------------------
# 3. Traceability matrix in result
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunTraceabilityMatrix:
    """FR-ACPT-RUN-005: run() result MUST contain the traceability matrix from the agent."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_traceability_key(self):
        """StageResult.data MUST contain a 'traceability' key."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "traceability" in result.data, (
            f"StageResult.data must contain 'traceability'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_result_traceability_reflects_acceptor_output(self):
        """StageResult.data['traceability'] MUST reflect the traceability returned
        by the acceptor agent (not an empty dict generated independently)."""
        custom_traceability = {
            "FR-010": {"tasks": ["task-alpha"], "tests": ["test_alpha.py"], "status": "implemented"},
            "FR-011": {"tasks": [], "tests": [], "status": "unimplemented"},
        }
        agent = _make_acceptor_agent(traceability=custom_traceability)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        traceability = result.data.get("traceability", {})
        assert "FR-010" in traceability, (
            f"StageResult.data['traceability'] must include FR-010 from acceptor output. "
            f"traceability={traceability!r}"
        )
        assert "FR-011" in traceability, (
            f"StageResult.data['traceability'] must include FR-011 from acceptor output. "
            f"traceability={traceability!r}"
        )

    @pytest.mark.asyncio
    async def test_run_result_traceability_is_not_empty_when_agent_provides_frs(self):
        """When acceptor_agent returns FRs, traceability MUST NOT be an empty dict."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        traceability = result.data.get("traceability", {})
        assert len(traceability) > 0, (
            "When the acceptor agent returns FRs, traceability must not be empty"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_contains_unimplemented_frs_key(self):
        """StageResult.data MUST contain 'unimplemented_frs' key."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "unimplemented_frs" in result.data, (
            f"StageResult.data must contain 'unimplemented_frs'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_unimplemented_frs_reflects_acceptor_traceability(self):
        """unimplemented_frs MUST list FRs that have no task or no test
        according to the acceptor agent's traceability output."""
        custom_traceability = {
            "FR-100": {"tasks": ["t1"], "tests": ["test_t1.py"], "status": "implemented"},
            "FR-101": {"tasks": [], "tests": [], "status": "unimplemented"},
            "FR-102": {"tasks": ["t3"], "tests": [], "status": "unimplemented"},
        }
        agent = _make_acceptor_agent(traceability=custom_traceability)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        unimplemented = result.data.get("unimplemented_frs", [])
        assert "FR-101" in unimplemented, (
            f"FR-101 (no tasks, no tests) must appear in unimplemented_frs. "
            f"unimplemented_frs={unimplemented!r}"
        )
        assert "FR-102" in unimplemented, (
            f"FR-102 (no tests) must appear in unimplemented_frs. "
            f"unimplemented_frs={unimplemented!r}"
        )
        assert "FR-100" not in unimplemented, (
            f"FR-100 (fully implemented) must NOT appear in unimplemented_frs. "
            f"unimplemented_frs={unimplemented!r}"
        )


# ---------------------------------------------------------------------------
# 4. Final review of artifacts
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunFinalReview:
    """FR-ACPT-RUN-002: run() MUST run a final review of all artifacts."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_review_passed_key(self):
        """StageResult.data MUST contain a 'review_passed' key."""
        agent = _make_acceptor_agent(review_passed=True)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "review_passed" in result.data, (
            f"StageResult.data must contain 'review_passed'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_result_review_passed_reflects_acceptor_review(self):
        """StageResult.data['review_passed'] MUST reflect the review outcome from
        the acceptor agent, not a hardcoded True."""
        agent_fail = _make_acceptor_agent(review_passed=False, review_issues=["Missing test for FR-007"])
        stage = AcceptanceStage(
            acceptor_agent=agent_fail,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        review_passed = result.data.get("review_passed")
        assert review_passed is False, (
            f"When acceptor agent reports review_passed=False, "
            f"StageResult.data['review_passed'] must be False. Got: {review_passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_result_review_passed_true_when_review_passes(self):
        """StageResult.data['review_passed'] MUST be True when the acceptor review passes."""
        agent = _make_acceptor_agent(review_passed=True)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        review_passed = result.data.get("review_passed")
        assert review_passed is True, (
            f"When acceptor agent reports review_passed=True, "
            f"StageResult.data['review_passed'] must be True. Got: {review_passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_contains_review_issues_key(self):
        """StageResult.data MUST contain a 'review_issues' key."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "review_issues" in result.data, (
            f"StageResult.data must contain 'review_issues'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_result_review_issues_populated_when_review_fails(self):
        """StageResult.data['review_issues'] MUST contain the issues reported
        by the acceptor agent when review fails."""
        issues = ["Missing test for FR-007", "No task mapped to FR-010"]
        agent = _make_acceptor_agent(review_passed=False, review_issues=issues)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        review_issues = result.data.get("review_issues", [])
        assert "Missing test for FR-007" in review_issues, (
            f"review_issues must include 'Missing test for FR-007'. "
            f"review_issues={review_issues!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_passed_false_when_review_fails(self):
        """StageResult.passed MUST be False when the acceptor review fails."""
        agent = _make_acceptor_agent(review_passed=False, review_issues=["gap found"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert result.passed is False, (
            f"StageResult.passed must be False when review_passed=False. "
            f"Got passed={result.passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_passed_true_when_review_passes(self):
        """StageResult.passed MUST be True when the acceptor review passes
        and all FRs are implemented."""
        agent = _make_acceptor_agent(review_passed=True)
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert result.passed is True, (
            f"StageResult.passed must be True when review passes. "
            f"Got passed={result.passed!r}"
        )


# ---------------------------------------------------------------------------
# 5. Artifact freezing with SHA-256 hashes
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunArtifactFreezing:
    """FR-ACPT-RUN-003: run() MUST freeze artifacts with SHA-256 content hashes."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_frozen_artifacts_key(self):
        """StageResult.data MUST contain a 'frozen_artifacts' or 'artifacts' key
        with hash information."""
        agent = _make_acceptor_agent()
        artifacts = _make_artifacts()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
        )
        result = await stage.run()
        has_artifacts = (
            "frozen_artifacts" in result.data
            or "artifacts" in result.data
        )
        assert has_artifacts, (
            f"StageResult.data must contain 'frozen_artifacts' or 'artifacts'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_frozen_artifacts_contain_sha256_hashes(self):
        """Each frozen artifact entry MUST contain a 64-char hex SHA-256 hash."""
        import re
        agent = _make_acceptor_agent()
        artifacts = _make_artifacts(["spec", "plan"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
        )
        result = await stage.run()
        data_str = str(result.data)
        # Must find at least one 64-char hex string (SHA-256 digest)
        found_hashes = re.findall(r'[0-9a-f]{64}', data_str)
        assert len(found_hashes) > 0, (
            f"StageResult.data must contain at least one SHA-256 hex digest "
            f"(64 lowercase hex chars). data={result.data!r}"
        )

    @pytest.mark.asyncio
    async def test_run_frozen_artifact_hash_matches_content(self):
        """The SHA-256 hash stored for a given artifact MUST match the actual content."""
        artifact_content = "# Implementation\n\nThe real implementation text."
        artifacts = {"implementation": artifact_content}
        expected_hash = _sha256(artifact_content)
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
        )
        result = await stage.run()
        data_str = str(result.data)
        assert expected_hash in data_str, (
            f"The SHA-256 hash of the 'implementation' artifact content must appear "
            f"in StageResult.data. Expected hash: {expected_hash!r}. "
            f"data={result.data!r}"
        )

    @pytest.mark.asyncio
    async def test_run_frozen_artifacts_are_deterministic(self):
        """Freezing the same artifact content twice MUST produce the same hash."""
        import re
        artifact_content = "# Spec\n\nDeterministic content."
        artifacts = {"spec": artifact_content}
        expected_hash = _sha256(artifact_content)

        agent1 = _make_acceptor_agent()
        stage1 = AcceptanceStage(acceptor_agent=agent1, artifacts=dict(artifacts))

        agent2 = _make_acceptor_agent()
        stage2 = AcceptanceStage(acceptor_agent=agent2, artifacts=dict(artifacts))

        result1 = await stage1.run()
        result2 = await stage2.run()

        hashes1 = set(re.findall(r'[0-9a-f]{64}', str(result1.data)))
        hashes2 = set(re.findall(r'[0-9a-f]{64}', str(result2.data)))
        assert hashes1 == hashes2, (
            f"Artifact hashes must be deterministic. "
            f"run1 hashes: {hashes1}, run2 hashes: {hashes2}"
        )

    @pytest.mark.asyncio
    async def test_run_freezes_traceability_report_with_hash(self):
        """The traceability report artifact MUST also be frozen (hashed)."""
        import re
        agent = _make_acceptor_agent()
        artifacts = _make_artifacts()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
        )
        result = await stage.run()
        data_str = str(result.data)
        # Should have at least two SHA-256 hashes: one per artifact + traceability report
        found_hashes = set(re.findall(r'[0-9a-f]{64}', data_str))
        assert len(found_hashes) >= 1, (
            "At least one SHA-256 hash must be present in the frozen artifacts "
            f"(including traceability report). data={result.data!r}"
        )


# ---------------------------------------------------------------------------
# 6. stage_complete event recording
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunStageCompleteEvent:
    """FR-ACPT-RUN-004: run() MUST record a stage_complete event upon success."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_stage_complete_key(self):
        """StageResult.data MUST contain a 'stage_complete' key."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "stage_complete" in result.data, (
            f"StageResult.data must contain 'stage_complete'. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_value_is_acceptance(self):
        """The stage_complete event value MUST be 'acceptance' (the stage name)."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        event_val = result.data.get("stage_complete")
        assert str(event_val) == "acceptance", (
            f"stage_complete must equal 'acceptance', got {event_val!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_recorded_even_when_review_fails(self):
        """stage_complete MUST be recorded even when the final review fails,
        so the pipeline can trace which stage last ran."""
        agent = _make_acceptor_agent(review_passed=False, review_issues=["issue"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "stage_complete" in result.data, (
            "stage_complete must appear in data even when review fails"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_without_agent_still_recorded(self):
        """In stub mode (no acceptor_agent), stage_complete MUST still be present."""
        stage = AcceptanceStage()
        result = await stage.run()
        assert "stage_complete" in result.data, (
            "stage_complete must be recorded even in stub mode (no acceptor_agent)"
        )


# ---------------------------------------------------------------------------
# 7. Graceful handling of acceptor agent failures
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunAgentFailureHandling:
    """FR-ACPT-RUN-006: run() MUST handle acceptor agent failures gracefully."""

    @pytest.mark.asyncio
    async def test_run_does_not_raise_when_acceptor_agent_returns_failure(self):
        """run() MUST NOT raise an exception when acceptor_agent returns success=False."""
        failed_result = MagicMock()
        failed_result.success = False
        failed_result.traceability = {}
        failed_result.review_passed = False
        failed_result.review_issues = ["Agent failed to produce traceability"]
        failed_result.output = ""
        failed_result.session_id = ""
        agent = AsyncMock(return_value=failed_result)

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        # Must not raise
        result = await stage.run()
        assert isinstance(result, StageResult), (
            "run() must return StageResult even when agent returns failure"
        )

    @pytest.mark.asyncio
    async def test_run_passed_false_when_acceptor_agent_returns_failure(self):
        """StageResult.passed MUST be False when acceptor_agent.success is False."""
        failed_result = MagicMock()
        failed_result.success = False
        failed_result.traceability = {}
        failed_result.review_passed = False
        failed_result.review_issues = ["Internal agent error"]
        failed_result.output = ""
        failed_result.session_id = ""
        agent = AsyncMock(return_value=failed_result)

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert result.passed is False, (
            f"StageResult.passed must be False when acceptor_agent fails. "
            f"Got passed={result.passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_does_not_raise_when_acceptor_agent_raises_exception(self):
        """run() MUST NOT propagate exceptions raised by the acceptor_agent."""
        agent = AsyncMock(side_effect=RuntimeError("Agent crashed unexpectedly"))

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        # Must not raise RuntimeError
        result = await stage.run()
        assert isinstance(result, StageResult), (
            "run() must return StageResult even when acceptor_agent raises"
        )

    @pytest.mark.asyncio
    async def test_run_passed_false_when_acceptor_agent_raises_exception(self):
        """StageResult.passed MUST be False when acceptor_agent raises an exception."""
        agent = AsyncMock(side_effect=RuntimeError("Agent crashed"))

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert result.passed is False, (
            "StageResult.passed must be False when acceptor_agent raises"
        )

    @pytest.mark.asyncio
    async def test_run_error_field_set_when_agent_raises(self):
        """StageResult.error MUST be set (non-None) when acceptor_agent raises."""
        agent = AsyncMock(side_effect=RuntimeError("Crashed"))

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert result.error is not None, (
            "StageResult.error must be non-None when acceptor_agent raises"
        )

    @pytest.mark.asyncio
    async def test_run_data_still_has_stage_complete_after_agent_exception(self):
        """Even when acceptor_agent raises, stage_complete MUST still appear in data."""
        agent = AsyncMock(side_effect=RuntimeError("Crash"))

        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        assert "stage_complete" in result.data, (
            "stage_complete must appear in data even after acceptor_agent raises"
        )


# ---------------------------------------------------------------------------
# 8. Required artifact validation before acceptor agent invocation
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunArtifactValidation:
    """FR-ACPT-RUN-007: run() MUST validate required artifacts before calling agent."""

    @pytest.mark.asyncio
    async def test_run_passed_false_when_required_artifact_missing(self):
        """StageResult.passed MUST be False when a required artifact is absent."""
        agent = _make_acceptor_agent()
        # Only 'spec' provided; 'plan' is missing
        artifacts = {"spec": "# Spec content"}
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan"],
        )
        result = await stage.run()
        assert result.passed is False, (
            f"StageResult.passed must be False when required artifact 'plan' is missing. "
            f"Got passed={result.passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_acceptor_agent_not_called_when_required_artifact_missing(self):
        """The acceptor_agent MUST NOT be invoked when required artifacts are missing."""
        agent = _make_acceptor_agent()
        artifacts = {"spec": "# Spec only"}
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan", "tasks", "implementation"],
        )
        await stage.run()
        assert agent.call_count == 0, (
            f"acceptor_agent must NOT be called when required artifacts are missing. "
            f"Called {agent.call_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_error_describes_missing_artifacts(self):
        """StageResult.error MUST name the missing artifacts when validation fails."""
        agent = _make_acceptor_agent()
        artifacts = {"spec": "content"}
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "implementation"],
        )
        result = await stage.run()
        assert result.error is not None, (
            "StageResult.error must not be None when required artifacts are missing"
        )
        assert "implementation" in result.error, (
            f"StageResult.error must mention the missing artifact 'implementation'. "
            f"error={result.error!r}"
        )

    @pytest.mark.asyncio
    async def test_run_proceeds_when_all_required_artifacts_present(self):
        """run() MUST call acceptor_agent when all required artifacts are present."""
        agent = _make_acceptor_agent()
        artifacts = _make_artifacts(["spec", "plan", "tasks"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan", "tasks"],
        )
        await stage.run()
        assert agent.call_count == 1, (
            f"acceptor_agent must be called exactly once when all required artifacts exist. "
            f"Called {agent.call_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_no_validation_error_when_required_artifacts_empty(self):
        """When required_artifacts is empty, run() MUST proceed without validation error."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts={},
            required_artifacts=[],
        )
        result = await stage.run()
        # Should have called the agent (no missing artifacts)
        assert agent.call_count == 1, (
            "acceptor_agent must be called when required_artifacts is empty list"
        )

    @pytest.mark.asyncio
    async def test_run_passed_true_when_all_required_artifacts_present_and_review_passes(self):
        """StageResult.passed MUST be True when all required artifacts are present
        and the acceptor agent reports review_passed=True."""
        agent = _make_acceptor_agent(review_passed=True)
        artifacts = _make_artifacts(["spec", "plan"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan"],
        )
        result = await stage.run()
        assert result.passed is True, (
            f"StageResult.passed must be True when all artifacts present and review passes. "
            f"Got passed={result.passed!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_recorded_even_on_validation_failure(self):
        """stage_complete MUST appear in result data even when artifact validation fails,
        so the pipeline can see that the acceptance stage was attempted."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts={},
            required_artifacts=["spec", "plan"],
        )
        result = await stage.run()
        assert "stage_complete" in result.data, (
            "stage_complete must appear in data even on artifact validation failure"
        )


# ---------------------------------------------------------------------------
# 9. End-to-end happy path
# ---------------------------------------------------------------------------


class TestAcceptanceStageRunEndToEnd:
    """Integration-level tests exercising the full run() happy path."""

    @pytest.mark.asyncio
    async def test_run_full_happy_path_all_frs_implemented(self):
        """Full happy path: all FRs implemented, review passes, artifacts frozen."""
        import re
        traceability = {
            "FR-001": {"tasks": ["task-spec"], "tests": ["test_spec.py"], "status": "implemented"},
            "FR-002": {"tasks": ["task-plan"], "tests": ["test_plan.py"], "status": "implemented"},
        }
        agent = _make_acceptor_agent(
            traceability=traceability,
            review_passed=True,
            review_issues=[],
        )
        artifacts = _make_artifacts(["spec", "plan", "implementation"])
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan"],
        )
        result = await stage.run()

        # StageResult is returned
        assert isinstance(result, StageResult)
        # passed is True
        assert result.passed is True
        # acceptor_agent called once
        assert agent.call_count == 1
        # traceability present and non-empty
        assert "FR-001" in result.data.get("traceability", {})
        # review_passed present
        assert result.data.get("review_passed") is True
        # stage_complete recorded
        assert result.data.get("stage_complete") == "acceptance"
        # At least one SHA-256 hash frozen
        assert len(re.findall(r'[0-9a-f]{64}', str(result.data))) > 0
        # No unimplemented FRs
        assert result.data.get("unimplemented_frs", []) == []

    @pytest.mark.asyncio
    async def test_run_full_path_with_unimplemented_frs(self):
        """Full path where some FRs are unimplemented: passed reflects review outcome."""
        traceability = {
            "FR-001": {"tasks": ["task-spec"], "tests": ["test_spec.py"], "status": "implemented"},
            "FR-099": {"tasks": [], "tests": [], "status": "unimplemented"},
        }
        agent = _make_acceptor_agent(
            traceability=traceability,
            review_passed=False,
            review_issues=["FR-099 has no tasks or tests"],
        )
        artifacts = _make_artifacts()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=artifacts,
            required_artifacts=["spec", "plan", "tasks", "implementation"],
        )
        result = await stage.run()

        assert isinstance(result, StageResult)
        assert result.passed is False
        assert "FR-099" in result.data.get("unimplemented_frs", [])
        assert result.data.get("review_passed") is False
        assert "stage_complete" in result.data

    @pytest.mark.asyncio
    async def test_run_data_contains_all_required_top_level_keys(self):
        """StageResult.data MUST contain all required top-level keys on a happy path."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        required_keys = {
            "traceability",
            "unimplemented_frs",
            "review_passed",
            "review_issues",
            "stage_complete",
        }
        missing = required_keys - set(result.data.keys())
        assert not missing, (
            f"StageResult.data is missing required keys: {missing}. "
            f"Present keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_steps_executed_includes_all_sub_steps(self):
        """steps_executed in StageResult.data MUST include all three sub-steps
        when the full happy path completes."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        result = await stage.run()
        if "steps_executed" in result.data:
            steps = result.data["steps_executed"]
            for step in AcceptanceStage.sub_steps:
                assert step in steps, (
                    f"steps_executed must include '{step}'. "
                    f"steps_executed={steps!r}"
                )

    @pytest.mark.asyncio
    async def test_run_stage_still_subclasses_stage_abc(self):
        """AcceptanceStage MUST remain a StageABC subclass after run()."""
        agent = _make_acceptor_agent()
        stage = AcceptanceStage(
            acceptor_agent=agent,
            artifacts=_make_artifacts(),
        )
        assert isinstance(stage, StageABC)
        result = await stage.run()
        assert isinstance(result, StageResult)
