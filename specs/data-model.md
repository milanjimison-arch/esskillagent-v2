# E+S Orchestrator v2 — Data Model

**Created**: 2026-04-01
**Status**: Draft
**Related**: [spec.md](spec.md) | [plan.md](plan.md)

## Overview

本文档定义 v2 所有持久化实体、内存数据结构、以及它们之间的关系。
设计原则：frozen dataclass 包装查询结果，底层 SQL 与 v1 完全兼容。

---

## 1. SQLite Schema（v1 兼容层）

v2 **不修改** v1 的 8 个表，仅可新增表。

### 1.1 stage_progress

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | 阶段 ID: spec / plan / implement / acceptance |
| status | TEXT | NOT NULL DEFAULT 'pending' | pending / running / completed / failed |
| started_at | TEXT | | ISO 8601 |
| completed_at | TEXT | | ISO 8601 |
| retries | INTEGER | DEFAULT 0 | 当前阶段已重试次数 |
| max_retries | INTEGER | DEFAULT 3 | |
| gate_verdict | TEXT | | pass / fail |
| gate_feedback | TEXT | | Opus 审核反馈 |
| checkpoint_sha | TEXT | | 阶段完成时的 git SHA |

### 1.2 step_status

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| phase | TEXT | NOT NULL | 所属阶段 |
| step | TEXT | NOT NULL | 子步骤名 (constitution, specify, clarify, review, ...) |
| status | TEXT | DEFAULT 'pending' | pending / running / completed / failed |
| detail | TEXT | | 步骤产出摘要 |
| started_at | TEXT | | |
| completed_at | TEXT | | |
| | | UNIQUE(phase, step) | |

### 1.3 tasks

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PK | T001, T002, ... |
| phase_num | INTEGER | | 排序用阶段编号 |
| description | TEXT | NOT NULL | 任务描述 |
| file_path | TEXT | | 主文件路径（[P] 必填） |
| story_ref | TEXT | | US1, US2, ... |
| parallel | INTEGER | DEFAULT 0 | 1=[P] 并行标记 |
| depends_on | TEXT | | 逗号分隔的依赖 task ID |
| status | TEXT | DEFAULT 'pending' | pending / red / green / failed |
| started_at | TEXT | | |
| completed_at | TEXT | | |
| tdd_phase | TEXT | | 当前 TDD 阶段 (red/green) |
| review_notes | TEXT | | 审查反馈 |

### 1.4 reviews

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| phase | TEXT | NOT NULL | 所属阶段 |
| stage | TEXT | NOT NULL | 子阶段 |
| reviewer | TEXT | NOT NULL | code / security / brooks |
| verdict | TEXT | NOT NULL | pass / fail |
| critical | INTEGER | DEFAULT 0 | 严重问题数 |
| high | INTEGER | DEFAULT 0 | |
| medium | INTEGER | DEFAULT 0 | |
| low | INTEGER | DEFAULT 0 | |
| issues | TEXT | | JSON 数组: [{type, desc, file, line}] |
| superseded | INTEGER | DEFAULT 0 | 1=被后续 review 替代 |
| created_at | TEXT | | |

### 1.5 evidence

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| phase | TEXT | NOT NULL | |
| stage | TEXT | NOT NULL | |
| verdict | TEXT | NOT NULL | pass / fail / warn |
| checks_passed | TEXT | | JSON 数组 |
| checks_failed | TEXT | | JSON 数组 |
| findings | TEXT | | 发现摘要 |
| artifacts | TEXT | | 产出文件列表 |
| output_hash | TEXT | | 产出内容 SHA256 |
| prior_id | INTEGER | | 前序 evidence ID（重试链） |
| batch_id | TEXT | | 批次 UUID |
| created_at | TEXT | | |

### 1.6 lvl_entries（审计日志）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| fact | TEXT | NOT NULL | 事实描述 |
| phase | TEXT | | |
| stage | TEXT | | |
| sub_stage | TEXT | | |
| result | TEXT | CHECK IN ('pass','fail','warn','skip','info') | |
| method | TEXT | | 验证方法 |
| detail | TEXT | | |
| file_hash | TEXT | | |
| git_sha | TEXT | | |
| agent_id | TEXT | | |
| attempt | INTEGER | DEFAULT 1 | |
| superseded | INTEGER | DEFAULT 0 | |
| created_at | TEXT | | |

### 1.7 checkpoints

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | |
| name | TEXT | NOT NULL | 检查点名 |
| phase | TEXT | NOT NULL | |
| git_sha | TEXT | NOT NULL | |
| stage_snapshot | TEXT | | JSON: 所有阶段状态快照 |
| tasks_snapshot | TEXT | | JSON: 所有 task 状态快照 |
| created_at | TEXT | | |

### 1.8 freeze_status（LVL 冻结）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| phase | TEXT | PK | |
| frozen | INTEGER | DEFAULT 0 | |
| frozen_at | TEXT | | |
| git_sha | TEXT | | |

### 1.9 config_cache（v2 新增）

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| key | TEXT | PK | 配置键 |
| value | TEXT | NOT NULL | JSON 序列化值 |
| source | TEXT | NOT NULL | defaults / brownfield / project / env |
| updated_at | TEXT | | |

> **v1 兼容性**：config_cache 是新表，不影响 v1 数据库。v2 读取 v1 DB 时该表不存在，migration 代码自动创建。

---

## 2. Python 数据模型（frozen dataclass）

所有模型定义在 `orchestrator/store/models.py`。

### 2.1 Task

```python
@dataclass(frozen=True)
class Task:
    id: str                    # "T001"
    phase_num: int | None      # 排序编号
    description: str
    file_path: str | None      # [P] 任务必填
    story_ref: str | None      # "US1"
    parallel: bool             # [P] 标记
    depends_on: list[str]      # ["T001", "T002"]
    status: str                # pending / red / green / failed
    started_at: str | None
    completed_at: str | None
    tdd_phase: str | None      # red / green
    review_notes: str | None
```

### 2.2 StageProgress

```python
@dataclass(frozen=True)
class StageProgress:
    id: str                    # spec / plan / implement / acceptance
    status: str                # pending / running / completed / failed
    started_at: str | None
    completed_at: str | None
    retries: int
    max_retries: int
    gate_verdict: str | None
    gate_feedback: str | None
    checkpoint_sha: str | None
```

### 2.3 StepStatus

```python
@dataclass(frozen=True)
class StepStatus:
    id: int
    phase: str
    step: str
    status: str
    detail: str | None
    started_at: str | None
    completed_at: str | None
```

### 2.4 Review

```python
@dataclass(frozen=True)
class Review:
    id: int
    phase: str
    stage: str
    reviewer: str              # "code" / "security" / "brooks"
    verdict: str               # "pass" / "fail"
    critical: int
    high: int
    medium: int
    low: int
    issues: list[dict] | None  # JSON parsed
    superseded: bool
    created_at: str | None
```

### 2.5 Evidence

```python
@dataclass(frozen=True)
class Evidence:
    id: int
    phase: str
    stage: str
    verdict: str
    checks_passed: list[str] | None
    checks_failed: list[str] | None
    findings: str | None
    artifacts: list[str] | None
    output_hash: str | None
    prior_id: int | None
    batch_id: str | None
    created_at: str | None
```

### 2.6 LVLEntry

```python
@dataclass(frozen=True)
class LVLEntry:
    id: int
    fact: str
    phase: str | None
    stage: str | None
    sub_stage: str | None
    result: str                # pass / fail / warn / skip / info
    method: str | None
    detail: str | None
    file_hash: str | None
    git_sha: str | None
    agent_id: str | None
    attempt: int
    superseded: bool
    created_at: str | None
```

### 2.7 Checkpoint

```python
@dataclass(frozen=True)
class Checkpoint:
    id: int
    name: str
    phase: str
    git_sha: str
    stage_snapshot: dict | None  # JSON parsed
    tasks_snapshot: dict | None  # JSON parsed
    created_at: str | None
```

### 2.8 CheckResult（内存模型，不持久化）

```python
@dataclass(frozen=True)
class CheckResult:
    success: bool
    detail: str
    jobs: list[JobResult] | None = None  # CI 模式下的 per-job 结果

@dataclass(frozen=True)
class JobResult:
    name: str                  # "Frontend Tests", "Rust Tests"
    conclusion: str            # "success" / "failure" / "skipped"
    relevant: bool             # 是否与当前 task stack 相关
    log_excerpt: str | None    # 截取的错误日志（在 2000 字符预算内）
```

### 2.9 Configuration（内存模型，可缓存到 config_cache）

```python
@dataclass(frozen=True)
class Configuration:
    # 模型
    model_default: str         # "claude-sonnet-4-6"
    model_spec: str            # "claude-opus-4-6"
    model_reviewer: str        # "claude-opus-4-6"

    # 测试
    test_command: str           # "npm test"
    local_test: bool            # True=本地, False=CI
    ci_timeout: int             # 秒

    # 重试
    max_retries: int
    max_green_retries: int
    max_fix_retries: int

    # 超时
    stage_timeout: int

    # 阶段跳过
    skip_stages: list[str]      # 显式跳过的阶段列表

    # 来源追踪
    _sources: dict[str, str]    # key -> "defaults" / "brownfield" / "project" / "env"
```

---

## 3. 实体关系图

```
┌──────────────┐       ┌──────────────┐
│ stage_progress│       │  step_status │
│   (4 rows)   │──1:N──│              │
│ id=spec/plan/│       │ phase=spec   │
│ implement/   │       │ step=consti- │
│ acceptance   │       │   tution/... │
└──────┬───────┘       └──────────────┘
       │
       │ 1:N
       ▼
┌──────────────┐       ┌──────────────┐
│    tasks     │       │   reviews    │
│ id=T001...   │       │ phase+stage  │
│ status=      │       │ reviewer=    │
│ pending/red/ │       │ code/security│
│ green/failed │       │ /brooks      │
└──────┬───────┘       └──────┬───────┘
       │                      │
       │ 1:N                  │ 1:N
       ▼                      ▼
┌──────────────┐       ┌──────────────┐
│ lvl_entries  │       │   evidence   │
│ 审计日志     │       │ prior_id →   │
│ fact + result│       │ evidence.id  │
│ + git_sha    │       │ (重试链)     │
└──────────────┘       └──────────────┘

┌──────────────┐       ┌──────────────┐
│ checkpoints  │       │ freeze_status│
│ phase + sha  │       │ phase=PK     │
│ snapshots    │       │ frozen=0/1   │
└──────────────┘       └──────────────┘

┌──────────────┐
│ config_cache │  ← v2 新增
│ key + value  │
│ + source     │
└──────────────┘
```

---

## 4. 状态机

### 4.1 Stage 状态机

```
pending ──→ running ──→ completed
              │              ↑
              ▼              │
           failed ───(retry)─┘
```

### 4.2 Task 状态机

```
pending ──→ red ──→ green ──→ (done)
             │       │
             ▼       ▼
          failed   failed
             │       │
             └──(retry)──→ red / green
```

### 4.3 Review 状态机

```
(create) ──→ pass ──→ stage 放行
              │
              ▼
            fail ──→ auto-fix ──→ re-review
                       │            │
                       ▼            ▼
                    (max retries) → fail (终止)
```

---

## 5. 配置加载层级

```
Layer 1: orchestrator/defaults.yaml    (内置默认)
    ↓ merge
Layer 2: <project>/brownfield.yaml     (v1 兼容，可选)
    ↓ merge
Layer 3: <project>/.orchestrator.yaml  (项目覆盖，可选)
    ↓ merge
Layer 4: ORCHESTRATOR_* 环境变量       (运行时覆盖)
    ↓
Final: Configuration (frozen dataclass)
```

合并规则：后层覆盖前层同名 key。嵌套 dict (如 `models`) 递归合并。

---

## 6. Migration 策略

```python
# store/db.py
MIGRATIONS = [
    # v1 → v2: 仅新增表，不改已有表
    """
    CREATE TABLE IF NOT EXISTS config_cache (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        source     TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now'))
    );
    """,
]

def migrate(conn: sqlite3.Connection) -> None:
    """幂等执行所有 migration。"""
    for sql in MIGRATIONS:
        conn.executescript(sql)
```

---

## 7. Row → Dataclass 映射约定

```python
# store/queries.py 中的通用模式
def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        phase_num=row["phase_num"],
        description=row["description"],
        file_path=row["file_path"],
        story_ref=row["story_ref"],
        parallel=bool(row["parallel"]),
        depends_on=row["depends_on"].split(",") if row["depends_on"] else [],
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        tdd_phase=row["tdd_phase"],
        review_notes=row["review_notes"],
    )
```

- JSON 字段 (issues, checks_passed, ...) 在映射时 `json.loads`
- `parallel` / `superseded` / `frozen` 从 INTEGER 映射为 `bool`
- `depends_on` 从逗号分隔 TEXT 映射为 `list[str]`
