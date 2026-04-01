"""RED-phase tests for SpecStage.run() orchestration logic.

Covers the four behaviors mandated by the task spec:
  1. SpecStage.run() invokes the spec-writer agent with the feature description.
  2. SpecStage.run() scans spec-writer output using perception to detect [NC:] markers.
  3. When [NC:] markers are found, SpecStage.run() triggers the clarify agent.
  4. After clarification (or when none is needed), artifacts are frozen with
     SHA-256 content hashes and a stage_complete event is recorded.

Feature acceptance scenarios (from requirement spec):
  - Given a git repo with a feature description, when run() is called,
    it produces all required artifacts (spec frozen with content hash).
  - Given spec-writer output with [NC:] markers, when run() processes the
    output, the clarify agent is triggered before proceeding.
  - Given spec-writer output with NO [NC:] markers, clarify agent is NOT
    called and the stage proceeds directly to freezing artifacts.
  - The returned StageResult.data contains frozen artifacts with SHA-256
    hashes and a stage_complete event entry.

All tests in this module are RED-phase tests. They MUST FAIL until
orchestrator/stages/spec.py provides a concrete SpecStage.run() that:
  - accepts spec_writer_agent and clarify_agent collaborators
  - invokes the spec-writer agent with the feature description
  - uses orchestrator.perception.detect_nc_markers on the output
  - conditionally triggers the clarify agent
  - freezes artifacts with SHA-256 content hashes
  - records a stage_complete event in the returned data
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.stages.base import StageABC, StageResult
from orchestrator.stages.spec import SpecStage


# ---------------------------------------------------------------------------
# Helpers / shared factories
# ---------------------------------------------------------------------------


def _make_spec_writer_agent(output: str = "# Feature Spec\n\nThis is the spec.") -> AsyncMock:
    """Return an async-callable mock simulating the spec-writer agent.

    The mock returns an AgentResult-like object with .output and .success.
    """
    result = MagicMock()
    result.output = output
    result.success = True
    result.session_id = "session-spec-001"
    agent = AsyncMock(return_value=result)
    return agent


def _make_clarify_agent(output: str = "Clarification: The feature targets web clients.") -> AsyncMock:
    """Return an async-callable mock simulating the clarify agent."""
    result = MagicMock()
    result.output = output
    result.success = True
    result.session_id = "session-clarify-001"
    agent = AsyncMock(return_value=result)
    return agent


def _make_store() -> MagicMock:
    store = MagicMock()
    store.save_checkpoint = MagicMock()
    return store


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 1. SpecStage accepts collaborator injection
# ---------------------------------------------------------------------------


class TestSpecStageCollaboratorInjection:
    """SpecStage MUST accept spec_writer_agent and clarify_agent via constructor."""

    def test_spec_stage_accepts_spec_writer_agent_kwarg(self):
        """FR-spec-run-001: SpecStage constructor MUST accept spec_writer_agent kwarg."""
        agent = _make_spec_writer_agent()
        stage = SpecStage(spec_writer_agent=agent)
        assert stage is not None

    def test_spec_stage_accepts_clarify_agent_kwarg(self):
        """FR-spec-run-002: SpecStage constructor MUST accept clarify_agent kwarg."""
        agent = _make_clarify_agent()
        stage = SpecStage(clarify_agent=agent)
        assert stage is not None

    def test_spec_stage_accepts_feature_description_kwarg(self):
        """FR-spec-run-003: SpecStage constructor MUST accept feature_description kwarg."""
        stage = SpecStage(feature_description="Implement login with OAuth2")
        assert stage is not None

    def test_spec_stage_accepts_all_collaborators_together(self):
        """SpecStage must accept all three collaborator kwargs simultaneously."""
        stage = SpecStage(
            spec_writer_agent=_make_spec_writer_agent(),
            clarify_agent=_make_clarify_agent(),
            feature_description="Implement login",
            store=_make_store(),
        )
        assert stage is not None

    def test_spec_stage_stores_spec_writer_agent(self):
        """The injected spec_writer_agent MUST be stored on the instance."""
        agent = _make_spec_writer_agent()
        stage = SpecStage(spec_writer_agent=agent)
        assert getattr(stage, "spec_writer_agent", None) is agent, (
            "SpecStage must store spec_writer_agent as self.spec_writer_agent"
        )

    def test_spec_stage_stores_clarify_agent(self):
        """The injected clarify_agent MUST be stored on the instance."""
        agent = _make_clarify_agent()
        stage = SpecStage(clarify_agent=agent)
        assert getattr(stage, "clarify_agent", None) is agent, (
            "SpecStage must store clarify_agent as self.clarify_agent"
        )

    def test_spec_stage_stores_feature_description(self):
        """The injected feature_description MUST be stored on the instance."""
        desc = "Build a REST API for task management"
        stage = SpecStage(feature_description=desc)
        assert getattr(stage, "feature_description", None) == desc, (
            "SpecStage must store feature_description as self.feature_description"
        )


# ---------------------------------------------------------------------------
# 2. run() invokes the spec-writer agent
# ---------------------------------------------------------------------------


class TestSpecStageRunInvokesSpecWriter:
    """FR-spec-run-004: run() MUST invoke the spec_writer_agent exactly once."""

    @pytest.mark.asyncio
    async def test_run_calls_spec_writer_agent(self):
        """run() MUST call spec_writer_agent at least once."""
        writer = _make_spec_writer_agent("# Spec\nDone.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        await stage.run()
        assert writer.call_count >= 1, (
            "run() must invoke spec_writer_agent at least once"
        )

    @pytest.mark.asyncio
    async def test_run_calls_spec_writer_exactly_once(self):
        """run() MUST invoke the spec-writer agent exactly once (not zero, not twice)."""
        writer = _make_spec_writer_agent("# Clean spec with no NC markers.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        await stage.run()
        assert writer.call_count == 1, (
            f"run() must call spec_writer_agent exactly once, called {writer.call_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_passes_feature_description_to_spec_writer(self):
        """run() MUST pass the feature_description to the spec_writer_agent call."""
        desc = "Build task management REST API"
        writer = _make_spec_writer_agent("# Spec\nTask management.")
        stage = SpecStage(
            spec_writer_agent=writer,
            clarify_agent=_make_clarify_agent(),
            feature_description=desc,
        )
        await stage.run()
        # The feature description must appear in the call arguments (positional or keyword)
        call_args_flat = str(writer.call_args_list)
        assert desc in call_args_flat, (
            f"run() must pass the feature_description {desc!r} to spec_writer_agent. "
            f"Actual call args: {call_args_flat}"
        )

    @pytest.mark.asyncio
    async def test_run_returns_stage_result_after_spec_writer(self):
        """run() MUST return a StageResult after calling spec_writer_agent."""
        writer = _make_spec_writer_agent("# Spec")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        result = await stage.run()
        assert isinstance(result, StageResult), (
            f"run() must return StageResult, got {type(result)}"
        )


# ---------------------------------------------------------------------------
# 3. run() scans output with perception for [NC:] markers
# ---------------------------------------------------------------------------


class TestSpecStageRunPerceptionScan:
    """FR-spec-run-005: run() MUST scan spec-writer output with perception."""

    @pytest.mark.asyncio
    async def test_run_calls_detect_nc_markers_on_spec_writer_output(self):
        """run() MUST invoke orchestrator.perception.detect_nc_markers on the
        spec-writer output text."""
        spec_output = "# Spec\n\nThis is the specification. [NC: clarify scope]"
        writer = _make_spec_writer_agent(spec_output)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers") as mock_detect:
            mock_detect.return_value = ["[NC: clarify scope]"]
            await stage.run()

        mock_detect.assert_called_once_with(spec_output), (
            "run() must call perception.detect_nc_markers with the spec-writer output"
        )

    @pytest.mark.asyncio
    async def test_run_uses_perception_module_not_direct_regex(self):
        """run() MUST use orchestrator.perception for NC detection, not inline regex."""
        spec_output = "# Spec\n\n[NC: needs scope definition]"
        writer = _make_spec_writer_agent(spec_output)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        call_record: list[str] = []

        with patch("orchestrator.perception.detect_nc_markers") as mock_detect:
            mock_detect.side_effect = lambda text: (
                call_record.append(text) or ["[NC: needs scope definition]"]
            )
            await stage.run()

        assert len(call_record) >= 1, (
            "run() must route NC detection through orchestrator.perception.detect_nc_markers"
        )

    @pytest.mark.asyncio
    async def test_run_scans_actual_spec_writer_output_not_empty_string(self):
        """The text passed to detect_nc_markers MUST be the spec-writer output,
        not an empty string or a different value."""
        spec_output = "# Real Spec Content\n\nFunctionality described here."
        writer = _make_spec_writer_agent(spec_output)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        scanned_texts: list[str] = []

        with patch("orchestrator.perception.detect_nc_markers") as mock_detect:
            mock_detect.side_effect = lambda text: (scanned_texts.append(text) or [])
            await stage.run()

        assert spec_output in scanned_texts, (
            f"detect_nc_markers must be called with the spec-writer output. "
            f"Scanned texts: {scanned_texts}"
        )


# ---------------------------------------------------------------------------
# 4. run() triggers clarify agent when NC markers are present
# ---------------------------------------------------------------------------


class TestSpecStageRunClarifyOnNCMarkers:
    """FR-spec-run-006: run() MUST trigger clarify agent when [NC:] markers found."""

    @pytest.mark.asyncio
    async def test_run_triggers_clarify_agent_when_nc_markers_found(self):
        """When detect_nc_markers returns non-empty list, clarify_agent MUST be called."""
        spec_output = "# Spec\n\n[NC: what is the target platform?]"
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent()
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch("orchestrator.perception.detect_nc_markers", return_value=["[NC: what is the target platform?]"]):
            await stage.run()

        assert clarifier.call_count >= 1, (
            "run() must invoke clarify_agent when NC markers are detected"
        )

    @pytest.mark.asyncio
    async def test_run_does_not_call_clarify_agent_when_no_nc_markers(self):
        """When detect_nc_markers returns empty list, clarify_agent MUST NOT be called."""
        spec_output = "# Clean Spec\n\nNo ambiguities here."
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent()
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            await stage.run()

        assert clarifier.call_count == 0, (
            "run() must NOT call clarify_agent when no NC markers are present"
        )

    @pytest.mark.asyncio
    async def test_run_calls_clarify_agent_once_per_nc_batch(self):
        """When NC markers are present, clarify_agent MUST be invoked exactly once
        (not once per marker — a single clarification round resolves all ambiguities)."""
        spec_output = "# Spec\n\n[NC: platform?]\n\n[NC: auth method?]"
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent()
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch(
            "orchestrator.perception.detect_nc_markers",
            return_value=["[NC: platform?]", "[NC: auth method?]"],
        ):
            await stage.run()

        assert clarifier.call_count == 1, (
            f"run() must invoke clarify_agent exactly once for a batch of NC markers, "
            f"called {clarifier.call_count} times"
        )

    @pytest.mark.asyncio
    async def test_run_passes_nc_markers_to_clarify_agent(self):
        """The NC markers detected MUST be passed to the clarify_agent call."""
        nc_markers = ["[NC: what platform?]", "[NC: which auth method?]"]
        spec_output = "# Spec\n\n" + " ".join(nc_markers)
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent()
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch("orchestrator.perception.detect_nc_markers", return_value=nc_markers):
            await stage.run()

        # At least one of the NC markers must appear in the clarifier call arguments
        call_args_flat = str(clarifier.call_args_list)
        assert any(marker in call_args_flat for marker in nc_markers), (
            f"run() must pass NC marker information to clarify_agent. "
            f"Clarifier call args: {call_args_flat}"
        )

    @pytest.mark.asyncio
    async def test_run_proceeds_after_clarification(self):
        """After clarification, run() MUST still return a StageResult (not hang/raise)."""
        spec_output = "# Spec with NC\n\n[NC: unclear requirement]"
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent("Clarification provided.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch("orchestrator.perception.detect_nc_markers", return_value=["[NC: unclear requirement]"]):
            result = await stage.run()

        assert isinstance(result, StageResult), (
            "run() must return StageResult even after clarification"
        )

    @pytest.mark.asyncio
    async def test_run_succeeds_when_nc_free_spec_produced(self):
        """run() MUST return passed=True when spec-writer output has no NC markers."""
        writer = _make_spec_writer_agent("# Perfect Spec\n\nAll clear.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert result.passed is True, (
            "run() must return passed=True when spec has no NC markers"
        )


# ---------------------------------------------------------------------------
# 5. Artifact freezing with SHA-256 content hashes
# ---------------------------------------------------------------------------


class TestSpecStageRunArtifactFreezing:
    """FR-spec-run-007: Artifacts MUST be frozen with SHA-256 content hashes."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_spec_content(self):
        """StageResult.data MUST include the spec content produced by spec-writer."""
        spec_text = "# Feature Spec\n\nDetailed specification text here."
        writer = _make_spec_writer_agent(spec_text)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert isinstance(result.data, dict), "StageResult.data must be a dict"
        data_str = str(result.data)
        assert spec_text in data_str or any(
            spec_text in str(v) for v in result.data.values()
        ), (
            f"StageResult.data must contain the spec content. data={result.data!r}"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_contains_sha256_hash(self):
        """StageResult.data MUST include a SHA-256 hash of the frozen spec artifact."""
        spec_text = "# Feature Spec\n\nContent to be hashed."
        writer = _make_spec_writer_agent(spec_text)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        expected_hash = _sha256(spec_text)

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        data_str = str(result.data)
        assert expected_hash in data_str, (
            f"StageResult.data must contain the SHA-256 hash {expected_hash!r} of the spec. "
            f"data={result.data!r}"
        )

    @pytest.mark.asyncio
    async def test_run_result_data_contains_artifacts_key(self):
        """StageResult.data MUST contain an 'artifacts' key with frozen artifact info."""
        writer = _make_spec_writer_agent("# Spec\n\nBody.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert "artifacts" in result.data, (
            f"StageResult.data must have an 'artifacts' key. data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_frozen_artifact_hash_is_sha256_hex_digest(self):
        """The hash value stored in artifacts MUST be a valid 64-character SHA-256 hex digest."""
        spec_text = "# Spec\n\nSpecific content."
        writer = _make_spec_writer_agent(spec_text)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        artifacts = result.data.get("artifacts", {})
        # Artifacts may be a dict mapping name -> {content, hash} or similar
        found_hash = False
        for key, val in (artifacts.items() if isinstance(artifacts, dict) else []):
            h = val.get("hash") if isinstance(val, dict) else None
            if h and len(h) == 64 and all(c in "0123456789abcdef" for c in h):
                found_hash = True
                break

        assert found_hash, (
            f"artifacts must contain at least one entry with a 64-char hex SHA-256 hash. "
            f"artifacts={artifacts!r}"
        )

    @pytest.mark.asyncio
    async def test_run_artifact_hash_matches_spec_content(self):
        """The SHA-256 hash in artifacts MUST match the actual spec content hash."""
        spec_text = "# Precise Spec\n\nMust match hash exactly."
        writer = _make_spec_writer_agent(spec_text)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())
        expected_hash = _sha256(spec_text)

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        artifacts = result.data.get("artifacts", {})
        found_correct_hash = False
        for key, val in (artifacts.items() if isinstance(artifacts, dict) else []):
            h = val.get("hash") if isinstance(val, dict) else None
            if h == expected_hash:
                found_correct_hash = True
                break

        assert found_correct_hash, (
            f"Artifact hash must equal SHA-256({spec_text!r}) = {expected_hash!r}. "
            f"artifacts={artifacts!r}"
        )

    @pytest.mark.asyncio
    async def test_run_artifact_includes_spec_content_in_frozen_artifact(self):
        """The frozen artifact entry MUST preserve the spec content alongside its hash."""
        spec_text = "# Spec to Freeze\n\nKeep this content."
        writer = _make_spec_writer_agent(spec_text)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        artifacts = result.data.get("artifacts", {})
        content_preserved = False
        for key, val in (artifacts.items() if isinstance(artifacts, dict) else []):
            content = val.get("content") if isinstance(val, dict) else None
            if content == spec_text:
                content_preserved = True
                break

        assert content_preserved, (
            f"Frozen artifact must preserve the spec content. artifacts={artifacts!r}"
        )

    @pytest.mark.asyncio
    async def test_run_clarified_spec_hash_reflects_clarified_content(self):
        """When clarification was performed, the frozen artifact hash MUST reflect
        the clarified/updated spec content (not the pre-clarification version)."""
        initial_spec = "# Spec\n\n[NC: unclear]"
        clarified_output = "# Spec\n\nClarified: platform is web browser."
        writer = _make_spec_writer_agent(initial_spec)
        clarifier = _make_clarify_agent(clarified_output)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)
        expected_hash = _sha256(clarified_output)

        with patch("orchestrator.perception.detect_nc_markers", return_value=["[NC: unclear]"]):
            result = await stage.run()

        data_str = str(result.data)
        assert expected_hash in data_str, (
            f"After clarification, the frozen artifact hash must reflect the clarified spec. "
            f"Expected hash of clarified content: {expected_hash!r}. data={result.data!r}"
        )


# ---------------------------------------------------------------------------
# 6. stage_complete event recording
# ---------------------------------------------------------------------------


class TestSpecStageRunStageCompleteEvent:
    """FR-spec-run-008: run() MUST record a stage_complete event upon success."""

    @pytest.mark.asyncio
    async def test_run_result_data_contains_stage_complete_event(self):
        """StageResult.data MUST contain a 'stage_complete' entry or event marker."""
        writer = _make_spec_writer_agent("# Spec")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert "stage_complete" in result.data, (
            f"StageResult.data must contain 'stage_complete' event. "
            f"data keys: {list(result.data.keys())}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_event_is_truthy(self):
        """The stage_complete entry MUST be truthy (not False/None/empty)."""
        writer = _make_spec_writer_agent("# Spec\n\nOK.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        event_val = result.data.get("stage_complete")
        assert event_val, (
            f"stage_complete must be truthy. Got: {event_val!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_event_contains_stage_name(self):
        """The stage_complete event MUST reference the 'spec' stage name."""
        writer = _make_spec_writer_agent("# Spec\n\nContent.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        event_val = result.data.get("stage_complete")
        event_str = str(event_val)
        assert "spec" in event_str, (
            f"stage_complete event must reference the 'spec' stage. "
            f"stage_complete value: {event_val!r}"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_recorded_after_clarification(self):
        """stage_complete event MUST be recorded even when clarification was needed."""
        spec_output = "# Spec\n\n[NC: unclear thing]"
        writer = _make_spec_writer_agent(spec_output)
        clarifier = _make_clarify_agent("Resolved clarification.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch("orchestrator.perception.detect_nc_markers", return_value=["[NC: unclear thing]"]):
            result = await stage.run()

        assert "stage_complete" in result.data, (
            "stage_complete event must be recorded even when clarification was triggered"
        )

    @pytest.mark.asyncio
    async def test_run_stage_complete_recorded_without_clarification(self):
        """stage_complete event MUST be recorded when no clarification was needed."""
        writer = _make_spec_writer_agent("# Perfect clean spec.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert "stage_complete" in result.data, (
            "stage_complete event must be recorded when no NC markers were found"
        )


# ---------------------------------------------------------------------------
# 7. End-to-end orchestration: full run() happy path
# ---------------------------------------------------------------------------


class TestSpecStageRunEndToEnd:
    """Integration-level tests that exercise the full run() happy path."""

    @pytest.mark.asyncio
    async def test_run_full_happy_path_no_nc_markers(self):
        """Full happy path: spec-writer produces clean output, no clarification needed,
        artifacts frozen and stage_complete recorded."""
        spec_text = "# Login Feature Spec\n\nOAuth2 with Google provider."
        writer = _make_spec_writer_agent(spec_text)
        clarifier = _make_clarify_agent()
        stage = SpecStage(
            spec_writer_agent=writer,
            clarify_agent=clarifier,
            feature_description="Implement OAuth2 login",
        )
        expected_hash = _sha256(spec_text)

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        # spec-writer called once
        assert writer.call_count == 1
        # clarify NOT called
        assert clarifier.call_count == 0
        # StageResult returned
        assert isinstance(result, StageResult)
        assert result.passed is True
        # artifacts present with correct hash
        assert expected_hash in str(result.data)
        # stage_complete present
        assert "stage_complete" in result.data

    @pytest.mark.asyncio
    async def test_run_full_happy_path_with_nc_markers(self):
        """Full happy path with clarification: spec-writer produces output with NC markers,
        clarify agent is invoked, final artifact frozen from clarified content."""
        initial_spec = "# Task API Spec\n\n[NC: REST or GraphQL?]"
        clarified_spec = "# Task API Spec\n\nREST API with JSON responses."
        writer = _make_spec_writer_agent(initial_spec)
        clarifier = _make_clarify_agent(clarified_spec)
        stage = SpecStage(
            spec_writer_agent=writer,
            clarify_agent=clarifier,
            feature_description="Task management API",
        )
        clarified_hash = _sha256(clarified_spec)

        with patch(
            "orchestrator.perception.detect_nc_markers",
            return_value=["[NC: REST or GraphQL?]"],
        ):
            result = await stage.run()

        # spec-writer called once
        assert writer.call_count == 1
        # clarify called once
        assert clarifier.call_count == 1
        # StageResult returned
        assert isinstance(result, StageResult)
        assert result.passed is True
        # artifact hash reflects clarified content
        assert clarified_hash in str(result.data)
        # stage_complete present
        assert "stage_complete" in result.data

    @pytest.mark.asyncio
    async def test_run_data_dict_has_required_top_level_keys(self):
        """StageResult.data MUST contain 'artifacts' and 'stage_complete' keys."""
        writer = _make_spec_writer_agent("# Spec\n\nReady.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        for required_key in ("artifacts", "stage_complete"):
            assert required_key in result.data, (
                f"StageResult.data must contain key {required_key!r}. "
                f"Present keys: {list(result.data.keys())}"
            )

    @pytest.mark.asyncio
    async def test_run_returned_stage_result_passed_true(self):
        """run() MUST return StageResult with passed=True on a successful spec run."""
        writer = _make_spec_writer_agent("# Spec done.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_run_still_subclasses_stage_abc(self):
        """Even with new collaborators, SpecStage MUST still be a StageABC subclass."""
        stage = SpecStage(
            spec_writer_agent=_make_spec_writer_agent(),
            clarify_agent=_make_clarify_agent(),
        )
        assert isinstance(stage, StageABC)


# ---------------------------------------------------------------------------
# 8. Edge cases
# ---------------------------------------------------------------------------


class TestSpecStageRunEdgeCases:
    """Edge cases for SpecStage.run()."""

    @pytest.mark.asyncio
    async def test_run_handles_empty_spec_writer_output(self):
        """run() MUST handle empty string output from spec-writer without raising."""
        writer = _make_spec_writer_agent("")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert isinstance(result, StageResult), (
            "run() must return StageResult even when spec-writer produces empty output"
        )

    @pytest.mark.asyncio
    async def test_run_handles_spec_writer_with_only_nc_markers(self):
        """run() MUST handle spec-writer output that consists entirely of NC markers."""
        writer = _make_spec_writer_agent("[NC: what is this?] [NC: and this?]")
        clarifier = _make_clarify_agent("All questions answered.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=clarifier)

        with patch(
            "orchestrator.perception.detect_nc_markers",
            return_value=["[NC: what is this?]", "[NC: and this?]"],
        ):
            result = await stage.run()

        assert isinstance(result, StageResult)
        assert clarifier.call_count == 1

    @pytest.mark.asyncio
    async def test_run_with_no_feature_description_does_not_raise(self):
        """run() MUST NOT raise if feature_description was not provided."""
        writer = _make_spec_writer_agent("# Generic spec.")
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        assert isinstance(result, StageResult)

    @pytest.mark.asyncio
    async def test_run_artifact_hash_is_deterministic(self):
        """The SHA-256 hash for the same content MUST be identical across two calls."""
        spec_text = "# Deterministic spec content."
        writer1 = _make_spec_writer_agent(spec_text)
        writer2 = _make_spec_writer_agent(spec_text)
        stage1 = SpecStage(spec_writer_agent=writer1, clarify_agent=_make_clarify_agent())
        stage2 = SpecStage(spec_writer_agent=writer2, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result1 = await stage1.run()

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result2 = await stage2.run()

        # Extract all 64-char hex strings from each result
        def _extract_hashes(data: dict) -> set[str]:
            hashes: set[str] = set()
            for v in str(data):
                pass  # handled below
            data_str = str(data)
            import re
            return set(re.findall(r'[0-9a-f]{64}', data_str))

        hashes1 = _extract_hashes(result1.data)
        hashes2 = _extract_hashes(result2.data)
        assert hashes1 == hashes2, (
            f"SHA-256 hashes must be deterministic for the same content. "
            f"run1 hashes: {hashes1}, run2 hashes: {hashes2}"
        )

    @pytest.mark.asyncio
    async def test_run_different_spec_content_produces_different_hash(self):
        """Two different spec texts MUST produce different SHA-256 hashes."""
        text_a = "# Spec version A\n\nContent A."
        text_b = "# Spec version B\n\nContent B."
        hash_a = _sha256(text_a)
        hash_b = _sha256(text_b)
        assert hash_a != hash_b  # sanity check on the helper

        writer = _make_spec_writer_agent(text_a)
        stage = SpecStage(spec_writer_agent=writer, clarify_agent=_make_clarify_agent())

        with patch("orchestrator.perception.detect_nc_markers", return_value=[]):
            result = await stage.run()

        data_str = str(result.data)
        assert hash_a in data_str, (
            f"Hash for text_a must appear in result data. data={result.data!r}"
        )
        assert hash_b not in data_str, (
            f"Hash for text_b must NOT appear in result data when text_a was used. "
            f"data={result.data!r}"
        )
