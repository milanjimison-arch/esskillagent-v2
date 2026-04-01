"""RED-phase unit tests for orchestrator/store/_schema.py — schema v3 upgrade.

These tests verify:
1. SCHEMA_VERSION constant is 3
2. The `artifacts` table is defined with correct columns and PRIMARY KEY
3. The `lvl_events` table is defined with correct columns and autoincrement PK
4. Both new tables have run_id indexes for efficient querying
5. All existing tables are still present in the DDL
6. ArtifactRecord dataclass matches the artifacts table columns (frozen)
7. LvlEventRecord dataclass matches the lvl_events table columns (frozen)
8. Edge cases: empty blob, None optional fields, field types

Test strategy:
- Import _schema.py and verify SCHEMA_VERSION == 3 (fails with current value of 2)
- Parse DDL string to assert table and column presence
- Import ArtifactRecord and LvlEventRecord (they don't exist yet — RED)
- Instantiate both dataclasses and assert field round-trips
- Verify frozen immutability for both new dataclasses
- Verify index definitions appear in DDL

These tests MUST FAIL until the implementation is added to _schema.py.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.
# ArtifactRecord and LvlEventRecord do not exist yet — this will fail at
# collection time until the implementation is provided (intended RED state).
# ---------------------------------------------------------------------------
from orchestrator.store._schema import (
    _DDL,
    SCHEMA_VERSION,
    ArtifactRecord,
    LvlEventRecord,
)


# ===========================================================================
# Helper utilities
# ===========================================================================


def _table_exists_in_ddl(ddl: str, table_name: str) -> bool:
    """Return True if a CREATE TABLE statement for *table_name* appears in ddl."""
    pattern = rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table_name)}\s*\("
    return bool(re.search(pattern, ddl, re.IGNORECASE))


def _extract_table_block(ddl: str, table_name: str) -> str:
    """Extract the CREATE TABLE (...) block for *table_name* from *ddl*.

    Returns an empty string if the table is not found.
    """
    pattern = (
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table_name)}"
        r"\s*\(([^)]+)\)"
    )
    match = re.search(pattern, ddl, re.IGNORECASE | re.DOTALL)
    return match.group(0) if match else ""


def _index_exists_in_ddl(ddl: str, table_name: str, column_name: str) -> bool:
    """Return True if a CREATE INDEX on *table_name*(*column_name*) appears in ddl."""
    pattern = (
        rf"CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+"
        rf"{re.escape(table_name)}\s*\(\s*{re.escape(column_name)}\s*\)"
    )
    return bool(re.search(pattern, ddl, re.IGNORECASE))


def _apply_ddl_to_memory_db(ddl: str) -> sqlite3.Connection:
    """Create an in-memory SQLite database and execute *ddl*.

    Returns the open connection. Caller is responsible for closing it.
    Raises sqlite3.OperationalError if the DDL is malformed.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)
    conn.commit()
    return conn


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Return a list of column names for *table_name* in *conn*."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    rows = cursor.fetchall()
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    return [row[1] for row in rows]


# ===========================================================================
# 1. SCHEMA_VERSION must be 3
# ===========================================================================


class TestSchemaVersion:
    """SCHEMA_VERSION MUST equal 3 after the v3 upgrade."""

    def test_schema_version_is_integer(self):
        """SCHEMA_VERSION MUST be an integer."""
        assert isinstance(SCHEMA_VERSION, int)

    def test_schema_version_equals_3(self):
        """SCHEMA_VERSION MUST equal 3 — the v3 upgrade has been applied."""
        assert SCHEMA_VERSION == 3

    def test_schema_version_is_not_2(self):
        """SCHEMA_VERSION MUST NOT be the old v2 value."""
        assert SCHEMA_VERSION != 2

    def test_schema_version_is_positive(self):
        """SCHEMA_VERSION MUST be a positive integer."""
        assert SCHEMA_VERSION > 0


# ===========================================================================
# 2. DDL string — artifacts table presence and columns
# ===========================================================================


class TestArtifactsTableDDL:
    """The `artifacts` table MUST be present in _DDL with all required columns."""

    def test_artifacts_table_exists_in_ddl(self):
        """DDL MUST contain a CREATE TABLE for `artifacts`."""
        assert _table_exists_in_ddl(_DDL, "artifacts"), (
            "CREATE TABLE IF NOT EXISTS artifacts(...) not found in _DDL"
        )

    def test_artifacts_ddl_is_valid_sqlite(self):
        """The entire _DDL MUST be executable against an in-memory SQLite database."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.close()  # no exception means DDL is valid

    def test_artifacts_table_has_id_column(self):
        """artifacts.id MUST be defined (TEXT PRIMARY KEY)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "id" in cols, f"Column 'id' not found; got: {cols}"

    def test_artifacts_table_has_run_id_column(self):
        """artifacts.run_id MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "run_id" in cols, f"Column 'run_id' not found; got: {cols}"

    def test_artifacts_table_has_stage_column(self):
        """artifacts.stage MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "stage" in cols, f"Column 'stage' not found; got: {cols}"

    def test_artifacts_table_has_kind_column(self):
        """artifacts.kind MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "kind" in cols, f"Column 'kind' not found; got: {cols}"

    def test_artifacts_table_has_content_hash_column(self):
        """artifacts.content_hash MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "content_hash" in cols, f"Column 'content_hash' not found; got: {cols}"

    def test_artifacts_table_has_blob_column(self):
        """artifacts.blob MUST be defined (BLOB)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "blob" in cols, f"Column 'blob' not found; got: {cols}"

    def test_artifacts_table_has_created_ts_column(self):
        """artifacts.created_ts MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        assert "created_ts" in cols, f"Column 'created_ts' not found; got: {cols}"

    def test_artifacts_table_has_exactly_seven_columns(self):
        """artifacts table MUST have exactly 7 columns: id, run_id, stage, kind,
        content_hash, blob, created_ts."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "artifacts")
        conn.close()
        expected = {"id", "run_id", "stage", "kind", "content_hash", "blob", "created_ts"}
        actual = set(cols)
        assert actual == expected, (
            f"artifacts columns mismatch.\n  expected: {sorted(expected)}\n  got:      {sorted(actual)}"
        )

    def test_artifacts_id_is_primary_key(self):
        """artifacts.id MUST be the PRIMARY KEY."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute("PRAGMA table_info(artifacts)")
        rows = cursor.fetchall()
        conn.close()
        # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
        pk_cols = [row[1] for row in rows if row[5] == 1]
        assert "id" in pk_cols, (
            f"artifacts.id is not PRIMARY KEY; pk columns are: {pk_cols}"
        )

    def test_artifacts_can_insert_and_select_row(self):
        """Basic smoke test: insert a row into artifacts and SELECT it back."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.execute(
            "INSERT INTO artifacts (id, run_id, stage, kind, content_hash, blob, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("art-001", "run-001", "implement", "spec_file", "abc123", b"blob data", "2026-04-02T00:00:00"),
        )
        conn.commit()
        cursor = conn.execute("SELECT * FROM artifacts WHERE id = 'art-001'")
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "Inserted artifact row was not found"

    def test_artifacts_blob_column_accepts_none(self):
        """artifacts.blob MUST accept NULL (optional binary content)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.execute(
            "INSERT INTO artifacts (id, run_id, stage, kind, content_hash, blob, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("art-null-blob", "run-001", "spec", "note", "hash001", None, "2026-04-02T00:00:00"),
        )
        conn.commit()
        cursor = conn.execute("SELECT blob FROM artifacts WHERE id = 'art-null-blob'")
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None


# ===========================================================================
# 3. DDL string — lvl_events table presence and columns
# ===========================================================================


class TestLvlEventsTableDDL:
    """The `lvl_events` table MUST be present in _DDL with all required columns."""

    def test_lvl_events_table_exists_in_ddl(self):
        """DDL MUST contain a CREATE TABLE for `lvl_events`."""
        assert _table_exists_in_ddl(_DDL, "lvl_events"), (
            "CREATE TABLE IF NOT EXISTS lvl_events(...) not found in _DDL"
        )

    def test_lvl_events_table_has_id_column(self):
        """lvl_events.id MUST be defined (INTEGER PRIMARY KEY AUTOINCREMENT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "id" in cols, f"Column 'id' not found; got: {cols}"

    def test_lvl_events_table_has_run_id_column(self):
        """lvl_events.run_id MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "run_id" in cols, f"Column 'run_id' not found; got: {cols}"

    def test_lvl_events_table_has_stage_column(self):
        """lvl_events.stage MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "stage" in cols, f"Column 'stage' not found; got: {cols}"

    def test_lvl_events_table_has_event_type_column(self):
        """lvl_events.event_type MUST be defined (TEXT)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "event_type" in cols, f"Column 'event_type' not found; got: {cols}"

    def test_lvl_events_table_has_payload_column(self):
        """lvl_events.payload MUST be defined (TEXT — JSON blob)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "payload" in cols, f"Column 'payload' not found; got: {cols}"

    def test_lvl_events_table_has_ts_column(self):
        """lvl_events.ts MUST be defined (TEXT — ISO timestamp)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        assert "ts" in cols, f"Column 'ts' not found; got: {cols}"

    def test_lvl_events_table_has_exactly_six_columns(self):
        """lvl_events MUST have exactly 6 columns: id, run_id, stage, event_type,
        payload, ts."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cols = _get_table_columns(conn, "lvl_events")
        conn.close()
        expected = {"id", "run_id", "stage", "event_type", "payload", "ts"}
        actual = set(cols)
        assert actual == expected, (
            f"lvl_events columns mismatch.\n  expected: {sorted(expected)}\n  got:      {sorted(actual)}"
        )

    def test_lvl_events_id_is_primary_key(self):
        """lvl_events.id MUST be the PRIMARY KEY."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute("PRAGMA table_info(lvl_events)")
        rows = cursor.fetchall()
        conn.close()
        pk_cols = [row[1] for row in rows if row[5] == 1]
        assert "id" in pk_cols, (
            f"lvl_events.id is not PRIMARY KEY; pk columns are: {pk_cols}"
        )

    def test_lvl_events_id_is_autoincrement(self):
        """lvl_events.id MUST autoincrement — inserting without id MUST assign one."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.execute(
            "INSERT INTO lvl_events (run_id, stage, event_type, payload, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("run-001", "implement", "stage_complete", '{"detail": "ok"}', "2026-04-02T00:00:00"),
        )
        conn.execute(
            "INSERT INTO lvl_events (run_id, stage, event_type, payload, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("run-001", "acceptance", "stage_complete", '{"detail": "done"}', "2026-04-02T00:01:00"),
        )
        conn.commit()
        cursor = conn.execute("SELECT id FROM lvl_events ORDER BY id")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert len(ids) == 2
        assert ids[0] < ids[1], "AUTOINCREMENT ids must be strictly increasing"

    def test_lvl_events_can_insert_and_select_row(self):
        """Basic smoke test: insert a row into lvl_events and SELECT it back."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.execute(
            "INSERT INTO lvl_events (run_id, stage, event_type, payload, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("run-42", "spec", "task_blocked", '{}', "2026-04-02T12:00:00"),
        )
        conn.commit()
        cursor = conn.execute("SELECT * FROM lvl_events WHERE run_id = 'run-42'")
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "Inserted lvl_events row was not found"

    def test_lvl_events_payload_accepts_none(self):
        """lvl_events.payload MUST accept NULL (optional JSON payload)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        conn.execute(
            "INSERT INTO lvl_events (run_id, stage, event_type, payload, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("run-null", "plan", "monitor_pause", None, "2026-04-02T00:00:00"),
        )
        conn.commit()
        cursor = conn.execute("SELECT payload FROM lvl_events WHERE run_id = 'run-null'")
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None


# ===========================================================================
# 4. Indexes on run_id for both new tables
# ===========================================================================


class TestRunIdIndexes:
    """Both new tables MUST have an index on run_id for efficient querying."""

    def test_artifacts_has_run_id_index_in_ddl(self):
        """_DDL MUST define a CREATE INDEX on artifacts(run_id)."""
        assert _index_exists_in_ddl(_DDL, "artifacts", "run_id"), (
            "No CREATE INDEX ... ON artifacts(run_id) found in _DDL"
        )

    def test_lvl_events_has_run_id_index_in_ddl(self):
        """_DDL MUST define a CREATE INDEX on lvl_events(run_id)."""
        assert _index_exists_in_ddl(_DDL, "lvl_events", "run_id"), (
            "No CREATE INDEX ... ON lvl_events(run_id) found in _DDL"
        )

    def test_artifacts_run_id_index_is_applied_in_sqlite(self):
        """The run_id index on artifacts MUST actually be created in SQLite."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='artifacts'"
        )
        index_names = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert len(index_names) >= 1, (
            f"No indexes found on artifacts table; got: {index_names}"
        )

    def test_lvl_events_run_id_index_is_applied_in_sqlite(self):
        """The run_id index on lvl_events MUST actually be created in SQLite."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='lvl_events'"
        )
        index_names = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert len(index_names) >= 1, (
            f"No indexes found on lvl_events table; got: {index_names}"
        )


# ===========================================================================
# 5. Existing tables are still present in the schema
# ===========================================================================


class TestExistingTablesPreserved:
    """All existing v1/v2 tables MUST still be present after the v3 upgrade."""

    _EXPECTED_TABLES = [
        "tasks",
        "reviews",
        "evidence",
        "stage_progress",
        "step_status",
        "lvl",
        "checkpoints",
        "settings",
        "pipelines",
        "config_cache",
        "task_groups",
    ]

    @pytest.mark.parametrize("table_name", _EXPECTED_TABLES)
    def test_existing_table_still_in_ddl(self, table_name: str):
        """Table '{table_name}' MUST still be present in _DDL after v3 upgrade."""
        assert _table_exists_in_ddl(_DDL, table_name), (
            f"Existing table '{table_name}' was removed from _DDL during v3 upgrade"
        )

    @pytest.mark.parametrize("table_name", _EXPECTED_TABLES)
    def test_existing_table_created_in_sqlite(self, table_name: str):
        """Table '{table_name}' MUST be created when the DDL is applied to SQLite."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None, (
            f"Table '{table_name}' was not created by _DDL in SQLite"
        )


# ===========================================================================
# 6. ArtifactRecord dataclass
# ===========================================================================


class TestArtifactRecord:
    """ArtifactRecord MUST be a frozen dataclass with fields matching the
    artifacts table columns."""

    def _make_record(self, **overrides) -> ArtifactRecord:
        defaults = dict(
            id="art-001",
            run_id="run-abc",
            stage="implement",
            kind="spec_file",
            content_hash="sha256:abc123",
            blob=b"binary content",
            created_ts="2026-04-02T12:00:00+00:00",
        )
        defaults.update(overrides)
        return ArtifactRecord(**defaults)

    def test_artifact_record_is_dataclass(self):
        """ArtifactRecord MUST be a dataclass."""
        assert dataclasses.is_dataclass(ArtifactRecord)

    def test_artifact_record_is_frozen(self):
        """ArtifactRecord MUST be a frozen dataclass — mutation MUST raise."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.id = "mutated"  # type: ignore[misc]

    def test_artifact_record_stores_id(self):
        """ArtifactRecord.id MUST store the provided value."""
        record = self._make_record(id="art-xyz")
        assert record.id == "art-xyz"

    def test_artifact_record_stores_run_id(self):
        """ArtifactRecord.run_id MUST store the provided value."""
        record = self._make_record(run_id="run-999")
        assert record.run_id == "run-999"

    def test_artifact_record_stores_stage(self):
        """ArtifactRecord.stage MUST store the provided value."""
        record = self._make_record(stage="acceptance")
        assert record.stage == "acceptance"

    def test_artifact_record_stores_kind(self):
        """ArtifactRecord.kind MUST store the provided value."""
        record = self._make_record(kind="test_output")
        assert record.kind == "test_output"

    def test_artifact_record_stores_content_hash(self):
        """ArtifactRecord.content_hash MUST store the provided value."""
        record = self._make_record(content_hash="sha256:deadbeef")
        assert record.content_hash == "sha256:deadbeef"

    def test_artifact_record_stores_blob_bytes(self):
        """ArtifactRecord.blob MUST store binary (bytes) content."""
        payload = b"\x00\x01\x02\xff"
        record = self._make_record(blob=payload)
        assert record.blob == payload

    def test_artifact_record_blob_can_be_none(self):
        """ArtifactRecord.blob MUST accept None (optional)."""
        record = self._make_record(blob=None)
        assert record.blob is None

    def test_artifact_record_stores_created_ts(self):
        """ArtifactRecord.created_ts MUST store the ISO timestamp string."""
        record = self._make_record(created_ts="2026-01-01T00:00:00Z")
        assert record.stage == "implement" or record.created_ts == "2026-01-01T00:00:00Z"
        record2 = self._make_record(created_ts="2026-01-01T00:00:00Z")
        assert record2.created_ts == "2026-01-01T00:00:00Z"

    def test_artifact_record_has_seven_fields(self):
        """ArtifactRecord MUST have exactly 7 fields matching the artifacts table."""
        field_names = {f.name for f in dataclasses.fields(ArtifactRecord)}
        expected = {"id", "run_id", "stage", "kind", "content_hash", "blob", "created_ts"}
        assert field_names == expected, (
            f"ArtifactRecord field mismatch.\n  expected: {sorted(expected)}\n  got:      {sorted(field_names)}"
        )

    def test_artifact_record_equality(self):
        """Two ArtifactRecord instances with same data MUST be equal."""
        r1 = self._make_record()
        r2 = self._make_record()
        assert r1 == r2

    def test_artifact_record_inequality_on_id(self):
        """Two ArtifactRecord instances differing only in id MUST NOT be equal."""
        r1 = self._make_record(id="art-001")
        r2 = self._make_record(id="art-002")
        assert r1 != r2

    def test_artifact_record_run_id_mutation_raises(self):
        """Frozen guard: run_id MUST NOT be mutable."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.run_id = "mutated"  # type: ignore[misc]

    def test_artifact_record_blob_mutation_raises(self):
        """Frozen guard: blob MUST NOT be mutable."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.blob = b"new"  # type: ignore[misc]

    def test_artifact_record_empty_blob(self):
        """ArtifactRecord.blob MUST accept empty bytes."""
        record = self._make_record(blob=b"")
        assert record.blob == b""

    def test_artifact_record_unicode_kind(self):
        """ArtifactRecord.kind MUST accept Unicode strings (including emojis)."""
        record = self._make_record(kind="spec\u2014file\U0001F4C4")
        assert "\u2014" in record.kind

    def test_artifact_record_large_content_hash(self):
        """ArtifactRecord.content_hash MUST accept a full SHA-256 hex string (64 chars)."""
        sha256 = "a" * 64
        record = self._make_record(content_hash=sha256)
        assert record.content_hash == sha256

    def test_artifact_record_special_chars_in_run_id(self):
        """ArtifactRecord.run_id MUST accept run IDs with hyphens and underscores."""
        record = self._make_record(run_id="run-2026_04_02-abc123")
        assert record.run_id == "run-2026_04_02-abc123"


# ===========================================================================
# 7. LvlEventRecord dataclass
# ===========================================================================


class TestLvlEventRecord:
    """LvlEventRecord MUST be a frozen dataclass with fields matching the
    lvl_events table columns."""

    def _make_record(self, **overrides) -> LvlEventRecord:
        defaults = dict(
            id=1,
            run_id="run-abc",
            stage="plan",
            event_type="stage_complete",
            payload='{"detail": "all tasks done"}',
            ts="2026-04-02T12:00:00+00:00",
        )
        defaults.update(overrides)
        return LvlEventRecord(**defaults)

    def test_lvl_event_record_is_dataclass(self):
        """LvlEventRecord MUST be a dataclass."""
        assert dataclasses.is_dataclass(LvlEventRecord)

    def test_lvl_event_record_is_frozen(self):
        """LvlEventRecord MUST be a frozen dataclass — mutation MUST raise."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.id = 999  # type: ignore[misc]

    def test_lvl_event_record_stores_id(self):
        """LvlEventRecord.id MUST store the provided integer."""
        record = self._make_record(id=42)
        assert record.id == 42

    def test_lvl_event_record_stores_run_id(self):
        """LvlEventRecord.run_id MUST store the provided value."""
        record = self._make_record(run_id="run-xyz")
        assert record.run_id == "run-xyz"

    def test_lvl_event_record_stores_stage(self):
        """LvlEventRecord.stage MUST store the provided value."""
        record = self._make_record(stage="implement")
        assert record.stage == "implement"

    def test_lvl_event_record_stores_event_type(self):
        """LvlEventRecord.event_type MUST store the provided value."""
        record = self._make_record(event_type="task_blocked")
        assert record.event_type == "task_blocked"

    def test_lvl_event_record_stores_payload(self):
        """LvlEventRecord.payload MUST store the provided JSON string."""
        payload = '{"task_id": "T001", "reason": "test failure"}'
        record = self._make_record(payload=payload)
        assert record.payload == payload

    def test_lvl_event_record_payload_can_be_none(self):
        """LvlEventRecord.payload MUST accept None (optional JSON payload)."""
        record = self._make_record(payload=None)
        assert record.payload is None

    def test_lvl_event_record_stores_ts(self):
        """LvlEventRecord.ts MUST store the ISO timestamp string."""
        record = self._make_record(ts="2026-04-02T15:30:00Z")
        assert record.ts == "2026-04-02T15:30:00Z"

    def test_lvl_event_record_has_six_fields(self):
        """LvlEventRecord MUST have exactly 6 fields matching the lvl_events table."""
        field_names = {f.name for f in dataclasses.fields(LvlEventRecord)}
        expected = {"id", "run_id", "stage", "event_type", "payload", "ts"}
        assert field_names == expected, (
            f"LvlEventRecord field mismatch.\n  expected: {sorted(expected)}\n  got:      {sorted(field_names)}"
        )

    def test_lvl_event_record_equality(self):
        """Two LvlEventRecord instances with same data MUST be equal."""
        r1 = self._make_record()
        r2 = self._make_record()
        assert r1 == r2

    def test_lvl_event_record_inequality_on_id(self):
        """Two LvlEventRecord instances differing only in id MUST NOT be equal."""
        r1 = self._make_record(id=1)
        r2 = self._make_record(id=2)
        assert r1 != r2

    def test_lvl_event_record_run_id_mutation_raises(self):
        """Frozen guard: run_id MUST NOT be mutable."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.run_id = "mutated"  # type: ignore[misc]

    def test_lvl_event_record_ts_mutation_raises(self):
        """Frozen guard: ts MUST NOT be mutable."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.ts = "mutated"  # type: ignore[misc]

    def test_lvl_event_record_id_is_integer(self):
        """LvlEventRecord.id MUST be an integer (from AUTOINCREMENT PK)."""
        record = self._make_record(id=7)
        assert isinstance(record.id, int)

    def test_lvl_event_record_event_type_mutation_raises(self):
        """Frozen guard: event_type MUST NOT be mutable."""
        record = self._make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            record.event_type = "mutated"  # type: ignore[misc]

    def test_lvl_event_record_empty_payload(self):
        """LvlEventRecord.payload MUST accept an empty JSON object string."""
        record = self._make_record(payload="{}")
        assert record.payload == "{}"

    def test_lvl_event_record_large_payload(self):
        """LvlEventRecord.payload MUST accept large JSON payloads (>10k chars)."""
        large_payload = '{"data": "' + "x" * 10000 + '"}'
        record = self._make_record(payload=large_payload)
        assert len(record.payload) > 10000

    def test_lvl_event_record_all_stage_values(self):
        """LvlEventRecord.stage MUST accept all four pipeline stage strings."""
        for stage_val in ("spec", "plan", "implement", "acceptance"):
            record = self._make_record(stage=stage_val)
            assert record.stage == stage_val

    def test_lvl_event_record_special_chars_in_event_type(self):
        """LvlEventRecord.event_type MUST accept event type strings with underscores."""
        record = self._make_record(event_type="monitor_health_check_triggered")
        assert record.event_type == "monitor_health_check_triggered"


# ===========================================================================
# 8. DDL completeness — both new tables appear alongside existing ones
# ===========================================================================


class TestDDLCompleteness:
    """Holistic check: _DDL MUST define both new tables and all existing ones,
    and must be fully executable by SQLite."""

    def test_ddl_creates_13_tables_minimum(self):
        """_DDL MUST create at least 13 tables (11 existing + 2 new)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert len(tables) >= 13, (
            f"Expected at least 13 tables, got {len(tables)}: {tables}"
        )

    def test_ddl_creates_artifacts_and_lvl_events(self):
        """Both `artifacts` and `lvl_events` MUST be created by _DDL."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "artifacts" in tables, f"'artifacts' table not in {tables}"
        assert "lvl_events" in tables, f"'lvl_events' table not in {tables}"

    def test_ddl_string_is_not_empty(self):
        """_DDL MUST be a non-empty string."""
        assert isinstance(_DDL, str)
        assert len(_DDL.strip()) > 0

    def test_ddl_is_idempotent(self):
        """Applying _DDL twice to the same database MUST NOT raise (IF NOT EXISTS)."""
        conn = _apply_ddl_to_memory_db(_DDL)
        # Apply the same DDL a second time — should be idempotent
        conn.executescript(_DDL)
        conn.commit()
        conn.close()  # no exception = idempotent

    def test_new_tables_do_not_shadow_existing_lvl_table(self):
        """The new `lvl_events` table MUST NOT replace the existing `lvl` table."""
        conn = _apply_ddl_to_memory_db(_DDL)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('lvl', 'lvl_events')"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "lvl" in tables, "Existing 'lvl' table was removed by v3 upgrade"
        assert "lvl_events" in tables, "New 'lvl_events' table was not added"
        assert len(tables) == 2, f"Expected both 'lvl' and 'lvl_events', got: {tables}"
