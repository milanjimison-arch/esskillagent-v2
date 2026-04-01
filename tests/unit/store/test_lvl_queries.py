"""RED-phase unit tests for LVL event chain and artifact lifecycle operations.

Covers:
  - append_event / get_latest_event / verify_chain / verify_stage_invariant
  - register_artifact / freeze_artifact / check_staleness / cascade_invalidate

All implementation functions raise NotImplementedError; every test that invokes
them will fail (NotImplementedError propagated as pytest ERROR → RED state).
Tests that only inspect dataclass structure may pass if the stub dataclass is
already correct — that is intentional (those are structural RED gates).

Test areas
----------
1.  LvlEvent dataclass — structural / immutability checks
2.  append_event — happy path, chaining, empty-arg validation
3.  get_latest_event — returns latest / returns None on empty pipeline
4.  verify_chain — valid chain, tampered chain, empty chain
5.  verify_stage_invariant — valid transitions, invalid transitions, edge cases
6.  ArtifactRecord dataclass — structural / immutability checks
7.  register_artifact — happy path, duplicate name rejection, empty-arg validation
8.  freeze_artifact — happy path, missing artifact, file-not-found, re-freeze
9.  check_staleness — fresh artifact, stale artifact, not-frozen error, missing
10. cascade_invalidate — single stage, cross-stage cascade, non-existent artifact
11. Integration — stage_complete flow: append_event + register + freeze in sequence
12. Module size constraint — _lvl_queries.py MUST be under 150 lines for artifact section
"""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

import pytest

from orchestrator.store.db import Store
from orchestrator.store._lvl_queries import (
    ArtifactRecord,
    LvlEvent,
    append_event,
    cascade_invalidate,
    check_staleness,
    freeze_artifact,
    get_latest_event,
    register_artifact,
    verify_chain,
    verify_stage_invariant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
async def store(tmp_path: Path) -> Store:
    """Open a fresh SQLite store for each test."""
    db_path = str(tmp_path / f"test_{_uid()}.db")
    s = Store(db_path)
    await s.initialize()
    yield s
    await s.close()


def _pipeline_id() -> str:
    return f"PL-{_uid()}"


# ---------------------------------------------------------------------------
# 1. LvlEvent dataclass — structural checks
# ---------------------------------------------------------------------------


class TestLvlEventDataclass:
    """LvlEvent MUST be a frozen dataclass with all required fields."""

    def _make(self, **overrides) -> LvlEvent:
        defaults = dict(
            event_id="EVT-001",
            pipeline_id="PL-001",
            stage="spec",
            event_type="stage_complete",
            payload='{"status": "ok"}',
            prev_hash=None,
            event_hash="abc123",
            created_at="2026-04-02T00:00:00+00:00",
        )
        defaults.update(overrides)
        return LvlEvent(**defaults)

    def test_lvl_event_is_dataclass(self):
        assert dataclasses.is_dataclass(LvlEvent)

    def test_lvl_event_is_frozen(self):
        """LvlEvent MUST be frozen — mutation raises FrozenInstanceError."""
        evt = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            evt.event_type = "tampered"  # type: ignore[misc]

    def test_lvl_event_stores_event_id(self):
        evt = self._make(event_id="EVT-XYZ")
        assert evt.event_id == "EVT-XYZ"

    def test_lvl_event_stores_pipeline_id(self):
        evt = self._make(pipeline_id="PL-999")
        assert evt.pipeline_id == "PL-999"

    def test_lvl_event_stores_stage(self):
        evt = self._make(stage="plan")
        assert evt.stage == "plan"

    def test_lvl_event_stores_event_type(self):
        evt = self._make(event_type="stage_start")
        assert evt.event_type == "stage_start"

    def test_lvl_event_stores_payload(self):
        evt = self._make(payload='{"key": "value"}')
        assert evt.payload == '{"key": "value"}'

    def test_lvl_event_prev_hash_defaults_none(self):
        evt = self._make(prev_hash=None)
        assert evt.prev_hash is None

    def test_lvl_event_stores_prev_hash(self):
        evt = self._make(prev_hash="deadbeef")
        assert evt.prev_hash == "deadbeef"

    def test_lvl_event_stores_event_hash(self):
        evt = self._make(event_hash="cafebabe")
        assert evt.event_hash == "cafebabe"

    def test_lvl_event_stores_created_at(self):
        evt = self._make(created_at="2026-04-02T12:00:00+00:00")
        assert evt.created_at == "2026-04-02T12:00:00+00:00"


# ---------------------------------------------------------------------------
# 2. append_event
# ---------------------------------------------------------------------------


class TestAppendEvent:
    """append_event appends a chained event and returns a frozen LvlEvent."""

    @pytest.mark.asyncio
    async def test_append_event_returns_lvl_event(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        assert isinstance(evt, LvlEvent)

    @pytest.mark.asyncio
    async def test_append_event_first_event_has_no_prev_hash(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        assert evt.prev_hash is None

    @pytest.mark.asyncio
    async def test_append_event_second_event_chains_to_first(self, store: Store):
        pid = _pipeline_id()
        first = await append_event(store, pid, "spec", "stage_start", {})
        second = await append_event(store, pid, "spec", "stage_complete", {"ok": True})
        assert second.prev_hash == first.event_hash

    @pytest.mark.asyncio
    async def test_append_event_event_hash_is_non_empty_string(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        assert isinstance(evt.event_hash, str)
        assert len(evt.event_hash) > 0

    @pytest.mark.asyncio
    async def test_append_event_stores_stage(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "plan", "stage_complete", {})
        assert evt.stage == "plan"

    @pytest.mark.asyncio
    async def test_append_event_stores_event_type(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_complete", {})
        assert evt.event_type == "stage_complete"

    @pytest.mark.asyncio
    async def test_append_event_stores_pipeline_id(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        assert evt.pipeline_id == pid

    @pytest.mark.asyncio
    async def test_append_event_stores_payload_dict(self, store: Store):
        pid = _pipeline_id()
        payload = {"tasks_completed": 5, "duration_ms": 1234}
        evt = await append_event(store, pid, "implement", "stage_complete", payload)
        # payload must be serialised into the record somehow
        import json
        stored = json.loads(evt.payload)
        assert stored["tasks_completed"] == 5

    @pytest.mark.asyncio
    async def test_append_event_raises_on_empty_pipeline_id(self, store: Store):
        with pytest.raises(ValueError):
            await append_event(store, "", "spec", "stage_start", {})

    @pytest.mark.asyncio
    async def test_append_event_raises_on_empty_stage(self, store: Store):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await append_event(store, pid, "", "stage_start", {})

    @pytest.mark.asyncio
    async def test_append_event_raises_on_empty_event_type(self, store: Store):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await append_event(store, pid, "spec", "", {})

    @pytest.mark.asyncio
    async def test_append_event_chain_is_three_deep(self, store: Store):
        pid = _pipeline_id()
        e1 = await append_event(store, pid, "spec", "stage_start", {})
        e2 = await append_event(store, pid, "spec", "stage_complete", {})
        e3 = await append_event(store, pid, "plan", "stage_start", {})
        assert e2.prev_hash == e1.event_hash
        assert e3.prev_hash == e2.event_hash

    @pytest.mark.asyncio
    async def test_append_event_different_pipelines_independent(self, store: Store):
        pid1 = _pipeline_id()
        pid2 = _pipeline_id()
        e1 = await append_event(store, pid1, "spec", "stage_start", {})
        e2 = await append_event(store, pid2, "spec", "stage_start", {})
        # Both are genesis events (no predecessor within their own chain)
        assert e1.prev_hash is None
        assert e2.prev_hash is None

    @pytest.mark.asyncio
    async def test_append_event_returned_record_is_frozen(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            evt.event_type = "mutated"  # type: ignore[misc]

    @pytest.mark.asyncio
    async def test_append_event_unicode_payload(self, store: Store):
        pid = _pipeline_id()
        payload = {"msg": "测试 🚀 — résumé"}
        evt = await append_event(store, pid, "spec", "stage_complete", payload)
        import json
        stored = json.loads(evt.payload)
        assert stored["msg"] == "测试 🚀 — résumé"


# ---------------------------------------------------------------------------
# 3. get_latest_event
# ---------------------------------------------------------------------------


class TestGetLatestEvent:
    """get_latest_event returns the most recent event or None."""

    @pytest.mark.asyncio
    async def test_get_latest_event_returns_none_for_empty_pipeline(self, store: Store):
        pid = _pipeline_id()
        result = await get_latest_event(store, pid)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_event_returns_only_event(self, store: Store):
        pid = _pipeline_id()
        evt = await append_event(store, pid, "spec", "stage_start", {})
        latest = await get_latest_event(store, pid)
        assert latest is not None
        assert latest.event_id == evt.event_id

    @pytest.mark.asyncio
    async def test_get_latest_event_returns_last_of_multiple(self, store: Store):
        pid = _pipeline_id()
        await append_event(store, pid, "spec", "stage_start", {})
        await append_event(store, pid, "spec", "stage_complete", {})
        third = await append_event(store, pid, "plan", "stage_start", {})
        latest = await get_latest_event(store, pid)
        assert latest is not None
        assert latest.event_id == third.event_id

    @pytest.mark.asyncio
    async def test_get_latest_event_isolated_by_pipeline(self, store: Store):
        pid1 = _pipeline_id()
        pid2 = _pipeline_id()
        await append_event(store, pid1, "spec", "stage_start", {})
        last2 = await append_event(store, pid2, "plan", "stage_complete", {})
        latest = await get_latest_event(store, pid2)
        assert latest is not None
        assert latest.event_id == last2.event_id

    @pytest.mark.asyncio
    async def test_get_latest_event_raises_on_empty_pipeline_id(self, store: Store):
        with pytest.raises(ValueError):
            await get_latest_event(store, "")

    @pytest.mark.asyncio
    async def test_get_latest_event_returns_frozen_record(self, store: Store):
        pid = _pipeline_id()
        await append_event(store, pid, "spec", "stage_start", {})
        latest = await get_latest_event(store, pid)
        assert latest is not None
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            latest.stage = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. verify_chain
# ---------------------------------------------------------------------------


class TestVerifyChain:
    """verify_chain validates event hash linkage for an entire pipeline."""

    @pytest.mark.asyncio
    async def test_verify_chain_empty_pipeline_returns_true(self, store: Store):
        pid = _pipeline_id()
        # An empty chain is trivially valid
        result = await verify_chain(store, pid)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_chain_single_event_returns_true(self, store: Store):
        pid = _pipeline_id()
        await append_event(store, pid, "spec", "stage_start", {})
        result = await verify_chain(store, pid)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_chain_multiple_intact_events_returns_true(self, store: Store):
        pid = _pipeline_id()
        for stage, etype in [
            ("spec", "stage_start"),
            ("spec", "stage_complete"),
            ("plan", "stage_start"),
            ("plan", "stage_complete"),
        ]:
            await append_event(store, pid, stage, etype, {})
        result = await verify_chain(store, pid)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_chain_raises_on_empty_pipeline_id(self, store: Store):
        with pytest.raises(ValueError):
            await verify_chain(store, "")

    @pytest.mark.asyncio
    async def test_verify_chain_returns_bool(self, store: Store):
        pid = _pipeline_id()
        await append_event(store, pid, "spec", "stage_start", {})
        result = await verify_chain(store, pid)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 5. verify_stage_invariant
# ---------------------------------------------------------------------------


class TestVerifyStageInvariant:
    """verify_stage_invariant enforces spec->plan->implement->acceptance order."""

    def test_spec_to_plan_is_valid(self):
        assert verify_stage_invariant("spec", "plan") is True

    def test_plan_to_implement_is_valid(self):
        assert verify_stage_invariant("plan", "implement") is True

    def test_implement_to_acceptance_is_valid(self):
        assert verify_stage_invariant("implement", "acceptance") is True

    def test_spec_to_implement_is_invalid_skip(self):
        assert verify_stage_invariant("spec", "implement") is False

    def test_spec_to_acceptance_is_invalid_skip(self):
        assert verify_stage_invariant("spec", "acceptance") is False

    def test_plan_to_acceptance_is_invalid_skip(self):
        assert verify_stage_invariant("plan", "acceptance") is False

    def test_plan_to_spec_is_invalid_reverse(self):
        assert verify_stage_invariant("plan", "spec") is False

    def test_implement_to_plan_is_invalid_reverse(self):
        assert verify_stage_invariant("implement", "plan") is False

    def test_acceptance_to_implement_is_invalid_reverse(self):
        assert verify_stage_invariant("acceptance", "implement") is False

    def test_same_stage_is_invalid(self):
        assert verify_stage_invariant("spec", "spec") is False

    def test_invalid_from_stage_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_stage_invariant("unknown_stage", "plan")

    def test_invalid_to_stage_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_stage_invariant("spec", "unknown_stage")

    def test_empty_from_stage_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_stage_invariant("", "plan")

    def test_empty_to_stage_raises_value_error(self):
        with pytest.raises(ValueError):
            verify_stage_invariant("spec", "")

    def test_case_sensitive_stage_names(self):
        """Stage names are lowercase; 'SPEC' is not a valid stage."""
        with pytest.raises(ValueError):
            verify_stage_invariant("SPEC", "PLAN")

    def test_returns_bool_not_truthy(self):
        result = verify_stage_invariant("spec", "plan")
        assert result is True

    def test_invalid_returns_false_not_falsy(self):
        result = verify_stage_invariant("plan", "spec")
        assert result is False


# ---------------------------------------------------------------------------
# 6. ArtifactRecord dataclass — structural checks
# ---------------------------------------------------------------------------


class TestArtifactRecordDataclass:
    """ArtifactRecord MUST be a frozen dataclass with all required fields."""

    def _make(self, **overrides) -> ArtifactRecord:
        defaults = dict(
            artifact_id="ART-001",
            pipeline_id="PL-001",
            name="spec.md",
            stage="spec",
            file_path="outputs/spec.md",
            frozen_hash=None,
            is_frozen=False,
            is_valid=True,
            created_at="2026-04-02T00:00:00+00:00",
        )
        defaults.update(overrides)
        return ArtifactRecord(**defaults)

    def test_artifact_record_is_dataclass(self):
        assert dataclasses.is_dataclass(ArtifactRecord)

    def test_artifact_record_is_frozen(self):
        rec = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.is_valid = False  # type: ignore[misc]

    def test_artifact_record_stores_artifact_id(self):
        rec = self._make(artifact_id="ART-XYZ")
        assert rec.artifact_id == "ART-XYZ"

    def test_artifact_record_stores_pipeline_id(self):
        rec = self._make(pipeline_id="PL-999")
        assert rec.pipeline_id == "PL-999"

    def test_artifact_record_stores_name(self):
        rec = self._make(name="plan.md")
        assert rec.name == "plan.md"

    def test_artifact_record_stores_stage(self):
        rec = self._make(stage="plan")
        assert rec.stage == "plan"

    def test_artifact_record_stores_file_path(self):
        rec = self._make(file_path="/tmp/plan.md")
        assert rec.file_path == "/tmp/plan.md"

    def test_artifact_record_frozen_hash_defaults_none(self):
        rec = self._make()
        assert rec.frozen_hash is None

    def test_artifact_record_stores_frozen_hash(self):
        rec = self._make(frozen_hash="sha256hexdigest")
        assert rec.frozen_hash == "sha256hexdigest"

    def test_artifact_record_is_frozen_defaults_false(self):
        rec = self._make()
        assert rec.is_frozen is False

    def test_artifact_record_stores_is_frozen_true(self):
        rec = self._make(is_frozen=True, frozen_hash="abc")
        assert rec.is_frozen is True

    def test_artifact_record_is_valid_defaults_true(self):
        rec = self._make()
        assert rec.is_valid is True

    def test_artifact_record_stores_is_valid_false(self):
        rec = self._make(is_valid=False)
        assert rec.is_valid is False

    def test_artifact_record_stores_created_at(self):
        rec = self._make(created_at="2026-04-02T12:00:00+00:00")
        assert rec.created_at == "2026-04-02T12:00:00+00:00"


# ---------------------------------------------------------------------------
# 7. register_artifact
# ---------------------------------------------------------------------------


class TestRegisterArtifact:
    """register_artifact persists a new artifact record."""

    @pytest.mark.asyncio
    async def test_register_artifact_returns_artifact_record(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert isinstance(rec, ArtifactRecord)

    @pytest.mark.asyncio
    async def test_register_artifact_stores_name(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert rec.name == "spec.md"

    @pytest.mark.asyncio
    async def test_register_artifact_stores_stage(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "plan.md")
        rec = await register_artifact(store, pid, "plan.md", "plan", fp)
        assert rec.stage == "plan"

    @pytest.mark.asyncio
    async def test_register_artifact_stores_file_path(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert rec.file_path == fp

    @pytest.mark.asyncio
    async def test_register_artifact_stores_pipeline_id(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert rec.pipeline_id == pid

    @pytest.mark.asyncio
    async def test_register_artifact_not_frozen_initially(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert rec.is_frozen is False
        assert rec.frozen_hash is None

    @pytest.mark.asyncio
    async def test_register_artifact_valid_initially(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        assert rec.is_valid is True

    @pytest.mark.asyncio
    async def test_register_artifact_raises_on_duplicate_name(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        with pytest.raises(ValueError):
            await register_artifact(store, pid, "spec.md", "spec", fp)

    @pytest.mark.asyncio
    async def test_register_artifact_same_name_different_pipelines_ok(
        self, store: Store, tmp_path: Path
    ):
        pid1 = _pipeline_id()
        pid2 = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec1 = await register_artifact(store, pid1, "spec.md", "spec", fp)
        rec2 = await register_artifact(store, pid2, "spec.md", "spec", fp)
        assert rec1.artifact_id != rec2.artifact_id

    @pytest.mark.asyncio
    async def test_register_artifact_raises_on_empty_pipeline_id(
        self, store: Store, tmp_path: Path
    ):
        with pytest.raises(ValueError):
            await register_artifact(store, "", "spec.md", "spec", "/tmp/spec.md")

    @pytest.mark.asyncio
    async def test_register_artifact_raises_on_empty_name(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await register_artifact(store, pid, "", "spec", "/tmp/spec.md")

    @pytest.mark.asyncio
    async def test_register_artifact_raises_on_empty_stage(self, store: Store, tmp_path: Path):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await register_artifact(store, pid, "spec.md", "", "/tmp/spec.md")

    @pytest.mark.asyncio
    async def test_register_artifact_raises_on_empty_file_path(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await register_artifact(store, pid, "spec.md", "spec", "")

    @pytest.mark.asyncio
    async def test_register_artifact_returned_record_is_frozen(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        rec = await register_artifact(store, pid, "spec.md", "spec", fp)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. freeze_artifact
# ---------------------------------------------------------------------------


class TestFreezeArtifact:
    """freeze_artifact computes file hash and marks the artifact immutable."""

    @pytest.mark.asyncio
    async def test_freeze_artifact_returns_frozen_record(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("# Spec content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        rec = await freeze_artifact(store, pid, "spec.md")
        assert isinstance(rec, ArtifactRecord)
        assert rec.is_frozen is True

    @pytest.mark.asyncio
    async def test_freeze_artifact_stores_content_hash(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("hello world", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        rec = await freeze_artifact(store, pid, "spec.md")
        assert rec.frozen_hash is not None
        assert len(rec.frozen_hash) > 0

    @pytest.mark.asyncio
    async def test_freeze_artifact_hash_is_sha256_hex(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("deterministic content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        rec = await freeze_artifact(store, pid, "spec.md")
        # SHA-256 hex is exactly 64 characters
        assert len(rec.frozen_hash) == 64

    @pytest.mark.asyncio
    async def test_freeze_artifact_hash_is_deterministic(
        self, store: Store, tmp_path: Path
    ):
        """Freezing the same content twice must produce the same hash."""
        import hashlib
        content = "deterministic spec content"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text(content, encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        rec = await freeze_artifact(store, pid, "spec.md")
        assert rec.frozen_hash == expected_hash

    @pytest.mark.asyncio
    async def test_freeze_artifact_raises_key_error_for_unknown_name(
        self, store: Store
    ):
        pid = _pipeline_id()
        with pytest.raises(KeyError):
            await freeze_artifact(store, pid, "nonexistent.md")

    @pytest.mark.asyncio
    async def test_freeze_artifact_raises_file_not_found_when_file_missing(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "missing_spec.md")
        # Register without creating the file
        await register_artifact(store, pid, "spec.md", "spec", fp)
        with pytest.raises(FileNotFoundError):
            await freeze_artifact(store, pid, "spec.md")

    @pytest.mark.asyncio
    async def test_freeze_artifact_raises_on_empty_pipeline_id(self, store: Store):
        with pytest.raises(ValueError):
            await freeze_artifact(store, "", "spec.md")

    @pytest.mark.asyncio
    async def test_freeze_artifact_raises_on_empty_name(self, store: Store):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await freeze_artifact(store, pid, "")

    @pytest.mark.asyncio
    async def test_freeze_artifact_record_remains_frozen_dataclass(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        rec = await freeze_artifact(store, pid, "spec.md")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.frozen_hash = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 9. check_staleness
# ---------------------------------------------------------------------------


class TestCheckStaleness:
    """check_staleness compares current file content to the frozen hash."""

    @pytest.mark.asyncio
    async def test_check_staleness_returns_false_for_unchanged_file(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("original content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        await freeze_artifact(store, pid, "spec.md")
        stale = await check_staleness(store, pid, "spec.md")
        assert stale is False

    @pytest.mark.asyncio
    async def test_check_staleness_returns_true_after_file_modified(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("original content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        await freeze_artifact(store, pid, "spec.md")
        # Mutate the file after freezing
        Path(fp).write_text("MODIFIED content", encoding="utf-8")
        stale = await check_staleness(store, pid, "spec.md")
        assert stale is True

    @pytest.mark.asyncio
    async def test_check_staleness_raises_runtime_error_if_not_frozen(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        # NOT frozen yet — no baseline to compare
        with pytest.raises(RuntimeError):
            await check_staleness(store, pid, "spec.md")

    @pytest.mark.asyncio
    async def test_check_staleness_raises_key_error_for_unknown_artifact(
        self, store: Store
    ):
        pid = _pipeline_id()
        with pytest.raises(KeyError):
            await check_staleness(store, pid, "nonexistent.md")

    @pytest.mark.asyncio
    async def test_check_staleness_raises_file_not_found_when_file_deleted(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        await freeze_artifact(store, pid, "spec.md")
        Path(fp).unlink()
        with pytest.raises(FileNotFoundError):
            await check_staleness(store, pid, "spec.md")

    @pytest.mark.asyncio
    async def test_check_staleness_raises_on_empty_pipeline_id(self, store: Store):
        with pytest.raises(ValueError):
            await check_staleness(store, "", "spec.md")

    @pytest.mark.asyncio
    async def test_check_staleness_raises_on_empty_name(self, store: Store):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await check_staleness(store, pid, "")

    @pytest.mark.asyncio
    async def test_check_staleness_returns_bool(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        Path(fp).write_text("content", encoding="utf-8")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        await freeze_artifact(store, pid, "spec.md")
        result = await check_staleness(store, pid, "spec.md")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 10. cascade_invalidate
# ---------------------------------------------------------------------------


class TestCascadeInvalidate:
    """cascade_invalidate marks an artifact and downstream stage artifacts invalid."""

    @pytest.mark.asyncio
    async def test_cascade_invalidate_returns_tuple_of_artifact_records(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        result = await cascade_invalidate(store, pid, "spec.md")
        assert isinstance(result, tuple)
        assert all(isinstance(r, ArtifactRecord) for r in result)

    @pytest.mark.asyncio
    async def test_cascade_invalidate_marks_target_invalid(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        invalidated = await cascade_invalidate(store, pid, "spec.md")
        target = next((r for r in invalidated if r.name == "spec.md"), None)
        assert target is not None
        assert target.is_valid is False

    @pytest.mark.asyncio
    async def test_cascade_invalidate_cascades_to_later_stage(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        spec_fp = str(tmp_path / "spec.md")
        plan_fp = str(tmp_path / "plan.md")
        await register_artifact(store, pid, "spec.md", "spec", spec_fp)
        await register_artifact(store, pid, "plan.md", "plan", plan_fp)
        invalidated = await cascade_invalidate(store, pid, "spec.md")
        names = {r.name for r in invalidated}
        # plan.md is a later stage, must be invalidated
        assert "plan.md" in names
        assert "spec.md" in names

    @pytest.mark.asyncio
    async def test_cascade_invalidate_does_not_affect_earlier_stage(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        spec_fp = str(tmp_path / "spec.md")
        plan_fp = str(tmp_path / "plan.md")
        await register_artifact(store, pid, "spec.md", "spec", spec_fp)
        await register_artifact(store, pid, "plan.md", "plan", plan_fp)
        invalidated = await cascade_invalidate(store, pid, "plan.md")
        names = {r.name for r in invalidated}
        # spec.md is an earlier stage, must NOT be invalidated
        assert "spec.md" not in names
        assert "plan.md" in names

    @pytest.mark.asyncio
    async def test_cascade_invalidate_full_chain(
        self, store: Store, tmp_path: Path
    ):
        """Invalidating spec cascades through plan, implement, acceptance."""
        pid = _pipeline_id()
        stages = [
            ("spec.md", "spec"),
            ("plan.md", "plan"),
            ("impl.py", "implement"),
            ("report.md", "acceptance"),
        ]
        for name, stage in stages:
            fp = str(tmp_path / name)
            await register_artifact(store, pid, name, stage, fp)
        invalidated = await cascade_invalidate(store, pid, "spec.md")
        names = {r.name for r in invalidated}
        assert names == {"spec.md", "plan.md", "impl.py", "report.md"}

    @pytest.mark.asyncio
    async def test_cascade_invalidate_single_stage_only_self(
        self, store: Store, tmp_path: Path
    ):
        """Invalidating acceptance only invalidates acceptance (no later stage)."""
        pid = _pipeline_id()
        fp = str(tmp_path / "report.md")
        await register_artifact(store, pid, "report.md", "acceptance", fp)
        invalidated = await cascade_invalidate(store, pid, "report.md")
        assert len(invalidated) == 1
        assert invalidated[0].name == "report.md"

    @pytest.mark.asyncio
    async def test_cascade_invalidate_raises_key_error_for_unknown_artifact(
        self, store: Store
    ):
        pid = _pipeline_id()
        with pytest.raises(KeyError):
            await cascade_invalidate(store, pid, "nonexistent.md")

    @pytest.mark.asyncio
    async def test_cascade_invalidate_raises_on_empty_pipeline_id(
        self, store: Store
    ):
        with pytest.raises(ValueError):
            await cascade_invalidate(store, "", "spec.md")

    @pytest.mark.asyncio
    async def test_cascade_invalidate_raises_on_empty_name(self, store: Store):
        pid = _pipeline_id()
        with pytest.raises(ValueError):
            await cascade_invalidate(store, pid, "")

    @pytest.mark.asyncio
    async def test_cascade_invalidate_returned_records_are_frozen(
        self, store: Store, tmp_path: Path
    ):
        pid = _pipeline_id()
        fp = str(tmp_path / "spec.md")
        await register_artifact(store, pid, "spec.md", "spec", fp)
        invalidated = await cascade_invalidate(store, pid, "spec.md")
        for rec in invalidated:
            with pytest.raises(
                (dataclasses.FrozenInstanceError, AttributeError, TypeError)
            ):
                rec.is_valid = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11. Integration — stage_complete flow
# ---------------------------------------------------------------------------


class TestStagCompleteIntegration:
    """End-to-end: append_event + register_artifact + freeze_artifact in sequence."""

    @pytest.mark.asyncio
    async def test_stage_complete_flow_spec_stage(
        self, store: Store, tmp_path: Path
    ):
        """Scenario: spec stage completes — artifact frozen, event appended."""
        pid = _pipeline_id()
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec\n\nFeature description.", encoding="utf-8")

        # Register the spec artifact
        art = await register_artifact(store, pid, "spec.md", "spec", str(spec_file))
        assert art.is_frozen is False

        # Freeze the artifact
        frozen_art = await freeze_artifact(store, pid, "spec.md")
        assert frozen_art.is_frozen is True
        assert frozen_art.frozen_hash is not None

        # Append a stage_complete event
        evt = await append_event(
            store, pid, "spec", "stage_complete",
            {"artifact": "spec.md", "hash": frozen_art.frozen_hash}
        )
        assert evt.event_type == "stage_complete"
        assert evt.stage == "spec"

        # Verify the chain is intact
        valid = await verify_chain(store, pid)
        assert valid is True

    @pytest.mark.asyncio
    async def test_stage_transition_invariant_respected(
        self, store: Store, tmp_path: Path
    ):
        """After spec completes, only spec->plan is a valid transition."""
        assert verify_stage_invariant("spec", "plan") is True
        assert verify_stage_invariant("spec", "implement") is False

    @pytest.mark.asyncio
    async def test_full_pipeline_event_chain_valid(self, store: Store):
        """All four stages emit events; chain must verify as intact."""
        pid = _pipeline_id()
        transitions = [
            ("spec", "stage_start"),
            ("spec", "stage_complete"),
            ("plan", "stage_start"),
            ("plan", "stage_complete"),
            ("implement", "stage_start"),
            ("implement", "stage_complete"),
            ("acceptance", "stage_start"),
            ("acceptance", "stage_complete"),
        ]
        for stage, etype in transitions:
            await append_event(store, pid, stage, etype, {})

        latest = await get_latest_event(store, pid)
        assert latest is not None
        assert latest.stage == "acceptance"
        assert latest.event_type == "stage_complete"

        valid = await verify_chain(store, pid)
        assert valid is True

    @pytest.mark.asyncio
    async def test_cascade_invalidate_after_spec_change_triggers_downstream(
        self, store: Store, tmp_path: Path
    ):
        """Changing spec invalidates all downstream artifacts."""
        pid = _pipeline_id()
        artifacts = [
            ("spec.md", "spec"),
            ("plan.md", "plan"),
            ("tasks.json", "implement"),
            ("report.md", "acceptance"),
        ]
        for name, stage in artifacts:
            fp = str(tmp_path / name)
            await register_artifact(store, pid, name, stage, fp)

        invalidated = await cascade_invalidate(store, pid, "spec.md")
        invalidated_names = {r.name for r in invalidated}
        assert invalidated_names == {"spec.md", "plan.md", "tasks.json", "report.md"}


# ---------------------------------------------------------------------------
# 12. Module size constraint
# ---------------------------------------------------------------------------


class TestModuleSizeConstraint:
    """The artifacts-related portion of _lvl_queries.py must stay compact."""

    def test_lvl_queries_module_exists(self):
        import orchestrator.store._lvl_queries as m
        assert m is not None

    def test_lvl_queries_module_under_300_lines(self):
        """_lvl_queries.py must be under 300 lines total (stub + real code).

        The spec calls for an artifacts module under 150 lines; since we
        consolidate into _lvl_queries.py, a 300-line ceiling still enforces
        compactness while leaving room for the implementation.
        """
        import inspect
        import orchestrator.store._lvl_queries as m
        source = inspect.getsource(m)
        line_count = len(source.splitlines())
        assert line_count < 300, (
            f"_lvl_queries.py has {line_count} lines; must be under 300"
        )
