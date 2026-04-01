# Quickstart: E+S Orchestrator v2

**Date**: 2026-04-01 | **Source**: [plan.md](plan.md)

---

## Prerequisites

- Python 3.12 or later
- Git (initialized repository with GitHub remote)
- GitHub CLI (`gh`) -- required for CI check strategy
- Claude Agent SDK or Claude CLI -- at least one must be available
- 14 ESSKILLAGENT agent directories at a known absolute path

### Verify prerequisites

```bash
python --version          # Expect: Python 3.12+
git --version             # Expect: git 2.x+
gh auth status            # Expect: Logged in to github.com
```

---

## Environment Setup

### 1. Clone the repository

```bash
git clone <repo-url> esskillagent-v2
cd esskillagent-v2
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
# Core dependencies (minimal)
pip install pyyaml

# Development dependencies
pip install pytest pytest-cov pytest-asyncio mypy ruff

# Optional: Claude Agent SDK
pip install claude-agent-sdk
```

### 4. Verify installation

```bash
python -m pytest tests/ -v --co    # Collect tests (dry run)
python -m orchestrator --help      # Show CLI help
```

---

## Project Configuration

### Global defaults

The file `orchestrator/defaults.yaml` ships with sensible defaults. No modification needed for most projects.

### Project-specific configuration

Create `.orchestrator.yaml` in your target project directory:

```yaml
# .orchestrator.yaml -- project-level overrides
local_test: false                    # Use CI check strategy
test_command: "pytest tests/ -v"     # Your project's test command
ci_timeout: 2400                     # CI timeout in seconds

agent_base_path: "F:/claude/ESSKILLAGENT"  # Absolute path to agent directories

stack_config:
  extensions:
    ".py": python

ci_jobs:
  python:
    - "Python Tests"
    - "Coverage Check"
```

### v1 brownfield compatibility

If you have an existing `brownfield.yaml` from v1, place it in the project root. It will be loaded between defaults and project config:

```
Loading order: defaults.yaml -> brownfield.yaml -> .orchestrator.yaml -> env vars
```

### Environment variable overrides

Any config key can be overridden via environment variables with the `ORCHESTRATOR_` prefix:

```bash
# Override CI timeout
export ORCHESTRATOR_CI_TIMEOUT=900

# Override nested keys with __ separator
export ORCHESTRATOR_MODELS__DEFAULT=claude-opus-4-6
```

---

## Basic Usage

### Start a new pipeline

```bash
python -m orchestrator run /path/to/project --req-file /path/to/requirement.md
```

This executes the full four-stage pipeline:
1. **Spec** -- generates constitution, specification, clarification, review
2. **Plan** -- generates plan, research, tasks, review
3. **Implement** -- TDD RED-GREEN cycles (serial + parallel), review, push+CI
4. **Acceptance** -- verification, traceability matrix, review

Each stage must pass its review gate before advancing to the next.

### Resume from checkpoint

If execution is interrupted (crash, timeout, manual stop):

```bash
python -m orchestrator resume /path/to/project
```

Resumes from the last completed checkpoint. No work is re-executed.

### Retry a specific task

If a single task failed during implementation:

```bash
python -m orchestrator retry /path/to/project T003
```

Re-executes only task T003 through its RED-GREEN cycle.

### Check pipeline status

```bash
python -m orchestrator status /path/to/project
```

Displays:
- Current stage and step
- Task completion count and percentage
- Failed task IDs with error summaries

---

## Pipeline Flow

```
orchestrator run
  |
  v
[Spec Stage]
  constitution -> specify -> clarify -> review gate
  |                                        |
  |  (fail: auto-fix -> re-review)         |
  v                                        v
[Plan Stage]                          checkpoint saved
  plan -> research -> tasks -> review gate
  |                                   |
  v                                   v
[Implement Stage]                checkpoint saved
  parse tasks.md
  |
  +-- Serial tasks: RED -> GREEN (one by one)
  |
  +-- [P] Parallel tasks:
  |     Phase A: parallel RED agents -> batch commit -> CI check
  |     Phase B: parallel GREEN agents -> batch commit -> CI check
  |              (retry loop for failures with per-job error feedback)
  |
  +-- Three-way review (code + security + brooks) in parallel
  |     |
  |     +-- (fail: auto-fix -> re-review)
  |     +-- (feature gap: create supplemental tasks -> re-enter TDD)
  |
  v
[Acceptance Stage]                   checkpoint saved
  verification -> traceability matrix -> review gate
  |
  v
DONE (pipeline completed)
```

---

## Running Tests

### Full test suite

```bash
python -m pytest tests/ -v
```

### With coverage report

```bash
python -m pytest tests/ --cov=orchestrator --cov-report=term-missing
```

### Coverage targets

| Module | Target |
|--------|--------|
| Overall | 80%+ |
| checks/ | 90%+ |
| tdd/parser.py | 95%+ |
| store/ | 85%+ |

### Run specific test categories

```bash
# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests only
python -m pytest tests/integration/ -v

# Contract tests only
python -m pytest tests/contract/ -v
```

### Type checking

```bash
mypy orchestrator/ --strict
```

### Linting

```bash
ruff check orchestrator/ tests/
```

---

## Directory Layout After Pipeline Execution

A completed pipeline creates the following artifacts in the project:

```
project/
├── .orchestrator.yaml          # Project config (user-created)
├── .workflow/
│   ├── workflow.db             # SQLite state (checkpoints, tasks, evidence)
│   └── outputs/                # Agent output artifacts
│       ├── constitution.txt
│       ├── specify.txt
│       └── ...
├── specs/
│   ├── spec.md                 # Generated specification
│   ├── plan.md                 # Generated plan
│   ├── data-model.md           # Data model
│   ├── tasks.md                # Generated task list
│   └── checklists/
│       ├── requirements.md     # Requirements checklist
│       └── traceability.md     # FR -> Task -> Test matrix
├── src/                        # Implementation (created by TDD agents)
└── tests/                      # Tests (created by TDD agents)
```

---

## Troubleshooting

### "No git repository found"

The orchestrator requires a git-initialized project with a GitHub remote.

```bash
cd /path/to/project
git init
gh repo create project-name --private --source=.
git add . && git commit -m "initial commit"
git push -u origin main
```

### "Agent directory not found"

Ensure `agent_base_path` in `.orchestrator.yaml` points to the absolute path containing the 14 ESSKILLAGENT agent directories.

### "CI timeout exceeded"

Increase `ci_timeout` in `.orchestrator.yaml`:

```yaml
ci_timeout: 3600  # 1 hour
```

### "Task rejected: missing file_path for parallel task"

Parallel tasks (`[P]` flag) require a `file_path` after the em-dash separator. Fix the tasks.md entry:

```
# Wrong (rejected)
- [ ] T005 [P] [US2] [FR-010] Add validation

# Correct
- [ ] T005 [P] [US2] [FR-010] Add validation -- src/validation.py
```

### "Parallel tasks fell back to serial"

Two `[P]` tasks in the same group have overlapping `file_path` values. This is a safety mechanism (not an error). To restore parallel execution, ensure each task targets a unique file.

### Check strategy not switching

Verify the configuration layer order. Run with debug logging to see which config files are loaded and the final merged values:

```bash
ORCHESTRATOR_LOG_LEVEL=DEBUG python -m orchestrator run /path/to/project
```
