# Tasks: E+S Orchestrator v2 — Full Rewrite

**Input**: Design documents from `specs/`
**Prerequisites**: plan.md, spec.md, data-model.md

**Tests**: TDD approach requested. The orchestrator's RED/GREEN separation is handled by the E+S orchestrator itself (tdd-guide for RED, implementer for GREEN). Each task describes the functional intent only.

**Organization**: Tasks are grouped by implementation phase following the Bottom-Up build order defined in plan.md. User stories are mapped to tasks via [US*] labels.

## Format: `[ID] [P?] [Story] [FR-###] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **[FR-###]**: Associated functional requirement IDs from spec.md
- Include exact file paths after em dash

## Path Conventions

- **Python package**: `orchestrator/` at repository root
- **Tests**: `tests/` at repository root
- **Config**: `orchestrator/defaults.yaml`

---

## Phase 1: Foundation (Data Model + Config + Store)

**Purpose**: Establish the foundation all upper modules depend on. No external dependencies, independently testable.

**CRITICAL**: No core strategy or stage work can begin until this phase is complete.

- [ ] T001 [US4] [FR-001][FR-002][FR-003][FR-004] Implement layered configuration system with frozen dataclass, load_config() supporting defaults.yaml/brownfield.yaml/.orchestrator.yaml/env override chain, unknown key warnings, and nested dict recursive merge — orchestrator/config.py
- [ ] T002 [US2][US4] [FR-039][FR-040][FR-041][FR-042][FR-043] Implement persistence layer: 7 frozen dataclass models in models.py, SQLite connection with WAL/busy_timeout/schema init (v1 8 tables)/v2 migration (config_cache) in db.py, and CRUD queries returning frozen dataclass in queries.py — orchestrator/store/models.py
- [ ] T003 [US4] [FR-001] Create defaults.yaml with all configuration keys and their default values (models, test_command, local_test, ci_timeout, retries, timeouts, skip_stages) — orchestrator/defaults.yaml

**Checkpoint**: Foundation ready — core strategies can now be developed in parallel.

---

## Phase 2: Core Strategies (Check Strategies + Task Parser + Agent System)

**Purpose**: Three independent subsystems that only depend on Phase 1 models and config. Can be developed in parallel.

- [ ] T004 [P] [US3] [FR-026][FR-027][FR-029][FR-030] Implement local check strategy: CheckStrategy ABC in base.py with tests_must_fail/tests_must_pass, detect_stack() in common.py using extension+path prefix detection, and LocalCheckStrategy in local.py calling config.test_command — orchestrator/checks/local.py
- [ ] T005 [P] [US3] [FR-028][FR-029][FR-030][FR-031] Implement CI check strategy: CICheckStrategy with commit/push/gh-run-watch flow, per-job structured log extraction within 2000-char budget, stack scoping via detect_stack, RED/GREEN shared evaluation methods, push retry (3x/5s), and subprocess exception handling — orchestrator/checks/ci.py
- [ ] T006 [P] [US1][US5] [FR-021][FR-022][FR-023][FR-024][FR-025] Implement task parser and parallel validator: parse_tasks() with em-dash primary strategy and "in src/" fallback, [P] without file_path rejection, non-canonical warning, phase grouping (setup/US*/polish), and validate_parallel_group() with file_path overlap detection and demotion to serial — orchestrator/tdd/parser.py
- [ ] T007 [P] [US10] [FR-035][FR-036][FR-037][FR-038] Implement agent system: AgentRegistry scanning ESSKILLAGENT directory loading 14 agents with KB paths, SessionManager for session creation/resume/expire, and AgentAdapter with Claude SDK primary and CLI fallback — orchestrator/agents/registry.py

**Checkpoint**: All core strategies ready — composition layer can now be built.

---

## Phase 3: Composition (TDD Runner + Review Pipeline)

**Purpose**: Combine Phase 2 strategy components into core business logic.

- [ ] T008 [P] [US1][US5] [FR-016][FR-017][FR-018][FR-019][FR-020] Implement TDD runner: TaskRunner with run_serial (RED then GREEN), run_parallel_group (Phase A RED concurrent + batch commit, Phase B GREEN concurrent + batch commit + retry loop), git add scope limited to project source excluding .workflow/, and asyncio.gather with sequential store writes — orchestrator/tdd/runner.py
- [ ] T009 [P] [US1][US8] [FR-032][FR-033][FR-034] Implement review pipeline: ReviewPipeline with parallel 3-way review (code+security+brooks via asyncio.gather), auto-fix cycle (fixer agent + re-review up to max_fix_retries, only re-running failed reviewers), and feature-gap detection creating supplementary tasks from "missing"/"unimplemented" patterns — orchestrator/review/pipeline.py

**Checkpoint**: TDD runner and review pipeline ready — stages can now be implemented.

---

## Phase 4: Stages (Four-Stage Pipeline)

**Purpose**: Four stages sharing base.py review/gate/checkpoint logic via Template Method pattern.

- [ ] T010 [US1] [FR-015] Implement Stage base class with template method pattern: run() orchestrating execute_steps/review/gate/checkpoint, shared _run_review/_check_gate/_save_checkpoint, engine_ctx dependency injection — orchestrator/stages/base.py
- [ ] T011 [P] [US1] [FR-011] Implement SpecStage extending Stage: _execute_steps running constitution/specify/clarify/review sub-steps via corresponding agents, no _is_small_project skip logic — orchestrator/stages/spec.py
- [ ] T012 [P] [US1] [FR-012] Implement PlanStage extending Stage: _execute_steps running plan/research/tasks/review sub-steps, tasks sub-step calling parser.parse_tasks and writing results to store — orchestrator/stages/plan.py
- [ ] T013 [P] [US1] [FR-013] Implement ImplementStage extending Stage: _execute_steps reading tasks from store, executing via TaskRunner (serial/parallel), ReviewPipeline review, feature-gap supplementary task handling, and final push+CI verification — orchestrator/stages/implement.py
- [ ] T014 [P] [US1] [FR-014] Implement AcceptanceStage extending Stage: _execute_steps running acceptor agent, generating traceability matrix (FR to Task to Test) to specs/checklists/traceability.md, and final review gate — orchestrator/stages/acceptance.py

**Checkpoint**: All four pipeline stages ready — engine can now orchestrate them.

---

## Phase 5: Orchestration (Engine + CLI)

**Purpose**: Top-level orchestration connecting all layers.

- [ ] T015 [US1][US2] [FR-005][FR-006][FR-007][FR-008][FR-009][FR-010][FR-052][FR-053][FR-054] Implement Engine class (under 300 lines): asyncio.Lock creation and injection, store/config/agents/checker/stages initialization, run() executing spec/plan/implement/acceptance with skip_stages support, resume() reading last checkpoint and continuing, retry(task_id) re-running single task TDD cycle — orchestrator/engine.py
- [ ] T016 [US1][US2][US6][US7] [FR-048][FR-049][FR-050][FR-051] Implement CLI entry point with argparse: run subcommand (project_path, --req-file/--req), resume subcommand, retry subcommand (task_id), status subcommand, all launching via asyncio.run(engine.*()) — orchestrator/cli.py

**Checkpoint**: Core orchestrator fully functional — optional UI can be added.

---

## Phase 6: Optional (UI)

**Purpose**: Visual monitoring layer, independently removable without affecting core.

- [ ] T017 [US9] [FR-044][FR-045][FR-046][FR-047] Implement Wave panel in wave.py (stage progress + task status display) and desktop notifier in notifier.py, with event/callback integration only (no core module imports from ui/), independently loadable and removable — orchestrator/ui/wave.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundation)**: No dependencies — start immediately. T001/T002/T003 execute sequentially.
- **Phase 2 (Core Strategies)**: Depends on Phase 1 completion. T004/T005/T006/T007 can all run in parallel.
- **Phase 3 (Composition)**: Depends on Phase 2 completion. T008/T009 can run in parallel.
- **Phase 4 (Stages)**: Depends on Phase 3 completion. T010 first, then T011/T012/T013/T014 in parallel.
- **Phase 5 (Orchestration)**: Depends on Phase 4 completion. T015 then T016 sequentially.
- **Phase 6 (Optional)**: Depends on Phase 5 completion. T017 independent.

### User Story Coverage

- **US1** (Full Pipeline, P1): T006, T008, T009, T010, T011, T012, T013, T014, T015, T016
- **US2** (Resume, P1): T002, T015, T016
- **US3** (Local/CI Strategies, P1): T004, T005
- **US4** (Per-Project Config, P2): T001, T002, T003
- **US5** (Parallel TDD, P2): T006, T008
- **US6** (Retry Task, P2): T016
- **US7** (View Status, P3): T016
- **US8** (Feature-Gap Detection, P2): T009
- **US9** (Wave Panel, P3): T017
- **US10** (Agent System, P2): T007

### Parallel Opportunities

```
Phase 2 (all parallel):
  T004 checks/local.py  |  T005 checks/ci.py  |  T006 tdd/parser.py  |  T007 agents/registry.py

Phase 3 (parallel):
  T008 tdd/runner.py  |  T009 review/pipeline.py

Phase 4 (T011-T014 parallel after T010):
  T011 stages/spec.py  |  T012 stages/plan.py  |  T013 stages/implement.py  |  T014 stages/acceptance.py
```

---

## FR Coverage Matrix

| FR Range | Task(s) | Status |
|----------|---------|--------|
| FR-001~004 | T001, T003 | Covered |
| FR-005~010 | T015 | Covered |
| FR-011 | T011 | Covered |
| FR-012 | T012 | Covered |
| FR-013 | T013 | Covered |
| FR-014 | T014 | Covered |
| FR-015 | T010 | Covered |
| FR-016~020 | T008 | Covered |
| FR-021~025 | T006 | Covered |
| FR-026~027,029~030 | T004 | Covered |
| FR-028~031 | T005 | Covered |
| FR-032~034 | T009 | Covered |
| FR-035~038 | T007 | Covered |
| FR-039~043 | T002 | Covered |
| FR-044~047 | T017 | Covered |
| FR-048~051 | T016 | Covered |
| FR-052~054 | T015 | Covered |

---

## Implementation Strategy

### MVP First (User Story 1 + Foundation)

1. Complete Phase 1: Foundation (T001-T003)
2. Complete Phase 2: Core Strategies (T004-T007)
3. Complete Phase 3: Composition (T008-T009)
4. Complete Phase 4: Stages (T010-T014)
5. Complete Phase 5: Engine + CLI (T015-T016)
6. **STOP and VALIDATE**: Full pipeline should work end-to-end

### Incremental Delivery

1. Phases 1-5 deliver US1 (full pipeline) + US2 (resume) + US3 (check strategies) + US4 (config) + US5 (parallel TDD) + US10 (agents)
2. Phase 6 adds US9 (Wave panel)
3. US6 (retry) and US7 (status) are delivered via CLI in Phase 5
4. US8 (feature-gap) is delivered via review pipeline in Phase 3
