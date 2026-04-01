<!--
Sync Impact Report
===================
Version change: N/A -> 1.0.0 (initial adoption)
Modified principles: N/A (initial)
Added sections:
  - Core Principles (7 principles)
  - Technical Constraints
  - Development Workflow
  - Governance
Removed sections: N/A
Templates requiring updates:
  - orchestrator/stages/spec.py: references constitution output path
    specs/constitution.md (consistent, no update needed)
  - agents-src/constitution-writer/: agent knowledge files
    (no constitution-specific references to update)
  - CLAUDE.md: no constitution references (no update needed)
Follow-up TODOs: none
-->

# ESSKILLAGENT-v2 Constitution

## Core Principles

### I. Four-Stage Pipeline Integrity

The orchestrator MUST execute the four-stage pipeline
(spec, plan, implement, acceptance) in strict sequential order.
Each stage MUST complete its gate check before the next stage
begins. No stage may be automatically skipped by heuristic
detection; skipping MUST be explicitly configured by the user
via `skip_stages` in `.orchestrator.yaml`.

**Rationale**: v1 used `_is_small_project` heuristics to skip
stages, causing repeated misclassification (pitfalls #11, #20).
Explicit configuration eliminates ambiguity.

### II. Test-First Discipline (NON-NEGOTIABLE)

All implementation work MUST follow the TDD Red-Green-Refactor
cycle:

- **RED**: Agent writes tests only. Implementation files contain
  empty stubs at most. Tests MUST fail due to assertion failure,
  not import or compilation errors.
- **GREEN**: Agent implements only enough code to pass existing
  tests. No new tests may be added in this phase.
- **REFACTOR**: Structural improvements with all tests passing.

RED and GREEN prompts MUST be separate templates with explicit
phase constraints. The RED template MUST include the hard
constraint "ONLY write tests, do NOT write implementation code."

**Rationale**: v1 agents completed entire TDD cycles in the RED
phase when prompts lacked explicit constraints (pitfall #27).
Strict phase separation prevents this.

### III. Modular Architecture

Every source module MUST remain under 450 lines (400-line soft
target, 50-line tolerance). `engine.py` MUST remain under
300 lines and contain zero stage-specific logic.

- Each file addresses one concern.
- Dependencies flow through `EngineContext` (frozen dataclass),
  not constructor parameter proliferation.
- The `ui/` package MUST NOT be imported by core modules.

**Rationale**: v1's engine.py reached 1,249 lines as a god
class mixing configuration, TDD scheduling, git operations, and
gate control (pitfall #2). Strict size limits enforce separation
of concerns.

### IV. Strategy Pattern for Test Verification

Test verification MUST use the `CheckStrategy` abstract
interface. Switching between local and CI verification MUST
require zero changes to calling code -- only a configuration
change (`local_test: true/false`).

- `CheckStrategy` exposes async `tests_must_fail()` and
  `tests_must_pass()` returning `CheckResult` (not bare bool).
- CI strategy MUST implement stack-scoped job evaluation:
  only jobs relevant to the task's detected technology stack
  (rust/frontend/python/etc.) are checked.
- CI job name mappings MUST be read from configuration, not
  hardcoded.

**Rationale**: v1 used dict mutation (`CHECKERS` global
replacement) to switch strategies, preventing static analysis
and requiring global state save/restore in tests (pitfall #1).
Stack-scoping absence caused cross-stack false failures
(pitfalls #5, #12, #15, #24, #25).

### V. Contract Alignment Between Agents and Parser

The `tasks.md` format MUST use em-dash separation between
description and file path:

```
- [ ] T001 [P?] [US*?] [FR-###]+ Description -- primary/file/path.ext
```

- The task-generator agent MUST produce this format.
- The parser MUST validate this format at startup and report
  incompatible tasks before execution begins.
- A contract test (`tests/contract/test_task_format.py`) MUST
  verify parser and generator remain aligned.
- Every `[P]` (parallel) task MUST have a non-empty `file_path`.

**Rationale**: v1's parser and generator drifted apart, causing
all file paths to parse as empty and all parallel tasks to
degrade to serial execution (pitfall #3).

### VI. Resilient External Operations

All operations involving network I/O or external processes
(git push, GitHub CLI, CI polling) MUST implement:

- Retry with backoff (minimum 3 attempts for network ops).
- Structured error capture: CI failure logs MUST be extracted
  per-job with a 2,000-character budget, including only the
  relevant technology stack's output.
- Explicit timeout handling: all subprocess calls MUST catch
  both `FileNotFoundError` and `subprocess.TimeoutExpired`.

**Rationale**: v1 had no retry on git push (pitfall #10),
truncated CI logs to 500 characters causing whack-a-mole
debugging (pitfall #4), and crashed on `gh auth` timeout
(pitfall #18).

### VII. Immutable Data and Type Safety

- All data transfer objects MUST use `@dataclass(frozen=True)`.
- All public APIs MUST have complete type annotations.
- No bare `except:` clauses; exception types MUST be specified.
- Dict mutation for state changes is prohibited; produce new
  dicts or use dedicated update methods.

**Rationale**: v1's mutable state and untyped interfaces caused
silent data corruption (pitfall #9: `INSERT OR IGNORE` failing
to update file_path) and made static analysis ineffective.

## Technical Constraints

- **Language**: Python 3.12+
- **Async model**: asyncio (single-threaded event loop).
  `asyncio.Lock` ownership in `engine.py`, injected into all
  components. Store itself is lock-free; callers coordinate.
- **Persistence**: SQLite. v2 MUST read v1's
  `.workflow/workflow.db` without schema changes to existing
  tables. New tables are permitted.
- **Agent runtime**: Claude Agent SDK with CLI fallback.
  Agent knowledge files reside in `agents-src/` (14 agents).
  Knowledge Base injection MUST use absolute paths.
- **Configuration layering**: `defaults.yaml` (global) then
  `brownfield.yaml` (v1 compat) then `.orchestrator.yaml`
  (project override). Later files override earlier ones.
- **Naming conventions**:
  - Modules: lowercase_underscore (`tdd/runner.py`)
  - Classes: PascalCase nouns (`TaskRunner`)
  - Public methods: lowercase_underscore, verb-leading
    (`run_stage()`)
  - Private methods: `_` prefix (`_commit_and_push()`)
  - Constants: UPPER_SNAKE (`MAX_RETRIES`)
- **Test coverage**: 80%+ overall, 90%+ for `checks/`,
  95%+ for `tdd/parser.py`, 85%+ for `store/`.
- **Test framework**: pytest with fixtures. External
  dependencies mocked per the mock strategy table in
  `requirement.md`.

## Development Workflow

### Code Review and Quality Gates

- Every stage transition MUST pass its gate check (Opus-level
  review for spec and plan stages).
- Three-way parallel review: code review, security review,
  and Brooks review. All three MUST pass before proceeding.
- Auto-fix loop: review failure triggers fixer agent, then
  re-review. Maximum fix retries governed by
  `max_fix_retries` configuration.

### Parallel Execution Safety

- Parallel (`[P]`) tasks MUST have non-overlapping `file_path`
  values within the same group. The validator MUST check for
  conflicts and degrade to serial on overlap.
- Phase A (RED): parallel agents write, then one batch
  commit+CI check.
- Phase B (GREEN): parallel agents implement, then one batch
  commit+CI check with retry loop.
- `git add` scope MUST be limited to project source
  directories, excluding `.workflow/`, `__pycache__`,
  `node_modules`, and `.git`.

### Checkpoint and Resume

- The orchestrator MUST support resuming from any stage or
  sub-step checkpoint via `resume` CLI command.
- LVL (audit log) events MUST be written at every decision
  point to support both post-hoc analysis and runtime
  decision-making (convergence detection, stale cascade
  identification, BLOCKED ratio monitoring).

## Governance

This constitution is the supreme governance document for the
ESSKILLAGENT-v2 project. All development practices, agent
behaviors, and architectural decisions MUST comply with the
principles defined herein.

### Amendment Procedure

1. Propose the amendment with rationale and impact analysis.
2. Document the change in this file with updated version.
3. Verify all dependent artifacts (agent templates, stage
   implementations, test suites) are consistent with the
   amendment.
4. Record the amendment in the Sync Impact Report (HTML
   comment at top of this file).

### Versioning Policy

This constitution follows semantic versioning:

- **MAJOR**: Principle removal, redefinition, or backward-
  incompatible governance change.
- **MINOR**: New principle or section added, or material
  expansion of existing guidance.
- **PATCH**: Clarification, wording fix, or non-semantic
  refinement.

### Compliance Review

- All code reviews MUST verify compliance with these
  principles.
- Added complexity MUST be justified against Principle III
  (Modular Architecture).
- Runtime guidance is maintained in `CLAUDE.md` and
  `reference/` documents; those documents MUST NOT contradict
  this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-04-01 | **Last Amended**: 2026-04-01
