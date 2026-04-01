# Feature Specification: E+S Orchestrator v2 — Autonomous Four-Stage TDD Orchestration

**Created**: 2026-04-02
**Status**: Draft
**Input**: User description: "E+S Orchestrator v2 complete rewrite — autonomous four-stage TDD pipeline with perception, decision-making, feedback loops, and self-correction capabilities"

---

## User Scenarios & Testing

### User Story 1 - Full Pipeline Run (Priority: P1)

A developer initiates a complete four-stage pipeline run (spec, plan, implement, acceptance) from the CLI. The orchestrator drives each stage autonomously, calling the appropriate AI agents, running TDD cycles, performing reviews, and producing a fully tested implementation with traceability.

**Why this priority**: This is the core value proposition of the orchestrator. Without a working end-to-end pipeline, no other feature matters.

**Independent Test**: Can be tested by running `run` on a small feature description and verifying that all four stages complete, producing spec, plan, tasks, implementation code, passing tests, and an acceptance report.

**Acceptance Scenarios**:

1. **Given** a git repository with a feature description, **When** the user runs the `run` command, **Then** the orchestrator executes spec, plan, implement, and acceptance stages in order, producing all required artifacts.
2. **Given** a running pipeline, **When** a stage completes successfully, **Then** its artifacts are frozen with content hashes and a `stage_complete` event is recorded before the next stage begins.
3. **Given** a running pipeline, **When** spec-writer output contains `[NC:]` markers or uncertainty indicators, **Then** the orchestrator triggers the clarify agent before proceeding.
4. **Given** a running pipeline, **When** planner output contains `[NR:]` markers or research-related keywords, **Then** the orchestrator triggers the research agent before task generation.

---

### User Story 2 - Resume from Checkpoint (Priority: P1)

A developer resumes a previously interrupted pipeline from the last successful checkpoint without re-executing completed stages or tasks.

**Why this priority**: Pipeline runs are long and expensive. Losing progress due to interruptions (network, crash, timeout) would make the tool impractical.

**Independent Test**: Can be tested by running a pipeline, killing it mid-stage, then running `resume` and verifying it picks up from the correct point.

**Acceptance Scenarios**:

1. **Given** a pipeline that was interrupted during the implement stage with 3 of 5 tasks completed, **When** the user runs `resume`, **Then** the orchestrator skips the 3 completed tasks and continues from task 4.
2. **Given** a pipeline that was interrupted during the plan stage, **When** the user runs `resume`, **Then** the orchestrator re-runs the plan stage from the beginning (stages are atomic; see atomicity rule below).
3. **Given** no previous pipeline state exists, **When** the user runs `resume`, **Then** the orchestrator reports an error indicating no checkpoint found.

**Stage Atomicity Rule**: The spec, plan, and acceptance stages are atomic — if interrupted, they must be re-run from the beginning on resume because their outputs are single coherent artifacts (spec.md, plan.md, traceability.md) that cannot be partially produced. The implement stage is NOT atomic — it supports task-level checkpointing because it consists of independent TDD cycles for each task, and completed tasks are recorded individually in the store.

---

### User Story 3 - Retry Single Task (Priority: P2)

A developer retries a specific BLOCKED task after resolving the underlying issue, without re-running the entire pipeline.

**Why this priority**: Individual tasks can fail for transient reasons. Targeted retry saves significant time compared to full re-runs.

**Independent Test**: Can be tested by marking a task as BLOCKED, then running `retry <task_id>` and verifying only that task is re-executed.

**Acceptance Scenarios**:

1. **Given** a task in BLOCKED status, **When** the user runs `retry <task_id>`, **Then** the orchestrator re-executes only that task's TDD cycle (RED, GREEN, review).
2. **Given** a task in DONE status, **When** the user runs `retry <task_id>`, **Then** the orchestrator rejects the request with a message explaining the task is already complete.

---

### User Story 4 - Pipeline Status Dashboard (Priority: P2)

A developer checks the current progress and health of a pipeline run, seeing stage completion, task statuses, and any issues.

**Why this priority**: Visibility into pipeline state is essential for developers to understand progress and diagnose problems.

**Independent Test**: Can be tested by running `status` at various pipeline points and verifying accurate progress reporting.

**Acceptance Scenarios**:

1. **Given** a pipeline in progress with mixed task statuses, **When** the user runs `status`, **Then** the orchestrator displays stage completion, task counts by status (pending/running/done/blocked), and any active warnings.
2. **Given** no active pipeline, **When** the user runs `status`, **Then** the orchestrator reports that no pipeline is active.

---

### User Story 5 - Autonomous BLOCKED Handling and Self-Correction (Priority: P2)

The orchestrator autonomously detects when too many tasks are BLOCKED and takes corrective action rather than blindly continuing.

**Why this priority**: Without self-correction, the orchestrator would waste resources on a failing pipeline. This is a key differentiator for v2's autonomy.

**Independent Test**: Can be tested by simulating a high BLOCKED ratio and verifying the orchestrator pauses and suggests corrective action.

**Acceptance Scenarios**:

1. **Given** a single task fails during implement, **When** the task is marked BLOCKED, **Then** the orchestrator skips it, continues with remaining tasks, and includes it in the final summary report.
2. **Given** the BLOCKED task ratio exceeds 50% of tasks in the current batch, **When** the monitor detects this, **Then** the orchestrator pauses execution and suggests rolling back to an earlier stage.
3. **Given** a stage-level BLOCKED condition (all remaining tasks are BLOCKED), **When** the orchestrator detects it, **Then** it requests human intervention or applies automatic degraded processing.

---

### User Story 6 - CI Mode Execution (Priority: P2)

The orchestrator runs in CI mode where test execution happens via GitHub Actions rather than locally, with proper commit, push, and CI result polling.

**Why this priority**: CI mode enables the orchestrator to work in environments where local execution is insufficient or where CI validation is mandatory. Many projects require CI as the authoritative test environment due to platform-specific dependencies, integration test infrastructure, or organizational policy.

**Independent Test**: Can be tested by configuring CI mode and verifying that test commands trigger CI workflows and poll for results.

**Acceptance Scenarios**:

1. **Given** CI check strategy is configured, **When** a TDD step requires test validation, **Then** the orchestrator commits changes, pushes to the remote, triggers the CI workflow, and polls for results.
2. **Given** a CI push fails due to conflicts, **When** the push is retried, **Then** the orchestrator retries up to 3 times before marking the step as failed.
3. **Given** different project stacks (Python, Rust, frontend), **When** CI strategy detects the stack, **Then** it maps to the correct CI job name.

---

### User Story 7 - Three-Way Review with Auto-Fix (Priority: P2)

After GREEN phase, the orchestrator runs code-review, security-review, and brooks-review in parallel, then auto-fixes issues in a convergent loop.

**Why this priority**: Automated review and fix cycles are central to the quality assurance promise. Without them, code quality depends entirely on the implementing agent.

**Independent Test**: Can be tested by producing code with known issues and verifying the review pipeline detects and fixes them.

**Acceptance Scenarios**:

1. **Given** a completed GREEN phase, **When** the review pipeline runs, **Then** three reviewers (code, security, brooks) execute in parallel and their findings are merged.
2. **Given** review findings exist, **When** the fixer agent is invoked, **Then** it addresses issues from each review source with appropriate context.
3. **Given** a fix attempt does not reduce the issue count compared to the previous attempt, **When** convergence is checked, **Then** the orchestrator terminates the fix loop and marks the task as BLOCKED. The maximum number of fix attempts is 3 (configurable via `max_fix_retries` in defaults.yaml).

---

### User Story 8 - LVL Evidence Chain Integrity (Priority: P3)

The orchestrator maintains a complete evidence chain via LVL events and artifacts, ensuring every decision and state transition is traceable and verifiable.

**Why this priority**: Traceability is critical for debugging, auditing, and acceptance. It is a foundation for trust in autonomous decisions.

**Independent Test**: Can be tested by running a pipeline and verifying that all invariants (INV-1 through INV-4) hold in the database.

**Acceptance Scenarios**:

1. **Given** a stage completes, **When** the LVL system records the completion, **Then** a `stage_complete` event exists AND all required artifacts are frozen AND content hashes match actual files.
2. **Given** a stage is about to start, **When** preconditions are checked, **Then** the previous stage must be complete with frozen, non-stale artifacts.
3. **Given** an artifact is modified after freezing, **When** staleness is checked, **Then** the artifact and its dependents are marked stale via cascade invalidation.
4. **Given** a task execution, **When** events are recorded, **Then** `red_pass` must precede `green_start` for every task.

---

### User Story 9 - Wave Dashboard Monitoring (Priority: P3)

A developer launches an optional web-based dashboard to monitor pipeline progress visually in real time.

**Why this priority**: Visual monitoring is a nice-to-have that improves developer experience but is not required for core functionality.

**Independent Test**: Can be tested by launching the Wave panel and verifying it displays current pipeline state.

**Acceptance Scenarios**:

1. **Given** the Wave panel is configured, **When** the user launches it, **Then** a web dashboard displays current stage, task progress, and recent events.

---

### User Story 10 - Acceptance Stage with Traceability Matrix (Priority: P3)

The orchestrator runs a final acceptance stage that validates all requirements are covered and produces a traceability matrix.

**Why this priority**: Acceptance ensures completeness. Without it, the pipeline may produce code that passes tests but misses requirements.

**Independent Test**: Can be tested by completing an implement stage and running acceptance to verify a traceability matrix is produced.

**Acceptance Scenarios**:

1. **Given** the implement stage is complete, **When** the acceptance stage runs, **Then** the acceptor agent produces a structured traceability matrix mapping requirements to tests.
2. **Given** the traceability matrix is produced, **When** final review runs, **Then** any gaps between requirements and implementation are identified.

---

### Edge Cases

- What happens when the orchestrator is started outside a git repository? (Must fail with clear error per R01)
- What happens when all tasks in a batch are BLOCKED? (Stage-level BLOCKED handling triggers)
- What happens when a session expires mid-agent-call? (Session manager handles expiry gracefully)
- What happens when CI is unreachable during CI mode? (Retry with timeout, then fail gracefully)
- What happens when the SQLite database is corrupted? (Graceful error, no silent data loss)
- What happens when two orchestrator instances target the same project? (Process lock prevents concurrent runs)
- What happens when an agent produces output missing required markers? (Heuristic scanning as fallback)
- What happens when a frozen artifact's file is deleted from disk? (Staleness check detects hash mismatch)
- What happens when `resume` is called but the checkpoint stage no longer has valid preconditions? (Re-validate preconditions before resuming)
- What happens when a fix attempt introduces new issues equal to or greater than the previous count? (Convergence failure detected; fix loop terminates, task marked BLOCKED)
- What happens when `max_fix_retries` is reached without convergence check triggering? (Loop terminates at the retry limit regardless; task marked BLOCKED if issues remain)

---

## Requirements

### Functional Requirements

#### Domain: Infrastructure (P0)

- **FR-001**: System MUST provide session management with `expire_session(session_id)` and `list_sessions()` capabilities in the agent adapter, with session continuation working correctly across RED, GREEN, and review phases. (P0-A)
- **FR-002**: System MUST enforce adapter module size below 400 lines. (P0-A)
- **FR-003**: System MUST provide an immutable EngineContext containing store, working directory, config, session manager, check strategy, notifier, and store lock. (P0-B1)
- **FR-004**: System MUST enforce context module size below 50 lines. (P0-B1)
- **FR-005**: System MUST provide asynchronous check strategies where `tests_must_fail` and `tests_must_pass` return a structured result containing pass status, output text, and attempt count. (P0-B2)
- **FR-006**: System MUST wrap local check strategy execution in async thread delegation for non-blocking operation. (P0-B2)
- **FR-007**: System MUST provide a stage base class with `_run_agent(agent_name, prompt, tools)`, `_check_output(path)`, and constructor accepting an EngineContext. (P0-B3)
- **FR-008**: System MUST provide CI check strategy with complete `tests_must_fail` and `tests_must_pass` implementations. (P0-C)
- **FR-009**: System MUST implement `_commit_and_push()` with 3-retry logic in CI strategy. (P0-C)
- **FR-010**: System MUST auto-detect project stack (Rust, frontend, Python) in CI strategy. (P0-C)
- **FR-011**: System MUST support configurable CI job name mapping per detected stack. (P0-C)
- **FR-012**: System MUST enforce CI strategy module size below 400 lines. (P0-C)
- **FR-013**: System MUST provide a review pipeline with three-way parallel review calling code-reviewer, security-reviewer, and brooks-reviewer agents. (P0-D)
- **FR-014**: System MUST apply fixes differentiated by review source in the review pipeline. (P0-D)
- **FR-015**: System MUST parse review verdicts tolerant of bold-formatted text. (P0-D)
- **FR-016**: System MUST register and load all 13 AI agents: constitution-writer, spec-writer, clarifier, planner, researcher, task-generator, implementer, code-reviewer, security-reviewer, brooks-reviewer, fixer, acceptor, and tdd-guide. (P0-E)

#### Domain: Spec Stage (P10)

- **FR-017**: System MUST execute the spec stage in sequence: constitution generation, specification generation, conditional clarification, and review. (P10)
- **FR-018**: System MUST trigger the clarify agent when spec-writer output contains `[NC:]` markers OR when heuristic scanning detects uncertainty indicators (more than 3 sentences with `?`, TBD/TODO keywords, more than 2 uncertainty expressions like "maybe"/"perhaps"). (P10, Clarify)
- **FR-019**: System MUST enforce spec stage module size below 150 lines. (P10)

#### Domain: Plan Stage (P1)

- **FR-020**: System MUST execute the plan stage in sequence: plan generation, optional research, task generation, and review. (P1)
- **FR-021**: System MUST trigger the research agent when planner output contains `[NR:]` markers OR when heuristic scanning detects research-related keywords ("new technology", "needs evaluation"). (P1, Research)
- **FR-022**: System MUST equip the clarify agent with WebSearch and WebFetch tools. (Clarify)
- **FR-023**: System MUST equip the research agent with WebSearch, WebFetch, and Bash tools. (Research)
- **FR-024**: System MUST call the task-generator agent to produce a tasks file and parse it into the store. (P1)
- **FR-025**: System MUST enforce plan stage module size below 150 lines. (P1)

#### Domain: Implement Stage (P2)

- **FR-026**: System MUST read pending tasks from the store and execute each through the TDD runner. (P2)
- **FR-027**: System MUST run three-way parallel review after each task's GREEN phase. (P2)
- **FR-028**: System MUST detect fix convergence failure (issue count not decreasing between attempts) and terminate the fix loop, marking the task BLOCKED. The fix loop is also bounded by `max_fix_retries` (default: 3). (P2)
- **FR-029**: System MUST detect feature gaps during review and create supplementary tasks. (P2)
- **FR-030**: System MUST record all implement-stage events to LVL. (P2)
- **FR-031**: System MUST enforce implement stage module size below 200 lines. (P2)

#### Domain: TDD Execution Engine (P3)

- **FR-032**: System MUST support both serial and parallel execution of RED-GREEN cycles. (P3)
- **FR-033**: System MUST constrain the RED prompt so the agent writes only test code, no implementation. (P3, R06)
- **FR-034**: System MUST provide extra retry attempts for GREEN failures caused by environment issues (distinguished from logic errors). (P3, R07, R08)
- **FR-035**: System MUST perform batch commit and CI validation after completing a set of tasks. (P3)
- **FR-036**: System MUST skip already-completed tasks. (P3, R09)
- **FR-037**: System MUST validate that task file sets are non-overlapping before parallel execution. (P3)
- **FR-038**: System MUST detect fix convergence failure in the TDD runner. (P3)
- **FR-039**: System MUST enforce TDD runner module size below 450 lines. (P3)

#### Domain: Common Checks (P4)

- **FR-040**: System MUST provide pure utility functions: `file_exists`, `coverage_above`, `no_critical`, and `parse_review_verdict`. (P4)
- **FR-041**: System MUST enforce common checks module size below 150 lines. (P4)

#### Domain: Engine Core (P5)

- **FR-042**: System MUST provide `resume()` to restore execution from the last checkpoint. (P5)
- **FR-043**: System MUST provide `retry(task_id)` to re-execute a single task. (P5)
- **FR-044**: System MUST provide `status()` to return current pipeline progress. (P5)
- **FR-045**: System MUST manage a process lock to prevent concurrent orchestrator instances on the same project. (P5)
- **FR-046**: System MUST enforce engine module size below 300 lines. (P5)

#### Domain: Integration Testing (P6)

- **FR-047**: System MUST have integration tests validating cross-module interactions across all four stages. (P6)

#### Domain: Wave Dashboard (P7)

- **FR-048**: System MUST provide an optional Wave panel launcher for visual pipeline monitoring. (P7)

#### Domain: Acceptance Stage (P8)

- **FR-049**: System MUST invoke the acceptor agent to produce a structured traceability matrix. (P8)
- **FR-050**: System MUST run a final review after traceability matrix generation. (P8)
- **FR-051**: System MUST enforce acceptance stage module size below 200 lines. (P8)

#### Domain: CLI (P9)

- **FR-052**: System MUST provide `run`, `resume`, `retry`, and `status` subcommands. (P9)

#### Domain: LVL Evidence Chain (P11-P14)

- **FR-053**: System MUST provide `append_event`, `get_latest_event`, `verify_chain`, `verify_stage_invariant`, and `list_events_for_stage` operations for event management. (P11)
- **FR-054**: System MUST enforce LVL module size below 200 lines. (P11)
- **FR-055**: System MUST provide `register_artifact`, `freeze_artifact`, `check_staleness`, `cascade_invalidate`, and `unfreeze_stage_artifacts` operations for artifact management. (P12)
- **FR-056**: System MUST enforce artifacts module size below 150 lines. (P12)
- **FR-057**: System MUST define ArtifactRecord and LvlEventRecord data models. (P13)
- **FR-058**: System MUST upgrade the database schema to version 3 with artifacts and lvl_events tables. Version 2 was an internal intermediate version during v1 development; the migration path is v1 (version 1) directly to v2 (version 3 schema). (P14)
- **FR-059**: System MUST enforce invariant INV-1: stage completion requires a `stage_complete` event AND all required artifacts frozen AND content hashes matching. (INV-1)
- **FR-060**: System MUST enforce invariant INV-2: stage start requires predecessor stage complete AND frozen artifacts not stale. (INV-2)
- **FR-061**: System MUST enforce invariant INV-3: every non-`stage_start` event must reference an existing prior event via `prior_event_id`. (INV-3)
- **FR-062**: System MUST enforce invariant INV-4: every task must have `red_pass` before `green_start`. (INV-4)

#### Domain: Pipeline Monitor (P15)

- **FR-063**: System MUST provide a rule-driven (no LLM) pipeline monitor that produces Observations with dimension, severity, message, and suggestion. (P15)
- **FR-064**: System MUST invoke the monitor at stage transitions and task batch completions. (P15)
- **FR-065**: System MUST monitor for: BLOCKED ratio anomalies (threshold: 50% of tasks in current batch), resource consumption trends, stale cascade depth, and fix-cycle global patterns. (P15)
- **FR-066**: System MUST write monitor observations to the lvl_events table. (P15)
- **FR-067**: System MUST enforce monitor module size below 200 lines. (P15)

#### Domain: Agent Adaptations (A1-A10)

- **FR-068**: System MUST adapt the tdd-guide agent's RED prompt to constrain output to test-only code. (A1)
- **FR-069**: System MUST adapt the task-generator agent to include CI estimation rules. (A2)
- **FR-070**: System MUST adapt the fixer agent to include dependency awareness in its fix context. (A6)
- **FR-071**: System MUST adapt the implementer agent's GREEN prompt for correct GREEN-phase behavior. (A7)
- **FR-072**: System MUST adapt the acceptor agent to produce structured output (traceability matrix format). (A8)
- **FR-073**: System MUST adapt the spec-writer agent to emit `[NC:]` trigger markers for unclear aspects. (A9)
- **FR-074**: System MUST adapt the planner agent to emit `[NR:]` trigger markers for research needs. (A10)

#### Domain: Configuration (C1-C3)

- **FR-075**: System MUST update defaults configuration to include idle_timeout, subprocess_timeout, source_dirs, global_timeout, and stage_timeout settings. (C1)
- **FR-076**: System MUST provide a CI workflow configuration supporting the project's test runner and coverage tooling. (C2)
- **FR-077**: System MUST resolve agent registration paths as relative paths from the configuration file. (C3)

#### Domain: Runtime Constraints (R01-R23)

- **FR-078**: System MUST verify the presence of a `.git` directory at startup and fail with a clear error if absent. (R01)
- **FR-079**: System MUST auto-detect source directories for `git add` operations. (R02)
- **FR-080**: System MUST detect Python stack correctly during stack detection. (R03-R05)
- **FR-081**: System MUST constrain the RED prompt to "write tests only" with no implementation code. (R06)
- **FR-082**: System MUST distinguish environment errors from logic errors in GREEN failures. (R07)
- **FR-083**: System MUST grant additional retry attempts for environment-caused GREEN failures. (R08)
- **FR-084**: System MUST skip tasks that are already completed when resuming or re-running. (R09)
- **FR-085**: System MUST use the configured global_timeout for the implement stage duration. (R12)
- **FR-086**: System MUST parse severity values using regex patterns that tolerate bold formatting (e.g., `**CRITICAL**`). (R21)

#### Domain: Security (C-1 through H-4)

- **FR-087**: System MUST validate all file paths produced by LLM agents against a whitelist of allowed directories. (C-1)
- **FR-088**: System MUST use safe command construction (list-based) for subprocess calls on Windows to prevent shell injection. (C-2)
- **FR-089**: System MUST serialize all SQLite write operations through a threading lock. (C-3)
- **FR-090**: System MUST execute CI check operations via async thread delegation to avoid blocking the event loop. (H-1, H-2)
- **FR-091**: System MUST perform secret/credential detection after staging project files but before committing. (H-4)

### Key Entities

- **Stage**: Represents one of the four pipeline phases (spec, plan, implement, acceptance). Has a status, preconditions, and produces artifacts. Spec, plan, and acceptance stages are atomic (re-run fully on resume); implement stage supports task-level checkpointing.
- **Task**: A unit of work within the implement stage. Has an ID, status (pending, running, done, blocked), associated files, and TDD cycle history.
- **Artifact**: A registered output file (spec.md, plan.md, tasks.md, code files). Has a path, content hash, status (draft, frozen, stale, superseded), and dependency relationships.
- **LvlEvent**: An immutable event record in the evidence chain. Has a type, severity, stage, task reference, artifact reference, and prior-event linkage.
- **Observation**: A monitor output representing a health assessment. Has a dimension, severity, message, and suggested action.
- **Session**: An agent interaction session. Has an ID, associated agent, expiry state, and continuation capability.
- **CheckResult**: The outcome of a test execution. Contains pass/fail status, output text, and attempt count.
- **EngineContext**: An immutable container holding all shared runtime dependencies (store, config, session manager, check strategy, notifier, store lock).

## Success Criteria

### Measurable Outcomes

- **SC-001**: A complete four-stage pipeline run (spec through acceptance) completes successfully on a small feature without manual intervention.
- **SC-002**: Pipeline resume recovers from any interruption point and completes without re-executing already-finished work.
- **SC-003**: Single-task retry re-executes only the targeted task and completes within the time of one TDD cycle.
- **SC-004**: Status command returns accurate progress information within 2 seconds.
- **SC-005**: All 13 AI agents load and respond correctly when invoked by their respective stages.
- **SC-006**: CI mode successfully commits, pushes, triggers CI, and retrieves results for all supported stacks.
- **SC-007**: Parallel TDD execution with batch commit completes without file conflicts when task file sets are non-overlapping.
- **SC-008**: No module exceeds its specified line count constraint (450 lines maximum for any module).
- **SC-009**: Engine module stays below 300 lines while providing run, resume, retry, and status functionality.
- **SC-010**: Test coverage reaches 80% or above across all orchestrator modules.
- **SC-011**: CI pipeline passes all checks (tests, linting, coverage) without failures.
- **SC-012**: No CRITICAL severity security issues are found in security review.
- **SC-013**: Existing v1 database state can be migrated or recovered to v2 schema (v1 schema version 1 to v2 schema version 3, skipping internal version 2).
- **SC-014**: All LVL invariants (INV-1 through INV-4) hold after every pipeline run, verified by automated chain verification.
- **SC-015**: Monitor correctly identifies and reports when BLOCKED task ratio exceeds 50% threshold, with no false negatives.
- **SC-016**: Fix convergence detection terminates non-converging fix loops within 2 extra iterations maximum (does not loop indefinitely). Total fix attempts bounded by `max_fix_retries` default of 3.
- **SC-017**: Contract tests between orchestrator and agents pass for all 13 agents.

## Assumptions

- The orchestrator targets developers using it in a local development environment with access to a git repository and optionally a CI system (GitHub Actions).
- Python 3.12+ is the minimum runtime version; no backward compatibility with older Python versions is required.
- SQLite is sufficient for single-user orchestrator state persistence; no multi-user concurrent access is expected beyond process-lock protection.
- The Claude Agent SDK is the primary agent invocation mechanism, with CLI fallback available when the SDK is unavailable or fails.
- Agent registration uses a YAML-based configuration file where paths are resolved relative to the config file location.
- The Wave dashboard (P7) is fully optional and the orchestrator functions completely without it.
- There are exactly 13 agents: constitution-writer, spec-writer, clarifier, planner, researcher, task-generator, implementer, code-reviewer, security-reviewer, brooks-reviewer, fixer, acceptor, and tdd-guide. The agents-src directory confirms 13 agent directories; no 14th agent exists.
- Global timeout and stage timeout values have sensible defaults in `defaults.yaml` and can be overridden per-project.
- The "no CRITICAL security issues" acceptance criterion refers to findings from the security-reviewer agent, not an external penetration test.
- For BLOCKED ratio threshold, the default is 50% of tasks in a batch, consistent with the requirement document's example ("50% task BLOCKED").
- Schema version upgrade from v1 to v3 implies v2 was an intermediate internal version during v1 development; the migration path handles v1 (version 1) to v2 (version 3 schema) directly with no need for a v2 intermediate step.
- Heuristic scanning thresholds (3 question sentences, 2 uncertainty expressions) are configurable but have the stated defaults.
- The spec, plan, and acceptance stages are atomic for resume purposes; implement is the only stage with sub-stage (task-level) checkpointing.
- The fix loop has dual termination conditions: (1) convergence failure (issue count not decreasing), and (2) maximum retry limit (`max_fix_retries`, default 3). Whichever triggers first terminates the loop.

## Priority Numbering Glossary

This spec uses two distinct priority numbering systems:

- **User Story Priorities (P1/P2/P3)**: Indicate relative importance of user-facing scenarios. P1 = must-have for MVP, P2 = important but not blocking, P3 = nice-to-have.
- **Requirement Domain Priorities (P0-P15, A1-A10, C1-C3)**: Indicate implementation wave ordering and dependency grouping as defined in requirement-v2.md. P0 = infrastructure prerequisites, P1 = plan stage, P2 = implement stage, etc. These are NOT the same as user story priorities. Refer to the execution order in requirement-v2.md for wave sequencing.

---

## Clarifications

The following ambiguities were identified and resolved autonomously based on analysis of requirement-v2.md, runtime-issues.md, pitfalls.md, and the agents-src directory structure.

- Q: User Story 6 "Why this priority" paragraph was truncated ("Why this prio") -> A: Paragraph completed with full rationale explaining CI mode's importance for environments where local execution is insufficient or CI validation is mandatory. (Reason: The truncation was a formatting artifact; the rationale was inferred from the user story context and requirement-v2.md's CI strategy description.)

- Q: FR-016 references "14 AI agents" but only 13 are named, with the 14th described as "one additional agent" -> A: Corrected to 13 agents. The agents-src directory contains exactly 13 agent directories (constitution-writer, spec-writer, clarifier, planner, researcher, task-generator, implementer, code-reviewer, security-reviewer, brooks-reviewer, fixer, acceptor, tdd-guide). The original "14" count was an error in requirement-v2.md that propagated to the spec. All references updated to 13. (Reason: Physical directory count is the authoritative source; no 14th agent exists in agents-src or is referenced by any stage logic.)

- Q: Two priority numbering systems (User Stories use P1/P2/P3; Requirements use P0-P15) create confusion -> A: Added a "Priority Numbering Glossary" section to the spec explicitly distinguishing the two systems and their meanings. (Reason: The two systems serve different purposes — user story triage vs. implementation wave ordering — and must coexist but need clear disambiguation to prevent misinterpretation during planning.)

- Q: "Stages are atomic" (User Story 2 Scenario 2) conflicts with implement stage's task-level checkpointing -> A: Added explicit "Stage Atomicity Rule" to User Story 2 clarifying that spec/plan/acceptance are atomic (single coherent artifact output) while implement is NOT atomic (independent per-task TDD cycles with individual checkpointing). Updated Key Entities "Stage" definition to reflect this distinction. (Reason: requirement-v2.md's P5 resume logic and P2 implement logic clearly differentiate: implement reads pending tasks from store and skips completed ones, while plan/spec produce single artifacts that must be coherent.)

- Q: BLOCKED ratio threshold not specified in User Story 5 -> A: Set to 50% of tasks in the current batch, consistent with requirement-v2.md which states "50% task BLOCKED" as the example threshold. Updated User Story 5 Scenario 2 and FR-065 to include this explicit value. (Reason: requirement-v2.md section "What is autonomous logic" uses 50% as the canonical example; SC-015 also references a threshold that should be concrete for testability.)

- Q: Review fix loop has no explicit maximum retry count (FR-028, User Story 7 Scenario 3) -> A: Maximum fix attempts set to 3 (configurable via `max_fix_retries` in defaults.yaml). The loop terminates on EITHER convergence failure (issue count not decreasing) OR reaching the retry limit, whichever comes first. Updated FR-028, User Story 7 Scenario 3, SC-016, and added edge cases. (Reason: requirement-v2.md P2 mentions "max_fix_retries" as a configurable value; 3 is a reasonable default balancing cost against fix opportunity, consistent with the 3-retry pattern used elsewhere in the system such as CI push retries.)

- Q: FR-058 schema version jumps from 1 to 3 with no explanation of version 2 -> A: Clarified that version 2 was an internal intermediate schema version during v1 development. The migration path is v1 (version 1) directly to v2 (version 3 schema). Updated FR-058, SC-013, and Assumptions. (Reason: requirement-v2.md's P14 section states "schema_version to 3" and "preserve old tables for backward compatibility", implying a direct upgrade path; the v2 intermediate was consumed internally and never shipped.)
