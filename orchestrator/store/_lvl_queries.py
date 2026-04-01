"""LVL audit log, event chain, and artifact lifecycle helpers for E+S Orchestrator v2."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from orchestrator.store.db import Store, now

_STAGES = ["spec", "plan", "implement", "acceptance"]


@dataclass(frozen=True)
class LvlLogRecord:
    id: int
    pipeline_id: str
    level: str
    message: str
    created_at: str
    detail: str | None = None


def _to_log(row: dict) -> LvlLogRecord:
    return LvlLogRecord(id=row["id"], pipeline_id=row["pipeline_id"], level=row["level"],
                        message=row["message"], detail=row.get("detail"), created_at=row["created_at"])


async def insert_lvl_log(store: Store, pipeline_id: str, level: str, message: str,
                         detail: str | None = None) -> LvlLogRecord:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not level: raise ValueError("level must not be empty")
    if not message: raise ValueError("message must not be empty")
    ts = now()
    async with store.execute(
        "INSERT INTO lvl (pipeline_id, level, message, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (pipeline_id, level, message, detail, ts),
    ) as cur:
        row_id = cur.lastrowid
    await store.commit()
    async with store.execute("SELECT * FROM lvl WHERE id = ?", (row_id,)) as cur:
        row = await cur.fetchone()
    return _to_log(dict(row))


async def list_lvl_logs(store: Store, pipeline_id: str) -> tuple[LvlLogRecord, ...]:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    async with store.execute(
        "SELECT * FROM lvl WHERE pipeline_id = ? ORDER BY id ASC", (pipeline_id,)
    ) as cur:
        rows = await cur.fetchall()
    return tuple(_to_log(dict(r)) for r in rows)


async def list_lvl_logs_by_level(store: Store, pipeline_id: str, level: str) -> tuple[LvlLogRecord, ...]:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not level: raise ValueError("level must not be empty")
    async with store.execute(
        "SELECT * FROM lvl WHERE pipeline_id = ? AND level = ? ORDER BY id ASC", (pipeline_id, level)
    ) as cur:
        rows = await cur.fetchall()
    return tuple(_to_log(dict(r)) for r in rows)


# ---------------------------------------------------------------------------
# LVL Event Chain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LvlEvent:
    event_id: str
    pipeline_id: str
    stage: str
    event_type: str
    payload: str
    prev_hash: str | None
    event_hash: str
    created_at: str


def _to_event(r: dict) -> LvlEvent:
    return LvlEvent(event_id=r["event_id"], pipeline_id=r["pipeline_id"], stage=r["stage"],
                    event_type=r["event_type"], payload=r["payload"], prev_hash=r["prev_hash"],
                    event_hash=r["event_hash"], created_at=r["created_at"])


def _event_hash(prev_hash: str | None, pipeline_id: str, stage: str,
                event_type: str, payload_json: str, created_at: str) -> str:
    raw = (prev_hash or "") + pipeline_id + stage + event_type + payload_json + created_at
    return hashlib.sha256(raw.encode()).hexdigest()


async def append_event(store: Store, pipeline_id: str, stage: str,
                       event_type: str, payload: dict) -> LvlEvent:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not stage: raise ValueError("stage must not be empty")
    if not event_type: raise ValueError("event_type must not be empty")
    latest = await get_latest_event(store, pipeline_id)
    prev_hash = latest.event_hash if latest else None
    event_id, payload_json, created_at = uuid.uuid4().hex[:12], json.dumps(payload, ensure_ascii=False), now()
    eh = _event_hash(prev_hash, pipeline_id, stage, event_type, payload_json, created_at)
    async with store.execute(
        "INSERT INTO pipeline_lvl_events (event_id,pipeline_id,stage,event_type,payload,prev_hash,event_hash,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (event_id, pipeline_id, stage, event_type, payload_json, prev_hash, eh, created_at),
    ):
        pass
    await store.commit()
    return LvlEvent(event_id=event_id, pipeline_id=pipeline_id, stage=stage, event_type=event_type,
                    payload=payload_json, prev_hash=prev_hash, event_hash=eh, created_at=created_at)


async def get_latest_event(store: Store, pipeline_id: str) -> LvlEvent | None:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    async with store.execute(
        "SELECT * FROM pipeline_lvl_events WHERE pipeline_id=? ORDER BY rowid DESC LIMIT 1", (pipeline_id,)
    ) as cur:
        row = await cur.fetchone()
    return _to_event(dict(row)) if row else None


async def verify_chain(store: Store, pipeline_id: str) -> bool:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    async with store.execute(
        "SELECT * FROM pipeline_lvl_events WHERE pipeline_id=? ORDER BY rowid ASC", (pipeline_id,)
    ) as cur:
        rows = await cur.fetchall()
    if not rows: return True
    prev: str | None = None
    for row in rows:
        r = dict(row)
        if r["prev_hash"] != prev: return False
        if r["event_hash"] != _event_hash(r["prev_hash"], r["pipeline_id"], r["stage"],
                                           r["event_type"], r["payload"], r["created_at"]):
            return False
        prev = r["event_hash"]
    return True


def verify_stage_invariant(from_stage: str, to_stage: str) -> bool:
    if not from_stage or from_stage not in _STAGES:
        raise ValueError(f"Unrecognised from_stage: {from_stage!r}")
    if not to_stage or to_stage not in _STAGES:
        raise ValueError(f"Unrecognised to_stage: {to_stage!r}")
    return _STAGES.index(to_stage) == _STAGES.index(from_stage) + 1


# ---------------------------------------------------------------------------
# Artifact lifecycle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    pipeline_id: str
    name: str
    stage: str
    file_path: str
    frozen_hash: str | None
    is_frozen: bool
    is_valid: bool
    created_at: str


def _to_artifact(r: dict) -> ArtifactRecord:
    return ArtifactRecord(artifact_id=r["artifact_id"], pipeline_id=r["pipeline_id"], name=r["name"],
                          stage=r["stage"], file_path=r["file_path"], frozen_hash=r["frozen_hash"],
                          is_frozen=bool(r["is_frozen"]), is_valid=bool(r["is_valid"]), created_at=r["created_at"])


async def _get_artifact(store: Store, pipeline_id: str, name: str) -> dict:
    async with store.execute(
        "SELECT * FROM pipeline_artifacts WHERE pipeline_id=? AND name=?", (pipeline_id, name)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise KeyError(f"Artifact {name!r} not found for pipeline {pipeline_id!r}")
    return dict(row)


async def register_artifact(store: Store, pipeline_id: str, name: str,
                             stage: str, file_path: str) -> ArtifactRecord:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not name: raise ValueError("name must not be empty")
    if not stage: raise ValueError("stage must not be empty")
    if not file_path: raise ValueError("file_path must not be empty")
    async with store.execute(
        "SELECT 1 FROM pipeline_artifacts WHERE pipeline_id=? AND name=?", (pipeline_id, name)
    ) as cur:
        if await cur.fetchone(): raise ValueError(f"Artifact {name!r} already exists")
    aid, ts = uuid.uuid4().hex[:12], now()
    async with store.execute(
        "INSERT INTO pipeline_artifacts (artifact_id,pipeline_id,name,stage,file_path,frozen_hash,is_frozen,is_valid,created_at) VALUES (?,?,?,?,?,NULL,0,1,?)",
        (aid, pipeline_id, name, stage, file_path, ts),
    ):
        pass
    await store.commit()
    return ArtifactRecord(artifact_id=aid, pipeline_id=pipeline_id, name=name, stage=stage,
                          file_path=file_path, frozen_hash=None, is_frozen=False, is_valid=True, created_at=ts)


async def freeze_artifact(store: Store, pipeline_id: str, name: str) -> ArtifactRecord:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not name: raise ValueError("name must not be empty")
    row = await _get_artifact(store, pipeline_id, name)
    fp = Path(row["file_path"])
    if not fp.exists(): raise FileNotFoundError(f"Artifact file not found: {fp}")
    h = hashlib.sha256(fp.read_bytes()).hexdigest()
    async with store.execute(
        "UPDATE pipeline_artifacts SET frozen_hash=?,is_frozen=1 WHERE pipeline_id=? AND name=?",
        (h, pipeline_id, name),
    ):
        pass
    await store.commit()
    return _to_artifact({**row, "frozen_hash": h, "is_frozen": 1})


async def check_staleness(store: Store, pipeline_id: str, name: str) -> bool:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not name: raise ValueError("name must not be empty")
    row = await _get_artifact(store, pipeline_id, name)
    if not row["is_frozen"]: raise RuntimeError(f"Artifact {name!r} has not been frozen yet")
    fp = Path(row["file_path"])
    if not fp.exists(): raise FileNotFoundError(f"Artifact file not found: {fp}")
    return hashlib.sha256(fp.read_bytes()).hexdigest() != row["frozen_hash"]


async def cascade_invalidate(store: Store, pipeline_id: str, name: str) -> tuple[ArtifactRecord, ...]:
    if not pipeline_id: raise ValueError("pipeline_id must not be empty")
    if not name: raise ValueError("name must not be empty")
    target = await _get_artifact(store, pipeline_id, name)
    tidx = _STAGES.index(target["stage"]) if target["stage"] in _STAGES else -1
    async with store.execute(
        "SELECT * FROM pipeline_artifacts WHERE pipeline_id=?", (pipeline_id,)
    ) as cur:
        all_rows = [dict(r) for r in await cur.fetchall()]
    to_inv = [r for r in all_rows if r["stage"] in _STAGES and _STAGES.index(r["stage"]) >= tidx]
    for r in to_inv:
        async with store.execute(
            "UPDATE pipeline_artifacts SET is_valid=0 WHERE artifact_id=?", (r["artifact_id"],)
        ):
            pass
    await store.commit()
    return tuple(_to_artifact({**r, "is_valid": 0}) for r in to_inv)
