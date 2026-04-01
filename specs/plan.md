# Implementation Plan: E+S Orchestrator v2 Complete Rewrite

**Branch**: `main` | **Date**: 2026-04-01 | **Spec**: [specs/spec.md](spec.md)
**Input**: Feature specification from `specs/spec.md`

## Summary

Complete rewrite of the E+S Orchestrator from v1 (6674 lines, 19 modules with tangled responsibilities) into a modular Python 3.12+ asyncio application. The v2 orchestrator manages AI agents through a four-stage TDD pipeline (spec, plan, implement, acceptance) with strategy-based polymorphism for test verification, layered configuration, parallel TDD with safety constraints, and contract alignment between task generators and parsers. Every design decision directly addresses a documented v1 pitfall.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: asyncio (stdlib), sqlite3 (stdlib), Claude Agent SDK (with CLI fallback), PyYAML (config loading), pytest (testing)
**Storage**: SQLite (`.workflow/workflow.db`) -- must read v1 schema without migration; new tables permitted
**Testing**: pytest with fixtures, monkeypatch mocking, contract tests; coverage targets 80%+ overall
**Target Platform**: Windows/Linux/macOS desktop (developer workstation)
**Project Type**: CLI tool / orchestrator
**Performance Goals**: N/A (batch orchestrator, not latency-sensitive; CI timeout configurable up to 2400s)
**Constraints**: Every module < 400 lines, engine.py < 300 lines; no bare except; frozen dataclasses for DTOs; asyncio single-threaded event loop
**Scale/Scope**: 14 agent directories, ~25 modules, ~4000-5000 lines estimated

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Single Responsibility per Module | PASS | Architecture splits engine.py into < 300 lines + stages/ sub-package; each module has one concern |
| II | Test-First Development | PASS | TDD RED-GREEN cycle is the core product feature (US2); coverage targets defined per module |
| III | Explicit Configuration over Implicit Behavior | PASS | Three-layer config (defaults.yaml, brownfield.yaml, .orchestrator.yaml) + env var overrides; no _is_small_project heuristic |
| IV | Strategy-Based Polymorphism | PASS | CheckStrategy ABC with LocalCheckStrategy and CICheckStrategy; no dict mutation |
| V | Contract Alignment | PASS | tasks.md em-dash format enforced by parser + generator + contract tests |
| VI | Resilient External Operations | PASS | Configurable retry + backoff for all network/subprocess ops; extensible stack registry via config |
| VII | Immutable Data and Type Safety | PASS | frozen dataclasses, type annotations on all public APIs, no bare except, exception chaining |

**Gate Result**: ALL PASS -- proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/
├── plan.md              # This file
├── research.md          # Phase 0 output (if needed)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
├── spec.md              # Feature specification
├── constitution.md      # Project constitution
├── checklists/
│   └── requirements.md  # Requirements checklist
└── tasks.md             # Phase 2 output (tasks step -- NOT created by plan step)
```

### Source Code (repository root)

```text
orchestrator/
├── __init__.py
├── cli.py              # Entry point: argparse + sub-commands (run/resume/retry/status)
├── config.py           # Layered configuration: defaults.yaml -> brownfield.yaml -> .orchestrator.yaml -> env
├── engine.py           # Stage flow control only (< 300 lines), asyncio.Lock owner
├── stages/
│   ├── __init__.py
│   ├── base.py         # Stage ABC: review gate + checkpoint + auto-fix loop
│   ├── spec.py         # Spec stage: constitution -> specify -> clarify -> review
│   ├── plan.py         # Plan stage: plan -> research -> tasks -> review
│   ├── implement.py    # Implement stage: TDD -> review -> push+CI
│   └── acceptance.py   # Acceptance stage: verification -> traceability -> review
├── tdd/
│   ├── __init__.py
│   ├── runner.py       # TDD task scheduler: serial + parallel (Phase A/B batch)
│   ├── parser.py       # tasks.md parser: em-dash format, strict validation
│   └── validator.py    # Parallel task validator: file_path conflict detection
├── review/
│   ├── __init__.py
│   └── pipeline.py     # Three-way parallel review + auto-fix + feature-gap detection
├── checks/
│   ├── __init__.py
│   ├── base.py         # CheckStrategy ABC: tests_must_fail, tests_must_pass
│   ├── local.py        # LocalCheckStrategy: subprocess test execution
│   ├── ci.py           # CICheckStrategy: commit -> push -> gh run watch + stack scoping
│   └── common.py       # Shared utilities: file_exists, coverage, verdict_parser
├── agents/
│   ├── __init__.py
│   ├── registry.py     # Agent registration + progressive knowledge loading
│   ├── adapter.py      # Claude SDK/CLI dual adapter
│   └── session.py      # Session continuation manager
├── store/
│   ├── __init__.py
│   ├── db.py           # SQLite connection + schema init (v1-compatible + new tables)
│   ├── models.py       # Frozen dataclass DTOs: Task, Review, Evidence, StageProgress, Checkpoint
│   └── queries.py      # CRUD operations returning model types
├── ui/                 # Optional -- no core module imports this
│   ├── __init__.py
│   ├── wave.py         # Wave panel (overview + stage detail)
│   └── notifier.py     # Desktop notifications
└── defaults.yaml       # Global default configuration

tests/
├── conftest.py         # Shared fixtures: mock store, mock agent, temp project dir
├── fixtures/
│   ├── workflow.db     # v1 database snapshot for schema compat tests
│   ├── tasks_valid.md  # Well-formed tasks.md samples
│   └── tasks_invalid.md# Malformed tasks.md samples
├── unit/
│   ├── test_config.py
│   ├── test_parser.py
│   ├── test_validator.py
│   ├── test_check_local.py
│   ├── test_check_ci.py
│   ├── test_store.py
│   └── test_registry.py
├── integration/
│   ├── test_tdd_runner.py
│   ├── test_review.py
│   └── test_resume.py
└── contract/
    └── test_task_format.py
```

**Structure Decision**: Single project layout. The orchestrator is a pure Python CLI tool with no frontend/backend split. All source code lives under `orchestrator/`, all tests under `tests/`. The `ui/` package is physically inside `orchestrator/` but architecturally isolated (no core imports).

---

## Phase 0: Research

All technical context items are resolved. The spec, constitution, requirement, and pitfalls documents provide comprehensive guidance. No NEEDS CLARIFICATION markers exist.

### Research Decisions

#### R-001: Async SQLite Access Pattern

- **Decision**: Use `asyncio.to_thread()` wrapping synchronous `sqlite3` calls, with `asyncio.Lock` owned by `engine.py` and injected into writing components.
- **Rationale**: Python's `sqlite3` module is not natively async. `aiosqlite` would add an external dependency. `asyncio.to_thread()` + lock is simpler and avoids the WAL-mode complexity. The lock-free store with caller-coordinated locking matches the constitution's design (Technical Constraints).
- **Alternatives considered**: `aiosqlite` library (rejected: unnecessary dependency for a single-writer workload); raw thread pool (rejected: more complex than `to_thread`).

#### R-002: CLI Framework

- **Decision**: Use `argparse` from stdlib with sub-commands.
- **Rationale**: The CLI has exactly four sub-commands (run, resume, retry, status) with minimal argument complexity. `argparse` is sufficient and avoids external dependencies. The orchestrator is invoked as `python -m orchestrator <sub-command>`.
- **Alternatives considered**: `click` (rejected: external dependency for minimal benefit); `typer` (rejected: adds typing magic that conflicts with explicit-over-implicit principle).

#### R-003: Configuration Merging Strategy

- **Decision**: Deep merge dictionaries with later sources overriding earlier ones. Use a simple recursive merge function. Environment variables override via `ORCHESTRATOR_` prefix with `__` as nested key separator (e.g., `ORCHESTRATOR_CI_TIMEOUT=900`).
- **Rationale**: YAML files naturally produce nested dicts. Deep merge preserves nested structures while allowing targeted overrides. The `ORCHESTRATOR_` prefix avoids collisions with system env vars.
- **Alternatives considered**: Flat key override only (rejected: loses nested structure); `pydantic-settings` (rejected: external dependency).

#### R-004: Agent SDK/CLI Dual Interface

- **Decision**: `adapter.py` tries Claude Agent SDK first; on `ImportError`, falls back to CLI subprocess invocation. The adapter exposes a unified `invoke(agent_name, prompt, knowledge_paths) -> AgentResult` interface.
- **Rationale**: Constitution mandates Claude Agent SDK with CLI fallback. The adapter pattern isolates this choice from all callers.
- **Alternatives considered**: Always CLI (rejected: SDK is more reliable when available); conditional import at call site (rejected: violates single responsibility).

#### R-005: v1 DB Schema Compatibility

- **Decision**: Read v1 tables (tasks, reviews, evidence, stage_progress, step_status, lvl, checkpoints, settings) as-is. Create new v2 tables (e.g., `config_cache`, `task_groups`) alongside. Use `CREATE TABLE IF NOT EXISTS` for all tables.
- **Rationale**: Constitution mandates no migration on existing tables. `IF NOT EXISTS` is idempotent and safe for both fresh and v1 databases.
- **Alternatives considered**: Schema migration tool like Alembic (rejected: overkill for additive-only changes).

#### R-006: Retry and Backoff Strategy

- **Decision**: Exponential backoff with jitter. Base delay 2s, multiplier 2x, max 3 attempts by default. All configurable via `max_retries`, `retry_base_delay`, `retry_multiplier` config keys.
- **Rationale**: Assumption A-008 specifies exponential backoff with jitter. This is the industry standard for transient failure recovery.
- **Alternatives considered**: Fixed delay (rejected: not adaptive); circuit breaker (rejected: unnecessary complexity for a batch orchestrator).

---

## Phase 1: Design

### Module Dependency Graph

```
cli.py
  └── engine.py
        ├── config.py
        ├── store/db.py + queries.py
        ├── agents/registry.py
        │     ├── agents/adapter.py
        │     └── agents/session.py
        └── stages/base.py
              ├── stages/spec.py
              ├── stages/plan.py
              ├── stages/implement.py
              │     ├── tdd/runner.py
              │     │     ├── tdd/parser.py
              │     │     └── tdd/validator.py
              │     └── checks/base.py
              │           ├── checks/local.py
              │           └── checks/ci.py
              │                 └── checks/common.py
              ├── stages/acceptance.py
              └── review/pipeline.py

ui/ (optional, no inbound arrows from above)
  ├── ui/wave.py
  └── ui/notifier.py
```

Dependency direction is strictly top-down. No circular imports. `store/models.py` is imported by many modules (data transfer objects) but has zero outbound dependencies.

### Key Technical Decisions

| Decision | Choice | Rationale | Constitution Ref |
|----------|--------|-----------|-----------------|
| Async model | asyncio single-threaded event loop | Matches v1, sufficient for I/O-bound agent calls | Technical Constraints |
| SQLite write coordination | asyncio.Lock in engine.py, injected | Lock-free store, caller coordinates | Technical Constraints |
| Check strategy | ABC subclass, constructor injection | Replaces v1 dict mutation (Pitfall #1) | Principle IV |
| Task format | Em-dash mandatory, contract tests | Fixes v1 parser/generator misalignment (Pitfall #3) | Principle V |
| CI error feedback | Per-job structured, 2000 char budget | Fixes v1 500-char truncation (Pitfall #4) | Principle VI |
| Stack detection | Config-driven registry, not if-elif | Extensible for new languages (Pitfall #24) | Principle VI |
| Stage skipping | Explicit config only, no heuristics | Removes _is_small_project (Pitfall #11, #20) | Principle III |
| Data transfer | @dataclass(frozen=True) | Immutable, type-safe (Pitfall #1 root cause) | Principle VII |

### Milestones

#### Milestone 1: Foundation (Tasks T001-T006)
**Goal**: Core infrastructure that all other modules depend on.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T001 | store/models.py | Define all frozen dataclass DTOs | None |
| T002 | config.py | Layered config loading (defaults + brownfield + project + env) | None |
| T003 | store/db.py | SQLite connection, schema init, v1 compatibility | T001 |
| T004 | store/queries.py | CRUD operations for all models | T001, T003 |
| T005 | checks/base.py | CheckStrategy ABC definition | T001 |
| T006 | agents/adapter.py | Claude SDK/CLI dual adapter | None |

#### Milestone 2: Agent and Check Infrastructure (Tasks T007-T012)
**Goal**: Agent management and test verification strategies.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T007 | agents/session.py | Session continuation manager | T006 |
| T008 | agents/registry.py | Agent registration + progressive knowledge loading | T006, T007 |
| T009 | checks/common.py | Shared check utilities (file detection, verdict parsing) | T005 |
| T010 | checks/local.py | LocalCheckStrategy implementation | T005, T009 |
| T011 | checks/ci.py | CICheckStrategy with stack scoping | T005, T009 |
| T012 | tdd/parser.py | tasks.md parser with strict format validation | T001 |

#### Milestone 3: TDD Engine (Tasks T013-T016)
**Goal**: Serial and parallel TDD execution.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T013 | tdd/validator.py | Parallel task validator (file_path conflicts) | T001, T012 |
| T014 | tdd/runner.py | TDD task scheduler (serial + parallel Phase A/B) | T005, T012, T013 |
| T015 | review/pipeline.py | Three-way parallel review + auto-fix + feature-gap | T008, T004 |
| T016 | stages/base.py | Stage ABC with review gate + checkpoint + auto-fix loop | T004, T015 |

#### Milestone 4: Pipeline Stages (Tasks T017-T020)
**Goal**: Four concrete stage implementations.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T017 | stages/spec.py | Spec stage: constitution -> specify -> clarify -> review | T016, T008 |
| T018 | stages/plan.py | Plan stage: plan -> research -> tasks -> review | T016, T008 |
| T019 | stages/implement.py | Implement stage: TDD -> review -> push+CI | T016, T014, T005 |
| T020 | stages/acceptance.py | Acceptance stage: verification -> traceability -> review | T016, T008 |

#### Milestone 5: Engine and CLI (Tasks T021-T023)
**Goal**: Top-level orchestration and user interface.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T021 | engine.py | Stage flow control (< 300 lines), asyncio.Lock owner | T002, T004, T008, T016-T020 |
| T022 | cli.py | argparse sub-commands: run, resume, retry, status | T021 |
| T023 | ui/ (optional) | Wave panel + desktop notifications | T021 (loose coupling) |

#### Milestone 6: Contract and Integration Tests (Tasks T024-T026)
**Goal**: Cross-module verification and v1 compatibility.

| Task | Module | Description | Dependencies |
|------|--------|-------------|-------------|
| T024 | tests/contract/ | Parser/generator format contract tests | T012 |
| T025 | tests/integration/ | TDD runner, review pipeline, resume from v1 DB | T014, T015, T004 |
| T026 | CI config | GitHub Actions workflow: pytest, coverage, type check, lint | All |

### Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Claude Agent SDK API changes | HIGH | Adapter pattern isolates SDK calls; CLI fallback always available |
| v1 DB schema has undocumented columns | MEDIUM | Integration test with real v1 workflow.db fixture validates compatibility |
| Parallel TDD batch commit race conditions | HIGH | asyncio single-threaded model eliminates true races; batch commit after gather ensures sequential git ops |
| Module size creep past 400 lines | MEDIUM | Constitution gate enforced in CI via line-count check; early splits planned |
| tasks.md format drift between generator and parser | HIGH | Contract tests in CI; em-dash format is non-negotiable per constitution |

---

## Constitution Re-Check (Post Phase 1 Design)

| # | Principle | Status | Design Evidence |
|---|-----------|--------|----------------|
| I | Single Responsibility | PASS | 25 modules, each with one concern; engine.py is flow control only; stages/ handles stage logic |
| II | Test-First Development | PASS | Test structure defined with unit/integration/contract; coverage targets per module |
| III | Explicit Configuration | PASS | Three-layer merge + env override; no heuristic skipping |
| IV | Strategy-Based Polymorphism | PASS | CheckStrategy ABC in checks/base.py; LocalCheckStrategy and CICheckStrategy implementations |
| V | Contract Alignment | PASS | Em-dash format in data-model.md; contract tests in Milestone 6 |
| VI | Resilient External Operations | PASS | Retry strategy R-006; extensible stack registry via config |
| VII | Immutable Data and Type Safety | PASS | All DTOs are frozen dataclasses; type annotations required on all public APIs |

**Gate Result**: ALL PASS -- design is constitution-compliant.

## Complexity Tracking

No constitution violations to justify. The design stays within all stated constraints:
- Module count: ~25 (reasonable for the scope)
- Max module size: < 400 lines (engine.py < 300)
- No circular dependencies
- No dict mutation patterns
- No heuristic-based behavior
