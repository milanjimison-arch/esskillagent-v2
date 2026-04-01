# Tasks: E+S Orchestrator v2 -- Autonomous Four-Stage TDD Orchestration

**Input**: Design documents from `specs/`
**Prerequisites**: plan.md, spec.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] [FR-###] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- **[FR-###]**: Linked functional requirement from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared fixtures, new modules, and schema upgrades that all user stories depend on.

- [ ] T001 [P] [FR-003][FR-004] Create EngineContext frozen dataclass and shared test fixtures (conftest.py with tmp_db, mock_adapter, mock_store) -- orchestrator/context.py
- [ ] T002 [P] [FR-057][FR-058] Upgrade store schema to v3 (artifacts and lvl_events tables) and define ArtifactRecord/LvlEventRecord data models -- orchestrator/store/_schema.py
- [ ] T003 [P] [FR-053][FR-054][FR-056] Implement LVL event operations (append_event, get_latest_event, verify_chain, verify_stage_invariant) and artifact operations (register_artifact, freeze_artifact, check_staleness, cascade_invalidate), enforce artifacts module size below 150 lines -- orchestrator/store/_lvl_queries.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Perception layer and core stage infrastructure that MUST be complete before user story work.

- [ ] T004 [P] [FR-018][FR-021] Create perception module with NC/NR marker detection and uncertainty heuristic scanner (question density, TBD/TODO, hedging expressions) -- orchestrator/perception.py
- [ ] T005 [P] [FR-063][FR-065][FR-066][FR-067] Create PipelineMonitor module with BLOCKED ratio detection, stale cascade detection, convergence tracking, and observation output to LVL -- orchestrator/monitor.py

**Checkpoint**: Foundation ready -- user story implementation can now begin.

---

## Phase 3: User Story 1 -- Full Pipeline Run (Priority: P1)

**Goal**: Developer initiates a complete four-stage pipeline run from CLI; orchestrator drives spec, plan, implement, acceptance autonomously.

**Independent Test**: Run `run` on a small feature and verify all four stages complete, producing spec, plan, tasks, implementation, passing tests, and acceptance report.

- [ ] T006 [P] [US1] [FR-017][FR-018][FR-019] Implement SpecStage.run(): invoke spec-writer, scan output with perception for NC markers, trigger clarify agent when needed, freeze artifacts with content hash -- orchestrator/stages/spec.py
- [ ] T007 [P] [US1] [FR-020][FR-021][FR-022][FR-023][FR-024][FR-025] Implement PlanStage.run(): invoke planner, scan for NR markers, trigger research agent, call task-generator to produce tasks.md, parse tasks into store -- orchestrator/stages/plan.py
- [ ] T008 [US1] [FR-026][FR-027][FR-028][FR-029][FR-030][FR-031][FR-033][FR-034][FR-035][FR-036][FR-037][FR-038][FR-039][FR-082][FR-083] Implement ImplementStage.run(): read pending tasks, run TDD cycles (RED prompt constrained to test-only, extra retry for env-caused GREEN failures, skip completed tasks, validate non-overlapping file sets for parallel execution), three-way review after GREEN, fix convergence detection in TDD runner, gap-detected supplementary tasks, batch commit with CI validation, LVL events, enforce TDD runner module size below 450 lines -- orchestrator/stages/implement.py
- [ ] T009 [US1] [FR-049][FR-050][FR-051] Implement AcceptanceStage.run(): invoke acceptor agent to produce traceability matrix, run final review, freeze artifacts -- orchestrator/stages/acceptance.py
- [ ] T010 [US1] [FR-042][FR-045][FR-046][FR-052][FR-059][FR-060][FR-061][FR-062][FR-078] Implement engine.run() full pipeline flow (stage sequencing, process lock, precondition validation, artifact freezing, enforce all LVL invariants INV-1 through INV-4 including prior-event linkage and red_pass-before-green_start ordering) and wire CLI `run` subcommand -- orchestrator/engine.py

**Checkpoint**: Full pipeline run is functional end-to-end.

---

## Phase 4: User Story 2 -- Resume from Checkpoint (Priority: P1)

**Goal**: Developer resumes an interrupted pipeline from the last successful checkpoint without re-executing completed stages or tasks.

**Independent Test**: Run a pipeline, kill it mid-stage, then run `resume` and verify it picks up from the correct point.

- [ ] T011 [US2] [FR-042][FR-052][FR-084] Implement engine.resume(): read last checkpoint, determine resume point, re-run atomic stages from start, resume implement from last completed task, handle no-checkpoint error -- orchestrator/engine.py

**Checkpoint**: Resume works correctly for all interruption points.

---

## Phase 5: User Story 3 -- Retry Single Task (Priority: P2)

**Goal**: Developer retries a specific BLOCKED task without re-running the entire pipeline.

**Independent Test**: Mark a task as BLOCKED, run `retry <task_id>`, verify only that task is re-executed.

- [ ] T012 [US3] [FR-043][FR-052] Implement engine.retry(task_id): validate task is BLOCKED, re-execute single TDD cycle (RED, GREEN, review), reject retry for DONE tasks -- orchestrator/engine.py

**Checkpoint**: Targeted retry works for individual BLOCKED tasks.

---

## Phase 6: User Story 4 -- Pipeline Status Dashboard (Priority: P2)

**Goal**: Developer checks current progress and health of a pipeline run.

**Independent Test**: Run `status` at various pipeline points and verify accurate progress reporting.

- [ ] T013 [US4] [FR-044][FR-052] Implement engine.status(): aggregate pipeline state from store, display stage completion, task counts by status, active warnings, handle no-active-pipeline case -- orchestrator/engine.py

**Checkpoint**: Status command provides accurate progress information.

---

## Phase 7: User Story 5 -- Autonomous BLOCKED Handling (Priority: P2)

**Goal**: Orchestrator autonomously detects high BLOCKED ratio and takes corrective action.

**Independent Test**: Simulate high BLOCKED ratio and verify orchestrator pauses and suggests corrective action.

- [ ] T014 [US5] [FR-064][FR-065] Wire PipelineMonitor into engine: invoke at stage transitions and batch completions, implement skip-single-BLOCKED behavior, pause on >50% BLOCKED ratio, suggest rollback -- orchestrator/engine.py

**Checkpoint**: Self-correction triggers appropriately on BLOCKED anomalies.

---

## Phase 8: User Story 6 -- CI Mode Execution (Priority: P2)

**Goal**: Orchestrator runs in CI mode with commit/push/poll workflow for test validation.

**Independent Test**: Configure CI mode and verify test commands trigger CI workflows and poll for results.

- [ ] T015 [P] [US6] [FR-008][FR-009][FR-010][FR-011][FR-012][FR-080][FR-090] Implement CI check strategy: tests_must_fail, tests_must_pass, _commit_and_push with 3-retry, auto-detect stack (including Python detection), configurable job name mapping, async thread delegation -- orchestrator/checks/ci.py
- [ ] T016 [P] [US6] [FR-005][FR-006][FR-041] Implement local check strategy: async thread delegation wrapper for tests_must_fail and tests_must_pass returning structured CheckResult, enforce common checks module size below 150 lines -- orchestrator/checks/local.py

**Checkpoint**: Both CI and local check strategies work correctly.

---

## Phase 9: User Story 7 -- Three-Way Review with Auto-Fix (Priority: P2)

**Goal**: After GREEN phase, three reviewers run in parallel with convergent auto-fix loop.

**Independent Test**: Produce code with known issues and verify review pipeline detects and fixes them.

- [ ] T017 [US7] [FR-013][FR-014][FR-015][FR-028] Implement review pipeline: three-way parallel review (code, security, brooks), differentiated fix application, bold-tolerant verdict parsing, convergence detection with max_fix_retries bound -- orchestrator/review/pipeline.py

**Checkpoint**: Review pipeline catches issues and auto-fixes converge or terminate.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Agent adaptations, configuration, security hardening, and integration validation.

- [ ] T018 [P] [FR-016][FR-068][FR-069][FR-070][FR-071][FR-072][FR-073][FR-074][FR-077] Adapt all 13 agent registrations and prompt templates: RED-only constraint for tdd-guide, NC markers for spec-writer, NR markers for planner, CI estimation for task-generator, dependency awareness for fixer, structured output for acceptor, relative path resolution -- orchestrator/agents/registry.py
- [ ] T019 [P] [FR-075][FR-076][FR-085][FR-086] Update defaults.yaml with idle_timeout, subprocess_timeout, source_dirs, global_timeout, stage_timeout; add bold-tolerant severity regex; configure CI workflow -- orchestrator/defaults.yaml
- [ ] T020 [P] [FR-001][FR-002][FR-087][FR-088][FR-089][FR-091] Security hardening and adapter compliance: file path whitelist validation for LLM outputs, safe list-based subprocess construction, SQLite write serialization lock, pre-commit secret detection, session management (expire_session, list_sessions), enforce adapter module size below 400 lines -- orchestrator/agents/adapter.py

---

## Phase 11: Integration Testing (Priority: P1)

**Purpose**: End-to-end integration tests validating full pipeline, resume, and retry + monitor workflows with mocked agents.

**Goal**: Verify that the orchestrator's core user stories work correctly as integrated units, covering scenarios that unit tests cannot validate (cross-stage data flow, checkpoint persistence across resume, monitor-triggered pause during retry).

**Independent Test**: Run `pytest tests/integration/` and verify all integration scenarios pass with mocked agents.

- [ ] T110 [P] [FR-047] Full pipeline integration test: exercise all four stages (spec, plan, implement, acceptance) end-to-end with mocked agents, verify stage sequencing, artifact freezing, LVL event chain integrity, and final acceptance report generation -- tests/integration/test_full_pipeline.py
- [ ] T111 [P] [FR-042] Resume integration test: run pipeline, simulate interruption at various points (mid-spec, mid-implement), invoke engine.resume(), verify atomic stages re-run from start and implement stage resumes from last completed task, validate checkpoint correctness -- tests/integration/test_resume.py
- [ ] T112 [P] [FR-043][FR-064] Retry + monitor integration test: set up pipeline with BLOCKED tasks, invoke engine.retry() for single task, simulate >50% BLOCKED ratio to trigger PipelineMonitor pause, verify monitor recommendations are written to LVL, validate retry re-executes only the targeted TDD cycle -- tests/integration/test_retry.py

**Checkpoint**: All integration tests pass, confirming cross-module workflows are correct.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies -- can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion -- BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational -- core pipeline
- **US2 (Phase 4)**: Depends on US1 (needs engine.run to exist before resume)
- **US3 (Phase 5)**: Depends on US1 implement stage (needs BLOCKED tasks to retry)
- **US4 (Phase 6)**: Depends on Foundational only (reads store, no stage dependency)
- **US5 (Phase 7)**: Depends on US1 + Foundational (needs monitor + engine wiring)
- **US6 (Phase 8)**: Depends on Foundational only (check strategies are independent)
- **US7 (Phase 9)**: Depends on Foundational only (review pipeline is independent)
- **Polish (Phase 10)**: Can start after Foundational; no strict dependency on user stories
- **Integration Tests (Phase 11)**: Depends on US1 (Phase 3), US2 (Phase 4), US3 (Phase 5), US5 (Phase 7) -- requires core pipeline, resume, retry, and monitor to be implemented

### Parallel Opportunities

- **Phase 1**: T001, T002, T003 all run in parallel (different files)
- **Phase 2**: T004, T005 run in parallel (perception.py vs monitor.py)
- **Phase 3**: T006, T007 run in parallel (spec.py vs plan.py); T008, T009 after
- **Phase 6/8/9**: US4, US6, US7 can run in parallel after Foundational (independent modules)
- **Phase 10**: T018, T019, T020 all run in parallel (different files)
- **Phase 11**: T110, T111, T112 all run in parallel (different test files, no shared state)

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T005)
3. Complete Phase 3: User Story 1 -- Full Pipeline Run (T006-T010)
4. Complete Phase 4: User Story 2 -- Resume (T011)
5. **STOP and VALIDATE**: Full pipeline run + resume works end-to-end

### Incremental Delivery

1. Setup + Foundational -> Foundation ready
2. US1 -> Full pipeline works -> MVP
3. US2 -> Resume works -> Production-ready core
4. US3 + US4 + US5 -> Retry, status, self-correction -> Full autonomy
5. US6 + US7 -> CI mode, review pipeline -> Enterprise features
6. Polish -> Agent adaptations, security, config -> Hardened release
7. Integration Tests -> End-to-end validation -> Confidence gate

---

## FR Coverage Matrix

| FR Range | Covered By |
|----------|-----------|
| FR-001..002 | T020 (adapter) |
| FR-003..004 | T001 (context) |
| FR-005..006 | T016 (local checks) |
| FR-007 | T006 (stage base, implicitly via spec stage) |
| FR-008..012 | T015 (CI checks) |
| FR-013..015 | T017 (review) |
| FR-016 | T018 (registry) |
| FR-017..019 | T006 (spec stage) |
| FR-020..025 | T007 (plan stage) |
| FR-026..031 | T008 (implement stage) |
| FR-032..039 | T008 (implement/TDD runner integration) |
| FR-040 | T016/T015 (check utilities) |
| FR-041 | T016 (local checks, module size constraint) |
| FR-042 | T010, T011 (engine); T111 (resume integration test) |
| FR-043 | T012 (engine retry); T112 (retry + monitor integration test) |
| FR-044 | T013 (engine status) |
| FR-045..046 | T010 (engine) |
| FR-047 | T008 (implement stage unit tests); T110 (full pipeline integration test) |
| FR-048 | Existing ui/wave.py (no task needed) |
| FR-049..051 | T009 (acceptance) |
| FR-052 | T010, T011, T012, T013 (CLI subcommands) |
| FR-053..054 | T003 (LVL queries) |
| FR-055..056 | T003 (artifact queries, module size constraint) |
| FR-057..058 | T002 (schema + models) |
| FR-059..060 | T010 (engine invariant enforcement INV-1, INV-2) |
| FR-061 | T010 (engine invariant enforcement INV-3: prior-event linkage) |
| FR-062 | T010 (engine invariant enforcement INV-4: red_pass before green_start) |
| FR-063..067 | T005, T014 (monitor); T112 (retry + monitor integration test for FR-064) |
| FR-068..074 | T018 (agent adaptations) |
| FR-075..076 | T019 (defaults config) |
| FR-077 | T018 (registry path resolution) |
| FR-078 | T010 (engine git check) |
| FR-079 | T015 (CI source dir detection) |
| FR-080 | T015 (CI Python stack detection) |
| FR-081 | T008 (TDD RED constraint) |
| FR-082 | T008 (env vs logic error distinction in GREEN failures) |
| FR-083 | T008 (additional retry for env-caused GREEN failures) |
| FR-084 | T011 (resume skip completed) |
| FR-085..086 | T019 (config + regex) |
| FR-087..091 | T020 (security) |

---

## Notes

- [P] tasks operate on different files with no import dependencies
- Each user story is independently testable at its checkpoint
- Total: 23 tasks across 11 phases
- engine.py is touched by T010, T011, T012, T013, T014 -- these MUST be sequential (no [P])
- New modules: context.py, perception.py, monitor.py, tests/conftest.py
- Brownfield modules (modify existing): all others
- Integration tests (T110-T112) use task IDs in the 1xx range to clearly distinguish from unit-level tasks (T001-T020)
