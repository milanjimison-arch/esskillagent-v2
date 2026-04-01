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


class Store:
    """SQLite store stub — raises NotImplementedError on all operations."""

    def __init__(self, db_path: str) -> None:
        raise NotImplementedError

    async def __aenter__(self) -> "Store":
        raise NotImplementedError

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        raise NotImplementedError

    async def initialize(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_pipeline(self, pipeline_id: str) -> dict | None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_task(self, task_id: str) -> dict | None:
        raise NotImplementedError

    async def list_tasks(self) -> list[dict]:
        raise NotImplementedError

    async def update_task_status(self, task_id: str, status: str) -> None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_stage_progress(
        self, pipeline_id: str, stage: str
    ) -> dict | None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def load_checkpoint(
        self, pipeline_id: str, stage: str, step: str
    ) -> dict | None:
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_reviews_for_task(self, task_id: str) -> list[dict]:
        raise NotImplementedError

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
        raise NotImplementedError

    async def list_evidence(
        self, pipeline_id: str
    ) -> list[dict]:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # settings                                                             #
    # ------------------------------------------------------------------ #

    async def set_setting(self, key: str, value: str) -> None:
        raise NotImplementedError

    async def get_setting(self, key: str) -> str | None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # config_cache                                                         #
    # ------------------------------------------------------------------ #

    async def cache_config(self, pipeline_id: str, config_json: str) -> None:
        raise NotImplementedError

    async def load_cached_config(self, pipeline_id: str) -> str | None:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # schema helpers                                                       #
    # ------------------------------------------------------------------ #

    async def get_schema_version(self) -> int:
        raise NotImplementedError

    def is_open(self) -> bool:
        raise NotImplementedError
