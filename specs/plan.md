# E+S Orchestrator v2 — Implementation Plan

**Created**: 2026-04-01
**Status**: Draft
**Spec**: [spec.md](spec.md) | **Data Model**: [data-model.md](data-model.md) | **Quick Start**: [quickstart.md](quickstart.md)

---

## Executive Summary

将 v1（6674 行、19 模块）完全重写为 v2，目标模块结构 ~25 个文件、每个 < 400 行。
采用 Bottom-Up 构建顺序：先基础层（data model, config, store），再核心层（checks, parser, agents），
然后组合层（tdd runner, review pipeline, stages），最后顶层（engine, CLI, UI）。

全部 17 个任务分为 6 个 Phase，预计实施 Task 总计 17 个。

---

## Phase 1: Foundation — 数据模型 + 配置 + 持久化

> 建立所有上层模块依赖的地基。无外部依赖，可独立测试。

### T001 [US4] [FR-001][FR-002][FR-003][FR-004] 配置系统 — orchestrator/config.py

**实现内容**：
- `Configuration` frozen dataclass（见 data-model.md §2.9）
- `load_config(project_path)` 函数：按 defaults.yaml → brownfield.yaml → .orchestrator.yaml → env 顺序加载合并
- 未知 key 警告（`warnings.warn`）但不中断
- `ORCHESTRATOR_*` 环境变量覆盖
- 嵌套 dict（如 `models`）递归合并

**关键决策**：
- 配置加载一次生成不可变对象，整个生命周期不再修改
- `_sources` 字段追踪每个 key 的来源层

**验收**：
- `defaults.yaml` 中所有 key 都有默认值
- `brownfield.yaml` 覆盖生效
- `.orchestrator.yaml` 覆盖生效
- 环境变量覆盖生效
- 未知 key 产生 warning

**TDD**：
```
RED:  test_config.py — test_defaults_loaded, test_project_override, test_env_override, test_unknown_key_warns
GREEN: config.py 实现
```

**预估行数**：~150 行

---

### T002 [US2][US4] [FR-039][FR-040][FR-041][FR-042][FR-043] 持久化层 — orchestrator/store/

**实现内容**：
- `store/models.py` — 7 个 frozen dataclass（Task, StageProgress, StepStatus, Review, Evidence, LVLEntry, Checkpoint）
- `store/db.py` — SQLite 连接 + WAL + busy_timeout + schema init（v1 8 表） + migration（v2 新表 config_cache）+ 锁管理接口
- `store/queries.py` — CRUD 方法，返回 frozen dataclass，内部用 `sqlite3.Row`

**关键决策**：
- `INSERT OR REPLACE` 替代 v1 的 `INSERT OR IGNORE`（修复 pitfall #9）
- Store 本身无锁，`asyncio.Lock` 由 engine.py 注入
- Migration 幂等执行（`CREATE TABLE IF NOT EXISTS`）
- v1 DB 兼容：读取时若 config_cache 不存在则自动创建

**验收**：
- 所有 8 个 v1 表 schema 完全一致
- v2 新表 config_cache 自动创建
- 从 v1 DB fixture 可成功读取数据
- frozen dataclass 返回值不可修改

**TDD**：
```
RED:  test_store.py — test_init_tables, test_upsert_task, test_row_to_dataclass, test_v1_compat
GREEN: models.py + db.py + queries.py
```

**预估行数**：models.py ~120 行, db.py ~130 行, queries.py ~250 行

---

### T003 [US4] defaults.yaml — orchestrator/defaults.yaml

**实现内容**：
- 全局默认配置文件，包含所有配置 key 的默认值

```yaml
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
skip_stages: []
```

**预估行数**：~15 行

---

## Phase 2: Core Strategies — 检查策略 + 任务解析 + Agent 系统

> 三个独立子系统，仅依赖 Phase 1 的 models 和 config。可并行开发。

### T004 [P] [US3] [FR-026][FR-027][FR-029][FR-030] 本地检查策略 — orchestrator/checks/

**实现内容**：
- `checks/base.py` — `CheckStrategy` ABC：`tests_must_fail(cwd, task_id, file_path) -> CheckResult` + `tests_must_pass(...)`
- `checks/common.py` — `detect_stack(file_path)` 用扩展名 + 路径前缀双重判断（修复 pitfall #15）
- `checks/local.py` — `LocalCheckStrategy`：调用 `config.test_command` 本地执行，解析退出码

**关键决策**：
- `detect_stack` 返回 `"rust" | "frontend" | None`
- `.rs` 文件无论目录位置都归 rust（修复 pitfall #15）
- `tests/` 目录按扩展名判断而非固定归 frontend
- 命令不存在时 `FileNotFoundError` → 快速失败

**验收**：
- `CheckStrategy` 接口定义正确
- `LocalCheckStrategy` 调用 test_command 并解析结果
- `detect_stack` 正确分类 .rs / .ts / .tsx / .js 文件
- 命令不存在时清晰报错

**TDD**：
```
RED:  test_check_local.py — test_red_pass, test_red_fail, test_green_pass, test_command_not_found, test_detect_stack
GREEN: base.py + common.py + local.py
```

**预估行数**：base.py ~40 行, common.py ~80 行, local.py ~120 行

---

### T005 [P] [US3] [FR-028][FR-029][FR-030][FR-031] CI 检查策略 — orchestrator/checks/ci.py

**实现内容**：
- `CICheckStrategy`：commit → push → `gh run list` 匹配 SHA → `gh run watch` → `_evaluate_red` / `_evaluate_green`
- `_get_failed_log`：per-job 结构化提取，2000 字符预算，`startswith(prefix)` 精确匹配（修复 pitfall #13）
- `_evaluate_red`：只看相关 stack job，TS Check 失败对 frontend task 视为有效 RED（修复 pitfall #12）
- `_evaluate_green`：skipped/cancelled = failure（修复 pitfall #14）
- git push 3 次重试 + 5 秒间隔（修复 pitfall #10）
- 所有 subprocess 捕获 `(FileNotFoundError, subprocess.TimeoutExpired)`（修复 pitfall #18）

**关键决策**：
- RED 和 GREEN 共用 `_evaluate_red` / `_evaluate_green`（修复 pitfall #1 双逻辑漂移）
- Stack scoping 内建：`detect_stack(file_path)` → 只检查相关 job
- 日志截取按 job 分段，每 job 上限 = 2000 / relevant_job_count

**验收**：
- commit SHA 匹配 run ID
- per-job 错误反馈 ≤ 2000 字符
- stack scoping 正确过滤不相关 job
- 网络重试 3 次
- subprocess 异常全捕获

**TDD**：
```
RED:  test_check_ci.py — test_red_evaluation, test_green_evaluation, test_stack_scoping,
      test_failed_log_budget, test_push_retry, test_timeout_handling
GREEN: ci.py
```

**预估行数**：~300 行

---

### T006 [P] [US1][US5] [FR-021][FR-022][FR-023][FR-024][FR-025] 任务解析 + 校验 — orchestrator/tdd/

**实现内容**：
- `tdd/parser.py` — `parse_tasks(content: str) -> list[Task]`
  - 主策略：em dash 分隔提取 file_path
  - 回退策略：`"in src/..."` 模式
  - `[P]` 无 file_path → 拒绝并报错（修复 pitfall #3）
  - 非 em dash 格式 → 标记为 non-canonical 并 warn
- `tdd/validator.py` — `validate_parallel_group(tasks: list[Task]) -> tuple[list[Task], list[Task]]`
  - 返回 (parallel_safe, demoted_to_serial)
  - file_path 重叠检测
  - 无 file_path 的 [P] task 拒绝

**关键决策**：
- 严格格式校验 + 宽容回退 = 既能捕获 generator 格式偏差，又不卡死流程
- `_group_by_phase` 支持 setup / US* / polish 三类分组，数字排序（修复 pitfall #8, #16）

**验收**：
- 标准 em dash 格式正确解析
- "in src/..." 回退正确解析
- [P] 无 file_path 报错
- 重叠 file_path 降级串行
- phase 排序正确（setup → US1 → US2 → ... → polish）

**TDD**：
```
RED:  test_parser.py — test_canonical_format, test_fallback_format, test_parallel_no_path,
      test_phase_grouping, test_polish_detection
      test_validator.py — test_no_overlap, test_overlap_demote, test_missing_path_reject
GREEN: parser.py + validator.py
```

**预估行数**：parser.py ~200 行, validator.py ~100 行

---

### T007 [P] [US10] [FR-035][FR-036][FR-037][FR-038] Agent 系统 — orchestrator/agents/

**实现内容**：
- `agents/registry.py` — `AgentRegistry`：扫描 ESSKILLAGENT 目录，加载 14 个 agent 的 `agent.md` + `source_files` + Knowledge Base 路径
- `agents/session.py` — `SessionManager`：session 创建 + 续接 + 自动 expire
- `agents/adapter.py` — `AgentAdapter`：Claude SDK 调用，失败降级 CLI

**关键决策**：
- 渐进式知识加载：`source_files` 只放核心指令，Knowledge Base 路径自动注入（修复 pitfall #19）
- Knowledge Base 注入使用绝对路径 + IMPORTANT 提示（修复 pitfall #21）
- v1 agent 目录结构不变，v2 只改加载方式

**验收**：
- 14 个 agent 全部加载成功
- Knowledge Base 路径注入正确
- SDK 调用失败时降级到 CLI
- session 续接工作正常

**TDD**：
```
RED:  test_registry.py — test_load_all_agents, test_knowledge_base_injection,
      test_malformed_agent_skip, test_sdk_fallback_cli
GREEN: registry.py + session.py + adapter.py
```

**预估行数**：registry.py ~150 行, session.py ~80 行, adapter.py ~150 行

---

## Phase 3: Composition — TDD Runner + Review Pipeline

> 组合 Phase 2 的策略组件，实现核心业务逻辑。

### T008 [US1][US5] [FR-016][FR-017][FR-018][FR-019][FR-020] TDD 运行器 — orchestrator/tdd/runner.py

**实现内容**：
- `TaskRunner` 类：
  - `run_serial(task)` — 单任务 RED → GREEN
  - `run_parallel_group(tasks)` — Phase A (RED): agents 并行 → batch commit+CI; Phase B (GREEN): agents 并行 → batch commit+CI + retry
  - `_batch_commit(tasks, cwd)` — `git add` 限定项目源码目录，排除 `.workflow/`（修复 pitfall #7）
  - 接收 `CheckStrategy` 和 `SessionManager` 通过构造注入

**关键决策**：
- Phase A/B 都是 batch 模式（修复 pitfall #7）
- `asyncio.gather` 并行 agent 调用 → 结果收集 → 顺序写 store
- GREEN retry 循环：最多 `max_green_retries` 次，每次 per-job 错误反馈
- `git add` 范围限制：只 add 项目源码文件，排除 `.workflow/`

**验收**：
- 串行 RED→GREEN 完整执行
- 并行 Phase A batch commit
- 并行 Phase B batch commit + retry
- git add 不包含 .workflow/
- gather 后顺序写 store

**TDD**：
```
RED:  test_tdd_runner.py — test_serial_red_green, test_parallel_batch_commit,
      test_green_retry_loop, test_git_scope_exclusion
GREEN: runner.py
```

**预估行数**：~350 行

---

### T009 [US1][US8] [FR-032][FR-033][FR-034] 审查流水线 — orchestrator/review/pipeline.py

**实现内容**：
- `ReviewPipeline`：
  - `run_review(stage, artifacts)` — `asyncio.gather` 并行运行 code + security + brooks 三路审查
  - `_auto_fix_cycle(failures)` — fixer agent 修复 → re-review → 最多 `max_fix_retries` 次
  - `_detect_feature_gap(review_results)` — 检测 "missing" / "unimplemented" 关键词 → 动态创建补充 task
- `AutoFixer`：封装 fixer agent 调用 + re-review 触发

**关键决策**：
- feature-gap 创建的补充 task 遵循相同 tasks.md 格式，回注到 TDD runner
- 三路审查结果合并：任一 fail → 触发 auto-fix
- auto-fix 后 re-review 只跑失败的 reviewer（不重复运行已 pass 的）

**验收**：
- 三路并行审查执行
- auto-fix 循环正确触发和终止
- feature-gap 检测创建补充 task
- 达到 max_fix_retries 后停止

**TDD**：
```
RED:  test_review.py — test_parallel_review, test_auto_fix_cycle, test_feature_gap_detection,
      test_max_retries_stop
GREEN: pipeline.py
```

**预估行数**：~300 行

---

## Phase 4: Stages — 四阶段实现

> 四个阶段共用 base.py 的 review + gate + checkpoint 逻辑。

### T010 [US1] [FR-015] Stage 基类 — orchestrator/stages/base.py

**实现内容**：
- `Stage` ABC：
  - `run(engine_ctx)` — 模板方法：execute_steps → review → gate → checkpoint
  - `_run_review(artifacts)` — 调用 ReviewPipeline
  - `_check_gate(review_result)` — 判定是否放行
  - `_save_checkpoint(git_sha)` — 持久化检查点

**关键决策**：
- Template Method 模式：子类只实现 `_execute_steps`，共享 review/gate/checkpoint
- engine_ctx 包含 store, config, agents, checker 等所有依赖

**验收**：
- 模板方法流程正确
- review + gate + checkpoint 共享逻辑可复用

**TDD**：
```
RED:  test_stage_base.py — test_template_flow, test_gate_pass, test_gate_fail
GREEN: base.py
```

**预估行数**：~120 行

---

### T011 [P] [US1] [FR-011] Spec 阶段 — orchestrator/stages/spec.py

**实现内容**：
- `SpecStage(Stage)` — `_execute_steps`: constitution → specify → clarify → review
- 每个子步骤调用对应 agent（constitution-writer, spec-writer, clarifier）
- 无 `_is_small_project` 自动跳过逻辑（修复 pitfall #11, #20）

**验收**：4 个子步骤顺序执行，阶段审查完成后保存检查点

**预估行数**：~100 行

---

### T012 [P] [US1] [FR-012] Plan 阶段 — orchestrator/stages/plan.py

**实现内容**：
- `PlanStage(Stage)` — `_execute_steps`: plan → research → tasks → review
- tasks 子步骤后自动调用 `parser.parse_tasks` 解析并写入 store

**验收**：4 个子步骤顺序执行，tasks 写入 store

**预估行数**：~100 行

---

### T013 [P] [US1] [FR-013] Implement 阶段 — orchestrator/stages/implement.py

**实现内容**：
- `ImplementStage(Stage)` — `_execute_steps`:
  1. 从 store 读取 tasks
  2. 调用 `TaskRunner` 执行（串行/并行）
  3. 调用 ReviewPipeline 审查
  4. 如有 feature-gap → 创建补充 task → 重跑 TDD
  5. push + CI 最终验证

**验收**：TDD 循环 + 审查 + feature-gap 处理

**预估行数**：~150 行

---

### T014 [P] [US1] [FR-014] Acceptance 阶段 — orchestrator/stages/acceptance.py

**实现内容**：
- `AcceptanceStage(Stage)` — `_execute_steps`:
  1. 运行 acceptor agent
  2. 生成 traceability matrix (FR → Task → Test) 到 `specs/checklists/traceability.md`
  3. 最终 review gate

**验收**：traceability matrix 生成且格式正确

**预估行数**：~120 行

---

## Phase 5: Orchestration — Engine + CLI

### T015 [US1][US2] [FR-005][FR-006][FR-007][FR-008][FR-009][FR-010] 引擎 — orchestrator/engine.py

**实现内容**：
- `Engine` 类（< 300 行）：
  - `__init__` — 创建 `asyncio.Lock`，初始化 store, config, agents, checker, stages
  - `run()` — 顺序执行 spec → plan → implement → acceptance（跳过 `skip_stages` 中的阶段）
  - `resume()` — 从 store 读取最后检查点 → 定位下一个待执行阶段/步骤 → 继续
  - `retry(task_id)` — 从 store 读取指定 task → 重跑 TDD 循环
  - 将 `asyncio.Lock` 注入到 stages, runner, review 等组件

**关键决策**：
- engine.py **只做**阶段流转控制，不含任何具体阶段逻辑
- `asyncio.Lock` 所有权在 engine，store 无锁
- 阶段跳过仅由 `config.skip_stages` 显式配置

**验收**：
- engine.py < 300 行
- 四阶段顺序执行
- resume 从正确检查点继续
- retry 单任务重跑

**TDD**：
```
RED:  test_engine.py — test_full_pipeline, test_resume_from_checkpoint, test_retry_task,
      test_skip_stages
GREEN: engine.py
```

**预估行数**：~250 行

---

### T016 [US1][US2][US6][US7] [FR-048][FR-049][FR-050][FR-051] CLI 入口 — orchestrator/cli.py

**实现内容**：
- `argparse` 子命令: `run`, `resume`, `retry`, `status`
- `run` — 参数: project_path, --req-file / --req
- `resume` — 参数: project_path
- `retry` — 参数: project_path, task_id
- `status` — 参数: project_path
- `asyncio.run(engine.run())` 启动

**验收**：4 个子命令全部可用

**预估行数**：~120 行

---

## Phase 6: Optional — UI + Contract Tests

### T017 [US9] [FR-044][FR-045][FR-046][FR-047] Wave 面板 — orchestrator/ui/

**实现内容**：
- `ui/wave.py` — Wave overview + stage detail 面板（合并）
- `ui/notifier.py` — 桌面通知
- 核心模块不 import ui，ui 通过事件/回调机制接收数据

**验收**：
- `ui/` 包独立可移除
- 核心模块无 ui import
- 面板显示阶段进度

**预估行数**：wave.py ~300 行, notifier.py ~60 行

---

## Contract Tests（跨 Phase）

### TC001 [US1][US5] [FR-024] parser ↔ generator 格式契约 — tests/contract/test_task_format.py

**实现内容**：
- 用 task-generator agent 的真实输出样例验证 parser 正确解析
- 样例存放在 `tests/fixtures/tasks_valid.md` 和 `tests/fixtures/tasks_invalid.md`

**验收**：CI 每次运行都验证格式对齐

---

## Integration Tests

### TI001 [US2] [FR-009][FR-010] Resume 集成测试 — tests/integration/test_resume.py

**实现内容**：
- 用 `tests/fixtures/workflow.db`（v1 快照）测试从 v1 DB 恢复

### TI002 [US1] TDD Runner 集成测试 — tests/integration/test_tdd_runner.py

**实现内容**：
- mock agent 调用，验证串行 + 并行 TDD 完整流程

### TI003 [US1] Review 集成测试 — tests/integration/test_review.py

**实现内容**：
- mock agent 调用，验证三路审查 + auto-fix 循环

---

## Dependency Graph

```
Phase 1 (Foundation)
  T001 config.py ─────────────┐
  T002 store/ ─────────────┐  │
  T003 defaults.yaml ──────┤  │
                            ▼  ▼
Phase 2 (Core)          ┌─ T004 checks/local  ─┐
  (all parallel)        ├─ T005 checks/ci     ─┤
                        ├─ T006 tdd/parser    ─┤
                        └─ T007 agents/       ─┤
                                                ▼
Phase 3 (Composition)  ┌─ T008 tdd/runner ─────┐
                       └─ T009 review/pipeline ─┤
                                                ▼
Phase 4 (Stages)       ┌─ T010 stages/base ────┐
  (T010 first,         ├─ T011 stages/spec   ──┤
   then T011-14        ├─ T012 stages/plan   ──┤
   parallel)           ├─ T013 stages/implement┤
                       └─ T014 stages/acceptance┤
                                                ▼
Phase 5 (Orchestration)┌─ T015 engine.py ──────┐
                       └─ T016 cli.py ─────────┤
                                                ▼
Phase 6 (Optional)      T017 ui/ (independent)
```

---

## Risk Register

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | engine.py 超 300 行 | 中 | 高 | Stage 基类承担 review/gate/checkpoint，engine 只做流转 |
| R2 | v1 DB 兼容性破坏 | 低 | 高 | fixtures/workflow.db 集成测试 + 不修改 v1 表 |
| R3 | 并行 TDD git 冲突 | 中 | 高 | validator 预检 + batch commit + git add 范围限制 |
| R4 | parser-generator 格式漂移 | 中 | 中 | 契约测试 + CI 每次运行验证 |
| R5 | CI 日志截断导致 retry 无效 | 低 | 中 | per-job 结构化提取 + 2000 字符预算 |
| R6 | Agent SDK 接口变更 | 低 | 中 | adapter 层隔离 + CLI 降级 |

---

## Module Line Budget

| 模块 | 预算 | 约束来源 |
|------|------|----------|
| engine.py | < 300 | NFR-002 |
| config.py | < 150 | 单一职责 |
| stages/base.py | < 150 | 共享逻辑 |
| stages/spec.py | < 120 | 单阶段 |
| stages/plan.py | < 120 | 单阶段 |
| stages/implement.py | < 180 | 最复杂阶段 |
| stages/acceptance.py | < 150 | 单阶段 |
| tdd/runner.py | < 350 | 串行+并行+retry |
| tdd/parser.py | < 200 | 95% 覆盖率要求 |
| tdd/validator.py | < 120 | 冲突检测 |
| checks/base.py | < 50 | 接口 |
| checks/common.py | < 100 | stack detection |
| checks/local.py | < 150 | 本地执行 |
| checks/ci.py | < 350 | CI 全流程 |
| review/pipeline.py | < 350 | 三路审查+auto-fix |
| agents/registry.py | < 180 | 14 agent 加载 |
| agents/session.py | < 100 | session 管理 |
| agents/adapter.py | < 180 | SDK+CLI 适配 |
| store/models.py | < 150 | 数据定义 |
| store/db.py | < 150 | 连接+migration |
| store/queries.py | < 300 | CRUD |
| cli.py | < 150 | 参数解析 |
| ui/wave.py | < 350 | 面板 |
| ui/notifier.py | < 80 | 通知 |
| **TOTAL** | **~3500** | v1 was 6674 |

---

## Task Summary Table

| Task | Phase | Parallel | Files | FR | US | Priority |
|------|-------|----------|-------|----|----|----------|
| T001 | 1 | - | config.py, defaults.yaml | FR-001~004 | US4 | P1 |
| T002 | 1 | - | store/models,db,queries | FR-039~043 | US2,4 | P1 |
| T003 | 1 | - | defaults.yaml | - | US4 | P1 |
| T004 | 2 | [P] | checks/base,common,local | FR-026~027,029~030 | US3 | P1 |
| T005 | 2 | [P] | checks/ci | FR-028~031 | US3 | P1 |
| T006 | 2 | [P] | tdd/parser,validator | FR-021~025 | US1,5 | P1 |
| T007 | 2 | [P] | agents/registry,session,adapter | FR-035~038 | US10 | P1 |
| T008 | 3 | - | tdd/runner | FR-016~020 | US1,5 | P1 |
| T009 | 3 | - | review/pipeline | FR-032~034 | US1,8 | P1 |
| T010 | 4 | - | stages/base | FR-015 | US1 | P1 |
| T011 | 4 | [P] | stages/spec | FR-011 | US1 | P1 |
| T012 | 4 | [P] | stages/plan | FR-012 | US1 | P1 |
| T013 | 4 | [P] | stages/implement | FR-013 | US1 | P1 |
| T014 | 4 | [P] | stages/acceptance | FR-014 | US1 | P1 |
| T015 | 5 | - | engine.py | FR-005~010 | US1,2 | P1 |
| T016 | 5 | - | cli.py | FR-048~051 | US1,2,6,7 | P1 |
| T017 | 6 | - | ui/wave,notifier | FR-044~047 | US9 | P3 |

---

## Pitfall Mitigation Cross-Reference

| Pitfall | Task | 具体措施 |
|---------|------|----------|
| #1 CHECKERS dict mutation | T004, T005 | CheckStrategy ABC + 构造注入 |
| #2 engine.py 上帝类 | T015 | < 300 行 + stages/ 子包 |
| #3 parser-generator 不对齐 | T006, TC001 | 强制 em dash + 契约测试 |
| #4 CI 日志截断 | T005 | per-job 2000 字符预算 |
| #5 CI 不区分 task 范围 | T005 | stack scoping 内建 |
| #7 并行 git 冲突 | T008 | batch commit + git add 范围限制 |
| #8 任务排序错乱 | T006 | 数字排序 + setup/US*/polish 分组 |
| #9 file_path 不更新 | T002 | INSERT OR REPLACE |
| #10 push 无重试 | T005 | 3 次重试 + 5 秒间隔 |
| #11, #20 _is_small_project | T011 | 删除，完整流水线 |
| #12 TS Check 误判 | T005 | RED 对 frontend 只看 Test job |
| #13 子串匹配 job 名 | T005 | startswith(prefix) |
| #14 skipped 当通过 | T005 | GREEN: skipped = failure |
| #15 tests/ 误归 frontend | T004 | 扩展名 + 路径前缀双重判断 |
| #16 polish 归入 setup | T006 | setup/US*/polish 三类分组 |
| #17 retry 不相关 stack | T005 | stack scoping 过滤 |
| #18 TimeoutExpired 未捕获 | T005, T007 | 统一 (FileNotFoundError, TimeoutExpired) |
| #19 知识文件预加载 | T007 | 渐进式加载 + KB 路径注入 |
| #21 agent 文件名映射 | T007 | 绝对路径 + IMPORTANT 提示 |
