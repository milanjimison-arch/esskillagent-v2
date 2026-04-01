"""RED-phase tests for engine.run() full pipeline flow.

Covers behaviors required by the task spec:
  1. Stage sequencing: spec → plan → implement → acceptance (strict order)
  2. Process lock: only one pipeline instance can run at a time (concurrent
     calls to run() on the same engine must be serialised via the lock)
  3. Precondition validation: each stage checks preconditions before starting
  4. Artifact freezing: completed stage artifacts get content hashes
  5. INV-1: Events append-only, immutable (no deletion or mutation of events)
  6. INV-2: Prior-event linkage (each event references previous event ID/hash)
  7. INV-3: red_pass before green_start ordering enforced
  8. INV-4: Stage transition preconditions enforced
  9. CLI `run` subcommand wiring

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/engine.py (or its collaborators) provides the full
implementations described below.

Implementation gap summary (what must be added to make tests go GREEN):
  - PipelineEngine.run() must acquire self.lock before starting execution
    and release it when done (process lock, concurrent guard)
  - PipelineEngine.run() must call validate_preconditions() (or equivalent)
    before dispatching each stage
  - PipelineEngine.run() must freeze artifacts after each successful stage
    (calling freeze_stage_artifacts() or equivalent)
  - PipelineEngine must emit / enforce LVL invariants INV-1 through INV-4
  - CLI `run` subcommand must build a fully-wired engine and call run()

FR references:
  FR-001  Stage sequencing
  FR-059  Process lock ownership and injection
  INV-1   Events append-only
  INV-2   Prior-event linkage
  INV-3   red_pass before green_start
  INV-4   Stage transition preconditions
  FR-CLI-001  CLI run wiring
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from orchestrator.engine import PipelineEngine, PipelineResult, STAGE_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_stage_result(name: str = "spec") -> MagicMock:
    r = MagicMock()
    r.passed = True
    r.attempts = 1
    r.data = {"stage": name, "artifacts": [f"{name}_output.txt"]}
    r.error = None
    return r


def _failing_stage_result(name: str = "spec") -> MagicMock:
    r = MagicMock()
    r.passed = False
    r.attempts = 3
    r.data = {}
    r.error = f"{name} failed"
    return r


def _make_stage(passing: bool = True, name: str = "spec") -> MagicMock:
    stage = MagicMock(name=f"MockStage_{name}")
    if passing:
        stage.execute_with_gate = AsyncMock(return_value=_passing_stage_result(name))
    else:
        stage.execute_with_gate = AsyncMock(return_value=_failing_stage_result(name))
    return stage


def _build_engine(
    stage_overrides: dict | None = None,
    skip_stages: list[str] | None = None,
    config: dict | None = None,
) -> PipelineEngine:
    """Build a PipelineEngine with all four stages mocked."""
    cfg = {"skip_stages": skip_stages or [], "max_retries": 3}
    if config:
        cfg.update(config)
    overrides = stage_overrides or {}
    stages = {n: overrides.get(n, _make_stage(True, n)) for n in STAGE_NAMES}
    return PipelineEngine(stages=stages, config=cfg)


# ===========================================================================
# 1. Stage sequencing (already tested in test_engine.py; these are additive
#    tests that focus on the full-pipeline contract as a whole)
# ===========================================================================


class TestFullPipelineStageSequencing:
    """FR-001: Full pipeline must execute all four stages in strict order."""

    @pytest.mark.asyncio
    async def test_FR001_stage_sequence_is_spec_plan_implement_acceptance(self):
        """FR-001: Stages must execute in exactly (spec, plan, implement, acceptance) order."""
        call_order: list[str] = []

        async def _gate(name: str):
            call_order.append(name)
            return _passing_stage_result(name)

        stages = {
            n: MagicMock(execute_with_gate=AsyncMock(side_effect=lambda n=n: _gate(n)))
            for n in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        result = await engine.run()

        assert result.passed is True
        assert call_order == ["spec", "plan", "implement", "acceptance"], (
            f"Expected spec→plan→implement→acceptance, got {call_order}"
        )

    @pytest.mark.asyncio
    async def test_FR001_later_stage_not_started_before_prior_completes(self):
        """FR-001: Plan must not start until spec has finished (no parallelism)."""
        completion_events: list[str] = []

        async def _spec_gate():
            await asyncio.sleep(0)  # yield, simulating async work
            completion_events.append("spec_done")
            return _passing_stage_result("spec")

        async def _plan_gate():
            completion_events.append("plan_started")
            return _passing_stage_result("plan")

        spec_mock = MagicMock(execute_with_gate=AsyncMock(side_effect=_spec_gate))
        plan_mock = MagicMock(execute_with_gate=AsyncMock(side_effect=_plan_gate))

        engine = _build_engine(stage_overrides={"spec": spec_mock, "plan": plan_mock})
        await engine.run()

        assert completion_events.index("spec_done") < completion_events.index("plan_started"), (
            "plan must not start before spec has completed"
        )

    @pytest.mark.asyncio
    async def test_FR001_full_pipeline_passes_returns_all_four_stage_results(self):
        """FR-001: A successful full pipeline returns results for all four stages."""
        engine = _build_engine()
        result = await engine.run()

        assert result.passed is True
        assert set(result.stage_results.keys()) == set(STAGE_NAMES), (
            f"All four stage names must appear in stage_results, got {list(result.stage_results.keys())}"
        )

    @pytest.mark.asyncio
    async def test_FR001_acceptance_stage_is_final_none_follows_it(self):
        """FR-001: After acceptance completes, no further stage is invoked."""
        extra_stage = _make_stage(True, "phantom")
        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        # We cannot inject a 5th stage; verify the engine respects STAGE_NAMES exactly
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        result = await engine.run()

        assert result.passed is True
        assert list(result.stage_results.keys()) == list(STAGE_NAMES), (
            "stage_results must contain exactly the four canonical stages in order"
        )


# ===========================================================================
# 2. Process lock — concurrent run() calls on same engine are serialised
# ===========================================================================


class TestProcessLock:
    """FR-059: engine.run() MUST acquire the process lock so that concurrent
    invocations on the same engine instance are serialised, not interleaved."""

    @pytest.mark.asyncio
    async def test_FR059_run_acquires_lock_during_execution(self):
        """FR-059: engine.lock MUST be held (locked) while run() is executing."""
        lock_states_during_run: list[bool] = []

        async def _gate(name: str):
            # Sample the lock state from inside a stage execution.
            # If the engine holds the lock during run(), this will be True.
            lock_states_during_run.append(engine.lock.locked())
            return _passing_stage_result(name)

        stages = {
            n: MagicMock(execute_with_gate=AsyncMock(side_effect=lambda n=n: _gate(n)))
            for n in STAGE_NAMES
        }
        engine = PipelineEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert all(lock_states_during_run), (
            "engine.lock must be held (locked=True) during every stage execution; "
            f"got lock states: {lock_states_during_run}"
        )

    @pytest.mark.asyncio
    async def test_FR059_concurrent_run_calls_are_serialised(self):
        """FR-059: Two concurrent run() calls on the same engine must not overlap."""
        execution_log: list[str] = []

        async def _gate_logging(prefix: str, name: str):
            execution_log.append(f"{prefix}:{name}:start")
            await asyncio.sleep(0)
            execution_log.append(f"{prefix}:{name}:end")
            return _passing_stage_result(name)

        # Build two separate stage dicts that log with different prefixes
        stages_a = {
            n: MagicMock(
                execute_with_gate=AsyncMock(
                    side_effect=lambda n=n: _gate_logging("A", n)
                )
            )
            for n in STAGE_NAMES
        }
        stages_b = {
            n: MagicMock(
                execute_with_gate=AsyncMock(
                    side_effect=lambda n=n: _gate_logging("B", n)
                )
            )
            for n in STAGE_NAMES
        }

        # Share a single engine (same lock) — override the stages between calls
        engine = PipelineEngine(stages=stages_a, config={"skip_stages": []})

        # Start both runs concurrently on the same engine
        async def run_a():
            engine._stages = stages_a
            return await engine.run()

        async def run_b():
            engine._stages = stages_b
            return await engine.run()

        await asyncio.gather(run_a(), run_b())

        # Verify no interleaving: all A events must be contiguous or all B events
        # must be contiguous (one run completes before the other starts).
        # Find where A ends and B begins (or vice versa).
        prefixes = [entry.split(":")[0] for entry in execution_log]
        # There must be a clean boundary with no ABAB interleaving of starts
        first_switch = None
        for i in range(1, len(prefixes)):
            if prefixes[i] != prefixes[i - 1]:
                if first_switch is None:
                    first_switch = i
                else:
                    # A second switch means interleaving occurred
                    interleaved = execution_log
                    assert False, (
                        "Concurrent run() calls on the same engine were interleaved. "
                        f"Lock must serialise them. Log: {interleaved}"
                    )

    @pytest.mark.asyncio
    async def test_FR059_lock_released_after_run_completes_normally(self):
        """FR-059: After run() returns normally, the lock MUST be released."""
        engine = _build_engine()
        assert engine.lock.locked() is False
        await engine.run()
        assert engine.lock.locked() is False, (
            "engine.lock must be released after a successful run()"
        )

    @pytest.mark.asyncio
    async def test_FR059_lock_released_after_run_with_failed_stage(self):
        """FR-059: After run() with a failing stage, the lock MUST still be released."""
        engine = _build_engine(
            stage_overrides={"spec": _make_stage(False, "spec")}
        )
        await engine.run()
        assert engine.lock.locked() is False, (
            "engine.lock must be released even when a stage fails"
        )

    @pytest.mark.asyncio
    async def test_FR059_lock_released_after_stage_raises_exception(self):
        """FR-059: If a stage raises an unexpected exception, the lock MUST still be released."""
        boom_stage = MagicMock()
        boom_stage.execute_with_gate = AsyncMock(side_effect=RuntimeError("boom"))
        engine = _build_engine(stage_overrides={"spec": boom_stage})

        with pytest.raises(RuntimeError, match="boom"):
            await engine.run()

        assert engine.lock.locked() is False, (
            "engine.lock must be released even when an exception propagates from a stage"
        )


# ===========================================================================
# 3. Precondition validation
# ===========================================================================


class TestPreconditionValidation:
    """INV-4: Each stage MUST validate its preconditions before starting.

    The engine is responsible for calling a precondition check before
    dispatching each stage. If preconditions are not met, the pipeline
    MUST stop with a failure rather than running the stage in an invalid state.
    """

    @pytest.mark.asyncio
    async def test_INV4_engine_calls_precondition_check_before_each_stage(self):
        """INV-4: engine.run() MUST invoke a precondition validator for every stage."""
        checked_stages: list[str] = []

        class PreconditionTrackingEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                checked_stages.append(stage_name)
                return True  # all pass

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionTrackingEngine(stages=stages, config={"skip_stages": []})
        result = await engine.run()

        assert result.passed is True
        assert set(checked_stages) == set(STAGE_NAMES), (
            f"Preconditions must be checked for all stages, checked: {checked_stages}"
        )

    @pytest.mark.asyncio
    async def test_INV4_precondition_failure_stops_pipeline_before_stage_runs(self):
        """INV-4: If preconditions fail for a stage, that stage MUST NOT run
        and the pipeline MUST stop with a failure result."""
        plan_mock = _make_stage(True, "plan")

        class PreconditionFailingEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                # Fail preconditions for 'plan'
                return stage_name != "plan"

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["plan"] = plan_mock
        engine = PreconditionFailingEngine(
            stages=stages, config={"skip_stages": []}
        )
        result = await engine.run()

        # plan should NOT have been called
        plan_mock.execute_with_gate.assert_not_awaited()
        assert result.passed is False, (
            "Pipeline must fail when a stage precondition is not met"
        )

    @pytest.mark.asyncio
    async def test_INV4_precondition_failure_sets_failed_stage(self):
        """INV-4: failed_stage in PipelineResult must identify the stage whose
        preconditions were not met."""
        class PreconditionFailingEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                return stage_name != "implement"

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionFailingEngine(
            stages=stages, config={"skip_stages": []}
        )
        result = await engine.run()

        assert result.failed_stage == "implement", (
            f"failed_stage must be 'implement' (precondition failed), got {result.failed_stage!r}"
        )

    @pytest.mark.asyncio
    async def test_INV4_stage_after_precondition_failure_is_not_executed(self):
        """INV-4: Stages after the one that fails preconditions must not run."""
        acceptance_mock = _make_stage(True, "acceptance")

        class PreconditionFailingEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                return stage_name != "implement"

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["acceptance"] = acceptance_mock
        engine = PreconditionFailingEngine(
            stages=stages, config={"skip_stages": []}
        )
        await engine.run()

        acceptance_mock.execute_with_gate.assert_not_awaited()


# ===========================================================================
# 4. Artifact freezing after each successful stage
# ===========================================================================


class TestArtifactFreezing:
    """After each stage completes successfully, the engine MUST freeze the
    stage's artifacts by computing and recording their content hashes.

    Implementation: engine.run() must call freeze_stage_artifacts(stage_name,
    stage_result) (or equivalent) after each successful stage.
    """

    @pytest.mark.asyncio
    async def test_artifact_freezing_called_after_each_successful_stage(self):
        """engine.run() MUST call _freeze_stage_artifacts() for each passing stage."""
        frozen_stages: list[str] = []

        class ArtifactFreezingEngine(PipelineEngine):
            def _freeze_stage_artifacts(self, stage_name: str, stage_result) -> None:
                frozen_stages.append(stage_name)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = ArtifactFreezingEngine(stages=stages, config={"skip_stages": []})
        result = await engine.run()

        assert result.passed is True
        assert frozen_stages == list(STAGE_NAMES), (
            f"_freeze_stage_artifacts must be called for every passing stage. "
            f"Expected {list(STAGE_NAMES)}, got {frozen_stages}"
        )

    @pytest.mark.asyncio
    async def test_artifact_freezing_not_called_for_failed_stage(self):
        """engine.run() MUST NOT freeze artifacts for a stage that fails."""
        frozen_stages: list[str] = []

        class ArtifactFreezingEngine(PipelineEngine):
            def _freeze_stage_artifacts(self, stage_name: str, stage_result) -> None:
                frozen_stages.append(stage_name)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["plan"] = _make_stage(False, "plan")
        engine = ArtifactFreezingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        # spec passes → frozen; plan fails → NOT frozen; later stages not reached
        assert "plan" not in frozen_stages, (
            "_freeze_stage_artifacts must NOT be called for the failed stage 'plan'"
        )
        assert "implement" not in frozen_stages, (
            "_freeze_stage_artifacts must NOT be called for stages after failure"
        )

    @pytest.mark.asyncio
    async def test_artifact_freezing_called_for_stages_before_failure(self):
        """Stages that pass before the failure point must still be frozen."""
        frozen_stages: list[str] = []

        class ArtifactFreezingEngine(PipelineEngine):
            def _freeze_stage_artifacts(self, stage_name: str, stage_result) -> None:
                frozen_stages.append(stage_name)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["plan"] = _make_stage(False, "plan")
        engine = ArtifactFreezingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert "spec" in frozen_stages, (
            "spec passed before the failure; its artifacts must be frozen"
        )

    @pytest.mark.asyncio
    async def test_artifact_freezing_receives_stage_result(self):
        """_freeze_stage_artifacts must receive the actual StageResult object."""
        freeze_calls: list[tuple] = []

        class ArtifactFreezingEngine(PipelineEngine):
            def _freeze_stage_artifacts(self, stage_name: str, stage_result) -> None:
                freeze_calls.append((stage_name, stage_result))

        spec_result = _passing_stage_result("spec")
        spec_mock = MagicMock()
        spec_mock.execute_with_gate = AsyncMock(return_value=spec_result)
        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["spec"] = spec_mock

        engine = ArtifactFreezingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        spec_freeze_call = next(
            (c for c in freeze_calls if c[0] == "spec"), None
        )
        assert spec_freeze_call is not None, "No freeze call recorded for 'spec'"
        assert spec_freeze_call[1] is spec_result, (
            "_freeze_stage_artifacts must receive the actual StageResult for 'spec'"
        )

    @pytest.mark.asyncio
    async def test_artifact_freezing_not_called_for_skipped_stages(self):
        """Skipped stages have no artifacts to freeze."""
        frozen_stages: list[str] = []

        class ArtifactFreezingEngine(PipelineEngine):
            def _freeze_stage_artifacts(self, stage_name: str, stage_result) -> None:
                frozen_stages.append(stage_name)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = ArtifactFreezingEngine(
            stages=stages, config={"skip_stages": ["spec", "plan"]}
        )
        await engine.run()

        assert "spec" not in frozen_stages, "spec was skipped; must not be frozen"
        assert "plan" not in frozen_stages, "plan was skipped; must not be frozen"


# ===========================================================================
# 5. INV-1: Events append-only and immutable
# ===========================================================================


class TestINV1EventsAppendOnly:
    """INV-1: LVL events MUST be append-only and immutable once written.

    The engine must enforce that events can never be deleted or mutated.
    This is tested by verifying that the engine's event-emitting interface
    raises an error (or otherwise refuses) when deletion or mutation is
    attempted on an already-written event.
    """

    @pytest.mark.asyncio
    async def test_INV1_engine_emits_stage_complete_event_after_each_stage(self):
        """INV-1: engine.run() MUST emit a 'stage_complete' event after each passing stage."""
        emitted_events: list[dict] = []

        class EventRecordingEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
                emitted_events.append({"type": event_type, "stage": stage, "payload": payload})

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = EventRecordingEngine(stages=stages, config={"skip_stages": []})
        result = await engine.run()

        assert result.passed is True
        stage_complete_events = [e for e in emitted_events if e["type"] == "stage_complete"]
        assert len(stage_complete_events) == 4, (
            f"Must emit exactly 4 'stage_complete' events (one per stage), "
            f"got {len(stage_complete_events)}: {stage_complete_events}"
        )

    @pytest.mark.asyncio
    async def test_INV1_stage_complete_event_emitted_for_correct_stages(self):
        """INV-1: Each 'stage_complete' event must reference the corresponding stage name."""
        emitted_events: list[dict] = []

        class EventRecordingEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
                emitted_events.append({"type": event_type, "stage": stage, "payload": payload})

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = EventRecordingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        emitted_stage_names = [
            e["stage"] for e in emitted_events if e["type"] == "stage_complete"
        ]
        assert emitted_stage_names == list(STAGE_NAMES), (
            f"stage_complete events must reference stages in order {list(STAGE_NAMES)}, "
            f"got {emitted_stage_names}"
        )

    @pytest.mark.asyncio
    async def test_INV1_no_stage_complete_event_for_failed_stage(self):
        """INV-1: 'stage_complete' must NOT be emitted for a stage that fails."""
        emitted_events: list[dict] = []

        class EventRecordingEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
                emitted_events.append({"type": event_type, "stage": stage, "payload": payload})

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        stages["plan"] = _make_stage(False, "plan")
        engine = EventRecordingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        plan_complete = [
            e for e in emitted_events
            if e["type"] == "stage_complete" and e["stage"] == "plan"
        ]
        assert len(plan_complete) == 0, (
            "stage_complete must NOT be emitted when a stage fails"
        )

    @pytest.mark.asyncio
    async def test_INV1_event_record_is_immutable(self):
        """INV-1: An emitted event record MUST be immutable — it cannot be altered
        after emission. The engine's internal event representation must be frozen.

        This test verifies that:
        1. The engine calls _emit_event() after each successful stage.
        2. The PipelineEvent objects emitted are frozen (immutable).
        """
        from orchestrator.engine import PipelineEvent
        captured_events: list = []

        class EventCapturingEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict) -> None:
                evt = PipelineEvent(event_type=event_type, stage=stage, payload=payload)
                captured_events.append(evt)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = EventCapturingEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        # The engine must have emitted at least one event (via _emit_event hook).
        # If no events were emitted, INV-1 cannot be satisfied — fail RED.
        assert len(captured_events) > 0, (
            "INV-1: engine.run() must call _emit_event() at least once. "
            "No events captured — implementation is missing."
        )
        # All emitted events must be immutable
        for evt in captured_events:
            with pytest.raises((AttributeError, TypeError)):
                evt.event_type = "mutated"  # type: ignore[misc]


# ===========================================================================
# 6. INV-2: Prior-event linkage (event chain integrity)
# ===========================================================================


class TestINV2PriorEventLinkage:
    """INV-2: Each event emitted by the engine MUST reference the previous
    event's identifier (prior-event linkage / event chain integrity).

    The first event in a run has no prior event (prev_id = None).
    Every subsequent event must carry the ID of the immediately preceding event.
    """

    @pytest.mark.asyncio
    async def test_INV2_each_event_has_prev_id_referencing_prior(self):
        """INV-2: All events except the first must carry a non-None prev_id that
        equals the id of the immediately preceding event."""
        emitted_events: list = []

        class EventChainEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict):
                from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]
                prev_id = emitted_events[-1].event_id if emitted_events else None
                evt = PipelineEvent(
                    event_type=event_type,
                    stage=stage,
                    payload=payload,
                    prev_event_id=prev_id,
                )
                emitted_events.append(evt)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = EventChainEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert len(emitted_events) >= 4, "Must emit at least 4 events for a full run"

        # First event: prev_id must be None
        assert emitted_events[0].prev_event_id is None, (
            "The first event's prev_event_id must be None"
        )

        # All subsequent events: prev_id must match the preceding event's id
        for i in range(1, len(emitted_events)):
            expected_prev = emitted_events[i - 1].event_id
            actual_prev = emitted_events[i].prev_event_id
            assert actual_prev == expected_prev, (
                f"Event[{i}] prev_event_id={actual_prev!r} must equal "
                f"Event[{i-1}].event_id={expected_prev!r} (INV-2 chain broken)"
            )

    @pytest.mark.asyncio
    async def test_INV2_event_chain_is_contiguous_no_gaps(self):
        """INV-2: The event chain must have no gaps — every event id must appear
        exactly once as the prev_id of the subsequent event."""
        emitted_events: list = []

        class EventChainEngine(PipelineEngine):
            def _emit_event(self, event_type: str, stage: str, payload: dict):
                from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]
                prev_id = emitted_events[-1].event_id if emitted_events else None
                evt = PipelineEvent(
                    event_type=event_type,
                    stage=stage,
                    payload=payload,
                    prev_event_id=prev_id,
                )
                emitted_events.append(evt)

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = EventChainEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        # Verify that the chain can be traversed from last to first without gaps
        ids = {e.event_id for e in emitted_events}
        prev_ids = {e.prev_event_id for e in emitted_events if e.prev_event_id is not None}

        # Every prev_id must reference a real event id (no dangling references)
        dangling = prev_ids - ids
        assert len(dangling) == 0, (
            f"INV-2: Found dangling prev_event_id references: {dangling}"
        )

    @pytest.mark.asyncio
    async def test_INV2_pipeline_event_exposes_event_id_and_prev_event_id(self):
        """INV-2: PipelineEvent must expose both event_id and prev_event_id fields."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        evt = PipelineEvent(
            event_type="stage_complete",
            stage="spec",
            payload={"result": "ok"},
            prev_event_id=None,
        )
        assert hasattr(evt, "event_id"), "PipelineEvent must have 'event_id' field"
        assert hasattr(evt, "prev_event_id"), "PipelineEvent must have 'prev_event_id' field"
        assert evt.prev_event_id is None
        assert isinstance(evt.event_id, str) and evt.event_id, (
            "event_id must be a non-empty string"
        )


# ===========================================================================
# 7. INV-3: red_pass before green_start ordering
# ===========================================================================


class TestINV3RedPassBeforeGreenStart:
    """INV-3: In any TDD cycle tracked by the engine, a 'red_pass' event MUST
    precede the corresponding 'green_start' event.

    The engine must enforce this ordering and raise an error (or refuse to
    proceed) if green_start is emitted without a prior red_pass.
    """

    @pytest.mark.asyncio
    async def test_INV3_engine_enforces_red_pass_before_green_start(self):
        """INV-3: Emitting green_start without prior red_pass must raise an error
        or cause pipeline failure (not silently proceed).

        The engine must expose _emit_event() and enforce that any green_start
        event is preceded by red_pass in the same TDD cycle.
        """
        engine = _build_engine()
        # The engine must have _emit_event to enforce INV-3 ordering.
        # Without it, INV-3 cannot be enforced — assertion fails RED.
        emit_fn = getattr(engine, "_emit_event", None)
        assert callable(emit_fn), (
            "INV-3: PipelineEngine must expose _emit_event() to enforce "
            "red_pass-before-green_start ordering. Method not found."
        )
        # With _emit_event present, green_start without prior red_pass must raise.
        with pytest.raises((ValueError, RuntimeError, AssertionError)):
            engine._emit_event("green_start", "spec", {"task": "T001"})

    @pytest.mark.asyncio
    async def test_INV3_red_pass_then_green_start_is_valid(self):
        """INV-3: Emitting red_pass then green_start in correct order must succeed.

        After emitting red_pass for a task, the engine must accept green_start
        for the same task without raising an error.
        """
        engine = _build_engine()
        emit_fn = getattr(engine, "_emit_event", None)
        assert callable(emit_fn), (
            "INV-3: PipelineEngine must expose _emit_event() to enforce "
            "TDD ordering. Method not found (RED: implementation missing)."
        )
        # Emit red_pass first — this establishes the correct precondition
        engine._emit_event("red_pass", "spec", {"task": "T001"})
        # Now green_start must be accepted (no exception)
        engine._emit_event("green_start", "spec", {"task": "T001"})
        # If we reach here, the valid ordering was accepted — assert it
        assert True, "red_pass then green_start sequence must be accepted"

    @pytest.mark.asyncio
    async def test_INV3_green_start_after_red_pass_same_task_is_valid(self):
        """INV-3: red_pass(T001) followed by green_start(T001) is a valid sequence.

        The engine must record and accept this ordering without raising.
        """
        engine = _build_engine()
        emit_fn = getattr(engine, "_emit_event", None)
        assert callable(emit_fn), (
            "INV-3: PipelineEngine._emit_event must exist. "
            "Without it, INV-3 ordering cannot be tracked (RED)."
        )
        # Both event types must be accepted in valid order
        # (no exception raised = ordering accepted)
        engine._emit_event("red_pass", "spec", {"task": "T001"})
        engine._emit_event("green_start", "spec", {"task": "T001"})
        # Confirm the events were recorded by checking the engine state
        # The engine must track events internally
        assert hasattr(engine, "_events") or hasattr(engine, "_event_log"), (
            "INV-3: Engine must maintain an internal event log to track "
            "red_pass/green_start ordering. No _events or _event_log attribute found."
        )

    def test_INV3_engine_exposes_emit_event_method(self):
        """INV-3: engine must expose a _emit_event method for TDD event emission."""
        engine = _build_engine()
        assert callable(getattr(engine, "_emit_event", None)), (
            "PipelineEngine must expose a '_emit_event' method for LVL event emission"
        )


# ===========================================================================
# 8. INV-4: Stage transition preconditions (more detailed)
# ===========================================================================


class TestINV4StageTransitionPreconditions:
    """INV-4: Stage transitions require all preconditions to be met.

    Each stage defines preconditions (typically: prior stages completed
    successfully, required artifacts exist and are unfrozen). The engine
    must query these preconditions before starting a stage.
    """

    @pytest.mark.asyncio
    async def test_INV4_plan_precondition_requires_spec_complete(self):
        """INV-4: plan stage must require spec to have completed successfully."""
        precondition_queries: list[tuple] = []

        class PreconditionQueryEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                precondition_queries.append((stage_name, "queried"))
                return True

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionQueryEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        queried_names = [q[0] for q in precondition_queries]
        # plan must be checked (which implicitly requires spec to have passed)
        assert "plan" in queried_names, (
            "INV-4: plan preconditions must be checked before plan runs"
        )

    @pytest.mark.asyncio
    async def test_INV4_implement_precondition_requires_plan_complete(self):
        """INV-4: implement stage must require plan to have completed successfully."""
        precondition_queries: list[tuple] = []

        class PreconditionQueryEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                precondition_queries.append((stage_name, "queried"))
                return True

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionQueryEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        queried_names = [q[0] for q in precondition_queries]
        assert "implement" in queried_names, (
            "INV-4: implement preconditions must be checked before implement runs"
        )

    @pytest.mark.asyncio
    async def test_INV4_acceptance_precondition_requires_implement_complete(self):
        """INV-4: acceptance stage must require implement to have completed successfully."""
        precondition_queries: list[tuple] = []

        class PreconditionQueryEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                precondition_queries.append((stage_name, "queried"))
                return True

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionQueryEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        queried_names = [q[0] for q in precondition_queries]
        assert "acceptance" in queried_names, (
            "INV-4: acceptance preconditions must be checked before acceptance runs"
        )

    @pytest.mark.asyncio
    async def test_INV4_precondition_check_called_in_stage_order(self):
        """INV-4: Precondition checks must occur in stage execution order."""
        check_order: list[str] = []

        class OrderedPreconditionEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                check_order.append(stage_name)
                return True

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = OrderedPreconditionEngine(stages=stages, config={"skip_stages": []})
        await engine.run()

        assert check_order == list(STAGE_NAMES), (
            f"Precondition checks must occur in stage order {list(STAGE_NAMES)}, "
            f"got {check_order}"
        )

    @pytest.mark.asyncio
    async def test_INV4_skipped_stage_does_not_trigger_precondition_check(self):
        """INV-4: Skipped stages should not have their preconditions checked
        (they are not being run, so there is nothing to validate)."""
        checked: list[str] = []

        class PreconditionTrackingEngine(PipelineEngine):
            def _check_preconditions(self, stage_name: str) -> bool:
                checked.append(stage_name)
                return True

        stages = {n: _make_stage(True, n) for n in STAGE_NAMES}
        engine = PreconditionTrackingEngine(
            stages=stages, config={"skip_stages": ["spec"]}
        )
        await engine.run()

        assert "spec" not in checked, (
            "Preconditions must not be checked for skipped stage 'spec'"
        )


# ===========================================================================
# 9. CLI `run` subcommand wiring
# ===========================================================================


class TestCLIRunSubcommandWiring:
    """FR-CLI-001: The CLI 'run' subcommand must build a fully-wired engine
    and delegate to engine.run(). The engine produced by _build_engine must
    have all four stages wired and the pipeline lock configured.
    """

    def test_FR_CLI_001_run_subcommand_wires_to_engine_run(self):
        """FR-CLI-001: 'run' dispatches to engine.run() via asyncio.run."""
        from orchestrator.cli import main

        mock_result = MagicMock()
        mock_result.passed = True
        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_result)

        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "run"]):
            try:
                main()
            except SystemExit:
                pass

        mock_engine.run.assert_called_once()

    def test_FR_CLI_001_run_passes_config_to_engine_builder(self):
        """FR-CLI-001: 'run --config path' must pass the config path to _build_engine."""
        from orchestrator.cli import main

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=MagicMock(passed=True))

        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine) as mock_build, \
             patch("sys.argv", ["orchestrator", "run", "--config", "/tmp/my_config.yaml"]):
            try:
                main()
            except SystemExit:
                pass

        call_args = mock_build.call_args
        assert call_args is not None, "_build_engine must be called"
        # config path must appear somewhere in the call args
        all_args = list(call_args.args) + list(call_args.kwargs.values())
        assert "/tmp/my_config.yaml" in str(all_args), (
            "_build_engine must receive the --config path, "
            f"got call args: {call_args}"
        )

    def test_FR_CLI_001_run_wired_engine_has_process_lock(self):
        """FR-CLI-001: The engine built by _build_engine for the 'run' subcommand
        must have a process lock (asyncio.Lock) configured."""
        import asyncio as _asyncio
        from orchestrator.cli import _build_engine as cli_build_engine

        engine = cli_build_engine()
        assert hasattr(engine, "lock"), (
            "Engine built by CLI _build_engine must have a 'lock' attribute"
        )
        assert isinstance(engine.lock, _asyncio.Lock), (
            f"engine.lock must be asyncio.Lock, got {type(engine.lock).__name__}"
        )

    def test_FR_CLI_001_run_does_not_call_resume(self):
        """FR-CLI-001: 'run' subcommand must not call engine.resume()."""
        from orchestrator.cli import main

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=MagicMock(passed=True))
        mock_engine.resume = AsyncMock(return_value=MagicMock(passed=True))

        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "run"]):
            try:
                main()
            except SystemExit:
                pass

        mock_engine.resume.assert_not_called()

    def test_FR_CLI_001_check_git_repo_called_before_engine_build(self):
        """FR-CLI-005: git check must happen before the engine is built or run()
        is called. This ensures 'run' operates in a valid git workspace."""
        call_sequence: list[str] = []

        from orchestrator.cli import main

        def _fake_git_check(*args, **kwargs):
            call_sequence.append("git_check")

        mock_engine = MagicMock()

        def _fake_build(*args, **kwargs):
            call_sequence.append("build_engine")
            e = mock_engine
            e.run = AsyncMock(return_value=MagicMock(passed=True))
            return e

        with patch("orchestrator.cli.check_git_repo", side_effect=_fake_git_check), \
             patch("orchestrator.cli._build_engine", side_effect=_fake_build), \
             patch("sys.argv", ["orchestrator", "run"]):
            try:
                main()
            except SystemExit:
                pass

        assert "git_check" in call_sequence, "check_git_repo must be called"
        assert "build_engine" in call_sequence, "_build_engine must be called"
        assert call_sequence.index("git_check") < call_sequence.index("build_engine"), (
            "check_git_repo must be called before _build_engine "
            f"(sequence: {call_sequence})"
        )


# ===========================================================================
# 10. PipelineEvent dataclass — structural contract
# ===========================================================================


class TestPipelineEventDataclass:
    """engine.py must expose a PipelineEvent frozen dataclass that represents
    a single LVL event emitted during a pipeline run.

    This is required to support INV-2 (prior-event linkage) and INV-1
    (immutability).
    """

    def test_pipeline_event_is_importable(self):
        """PipelineEvent must be importable from orchestrator.engine."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]
        assert PipelineEvent is not None

    def test_pipeline_event_is_a_class(self):
        """PipelineEvent must be a class."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]
        assert inspect.isclass(PipelineEvent)

    def test_pipeline_event_is_immutable(self):
        """PipelineEvent must be immutable (frozen dataclass or equivalent)."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        evt = PipelineEvent(
            event_type="stage_complete",
            stage="spec",
            payload={"result": "ok"},
            prev_event_id=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            evt.event_type = "mutated"  # type: ignore[misc]

    def test_pipeline_event_has_required_fields(self):
        """PipelineEvent must expose event_id, event_type, stage, payload,
        prev_event_id fields."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        evt = PipelineEvent(
            event_type="stage_complete",
            stage="plan",
            payload={"status": "passed"},
            prev_event_id="abc123",
        )
        assert hasattr(evt, "event_id"), "PipelineEvent must have 'event_id'"
        assert hasattr(evt, "event_type"), "PipelineEvent must have 'event_type'"
        assert hasattr(evt, "stage"), "PipelineEvent must have 'stage'"
        assert hasattr(evt, "payload"), "PipelineEvent must have 'payload'"
        assert hasattr(evt, "prev_event_id"), "PipelineEvent must have 'prev_event_id'"

    def test_pipeline_event_event_id_is_unique_per_instance(self):
        """Each PipelineEvent instance must have a unique event_id."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        evt_a = PipelineEvent(
            event_type="stage_complete", stage="spec",
            payload={}, prev_event_id=None
        )
        evt_b = PipelineEvent(
            event_type="stage_complete", stage="plan",
            payload={}, prev_event_id=evt_a.event_id
        )
        assert evt_a.event_id != evt_b.event_id, (
            "Each PipelineEvent must have a unique event_id"
        )

    def test_pipeline_event_prev_event_id_none_for_first_event(self):
        """The first event in a chain has prev_event_id=None."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        evt = PipelineEvent(
            event_type="pipeline_start",
            stage="spec",
            payload={},
            prev_event_id=None,
        )
        assert evt.prev_event_id is None

    def test_pipeline_event_accepts_arbitrary_payload_dict(self):
        """PipelineEvent payload must accept any dict (arbitrary JSON-serialisable data)."""
        from orchestrator.engine import PipelineEvent  # type: ignore[attr-defined]

        payload = {
            "artifacts": ["spec.md", "plan.yaml"],
            "duration_ms": 1234,
            "passed": True,
        }
        evt = PipelineEvent(
            event_type="stage_complete",
            stage="implement",
            payload=payload,
            prev_event_id="prev_abc",
        )
        assert evt.payload == payload
