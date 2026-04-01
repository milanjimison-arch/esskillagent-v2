# E+S Orchestrator v2 — 重构需求

## 背景

当前编排器（v1, `F:\claude\技能备份\E+S\`）经过多轮迭代已积累大量技术债：
- 6674 行 Python 代码，19 个模块，命名和职责边界混乱
- engine.py 仍有 1249 行，是多个关注点的混合体
- checks.py 和 ci_checks.py 职责重叠，通过 dict mutation 切换
- 模块命名不一致（engine_support、engine_log、wave_common）
- task_parser 和 task-generator 格式未对齐导致运行时 bug
- 并行 TDD 逻辑复杂且刚修复多个 CRITICAL 问题
- 配置只有全局 brownfield.yaml，无项目级覆盖
- Wave 面板代码和核心逻辑耦合

## 目标

完全重写编排器，保留经过验证的设计决策，修正已知缺陷，实现：
1. **模块职责清晰** — 每个文件一个关注点，< 400 行
2. **命名一致** — 统一的命名规范，模块/类/函数风格统一
3. **配置分层** — 全局默认 + 项目级覆盖
4. **测试策略可插拔** — local/CI 切换不靠 dict mutation
5. **并行安全** — 并行 TDD 的 git 冲突和 stack scoping 内建而非修补

## 前代参考

v1 代码在 `F:\claude\技能备份\E+S\`，可参考设计决策和实现模式，但不直接复制。

**可复用的设计决策**（经实践验证）：
- 四阶段流水线：spec → plan → implement → acceptance
- Agent 注册表 + 渐进式知识加载（Knowledge Base 路径注入）
- SessionManager 统一 agent/claude 调用 + session 续接
- Store (SQLite) 持久化状态 + LVL 审计日志 + 证据链
- ReviewPipeline 并行审查（code + security + brooks）
- CI Checks 的 commit SHA 精确匹配 run ID
- task_runner 两阶段并行（Phase A: 并行 RED → 批量验证，Phase B: 并行 GREEN → 批量验证 + 重试）
- Stack scoping（rust/frontend 分离，只检查相关 CI job）
- Feature-gap 检测（审查发现功能缺失时动态创建补充 task）
- Traceability matrix（FR→Task→Test 追溯矩阵生成）

**必须修正的已知缺陷**：
- `checks.py` + `ci_checks.py` 的 CHECKERS dict mutation 模式 → 改为策略接口
- `engine.py` 仍然 1249 行 → 拆分到 stages/ 子包
- `engine_support.py` / `engine_log.py` 命名模糊 → 按职责重命名
- task_parser 的 file_path 提取不稳健 → 与 task-generator 格式强制对齐 + 契约测试
- `_get_failed_log` 截断策略 → 按 job 结构化提取，2000 字符预算
- GREEN retry 时 agent 只看到部分错误 → per-job 错误反馈，仅包含相关 stack
- Wave 面板代码（3 个模块 1100 行）和核心逻辑耦合 → 独立 ui/ 包
- `brownfield.yaml` 全局唯一 → 支持项目目录下 `.orchestrator.yaml` 覆盖
- `ci_tests_must_fail` 和 `ci_tests_must_pass` 有各自独立的 job 检查逻辑 → 统一到 CheckStrategy
- `_is_small_project` 自动跳过阶段不可靠 → 删除，所有项目执行完整流水线，跳过由用户配置显式指定

## 架构要求

### 模块结构

```
orchestrator/
├── __init__.py
├── cli.py                  # 入口：参数解析 + 启动 + resume + retry
├── config.py               # 配置加载：全局默认 + 项目覆盖 + 环境变量
├── engine.py               # 阶段流转控制（< 300 行），不含具体阶段逻辑
├── stages/
│   ├── __init__.py
│   ├── base.py             # Stage 基类（共享的 review + gate + checkpoint 逻辑）
│   ├── spec.py             # spec 阶段：constitution → specify → clarify → review
│   ├── plan.py             # plan 阶段：plan → research → tasks → review
│   ├── implement.py        # implement 阶段：TDD → review → push+CI
│   └── acceptance.py       # acceptance 阶段：验收 → traceability → review
├── tdd/
│   ├── __init__.py
│   ├── runner.py           # TDD 任务调度（串行 + 并行）
│   ├── parser.py           # tasks.md 解析（与 task-generator 格式强制对齐）
│   └── validator.py        # [P] 并行校验（file_path 冲突检测）
├── review/
│   ├── __init__.py         # 导出 ReviewPipeline + AutoFixer
│   └── pipeline.py         # 并行审查 + 自动修复循环（合并为单文件）
├── checks/
│   ├── __init__.py
│   ├── base.py             # CheckStrategy 抽象接口
│   ├── local.py            # 本地测试策略（npm test / cargo test）
│   ├── ci.py               # CI 测试策略（commit → push → gh run watch）
│   └── common.py           # 通用检查（file_exists, coverage, no_critical, verdict_parser）
├── agents/
│   ├── __init__.py
│   ├── registry.py         # Agent 注册表 + 渐进式知识加载
│   ├── adapter.py          # Claude SDK/CLI 调用适配器
│   └── session.py          # Session 续接管理
├── store/
│   ├── __init__.py
│   ├── db.py               # SQLite 连接 + schema migrations + 锁管理
│   ├── models.py           # 数据模型（Task, Review, Evidence, StageProgress）— 仅定义
│   └── queries.py          # 查询方法 — 返回 models 中的类型，内部用 sqlite3.Row
├── ui/                     # 可选模块，核心不 import
│   ├── __init__.py
│   ├── wave.py             # Wave 面板（overview + stage detail 合并）
│   └── notifier.py         # 桌面通知
└── defaults.yaml           # 全局默认配置
```

### 命名规范

| 类别 | 规范 | 示例 |
|------|------|------|
| 模块名 | 小写下划线，描述职责 | `tdd/runner.py`, `checks/ci.py` |
| 类名 | PascalCase，名词 | `TaskRunner`, `CheckStrategy`, `ReviewPipeline` |
| 公开方法 | 小写下划线，动词开头 | `run_stage()`, `parse_tasks()`, `check_green()` |
| 私有方法 | `_` 前缀 | `_commit_and_push()`, `_get_run_id()` |
| 常量 | 大写下划线 | `STAGE_NAMES`, `MAX_RETRIES` |
| 配置键 | 小写下划线 | `local_test`, `ci_timeout`, `max_green_retries` |

### 检查策略接口

```python
# checks/base.py
from abc import ABC, abstractmethod

class CheckStrategy(ABC):
    """测试验证策略 — local 和 CI 两种实现。"""

    @abstractmethod
    def tests_must_fail(self, cwd: str, task_id: str, file_path: str) -> tuple[bool, str]:
        """RED: 测试必须失败（断言失败，非编译错误）。"""

    @abstractmethod
    def tests_must_pass(self, cwd: str, task_id: str, file_path: str) -> tuple[bool, str]:
        """GREEN: 测试必须通过。"""

# engine.py 初始化 — 由 config 决定策略，调用方不感知
if config.local_test:
    self.checker = LocalCheckStrategy(config)
else:
    self.checker = CICheckStrategy(config)
```

### 配置分层

```yaml
# orchestrator/defaults.yaml — 全局默认
models:
  default: claude-sonnet-4-6
  spec: claude-opus-4-6
  reviewer: claude-opus-4-6
test_command: npm test
local_test: true
ci_timeout: 1800
max_retries: 3
max_green_retries: 3
max_fix_retries: 2
stage_timeout: 3600

# 项目目录/.orchestrator.yaml — 项目级覆盖（可选）
local_test: false
test_command: "cargo test -- --test-threads=1"
ci_timeout: 2400
```

加载顺序：`defaults.yaml` → `brownfield.yaml`（v1 兼容）→ `.orchestrator.yaml`（项目覆盖），后者覆盖前者。

### tasks.md 格式强制规范

parser 和 generator 必须对齐的格式：

```
- [ ] T001 [P?] [US*?] [FR-###]+ Description — primary/file/path.ext
```

- `—` (em dash) 分隔描述和路径，**强制**
- `[P]` 标记必须有非空 file_path
- parser 用 em dash 提取路径（主策略），回退到 "in src/..." 模式
- generator 的 tasks-command.md 强制此格式
- **契约测试**：`tests/test_task_format.py` 用 generator 输出的样例验证 parser 能正确解析

### Stack Scoping 内建

CI 模式的 stack 检测从一开始设计进 CheckStrategy 接口：

```python
class CICheckStrategy(CheckStrategy):
    def tests_must_fail(self, cwd, task_id, file_path):
        stack = detect_stack(file_path)  # rust/frontend/None
        # ... push + wait CI ...
        return self._evaluate_red(jobs, stack)

    def tests_must_pass(self, cwd, task_id, file_path):
        stack = detect_stack(file_path)
        # ... push + wait CI ...
        return self._evaluate_green(jobs, stack)
```

RED 和 GREEN 共用同一套 `_evaluate_red` / `_evaluate_green` 方法，不再有两套独立的 job 检查逻辑。

### 并行 TDD 安全约束

1. [P] task 必须有 file_path（generator 强制 + parser 校验 + validator 运行时兜底）
2. 同组 [P] task 的 file_path 不重叠（validator 检查，冲突时降级串行）
3. Phase A（RED）: agents 并行 → 一次 batch commit+CI（一个坏测试会失败整组，已记录为设计决策）
4. Phase B（GREEN）: agents 并行 → 一次 batch commit+CI + 重试循环（安全前提：非重叠 file_path）
5. `git add` 范围限制在项目源码目录，排除 `.workflow/`

### 并发模型

- 所有异步操作用 `asyncio`（单线程事件循环）
- SQLite 写入保护：`asyncio.Lock` 实例由 engine.py 创建，注入到所有需要写 store 的组件（stages、tdd/runner、review/pipeline）
- 并行 agent 调用（`asyncio.gather`）后，store 写入在 for 循环中顺序执行（gather 后不存在并发写入）
- `asyncio.Lock` 的所有权在 engine.py，不在 store 内部 — store 本身是无锁的，调用方负责协调

## 功能范围

### 必须保留
- 四阶段流水线 + Opus 阶段审核 + Gate + Checkpoint
- TDD RED→GREEN 循环（串行 + 并行）
- 三路并行审查（code + security + brooks）
- 自动修复循环（审查失败 → fixer → re-review）
- Feature-gap 检测（审查发现 "missing/unimplemented" → 动态创建补充 task → 重跑 TDD）
- Traceability matrix（FR→Task→Test 追溯矩阵，生成到 specs/checklists/traceability.md）
- SQLite 持久化 + LVL 审计 + 证据链
- Agent 注册表 + 渐进式知识加载
- Session 续接
- Push + CI 等待 + 自动修复
- Checkpoint/Resume（从任意阶段断点恢复）
- Wave 面板（独立模块，可选）
- 桌面通知

### 必须新增
- 项目级配置覆盖（`.orchestrator.yaml`）
- CheckStrategy 接口（local/CI 可插拔）
- 结构化 CI 错误反馈（per-job 摘要，2000 字符预算，仅相关 stack）
- Stack scoping 内建于 CheckStrategy
- tasks.md 格式校验（parser 启动时校验 + 报告不兼容的 task）
- tasks.md 契约测试（parser ↔ generator 格式对齐验证）
- CLI 子命令：`run`（启动新流程）、`resume`（从断点恢复）、`retry <task_id>`（重跑单 task）、`status`（查看进度）

### 可选改进
- 进度百分比（已完成 task / 总 task）
- 实时日志流到 Wave 面板

## 测试策略

### 测试基础设施

参考 `reference/python-testing.md`，测试框架用 pytest。

```
tests/
├── conftest.py              # 共享 fixture（mock store, mock agent, temp project dir）
├── fixtures/
│   ├── workflow.db           # v1 数据库快照（用于 schema 兼容验证）
│   ├── tasks_valid.md        # 格式正确的 tasks.md 样例
│   └── tasks_invalid.md      # 格式错误的 tasks.md 样例
├── unit/
│   ├── test_config.py        # 配置加载 + 分层覆盖
│   ├── test_parser.py        # tasks.md 解析 + 格式校验
│   ├── test_validator.py     # [P] 并行冲突检测
│   ├── test_check_local.py   # LocalCheckStrategy
│   ├── test_check_ci.py      # CICheckStrategy（mock subprocess + gh CLI）
│   ├── test_store.py         # Store CRUD + migration
│   └── test_registry.py      # Agent 注册 + 知识加载
├── integration/
│   ├── test_tdd_runner.py    # TDD 串行 + 并行（mock agent calls）
│   ├── test_review.py        # 审查流水线（mock agent calls）
│   └── test_resume.py        # 从 v1 DB 恢复（用 fixtures/workflow.db）
└── contract/
    └── test_task_format.py   # parser ↔ generator 格式契约
```

### Mock 策略

| 外部依赖 | Mock 方式 |
|----------|----------|
| Claude SDK / CLI | `MockSessionManager` — 返回预设 `ClaudeResult` |
| git 操作 | `monkeypatch` subprocess.run — 返回预设 stdout/stderr |
| GitHub Actions CI | `MockCICheckStrategy` — 直接返回 (True/False, detail) |
| SQLite | 内存数据库 `":memory:"` + 真实 schema migration |
| 文件系统 | `tmp_path` fixture（pytest 内建） |

### 覆盖率目标

- 总体：80%+
- checks/：90%+（核心判定逻辑）
- tdd/parser.py：95%+（格式解析是高风险区）
- store/：85%+（数据完整性）

## DB Schema 兼容策略

v2 的 store 必须能读取 v1 的 `.workflow/workflow.db`：

- **表结构不变**：保留 v1 的 8 个表（tasks, reviews, evidence, stage_progress, step_status, lvl, checkpoints, settings）
- **列不变**：不增删列，不改类型
- **Python API 可变**：v2 用 `@dataclass(frozen=True)` 包装查询结果，但底层 SQL 查询保持兼容
- **新增表允许**：v2 可以加新表（如 config_cache），但不修改 v1 的表
- **验证方式**：`tests/integration/test_resume.py` 用 `fixtures/workflow.db`（v1 快照）测试恢复

## 技术约束

- Python 3.12+
- 每个模块 < 400 行
- engine.py < 300 行
- 类型标注所有公开 API
- 无裸 except（必须指定异常类型）
- 不可变数据优先（dataclass frozen=True，dict 不原地修改）
- 异步 I/O 用 asyncio（与 v1 一致）
- Claude Agent SDK + CLI 降级（与 v1 一致）

## 验收标准

1. 所有 Python 模块各 < 400 行，engine.py < 400 行
2. CheckStrategy 接口：切换 `local_test` 配置无需改动调用方
3. 现有 ESSKILLAGENT agent 目录（14 个 agent）无需修改即可加载
4. brownfield.yaml 兼容 v1 格式 + `.orchestrator.yaml` 项目覆盖生效
5. Wave 面板代码在 `ui/` 包中，核心模块不 import ui
6. 从 v1 的 `.workflow/workflow.db` 可恢复运行（fixtures 测试验证）
7. CLI 子命令 `run` / `resume` / `retry` / `status` 可用
8. pytest 测试覆盖率 80%+
9. CI 全绿（GitHub Actions）
10. 契约测试验证 parser ↔ generator 格式一致
