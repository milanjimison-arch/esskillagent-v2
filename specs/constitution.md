<!--
Sync Impact Report
==================
Version change: N/A -> 1.0.0 (initial ratification)
Modified principles: N/A (first version)
Added sections:
  - Core Principles (7 principles)
  - Technical Constraints
  - Development Workflow
  - Governance
Removed sections: N/A
Templates requiring updates:
  - specs/ directory created (no prior specs existed)
  - No dependent templates to propagate (fresh project)
Follow-up TODOs: None
-->

# E+S Orchestrator v2 Constitution

## Core Principles

### I. Single Responsibility per Module

Every source file MUST have exactly one concern. No module may exceed
400 lines. `engine.py` MUST remain under 300 lines and contain only
stage flow-control logic; all stage-specific behavior MUST reside in
the `stages/` sub-package. The `ui/` package MUST NOT be imported by
any core module.

Rationale: v1 accumulated a 1249-line engine.py that mixed
configuration loading, TDD scheduling, file lookup, git operations,
and gate control. Splitting by concern eliminates navigational
overhead and reduces merge-conflict surface area.

### II. Test-First Development (NON-NEGOTIABLE)

All new functionality MUST follow the TDD Red-Green-Refactor cycle:

- RED: Write a failing test that specifies the desired behavior.
- GREEN: Write the minimal code to make the test pass.
- REFACTOR: Improve structure while keeping tests green.

The orchestrator enforces this via its four-stage pipeline
(spec, plan, implement, acceptance). Skipping RED or GREEN phases
is forbidden. Coverage targets:

- Overall: 80%+
- `checks/`: 90%+
- `tdd/parser.py`: 95%+
- `store/`: 85%+

Rationale: TDD is the product's core value proposition. The
orchestrator itself MUST exemplify the discipline it enforces.

### III. Explicit Configuration over Implicit Behavior

Configuration MUST follow a deterministic layering order:
`defaults.yaml` then `brownfield.yaml` (v1 compat) then
`.orchestrator.yaml` (project override). Later sources override
earlier ones. Environment variables may override any key.

No automatic stage-skipping based on heuristics (e.g., requirement
text length). Stage skipping MUST be explicitly requested via
configuration (`skip_stages: [...]`).

Rationale: v1's `_is_small_project` heuristic repeatedly misjudged
projects, skipping critical phases. Explicit configuration eliminates
surprise behavior.

### IV. Strategy-Based Polymorphism

Behavioral variation MUST be expressed through strategy interfaces
(ABC subclasses), not through dict mutation or runtime monkey-patching.
`CheckStrategy` is the canonical example: `LocalCheckStrategy` and
`CICheckStrategy` implement the same abstract interface. The calling
code MUST NOT branch on which strategy is active.

Rationale: v1's `CHECKERS` dict-mutation pattern made static analysis
impossible and caused RED/GREEN evaluation logic to drift between
local and CI modes.

### V. Contract Alignment

Any boundary between producer and consumer (e.g., task-generator
output and task-parser input) MUST have a documented format contract
and a contract test in `tests/contract/`. The canonical format for
`tasks.md` entries is:

```
- [ ] T001 [P?] [US*?] [FR-###]+ Description -- primary/file/path.ext
```

The em-dash separator is mandatory. The parser MUST reject entries
that violate the contract and report them at startup.

Rationale: v1's parser/generator format misalignment silently emptied
all `file_path` fields, degrading every parallel task to serial
execution.

### VI. Resilient External Operations

All network and subprocess operations (git push, gh CLI, Claude
SDK/CLI calls) MUST implement retry with configurable attempt count
and backoff. Subprocess calls MUST catch both `FileNotFoundError`
and `subprocess.TimeoutExpired`. CI job name mapping MUST be loaded
from configuration, not hardcoded.

Stack detection (`detect_stack`) MUST support extensible technology
registration (rust, frontend, python, go, etc.) via configuration
rather than if-elif chains.

Rationale: v1 hardcoded job names and lacked retry on network
operations, causing single transient failures to permanently mark
tasks as failed.

### VII. Immutable Data and Type Safety

All public APIs MUST carry type annotations. Data transfer objects
MUST use `@dataclass(frozen=True)`. Dicts MUST NOT be mutated in
place when passed across module boundaries; produce new dicts
instead. Bare `except:` is forbidden; every except clause MUST
specify an exception type. Exception chaining (`raise X from Y`)
MUST be used when re-raising.

Rationale: Mutable shared state caused v1's `CHECKERS` dict bug and
made reasoning about concurrent TDD phases unreliable. Type
annotations enable static analysis and IDE support.

## Technical Constraints

- **Runtime**: Python 3.12+
- **Async model**: `asyncio` single-threaded event loop. SQLite
  write coordination via `asyncio.Lock` owned by `engine.py`,
  injected into all writing components. The store itself is lock-free;
  callers coordinate.
- **Persistence**: SQLite. v2 MUST read v1's `workflow.db` without
  schema migration on existing tables. New tables are permitted;
  existing tables and columns MUST NOT be altered.
- **Agent interface**: Claude Agent SDK with CLI fallback.
  14 existing ESSKILLAGENT agent directories MUST load without
  modification. Knowledge Base injection MUST use absolute paths.
- **CI**: GitHub Actions. Jobs: Python Tests, Coverage Check,
  Type Check, Lint. CI MUST be green before merging.
- **Module size**: Every `.py` file < 400 lines. `engine.py` < 300
  lines.
- **Naming conventions**:
  | Category | Convention | Example |
  |----------|-----------|---------|
  | Module | lowercase_underscore | `tdd/runner.py` |
  | Class | PascalCase noun | `TaskRunner` |
  | Public method | lowercase_underscore, verb-led | `run_stage()` |
  | Private method | `_` prefix | `_commit_and_push()` |
  | Constant | UPPER_UNDERSCORE | `MAX_RETRIES` |
  | Config key | lowercase_underscore | `ci_timeout` |

## Development Workflow

### Four-Stage Pipeline

Every project MUST execute the full pipeline unless stages are
explicitly skipped via `skip_stages` configuration:

1. **Spec**: constitution, specify, clarify, review.
2. **Plan**: plan, research, tasks, review.
3. **Implement**: TDD (serial + parallel), review, push + CI.
4. **Acceptance**: verification, traceability matrix, review.

### Parallel TDD Safety Rules

1. `[P]` tasks MUST have a non-empty `file_path` (enforced by
   generator, parser, and runtime validator).
2. Parallel tasks in the same group MUST NOT share `file_path`
   values. Conflicts trigger automatic fallback to serial execution.
3. Phase A (RED): agents run in parallel, then batch commit + CI.
4. Phase B (GREEN): agents run in parallel, then batch commit + CI
   with retry loop.
5. `git add` scope MUST be limited to project source directories,
   excluding `.workflow/`, `.git/`, and `node_modules/`.

### Review and Quality Gates

- Three-way parallel review: code, security, brooks.
- Auto-fix loop: review failure triggers fixer agent, then re-review.
- Feature-gap detection: missing functionality discovered during
  review MUST generate supplemental tasks and re-enter TDD.
- Gate: each stage MUST pass its review gate before advancing.
- Checkpoint: stage completion is persisted to SQLite for resume.

### CLI Interface

The orchestrator MUST expose these sub-commands:

- `run` -- start a new pipeline execution.
- `resume` -- continue from the last checkpoint.
- `retry <task_id>` -- re-execute a single task.
- `status` -- display current pipeline progress.

## Governance

This constitution is the supreme authority for all design and
implementation decisions in the E+S Orchestrator v2 project. When
any practice, pattern, or convention conflicts with this document,
this document prevails.

### Amendment Procedure

1. Propose the change with rationale in a pull request modifying
   this file.
2. The change MUST include a version bump following semantic
   versioning:
   - MAJOR: backward-incompatible principle removal or redefinition.
   - MINOR: new principle or materially expanded guidance.
   - PATCH: clarification, wording, or typo fix.
3. Update `LAST_AMENDED_DATE` to the date of merge.
4. Propagate changes to any dependent artifacts (CLAUDE.md,
   reference docs, agent knowledge files) in the same PR.

### Compliance

- All pull requests and code reviews MUST verify compliance with
  this constitution.
- Added complexity MUST be justified against the relevant principle.
- `CLAUDE.md` serves as the runtime development guidance file and
  MUST remain consistent with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-04-01 | **Last Amended**: 2026-04-01
