# Feature Specification: E+S Orchestrator v2 Complete Rewrite

**Created**: 2026-04-01
**Status**: Draft
**Input**: User description: "E+S Orchestrator v2 complete rewrite - Python orchestrator managing AI agent four-stage TDD workflow (spec, plan, implement, acceptance) with modular architecture, strategy-based polymorphism, layered configuration, parallel TDD safety, and contract alignment."

---

## User Scenarios & Testing

### User Story 1 - Run a Full Four-Stage Pipeline (Priority: P1)

A user starts a new project and runs the orchestrator to execute the complete four-stage TDD pipeline (spec, plan, implement, acceptance). The orchestrator loads configuration, initializes agents, and progresses through each stage with review gates and checkpoints.

**Why this priority**: This is the core value proposition of the orchestrator. Without the pipeline, no other feature is meaningful.

**Independent Test**: Can be tested by running a minimal project through all four stages and verifying each stage produces expected artifacts and persists checkpoints.

**Acceptance Scenarios**:

1. **Given** a project directory with valid configuration and a requirement document, **When** the user runs `orchestrator run`, **Then** the orchestrator executes spec, plan, implement, and acceptance stages in sequence, each stage passing its review gate before advancing.
2. **Given** a project where the spec stage review gate fails, **When** the auto-fix loop triggers, **Then** the fixer agent corrects the issues and the stage is re-reviewed until it passes or the retry limit is reached.
3. **Given** a project with `skip_stages: [spec]` in configuration, **When** the user runs the pipeline, **Then** the spec stage is skipped and execution begins at the plan stage.
4. **Given** any project regardless of size or requirement complexity, **When** the pipeline starts, **Then** all stages execute (no automatic stage-skipping based on heuristics). (SPEC-010)

---

### User Story 2 - TDD RED-GREEN Cycle with Serial and Parallel Execution (Priority: P1)

A user's project has tasks generated from the plan stage. The orchestrator runs TDD cycles: RED phase (tests must fail), then GREEN phase (tests must pass), supporting both serial and parallel task execution.

**Why this priority**: TDD enforcement is the product's core discipline. Parallel execution is critical for throughput on larger projects.

**Independent Test**: Can be tested by providing a tasks.md file with both serial and `[P]` parallel tasks and verifying RED/GREEN phases complete correctly with proper batch commits.

**Acceptance Scenarios**:

1. **Given** a tasks.md with serial tasks, **When** the implement stage runs, **Then** each task executes RED then GREEN sequentially, with check strategy verifying test failure then test passage. (SPEC-020)
2. **Given** a tasks.md with `[P]` parallel tasks having non-overlapping file paths, **When** Phase A (RED) runs, **Then** agents execute in parallel followed by a single batch commit and CI check. (SPEC-021)
3. **Given** a tasks.md with `[P]` parallel tasks, **When** Phase B (GREEN) completes with some failures, **Then** the retry loop re-executes only failing tasks with per-job error feedback containing only the relevant stack trace. (SPEC-022)
4. **Given** a `[P]` task without a `file_path`, **When** the parser validates the task, **Then** the task is rejected with an error message. (SPEC-023)
5. **Given** two `[P]` tasks in the same group with overlapping `file_path`, **When** the validator runs, **Then** the tasks fall back to serial execution. (SPEC-024)
6. **Given** parallel agents completing GREEN phase, **When** `git add` is invoked, **Then** only files within the project source directory are staged (excluding `.workflow/`, `.git/`, `node_modules/`). (SPEC-025)

---

### User Story 3 - Check Strategy Switching (Local vs CI) (Priority: P1)

A user configures whether tests run locally or via CI. The orchestrator uses the appropriate check strategy without any code changes to calling modules.

**Why this priority**: This directly addresses the v1 CHECKERS dict mutation bug and is fundamental to the strategy-based architecture.

**Independent Test**: Can be tested by switching `local_test` configuration and verifying both LocalCheckStrategy and CICheckStrategy correctly evaluate RED/GREEN conditions.

**Acceptance Scenarios**:

1. **Given** configuration with `local_test: true`, **When** a RED check runs, **Then** LocalCheckStrategy executes tests locally and verifies they fail. (SPEC-030)
2. **Given** configuration with `local_test: false`, **When** a RED check runs, **Then** CICheckStrategy triggers CI, waits for results, and verifies tests fail. (SPEC-031)
3. **Given** a CICheckStrategy instance, **When** evaluating test results, **Then** stack scoping filters CI jobs to only those relevant to the task's technology stack. (SPEC-032)
4. **Given** a CI job with status `skipped` or `cancelled`, **When** test results are evaluated, **Then** the job is NOT treated as passing; instead the check strategy applies the configured failure condition for each status. (SPEC-033)
5. **Given** a CI check that fails, **When** error feedback is returned, **Then** the log is structured per-job with a maximum of 2000 characters per job, using `startswith` for job name matching. (SPEC-034)

---

### User Story 4 - Layered Configuration Loading (Priority: P2)

A user has a global defaults.yaml, an existing brownfield.yaml (v1 format), and a project-specific .orchestrator.yaml. The orchestrator merges them in order, with later files overriding earlier ones.

**Why this priority**: Configuration layering enables project-specific customization and v1 backward compatibility.

**Independent Test**: Can be tested by creating config files at each layer with conflicting values and verifying the final merged configuration reflects the correct override order.

**Acceptance Scenarios**:

1. **Given** `defaults.yaml` with key `ci_timeout: 300` and `.orchestrator.yaml` with `ci_timeout: 600`, **When** configuration loads, **Then** the effective value is `600`. (SPEC-040)
2. **Given** a v1-format `brownfield.yaml`, **When** configuration loads, **Then** all v1 configuration keys are correctly interpreted. (SPEC-041)
3. **Given** an environment variable `ORCHESTRATOR_CI_TIMEOUT=900`, **When** configuration loads, **Then** the environment variable overrides all file-based values. (SPEC-042)
4. **Given** no `.orchestrator.yaml` in the project directory, **When** configuration loads, **Then** only defaults.yaml and brownfield.yaml apply without error. (SPEC-043)

---

### User Story 5 - CLI Sub-Commands (Priority: P2)

A user interacts with the orchestrator via CLI sub-commands: run, resume, retry, and status.

**Why this priority**: CLI is the primary user interface and supports key operational workflows including recovery.

**Independent Test**: Can be tested by invoking each sub-command and verifying correct behavior.

**Acceptance Scenarios**:

1. **Given** a project directory, **When** the user runs `orchestrator run`, **Then** a new pipeline execution starts from the spec stage. (SPEC-050)
2. **Given** a previously interrupted pipeline with a checkpoint at the plan stage, **When** the user runs `orchestrator resume`, **Then** execution continues from the plan stage. (SPEC-051)
3. **Given** a failed task T003, **When** the user runs `orchestrator retry T003`, **Then** only task T003 is re-executed. (SPEC-052)
4. **Given** a running or completed pipeline, **When** the user runs `orchestrator status`, **Then** the current pipeline progress is displayed including stage, task status, and completion percentage. (SPEC-053)

---

### User Story 6 - Checkpoint, Resume, and Persistence (Priority: P2)

The orchestrator persists state to SQLite so that execution can be resumed after interruption. The v2 store must be able to read v1's workflow.db.

**Why this priority**: Resume capability prevents wasted work on long-running pipelines, and DB compatibility enables migration.

**Independent Test**: Can be tested by interrupting a pipeline mid-stage, then resuming and verifying continuation from checkpoint.

**Acceptance Scenarios**:

1. **Given** a pipeline that completed the spec stage, **When** the process is interrupted, **Then** a checkpoint is persisted to SQLite with the completed stage and all state needed for resume. (SPEC-060)
2. **Given** a v1 workflow.db file, **When** the v2 orchestrator opens it, **Then** all existing tables and data are readable without schema migration. (SPEC-061)
3. **Given** v2 needs additional tables, **When** the store initializes, **Then** new tables are created alongside existing v1 tables without altering v1 table structure. (SPEC-062)
4. **Given** a task completes and its `file_path` changes during execution, **When** the result is persisted, **Then** the store uses INSERT OR REPLACE to ensure the latest `file_path` is recorded. (SPEC-063)

---

### User Story 7 - Tasks.md Parsing and Contract Alignment (Priority: P2)

The tasks.md parser strictly validates the format contract between the task generator and parser, rejecting entries that violate the contract.

**Why this priority**: Format misalignment was a critical v1 bug causing silent failures in parallel execution.

**Independent Test**: Can be tested with valid and invalid tasks.md entries, verifying parsing correctness and rejection of malformed entries.

**Acceptance Scenarios**:

1. **Given** a tasks.md entry `- [ ] T001 [P] [US1] [FR-001] Implement login -- src/auth.py`, **When** the parser processes it, **Then** task_id=T001, parallel=true, user_story=US1, requirements=[FR-001], description="Implement login", file_path="src/auth.py" are extracted. (SPEC-070)
2. **Given** a tasks.md entry missing the em-dash separator, **When** the parser processes it, **Then** the entry is rejected with a clear error message at startup. (SPEC-071)
3. **Given** a tasks.md with entries in non-sequential order, **When** the parser loads tasks, **Then** tasks are sorted by their numeric ID (T001, T002, ...) to ensure deterministic execution order. (SPEC-072)
4. **Given** a contract test suite, **When** the task generator produces output, **Then** the parser can successfully parse every generated entry without errors. (SPEC-073)
5. **Given** a task entry with `[P]` flag but no file_path after the em-dash, **When** the parser validates it, **Then** the entry is rejected with an error. (SPEC-074)

---

### User Story 8 - Agent Registry and Progressive Knowledge Loading (Priority: P2)

The orchestrator loads 14 existing ESSKILLAGENT agent directories and injects knowledge base paths progressively as stages advance, without requiring modifications to the agent directories.

**Why this priority**: Agent compatibility ensures the existing agent ecosystem works without rework.

**Independent Test**: Can be tested by loading all 14 agent directories and verifying each agent's knowledge base path injection uses absolute paths.

**Acceptance Scenarios**:

1. **Given** 14 existing ESSKILLAGENT agent directories, **When** the agent registry loads, **Then** all agents are registered without requiring any modification to the agent directories. (SPEC-080)
2. **Given** an agent entering the plan stage, **When** knowledge is loaded, **Then** only knowledge relevant to the current and prior stages is injected, using absolute file paths. (SPEC-081)
3. **Given** an agent session that was previously created, **When** a follow-up call is needed, **Then** session continuation resumes the existing session rather than creating a new one. (SPEC-082)

---

### User Story 9 - Three-Way Parallel Review and Auto-Fix (Priority: P2)

After TDD implementation, three review agents (code, security, brooks) run in parallel. Failures trigger an auto-fix loop.

**Why this priority**: Review quality directly impacts the reliability of shipped code.

**Independent Test**: Can be tested by simulating review results (pass/fail) and verifying auto-fix loop behavior.

**Acceptance Scenarios**:

1. **Given** implementation stage output, **When** review runs, **Then** code review, security review, and brooks review execute in parallel. (SPEC-090)
2. **Given** a code review failure, **When** the auto-fix loop triggers, **Then** the fixer agent applies corrections and the review is re-run. (SPEC-091)
3. **Given** a review that identifies a missing feature, **When** feature-gap detection triggers, **Then** supplemental tasks are dynamically created and execution re-enters the TDD phase. (SPEC-092)

---

### User Story 10 - Resilient External Operations (Priority: P3)

Network and subprocess operations (git push, gh CLI, Claude SDK/CLI calls) implement retry with configurable attempts and backoff.

**Why this priority**: Transient failures should not permanently mark tasks as failed.

**Independent Test**: Can be tested by simulating transient failures and verifying retry behavior.

**Acceptance Scenarios**:

1. **Given** a `git push` that fails due to a transient network error, **When** the retry policy is active, **Then** the operation retries up to the configured attempt count with backoff. (SPEC-100)
2. **Given** a subprocess call, **When** the process times out, **Then** `TimeoutExpired` is caught and handled (not silently ignored). (SPEC-101)
3. **Given** a subprocess call to a binary that does not exist, **When** `FileNotFoundError` is raised, **Then** it is caught and a clear error message is reported. (SPEC-102)
4. **Given** a project not initialized with git, **When** the pipeline starts, **Then** the orchestrator checks for git initialization and reports an error before proceeding. (SPEC-103)

---

### User Story 11 - Stack Scoping and Technology Detection (Priority: P3)

The orchestrator detects the technology stack of each task and scopes CI checks to only relevant jobs. Stack detection supports extensible technology registration.

**Why this priority**: Stack scoping prevents false positives from unrelated CI jobs and enables multi-stack projects.

**Independent Test**: Can be tested by providing tasks with different file types and verifying correct stack classification and CI job filtering.

**Acceptance Scenarios**:

1. **Given** a task with file_path `src/auth.rs`, **When** stack detection runs, **Then** the task is classified as `rust` stack. (SPEC-110)
2. **Given** a task classified as `rust`, **When** CI jobs are evaluated, **Then** only Rust-related CI jobs are checked (not frontend or Python jobs). (SPEC-111)
3. **Given** a file in `tests/` directory with `.py` extension, **When** stack detection runs, **Then** the file is classified as `python` (not `frontend`), using both extension and path prefix for classification. (SPEC-112)
4. **Given** a new technology stack `go`, **When** the user adds it to the stack configuration, **Then** the orchestrator recognizes `.go` files and maps them to configured CI jobs without code changes. (SPEC-113)
5. **Given** CI job names, **When** the orchestrator maps tasks to jobs, **Then** job names are read from configuration rather than hardcoded. (SPEC-114)

---

### User Story 12 - Wave Panel and Desktop Notifications (Priority: P3)

The Wave panel UI and desktop notifications are available as optional modules, fully decoupled from the core orchestrator.

**Why this priority**: UI is a nice-to-have feature that must not impact core stability.

**Independent Test**: Can be tested by verifying core modules have no import of `ui/` and that Wave panel loads independently.

**Acceptance Scenarios**:

1. **Given** the core orchestrator modules, **When** imports are analyzed, **Then** no core module imports from the `ui/` package. (SPEC-120)
2. **Given** the Wave panel is installed, **When** the orchestrator runs, **Then** the Wave panel displays real-time pipeline progress. (SPEC-121)
3. **Given** the Wave panel is NOT installed, **When** the orchestrator runs, **Then** the core pipeline functions normally without errors. (SPEC-122)
4. **Given** a stage completes, **When** desktop notifications are enabled, **Then** the user receives a notification. (SPEC-123)

---

### User Story 13 - Traceability Matrix (Priority: P3)

The orchestrator generates a traceability matrix mapping functional requirements (FR) to tasks and tests.

**Why this priority**: Traceability ensures completeness of implementation against specification.

**Independent Test**: Can be tested by running a completed pipeline and verifying the matrix correctly maps FR to tasks to tests.

**Acceptance Scenarios**:

1. **Given** a completed pipeline with FR-001 linked to tasks T001 and T002, **When** the traceability matrix is generated, **Then** FR-001 shows links to T001, T002, and their associated test results. (SPEC-130)
2. **Given** an FR with no linked task, **When** the matrix is generated, **Then** the gap is flagged as unimplemented. (SPEC-131)

---

### User Story 14 - Task Grouping and Ordering (Priority: P3)

Tasks are grouped into setup, user-story (US*), and polish categories, with deterministic numeric ordering within each group.

**Why this priority**: Correct ordering prevents execution dependency issues discovered in v1.

**Independent Test**: Can be tested by providing tasks with mixed group types and verifying correct grouping and sort order.

**Acceptance Scenarios**:

1. **Given** tasks with labels `setup`, `US1`, `US2`, and `polish`, **When** the runner organizes execution, **Then** setup tasks run first, then US-grouped tasks in order, then polish tasks last. (SPEC-140)
2. **Given** tasks T003, T001, T002 in a group, **When** sorting is applied, **Then** execution order is T001, T002, T003 (numeric sort). (SPEC-141)
3. **Given** a polish task, **When** the grouping logic runs, **Then** it is assigned to the `polish` group (not `setup` as in v1). (SPEC-142)

---

### Edge Cases

- **SPEC-EC01**: What happens when `.orchestrator.yaml` contains invalid YAML? The orchestrator reports a clear parsing error and halts.
- **SPEC-EC02**: What happens when a CI run never completes within the configured timeout? The check strategy reports a timeout failure and the task enters the retry loop.
- **SPEC-EC03**: What happens when all agents in a parallel group fail? All failures are collected and reported; the pipeline enters the configured failure handling mode.
- **SPEC-EC04**: What happens when the SQLite database file is locked by another process? The orchestrator waits with backoff and retries, then fails with a clear error message.
- **SPEC-EC05**: What happens when a `git add` attempts to stage files outside the project source directory? The operation is blocked and an error is logged.
- **SPEC-EC06**: What happens when a tasks.md has zero tasks? The implement stage reports an error and halts.
- **SPEC-EC07**: What happens when the same task ID appears twice in tasks.md? The parser rejects the file with a duplicate ID error.

---

## Requirements

### Functional Requirements

#### Pipeline and Stage Management

- **FR-001**: System MUST execute a four-stage pipeline (spec, plan, implement, acceptance) in sequence, each stage passing a review gate before advancing.
- **FR-002**: System MUST persist a checkpoint to SQLite after each stage completes, enabling resume from the last checkpoint.
- **FR-003**: System MUST support explicit stage skipping via `skip_stages` configuration. No automatic stage-skipping based on heuristics.
- **FR-004**: System MUST enforce review gates at each stage: a stage MUST NOT advance until its review passes.
- **FR-005**: Engine module MUST contain only stage flow-control logic, delegating all stage-specific behavior to the `stages/` sub-package.

#### TDD Execution

- **FR-006**: System MUST support serial TDD execution: RED phase (test must fail) followed by GREEN phase (test must pass) for each task.
- **FR-007**: System MUST support parallel TDD execution for tasks marked with `[P]` flag, with Phase A (parallel RED then batch commit+CI) and Phase B (parallel GREEN then batch commit+CI with retry).
- **FR-008**: System MUST reject `[P]` tasks that lack a `file_path`.
- **FR-009**: System MUST detect overlapping `file_path` values among `[P]` tasks in the same group and fall back to serial execution.
- **FR-010**: System MUST limit `git add` scope to project source directories, excluding `.workflow/`, `.git/`, and `node_modules/`.
- **FR-011**: GREEN retry MUST provide per-job error feedback containing only the relevant stack trace for the failing task.

#### Check Strategy

- **FR-012**: System MUST provide a CheckStrategy abstract interface with `tests_must_fail` and `tests_must_pass` methods.
- **FR-013**: System MUST implement LocalCheckStrategy for local test execution and CICheckStrategy for CI-based test execution.
- **FR-014**: Switching between local and CI check strategies MUST be achieved solely through configuration, with no changes to calling code.
- **FR-015**: CICheckStrategy MUST implement stack scoping, filtering CI jobs to only those relevant to the task's technology stack.
- **FR-016**: CI job status `skipped` or `cancelled` MUST NOT be treated as passing; each status MUST have a defined failure condition.
- **FR-017**: CI error logs MUST be structured per-job with a maximum of 2000 characters per job.
- **FR-018**: CI job name matching MUST use `startswith` prefix matching (not substring matching).

#### Configuration

- **FR-019**: System MUST load configuration in layered order: `defaults.yaml`, then `brownfield.yaml` (v1 compatibility), then `.orchestrator.yaml` (project override), with later sources overriding earlier ones.
- **FR-020**: System MUST support environment variable overrides for any configuration key.
- **FR-021**: System MUST accept and correctly interpret v1-format `brownfield.yaml` files.

#### Tasks Parsing and Contract

- **FR-022**: Task parser MUST parse entries in the format: `- [ ] T001 [P?] [US*?] [FR-###]+ Description -- primary/file/path.ext`.
- **FR-023**: Task parser MUST reject entries that violate the format contract and report violations at startup.
- **FR-024**: Tasks MUST be sorted by numeric ID for deterministic execution order.
- **FR-025**: Contract tests MUST verify that the task generator output is parseable by the task parser.
- **FR-026**: Task grouping MUST classify tasks into setup, user-story (US*), and polish groups, with setup first, then US groups in order, then polish last.

#### Agent Management

- **FR-027**: Agent registry MUST load all 14 existing ESSKILLAGENT agent directories without requiring modifications to agent directories.
- **FR-028**: Knowledge base injection MUST use absolute file paths and load progressively as stages advance.
- **FR-029**: Session continuation MUST resume existing agent sessions rather than creating new ones.

#### Review and Quality

- **FR-030**: System MUST run three-way parallel review (code, security, brooks) after implementation.
- **FR-031**: Auto-fix loop MUST trigger on review failure: fixer agent corrects issues, then re-review runs.
- **FR-032**: Feature-gap detection MUST dynamically create supplemental tasks when a review identifies missing functionality.

#### Persistence and Store

- **FR-033**: Store MUST use SQLite for persistence with `asyncio.Lock` coordination for write operations.
- **FR-034**: Store MUST read v1 workflow.db without schema migration on existing tables.
- **FR-035**: Store MAY create new tables; existing v1 tables and columns MUST NOT be altered.
- **FR-036**: Store MUST use INSERT OR REPLACE when updating task records to ensure `file_path` and other mutable fields are current.
- **FR-037**: Store MUST maintain LVL audit logs and evidence chain for all pipeline operations.

#### CLI

- **FR-038**: CLI MUST provide `run` sub-command to start a new pipeline execution.
- **FR-039**: CLI MUST provide `resume` sub-command to continue from the last checkpoint.
- **FR-040**: CLI MUST provide `retry <task_id>` sub-command to re-execute a single task.
- **FR-041**: CLI MUST provide `status` sub-command to display current pipeline progress.

#### Resilience

- **FR-042**: All network and subprocess operations MUST implement retry with configurable attempt count and backoff.
- **FR-043**: Subprocess calls MUST catch `FileNotFoundError` and `subprocess.TimeoutExpired`.
- **FR-044**: System MUST verify git initialization at startup and report errors if not initialized.

#### Stack Scoping

- **FR-045**: Stack detection MUST support extensible technology registration via configuration (not hardcoded if-elif chains).
- **FR-046**: File classification MUST use both file extension and path prefix for stack determination (e.g., `tests/*.py` is `python`, not `frontend`).
- **FR-047**: CI job name mapping MUST be loaded from configuration.

#### UI Decoupling

- **FR-048**: Core orchestrator modules MUST NOT import from the `ui/` package.
- **FR-049**: Wave panel MUST function as an optional module; core pipeline MUST work without it.
- **FR-050**: Desktop notifications MUST be an optional feature enabled via configuration.

#### Traceability

- **FR-051**: System MUST generate a traceability matrix mapping FR to tasks to tests.
- **FR-052**: Traceability matrix MUST flag FRs with no linked tasks as unimplemented.

#### Module Structure

- **FR-053**: Every Python module MUST be under 400 lines. Engine.py MUST be under 300 lines.
- **FR-054**: All public APIs MUST carry type annotations.
- **FR-055**: Data transfer objects MUST use `@dataclass(frozen=True)`.
- **FR-056**: No bare `except:` clauses; every except MUST specify an exception type.
- **FR-057**: Exception chaining (`raise X from Y`) MUST be used when re-raising.

#### Concurrency

- **FR-058**: System MUST use asyncio single-threaded event loop for concurrency.
- **FR-059**: SQLite write operations MUST be coordinated via `asyncio.Lock` created by engine.py and injected into all writing components.

### Key Entities

- **Pipeline**: A single execution of the four-stage workflow for a project. Contains stages, configuration, and checkpoint state.
- **Stage**: One phase of the pipeline (spec, plan, implement, acceptance). Has a review gate and checkpoint.
- **Task**: A unit of work within the implement stage. Has a task_id, optional parallel flag, user story link, FR links, description, and file_path.
- **CheckStrategy**: An abstract interface for test verification. Implementations include LocalCheckStrategy and CICheckStrategy.
- **Agent**: A registered AI agent with knowledge base paths. Managed by the registry, invoked through session adapters.
- **Session**: A conversation continuation handle for agent interactions.
- **Configuration**: A merged view of defaults.yaml, brownfield.yaml, and .orchestrator.yaml with environment variable overrides.
- **Checkpoint**: A persisted state snapshot enabling pipeline resume after interruption.
- **ReviewResult**: The outcome of a code/security/brooks review, including pass/fail and findings.
- **TraceabilityMatrix**: A mapping from functional requirements to tasks to test results.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: All Python modules are individually verifiable as under 400 lines, with engine.py under 300 lines.
- **SC-002**: Switching between local and CI test strategies requires only a configuration change; no source code modifications.
- **SC-003**: All 14 existing ESSKILLAGENT agent directories load successfully without any modification to agent files.
- **SC-004**: v1-format brownfield.yaml files are correctly loaded, and .orchestrator.yaml project overrides take effect.
- **SC-005**: No core module contains any import from the ui/ package.
- **SC-006**: A v1 workflow.db file is readable by the v2 store, and pipeline execution can resume from v1 checkpoint data.
- **SC-007**: All four CLI sub-commands (run, resume, retry, status) complete successfully for their intended use cases.
- **SC-008**: Test coverage reaches 80% overall, 90% for checks/, 95% for tdd/parser.py, and 85% for store/.
- **SC-009**: Contract tests verify parser/generator format alignment with zero format mismatches.
- **SC-010**: Parallel TDD tasks with file_path conflicts automatically fall back to serial execution without user intervention.
- **SC-011**: CI error feedback per job stays within the 2000-character budget and contains only relevant stack information.
- **SC-012**: Pipeline checkpoint and resume works correctly: resuming after interruption continues from the last completed stage without re-executing completed work.

---

## Assumptions

- **A-001**: The 14 existing ESSKILLAGENT agent directories follow a consistent structure (each has a knowledge base directory and agent configuration).
- **A-002**: The target execution environment has Python 3.12+ installed.
- **A-003**: GitHub Actions is the CI platform; CI job structure follows the pattern defined in the project's workflow files.
- **A-004**: The Claude Agent SDK is available for agent invocation, with CLI as fallback.
- **A-005**: SQLite is sufficient for persistence needs; no distributed database is required.
- **A-006**: The v1 brownfield.yaml format is stable and will not change.
- **A-007**: Desktop notification support depends on the host OS notification system being available; failure to send a notification does not block the pipeline.
- **A-008**: Retry policies use exponential backoff with jitter as the default strategy, configurable via configuration files.
- **A-009**: The asyncio concurrency model is sufficient for all parallel operations; no multi-process parallelism is needed.
- **A-010**: The em-dash (`--`) in tasks.md format is the canonical separator (consistent with constitution V. Contract Alignment).
