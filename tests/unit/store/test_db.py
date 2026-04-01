"""RED-phase unit tests for orchestrator/store/db.py — SQLite persistence layer.

FR-002: Store MUST support pipeline resume via checkpoint persistence.
FR-036: Store MUST use INSERT OR REPLACE (upsert) for task records so that
        mutable fields (file_path, status, group_name) stay current.
FR-037: Store MUST maintain an audit trail via the evidence table.

Spec references:
    data-model.md "SQLite Schema" — v1-compatible tables + v2 new tables.
    data-model.md "Write Coordination" — WAL mode, lock-free store.
    pitfall #9 — INSERT OR IGNORE loses mutable-field updates; use REPLACE.

These are RED-phase tests.  They MUST FAIL until orchestrator/store/db.py
provides a full implementation.  The stub currently raises NotImplementedError
on every method, so all tests will fail with AssertionError or a propagated
NotImplementedError — this is the intended RED state.

Test coverage areas:
    1. Store.__init__ — accepts db_path, does NOT connect immediately
    2. Store.initialize — creates all v1-compatible tables
    3. Store.initialize — creates all v2 new tables
    4. Store.initialize — enables WAL journal mode
    5. Async context manager (__aenter__ / __aexit__)
    6. Store.is_open / Store.close connection lifecycle
    7. Pipeline CRUD (upsert_pipeline / get_pipeline)
    8. Task CRUD — upsert_task / get_task / list_tasks / update_task_status
    9. Task upsert IS OR REPLACE (overwrites mutable fields on re-insert)
   10. StageProgress CRUD (upsert_stage_progress / get_stage_progress)
   11. Checkpoint persistence (save_checkpoint / load_checkpoint)
   12. Review insert / get_reviews_for_task
   13. Evidence insert / list_evidence
   14. Settings key-value (set_setting / get_setting)
   15. Config cache (cache_config / load_cached_config)
   16. Schema version tracking (get_schema_version)
   17. Error paths — get_* returns None for missing keys
   18. Edge cases — empty lists, special characters, large payloads
"""

from __future__ import annotations

import asyncio
import json
import os
import string
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.
# The stub raises NotImplementedError on every method, so tests will fail
# with NotImplementedError (propagated) — the intended RED state.
# ---------------------------------------------------------------------------
from orchestrator.store.db import Store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_db(tmp_path: Path) -> str:
    """Return a unique temporary database file path."""
    return str(tmp_path / f"test_{uuid.uuid4().hex}.db")


def _uid() -> str:
    return uuid.uuid4().hex


# ===========================================================================
# 1. Store construction — does NOT connect on __init__
# ===========================================================================


class TestStoreConstruction:
    """Store(db_path) MUST accept a file-system path and store it without
    opening a database connection eagerly."""

    def test_store_accepts_string_db_path(self, tmp_path: Path):
        """Store MUST construct with a string db_path without raising."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        assert store is not None

    def test_store_db_path_attribute_is_stored(self, tmp_path: Path):
        """FR-002: Store MUST expose the db_path it was given."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        assert store.db_path == db_path

    def test_store_is_not_open_after_construction(self, tmp_path: Path):
        """Store MUST NOT open a connection during __init__ (lazy open)."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        assert store.is_open() is False

    def test_store_does_not_create_db_file_on_construction(self, tmp_path: Path):
        """DB file MUST NOT exist on disk after __init__ (file created on
        initialize or __aenter__)."""
        db_path = _tmp_db(tmp_path)
        Store(db_path)
        assert not os.path.exists(db_path), (
            "DB file MUST NOT be created by __init__; only by initialize()."
        )


# ===========================================================================
# 2. initialize() — creates all v1-compatible tables
# ===========================================================================


class TestInitializeV1Tables:
    """Store.initialize MUST create all v1-compatible tables so that v2 can
    open databases originally created by v1."""

    @pytest.fixture
    async def open_store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        yield store
        await store.close()

    async def _table_exists(self, store: Store, table: str) -> bool:
        """Query sqlite_master to check for table existence."""
        import sqlite3
        conn = sqlite3.connect(store.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        result = cur.fetchone()
        conn.close()
        return result is not None

    async def test_tasks_table_created(self, open_store: Store):
        """FR-036: 'tasks' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "tasks")

    async def test_reviews_table_created(self, open_store: Store):
        """'reviews' table MUST exist after initialize (v1-compatible)."""
        assert await self._table_exists(open_store, "reviews")

    async def test_evidence_table_created(self, open_store: Store):
        """FR-037: 'evidence' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "evidence")

    async def test_stage_progress_table_created(self, open_store: Store):
        """'stage_progress' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "stage_progress")

    async def test_step_status_table_created(self, open_store: Store):
        """'step_status' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "step_status")

    async def test_lvl_table_created(self, open_store: Store):
        """'lvl' table MUST exist after initialize (LVL audit logs)."""
        assert await self._table_exists(open_store, "lvl")

    async def test_checkpoints_table_created(self, open_store: Store):
        """FR-002: 'checkpoints' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "checkpoints")

    async def test_settings_table_created(self, open_store: Store):
        """'settings' table MUST exist after initialize."""
        assert await self._table_exists(open_store, "settings")


# ===========================================================================
# 3. initialize() — creates v2 new tables
# ===========================================================================


class TestInitializeV2Tables:
    """Store.initialize MUST also create the new v2-only tables."""

    @pytest.fixture
    async def open_store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        yield store
        await store.close()

    async def _table_exists(self, store: Store, table: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(store.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        result = cur.fetchone()
        conn.close()
        return result is not None

    async def test_pipelines_table_created(self, open_store: Store):
        """'pipelines' table MUST exist after initialize (new in v2)."""
        assert await self._table_exists(open_store, "pipelines")

    async def test_config_cache_table_created(self, open_store: Store):
        """'config_cache' table MUST exist after initialize (new in v2)."""
        assert await self._table_exists(open_store, "config_cache")

    async def test_task_groups_table_created(self, open_store: Store):
        """'task_groups' table MUST exist after initialize (new in v2)."""
        assert await self._table_exists(open_store, "task_groups")


# ===========================================================================
# 4. initialize() — WAL journal mode
# ===========================================================================


class TestWALMode:
    """Store.initialize MUST enable WAL journal mode for concurrent reads."""

    async def test_wal_mode_enabled_after_initialize(self, tmp_path: Path):
        """PRAGMA journal_mode MUST return 'wal' after initialize."""
        import sqlite3

        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        await store.close()

        conn = sqlite3.connect(db_path)
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        conn.close()

        assert mode == "wal", (
            f"Expected WAL journal mode, got '{mode}'. "
            "WAL mode is required for concurrent reads without blocking writes."
        )

    async def test_is_open_true_after_initialize(self, tmp_path: Path):
        """is_open() MUST return True after initialize() is called."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        assert store.is_open() is True
        await store.close()


# ===========================================================================
# 5. Async context manager
# ===========================================================================


class TestAsyncContextManager:
    """Store MUST support async context manager protocol so callers can use
    `async with Store(path) as store:`."""

    async def test_aenter_returns_store_instance(self, tmp_path: Path):
        """__aenter__ MUST return the Store instance itself."""
        db_path = _tmp_db(tmp_path)
        async with Store(db_path) as store:
            assert isinstance(store, Store)

    async def test_store_is_open_inside_context(self, tmp_path: Path):
        """is_open() MUST return True while inside the async with block."""
        db_path = _tmp_db(tmp_path)
        async with Store(db_path) as store:
            assert store.is_open() is True

    async def test_store_is_closed_after_context_exits(self, tmp_path: Path):
        """is_open() MUST return False after the async with block exits."""
        db_path = _tmp_db(tmp_path)
        async with Store(db_path) as store:
            pass
        assert store.is_open() is False

    async def test_aexit_closes_connection_on_exception(self, tmp_path: Path):
        """__aexit__ MUST close the connection even when an exception is raised
        inside the with block."""
        db_path = _tmp_db(tmp_path)
        store_ref = None
        try:
            async with Store(db_path) as store:
                store_ref = store
                raise RuntimeError("intentional error")
        except RuntimeError:
            pass
        assert store_ref is not None
        assert store_ref.is_open() is False

    async def test_context_manager_creates_all_tables(self, tmp_path: Path):
        """Entering the context manager MUST create all required tables."""
        import sqlite3

        db_path = _tmp_db(tmp_path)
        async with Store(db_path) as _store:
            pass

        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cur.fetchall()}
        conn.close()

        required = {"tasks", "pipelines", "checkpoints", "stage_progress", "evidence"}
        missing = required - tables
        assert not missing, f"Tables missing after context manager exit: {missing}"


# ===========================================================================
# 6. Connection lifecycle — close()
# ===========================================================================


class TestConnectionLifecycle:
    """Store.close() MUST release the SQLite connection."""

    async def test_close_sets_is_open_false(self, tmp_path: Path):
        """After close(), is_open() MUST return False."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        assert store.is_open() is True
        await store.close()
        assert store.is_open() is False

    async def test_close_is_idempotent(self, tmp_path: Path):
        """Calling close() twice MUST NOT raise an exception."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        await store.close()
        await store.close()  # second call must not raise

    async def test_initialize_can_be_called_again_after_close(self, tmp_path: Path):
        """After close(), calling initialize() on the SAME store MUST re-open
        the connection (store is reusable)."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()
        await store.close()
        await store.initialize()
        assert store.is_open() is True
        await store.close()


# ===========================================================================
# 7. Pipeline CRUD
# ===========================================================================


class TestPipelineCRUD:
    """upsert_pipeline / get_pipeline provide full pipeline lifecycle support."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_upsert_pipeline_stores_pipeline(self, store: Store):
        """upsert_pipeline MUST persist a pipeline row retrievable by get_pipeline."""
        pid = _uid()
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/workspace/myproject",
            requirement_path="/workspace/myproject/requirement.md",
            current_stage="spec",
            status="running",
        )
        row = await store.get_pipeline(pid)
        assert row is not None
        assert row["pipeline_id"] == pid

    async def test_get_pipeline_returns_correct_fields(self, store: Store):
        """get_pipeline MUST return all stored fields."""
        pid = _uid()
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/workspace/proj",
            requirement_path="/workspace/proj/req.md",
            current_stage="plan",
            status="running",
        )
        row = await store.get_pipeline(pid)
        assert row["project_path"] == "/workspace/proj"
        assert row["requirement_path"] == "/workspace/proj/req.md"
        assert row["current_stage"] == "plan"
        assert row["status"] == "running"

    async def test_get_pipeline_returns_none_for_missing_id(self, store: Store):
        """get_pipeline MUST return None when the pipeline_id does not exist."""
        result = await store.get_pipeline("nonexistent-pipeline-id")
        assert result is None

    async def test_upsert_pipeline_overwrites_on_duplicate_id(self, store: Store):
        """upsert_pipeline MUST update existing rows (INSERT OR REPLACE semantics)."""
        pid = _uid()
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/first",
            requirement_path=None,
            current_stage="spec",
            status="running",
        )
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/first",
            requirement_path=None,
            current_stage="plan",
            status="running",
        )
        row = await store.get_pipeline(pid)
        assert row["current_stage"] == "plan"

    async def test_upsert_pipeline_accepts_none_requirement_path(self, store: Store):
        """requirement_path may be None (optional field)."""
        pid = _uid()
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/workspace",
            requirement_path=None,
            current_stage="spec",
            status="running",
        )
        row = await store.get_pipeline(pid)
        assert row["requirement_path"] is None

    async def test_pipeline_created_at_is_set(self, store: Store):
        """created_at MUST be set automatically when pipeline is inserted."""
        pid = _uid()
        await store.upsert_pipeline(
            pipeline_id=pid,
            project_path="/p",
            requirement_path=None,
            current_stage="spec",
            status="running",
        )
        row = await store.get_pipeline(pid)
        assert row.get("created_at") is not None


# ===========================================================================
# 8. Task CRUD
# ===========================================================================


class TestTaskCRUD:
    """upsert_task / get_task / list_tasks / update_task_status."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    def _make_task_kwargs(self, task_id: str = "T001") -> dict:
        return dict(
            task_id=task_id,
            description="Implement user authentication",
            file_path="src/auth.py",
            parallel=False,
            user_story="US1",
            requirements=["FR-001", "FR-002"],
            status="pending",
            group_name="us_1",
        )

    async def test_upsert_task_stores_task(self, store: Store):
        """upsert_task MUST persist a task row retrievable by get_task."""
        await store.upsert_task(**self._make_task_kwargs("T001"))
        row = await store.get_task("T001")
        assert row is not None
        assert row["task_id"] == "T001"

    async def test_get_task_returns_correct_description(self, store: Store):
        """get_task MUST return the description field."""
        await store.upsert_task(**self._make_task_kwargs("T002"))
        row = await store.get_task("T002")
        assert row["description"] == "Implement user authentication"

    async def test_get_task_returns_correct_file_path(self, store: Store):
        """get_task MUST return the file_path field."""
        await store.upsert_task(**self._make_task_kwargs("T003"))
        row = await store.get_task("T003")
        assert row["file_path"] == "src/auth.py"

    async def test_get_task_returns_parallel_flag(self, store: Store):
        """get_task MUST return the parallel boolean field."""
        kw = self._make_task_kwargs("T004")
        kw["parallel"] = True
        await store.upsert_task(**kw)
        row = await store.get_task("T004")
        # parallel may be stored as int 1/0 or bool True/False
        assert bool(row["parallel"]) is True

    async def test_get_task_returns_requirements_as_list(self, store: Store):
        """requirements MUST be returned as a Python list (deserialized from JSON)."""
        await store.upsert_task(**self._make_task_kwargs("T005"))
        row = await store.get_task("T005")
        reqs = row["requirements"]
        assert isinstance(reqs, list), "requirements MUST be a list, not a raw JSON string"
        assert "FR-001" in reqs

    async def test_get_task_returns_none_for_missing_id(self, store: Store):
        """get_task MUST return None when the task_id does not exist."""
        result = await store.get_task("T999")
        assert result is None

    async def test_list_tasks_returns_all_tasks(self, store: Store):
        """list_tasks MUST return all inserted tasks."""
        for i in range(1, 4):
            kw = self._make_task_kwargs(f"T{i:03d}")
            await store.upsert_task(**kw)
        tasks = await store.list_tasks()
        ids = {t["task_id"] for t in tasks}
        assert {"T001", "T002", "T003"}.issubset(ids)

    async def test_list_tasks_returns_empty_list_when_no_tasks(self, store: Store):
        """list_tasks MUST return an empty list when no tasks exist."""
        tasks = await store.list_tasks()
        assert tasks == []

    async def test_update_task_status_changes_status(self, store: Store):
        """update_task_status MUST change the status field of the specified task."""
        await store.upsert_task(**self._make_task_kwargs("T010"))
        await store.update_task_status("T010", "red_pass")
        row = await store.get_task("T010")
        assert row["status"] == "red_pass"

    async def test_upsert_task_accepts_none_user_story(self, store: Store):
        """user_story may be None for tasks without a user story tag."""
        kw = self._make_task_kwargs("T011")
        kw["user_story"] = None
        await store.upsert_task(**kw)
        row = await store.get_task("T011")
        assert row["user_story"] is None


# ===========================================================================
# 9. Task upsert IS OR REPLACE — FR-036 / Pitfall #9
# ===========================================================================


class TestTaskUpsertOrReplace:
    """FR-036: INSERT OR REPLACE MUST overwrite mutable fields on re-insert.
    This prevents Pitfall #9 where INSERT OR IGNORE silently drops updates."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_upsert_overwrites_file_path(self, store: Store):
        """Re-inserting same task_id with new file_path MUST update the row."""
        await store.upsert_task(
            task_id="T001",
            description="Old desc",
            file_path="old/path.py",
            parallel=False,
            user_story=None,
            requirements=["FR-001"],
            status="pending",
            group_name="setup",
        )
        await store.upsert_task(
            task_id="T001",
            description="Old desc",
            file_path="new/path.py",
            parallel=False,
            user_story=None,
            requirements=["FR-001"],
            status="pending",
            group_name="setup",
        )
        row = await store.get_task("T001")
        assert row["file_path"] == "new/path.py", (
            "FR-036: file_path MUST be updated on second upsert. "
            "INSERT OR IGNORE would leave 'old/path.py' — that is the pitfall #9 bug."
        )

    async def test_upsert_overwrites_status(self, store: Store):
        """Re-inserting same task_id with new status MUST update the row."""
        await store.upsert_task(
            task_id="T002",
            description="Desc",
            file_path="src/foo.py",
            parallel=False,
            user_story=None,
            requirements=["FR-002"],
            status="pending",
            group_name="us_1",
        )
        await store.upsert_task(
            task_id="T002",
            description="Desc",
            file_path="src/foo.py",
            parallel=False,
            user_story=None,
            requirements=["FR-002"],
            status="red_pass",
            group_name="us_1",
        )
        row = await store.get_task("T002")
        assert row["status"] == "red_pass"

    async def test_upsert_overwrites_group_name(self, store: Store):
        """Re-inserting with new group_name MUST update the row."""
        await store.upsert_task(
            task_id="T003",
            description="Desc",
            file_path="src/bar.py",
            parallel=False,
            user_story=None,
            requirements=["FR-003"],
            status="pending",
            group_name="setup",
        )
        await store.upsert_task(
            task_id="T003",
            description="Desc",
            file_path="src/bar.py",
            parallel=False,
            user_story=None,
            requirements=["FR-003"],
            status="pending",
            group_name="polish",
        )
        row = await store.get_task("T003")
        assert row["group_name"] == "polish"


# ===========================================================================
# 10. StageProgress CRUD
# ===========================================================================


class TestStageProgressCRUD:
    """upsert_stage_progress / get_stage_progress."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_upsert_stage_progress_stores_row(self, store: Store):
        """upsert_stage_progress MUST persist a row retrievable by get_stage_progress."""
        pid = _uid()
        await store.upsert_stage_progress(
            pipeline_id=pid,
            stage="spec",
            status="running",
        )
        row = await store.get_stage_progress(pid, "spec")
        assert row is not None
        assert row["pipeline_id"] == pid
        assert row["stage"] == "spec"
        assert row["status"] == "running"

    async def test_get_stage_progress_returns_none_for_missing(self, store: Store):
        """get_stage_progress MUST return None when the (pipeline_id, stage) pair
        does not exist."""
        result = await store.get_stage_progress("no-such-pipeline", "spec")
        assert result is None

    async def test_upsert_stage_progress_updates_status(self, store: Store):
        """Second upsert MUST overwrite the status field."""
        pid = _uid()
        await store.upsert_stage_progress(
            pipeline_id=pid, stage="plan", status="running"
        )
        await store.upsert_stage_progress(
            pipeline_id=pid, stage="plan", status="passed"
        )
        row = await store.get_stage_progress(pid, "plan")
        assert row["status"] == "passed"

    async def test_upsert_stage_progress_stores_review_attempts(self, store: Store):
        """review_attempts MUST be persisted and returned."""
        pid = _uid()
        await store.upsert_stage_progress(
            pipeline_id=pid,
            stage="implement",
            status="review",
            review_attempts=2,
        )
        row = await store.get_stage_progress(pid, "implement")
        assert row["review_attempts"] == 2

    async def test_upsert_stage_progress_stores_checkpoint_data(self, store: Store):
        """checkpoint_data JSON blob MUST be persisted and returned."""
        pid = _uid()
        blob = json.dumps({"spec_file": "specs/spec.md", "tasks_written": 12})
        await store.upsert_stage_progress(
            pipeline_id=pid,
            stage="spec",
            status="passed",
            checkpoint_data=blob,
        )
        row = await store.get_stage_progress(pid, "spec")
        assert row["checkpoint_data"] == blob

    async def test_upsert_stage_progress_defaults_review_attempts_zero(
        self, store: Store
    ):
        """If review_attempts is not supplied, it MUST default to 0."""
        pid = _uid()
        await store.upsert_stage_progress(
            pipeline_id=pid, stage="acceptance", status="pending"
        )
        row = await store.get_stage_progress(pid, "acceptance")
        assert row["review_attempts"] == 0


# ===========================================================================
# 11. Checkpoint persistence — FR-002
# ===========================================================================


class TestCheckpointPersistence:
    """FR-002: save_checkpoint / load_checkpoint enable pipeline resume."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_save_and_load_checkpoint(self, store: Store):
        """save_checkpoint followed by load_checkpoint MUST return the same state."""
        pid = _uid()
        state = json.dumps({"step": "constitution", "tasks_count": 5})
        await store.save_checkpoint(
            pipeline_id=pid,
            stage="spec",
            step="constitution",
            state_json=state,
        )
        row = await store.load_checkpoint(pid, "spec", "constitution")
        assert row is not None
        assert row["state_json"] == state

    async def test_load_checkpoint_returns_none_for_missing(self, store: Store):
        """load_checkpoint MUST return None when the triple (pid, stage, step)
        does not exist."""
        result = await store.load_checkpoint("ghost-pid", "spec", "constitution")
        assert result is None

    async def test_save_checkpoint_overwrites_previous_state(self, store: Store):
        """Saving a checkpoint for the same (pid, stage, step) MUST replace the
        previous state (not create a duplicate)."""
        pid = _uid()
        await store.save_checkpoint(
            pipeline_id=pid, stage="spec", step="constitution",
            state_json=json.dumps({"v": 1})
        )
        await store.save_checkpoint(
            pipeline_id=pid, stage="spec", step="constitution",
            state_json=json.dumps({"v": 2})
        )
        row = await store.load_checkpoint(pid, "spec", "constitution")
        saved = json.loads(row["state_json"])
        assert saved["v"] == 2, (
            "Second save_checkpoint MUST overwrite first; only one row per "
            "(pipeline_id, stage, step)."
        )

    async def test_save_checkpoint_stores_created_at(self, store: Store):
        """created_at MUST be set automatically when a checkpoint is saved."""
        pid = _uid()
        await store.save_checkpoint(
            pipeline_id=pid, stage="plan", step="draft",
            state_json=json.dumps({"ok": True})
        )
        row = await store.load_checkpoint(pid, "plan", "draft")
        assert row.get("created_at") is not None

    async def test_multiple_stages_tracked_independently(self, store: Store):
        """Checkpoints for different stages MUST not interfere with each other."""
        pid = _uid()
        await store.save_checkpoint(
            pipeline_id=pid, stage="spec", step="s1", state_json='{"a":1}'
        )
        await store.save_checkpoint(
            pipeline_id=pid, stage="plan", step="s1", state_json='{"b":2}'
        )
        spec_row = await store.load_checkpoint(pid, "spec", "s1")
        plan_row = await store.load_checkpoint(pid, "plan", "s1")
        assert json.loads(spec_row["state_json"])["a"] == 1
        assert json.loads(plan_row["state_json"])["b"] == 2


# ===========================================================================
# 12. Review CRUD
# ===========================================================================


class TestReviewCRUD:
    """insert_review / get_reviews_for_task."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_insert_review_stores_row(self, store: Store):
        """insert_review MUST persist a review row."""
        rid = _uid()
        await store.insert_review(
            review_id=rid,
            task_id="T001",
            review_type="code",
            passed=True,
            findings=[],
            raw_output="LGTM",
        )
        rows = await store.get_reviews_for_task("T001")
        ids = [r["review_id"] for r in rows]
        assert rid in ids

    async def test_get_reviews_for_task_returns_empty_list_when_none(
        self, store: Store
    ):
        """get_reviews_for_task MUST return an empty list when no reviews exist."""
        rows = await store.get_reviews_for_task("T999")
        assert rows == []

    async def test_review_passed_field_persisted(self, store: Store):
        """passed boolean MUST be persisted and returned correctly."""
        rid = _uid()
        await store.insert_review(
            review_id=rid,
            task_id="T002",
            review_type="security",
            passed=False,
            findings=["SQL injection risk"],
            raw_output="Found issues.",
        )
        rows = await store.get_reviews_for_task("T002")
        row = next(r for r in rows if r["review_id"] == rid)
        assert bool(row["passed"]) is False

    async def test_review_findings_returned_as_list(self, store: Store):
        """findings MUST be returned as a Python list (deserialized from JSON)."""
        rid = _uid()
        await store.insert_review(
            review_id=rid,
            task_id="T003",
            review_type="brooks",
            passed=True,
            findings=["Minor: add docstring"],
            raw_output="One suggestion.",
        )
        rows = await store.get_reviews_for_task("T003")
        row = next(r for r in rows if r["review_id"] == rid)
        assert isinstance(row["findings"], list)
        assert "Minor: add docstring" in row["findings"]

    async def test_multiple_reviews_per_task(self, store: Store):
        """Multiple reviews for the same task_id MUST all be returned."""
        for i in range(3):
            await store.insert_review(
                review_id=_uid(),
                task_id="T004",
                review_type="code",
                passed=(i % 2 == 0),
                findings=[],
                raw_output=f"Review pass {i}",
            )
        rows = await store.get_reviews_for_task("T004")
        assert len(rows) == 3

    async def test_review_review_type_persisted(self, store: Store):
        """review_type MUST be persisted and returned."""
        rid = _uid()
        await store.insert_review(
            review_id=rid,
            task_id="T005",
            review_type="brooks",
            passed=True,
            findings=[],
            raw_output="",
        )
        rows = await store.get_reviews_for_task("T005")
        row = next(r for r in rows if r["review_id"] == rid)
        assert row["review_type"] == "brooks"


# ===========================================================================
# 13. Evidence CRUD — FR-037
# ===========================================================================


class TestEvidenceCRUD:
    """FR-037: insert_evidence / list_evidence maintain the audit trail."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_insert_evidence_stores_row(self, store: Store):
        """insert_evidence MUST persist an evidence row."""
        pid = _uid()
        eid = _uid()
        await store.insert_evidence(
            evidence_id=eid,
            pipeline_id=pid,
            stage="spec",
            task_id=None,
            event_type="agent_call",
            detail=json.dumps({"agent": "specifier", "tokens": 1200}),
        )
        rows = await store.list_evidence(pid)
        ids = [r["evidence_id"] for r in rows]
        assert eid in ids

    async def test_list_evidence_returns_empty_list_for_unknown_pipeline(
        self, store: Store
    ):
        """list_evidence MUST return an empty list when no evidence for pipeline_id."""
        rows = await store.list_evidence("ghost-pipeline")
        assert rows == []

    async def test_evidence_event_type_persisted(self, store: Store):
        """event_type MUST be persisted and returned."""
        pid = _uid()
        eid = _uid()
        await store.insert_evidence(
            evidence_id=eid,
            pipeline_id=pid,
            stage="implement",
            task_id="T001",
            event_type="commit",
            detail="{}",
        )
        rows = await store.list_evidence(pid)
        row = next(r for r in rows if r["evidence_id"] == eid)
        assert row["event_type"] == "commit"

    async def test_evidence_task_id_can_be_none(self, store: Store):
        """task_id MUST be allowed to be None (stage-level evidence)."""
        pid = _uid()
        eid = _uid()
        await store.insert_evidence(
            evidence_id=eid,
            pipeline_id=pid,
            stage="plan",
            task_id=None,
            event_type="review",
            detail="{}",
        )
        rows = await store.list_evidence(pid)
        row = next(r for r in rows if r["evidence_id"] == eid)
        assert row["task_id"] is None

    async def test_evidence_scoped_to_pipeline(self, store: Store):
        """list_evidence MUST only return evidence for the specified pipeline_id."""
        pid_a = _uid()
        pid_b = _uid()
        eid_a = _uid()
        eid_b = _uid()
        await store.insert_evidence(
            evidence_id=eid_a,
            pipeline_id=pid_a,
            stage="spec",
            task_id=None,
            event_type="agent_call",
            detail="{}",
        )
        await store.insert_evidence(
            evidence_id=eid_b,
            pipeline_id=pid_b,
            stage="spec",
            task_id=None,
            event_type="agent_call",
            detail="{}",
        )
        rows_a = await store.list_evidence(pid_a)
        ids_a = {r["evidence_id"] for r in rows_a}
        assert eid_a in ids_a
        assert eid_b not in ids_a

    async def test_evidence_detail_is_json_string(self, store: Store):
        """detail MUST be stored and returned as the original JSON string."""
        pid = _uid()
        eid = _uid()
        detail = json.dumps({"agent": "specifier", "tokens": 1337, "nested": {"x": 1}})
        await store.insert_evidence(
            evidence_id=eid,
            pipeline_id=pid,
            stage="spec",
            task_id=None,
            event_type="agent_call",
            detail=detail,
        )
        rows = await store.list_evidence(pid)
        row = next(r for r in rows if r["evidence_id"] == eid)
        assert row["detail"] == detail


# ===========================================================================
# 14. Settings key-value
# ===========================================================================


class TestSettings:
    """set_setting / get_setting provide a key-value store for configuration."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_set_and_get_setting(self, store: Store):
        """set_setting followed by get_setting MUST return the stored value."""
        await store.set_setting("last_run", "2026-04-01T12:00:00Z")
        value = await store.get_setting("last_run")
        assert value == "2026-04-01T12:00:00Z"

    async def test_get_setting_returns_none_for_missing_key(self, store: Store):
        """get_setting MUST return None for a key that has never been set."""
        value = await store.get_setting("nonexistent_key")
        assert value is None

    async def test_set_setting_overwrites_existing_value(self, store: Store):
        """Re-setting the same key MUST overwrite the previous value."""
        await store.set_setting("schema_version", "1")
        await store.set_setting("schema_version", "2")
        value = await store.get_setting("schema_version")
        assert value == "2"

    async def test_multiple_settings_stored_independently(self, store: Store):
        """Multiple distinct keys MUST be stored and retrieved independently."""
        await store.set_setting("key_a", "val_a")
        await store.set_setting("key_b", "val_b")
        assert await store.get_setting("key_a") == "val_a"
        assert await store.get_setting("key_b") == "val_b"


# ===========================================================================
# 15. Config cache
# ===========================================================================


class TestConfigCache:
    """cache_config / load_cached_config persist the merged OrchestratorConfig."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_cache_and_load_config(self, store: Store):
        """cache_config followed by load_cached_config MUST return the same JSON."""
        pid = _uid()
        config_json = json.dumps({"max_retries": 3, "local_test": True})
        await store.cache_config(pid, config_json)
        result = await store.load_cached_config(pid)
        assert result == config_json

    async def test_load_cached_config_returns_none_for_missing(self, store: Store):
        """load_cached_config MUST return None for an unknown pipeline_id."""
        result = await store.load_cached_config("no-such-pipeline")
        assert result is None

    async def test_cache_config_overwrites_on_same_pipeline_id(self, store: Store):
        """Re-caching the same pipeline_id MUST replace the previous config."""
        pid = _uid()
        await store.cache_config(pid, '{"v": 1}')
        await store.cache_config(pid, '{"v": 2}')
        result = await store.load_cached_config(pid)
        assert json.loads(result)["v"] == 2


# ===========================================================================
# 16. Schema version tracking
# ===========================================================================


class TestSchemaVersion:
    """get_schema_version provides version-aware migration support."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_schema_version_is_int_after_initialize(self, store: Store):
        """get_schema_version MUST return an integer (schema version number)."""
        version = await store.get_schema_version()
        assert isinstance(version, int), (
            f"Expected int schema version, got {type(version).__name__}"
        )

    async def test_schema_version_is_positive(self, store: Store):
        """Schema version MUST be >= 1 after initialize."""
        version = await store.get_schema_version()
        assert version >= 1, f"Schema version MUST be >= 1, got {version}"

    async def test_schema_version_consistent_across_calls(self, store: Store):
        """Two calls to get_schema_version MUST return the same value."""
        v1 = await store.get_schema_version()
        v2 = await store.get_schema_version()
        assert v1 == v2


# ===========================================================================
# 17. Error paths — missing rows return None / empty list
# ===========================================================================


class TestMissingRowReturnValues:
    """All get_* methods MUST return sentinel values (None or []) for
    missing rows rather than raising exceptions."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_get_pipeline_missing_returns_none(self, store: Store):
        assert await store.get_pipeline("ghost") is None

    async def test_get_task_missing_returns_none(self, store: Store):
        assert await store.get_task("T999") is None

    async def test_get_stage_progress_missing_returns_none(self, store: Store):
        assert await store.get_stage_progress("ghost", "spec") is None

    async def test_load_checkpoint_missing_returns_none(self, store: Store):
        assert await store.load_checkpoint("ghost", "spec", "step") is None

    async def test_get_reviews_for_task_missing_returns_empty_list(self, store: Store):
        assert await store.get_reviews_for_task("T999") == []

    async def test_list_evidence_missing_pipeline_returns_empty_list(
        self, store: Store
    ):
        assert await store.list_evidence("ghost-pipeline") == []

    async def test_get_setting_missing_returns_none(self, store: Store):
        assert await store.get_setting("nonexistent") is None

    async def test_load_cached_config_missing_returns_none(self, store: Store):
        assert await store.load_cached_config("ghost-pipeline") is None


# ===========================================================================
# 18. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Null bytes, special characters, large payloads, and concurrent access."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> Store:
        db_path = _tmp_db(tmp_path)
        s = Store(db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_task_with_unicode_description(self, store: Store):
        """Task description MUST support full Unicode including CJK and emoji."""
        desc = "实现用户认证 🔐 — UTF-8 edge case"
        await store.upsert_task(
            task_id="T_UNICODE",
            description=desc,
            file_path="src/auth.py",
            parallel=False,
            user_story=None,
            requirements=["FR-001"],
            status="pending",
            group_name="setup",
        )
        row = await store.get_task("T_UNICODE")
        assert row["description"] == desc

    async def test_task_with_empty_requirements_list(self, store: Store):
        """requirements=[] (empty list) MUST be stored and returned as empty list."""
        await store.upsert_task(
            task_id="T_EMPTY_REQS",
            description="No FR tags task",
            file_path="src/misc.py",
            parallel=False,
            user_story=None,
            requirements=[],
            status="pending",
            group_name="setup",
        )
        row = await store.get_task("T_EMPTY_REQS")
        assert row["requirements"] == []

    async def test_checkpoint_with_large_state_json(self, store: Store):
        """state_json blobs up to 100 KB MUST be stored and retrieved intact."""
        pid = _uid()
        large_data = {"tasks": [{"id": f"T{i:04d}", "desc": "x" * 100} for i in range(500)]}
        large_json = json.dumps(large_data)
        assert len(large_json) > 50_000, "Pre-condition: payload should be > 50 KB"

        await store.save_checkpoint(
            pipeline_id=pid,
            stage="implement",
            step="batch",
            state_json=large_json,
        )
        row = await store.load_checkpoint(pid, "implement", "batch")
        assert row["state_json"] == large_json

    async def test_evidence_with_sql_special_characters(self, store: Store):
        """Detail strings with SQL special characters MUST be stored safely
        (no SQL injection, no truncation)."""
        pid = _uid()
        eid = _uid()
        dangerous = json.dumps({"msg": "O'Reilly; DROP TABLE tasks; --"})
        await store.insert_evidence(
            evidence_id=eid,
            pipeline_id=pid,
            stage="spec",
            task_id=None,
            event_type="agent_call",
            detail=dangerous,
        )
        rows = await store.list_evidence(pid)
        row = next(r for r in rows if r["evidence_id"] == eid)
        assert row["detail"] == dangerous

    async def test_concurrent_writes_do_not_corrupt_data(self, tmp_path: Path):
        """Multiple concurrent upsert_task calls MUST not corrupt the database.
        This tests that the store handles concurrent async operations safely."""
        db_path = _tmp_db(tmp_path)
        store = Store(db_path)
        await store.initialize()

        async def write_task(i: int) -> None:
            await store.upsert_task(
                task_id=f"T{i:04d}",
                description=f"Concurrent task {i}",
                file_path=f"src/module_{i}.py",
                parallel=False,
                user_story=None,
                requirements=[f"FR-{i:03d}"],
                status="pending",
                group_name="setup",
            )

        await asyncio.gather(*[write_task(i) for i in range(20)])

        tasks = await store.list_tasks()
        assert len(tasks) == 20, (
            f"All 20 concurrent tasks MUST be stored; only found {len(tasks)}."
        )

        await store.close()

    async def test_setting_value_with_newlines(self, store: Store):
        """Setting values containing newlines MUST round-trip correctly."""
        multiline = "line1\nline2\nline3"
        await store.set_setting("multi", multiline)
        result = await store.get_setting("multi")
        assert result == multiline

    async def test_upsert_task_with_many_requirements(self, store: Store):
        """A task with 20 FR requirements MUST store and return all of them."""
        reqs = [f"FR-{i:03d}" for i in range(1, 21)]
        await store.upsert_task(
            task_id="T_MANY_REQS",
            description="Complex task",
            file_path="src/complex.py",
            parallel=True,
            user_story="US5",
            requirements=reqs,
            status="pending",
            group_name="us_5",
        )
        row = await store.get_task("T_MANY_REQS")
        assert len(row["requirements"]) == 20
        assert "FR-020" in row["requirements"]
