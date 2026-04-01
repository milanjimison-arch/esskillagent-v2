# Feature Specification: E+S Orchestrator v2 — Full Rewrite

**Created**: 2026-04-01
**Status**: Draft
**Input**: User description: "Complete rewrite of the E+S Orchestrator (v1) to resolve accumulated technical debt (6674 lines, 19 modules with unclear boundaries), preserve validated design decisions, and establish clean module boundaries, consistent naming, layered configuration, pluggable test strategies, and built-in parallel safety."

## User Scenarios & Testing

### User Story 1 - Run a New Feature Through the Full Pipeline (Priority: P1)

A developer wants to take a feature description and run it through the orchestrator's four-stage pipeline (spec, plan, implement, acceptance) to produce a fully tested, reviewed, and verified implementation.

**Why this priority**: This is the core value proposition of the orchestrator. Without the pipeline working end-to-end, nothing else matters.

**Independent Test**: Can be fully tested by providing a small feature description and verifying that the orchestrator produces spec, plan, tasks, implementation code, passing tests, reviews, and a traceability matrix.

**Acceptance Scenarios**:

1. **Given** a project directory with a valid `.orchestrator.yaml` or `brownfield.yaml`, **When** the user runs `orchestrator run` with a feature description, **Then** the system executes all four stages (spec, plan, implement, acceptance) in sequence, producing artifacts at each stage.
2. **Given** the pipeline is in the implement stage, **When** TDD tasks are executed, **Then** each task follows RED (test must fail) then GREEN (test must pass) with appropriate check strategy (local or CI).
3. **Given** a completed implement stage, **When** the acceptance stage runs, **Then** the system produces a traceability matrix mapping FR to Task to Test and completes a final review gate.
4. **Given** a stage review identifies issues, **When** the auto-fix cycle triggers, **Then** the fixer agent addresses the issues and re-review occurs, up to the configured retry limit.

---

### User Story 2 - Resume from a Checkpoint After Interruption (Priority: P1)

A developer's orchestrator run was interrupted (crash, network failure, manual stop). They want to resume from the last saved checkpoint without re-running completed work.

**Why this priority**: Long pipeline runs (hours) make interruption recovery essential. Without resume, any failure forces a full restart, wasting significant time and API costs.

**Independent Test**: Can be tested by running a pipeline partially, terminating it, then running `orchestrator resume` and verifying it continues from the correct checkpoint.

**Acceptance Scenarios**:

1. **Given** a previously interrupted run with a checkpoint saved in `.workflow/workflow.db`, **When** the user runs `orchestrator resume`, **Then** the system reads the last completed stage/step and resumes from the next pending step.
2. **Given** a v1 `.workflow/workflow.db` database, **When** the user runs `orchestrator resume` with the v2 orchestrator, **Then** the system successfully reads the v1 schema and resumes execution.
3. **Given** no checkpoint exists in the project directory, **When** the user runs `orchestrator resume`, **Then** the system reports an error indicating no prior run was found.

---

### User Story 3 - Switch Between Local and CI Test Strategies (Priority: P1)

A developer wants to use local tests during development and CI tests for final verification, controlled by configuration rather than code changes.

**Why this priority**: The v1 dict-mutation pattern for switching between local and CI checks was a major source of bugs. A clean strategy interface is a core architectural improvement.

**Independent Test**: Can be tested by running the same task with `local_test: true` and `local_test: false`, verifying that the correct strategy executes without any code changes.

**Acceptance Scenarios**:

1. **Given** a project with `local_test: true` in configuration, **When** TDD tasks execute, **Then** the system runs tests locally using the configured `test_command`.
2. **Given** a project with `local_test: false` in configuration, **When** TDD tasks execute, **Then** the system commits, pushes, and waits for CI results via GitHub Actions.
3. **Given** a CI check fails, **When** the system reports the failure to the agent, **Then** the error feedback is structured per-job with only the relevant stack trace, within a 2000-character budget.

---

### User Story 4 - Configure Orchestrator Per-Project (Priority: P2)

A developer working on multiple projects wants each project to have its own orchestrator settings (test command, CI timeout, model selection) without modifying global defaults.

**Why this priority**: v1 only supported global configuration, forcing manual edits when switching projects. Per-project config is a frequently requested improvement.

**Independent Test**: Can be tested by creating a `.orchestrator.yaml` in a project directory with overrides and verifying those values take precedence over global defaults.

**Acceptance Scenarios**:

1. **Given** global defaults in `defaults.yaml` and a project-level `.orchestrator.yaml`, **When** configuration is loaded, **Then** project-level values override global defaults for matching keys.
2. **Given** a v1 `brownfield.yaml` exists alongside a `.orchestrator.yaml`, **When** configuration is loaded, **Then** the loading order is: `defaults.yaml` then `brownfield.yaml` then `.orchestrator.yaml`, with later files overriding earlier ones.
3. **Given** a `.orchestrator.yaml` contains an invalid key, **When** configuration is loaded, **Then** the system warns about the unknown key but continues with valid settings.
4. **Given** no `.orchestrator.yaml` exists in the project directory, **When** configuration is loaded, **Then** the system uses global defaults (and `brownfield.yaml` if present) without error.

---

### User Story 5 - Execute Parallel TDD Tasks Safely (Priority: P2)

A developer has a plan with multiple independent tasks marked `[P]` for parallel execution. They want these to run concurrently without git conflicts or test interference.

**Why this priority**: Parallel execution dramatically reduces pipeline time, but v1 had critical bugs in this area. Built-in safety is essential.

**Independent Test**: Can be tested by creating tasks with `[P]` markers and non-overlapping file paths, running them in parallel, and verifying no git conflicts occur and all tests pass independently.

**Acceptance Scenarios**:

1. **Given** multiple `[P]` tasks with non-overlapping `file_path` values, **When** parallel TDD executes, **Then** agents run concurrently and a single batch commit+CI validates all changes.
2. **Given** multiple `[P]` tasks where two share an overlapping `file_path`, **When** the validator checks before execution, **Then** the conflicting tasks are flagged and demoted to serial execution.
3. **Given** a `[P]` task missing its `file_path`, **When** the parser validates the task list, **Then** the task is rejected with a clear error identifying the missing path.
4. **Given** Phase A (RED) completes for a parallel group, **When** Phase B (GREEN) executes, **Then** agents run in parallel with per-job error feedback if any task fails, and retries occur up to the configured limit.

---

### User Story 6 - Retry a Single Failed Task (Priority: P2)

A developer wants to retry just one task that failed (due to a transient CI error or a fixable agent mistake) without re-running the entire pipeline.

**Why this priority**: Granular retry saves time and API costs compared to re-running entire stages.

**Independent Test**: Can be tested by running a pipeline where one task fails, then using `orchestrator retry T003` to re-run only that task.

**Acceptance Scenarios**:

1. **Given** a completed implement stage with task T003 marked as failed, **When** the user runs `orchestrator retry T003`, **Then** only task T003 re-executes through the TDD cycle.
2. **Given** a task ID that does not exist, **When** the user runs `orchestrator retry T999`, **Then** the system reports an error indicating the task was not found.

---

### User Story 7 - View Pipeline Status (Priority: P3)

A developer wants to check the current progress of an ongoing or completed pipeline run.

**Why this priority**: Visibility into pipeline state is important but not blocking for core functionality.

**Independent Test**: Can be tested by running a pipeline partially and then running `orchestrator status` to see current stage, completed tasks, and overall progress.

**Acceptance Scenarios**:

1. **Given** an active pipeline run, **When** the user runs `orchestrator status`, **Then** the system displays the current stage, completed/pending tasks, and overall progress.
2. **Given** no active run in the project directory, **When** the user runs `orchestrator status`, **Then** the system reports that no run is in progress.

---

### User Story 8 - Review Pipeline with Feature-Gap Detection (Priority: P2)

During the review phase, reviewers may identify functionality that was specified but not implemented. The system should automatically detect these gaps and create supplementary tasks.

**Why this priority**: Feature-gap detection prevents incomplete implementations from passing review, which is a key quality gate.

**Independent Test**: Can be tested by providing an implementation that deliberately omits a specified feature, running the review, and verifying a supplementary task is created and executed.

**Acceptance Scenarios**:

1. **Given** an implementation that is missing functionality described in the spec, **When** the review pipeline detects "missing" or "unimplemented" patterns, **Then** the system creates supplementary tasks for the missing functionality.
2. **Given** supplementary tasks are created by feature-gap detection, **When** the TDD runner processes them, **Then** they follow the same RED-GREEN cycle as original tasks.

---

### User Story 9 - Use Wave Panel for Visual Monitoring (Priority: P3)

A developer wants a visual dashboard to monitor pipeline progress in real-time, without the Wave panel affecting core orchestrator functionality.

**Why this priority**: Nice-to-have visual monitoring. Core functionality must work without it.

**Independent Test**: Can be tested by running the orchestrator with and without the Wave panel enabled, verifying core behavior is identical in both cases.

**Acceptance Scenarios**:

1. **Given** the Wave panel is enabled, **When** the pipeline runs, **Then** the panel displays stage progress and task status in real-time.
2. **Given** the `ui/` package is removed or unavailable, **When** the pipeline runs, **Then** the core orchestrator functions normally without errors related to the missing UI.

---

### User Story 10 - Load Existing Agents Without Modification (Priority: P1)

The orchestrator must load the existing 14 ESSKILLAGENT agent directories with their knowledge bases, without requiring any changes to the agent definitions.

**Why this priority**: Agent compatibility is a hard constraint. Breaking existing agents would block adoption of v2.

**Independent Test**: Can be tested by pointing v2 at the existing ESSKILLAGENT agent directory and verifying all 14 agents load correctly with their knowledge base paths.

**Acceptance Scenarios**:

1. **Given** the existing ESSKILLAGENT agent directory with 14 agents, **When** the v2 agent registry loads them, **Then** all agents are registered with correct knowledge base paths and are callable.
2. **Given** an agent directory with a missing or malformed agent definition, **When** the registry attempts to load it, **Then** the system reports a clear error for the specific agent without affecting other agents.

---

### Edge Cases

- What happens when the SQLite database file is locked by another process during a write operation? The system should wait briefly and retry, then fail with a clear error.
- What happens when a CI run times out after the configured `ci_timeout`? The system should mark the task as failed with a timeout reason and allow retry.
- What happens when `asyncio.gather` raises an exception from one of the parallel agents? The other agents' results should be collected where possible; the failed agent's task should be marked as failed.
- What happens when the `.orchestrator.yaml` file is malformed YAML? The system should report the parse error with line number and fall back to global defaults.
- What happens when a task's `file_path` points to a file outside the project source directory? The system should reject the task with a clear scope violation error.
- What happens when the generator produces a task without the em-dash separator? The parser should reject the task and report the format violation, referencing the expected format.
- What happens when all tasks in a `[P]` group fail during Phase A (RED)? The system should report each failure individually and not proceed to Phase B.
- What happens when the `test_command` configured in `.orchestrator.yaml` does not exist on the system? The LocalCheckStrategy should fail fast with a clear error message on the first test attempt.

## Requirements

### Functional Requirements

#### Configuration System

- **FR-001**: System MUST load configuration in a defined layered order: `defaults.yaml` (global defaults), then `brownfield.yaml` (v1 compatibility), then `.orchestrator.yaml` (project-level override), where later values override earlier ones for matching keys.
- **FR-002**: System MUST support project-level configuration via a `.orchestrator.yaml` file placed in the project root directory.
- **FR-003**: System MUST warn the user when an unrecognized configuration key is found in `.orchestrator.yaml` but continue loading valid settings.
- **FR-004**: System MUST support configuration via environment variables as an additional override layer.

#### Pipeline Engine

- **FR-005**: System MUST execute the four-stage pipeline in fixed order: spec, plan, implement, acceptance.
- **FR-006**: System MUST enforce a review gate at the end of each stage; a stage cannot proceed to the next until its review passes or the auto-fix cycle exhausts retries.
- **FR-007**: System MUST save a checkpoint to the persistent store after each completed stage or significant sub-step, enabling resume from that point.
- **FR-008**: Engine module MUST remain under 300 lines, containing only stage flow control logic without concrete stage implementations.
- **FR-009**: System MUST support resuming a pipeline from the last saved checkpoint via the `resume` CLI command.
- **FR-010**: System MUST support resuming from a v1 `.workflow/workflow.db` database without schema modifications to v1 tables.

#### Stages

- **FR-011**: The spec stage MUST execute the sub-steps: constitution, specify, clarify, and review, in order.
- **FR-012**: The plan stage MUST execute the sub-steps: plan, research, tasks, and review, in order.
- **FR-013**: The implement stage MUST execute TDD cycles followed by review and push+CI verification.
- **FR-014**: The acceptance stage MUST produce a traceability matrix (FR to Task to Test) and complete a final review gate.
- **FR-015**: Each stage MUST share common review, gate, and checkpoint logic via a Stage base class.

#### TDD Runner

- **FR-016**: System MUST support both serial and parallel TDD task execution, determined by the `[P]` marker on tasks.
- **FR-017**: For serial tasks, the system MUST execute RED (test must fail) then GREEN (test must pass) sequentially for each task.
- **FR-018**: For parallel tasks (Phase A - RED), agents MUST run concurrently followed by a single batch commit and verification.
- **FR-019**: For parallel tasks (Phase B - GREEN), agents MUST run concurrently followed by a single batch commit, verification, and retry loop up to the configured `max_green_retries`.
- **FR-020**: System MUST limit `git add` scope to the project source directory, excluding `.workflow/` and other orchestrator-internal paths.

#### Task Parser and Validation

- **FR-021**: The task parser MUST enforce the canonical task format: `- [ ] T001 [P?] [US*?] [FR-###]+ Description — primary/file/path.ext`, using the em-dash as the primary separator for description and file path.
- **FR-022**: The parser MUST reject tasks that have the `[P]` marker but lack a `file_path`, reporting a clear error.
- **FR-023**: The parser MUST fall back to an `"in src/..."` pattern for file path extraction when no em-dash is present, but flag the task as non-canonical.
- **FR-024**: System MUST provide contract tests that validate parser and generator format alignment using sample generator output.
- **FR-025**: The parallel validator MUST detect overlapping `file_path` values among `[P]` tasks in the same group and demote conflicting tasks to serial execution.

#### Check Strategies

- **FR-026**: System MUST define a `CheckStrategy` abstract interface with two methods: `tests_must_fail` (RED) and `tests_must_pass` (GREEN), each returning a success boolean and detail string.
- **FR-027**: `LocalCheckStrategy` MUST execute the configured `test_command` locally and interpret the results.
- **FR-028**: `CICheckStrategy` MUST commit, push, and wait for GitHub Actions CI results, matching the commit SHA to the run ID.
- **FR-029**: Both check strategies MUST incorporate stack scoping: detecting the relevant stack (e.g., rust, frontend) from the `file_path` and evaluating only related CI jobs.
- **FR-030**: RED and GREEN evaluations MUST share the same `_evaluate_red` and `_evaluate_green` methods within each strategy, eliminating duplicate job-checking logic.
- **FR-031**: CI error feedback MUST be structured per-job, containing only the relevant stack trace, within a 2000-character budget per task.

#### Review Pipeline

- **FR-032**: System MUST perform three parallel reviews: code review, security review, and Brooks review (architectural review).
- **FR-033**: When a review fails, the system MUST trigger an auto-fix cycle: fixer agent addresses issues, then re-review occurs, up to `max_fix_retries`.
- **FR-034**: When a review detects "missing" or "unimplemented" functionality (feature-gap detection), the system MUST dynamically create supplementary tasks and feed them back into the TDD runner.

#### Agent System

- **FR-035**: System MUST maintain an agent registry that loads agent definitions and injects knowledge base paths progressively.
- **FR-036**: System MUST support session continuation (session resume) for agent calls, allowing multi-turn interactions within a stage.
- **FR-037**: System MUST load all existing ESSKILLAGENT agent directories (14 agents) without requiring modifications to agent definitions.
- **FR-038**: The agent adapter MUST support both Claude SDK and CLI invocation, with CLI as a fallback.

#### Persistent Store

- **FR-039**: System MUST use SQLite for state persistence, with all schema migrations managed in code.
- **FR-040**: The store MUST preserve v1 table structure (8 tables: tasks, reviews, evidence, stage_progress, step_status, lvl, checkpoints, settings) without modifying columns or types.
- **FR-041**: v2 MAY add new tables (e.g., `config_cache`) but MUST NOT alter v1 tables.
- **FR-042**: Query results MUST be wrapped in immutable data classes (`@dataclass(frozen=True)`), while underlying SQL remains v1-compatible.
- **FR-043**: System MUST record LVL (level) audit logs and maintain an evidence chain for all pipeline decisions.

#### UI Module

- **FR-044**: The Wave panel and desktop notification code MUST reside in a separate `ui/` package.
- **FR-045**: Core orchestrator modules MUST NOT import from the `ui/` package; the UI is an optional, independently loadable component.
- **FR-046**: The Wave panel MUST display stage progress and task status.
- **FR-047**: The system MUST support desktop notifications for stage completions and failures.

#### CLI

- **FR-048**: System MUST provide a `run` subcommand to start a new pipeline execution with a feature description.
- **FR-049**: System MUST provide a `resume` subcommand to continue from the last saved checkpoint.
- **FR-050**: System MUST provide a `retry <task_id>` subcommand to re-execute a single failed task.
- **FR-051**: System MUST provide a `status` subcommand to display current pipeline progress.

#### Concurrency Model

- **FR-052**: All asynchronous operations MUST use `asyncio` (single-threaded event loop).
- **FR-053**: SQLite write protection MUST use an `asyncio.Lock` instance created by the engine and injected into all components that write to the store.
- **FR-054**: After parallel agent calls via `asyncio.gather`, store writes MUST execute sequentially in a for-loop (no concurrent writes after gather).

### Non-Functional Requirements

- **NFR-001**: Every Python module MUST be under 400 lines of code.
- **NFR-002**: `engine.py` MUST be under 300 lines of code.
- **NFR-003**: All public APIs MUST have type annotations.
- **NFR-004**: No bare `except` clauses; all exception handlers MUST specify the exception type.
- **NFR-005**: Immutable data preferred: `dataclass(frozen=True)` for data models; no in-place dict mutation for strategy selection.
- **NFR-006**: Python 3.12+ is the minimum supported version.
- **NFR-007**: Test coverage MUST be 80% or above overall; `checks/` at 90%+; `tdd/parser.py` at 95%+; `store/` at 85%+.
- **NFR-008**: Naming conventions MUST follow the defined standard: snake_case modules, PascalCase classes, verb-prefixed public methods, underscore-prefixed private methods, UPPER_SNAKE constants, lower_snake config keys.

### Key Entities

- **Task**: A unit of work in the TDD pipeline. Attributes: task ID, description, file path, parallel marker, associated FRs and user stories, status (pending/red/green/failed), retry count.
- **Stage**: A pipeline phase (spec, plan, implement, acceptance). Attributes: stage name, status, sub-steps, checkpoint data.
- **Review**: An evaluation of stage output. Attributes: review type (code/security/brooks), verdict (pass/fail), findings, associated stage.
- **Evidence**: An audit record linking a decision to its justification. Attributes: timestamp, stage, action, detail, linked review or task.
- **StageProgress**: A persistent record of pipeline progress. Attributes: stage name, step name, status, timestamp.
- **CheckResult**: The outcome of a test strategy evaluation. Attributes: success (boolean), detail (string), job-level breakdown (for CI).
- **Configuration**: Merged configuration from all layers. Attributes: all config keys (models, test_command, local_test, ci_timeout, max_retries, etc.), source layer for each value.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All Python modules in the orchestrator are individually under 400 lines; engine.py is under 300 lines — verifiable by line count.
- **SC-002**: Switching between local and CI test strategies requires only a configuration change (`local_test: true/false`); no calling code changes are needed — verifiable by running the same task under both configurations.
- **SC-003**: All 14 existing ESSKILLAGENT agent directories load successfully without any modifications to agent definition files — verifiable by running the agent registry loader against the existing directory.
- **SC-004**: A v1 `brownfield.yaml` is loaded correctly, and a project-level `.orchestrator.yaml` successfully overrides its values — verifiable by creating both files with conflicting keys and checking resolved values.
- **SC-005**: The Wave panel code resides entirely in `ui/` and no core module contains imports from `ui/` — verifiable by static analysis of import statements.
- **SC-006**: The orchestrator can resume a run from a v1 `.workflow/workflow.db` database — verifiable by the integration test using a v1 database fixture.
- **SC-007**: CLI subcommands `run`, `resume`, `retry`, and `status` are all functional and produce expected outputs — verifiable by running each command in a test project.
- **SC-008**: Overall test coverage is 80% or above; `checks/` coverage is 90%+; `tdd/parser.py` coverage is 95%+; `store/` coverage is 85%+ — verifiable by coverage report.
- **SC-009**: All tests pass in CI (GitHub Actions) with no failures — verifiable by CI run status.
- **SC-010**: Contract tests confirm that the task parser correctly parses all sample outputs from the task generator — verifiable by running the contract test suite.
- **SC-011**: Parallel TDD tasks with non-overlapping file paths execute concurrently without git conflicts — verifiable by running a parallel task group and confirming batch commit succeeds.
- **SC-012**: CI error feedback for failed tasks contains only relevant stack information and stays within 2000 characters — verifiable by inspecting error output for CI-mode task failures.

## Assumptions

- **A-001**: The existing 14 ESSKILLAGENT agent directories follow the current agent definition format and will not change their structure during v2 development.
- **A-002**: The v1 `.workflow/workflow.db` schema (8 tables) is stable and will not receive further modifications in v1.
- **A-003**: GitHub Actions is the only CI provider that needs to be supported; other CI systems are out of scope.
- **A-004**: The `gh` CLI tool is available on the host system for CI integration commands.
- **A-005**: Claude Agent SDK is the primary invocation method, with CLI (`claude` command) as the fallback — consistent with v1 behavior.
- **A-006**: The Wave panel uses the H2O Wave framework, consistent with v1 — UI framework choice is inherited, not redesigned.
- **A-007**: Desktop notifications use OS-native notification mechanisms (e.g., `plyer` or equivalent) consistent with v1.
- **A-008**: All projects use git for version control; the orchestrator assumes a git repository is present in the project directory.
- **A-009**: The `asyncio` concurrency model is sufficient; multi-process parallelism is not needed for the expected workload.
- **A-010**: Environment variable overrides for configuration follow the pattern `ORCHESTRATOR_<UPPER_KEY>` (e.g., `ORCHESTRATOR_CI_TIMEOUT=2400`). This is a reasonable default pattern for environment-based configuration.
