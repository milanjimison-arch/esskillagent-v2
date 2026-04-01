"""SQLite persistence layer for E+S Orchestrator v2.

FR-036: Store MUST use INSERT OR REPLACE (upsert) for task records.
FR-037: Store MUST maintain an audit trail via the evidence table.
FR-002: Store MUST support pipeline resume via checkpoint persistence.

This module is the stub skeleton. All public classes and functions are
defined with the correct signatures but raise NotImplementedError.
Tests in tests/unit/store/test_db.py assert concrete return values and
behaviours — they will fail (RED) until the full implementation is added.

Design rules (from pitfalls.md and CLAUDE.md):
- asyncio.Lock coordination is the CALLER's responsibility; the store itself
  is lock-free (see data-model.md "Write Coordination").
- WAL journal mode MUST be enabled on every new connection.
- Context-manager support (__aenter__ / __aexit__) is required.
- No bare except; explicit exception types only.
- Module < 400 lines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from orchestrator.store._schema import _DDL

_SCHEMA_VERSION = 2


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return now()


def now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Async SQLite store for E+S Orchestrator v2."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def __aenter__(self) -> "Store":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def initialize(self) -> None:
        """Open connection, enable WAL, create schema, set schema version."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_DDL)
        await self._conn.commit()
        version_val = await self.get_setting("schema_version")
        if version_val is None:
            await self.set_setting("schema_version", str(_SCHEMA_VERSION))

    async def close(self) -> None:
        """Close the connection idempotently."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    def is_open(self) -> bool:
        return self._conn is not None

    def execute(self, sql: str, params: Any = ()) -> Any:
        """Execute a SQL statement and return the cursor context manager."""
        return self._conn.execute(sql, params)

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    # pipelines                                                            #
    # ------------------------------------------------------------------ #

    async def upsert_pipeline(
        self,
        pipeline_id: str,
        project_path: str,
        requirement_path: str | None,
        current_stage: str,
        status: str,
    ) -> None:
        now = _now()
        await self._conn.execute(
            """INSERT INTO pipelines
               (pipeline_id, project_path, requirement_path, current_stage, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(pipeline_id) DO UPDATE SET
                 project_path=excluded.project_path,
                 requirement_path=excluded.requirement_path,
                 current_stage=excluded.current_stage,
                 status=excluded.status,
                 updated_at=excluded.updated_at""",
            (pipeline_id, project_path, requirement_path, current_stage, status, now, now),
        )
        await self._conn.commit()

    async def get_pipeline(self, pipeline_id: str) -> dict | None:
        async with self._conn.execute(
            "SELECT * FROM pipelines WHERE pipeline_id = ?", (pipeline_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # tasks                                                                #
    # ------------------------------------------------------------------ #

    async def upsert_task(
        self,
        task_id: str,
        description: str,
        file_path: str,
        parallel: bool,
        user_story: str | None,
        requirements: list[str],
        status: str,
        group_name: str,
    ) -> None:
        now = _now()
        reqs_json = json.dumps(requirements)
        parallel_int = int(bool(parallel))
        await self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, description, file_path, parallel, user_story, requirements,
                status, group_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, description, file_path, parallel_int, user_story,
             reqs_json, status, group_name, now, now),
        )
        await self._conn.commit()

    async def get_task(self, task_id: str) -> dict | None:
        async with self._conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["requirements"] = json.loads(result["requirements"]) if result["requirements"] else []
        return result

    async def list_tasks(self) -> list[dict]:
        async with self._conn.execute("SELECT * FROM tasks") as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["requirements"] = json.loads(d["requirements"]) if d["requirements"] else []
            result.append(d)
        return result

    async def update_task_status(self, task_id: str, status: str) -> None:
        now = _now()
        await self._conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (status, now, task_id),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    # stage_progress                                                       #
    # ------------------------------------------------------------------ #

    async def upsert_stage_progress(
        self,
        pipeline_id: str,
        stage: str,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        review_attempts: int = 0,
        checkpoint_data: str | None = None,
    ) -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO stage_progress
               (pipeline_id, stage, status, started_at, completed_at,
                review_attempts, checkpoint_data)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pipeline_id, stage, status, started_at, completed_at,
             review_attempts, checkpoint_data),
        )
        await self._conn.commit()

    async def get_stage_progress(self, pipeline_id: str, stage: str) -> dict | None:
        async with self._conn.execute(
            "SELECT * FROM stage_progress WHERE pipeline_id = ? AND stage = ?",
            (pipeline_id, stage),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # checkpoints                                                          #
    # ------------------------------------------------------------------ #

    async def save_checkpoint(
        self,
        pipeline_id: str,
        stage: str,
        step: str,
        state_json: str,
    ) -> None:
        now = _now()
        await self._conn.execute(
            """INSERT OR REPLACE INTO checkpoints
               (pipeline_id, stage, step, state_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (pipeline_id, stage, step, state_json, now),
        )
        await self._conn.commit()

    async def load_checkpoint(self, pipeline_id: str, stage: str, step: str) -> dict | None:
        async with self._conn.execute(
            "SELECT * FROM checkpoints WHERE pipeline_id = ? AND stage = ? AND step = ?",
            (pipeline_id, stage, step),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # reviews                                                              #
    # ------------------------------------------------------------------ #

    async def insert_review(
        self,
        review_id: str,
        task_id: str,
        review_type: str,
        passed: bool,
        findings: list[str],
        raw_output: str,
    ) -> None:
        now = _now()
        passed_int = int(bool(passed))
        findings_json = json.dumps(findings)
        await self._conn.execute(
            """INSERT INTO reviews
               (review_id, task_id, review_type, passed, findings, raw_output, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (review_id, task_id, review_type, passed_int, findings_json, raw_output, now),
        )
        await self._conn.commit()

    async def get_reviews_for_task(self, task_id: str) -> list[dict]:
        async with self._conn.execute(
            "SELECT * FROM reviews WHERE task_id = ?", (task_id,)
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["findings"] = json.loads(d["findings"]) if d["findings"] else []
            result.append(d)
        return result

    # ------------------------------------------------------------------ #
    # evidence                                                             #
    # ------------------------------------------------------------------ #

    async def insert_evidence(
        self,
        evidence_id: str,
        pipeline_id: str,
        stage: str,
        task_id: str | None,
        event_type: str,
        detail: str,
    ) -> None:
        now = _now()
        await self._conn.execute(
            """INSERT INTO evidence
               (evidence_id, pipeline_id, stage, task_id, event_type, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (evidence_id, pipeline_id, stage, task_id, event_type, detail, now),
        )
        await self._conn.commit()

    async def list_evidence(self, pipeline_id: str) -> list[dict]:
        async with self._conn.execute(
            "SELECT * FROM evidence WHERE pipeline_id = ?", (pipeline_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ #
    # settings                                                             #
    # ------------------------------------------------------------------ #

    async def set_setting(self, key: str, value: str) -> None:
        now = _now()
        await self._conn.execute(
            """INSERT OR REPLACE INTO settings (key, value, updated_at)
               VALUES (?, ?, ?)""",
            (key, value, now),
        )
        await self._conn.commit()

    async def get_setting(self, key: str) -> str | None:
        async with self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------ #
    # config_cache                                                         #
    # ------------------------------------------------------------------ #

    async def cache_config(self, pipeline_id: str, config_json: str) -> None:
        now = _now()
        await self._conn.execute(
            """INSERT OR REPLACE INTO config_cache (pipeline_id, config_json, created_at)
               VALUES (?, ?, ?)""",
            (pipeline_id, config_json, now),
        )
        await self._conn.commit()

    async def load_cached_config(self, pipeline_id: str) -> str | None:
        async with self._conn.execute(
            "SELECT config_json FROM config_cache WHERE pipeline_id = ?",
            (pipeline_id,),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------ #
    # schema helpers                                                       #
    # ------------------------------------------------------------------ #

    async def get_schema_version(self) -> int:
        value = await self.get_setting("schema_version")
        return int(value) if value is not None else 0
