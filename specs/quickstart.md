# Quickstart Guide: E+S Orchestrator v2

**Date**: 2026-04-02

---

## Environment Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required for `type` union syntax and performance improvements |
| Git | 2.30+ | Project must be a git repository |
| Claude CLI | Latest | Or Claude Agent SDK (auto-detected) |
| pip | 23.0+ | For dependency installation |

### Optional

| Tool | Purpose |
|------|---------|
| GitHub CLI (`gh`) | CI check strategy and PR operations |
| Wave (H2O Wave) | Optional dashboard UI |

---

## Installation

### 1. Clone and enter the project

```bash
git clone <repository-url>
cd ESSKILLAGENT-v2
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

The `requirements.txt` includes:
- `pyyaml` -- Configuration file parsing
- `aiosqlite` -- Async SQLite access
- `pytest` -- Test framework
- `pytest-asyncio` -- Async test support

### 4. Verify Claude CLI is available

```bash
claude --version
```

If using the Claude Agent SDK instead, ensure it is installed:

```bash
pip install claude-agent-sdk
```

The orchestrator auto-detects SDK availability and falls back to CLI if the SDK is not installed.

---

## Project Configuration

### Configuration layering

The orchestrator loads configuration from four sources (later overrides earlier):

1. `orchestrator/defaults.yaml` -- Bundled defaults (always loaded)
2. `<project>/brownfield.yaml` -- v1 compatibility layer (optional)
3. `<project>/.orchestrator.yaml` -- Project-specific overrides (optional)
4. Environment variables with `ORCH_` or `ORCHESTRATOR_` prefix

### Minimal `.orchestrator.yaml`

Create this file in your project root to customize behavior:

```yaml
# Skip stages you don't need
skip_stages: []

# Local test execution (set to false for CI-based verification)
local_test: true

# Maximum auto-fix retries per review gate
max_fix_retries: 3

# Maximum GREEN-phase retries per task
max_green_retries: 3

# Enable parallel task execution
parallel: false

# CI timeout in seconds (only when local_test: false)
ci_timeout: 300
```

### Environment variable overrides

Any top-level config key can be overridden via environment variable:

```bash
# Override max_retries
export ORCH_MAX_RETRIES=5

# Override parallel execution
export ORCHESTRATOR_PARALLEL=true
```

---

## Basic Usage

### Prerequisites

Your project directory must:
1. Be a git repository (`git init` if needed)
2. Contain a requirement/feature description file

### Run a full pipeline

```bash
python -m orchestrator run --config .orchestrator.yaml
```

This executes all four stages in order:

1. **Spec** -- AI agent writes a feature specification from your requirement
2. **Plan** -- AI agent creates an implementation plan with tasks
3. **Implement** -- TDD cycles (RED -> GREEN -> Review) for each task
4. **Acceptance** -- Traceability verification and acceptance report

The orchestrator stores all state in `.workflow/workflow.db` (SQLite).

### Resume an interrupted pipeline

If a pipeline run is interrupted (crash, timeout, Ctrl+C):

```bash
python -m orchestrator resume
```

Resume behavior depends on which stage was interrupted:
- **Spec/Plan/Acceptance**: Re-runs the entire stage (these stages are atomic)
- **Implement**: Resumes from the last completed task (task-level checkpointing)

### Retry a blocked task

If a specific task is marked BLOCKED after implementation:

```bash
python -m orchestrator retry --stage implement
```

This re-executes only the blocked task's TDD cycle without affecting other completed tasks.

### Check pipeline status

```bash
python -m orchestrator status
```

Displays:
- Current pipeline stage
- Task counts by status (pending / running / done / blocked)
- Any active warnings from the PipelineMonitor
- Recent LVL events

---

## CLI Command Reference

### `orchestrator run`

Start a new pipeline execution.

```
Usage: python -m orchestrator run [OPTIONS]

Options:
  --config PATH    Path to config file (default: auto-detect .orchestrator.yaml)

Exit codes:
  0    Pipeline completed successfully (all stages passed)
  1    Pipeline failed (a stage exceeded max retries)
```

### `orchestrator resume`

Resume a previously interrupted pipeline.

```
Usage: python -m orchestrator resume

Exit codes:
  0    Pipeline resumed and completed successfully
  1    No checkpoint found or pipeline failed on resume
```

### `orchestrator retry`

Retry a specific failed/blocked stage or task.

```
Usage: python -m orchestrator retry [OPTIONS]

Options:
  --stage NAME     Stage to retry (e.g., "implement")

Exit codes:
  0    Retry succeeded
  1    Retry failed or invalid target
```

### `orchestrator status`

Display current pipeline progress.

```
Usage: python -m orchestrator status

Output:
  Pipeline: <pipeline_id>
  Stage: <current_stage> (<status>)
  Tasks: <done>/<total> done, <blocked> blocked, <pending> pending
  Monitor: <health_status>
```

---

## Development Workflow

### Running tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run only unit tests
python -m pytest tests/unit/ -v

# Run contract tests (parser/generator alignment)
python -m pytest tests/contract/ -v

# Run integration tests
python -m pytest tests/integration/ -v

# Run with coverage
python -m pytest tests/ --cov=orchestrator --cov-report=term-missing
```

### Coverage targets

| Module | Target |
|--------|--------|
| Overall | 80%+ |
| `checks/` | 90%+ |
| `tdd/parser.py` | 95%+ |
| `store/` | 85%+ |

### Project structure overview

```
orchestrator/           # Source code
  cli.py                # CLI entry point
  config.py             # Configuration loading
  engine.py             # Pipeline flow controller (< 300 lines)
  monitor.py            # Global health monitoring
  perception.py         # Agent output scanning
  stages/               # Four pipeline stages
  tdd/                  # TDD runner and parser
  review/               # Three-way review pipeline
  checks/               # Test verification strategies
  agents/               # Agent adapter and registry
  store/                # SQLite persistence
  ui/                   # Optional Wave dashboard

tests/                  # Test suite
  unit/                 # Unit tests (per module)
  contract/             # Contract tests (format alignment)
  integration/          # End-to-end tests

agents-src/             # Agent knowledge files (14 agents)
specs/                  # Design documents
reference/              # Coding standards and patterns
```

---

## Troubleshooting

### "not a git repository" error

The orchestrator requires a git repository. Initialize one if needed:

```bash
cd your-project
git init
git add .
git commit -m "Initial commit"
```

### "claude not found" error

Ensure the Claude CLI is installed and on your PATH:

```bash
which claude    # Linux/macOS
where claude    # Windows
```

If using the SDK instead, install it:

```bash
pip install claude-agent-sdk
```

### Resume finds no checkpoint

This means no stage completed successfully before the interruption. Run a fresh pipeline:

```bash
python -m orchestrator run
```

### Task stuck in BLOCKED status

1. Check the task's error in the LVL log: `python -m orchestrator status`
2. Fix the underlying issue in your code
3. Retry: `python -m orchestrator retry --stage implement`

### SQLite "database is locked" error

The orchestrator uses asyncio with a single event loop and `asyncio.Lock` coordination. If you see this error, ensure only one orchestrator instance is running per project directory. Check for stale lock files:

```bash
ls .workflow/engine.lock
```

Remove the lock file if the previous process has terminated.
