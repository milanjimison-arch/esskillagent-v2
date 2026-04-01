"""RED-phase unit tests for orchestrator/store/queries.py — CRUD query helpers.

FR-036: Store MUST use INSERT OR REPLACE (upsert) semantics for task records so
        that mutable fields (file_path, status, group_name) stay current.
FR-037: Store MUST maintain an evidence chain audit trail (insert + list).
FR-LVL: LVL audit logs MUST support append and filtered retrieval.

These are RED-phase tests. All functions in queries.py raise NotImplementedError,
so every test that calls a query helper will fail with NotImplementedError
propagated as an unexpected exception — the intended RED state.

Additionally the frozen dataclass assertions (immutability, field values) will
fail once real objects are returned, confirming behavior under GREEN.

Test coverage areas:
    1. Frozen return types — TaskRecord, EvidenceRecord, LvlLogRecord
       a. All are frozen dataclasses (FrozenInstanceError on mutation)
       b. All required fields are stored correctly
       c. Optional fields default to None / empty tuple
    2. upsert_task_record — INSERT OR REPLACE semantics
       a. New task is persisted and returned as TaskRecord
       b. Re-upsert with new status overwrites mutable fields
       c. requirements stored as tuple (immutable)
       d. Raises ValueError on empty task_id
       e. Raises ValueError on empty description
    3. get_task_record — single-row fetch
       a. Returns correct TaskRecord after upsert
       b. Returns None for missing task_id
       c. Raises ValueError on empty task_id
    4. list_task_records — all rows
       a. Returns empty tuple when no tasks exist
       b. Returns all upserted tasks as frozen tuple
       c. Return type is tuple (not list)
    5. update_task_status_record — status-only update
       a. Persists new status and returns updated TaskRecord
       b. Raises KeyError for non-existent task_id
       c. Raises ValueError on empty task_id
       d. Raises ValueError on empty status
    6. insert_evidence_record — evidence chain
       a. Persists evidence and returns EvidenceRecord
       b. Returns correct field values
       c. Optional task_id may be None
       d. Multiple inserts for same pipeline accumulate
       e. Raises ValueError on empty evidence_id
       f. Raises ValueError on empty pipeline_id
    7. list_evidence_records — all evidence for a pipeline
       a. Returns empty tuple when no evidence
       b. Returns all evidence as frozen tuple
       c. Only returns evidence for the specified pipeline
    8. list_evidence_records_for_stage — filtered by stage
       a. Returns only evidence matching the stage
       b. Returns empty tuple when no matching evidence
       c. Raises ValueError on empty stage
    9. insert_lvl_log — LVL audit log append
       a. Persists log entry and returns LvlLogRecord
       b. Auto-incremented id is a positive integer
       c. Optional detail defaults to None
       d. Raises ValueError on empty pipeline_id
       e. Raises ValueError on empty level
       f. Raises ValueError on empty message
   10. list_lvl_logs — all logs for a pipeline ordered by id
       a. Returns empty tuple when no logs
       b. Returns all logs in ascending id order
       c. Only returns logs for the specified pipeline
   11. list_lvl_logs_by_level — filtered by level
       a. Returns only entries matching the level
       b. Returns empty tuple when no matching entries
       c. Case-sensitive level matching
   12. Immutability — all returned objects resist mutation
   13. Edge cases — special characters, Unicode, empty requirements
"""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from orchestrator.store.db import Store
from orchestrator.store.queries import (
    EvidenceRecord,
    LvlLogRecord,
    TaskRecord,
    get_task_record,
    insert_evidence_record,
    insert_lvl_log,
    list_evidence_records,
    list_evidence_records_for_stage,
    list_lvl_logs,
    list_lvl_logs_by_level,
    list_task_records,
    update_task_status_record,
    upsert_task_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
async def store(tmp_path: Path) -> Store:
    """Open a fresh in-memory-style temp SQLite store for each test."""
    db_path = str(tmp_path / f"test_{_uid()}.db")
    s = Store(db_path)
    await s.initialize()
    yield s
    await s.close()


def _task_kwargs(**overrides) -> dict:
    """Return default kwargs for upsert_task_record, merged with overrides."""
    defaults = dict(
        task_id=f"T-{_uid()}",
        description="Write failing tests",
        file_path="src/module.py",
        parallel=False,
        user_story="As a developer I want tests",
        requirements=["req-001", "req-002"],
        status="pending",
        group_name="group-A",
    )
    defaults.update(overrides)
    return defaults


def _evidence_kwargs(**overrides) -> dict:
    """Return default kwargs for insert_evidence_record."""
    defaults = dict(
        evidence_id=f"EV-{_uid()}",
        pipeline_id=f"PL-{_uid()}",
        stage="spec",
        task_id=None,
        event_type="test_output",
        detail="All tests passed.",
    )
    defaults.update(overrides)
    return defaults


def _lvl_kwargs(**overrides) -> dict:
    """Return default kwargs for insert_lvl_log."""
    defaults = dict(
        pipeline_id=f"PL-{_uid()}",
        level="INFO",
        message="Stage started",
        detail=None,
    )
    defaults.update(overrides)
    return defaults


# ===========================================================================
# 1. Frozen return types — unit-level checks on the dataclasses themselves
# ===========================================================================


class TestTaskRecordDataclass:
    """TaskRecord MUST be a frozen dataclass with all required fields."""

    def _make(self, **overrides) -> TaskRecord:
        defaults = dict(
            task_id="T001",
            description="do something",
            file_path="src/foo.py",
            parallel=False,
            status="pending",
            group_name="grp",
            created_at="2026-04-01T00:00:00+00:00",
            updated_at="2026-04-01T00:00:00+00:00",
        )
        defaults.update(overrides)
        return TaskRecord(**defaults)

    def test_FR036_task_record_is_dataclass(self):
        assert dataclasses.is_dataclass(TaskRecord)

    def test_FR036_task_record_is_frozen(self):
        """FR-036: TaskRecord MUST be frozen — mutation raises."""
        rec = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.status = "passed"  # type: ignore[misc]

    def test_FR036_task_record_task_id_frozen(self):
        rec = self._make(task_id="T-orig")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.task_id = "T-mutated"  # type: ignore[misc]

    def test_FR036_task_record_stores_task_id(self):
        rec = self._make(task_id="T-XYZ")
        assert rec.task_id == "T-XYZ"

    def test_FR036_task_record_stores_description(self):
        rec = self._make(description="Implement login")
        assert rec.description == "Implement login"

    def test_FR036_task_record_stores_file_path(self):
        rec = self._make(file_path="src/auth/login.py")
        assert rec.file_path == "src/auth/login.py"

    def test_FR036_task_record_stores_parallel_flag(self):
        rec = self._make(parallel=True)
        assert rec.parallel is True

    def test_FR036_task_record_parallel_defaults_false(self):
        rec = self._make()
        assert rec.parallel is False

    def test_FR036_task_record_stores_status(self):
        rec = self._make(status="running")
        assert rec.status == "running"

    def test_FR036_task_record_stores_group_name(self):
        rec = self._make(group_name="auth-group")
        assert rec.group_name == "auth-group"

    def test_FR036_task_record_user_story_defaults_none(self):
        rec = self._make()
        assert rec.user_story is None

    def test_FR036_task_record_stores_user_story(self):
        rec = self._make(user_story="As a user I want to log in")
        assert rec.user_story == "As a user I want to log in"

    def test_FR036_task_record_requirements_defaults_empty_tuple(self):
        rec = self._make()
        assert rec.requirements == ()

    def test_FR036_task_record_stores_requirements_as_tuple(self):
        rec = TaskRecord(
            task_id="T1",
            description="d",
            file_path="f.py",
            parallel=False,
            status="pending",
            group_name="g",
            created_at="ts",
            updated_at="ts",
            requirements=("req-001", "req-002"),
        )
        assert isinstance(rec.requirements, tuple)
        assert "req-001" in rec.requirements

    def test_FR036_task_record_stores_created_at(self):
        rec = self._make(created_at="2026-04-01T12:00:00+00:00")
        assert rec.created_at == "2026-04-01T12:00:00+00:00"

    def test_FR036_task_record_stores_updated_at(self):
        rec = self._make(updated_at="2026-04-02T00:00:00+00:00")
        assert rec.updated_at == "2026-04-02T00:00:00+00:00"


class TestEvidenceRecordDataclass:
    """EvidenceRecord MUST be a frozen dataclass with all required fields."""

    def _make(self, **overrides) -> EvidenceRecord:
        defaults = dict(
            evidence_id="EV001",
            pipeline_id="PL001",
            stage="spec",
            event_type="test_output",
            detail="10 passed",
            created_at="2026-04-01T00:00:00+00:00",
        )
        defaults.update(overrides)
        return EvidenceRecord(**defaults)

    def test_FR037_evidence_record_is_dataclass(self):
        assert dataclasses.is_dataclass(EvidenceRecord)

    def test_FR037_evidence_record_is_frozen(self):
        """FR-037: EvidenceRecord MUST be frozen."""
        rec = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.detail = "mutated"  # type: ignore[misc]

    def test_FR037_evidence_record_stores_evidence_id(self):
        rec = self._make(evidence_id="EV-ALPHA")
        assert rec.evidence_id == "EV-ALPHA"

    def test_FR037_evidence_record_stores_pipeline_id(self):
        rec = self._make(pipeline_id="PL-99")
        assert rec.pipeline_id == "PL-99"

    def test_FR037_evidence_record_stores_stage(self):
        rec = self._make(stage="implement")
        assert rec.stage == "implement"

    def test_FR037_evidence_record_stores_event_type(self):
        rec = self._make(event_type="lint_result")
        assert rec.event_type == "lint_result"

    def test_FR037_evidence_record_stores_detail(self):
        rec = self._make(detail="No errors found.")
        assert rec.detail == "No errors found."

    def test_FR037_evidence_record_task_id_defaults_none(self):
        rec = self._make()
        assert rec.task_id is None

    def test_FR037_evidence_record_stores_task_id(self):
        rec = self._make(task_id="T-42")
        assert rec.task_id == "T-42"

    def test_FR037_evidence_record_stores_created_at(self):
        rec = self._make(created_at="2026-04-01T10:00:00+00:00")
        assert rec.created_at == "2026-04-01T10:00:00+00:00"


class TestLvlLogRecordDataclass:
    """LvlLogRecord MUST be a frozen dataclass with all required fields."""

    def _make(self, **overrides) -> LvlLogRecord:
        defaults = dict(
            id=1,
            pipeline_id="PL001",
            level="INFO",
            message="Stage started",
            created_at="2026-04-01T00:00:00+00:00",
        )
        defaults.update(overrides)
        return LvlLogRecord(**defaults)

    def test_lvl_log_record_is_dataclass(self):
        assert dataclasses.is_dataclass(LvlLogRecord)

    def test_lvl_log_record_is_frozen(self):
        """LvlLogRecord MUST be frozen."""
        rec = self._make()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            rec.message = "mutated"  # type: ignore[misc]

    def test_lvl_log_record_stores_id(self):
        rec = self._make(id=42)
        assert rec.id == 42

    def test_lvl_log_record_stores_pipeline_id(self):
        rec = self._make(pipeline_id="PL-XYZ")
        assert rec.pipeline_id == "PL-XYZ"

    def test_lvl_log_record_stores_level(self):
        rec = self._make(level="ERROR")
        assert rec.level == "ERROR"

    def test_lvl_log_record_stores_message(self):
        rec = self._make(message="Stage completed")
        assert rec.message == "Stage completed"

    def test_lvl_log_record_detail_defaults_none(self):
        rec = self._make()
        assert rec.detail is None

    def test_lvl_log_record_stores_detail(self):
        rec = self._make(detail="Detailed explanation here")
        assert rec.detail == "Detailed explanation here"

    def test_lvl_log_record_stores_created_at(self):
        rec = self._make(created_at="2026-04-01T09:00:00+00:00")
        assert rec.created_at == "2026-04-01T09:00:00+00:00"


# ===========================================================================
# 2. upsert_task_record — INSERT OR REPLACE semantics
# ===========================================================================


class TestUpsertTaskRecord:
    """FR-036: upsert_task_record MUST persist tasks with upsert semantics
    and return a frozen TaskRecord."""

    async def test_FR036_upsert_returns_task_record_instance(self, store: Store):
        """upsert_task_record MUST return a TaskRecord."""
        kw = _task_kwargs()
        result = await upsert_task_record(store, **kw)
        assert isinstance(result, TaskRecord)

    async def test_FR036_upsert_returned_record_is_frozen(self, store: Store):
        """Returned TaskRecord MUST be frozen (immutable)."""
        result = await upsert_task_record(store, **_task_kwargs())
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.status = "mutated"  # type: ignore[misc]

    async def test_FR036_upsert_stores_task_id(self, store: Store):
        """task_id field MUST match what was provided."""
        kw = _task_kwargs(task_id="T-FIXED")
        result = await upsert_task_record(store, **kw)
        assert result.task_id == "T-FIXED"

    async def test_FR036_upsert_stores_description(self, store: Store):
        """description field MUST be persisted correctly."""
        kw = _task_kwargs(description="Implement OAuth2 login")
        result = await upsert_task_record(store, **kw)
        assert result.description == "Implement OAuth2 login"

    async def test_FR036_upsert_stores_file_path(self, store: Store):
        """file_path field MUST be persisted correctly."""
        kw = _task_kwargs(file_path="src/auth/oauth.py")
        result = await upsert_task_record(store, **kw)
        assert result.file_path == "src/auth/oauth.py"

    async def test_FR036_upsert_stores_parallel_true(self, store: Store):
        """parallel=True MUST be persisted correctly."""
        kw = _task_kwargs(parallel=True)
        result = await upsert_task_record(store, **kw)
        assert result.parallel is True

    async def test_FR036_upsert_stores_parallel_false(self, store: Store):
        """parallel=False MUST be persisted correctly."""
        kw = _task_kwargs(parallel=False)
        result = await upsert_task_record(store, **kw)
        assert result.parallel is False

    async def test_FR036_upsert_stores_status(self, store: Store):
        """status field MUST be persisted correctly."""
        kw = _task_kwargs(status="running")
        result = await upsert_task_record(store, **kw)
        assert result.status == "running"

    async def test_FR036_upsert_stores_group_name(self, store: Store):
        """group_name field MUST be persisted correctly."""
        kw = _task_kwargs(group_name="auth-tasks")
        result = await upsert_task_record(store, **kw)
        assert result.group_name == "auth-tasks"

    async def test_FR036_upsert_stores_user_story(self, store: Store):
        """user_story MUST be persisted when provided."""
        kw = _task_kwargs(user_story="As an admin I want access control")
        result = await upsert_task_record(store, **kw)
        assert result.user_story == "As an admin I want access control"

    async def test_FR036_upsert_null_user_story_stored_as_none(self, store: Store):
        """user_story=None MUST be stored as None."""
        kw = _task_kwargs(user_story=None)
        result = await upsert_task_record(store, **kw)
        assert result.user_story is None

    async def test_FR036_upsert_requirements_returned_as_tuple(self, store: Store):
        """requirements MUST be returned as an immutable tuple."""
        kw = _task_kwargs(requirements=["r1", "r2", "r3"])
        result = await upsert_task_record(store, **kw)
        assert isinstance(result.requirements, tuple)

    async def test_FR036_upsert_requirements_content_preserved(self, store: Store):
        """requirements items MUST be preserved after persistence."""
        kw = _task_kwargs(requirements=["req-A", "req-B"])
        result = await upsert_task_record(store, **kw)
        assert "req-A" in result.requirements
        assert "req-B" in result.requirements

    async def test_FR036_upsert_empty_requirements_stored(self, store: Store):
        """requirements=[] MUST be stored as an empty tuple."""
        kw = _task_kwargs(requirements=[])
        result = await upsert_task_record(store, **kw)
        assert result.requirements == ()

    async def test_FR036_upsert_second_call_overwrites_status(self, store: Store):
        """FR-036: Re-upserting with a new status MUST overwrite the previous status."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="pending"))
        result2 = await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="passed"))
        assert result2.status == "passed"

    async def test_FR036_upsert_second_call_overwrites_file_path(self, store: Store):
        """FR-036: Re-upserting with a new file_path MUST overwrite previous value."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, file_path="old/path.py"))
        result2 = await upsert_task_record(store, **_task_kwargs(task_id=task_id, file_path="new/path.py"))
        assert result2.file_path == "new/path.py"

    async def test_FR036_upsert_second_call_overwrites_group_name(self, store: Store):
        """FR-036: Re-upserting with a new group_name MUST overwrite previous value."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, group_name="old-group"))
        result2 = await upsert_task_record(store, **_task_kwargs(task_id=task_id, group_name="new-group"))
        assert result2.group_name == "new-group"

    async def test_FR036_upsert_raises_value_error_on_empty_task_id(self, store: Store):
        """upsert_task_record MUST raise ValueError when task_id is empty."""
        kw = _task_kwargs(task_id="")
        with pytest.raises(ValueError):
            await upsert_task_record(store, **kw)

    async def test_FR036_upsert_raises_value_error_on_empty_description(self, store: Store):
        """upsert_task_record MUST raise ValueError when description is empty."""
        kw = _task_kwargs(description="")
        with pytest.raises(ValueError):
            await upsert_task_record(store, **kw)

    async def test_FR036_upsert_created_at_is_non_empty_string(self, store: Store):
        """created_at in returned record MUST be a non-empty ISO string."""
        result = await upsert_task_record(store, **_task_kwargs())
        assert isinstance(result.created_at, str)
        assert len(result.created_at) > 0

    async def test_FR036_upsert_updated_at_is_non_empty_string(self, store: Store):
        """updated_at in returned record MUST be a non-empty ISO string."""
        result = await upsert_task_record(store, **_task_kwargs())
        assert isinstance(result.updated_at, str)
        assert len(result.updated_at) > 0


# ===========================================================================
# 3. get_task_record — single-row fetch
# ===========================================================================


class TestGetTaskRecord:
    """get_task_record MUST fetch a persisted task and return a frozen TaskRecord."""

    async def test_get_returns_task_record_after_upsert(self, store: Store):
        """A task persisted by upsert MUST be retrievable by get."""
        kw = _task_kwargs(task_id="T-GET-01")
        await upsert_task_record(store, **kw)
        result = await get_task_record(store, "T-GET-01")
        assert isinstance(result, TaskRecord)
        assert result.task_id == "T-GET-01"

    async def test_get_returns_correct_description(self, store: Store):
        """get_task_record MUST return the persisted description."""
        kw = _task_kwargs(task_id="T-GET-02", description="Build API endpoint")
        await upsert_task_record(store, **kw)
        result = await get_task_record(store, "T-GET-02")
        assert result.description == "Build API endpoint"

    async def test_get_returns_correct_status(self, store: Store):
        """get_task_record MUST reflect the current status."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="failed"))
        result = await get_task_record(store, task_id)
        assert result.status == "failed"

    async def test_get_returns_requirements_as_tuple(self, store: Store):
        """get_task_record MUST return requirements as a tuple."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, requirements=["r1"]))
        result = await get_task_record(store, task_id)
        assert isinstance(result.requirements, tuple)

    async def test_get_returns_none_for_missing_task(self, store: Store):
        """get_task_record MUST return None when task_id does not exist."""
        result = await get_task_record(store, "NONEXISTENT-TASK-ID")
        assert result is None

    async def test_get_returns_none_for_unknown_id(self, store: Store):
        """Ensure None is returned even after other tasks have been inserted."""
        await upsert_task_record(store, **_task_kwargs(task_id="T-OTHER"))
        result = await get_task_record(store, "T-DOES-NOT-EXIST")
        assert result is None

    async def test_get_returned_record_is_frozen(self, store: Store):
        """Returned TaskRecord from get MUST be frozen."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        result = await get_task_record(store, task_id)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.status = "mutated"  # type: ignore[misc]

    async def test_get_raises_value_error_on_empty_task_id(self, store: Store):
        """get_task_record MUST raise ValueError when task_id is empty."""
        with pytest.raises(ValueError):
            await get_task_record(store, "")


# ===========================================================================
# 4. list_task_records — all rows
# ===========================================================================


class TestListTaskRecords:
    """list_task_records MUST return a frozen tuple of all TaskRecords."""

    async def test_list_returns_empty_tuple_when_no_tasks(self, store: Store):
        """list_task_records MUST return an empty tuple when no tasks exist."""
        result = await list_task_records(store)
        assert result == ()

    async def test_list_returns_tuple_not_list(self, store: Store):
        """list_task_records MUST return a tuple, not a list."""
        result = await list_task_records(store)
        assert isinstance(result, tuple)

    async def test_list_returns_one_task(self, store: Store):
        """list_task_records MUST return the single upserted task."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        result = await list_task_records(store)
        assert len(result) == 1
        assert result[0].task_id == task_id

    async def test_list_returns_multiple_tasks(self, store: Store):
        """list_task_records MUST return all upserted tasks."""
        ids = [f"T-{_uid()}" for _ in range(3)]
        for tid in ids:
            await upsert_task_record(store, **_task_kwargs(task_id=tid))
        result = await list_task_records(store)
        returned_ids = {r.task_id for r in result}
        for tid in ids:
            assert tid in returned_ids

    async def test_list_returns_task_records_type(self, store: Store):
        """Each element in the returned tuple MUST be a TaskRecord."""
        await upsert_task_record(store, **_task_kwargs())
        result = await list_task_records(store)
        for rec in result:
            assert isinstance(rec, TaskRecord)

    async def test_list_upsert_does_not_duplicate(self, store: Store):
        """Re-upserting the same task_id MUST NOT create a duplicate row."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="passed"))
        result = await list_task_records(store)
        matching = [r for r in result if r.task_id == task_id]
        assert len(matching) == 1

    async def test_list_tuple_elements_are_frozen(self, store: Store):
        """Each element in the returned tuple MUST be frozen."""
        await upsert_task_record(store, **_task_kwargs())
        result = await list_task_records(store)
        for rec in result:
            with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                rec.status = "mutated"  # type: ignore[misc]


# ===========================================================================
# 5. update_task_status_record
# ===========================================================================


class TestUpdateTaskStatusRecord:
    """update_task_status_record MUST update status and return a frozen TaskRecord."""

    async def test_update_returns_task_record(self, store: Store):
        """update_task_status_record MUST return a TaskRecord."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="pending"))
        result = await update_task_status_record(store, task_id, "passed")
        assert isinstance(result, TaskRecord)

    async def test_update_status_is_reflected(self, store: Store):
        """The returned record's status MUST equal the new status."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="pending"))
        result = await update_task_status_record(store, task_id, "passed")
        assert result.status == "passed"

    async def test_update_status_persisted_on_subsequent_get(self, store: Store):
        """After update, get_task_record MUST return the updated status."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id, status="pending"))
        await update_task_status_record(store, task_id, "failed")
        fetched = await get_task_record(store, task_id)
        assert fetched.status == "failed"

    async def test_update_task_id_unchanged(self, store: Store):
        """update_task_status_record MUST NOT change task_id."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        result = await update_task_status_record(store, task_id, "skipped")
        assert result.task_id == task_id

    async def test_update_returned_record_is_frozen(self, store: Store):
        """Returned TaskRecord MUST be frozen."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        result = await update_task_status_record(store, task_id, "running")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.status = "mutated"  # type: ignore[misc]

    async def test_update_raises_key_error_for_nonexistent_task(self, store: Store):
        """update_task_status_record MUST raise KeyError when task_id is absent."""
        with pytest.raises(KeyError):
            await update_task_status_record(store, "NONEXISTENT-9999", "passed")

    async def test_update_raises_value_error_on_empty_task_id(self, store: Store):
        """update_task_status_record MUST raise ValueError when task_id is empty."""
        with pytest.raises(ValueError):
            await update_task_status_record(store, "", "passed")

    async def test_update_raises_value_error_on_empty_status(self, store: Store):
        """update_task_status_record MUST raise ValueError when status is empty."""
        task_id = f"T-{_uid()}"
        await upsert_task_record(store, **_task_kwargs(task_id=task_id))
        with pytest.raises(ValueError):
            await update_task_status_record(store, task_id, "")


# ===========================================================================
# 6. insert_evidence_record
# ===========================================================================


class TestInsertEvidenceRecord:
    """FR-037: insert_evidence_record MUST persist evidence and return a
    frozen EvidenceRecord."""

    async def test_FR037_insert_returns_evidence_record(self, store: Store):
        """insert_evidence_record MUST return an EvidenceRecord."""
        kw = _evidence_kwargs()
        result = await insert_evidence_record(store, **kw)
        assert isinstance(result, EvidenceRecord)

    async def test_FR037_insert_returned_record_is_frozen(self, store: Store):
        """Returned EvidenceRecord MUST be frozen."""
        result = await insert_evidence_record(store, **_evidence_kwargs())
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.detail = "mutated"  # type: ignore[misc]

    async def test_FR037_insert_stores_evidence_id(self, store: Store):
        """evidence_id MUST be preserved in the returned record."""
        ev_id = f"EV-{_uid()}"
        result = await insert_evidence_record(store, **_evidence_kwargs(evidence_id=ev_id))
        assert result.evidence_id == ev_id

    async def test_FR037_insert_stores_pipeline_id(self, store: Store):
        """pipeline_id MUST be preserved in the returned record."""
        pl_id = f"PL-{_uid()}"
        result = await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id))
        assert result.pipeline_id == pl_id

    async def test_FR037_insert_stores_stage(self, store: Store):
        """stage MUST be preserved in the returned record."""
        result = await insert_evidence_record(store, **_evidence_kwargs(stage="acceptance"))
        assert result.stage == "acceptance"

    async def test_FR037_insert_stores_event_type(self, store: Store):
        """event_type MUST be preserved in the returned record."""
        result = await insert_evidence_record(store, **_evidence_kwargs(event_type="lint_result"))
        assert result.event_type == "lint_result"

    async def test_FR037_insert_stores_detail(self, store: Store):
        """detail MUST be preserved in the returned record."""
        result = await insert_evidence_record(store, **_evidence_kwargs(detail="ruff: 0 errors"))
        assert result.detail == "ruff: 0 errors"

    async def test_FR037_insert_task_id_none_stored(self, store: Store):
        """task_id=None MUST be stored as None."""
        result = await insert_evidence_record(store, **_evidence_kwargs(task_id=None))
        assert result.task_id is None

    async def test_FR037_insert_task_id_stored_when_provided(self, store: Store):
        """task_id MUST be preserved when provided."""
        result = await insert_evidence_record(store, **_evidence_kwargs(task_id="T-99"))
        assert result.task_id == "T-99"

    async def test_FR037_insert_created_at_non_empty(self, store: Store):
        """created_at MUST be a non-empty ISO string."""
        result = await insert_evidence_record(store, **_evidence_kwargs())
        assert isinstance(result.created_at, str)
        assert len(result.created_at) > 0

    async def test_FR037_insert_multiple_evidence_same_pipeline(self, store: Store):
        """Multiple inserts for the same pipeline MUST all persist (no replace)."""
        pl_id = f"PL-{_uid()}"
        for i in range(3):
            await insert_evidence_record(
                store,
                **_evidence_kwargs(evidence_id=f"EV-{i}-{_uid()}", pipeline_id=pl_id)
            )
        records = await list_evidence_records(store, pl_id)
        assert len(records) == 3

    async def test_FR037_insert_raises_value_error_on_empty_evidence_id(self, store: Store):
        """insert_evidence_record MUST raise ValueError when evidence_id is empty."""
        kw = _evidence_kwargs(evidence_id="")
        with pytest.raises(ValueError):
            await insert_evidence_record(store, **kw)

    async def test_FR037_insert_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """insert_evidence_record MUST raise ValueError when pipeline_id is empty."""
        kw = _evidence_kwargs(pipeline_id="")
        with pytest.raises(ValueError):
            await insert_evidence_record(store, **kw)

    async def test_FR037_insert_raises_value_error_on_empty_event_type(self, store: Store):
        """insert_evidence_record MUST raise ValueError when event_type is empty."""
        kw = _evidence_kwargs(event_type="")
        with pytest.raises(ValueError):
            await insert_evidence_record(store, **kw)


# ===========================================================================
# 7. list_evidence_records — all evidence for a pipeline
# ===========================================================================


class TestListEvidenceRecords:
    """FR-037: list_evidence_records MUST return a frozen tuple of EvidenceRecords."""

    async def test_FR037_list_returns_empty_tuple_when_none(self, store: Store):
        """list_evidence_records MUST return an empty tuple when no evidence."""
        result = await list_evidence_records(store, "PL-EMPTY")
        assert result == ()

    async def test_FR037_list_return_type_is_tuple(self, store: Store):
        """list_evidence_records MUST return a tuple, not a list."""
        result = await list_evidence_records(store, "PL-EMPTY")
        assert isinstance(result, tuple)

    async def test_FR037_list_returns_inserted_evidence(self, store: Store):
        """list_evidence_records MUST include evidence inserted for the pipeline."""
        pl_id = f"PL-{_uid()}"
        ev_id = f"EV-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(evidence_id=ev_id, pipeline_id=pl_id))
        result = await list_evidence_records(store, pl_id)
        assert len(result) == 1
        assert result[0].evidence_id == ev_id

    async def test_FR037_list_returns_evidence_record_types(self, store: Store):
        """Each element MUST be an EvidenceRecord."""
        pl_id = f"PL-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id))
        result = await list_evidence_records(store, pl_id)
        for rec in result:
            assert isinstance(rec, EvidenceRecord)

    async def test_FR037_list_only_returns_matching_pipeline(self, store: Store):
        """list_evidence_records MUST NOT return evidence from other pipelines."""
        pl_a = f"PL-A-{_uid()}"
        pl_b = f"PL-B-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_a))
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_b))
        result_a = await list_evidence_records(store, pl_a)
        assert all(r.pipeline_id == pl_a for r in result_a)

    async def test_FR037_list_tuple_elements_are_frozen(self, store: Store):
        """Each EvidenceRecord in the tuple MUST be frozen."""
        pl_id = f"PL-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id))
        result = await list_evidence_records(store, pl_id)
        for rec in result:
            with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                rec.detail = "mutated"  # type: ignore[misc]

    async def test_FR037_list_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """list_evidence_records MUST raise ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError):
            await list_evidence_records(store, "")


# ===========================================================================
# 8. list_evidence_records_for_stage
# ===========================================================================


class TestListEvidenceRecordsForStage:
    """list_evidence_records_for_stage MUST filter by both pipeline_id and stage."""

    async def test_stage_filter_returns_matching_records(self, store: Store):
        """Only evidence with the matching stage MUST be returned."""
        pl_id = f"PL-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id, stage="spec"))
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id, stage="plan"))
        result = await list_evidence_records_for_stage(store, pl_id, "spec")
        assert all(r.stage == "spec" for r in result)

    async def test_stage_filter_count_correct(self, store: Store):
        """Only evidence rows for the requested stage MUST be counted."""
        pl_id = f"PL-{_uid()}"
        for _ in range(2):
            await insert_evidence_record(
                store, **_evidence_kwargs(evidence_id=f"EV-{_uid()}", pipeline_id=pl_id, stage="spec")
            )
        await insert_evidence_record(
            store, **_evidence_kwargs(evidence_id=f"EV-{_uid()}", pipeline_id=pl_id, stage="plan")
        )
        result = await list_evidence_records_for_stage(store, pl_id, "spec")
        assert len(result) == 2

    async def test_stage_filter_returns_empty_when_no_match(self, store: Store):
        """Returns empty tuple when no evidence matches the stage."""
        pl_id = f"PL-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id, stage="spec"))
        result = await list_evidence_records_for_stage(store, pl_id, "acceptance")
        assert result == ()

    async def test_stage_filter_return_type_is_tuple(self, store: Store):
        """Return type MUST be a tuple."""
        pl_id = f"PL-{_uid()}"
        result = await list_evidence_records_for_stage(store, pl_id, "spec")
        assert isinstance(result, tuple)

    async def test_stage_filter_records_are_frozen(self, store: Store):
        """Returned EvidenceRecords MUST be frozen."""
        pl_id = f"PL-{_uid()}"
        await insert_evidence_record(store, **_evidence_kwargs(pipeline_id=pl_id, stage="implement"))
        result = await list_evidence_records_for_stage(store, pl_id, "implement")
        for rec in result:
            with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                rec.stage = "mutated"  # type: ignore[misc]

    async def test_stage_filter_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """Raises ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError):
            await list_evidence_records_for_stage(store, "", "spec")

    async def test_stage_filter_raises_value_error_on_empty_stage(self, store: Store):
        """Raises ValueError when stage is empty."""
        with pytest.raises(ValueError):
            await list_evidence_records_for_stage(store, "PL-X", "")


# ===========================================================================
# 9. insert_lvl_log
# ===========================================================================


class TestInsertLvlLog:
    """insert_lvl_log MUST append an audit entry and return a frozen LvlLogRecord."""

    async def test_insert_lvl_returns_lvl_log_record(self, store: Store):
        """insert_lvl_log MUST return a LvlLogRecord."""
        result = await insert_lvl_log(store, **_lvl_kwargs())
        assert isinstance(result, LvlLogRecord)

    async def test_insert_lvl_returned_record_is_frozen(self, store: Store):
        """Returned LvlLogRecord MUST be frozen."""
        result = await insert_lvl_log(store, **_lvl_kwargs())
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            result.message = "mutated"  # type: ignore[misc]

    async def test_insert_lvl_id_is_positive_integer(self, store: Store):
        """Auto-incremented id MUST be a positive integer."""
        result = await insert_lvl_log(store, **_lvl_kwargs())
        assert isinstance(result.id, int)
        assert result.id > 0

    async def test_insert_lvl_stores_pipeline_id(self, store: Store):
        """pipeline_id MUST be preserved in the returned record."""
        pl_id = f"PL-{_uid()}"
        result = await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id))
        assert result.pipeline_id == pl_id

    async def test_insert_lvl_stores_level(self, store: Store):
        """level MUST be preserved in the returned record."""
        result = await insert_lvl_log(store, **_lvl_kwargs(level="WARN"))
        assert result.level == "WARN"

    async def test_insert_lvl_stores_message(self, store: Store):
        """message MUST be preserved in the returned record."""
        result = await insert_lvl_log(store, **_lvl_kwargs(message="Pipeline resumed"))
        assert result.message == "Pipeline resumed"

    async def test_insert_lvl_detail_none_when_not_provided(self, store: Store):
        """detail MUST be None when not provided."""
        result = await insert_lvl_log(store, **_lvl_kwargs(detail=None))
        assert result.detail is None

    async def test_insert_lvl_stores_detail_when_provided(self, store: Store):
        """detail MUST be preserved when provided."""
        result = await insert_lvl_log(store, **_lvl_kwargs(detail="Extended context"))
        assert result.detail == "Extended context"

    async def test_insert_lvl_created_at_non_empty(self, store: Store):
        """created_at MUST be a non-empty ISO string."""
        result = await insert_lvl_log(store, **_lvl_kwargs())
        assert isinstance(result.created_at, str)
        assert len(result.created_at) > 0

    async def test_insert_lvl_ids_increment(self, store: Store):
        """Successive inserts MUST produce increasing id values."""
        pl_id = f"PL-{_uid()}"
        r1 = await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id))
        r2 = await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id))
        assert r2.id > r1.id

    async def test_insert_lvl_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """insert_lvl_log MUST raise ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError):
            await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=""))

    async def test_insert_lvl_raises_value_error_on_empty_level(self, store: Store):
        """insert_lvl_log MUST raise ValueError when level is empty."""
        with pytest.raises(ValueError):
            await insert_lvl_log(store, **_lvl_kwargs(level=""))

    async def test_insert_lvl_raises_value_error_on_empty_message(self, store: Store):
        """insert_lvl_log MUST raise ValueError when message is empty."""
        with pytest.raises(ValueError):
            await insert_lvl_log(store, **_lvl_kwargs(message=""))


# ===========================================================================
# 10. list_lvl_logs
# ===========================================================================


class TestListLvlLogs:
    """list_lvl_logs MUST return a frozen tuple of LvlLogRecords ordered by id."""

    async def test_list_lvl_returns_empty_tuple_when_none(self, store: Store):
        """list_lvl_logs MUST return an empty tuple when no logs exist."""
        result = await list_lvl_logs(store, "PL-EMPTY-LVL")
        assert result == ()

    async def test_list_lvl_return_type_is_tuple(self, store: Store):
        """list_lvl_logs MUST return a tuple, not a list."""
        result = await list_lvl_logs(store, "PL-X")
        assert isinstance(result, tuple)

    async def test_list_lvl_returns_inserted_log(self, store: Store):
        """Logs inserted for a pipeline MUST be retrievable."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, message="hello"))
        result = await list_lvl_logs(store, pl_id)
        assert len(result) == 1
        assert result[0].message == "hello"

    async def test_list_lvl_returns_multiple_logs(self, store: Store):
        """list_lvl_logs MUST return all inserted logs for the pipeline."""
        pl_id = f"PL-{_uid()}"
        for i in range(4):
            await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, message=f"msg-{i}"))
        result = await list_lvl_logs(store, pl_id)
        assert len(result) == 4

    async def test_list_lvl_ordered_by_id_ascending(self, store: Store):
        """list_lvl_logs MUST return records in ascending id order."""
        pl_id = f"PL-{_uid()}"
        for i in range(3):
            await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, message=f"msg-{i}"))
        result = await list_lvl_logs(store, pl_id)
        ids = [r.id for r in result]
        assert ids == sorted(ids)

    async def test_list_lvl_only_returns_matching_pipeline(self, store: Store):
        """list_lvl_logs MUST NOT return logs from other pipelines."""
        pl_a = f"PL-A-{_uid()}"
        pl_b = f"PL-B-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_a))
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_b))
        result_a = await list_lvl_logs(store, pl_a)
        assert all(r.pipeline_id == pl_a for r in result_a)

    async def test_list_lvl_elements_are_frozen(self, store: Store):
        """Each LvlLogRecord in the returned tuple MUST be frozen."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id))
        result = await list_lvl_logs(store, pl_id)
        for rec in result:
            with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                rec.message = "mutated"  # type: ignore[misc]

    async def test_list_lvl_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """list_lvl_logs MUST raise ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError):
            await list_lvl_logs(store, "")


# ===========================================================================
# 11. list_lvl_logs_by_level
# ===========================================================================


class TestListLvlLogsByLevel:
    """list_lvl_logs_by_level MUST filter audit logs by level for a pipeline."""

    async def test_by_level_returns_matching_records(self, store: Store):
        """Only logs with the requested level MUST be returned."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="INFO"))
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="ERROR"))
        result = await list_lvl_logs_by_level(store, pl_id, "INFO")
        assert all(r.level == "INFO" for r in result)

    async def test_by_level_count_correct(self, store: Store):
        """Correct count of matching logs MUST be returned."""
        pl_id = f"PL-{_uid()}"
        for _ in range(3):
            await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="WARN"))
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="INFO"))
        result = await list_lvl_logs_by_level(store, pl_id, "WARN")
        assert len(result) == 3

    async def test_by_level_returns_empty_when_no_match(self, store: Store):
        """Returns empty tuple when no logs match the level."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="INFO"))
        result = await list_lvl_logs_by_level(store, pl_id, "DEBUG")
        assert result == ()

    async def test_by_level_return_type_is_tuple(self, store: Store):
        """Return type MUST be a tuple."""
        result = await list_lvl_logs_by_level(store, "PL-X", "INFO")
        assert isinstance(result, tuple)

    async def test_by_level_case_sensitive(self, store: Store):
        """Level matching MUST be case-sensitive (INFO != info)."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="INFO"))
        result_lower = await list_lvl_logs_by_level(store, pl_id, "info")
        assert result_lower == ()

    async def test_by_level_records_are_frozen(self, store: Store):
        """Returned LvlLogRecords MUST be frozen."""
        pl_id = f"PL-{_uid()}"
        await insert_lvl_log(store, **_lvl_kwargs(pipeline_id=pl_id, level="ERROR"))
        result = await list_lvl_logs_by_level(store, pl_id, "ERROR")
        for rec in result:
            with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
                rec.level = "mutated"  # type: ignore[misc]

    async def test_by_level_raises_value_error_on_empty_pipeline_id(self, store: Store):
        """Raises ValueError when pipeline_id is empty."""
        with pytest.raises(ValueError):
            await list_lvl_logs_by_level(store, "", "INFO")

    async def test_by_level_raises_value_error_on_empty_level(self, store: Store):
        """Raises ValueError when level is empty."""
        with pytest.raises(ValueError):
            await list_lvl_logs_by_level(store, "PL-X", "")


# ===========================================================================
# 12. Edge cases — special characters, Unicode, large payloads
# ===========================================================================


class TestEdgeCases:
    """Edge cases MUST be handled correctly by all query helpers."""

    async def test_task_description_with_single_quotes(self, store: Store):
        """Task description with SQL single quotes MUST be stored safely."""
        kw = _task_kwargs(description="It's a test with 'quotes'")
        result = await upsert_task_record(store, **kw)
        assert result.description == "It's a test with 'quotes'"

    async def test_task_description_with_unicode(self, store: Store):
        """Task description with Unicode (including CJK) MUST be stored correctly."""
        kw = _task_kwargs(description="测试任务: 实现登录功能 \U0001f600")
        result = await upsert_task_record(store, **kw)
        assert result.description == "测试任务: 实现登录功能 \U0001f600"

    async def test_evidence_detail_with_newlines(self, store: Store):
        """Evidence detail with newlines MUST be stored and retrieved intact."""
        detail = "Line1\nLine2\nLine3"
        kw = _evidence_kwargs(detail=detail)
        result = await insert_evidence_record(store, **kw)
        assert result.detail == detail

    async def test_lvl_log_message_with_special_characters(self, store: Store):
        """LVL log message with special chars MUST be stored correctly."""
        msg = "Stage <spec> failed: 5 errors & 2 warnings"
        result = await insert_lvl_log(store, **_lvl_kwargs(message=msg))
        assert result.message == msg

    async def test_task_with_many_requirements(self, store: Store):
        """Task with 50 requirements MUST store all of them."""
        reqs = [f"req-{i:03d}" for i in range(50)]
        kw = _task_kwargs(requirements=reqs)
        result = await upsert_task_record(store, **kw)
        assert len(result.requirements) == 50

    async def test_evidence_chain_large_detail(self, store: Store):
        """Evidence detail with 10 000 characters MUST be stored in full."""
        large_detail = "x" * 10_000
        kw = _evidence_kwargs(detail=large_detail)
        result = await insert_evidence_record(store, **kw)
        assert result.detail == large_detail
        assert len(result.detail) == 10_000

    async def test_task_file_path_with_spaces(self, store: Store):
        """file_path containing spaces MUST be stored correctly."""
        kw = _task_kwargs(file_path="src/my module/foo bar.py")
        result = await upsert_task_record(store, **kw)
        assert result.file_path == "src/my module/foo bar.py"

    async def test_upsert_and_get_round_trip(self, store: Store):
        """upsert then get MUST return identical field values."""
        task_id = f"T-{_uid()}"
        kw = _task_kwargs(
            task_id=task_id,
            description="Round-trip test",
            file_path="src/rt.py",
            parallel=True,
            user_story="As a user",
            requirements=["r1", "r2"],
            status="pending",
            group_name="rt-group",
        )
        await upsert_task_record(store, **kw)
        fetched = await get_task_record(store, task_id)
        assert fetched.task_id == task_id
        assert fetched.description == "Round-trip test"
        assert fetched.file_path == "src/rt.py"
        assert fetched.parallel is True
        assert fetched.user_story == "As a user"
        assert set(fetched.requirements) == {"r1", "r2"}
        assert fetched.status == "pending"
        assert fetched.group_name == "rt-group"
