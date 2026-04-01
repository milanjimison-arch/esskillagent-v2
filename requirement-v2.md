# E+S Orchestrator v2 — 完成需求（Phase 2）

## 背景

Phase 1 由 v1 编排器自动构建，生成了 v2 的骨架代码：
- **已完成**：config.py、store/（db+models+queries+schema+lvl）、checks/（base+local+ci）、agents/（registry+adapter）、review/pipeline.py、stages/base.py、tdd/（parser+validator）、ui/wave.py、cli.py、engine.py（96 行调度器）、契约测试
- **桩代码**：stages/plan.py（37 行空壳）、stages/implement.py（37 行空壳）、tdd/runner.py（155 行骨架，无实际执行逻辑）
- **缺失**：集成测试、conftest.py、fixtures、checks/common.py、agents/session.py、launch.py

Phase 1 运行中发现 23 条运行时问题（runtime-issues.md R01-R23）和两轮对抗审核发现的架构问题（N01-N07、C-1/C-2/C-3、H-1~H-7），已在 v1 代码中修复但 v2 骨架需要吸收这些经验。

## 目标

将 v2 从"精心测试的骨架"变为一个**有自有逻辑的编排器**，而非按顺序跑 agent 的脚本。

### 什么是"自有逻辑"

编排器必须具备四个维度的自主能力：

1. **感知**：不仅感知 agent 输出和 CI 结果，还能感知全局健康状态（BLOCKED 比例、资源消耗趋势、产物一致性）
2. **决策**：在关键分叉点做出有逻辑的选择（触发 clarify？并行还是串行？继续重试还是提前终止？回退到上一阶段？），而非机械执行固定流程
3. **反馈闭环**：每个决策的结果必须能影响后续决策（修复收敛性、stale 级联、feature-gap 补充 task）
4. **自我修正**：当整体方向走偏时（如 50% task BLOCKED），编排器应能识别并建议调整策略，而非在错误路径上耗尽重试

具体的实现方式（规则引擎、启发式扫描、阈值判断等）由 agent 在编码时自行设计，不做硬性规定。以上四个维度是**设计目标**，不是实现规范。

### PipelineMonitor — 全局观察能力

编排器需要一个监控模块（代码模块而非 LLM agent），负责：
- 在阶段转换和 task 批次完成时聚合全局信号
- 检测局部观察者无法发现的全局异常（如 BLOCKED 比例过高、资源消耗超预算、stale 级联过深）
- 产生可操作的建议（回退、降级、终止），写入 LVL 事件流

具体的检测规则、阈值、触发时机由 agent 参考 `runtime-issues.md` 和 `pitfalls.md` 中的经验自行设计。

### BLOCKED 不是死胡同

当 task 或阶段被标记为 BLOCKED 时，编排器必须有后续处理逻辑，不能让 BLOCKED 成为永久停滞状态。可能的处理策略包括但不限于：
- 单 task BLOCKED → 跳过，继续其他 task，最终汇总报告
- 多 task BLOCKED（比例过高）→ 暂停执行，建议回退到更早的阶段
- 阶段 BLOCKED → 请求人工干预或自动降级处理

具体阈值和策略由 agent 根据实际场景设计。

### LVL 是决策依据，不只是审计日志

LVL 事件流的设计目标是支撑编排器的自主决策，而非仅用于事后审计。编排器应在以下场景主动查询 LVL：
- 阶段启动前验证前置条件
- 修复循环中判断收敛性
- resume 时确定恢复点
- 全局监控时聚合历史模式

具体的查询方式和决策逻辑由 agent 结合 LVL 数据模型自行设计。

## 重要原则

### 禁止直接复制 v1 代码

v1 代码（`F:\claude\技能备份\E+S\`）仅作为**设计决策参考**。v2 的实现必须：
- 基于 v2 已有的架构（CheckStrategy 接口、Stage ABC、frozen dataclass 等）重新编写
- 不得将 v1 的函数/方法直接复制粘贴到 v2 中
- 可参考 v1 的逻辑流程和经验教训，但必须用 v2 的模式重新表达
- v1 的 1249 行 engine.py、500+ 行 task_runner.py 的"上帝类"模式是反面教材，v2 必须保持模块化

### clarify 和 research — 智能条件触发

v1 中这两步从未被启用过（条件触发标记 `[NEEDS CLARIFICATION]` 无 agent 输出）。v2 保留为可选步骤，但用**双向触发机制**确保有需要时能真正启用：

**触发机制（二选一触发即执行）**：
1. **Agent 自报**：spec-writer / planner 的 prompt 中引导输出 `[NC: 具体问题]` 标记（需 A9/A10 适配）
2. **编排器检测**：对 agent 输出做启发式扫描 — 检测到以下模式时自动触发：
   - 含 `?` 的句子超过 3 个（大量疑问 = 需要澄清）
   - 含 "TBD"/"TODO"/"待定"/"未确定" 关键词
   - 含 "可能"/"或许"/"建议进一步" 等不确定表达超过 2 处
   - research 额外检测：含 "新技术"/"未使用过"/"需要评估" 等技术风险词

**工具配置**：
- clarify agent 配备 WebSearch + WebFetch（可搜索外部文档澄清歧义）
- research agent 配备 WebSearch + WebFetch + Bash（可搜索、获取页面、执行验证命令）

**成本控制**：只在检测到触发条件时执行，正常需求不触发则跳过（保持 v1 的高效路径）

## 前代参考

| 资源 | 位置 | 用途 |
|------|------|------|
| v1 编排器 | `F:\claude\技能备份\E+S\` | 实现模式参考（不直接复制） |
| v1 踩坑记录 | `pitfalls.md`（26 条） | 避免重复犯错 |
| v2 运行时问题 | `runtime-issues.md`（R01-R23） | 设计约束 |
| Agent 知识文件 | `agents-src/`（14 个 agent 目录） | 适应性修改的源文件 |
| Python 编码模式 | `reference/python-patterns.md` | 编码规范 |
| Python 测试规范 | `reference/python-testing.md` | 测试规范 |

---

## 执行顺序

```
Wave 0（前置）:  P0（基础设施补全）+ P11-P14（LVL/证据链体系）
Wave 1（并行）:  P4, P15, C1, C2, C3, A6-A10（仅未完成的 agent 修改）
Wave 2（并行）:  P1, P5, P10（spec.py 填充）, P9
Wave 3:          P3（依赖 P4, C1, P11-P12）
Wave 4:          P2（依赖 P3, P0-D）
Wave 5（并行）:  P7, P8
Wave 6:          P6（集成测试，依赖全部完成）

注意：
- A2/A3/A4/A5 已在 Phase 1 中完成（agent.md 已包含适配段落），无需重做
- P11-P14（LVL 体系）在 Wave 0 因为 P3/P2 的 TDD 和审查逻辑依赖 LVL 事件写入
- P3 依赖 P11（lvl.py）+ P12（artifacts.py）用于 RED/GREEN 事件记录和产物冻结
```

---

## 第一部分：代码补全任务

### P0. 基础设施补全（前置任务）

**目标**：填补 Phase 1 遗留的基础设施缺口，解除后续任务的阻塞。

**P0-A. agents/adapter.py — 扩展 SessionManager**

SessionManager 已存在于 `adapter.py`（262-299 行），实现了 get/save/clear_session + send_with_session。需要扩展而非新建：
1. 补充 `expire_session(session_id)` — 过期清理（超时或显式释放）
2. 补充 `list_sessions()` — 用于 status 命令显示活跃 session
3. 确保 session 续接在 RED/GREEN/review 三个场景中正确工作
4. 如果 adapter.py 超出行数约束，可将 SessionManager 提取到独立的 `agents/session.py`

约束：adapter.py 总行数 < 400 行；如提取则 session.py < 120 行。

**P0-B. 架构基础演进**

**B1. EngineContext frozen dataclass**（新建 `orchestrator/context.py`）

解决依赖注入参数膨胀问题（v1 的 ReviewPipeline 构造函数有 13 个参数）：
```python
@dataclass(frozen=True)
class EngineContext:
    store: Store
    cwd: str
    config: dict
    session_manager: SessionManager
    check_strategy: CheckStrategy
    notifier: Notifier | None
    store_lock: asyncio.Lock
```
所有 stage、runner、pipeline 通过单个 `ctx: EngineContext` 接收依赖。约束：< 50 行。

**B2. CheckStrategy 异步化**

当前 CheckStrategy 接口是同步的（`-> bool`），但 CI 策略需要 commit→push→等待→解析（异步副作用链）。修改：
```python
class CheckStrategy(ABC):
    @abstractmethod
    async def tests_must_fail(self, task_id: str, file_path: str) -> CheckResult: ...
    @abstractmethod
    async def tests_must_pass(self, task_id: str, file_path: str) -> CheckResult: ...
```
返回 `CheckResult` dataclass（passed: bool, output: str, attempts: int）而非裸 bool。LocalCheckStrategy 内部用 `asyncio.to_thread` 包装同步 subprocess。约束：base.py < 80 行。

**B3. stages/base.py — 补充 `_run_agent()` 和 `_check_output()`**

当前 base.py 无这两个方法，但 P1/P8/P10 需要。添加：
1. `async _run_agent(agent_name, prompt, tools)` — 通过 ctx.session_manager 调用 agent 并记录 lvl
2. `_check_output(path)` — 检查产物文件是否存在且非空
3. StageABC 构造函数接收 `ctx: EngineContext`（替代零散参数）

约束：base.py 总行数 < 200 行。

**P0-C. checks/ci.py — 填充 CI 策略实现**

当前 75 行骨架，`tests_must_fail`/`tests_must_pass` 返回 False。填充：
1. `tests_must_fail()` — commit+push → CI 等待 → stack-scoped job 评估（RED）
2. `tests_must_pass()` — commit+push → CI 等待 → stack-scoped job 评估（GREEN）
3. `_commit_and_push()` — 复用 `stage_project_files()`，3 次重试
4. `_get_run_id_for_sha()` — SHA 精确匹配 CI run
5. `_get_failed_log()` — per-job 结构化日志提取，2000 字符预算
6. `detect_stack()` — rust/frontend/python 识别，CI job 映射可配置

约束：ci.py < 400 行（策略编排）。如超出可拆出 `checks/ci_helpers.py`（git 操作 + 日志解析，< 120 行），总包 < 520 行。参考 v1 `ci_checks.py` 的设计决策（非复制代码），用 v2 的 CheckStrategy 接口重新表达。

**P0-D. review/pipeline.py — 填充 reviewer 函数和 _apply_fix**

当前 reviewer 函数抛 NotImplementedError，`_apply_fix` 为空。填充：
1. `_run_code_review()` / `_run_security_review()` / `_run_brooks_review()` — 调用对应 agent
2. `_apply_fix()` — 调用 fixer agent，按 source 区分输入（R22/M04）
3. `_parse_verdict()` — 解析 Verdict + severity 计数，兼容加粗格式（R21）

约束：pipeline.py 总行数 < 350 行。

**P0-E. 14 个 agent 的注册配置**

当前 `agents-src/` 下只有 `.md` 文件，**无 agent.json**。registry.py 的 `_try_load_agent()` 依赖配置文件加载 agent。必须：
1. 确认 registry.py 的加载方式（agent.json 或 agent.md frontmatter）
2. 如果依赖 agent.json：**为每个 agent 创建 `agent.json`**，格式：`{"name": "...", "model": "...", "tools": [...], "knowledge_files": [...]}`
3. 如果从 agent.md frontmatter 解析：确认 14 个 agent.md 的 frontmatter 格式正确（name, description, tools, model）
4. 路径改为 `agents-src/` 相对路径（C3）
5. **验证**：编写测试确认 14 个 agent 全部加载成功

### P1. stages/plan.py — 填充业务逻辑

**当前**：37 行空壳，返回硬编码 StageResult。

**目标**：实现 plan → research(可选) → tasks → review 子流程。

**具体要求**：
1. `_execute_steps()` 调用 planner agent 生成 `specs/plan.md`
2. 智能触发 research：对 plan.md 做启发式扫描（`[NR:]` 标记 + "新技术"/"未使用过" 关键词），触发时调用 researcher agent 生成 `specs/research.md`
3. 调用 task-generator agent 生成 `specs/tasks.md`
4. 调用 `tdd/parser.py` 解析 tasks.md 并写入 store
5. 返回 artifacts dict 包含 plan/research/tasks 路径
6. 错误处理：agent 调用失败时记录 lvl 并抛异常（由 base.py 的重试逻辑处理）

**约束**：< 150 行，复用 base.py 的 `_run_agent()` 和 `_check_output()` 方法（P0-B 补充）。

### P2. stages/implement.py — 填充业务逻辑

**当前**：37 行空壳。

**目标**：实现 TDD 执行 → 审查 → 修复 → push+CI 完整流程。

**具体要求**：
1. 从 store 读取 pending tasks
2. 调用 `tdd/runner.py` 执行 RED→GREEN 循环
3. 调用 `review/pipeline.py` 执行三路并行审查
4. 审查未通过时进入自动修复循环（fixer agent → re-review，最多 max_fix_retries 次）
5. **修复收敛性检测**：每轮 fix 后统计 issue 数量，如果 >= 上一轮（修了 A 引入 B），提前终止标记 BLOCKED
6. Feature-gap 检测：审查发现 "missing/unimplemented" 时创建补充 task 并重跑 TDD
7. 最终 push+CI 验证
8. 跳过已完成的 task（R09）
9. **LVL 集成**：TDD 和审查的每个关键步骤写入 `lvl_events`，产物通过 `artifacts` 注册和冻结

**约束**：< 200 行，TDD 执行委托给 runner，审查委托给 pipeline，implement.py 只做编排。

### P3. tdd/runner.py — 填充执行逻辑

**当前**：155 行骨架，`git_add()` 为空，executor 未接入 agent adapter。

**目标**：实现完整的 RED→GREEN 循环，支持串行和并行。

**具体要求**：
1. **串行执行**：`run_serial(task, spec_content)` — RED agent 写测试 → CI 验证 RED → GREEN agent 写实现 → CI 验证 GREEN → 重试循环
2. **并行执行**：`run_parallel(tasks, spec_content)` — Phase A: N 个 RED agent 并行 → batch commit+CI → Phase B: N 个 GREEN agent 并行 → batch commit+CI → 重试
3. **RED prompt 约束**（R06）：使用 `_build_red_prompt()` 模板，明确"只写测试，禁止写实现"
4. **GREEN 重试**：环境问题（ModuleNotFoundError）给额外重试机会（R08/N05），prompt 中提示更新 requirements.txt
5. **batch GREEN 写 LVL**（R15）：为每个 task 写入 GREEN lvl 记录
6. **task 跳过**（R09）：已完成的 task 自动跳过
7. **git 操作**：复用 `stage_project_files()` 统一 git add（N07）

8. **并行文件不相交性运行时验证**：`run_parallel()` 启动前必须验证所有 task 的 file_path 集合两两不相交，不相交则降级串行
9. **修复收敛性检测**：每轮 fix 后统计 issue 数量，如果 >= 上一轮数量（修了 A 引入 B），提前终止并标记 BLOCKED（不浪费重试次数）

**约束**：< 450 行（含 50 行波动）。如超出可拆出 `tdd/prompts.py`（~50 行 prompt 模板）。超时用 `asyncio.to_thread` 包装 CI 检查（H-1/H-2）。

### P4. checks/common.py — 通用检查函数

**当前**：不存在。

**目标**：提供 file_exists、coverage_above、no_critical、parse_review_verdict 等通用检查。

**具体要求**：
1. `file_exists(path)` — 检查产物文件是否存在
2. `coverage_above(cwd, threshold)` — 解析覆盖率报告
3. `no_critical(output_path)` — 检查审查输出无 CRITICAL
4. `parse_review_verdict(output_path)` — 提取 Verdict + severity 计数，兼容 `**加粗**` 格式（R21）

**约束**：纯函数，无副作用，< 150 行。

### P5. engine.py — 补全 resume/retry/status

**当前**：96 行，只有 `run()` 方法。

**目标**：添加 `resume()`、`retry(task_id)`、`status()` 方法。

**具体要求**：
1. `resume()` — 从 store 读取最后的 checkpoint，恢复运行。Wave 面板回填（R18）
2. `retry(task_id)` — 重跑单个 task 的 RED→GREEN 循环。supersede 旧 LVL（R17）
3. `status()` — 返回当前进度（stages 完成情况 + task 完成率）
4. 进程锁管理 + `_release_lock()`（H-5）
5. implement 阶段用 `global_timeout` 而非 `stage_timeout`（R12）

**约束**：< 300 行。

### P6. 集成测试

**当前**：不存在。

**目标**：验证模块间真实交互。

**具体要求**：
1. `tests/integration/test_tdd_runner.py` — mock agent 调用，验证 RED→GREEN 串行/并行流程
2. `tests/integration/test_review.py` — mock agent 调用，验证三路审查 + 自动修复循环
3. `tests/integration/test_resume.py` — 用 fixtures/workflow.db 验证从 v1 DB 恢复
4. `tests/conftest.py` — 共享 fixtures（mock store、mock agent、temp project dir）
5. `tests/fixtures/` — workflow.db（v1 快照）、tasks_valid.md、tasks_invalid.md

### P7. launch.py — 启动脚本

**当前**：不存在。

**目标**：支持 Wave 面板启动。

**具体要求**：
1. 解析命令行参数（project_path, --req-file）
2. 初始化 WaveNotifier
3. 创建 Engine 实例并调用 `run()`
4. 错误处理 + 进程退出码

### P8. stages/acceptance.py — 填充业务逻辑

**当前**：142 行，有 traceability matrix 生成的骨架但 agent 调用未接入。

**目标**：实现 acceptor agent 调用 → traceability matrix 生成 → 最终审查。

**具体要求**：
1. 调用 acceptor agent 执行验收分析
2. 生成 FR→Task→Test 追溯矩阵到 `specs/checklists/traceability.md`
3. 最终 review gate
4. 返回验收结果

**约束**：< 200 行。

### P10. stages/spec.py — 填充业务逻辑

**当前**：25 行，有子步骤列表但 agent 调用未接入。

**目标**：实现 constitution → specify → clarify(智能触发) → review 子流程。

**具体要求**：
1. 调用 constitution-writer agent 生成 `specs/constitution.md`
2. 调用 spec-writer agent 生成 `specs/spec.md`
3. 智能触发 clarify：对 spec.md 做启发式扫描（疑问句数、TBD 关键词），触发时调用 clarifier agent
4. 最终 review gate
5. 所有项目无论大小都执行完整流程（不做 `_is_small_project` 判断，pitfall #20）

**约束**：< 150 行。

### P9. cli.py — 补全参数和子命令

**当前**：114 行，`run` 子命令只有 `--config`，缺少 `<project>` 位置参数和 `--req-file`。

**目标**：匹配验收标准的命令行格式。

**具体要求**：
1. `run <project_path> --req-file <path>` — 启动新流程
2. `resume <project_path>` — 从断点恢复
3. `retry <project_path> <task_id>` — 重跑单 task
4. `status <project_path>` — 查看进度
5. 添加 `__main__.py` 支持 `python -m orchestrator`

### P15. orchestrator/monitor.py — 管道健康监控

**目标**：实现编排器的全局观察能力，弥补局部观察者（CI 检查、审查 verdict、stale 检测）无法覆盖的全局盲区。

**设计方向**：
- 纯规则驱动（无 LLM 调用），在阶段转换和 task 批次完成时被 engine 调用
- 聚合 LVL 事件流中的历史模式，产生全局健康判断
- 输出为 `Observation`（维度 + 严重度 + 消息 + 建议），写入 lvl_events

**需要覆盖的盲区**（具体规则和阈值由 agent 自行设计）：
- BLOCKED 比例异常 → 是否应该回退到更早阶段？
- 资源消耗趋势 → 是否应该降级模型或调整并行策略？
- stale 级联深度 → 是否说明源头产物质量有问题？
- 修复循环的全局模式 → 同一类 issue 反复出现说明什么？

**约束**：< 200 行。参考 `runtime-issues.md` 和 `pitfalls.md` 中的经验作为规则设计的输入。

---

## 第二部分：Agent 适应性修改

Agent 知识文件已复制到 `agents-src/`。以下 agent 需要适应性修改以兼容 v2 架构。**修改在 `agents-src/` 副本上进行，不修改原始 `ESSKILLAGENT/` 目录。**

### A1. tdd-guide — RED prompt 适应

**文件**：`agents-src/tdd-guide/agent.md`

**修改**：
1. 在 `## Your Role` 后增加："当编排器传入 `## 阶段\nRED` 时，只执行 RED 阶段（只写测试），不要进入 GREEN 或 REFACTOR"
2. 在 `## TDD Workflow` 的 RED 步骤中强调："在编排器模式下，RED 阶段结束后**停止**，等待编排器的 GREEN 指令"
3. 增加依赖提示："引入新第三方依赖时必须同时更新 requirements.txt / Cargo.toml"

### A2. task-generator — CI 预估规则（[P] 策略已完成）

**文件**：`agents-src/task-generator/tasks-command.md`

**已完成**：`[P]` 标记策略已更新为"Default to [P] when files don't overlap"（第 101 行）。

**仍需修改**：
1. 增加 CI 预估规则："在 tasks.md 末尾增加 `## CI 预估` 段落，列出预计 CI 调用次数"
2. 强化 em dash 格式要求

### ~~A3/A4/A5~~ — 已在 Phase 1 完成

code-reviewer、brooks-reviewer、security-reviewer 的 agent.md **已包含**纯文本 severity 表格格式和 Verdict 行规则。无需重做。验证位置：
- code-reviewer: 第 223-233 行 "Severity 表格格式（强制）"
- brooks-reviewer: 第 192-224 行 "E+S Orchestrator Adaptation"
- security-reviewer: 第 124-151 行 "E+S 编排器适配"

### A6. fixer — 增加依赖感知

**文件**：`agents-src/fixer/agent.md`

**修改**：
1. 增加规则："修复时如果引入新第三方依赖，必须同时更新 requirements.txt"
2. 增加规则："不要修改 CI workflow 文件（.github/workflows/），如果问题在 CI 环境，报告给用户"
3. commit 消息约束："修复的 commit 消息不超过 72 字符，格式为 `fix(scope): description`"

### A7. implementer — GREEN prompt 适应

**文件**：`agents-src/implementer/green.md`（如果存在）或 `agent.md`

**修改**：
1. 增加规则："引入新第三方依赖时必须同时更新 requirements.txt / Cargo.toml"
2. 增加规则："不要修改测试文件，只写实现代码让已有测试通过"
3. GREEN 重试 prompt 增加失败分类信息（环境问题 vs 代码问题，R07/R08）

### A9. spec-writer — 触发标记引导

**文件**：`agents-src/spec-writer/specify-command.md`

**修改**：在输出规则中增加："如果需求中有不明确、歧义或需要外部信息的点，在 spec.md 中标注 `[NC: 具体问题描述]`。编排器会根据此标记决定是否启动 clarify 步骤。"

### A10. planner — 触发标记引导

**文件**：`agents-src/planner/` 下的命令文件

**修改**：在输出规则中增加："如果计划中涉及未验证的技术选型、新框架或需要调研的技术点，在 plan.md 中标注 `[NR: 具体研究主题]`。编排器会根据此标记决定是否启动 research 步骤。"

### A8. acceptor — 结构化输出

**文件**：`agents-src/acceptor/analyze-command.md`

**修改**：
1. 输出 Verdict 行格式与 A3-A5 统一：`Verdict: PASS` 或 `Verdict: FAIL`
2. severity 表格使用纯文本格式（不加粗）
3. 增加 FR 覆盖率表格输出要求

---

## 第三部分：配置与基础设施

### C1. defaults.yaml 更新

**修改**：
1. 增加 `idle_timeout: 600`（单次 agent 调用空闲超时）
2. 增加 `subprocess_timeout: 300`（本地测试命令超时，H1 修复）
3. 增加 `source_dirs: auto`（git add 目录策略：auto=自动扫描，或显式列表）
4. `global_timeout: 14400` 作为 implement 阶段的超时上限（R12），`stage_timeout: 3600` 用于 spec/plan/acceptance
5. 同步更新 config.py 的验证逻辑（`_POSITIVE_INT_KEYS` 等）

### C2. CI workflow 适配

**文件**：`.github/workflows/ci.yml`

**修改**：
1. `pip install` 步骤读取 `requirements.txt`（已有 `if [ -f requirements.txt ]` 条件）
2. 确保 Python 3.12 + pytest + pytest-cov + pytest-asyncio 安装
3. Coverage Check job 的 `--cov-fail-under=80`

### C3. agents-src 注册表映射

**文件**：`orchestrator/agents/registry.py`

**修改**：
1. Agent 目录路径从 `F:\claude\技能备份\ESSKILLAGENT\` 改为相对路径 `agents-src/`（v2 自包含）
2. 确保 14 个 agent 都能正确加载
3. Knowledge Base 路径注入使用绝对路径

---

## 第三点五部分：LVL/证据链体系（从第一性原理设计）

### 为什么需要重新设计

v2 当前的 LVL 实现只是一个日志表（`lvl_entries`），加上一个孤立的 `evidence` 表。两者职责重叠、都不完整：
- `lvl_entries` 没有 artifact_hash、depends_on，无法支撑 freeze/stale 检测
- `evidence` 有 stage 但没有因果链接，无法追溯事件因果关系
- 没有产物注册表，无法知道哪些文件是哪个阶段生成的、是否被修改过

### 设计原则

1. **单一事实源**：`lvl_events` 是所有"已发生事件"的唯一权威记录
2. **因果链接**：每条记录通过 `prior_event_id` 指向因果前驱，形成 DAG（非线性链）
3. **内容寻址**：产物用 `content_hash` 标识（SHA-256 前 16 位），同路径不同版本是不同产物
4. **冻结即承诺**：freeze 不可逆（除非显式 rollback），冻结后的 hash 成为下游输入约束
5. **级联失效可计算**：任何产物变更 → O(n) 时间计算所有失效的下游产物

### 两层模型（替代现有三张表）

**表 1: `artifacts` — 产物注册表**

```sql
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id   TEXT PRIMARY KEY,
    pipeline_id   TEXT NOT NULL,
    path          TEXT NOT NULL,            -- 相对路径 "specs/spec.md"
    stage         TEXT NOT NULL,            -- 产出阶段
    content_hash  TEXT NOT NULL,            -- SHA-256[:16]
    status        TEXT DEFAULT 'draft',     -- draft | frozen | stale | superseded
    depends_on    TEXT DEFAULT '[]',        -- JSON array of artifact_id
    frozen_at     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

**表 2: `lvl_events` — 统一事件流（合并 lvl + evidence）**

```sql
CREATE TABLE IF NOT EXISTS lvl_events (
    event_id        TEXT PRIMARY KEY,
    pipeline_id     TEXT NOT NULL,
    stage           TEXT NOT NULL,            -- spec | plan | implement | acceptance
    task_id         TEXT,                     -- 可选，implement 阶段关联
    event_type      TEXT NOT NULL,            -- 见枚举
    severity        TEXT DEFAULT 'INFO',      -- INFO | WARN | ERROR | FATAL
    message         TEXT NOT NULL,
    detail          TEXT,                     -- JSON blob
    artifact_id     TEXT,                     -- 关联产物
    artifact_hash   TEXT,                     -- 事件时的产物 hash 快照
    prior_event_id  TEXT,                     -- 因果前驱
    agent_id        TEXT,
    created_at      TEXT NOT NULL
);
```

**event_type 枚举**：

| 类别 | event_type | 含义 |
|------|-----------|------|
| 生命周期 | `stage_start` / `stage_complete` / `stage_fail` | 阶段级 |
| 产物 | `artifact_created` / `artifact_frozen` / `artifact_stale` / `artifact_superseded` | 产物状态变更 |
| TDD | `red_start` / `red_pass` / `red_fail` / `green_start` / `green_pass` / `green_fail` | RED/GREEN 循环 |
| 审查 | `review_start` / `review_pass` / `review_fail` / `fix_attempt` | 审查 + 修复 |
| CI | `ci_triggered` / `ci_pass` / `ci_fail` | CI 事件 |
| 控制 | `freeze` / `unfreeze` / `rollback` / `skip` | 流程控制 |

### 不变量规则

**INV-1 阶段完成条件**：阶段 S 完成 ⇔ 存在 `stage_complete` 事件 + 所有必需产物均 `frozen` + hash 一致

**INV-2 阶段启动前置**：阶段 S 可启动 ⇔ 所有前驱阶段已完成（INV-1）+ 前驱 frozen 产物未 stale

**INV-3 证据链完整性**：每个非 `stage_start` 事件的 `prior_event_id` 必须指向同 pipeline 中存在的事件

**INV-4 RED-GREEN 配对**：每个 task 必须先 `red_pass` → 再 `green_start`；`red_pass` 时的测试文件 hash 必须等于 `green_pass` 时的 hash（GREEN 未修改测试）

### freeze + stale 级联规则

```
freeze（阶段完成时）:
  foreach artifact A in stage:
    A.status = 'frozen', A.frozen_at = now()
    append_event(artifact_frozen, artifact_hash=A.content_hash)

stale 检测（下一阶段启动前）:
  foreach frozen artifact A:
    if current_hash(A.path) != A.content_hash:
      A.status = 'stale'
      cascade: BFS 遍历 depends_on → 所有下游标 stale
      最早 stale 阶段及后续需要重做

rollback（显式回退时）:
  foreach stage S' >= target_stage:
    unfreeze all artifacts in S'
```

### 实现任务

**P11. store/lvl.py — LVL 事件模块**（新建）

替代现有 `_lvl_queries.py`。提供：
1. `append_event()` — 追加不可变事件
2. `get_latest_event()` — 查询最新事件
3. `verify_chain()` — 验证 INV-3 证据链完整性
4. `verify_stage_invariant()` — 验证 INV-1 阶段完成条件
5. `list_events_for_stage()` — 列出阶段事件

约束：< 200 行。

**P12. store/artifacts.py — 产物管理模块**（新建）

提供：
1. `register_artifact()` — 注册新产物（draft 状态）
2. `freeze_artifact()` — 冻结产物
3. `check_staleness()` — 检测 stale 产物
4. `cascade_invalidate()` — BFS 级联失效
5. `unfreeze_stage_artifacts()` — 回退时解冻

约束：< 150 行。

**P13. store/models.py — 新增数据模型**

追加 `ArtifactRecord` 和 `LvlEventRecord` frozen dataclass。

**P14. store/_schema.py — Schema 升级**

追加 `artifacts` 和 `lvl_events` 表定义。`schema_version` 升至 3。保留旧表向后兼容。

### 产物依赖图（每个阶段的最小产物集）

```
spec:
  constitution.md → spec.md（depends_on: constitution.md）

plan:
  plan.md（depends_on: spec.md）→ research.md（可选）→ tasks.md（depends_on: plan.md）

implement:
  foreach task T:
    test_T.py（depends_on: tasks.md）→ impl_T.py（depends_on: test_T.py）
  code_review.txt + security.txt + brooks_review.txt

acceptance:
  traceability.md（depends_on: tasks.md + all impl files）
```

---

## 第四部分：运行时问题约束（从 runtime-issues.md 提取）

以下是 v2 必须从架构层面解决的问题，不是修补而是内建：

| ID | 约束 | 实现位置 |
|----|------|---------|
| R01 | 启动时检测 `.git` 存在，不存在报错 | engine.py `_preflight()` |
| R02 | git add 自动检测项目目录，不硬编码 | `stage_project_files()` |
| R03-R05 | stack 检测支持 python/rust/frontend，CI job 映射可配置 | checks/ci.py |
| R06 | RED prompt 明确"只写测试" | tdd/runner.py `_build_red_prompt()` |
| R07-R08 | 环境问题区分 + 额外重试 + prompt 提示 | tdd/runner.py |
| R09 | 已完成 task 跳过 | tdd/runner.py 入口检查 |
| R11 | RED/GREEN prompt 增加"更新 requirements.txt"提示 | tdd/runner.py |
| R12 | implement 用 `config.global_timeout`（14400s），其他阶段用 `config.stage_timeout`（3600s） | engine.py |
| R13 | tasks prompt 默认标 `[P]` | agents-src/task-generator |
| R15 | batch GREEN 写 LVL 记录 | tdd/runner.py |
| R16 | `force_complete_task()` 方法 | store/queries.py |
| R17 | `mark_task_running()` supersede 旧 LVL | store/queries.py |
| R18 | 续接运行回填 Wave 面板 | ui/wave.py + engine.py |
| R20 | commit 消息可配置，不硬编码 | checks/ci.py |
| R21 | severity 正则兼容加粗格式 | checks/common.py |
| R22 | fixer 按 source 区分输入（review 读文件，ci 读日志） | review/pipeline.py |
| R23 | auto_fix 后不检查旧审查文件 | review/pipeline.py |

**补充约束（从 pitfalls.md 提取，Phase 1 未覆盖）**：

| 踩坑 # | 约束 | 实现位置 |
|--------|------|---------|
| #8/#16 | 任务排序：数字排序 + setup/US*/polish 三类分组 | tdd/runner.py `_group_by_phase()` |
| #9 | DB import_tasks 用 `INSERT OR REPLACE`（非 IGNORE） | store/queries.py |
| #14 | GREEN 阶段 skipped/cancelled job 视为 failure | checks/ci.py `_evaluate_green()` |
| #18 | 所有 subprocess 调用统一捕获 `(FileNotFoundError, TimeoutExpired)` | 全局约束 |

**并发模型决策**：
- 协程级保护：`asyncio.Lock`（engine.py 创建，注入到 stages/runner/pipeline）
- 线程级保护：`threading.Lock` 内建于 store/db.py（防 `asyncio.to_thread` 回调的并发写入，C-3）
- 两层锁不冲突：asyncio.Lock 保护协程交错，threading.Lock 保护线程交错

## 第五部分：安全约束（从对抗审核提取）

| ID | 约束 | 实现位置 |
|----|------|---------|
| C-1 | LLM 生成的路径做白名单校验 | checks/common.py `sanitize_path()` |
| C-2 | Windows shell=True 用 `list2cmdline` 转字符串 | agents/adapter.py |
| C-3 | SQLite 写入用 `threading.Lock` 保护 | store/db.py |
| H-1/H-2 | CI 检查用 `asyncio.to_thread` 避免阻塞 | stages/implement.py |
| H-4 | 密钥检查在 stage_project_files 之后执行 | review/pipeline.py |
| M-8 | git 不可用时密钥检查返回 False（不跳过） | review/pipeline.py |

---

## 验收标准

### 功能验收
1. `python -m orchestrator run <project> --req-file <req.md>` 能执行完整四阶段流水线
2. `python -m orchestrator resume <project>` 能从断点恢复
3. `python -m orchestrator retry <project> <task_id>` 能重跑单 task
4. `python -m orchestrator status <project>` 能显示进度
5. 所有 14 个 agent 从 `agents-src/` 正确加载并可调用
6. CI 模式下 commit→push→CI 等待→结果解析 完整工作
7. 并行 TDD（[P] task）batch commit+CI 正确执行

### 质量验收
8. 所有 Python 模块 < 450 行（400 行软约束 + 50 行波动）
9. engine.py < 300 行
10. pytest 测试覆盖率 80%+
11. CI 全绿（GitHub Actions）
12. 无 CRITICAL 安全问题（对抗审核确认）
13. 从 v1 DB 可恢复运行（集成测试验证）
14. 契约测试验证 parser ↔ generator 格式一致

### 文档验收
15. CLAUDE.md 更新反映最终架构
16. runtime-issues.md 中所有 R01-R23 标注"已解决"或"v2 内建"
17. agents-src/ 中修改的 agent 有变更说明注释
