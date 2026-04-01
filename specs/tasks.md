# Tasks: E+S Orchestrator v2 Complete Rewrite

**Input**: Design documents from `specs/`
**Prerequisites**: plan.md, spec.md, data-model.md, constitution.md

**Tests**: TDD approach -- tests are part of the orchestrator's RED/GREEN cycle.

**Organization**: Tasks grouped by milestone, mapping user stories to implementation phases.

## Format: `[ID] [P?] [Story] [FR-###] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **[FR-###]**: Associated functional requirements from spec.md
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `orchestrator/` at repository root
- **Tests**: `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, frozen dataclass DTOs, and layered configuration

- [ ] T001 [FR-055] [FR-054] Define all frozen dataclass DTOs (Task, Pipeline, StageProgress, Checkpoint, ReviewResult, Evidence, AgentInfo, AgentResult, OrchestratorConfig, enums) — orchestrator/store/models.py
- [ ] T002 [FR-019] [FR-020] [FR-021] Implement layered configuration loading (defaults.yaml, brownfield.yaml, .orchestrator.yaml, env var overrides) with v1 compatibility — orchestrator/config.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Persistence layer and base abstractions that ALL user stories depend on

- [ ] T003 [FR-033] [FR-034] [FR-035] [FR-059] Implement SQLite store with v1-compatible schema, new v2 tables, asyncio.Lock coordination, and connection management — orchestrator/store/db.py
- [ ] T004 [FR-036] [FR-037] Implement CRUD operations (INSERT OR REPLACE, evidence chain, LVL audit logs) returning frozen dataclass types — orchestrator/store/queries.py
- [ ] T005 [P] [FR-012] [FR-014] Define CheckStrategy ABC with tests_must_fail and tests_must_pass abstract methods — orchestrator/checks/base.py
- [ ] T006 [P] [FR-027] [FR-029] Implement Claude SDK/CLI dual adapter and session continuation manager — orchestrator/agents/adapter.py

**Checkpoint**: Foundation ready -- user story implementation can now begin

---

## Phase 3: User Story 2+7+14 - TDD Engine and Task Parsing (Priority: P1/P2)

**Goal**: Parse tasks.md, validate parallel constraints, and execute serial+parallel TDD cycles

**Independent Test**: Provide a tasks.md with serial and [P] parallel tasks; verify parsing, grouping, validation, and RED/GREEN execution

- [ ] T007 [US2] [FR-022] [FR-023] [FR-024] [FR-008] [FR-026] Implement tasks.md parser with strict em-dash format validation, numeric sort, [P] without file_path rejection, and task grouping (setup/US/polish) — orchestrator/tdd/parser.py
- [ ] T008 [US2] [FR-009] Implement parallel task validator with file_path conflict detection and serial fallback — orchestrator/tdd/validator.py
- [ ] T009 [US2] [FR-006] [FR-007] [FR-010] [FR-011] Implement TDD task scheduler with serial RED-GREEN, parallel Phase A/B batch execution, git add scoping, and per-job error feedback retry — orchestrator/tdd/runner.py

**Checkpoint**: TDD engine functional -- can parse tasks and execute RED/GREEN cycles

---

## Phase 4: User Story 3+11 - Check Strategies (Priority: P1/P3)

**Goal**: Local and CI test verification with stack-scoped CI job filtering

**Independent Test**: Switch local_test config and verify both strategies evaluate RED/GREEN correctly

- [ ] T010 [P] [US3] [FR-013] [FR-042] [FR-043] Implement LocalCheckStrategy with subprocess test execution, retry with backoff, and TimeoutExpired/FileNotFoundError handling — orchestrator/checks/local.py
- [ ] T011 [P] [US3] [FR-013] [FR-015] [FR-016] [FR-017] [FR-018] [FR-045] [FR-046] [FR-047] Implement CICheckStrategy with stack scoping, extensible technology registry via config, CI job name startswith matching, skipped/cancelled handling, and 2000-char per-job error budget — orchestrator/checks/ci.py

**Checkpoint**: Both check strategies operational -- TDD runner can use either

---

## Phase 5: User Story 8+9 - Agent Registry and Review Pipeline (Priority: P2)

**Goal**: Load 14 agents with progressive knowledge, run three-way parallel review with auto-fix

**Independent Test**: Load all agent directories; simulate review pass/fail and verify auto-fix loop

- [ ] T012 [P] [US8] [FR-027] [FR-028] [FR-029] Implement agent registry with 14 agent directory loading, progressive knowledge injection (absolute paths), and session continuation — orchestrator/agents/registry.py
- [ ] T013 [P] [US9] [FR-030] [FR-031] [FR-032] Implement three-way parallel review pipeline (code, security, brooks), auto-fix loop on failure, and feature-gap detection with supplemental task creation — orchestrator/review/pipeline.py

**Checkpoint**: Agent infrastructure and review pipeline ready

---

## Phase 6: User Story 1+6 - Pipeline Engine and Stages (Priority: P1/P2)

**Goal**: Four-stage pipeline with review gates, checkpoints, resume, and stage skipping

**Independent Test**: Run minimal project through all four stages; interrupt and resume from checkpoint

- [ ] T014 [US1] [FR-004] [FR-002] Implement Stage ABC with review gate enforcement, checkpoint persistence after completion, and auto-fix retry loop — orchestrator/stages/base.py
- [ ] T015 [US1] [FR-001] [FR-003] [FR-005] [FR-053] [FR-058] Implement engine.py with four-stage sequential flow control, skip_stages support, asyncio.Lock ownership, and stage delegation (< 300 lines) — orchestrator/engine.py
- [ ] T016 [US1] [FR-001] Implement four concrete stages (spec: constitution-specify-clarify-review; plan: plan-research-tasks-review; implement: TDD-review-push+CI; acceptance: verification-traceability-review) — orchestrator/stages/spec.py

**Checkpoint**: Full pipeline executable end-to-end

---

## Phase 7: User Story 5+4 - CLI and Configuration (Priority: P2)

**Goal**: CLI sub-commands and verified layered config integration

**Independent Test**: Invoke each sub-command; verify config override chain

- [ ] T017 [US5] [FR-038] [FR-039] [FR-040] [FR-041] [FR-044] Implement CLI with argparse sub-commands (run, resume, retry, status), git initialization check, and entry point wiring to engine — orchestrator/cli.py

**Checkpoint**: User-facing CLI operational

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Optional modules, traceability, contract tests, and module quality

- [ ] T018 [P] [FR-048] [FR-049] [FR-050] Implement optional Wave panel and desktop notifications with zero core imports from ui/ — orchestrator/ui/wave.py
- [ ] T019 [P] [FR-051] [FR-052] Implement traceability matrix generation (FR-to-task-to-test mapping) with unimplemented FR flagging — orchestrator/stages/acceptance.py
- [ ] T020 [FR-025] [FR-056] [FR-057] Implement contract tests verifying parser/generator format alignment, and validate module constraints (no bare except, exception chaining, < 400 lines) — tests/contract/test_task_format.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies -- can start immediately
- **Foundational (Phase 2)**: Depends on T001 (models); T005/T006 are parallel
- **TDD Engine (Phase 3)**: Depends on T001 (models), T005 (CheckStrategy ABC)
- **Check Strategies (Phase 4)**: Depends on T005 (ABC), T009 (runner uses strategies)
- **Agent & Review (Phase 5)**: Depends on T006 (adapter), T004 (queries)
- **Pipeline & Stages (Phase 6)**: Depends on T004, T009, T012, T013, T014
- **CLI (Phase 7)**: Depends on T015 (engine)
- **Polish (Phase 8)**: Depends on all prior phases

### User Story Dependencies

- **US2 (TDD)**: Can start after Phase 2 -- no dependencies on other stories
- **US3 (Checks)**: Can start after T005 -- parallel with US2
- **US8 (Agents)**: Can start after T006 -- parallel with US2/US3
- **US9 (Review)**: Can start after T006, T004 -- parallel with US2/US3
- **US1 (Pipeline)**: Depends on US2, US3, US8, US9 (integrates all subsystems)
- **US5 (CLI)**: Depends on US1 (wraps engine)
- **US4 (Config)**: Covered by T002 in Setup -- independently testable early
- **US6 (Checkpoint)**: Covered by T003/T004/T014 -- tested within pipeline flow
- **US7 (Parser)**: Covered by T007 -- independently testable
- **US10 (Resilience)**: Covered by T010/T011 retry logic -- tested within check strategies
- **US11 (Stack)**: Covered by T011 stack scoping -- tested within CI strategy
- **US12 (UI)**: Covered by T018 -- independently testable, no core deps
- **US13 (Trace)**: Covered by T019 -- testable after pipeline completion
- **US14 (Grouping)**: Covered by T007 grouping logic -- tested within parser

### Parallel Opportunities

- T005 + T006 (Phase 2): different packages, no overlap
- T010 + T011 (Phase 4): different check strategy files
- T012 + T013 (Phase 5): agents/ vs review/ packages
- T018 + T019 (Phase 8): ui/ vs stages/acceptance.py

---

## Parallel Example: Phase 4 (Check Strategies)

```bash
# Launch both check strategies in parallel:
Task T010: "Implement LocalCheckStrategy — orchestrator/checks/local.py"
Task T011: "Implement CICheckStrategy — orchestrator/checks/ci.py"
```

## Parallel Example: Phase 5 (Agent & Review)

```bash
# Launch agent registry and review pipeline in parallel:
Task T012: "Implement agent registry — orchestrator/agents/registry.py"
Task T013: "Implement review pipeline — orchestrator/review/pipeline.py"
```

---

## Implementation Strategy

### MVP First (Pipeline + TDD + Checks)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T006)
3. Complete Phase 3: TDD Engine (T007-T009)
4. Complete Phase 4: Check Strategies (T010-T011)
5. **STOP and VALIDATE**: TDD engine parses tasks and runs RED/GREEN with both strategies

### Incremental Delivery

1. Setup + Foundational -> Core infrastructure ready
2. TDD Engine + Checks -> Can execute TDD cycles (US2+US3 MVP)
3. Agent + Review -> Full review pipeline (US8+US9)
4. Pipeline + Stages -> End-to-end four-stage flow (US1+US6)
5. CLI -> User-facing interface (US5)
6. Polish -> Optional features, traceability, contract tests (US12+US13)

### FR Coverage Validation

All 59 functional requirements (FR-001 through FR-059) are covered:
- FR-001..FR-005: T014, T015, T016
- FR-006..FR-011: T007, T008, T009
- FR-012..FR-018: T005, T010, T011
- FR-019..FR-021: T002
- FR-022..FR-026: T007
- FR-027..FR-029: T006, T012
- FR-030..FR-032: T013
- FR-033..FR-037: T003, T004
- FR-038..FR-044: T010, T017
- FR-045..FR-047: T011
- FR-048..FR-050: T018
- FR-051..FR-052: T019
- FR-053..FR-057: T015, T020
- FR-058..FR-059: T003, T015
