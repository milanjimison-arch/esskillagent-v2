<!--
=== Sync Impact Report ===
Version change: N/A -> 1.0.0 (initial ratification)
Modified principles: N/A (initial version)
Added sections:
  - Core Principles (7 principles)
  - Technical Constraints
  - Development Workflow
  - Governance
Removed sections: N/A
Templates requiring updates: N/A (no prior dependent artifacts)
Follow-up TODOs: None
===========================
-->

# E+S Orchestrator v2 Constitution

## Core Principles

### I. Modular Single-Responsibility

Every module MUST have exactly one concern and MUST NOT exceed
400 lines of code. `engine.py` MUST NOT exceed 300 lines and MUST
contain only stage-flow orchestration logic -- no TDD scheduling,
no Git operations, no file parsing.

Stage-specific logic MUST reside in `stages/` sub-package files.
TDD execution MUST reside in `tdd/`. Review logic MUST reside in
`review/`. Check strategies MUST reside in `checks/`. UI code
MUST reside in `ui/` and core modules MUST NOT import from `ui/`.

**Rationale**: v1's `engine.py` grew to 1249 lines mixing
configuration, TDD, Git, and gate logic, making navigation and
maintenance impractical (pitfall #2). Strict line budgets and
single-concern modules prevent recurrence.

### II. TDD-First (Non-Negotiable)

All production code MUST follow the Red-Green-Refactor cycle:
tests written first, tests fail (RED), then minimal implementation
to pass (GREEN), then refactor. No implementation code MUST be
written before a failing test exists.

The orchestrator itself MUST enforce TDD on managed projects via
the `tdd/runner.py` scheduler. RED validation MUST confirm test
failure is an assertion failure, not a compilation error. GREEN
validation MUST confirm all relevant tests pass.

Test coverage MUST meet these thresholds:
- Overall: 80%+
- `checks/`: 90%+ (core judgment logic)
- `tdd/parser.py`: 95%+ (high-risk format parsing)
- `store/`: 85%+ (data integrity)

**Rationale**: TDD is the project's core value proposition -- the
orchestrator exists to enforce TDD on target projects. The
orchestrator itself MUST exemplify the discipline it enforces.

### III. Pluggable Strategy Interfaces

Cross-cutting concerns with multiple implementations MUST use
abstract base classes (`ABC`) with constructor injection. The
`CheckStrategy` interface (`checks/base.py`) is the canonical
example: `LocalCheckStrategy` and `CICheckStrategy` MUST share
the same interface. Callers MUST NOT be aware of which strategy
is active.

RED and GREEN evaluation MUST share unified `_evaluate_red` /
`_evaluate_green` methods within each strategy. There MUST NOT
be separate, drifting job-check logic paths (pitfall #1).

**Rationale**: v1 used `CHECKERS` dict mutation to swap
implementations at runtime, causing logic drift between local and
CI paths, untestable global state, and static analysis blindness.

### IV. Immutable Data and Explicit State

Data models MUST use `@dataclass(frozen=True)`. Dicts MUST NOT
be mutated in place; new dicts MUST be created instead. SQLite
query results MUST be wrapped in frozen dataclasses, not returned
as raw `sqlite3.Row` objects.

Configuration MUST be loaded once into an immutable structure.
No global mutable state MUST exist. All state transitions MUST be
persisted to the SQLite store with an audit trail.

**Rationale**: Mutable shared state caused v1's dict-mutation
strategy swap (pitfall #1), DB file_path non-update (pitfall #9),
and several parallel TDD race conditions (pitfall #7).

### V. Parallel Safety by Design

Parallel TDD MUST satisfy these invariants:
1. Every `[P]` task MUST have a non-empty `file_path`
   (generator enforced, parser validated, validator runtime check).
2. Concurrent `[P]` tasks in the same group MUST NOT have
   overlapping `file_path` values. Conflicts MUST cause automatic
   fallback to serial execution.
3. Phase A (RED) and Phase B (GREEN) MUST use batch commit mode:
   all parallel agents complete, then one combined commit+push+CI.
4. `git add` scope MUST be restricted to project source
   directories, excluding `.workflow/`.
5. `asyncio.Lock` ownership MUST reside in `engine.py`; the store
   itself MUST be lock-free. Store writes after `asyncio.gather`
   MUST execute sequentially in a for-loop.

**Rationale**: v1 suffered parallel git conflicts (pitfall #7),
missing file_path data (pitfall #3), and task ordering errors
(pitfall #8). These invariants MUST be built in from the start,
not patched after failures.

### VI. Contract Alignment and Format Safety

The `tasks.md` format MUST be enforced by both the task-generator
agent and the `tdd/parser.py` module. The canonical format is:

```
- [ ] T001 [P?] [US*?] [FR-###]+ Description -- primary/file/path.ext
```

Em dash (`--`) MUST separate description from file path. Parser
MUST use em dash extraction as primary strategy with "in src/..."
fallback. Contract tests (`tests/contract/test_task_format.py`)
MUST verify parser-generator alignment on every CI run.

Stack detection (`detect_stack`) MUST use file extension + path
prefix dual check. `.rs` files MUST map to rust stack regardless
of directory location.

All subprocess calls MUST catch both `FileNotFoundError` and
`subprocess.TimeoutExpired`. Network operations (git push, gh CLI)
MUST retry 3 times with 5-second intervals.

**Rationale**: Parser-generator misalignment (pitfall #3), CI log
truncation (pitfall #4), stack misdetection (pitfalls #5, #12,
#15), and network failures (pitfall #10) were the most frequent
v1 failure modes.

### VII. Explicit Configuration over Implicit Behavior

Configuration MUST follow a three-layer loading order:
`defaults.yaml` -> `brownfield.yaml` (v1 compat) ->
`.orchestrator.yaml` (project override). Later layers MUST
override earlier ones.

There MUST NOT be any automatic stage-skipping logic. All projects
MUST execute the full four-stage pipeline. Stage skipping MUST
only occur via explicit user configuration
(`skip_stages: [stage_name]`).

CI error feedback MUST be structured per-job with a 2000-character
budget, including only the relevant stack's jobs.

**Rationale**: v1's `_is_small_project` heuristic repeatedly
misjudged projects (pitfalls #11, #20), and the 500-character CI
log truncation caused cascading retry failures (pitfall #4).

## Technical Constraints

- **Python version**: 3.12+ required.
- **Async model**: `asyncio` single-threaded event loop for all
  I/O operations. No threads for core logic.
- **Persistence**: SQLite with v1-compatible schema. Existing v1
  tables (tasks, reviews, evidence, stage_progress, step_status,
  lvl, checkpoints, settings) MUST NOT be altered. New tables MAY
  be added. `INSERT OR REPLACE` or explicit upsert MUST be used
  instead of `INSERT OR IGNORE` for metadata updates.
- **Agent compatibility**: All 14 ESSKILLAGENT agent directories
  MUST load without modification. Knowledge Base injection MUST
  use absolute paths with explicit instructions to agents.
- **Type annotations**: All public API functions and methods MUST
  have complete type annotations.
- **Exception handling**: Bare `except` is forbidden. All except
  clauses MUST specify concrete exception types. Exception
  chaining (`raise ... from e`) MUST be used when re-raising.
- **Naming conventions**:
  - Modules: lowercase_underscore, describing responsibility
  - Classes: PascalCase, nouns
  - Public methods: lowercase_underscore, verb-initial
  - Private methods: `_` prefix
  - Constants: UPPER_SNAKE_CASE
  - Config keys: lowercase_underscore
- **Dependencies**: Pure Python + Claude SDK. No additional
  runtime dependencies beyond the standard library and Claude SDK.

## Development Workflow

### Four-Stage Pipeline

Every managed project MUST pass through all four stages in order:

1. **Spec**: constitution -> specify -> clarify -> review
2. **Plan**: plan -> research -> tasks -> review
3. **Implement**: TDD (RED->GREEN per task) -> review -> push+CI
4. **Acceptance**: acceptance test -> traceability matrix -> review

Each stage MUST have an Opus-level gate review. Checkpoint/resume
MUST be supported from any stage boundary.

### Review Process

Three-way parallel review MUST execute on implementation output:
code review + security review + Brooks review. Review failures
MUST trigger an auto-fix cycle (fixer agent -> re-review) with a
configurable retry limit (`max_fix_retries`, default 2).

Feature-gap detection MUST dynamically create supplementary tasks
when reviewers identify missing or unimplemented functionality.

### Quality Gates

- All tests MUST pass before stage transition.
- Traceability matrix (FR -> Task -> Test) MUST be generated in
  the acceptance stage.
- CLI subcommands `run`, `resume`, `retry <task_id>`, and `status`
  MUST be functional.
- CI green status MUST be verified when `local_test: false`.

### Reference Documents

The following documents are normative and MUST be consulted:
- `reference/python-patterns.md` -- Python coding patterns
- `reference/python-testing.md` -- Python testing standards
- `pitfalls.md` -- v1 lessons learned (21 documented pitfalls)

## Governance

This constitution is the supreme governance document for the
E+S Orchestrator v2 project. All development decisions, code
reviews, and architectural changes MUST comply with the principles
defined herein.

### Amendment Procedure

1. Proposed amendments MUST be documented with rationale.
2. Amendments MUST include a migration plan for any existing code
   that becomes non-compliant.
3. Version MUST be incremented per semantic versioning:
   - MAJOR: principle removal or backward-incompatible redefinition
   - MINOR: new principle or materially expanded guidance
   - PATCH: clarification, wording, or typo fix
4. `LAST_AMENDED_DATE` MUST be updated to the amendment date.

### Compliance Review

- All code contributions MUST be verified against these principles.
- Complexity beyond what a principle permits MUST be justified in
  writing (code comment or PR description).
- `CLAUDE.md` serves as the runtime development guidance file and
  MUST remain consistent with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-04-01 | **Last Amended**: 2026-04-01
