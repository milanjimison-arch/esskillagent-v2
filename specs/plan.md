# Implementation Plan: E+S Orchestrator v2 -- Autonomous Four-Stage TDD Orchestration

**Branch**: `main` | **Date**: 2026-04-02 | **Spec**: `specs/spec.md`
**Input**: Feature specification from `specs/spec.md`

---

## Summary

E+S Orchestrator v2 is a complete rewrite of the v1 orchestrator, transforming it from a sequential agent-runner into an autonomous four-stage TDD pipeline (spec, plan, implement, acceptance) with perception, decision-making, feedback loops, and self-correction capabilities. The orchestrator drives each stage autonomously, managing AI agents, TDD cycles, three-way parallel reviews, checkpoint/resume, and BLOCKED-task self-correction -- all built on Python 3.12+ with asyncio, SQLite persistence, and the Claude Agent SDK.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: Claude Agent SDK (with CLI fallback), PyYAML, aiosqlite
**Storage**: SQLite (`.workflow/workflow.db`), must maintain v1 schema compatibility for existing tables
**Testing**: pytest with fixtures, 80%+ overall coverage, 90%+ for `checks/`, 95%+ for `tdd/parser.py`
**Target Platform**: Windows / Linux / macOS (developer workstations)
**Project Type**: CLI tool / orchestration engine
**Performance Goals**: Pipeline completion within reasonable time bounds; individual stage timeout configurable via `stage_timeout`
**Constraints**: engine.py < 300 lines, all modules < 450 lines, frozen dataclasses for all DTOs, no bare `except`
**Scale/Scope**: Single developer per pipeline run; 5-50 tasks per implement stage; 14 registered agents

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Four-Stage Pipeline Integrity | PASS | Design preserves strict spec->plan->implement->acceptance order; skip only via explicit `skip_stages` config |
| II. Test-First Discipline | PASS | TDD runner enforces separate RED/GREEN phases with distinct prompt templates |
| III. Modular Architecture | PASS | Engine < 300 lines; all modules < 450 lines; PipelineMonitor is a separate module, not embedded in engine |
| IV. Strategy Pattern for Test Verification | PASS | CheckStrategy ABC already implemented; LocalCheckStrategy and CICheckStrategy both conform |
| V. Contract Alignment | PASS | Task format em-dash convention enforced by parser + contract test |
| VI. Resilient External Operations | PASS | Retry with backoff for network ops; structured error capture; timeout handling |
| VII. Immutable Data and Type Safety | PASS | All DTOs use `@dataclass(frozen=True)`; full type annotations; no bare except |

No violations detected. Complexity Tracking section not required.

---

## Architecture Overview

### System Architecture Diagram

```
                          CLI (cli.py)
                              |
                              v
                     PipelineEngine (engine.py)
                     [< 300 lines, flow only]
                              |
          +--------+----------+----------+---------+
          |        |          |          |         |
          v        v          v          v         v
       SpecStage PlanStage ImplementStage AcceptanceStage
       (stages/) (stages/)  (stages/)     (stages/)
          |        |          |               |
          v        v          v               v
     AgentAdapter  AgentAdapter  TDDRunner   AgentAdapter
     (agents/)     (agents/)    (tdd/)       (agents/)
                                   |
                                   v
                             CheckStrategy
                             (checks/)
                              |       |
                              v       v
                           Local     CI

     ReviewPipeline (review/)        PipelineMonitor (monitor.py)
     [code + security + brooks]      [BLOCKED ratio, convergence,
                                      stale cascade detection]

     Store (store/)                  LVL Event Stream (store/lvl)
     [SQLite persistence]            [Decision support + audit]
```

### Key Design Decisions

1. **PipelineMonitor as code module** (not an LLM agent): Aggregates signals at stage transitions and task batch completions; detects global anomalies (BLOCKED ratio > 50%, stale cascades); produces actionable recommendations written to LVL.

2. **Dual-trigger for clarify/research**: Both agent self-report (`[NC:]`, `[NR:]` markers) and orchestrator heuristic scanning (question marks, TBD/TODO keywords, uncertainty expressions) can trigger clarify/research agents.

3. **Stage atomicity with task-level checkpointing**: Spec, plan, and acceptance are atomic (re-run from start on resume). Implement supports task-level resume via per-task status in the store.

4. **LVL as decision substrate**: LVL events are queried at runtime for convergence detection, resume-point determination, and pre-condition validation -- not just post-hoc auditing.

---

## Project Structure

### Documentation (this feature)

```text
specs/
├── plan.md              # This file
├── data-model.md        # Phase 1 output: entity definitions
├── quickstart.md        # Phase 1 output: getting started guide
├── constitution.md      # Governance document
├── spec.md              # Feature specification
└── checklists/
    └── requirements.md  # Requirements checklist
```

### Source Code (repository root)

```text
orchestrator/
├── cli.py              # CLI entry point (run/resume/retry/status)
├── config.py           # Layered config: defaults.yaml -> brownfield.yaml -> .orchestrator.yaml -> env
├── engine.py           # Pipeline flow controller (< 300 lines, no stage logic)
├── monitor.py          # [NEW] PipelineMonitor: BLOCKED ratio, convergence, stale cascade
├── perception.py       # [NEW] Output scanning: NC/NR markers, uncertainty heuristics
├── stages/
│   ├── base.py         # StageABC with review gate template method
│   ├── spec.py         # Spec stage: spec-writer agent + clarify trigger
│   ├── plan.py         # Plan stage: planner agent + research trigger
│   ├── implement.py    # Implement stage: TDD cycles + task-level checkpoint
│   └── acceptance.py   # Acceptance stage: traceability verification
├── tdd/
│   ├── parser.py       # Task format parser (em-dash convention)
│   ├── runner.py       # TDD job runner: RED -> GREEN with parallel batches
│   └── validator.py    # Task validation (parallel file overlap, format)
├── review/
│   └── pipeline.py     # Three-way parallel review + auto-fix loop + gap detection
├── checks/
│   ├── base.py         # CheckStrategy ABC
│   ├── local.py        # LocalCheckStrategy
│   └── ci.py           # CICheckStrategy (stack-scoped job evaluation)
├── agents/
│   ├── adapter.py      # Claude SDK / CLI dual adapter
│   └── registry.py     # Agent registration and capability lookup
├── store/
│   ├── db.py           # SQLite connection management
│   ├── models.py       # Frozen dataclass DTOs and enums
│   ├── queries.py      # CRUD query helpers
│   ├── _schema.py      # DDL schema
│   └── _lvl_queries.py # LVL audit log queries
├── ui/
│   └── wave.py         # Optional Wave dashboard (not imported by core)
└── defaults.yaml       # Global default configuration

tests/
├── contract/
│   └── test_task_format.py   # Parser/generator alignment contract test
├── integration/              # [NEW] End-to-end pipeline tests
│   ├── test_full_pipeline.py
│   ├── test_resume.py
│   └── test_retry.py
└── unit/
    ├── agents/
    ├── checks/
    ├── config/
    ├── review/
    ├── stages/
    ├── store/
    ├── tdd/
    ├── test_cli.py
    ├── test_engine.py
    ├── test_monitor.py       # [NEW]
    └── test_perception.py    # [NEW]
```

**Structure Decision**: Single-project layout (Option 1). The orchestrator is a Python CLI tool with no frontend/backend split. All source lives under `orchestrator/`, all tests under `tests/`.

---

## Phased Implementation Plan

### Phase 0: Infrastructure and Foundation

**Goal**: Complete the infrastructure layer needed by all subsequent phases.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P0-1 | Add `conftest.py` with shared fixtures (tmp_db, mock_adapter, mock_store) | None | P0 |
| P0-2 | Implement `Store` async context manager and full CRUD in `store/db.py` | None | P0 |
| P0-3 | Add `pipelines` table queries: create_pipeline, get_pipeline, update_pipeline_stage | P0-2 | P0 |
| P0-4 | Implement LVL event insertion and querying with decision-support filters | P0-2 | P0 |
| P0-5 | Add `stage_progress` table queries: upsert_stage_progress, get_stage_progress | P0-2 | P0 |
| P0-6 | Add `checkpoints` table queries: save_checkpoint, get_latest_checkpoint | P0-2 | P0 |

### Phase 1: Perception Layer

**Goal**: Enable the orchestrator to perceive agent outputs and detect clarification/research needs.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P1-1 | Create `perception.py`: NC/NR marker detection from agent output | None | P1 |
| P1-2 | Implement uncertainty heuristic scanner (question density, TBD/TODO, hedging expressions) | P1-1 | P1 |
| P1-3 | Wire perception into SpecStage: scan spec-writer output, trigger clarify agent when needed | P1-1, Phase 0 | P1 |
| P1-4 | Wire perception into PlanStage: scan planner output, trigger research agent when needed | P1-1, Phase 0 | P1 |

### Phase 2: Core Pipeline Stages

**Goal**: Implement the four stages with full review gates and checkpoint persistence.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P2-1 | Implement `SpecStage.run()`: invoke spec-writer agent, handle clarify trigger, freeze artifacts with content hash | Phase 1 | P1 |
| P2-2 | Implement `PlanStage.run()`: invoke planner agent, handle research trigger, generate tasks.md, freeze artifacts | Phase 1 | P1 |
| P2-3 | Implement `ImplementStage.run()`: parse tasks, run TDD cycles per task, task-level checkpointing | Phase 0 | P1 |
| P2-4 | Implement `AcceptanceStage.run()`: run traceability verification, produce acceptance report | Phase 0 | P1 |
| P2-5 | Integrate `StageABC.execute_with_gate()` with real review pipeline (three-way parallel) | P2-1..P2-4 | P1 |
| P2-6 | Implement artifact freezing: content hash computation and `stage_complete` event recording | Phase 0 | P1 |

### Phase 3: Decision-Making and Self-Correction

**Goal**: Add autonomous decision-making, BLOCKED handling, and the PipelineMonitor.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P3-1 | Create `monitor.py`: PipelineMonitor class with BLOCKED ratio detection | Phase 0 | P2 |
| P3-2 | Implement convergence detection: track fix-retry trends via LVL query | P3-1, P0-4 | P2 |
| P3-3 | Implement stale cascade detection: identify when BLOCKED tasks cause downstream blocks | P3-1 | P2 |
| P3-4 | Wire PipelineMonitor into engine: invoke at stage transitions and batch completions | P3-1, Phase 2 | P2 |
| P3-5 | Implement BLOCKED handling strategy: skip single BLOCKED, pause on > 50% BLOCKED ratio | P3-1, P2-3 | P2 |
| P3-6 | Implement self-correction suggestions: generate actionable recommendations to LVL | P3-1 | P2 |

### Phase 4: Resume, Retry, and Status

**Goal**: Implement checkpoint-based resume, targeted task retry, and status dashboard.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P4-1 | Implement `engine.resume()`: read last checkpoint, determine resume point, re-run from there | P0-6, Phase 2 | P1 |
| P4-2 | Implement stage atomicity: spec/plan/acceptance re-run from start; implement resumes from last completed task | P4-1 | P1 |
| P4-3 | Implement `engine.retry(task_id)`: validate task status is BLOCKED, re-run single TDD cycle | P2-3 | P2 |
| P4-4 | Implement `engine.status()`: aggregate pipeline state from store, display stage/task progress | Phase 0 | P2 |
| P4-5 | Error handling for resume with no checkpoint: clear error message | P4-1 | P1 |

### Phase 5: Agent Adaptation

**Goal**: Adapt agent prompt templates for v2 dual-trigger mechanism.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P5-1 | Update spec-writer prompt to include `[NC: ...]` marker guidance | Phase 1 | P2 |
| P5-2 | Update planner prompt to include `[NR: ...]` marker guidance | Phase 1 | P2 |
| P5-3 | Configure clarify agent with WebSearch + WebFetch tools | None | P2 |
| P5-4 | Configure research agent with WebSearch + WebFetch + Bash tools | None | P2 |
| P5-5 | Update RED/GREEN prompt templates with strict phase constraints per Constitution II | None | P1 |

### Phase 6: Integration Testing and Hardening

**Goal**: End-to-end tests and production hardening.

| Task | Description | Dependencies | Priority |
|------|-------------|--------------|----------|
| P6-1 | Integration test: full pipeline run with mocked agents | Phase 2, Phase 4 | P1 |
| P6-2 | Integration test: resume from interrupted implement stage | P4-1, P4-2 | P1 |
| P6-3 | Integration test: retry single BLOCKED task | P4-3 | P2 |
| P6-4 | Integration test: BLOCKED ratio triggers monitor pause | P3-5 | P2 |
| P6-5 | Add retry with backoff for all network/subprocess operations per Constitution VI | All phases | P1 |
| P6-6 | CI pipeline configuration (`.github/workflows/ci.yml` updates) | All phases | P2 |

---

## Dependency Graph

```
Phase 0 (Infrastructure)
    |
    +---> Phase 1 (Perception)
    |         |
    |         +---> Phase 2 (Core Stages)
    |                   |
    |                   +---> Phase 3 (Decision/Monitor)
    |                   |         |
    |                   +---> Phase 4 (Resume/Retry/Status)
    |                             |
    +---> Phase 5 (Agent Adaptation) [independent, can parallelize]
    |
    +---> Phase 6 (Integration Tests) [after Phase 2-4]
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent output format drift (parser/generator misalignment) | Medium | High | Contract test `test_task_format.py` runs on every CI build; parser validates format at startup |
| SQLite contention under parallel task execution | Low | Medium | Single asyncio event loop with `asyncio.Lock` in engine; store itself is lock-free, callers coordinate |
| Claude SDK API changes breaking adapter | Medium | Medium | CLI fallback path always available; adapter abstraction isolates SDK changes |
| Heuristic scanner false positives (unnecessary clarify/research triggers) | Medium | Low | Tunable thresholds in config; LVL logs all trigger decisions for post-hoc review |
| Implement stage taking too long with many tasks | Medium | Medium | Task-level checkpointing enables resume; configurable `stage_timeout` |
| BLOCKED cascade (one bad task blocks many downstream) | Medium | High | PipelineMonitor detects stale cascades; > 50% BLOCKED triggers pause + self-correction |
| v1 database schema incompatibility | Low | High | v2 only adds new tables; existing table schema preserved per Constitution constraint |

---

## New Modules Summary

| Module | Purpose | Lines (est.) | Key Interfaces |
|--------|---------|-------------|----------------|
| `orchestrator/monitor.py` | PipelineMonitor: global health observation | ~200 | `check_health(pipeline_id) -> HealthReport` |
| `orchestrator/perception.py` | Agent output scanning for NC/NR markers and uncertainty | ~150 | `scan_output(text) -> ScanResult` |
| `tests/integration/test_full_pipeline.py` | End-to-end pipeline integration test | ~200 | pytest fixtures with mocked agents |
| `tests/integration/test_resume.py` | Resume from checkpoint integration test | ~150 | pytest fixtures with pre-populated store |
| `tests/integration/test_retry.py` | Single task retry integration test | ~100 | pytest fixtures with BLOCKED task |
| `tests/conftest.py` | Shared test fixtures | ~100 | `tmp_db`, `mock_adapter`, `mock_store` |
