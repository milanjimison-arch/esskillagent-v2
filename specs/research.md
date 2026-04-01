# Phase 0 — 技术选型研究报告

> 生成时间: 2026-04-02
> 项目: ESSKILLAGENT-v2 (E+S Orchestrator v2)
> 研究范围: 项目中所有标记待定事项 + 8 项技术深度研究

---

## 1. 项目中标记的待定事项

经过全面搜索，项目中不存在显式的 `NEEDS CLARIFICATION`、`TBD`、`TODO`（除启发式扫描关键词列表中的引用）、`FIXME`、`HACK`、`待定`、`待研究`、`open question` 标记。specs/spec.md 的 Clarifications 部分已将所有歧义自主解决。specs/checklists/requirements.md 确认 "No [NEEDS CLARIFICATION] markers remain"。

但以下隐含的技术决策点尚未在现有代码或文档中明确落地：

### 1.1 TaskStatus 枚举缺少 DONE 和 BLOCKED 状态

- **来源**: `orchestrator/store/models.py:42-53` vs `specs/data-model.md:36-44`
- **原始标记**: data-model.md 定义了 DONE 和 BLOCKED 状态（标注 `# NEW`），但 models.py 代码中缺失
- **问题描述**: data-model.md 设计文档中 TaskStatus 包含 `DONE` 和 `BLOCKED` 两个状态（用于 implement 阶段的 task 生命周期），但现有 models.py 实现只有 PENDING/RUNNING/PASSED/FAILED/SKIPPED。这导致 task 级别的完成/阻塞状态无法表达，resume 和 retry 逻辑缺少基础。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 在 TaskStatus 中直接增加 DONE/BLOCKED | 简单直接，与 data-model.md 对齐 | 需要区分 task 状态和 pipeline/stage 状态 |
  | B: 创建独立的 TaskLifecycle 枚举 | 语义清晰，task 和 pipeline 状态分离 | 增加类型数量，查询逻辑复杂化 |
- **推荐**: 方案 A
- **理由**: data-model.md 已明确设计，DONE/BLOCKED 作为 TaskStatus 的扩展语义清晰。PASSED/FAILED 可保留用于 stage 级别状态，DONE/BLOCKED 用于 task 级别。这也是 requirement-v2.md 中 P2、P3、P5 任务的直接依赖。
- **架构影响**: 低。仅影响 models.py 枚举定义和 store 查询中的状态过滤逻辑。

### 1.2 Agent 数量不一致（13 vs 14）

- **来源**: `specs/spec.md:373`（13 agents）vs `requirement-v2.md:90`（14 个 agent 目录）vs `CLAUDE.md:11`（14 个 agent）
- **原始标记**: spec.md Clarifications 已将数量修正为 13，但 requirement-v2.md 和 CLAUDE.md 仍引用 14
- **问题描述**: spec.md 基于 agents-src 目录实际计数确认为 13 个 agent。requirement-v2.md 的 "14 个 agent 目录" 描述可能包含了某个已废弃或未使用的目录（或计数错误）。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 以 spec.md 的 13 为准 | 与实际目录结构一致 | 需要更新 CLAUDE.md 和 requirement-v2.md |
  | B: 验证 agents-src 并确认实际数量 | 最准确 | 需要额外验证步骤 |
- **推荐**: 方案 B（验证后以实际为准）
- **理由**: spec.md 已做过验证并确认 13。实现阶段应以 agents-src 目录的实际内容为权威来源。CLAUDE.md 中的 "14" 应在后续更新中修正。
- **架构影响**: 无。仅影响 registry.py 的 agent 列表和相关测试断言。

### 1.3 defaults.yaml 配置项不完整

- **来源**: `orchestrator/defaults.yaml` vs `requirement-v2.md:443-451`（C1 要求）
- **原始标记**: C1 任务要求增加 idle_timeout、subprocess_timeout、source_dirs、global_timeout
- **问题描述**: 当前 defaults.yaml 只有 12 个配置项，缺少 C1 要求的多个关键配置。特别是 `test_command: npm test` 作为全局默认不适用于 Python 项目，且缺少 implement 阶段所需的 `global_timeout`（R12 要求）。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 直接扩展 defaults.yaml | 简单，一次性解决 | 配置项增多可能导致维护负担 |
  | B: 分层配置（基础 + 扩展） | 清晰分组 | 增加加载复杂度 |
- **推荐**: 方案 A
- **理由**: YAML 配置天然支持扁平结构，项目级覆盖通过 `.orchestrator.yaml` 处理。R12 明确要求 implement 阶段用 global_timeout 而非 stage_timeout，必须在默认配置中体现。
- **架构影响**: 低。需同步更新 config.py 的验证逻辑（`_POSITIVE_INT_KEYS` 等）。

### 1.4 Schema 版本升级路径（v1 -> v3）

- **来源**: `orchestrator/store/db.py:31`（`_SCHEMA_VERSION = 2`）vs `requirement-v2.md:597-599`（P14 要求升至 3）
- **原始标记**: FR-058 和 spec.md 已澄清 v2 是内部中间版本
- **问题描述**: 当前代码 schema_version 为 2，P14 要求升至 3 并新增 artifacts 和 lvl_events 表。需要 migration 逻辑处理 v1(version 1) -> v2(version 3 schema) 的升级路径。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 直接 CREATE IF NOT EXISTS + 更新 version | 简单，不需要 migration 框架 | 无法处理已存在但结构不同的表 |
  | B: 显式 migration 函数（v1->v3, v2->v3） | 健壮，处理所有升级路径 | 增加代码量 |
- **推荐**: 方案 B
- **理由**: 需要支持从 v1 数据库恢复（FR-058 验收标准），必须处理 schema 版本 1 到 3 的升级。CREATE IF NOT EXISTS 可以处理新表，但需要 migration 函数检测版本并执行相应 DDL。
- **架构影响**: 中。影响 store/db.py 的 initialize() 方法和 _schema.py。需要新增 migration 测试。

### 1.5 SessionManager 缺少 expire 和 list 方法

- **来源**: `orchestrator/agents/adapter.py:262-299` vs `requirement-v2.md:122-128`（P0-A 要求）
- **原始标记**: P0-A 明确要求补充 expire_session 和 list_sessions
- **问题描述**: 当前 SessionManager 只有 get/save/clear/send_with_session 四个方法。缺少过期清理和会话列表功能，status 命令无法显示活跃 session。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 在现有 SessionManager 中添加 | 代码集中 | adapter.py 可能接近 400 行上限 |
  | B: 提取 SessionManager 到 agents/session.py | 职责分离 | 增加文件数 |
- **推荐**: 方案 A（当前 adapter.py 为 311 行，添加两个方法约 20 行，仍在 400 行内）
- **理由**: adapter.py 当前 311 行，添加 expire_session 和 list_sessions 不会超过 400 行限制。如果后续扩展导致超出，再提取。
- **架构影响**: 低。新增两个公共方法，不改变现有接口。

### 1.6 EngineContext 尚未实现

- **来源**: `requirement-v2.md:133-148`（P0-B1 要求）
- **原始标记**: P0-B1 明确要求新建 context.py
- **问题描述**: 当前 stage 构造函数直接接收零散参数。EngineContext frozen dataclass 是所有后续阶段实现的基础依赖（P1, P2, P3, P5, P8, P10 都通过 ctx 接收依赖）。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 独立 context.py（< 50 行） | 简洁，符合 requirement 要求 | 增加一个极小文件 |
  | B: 放入 engine.py | 减少文件数 | engine.py 已有 300 行限制 |
- **推荐**: 方案 A
- **理由**: requirement-v2.md P0-B1 明确指定 "新建 orchestrator/context.py"，约束 < 50 行。独立文件避免循环导入（stages 导入 context，engine 导入 stages）。
- **架构影响**: 中。所有 stage、runner、pipeline 的构造函数签名需要从零散参数改为单一 ctx 参数。

---

## 2. 技术选型深度研究

### 2.1 Claude Agent SDK vs CLI Fallback 最佳实践

- **背景**: 编排器需要调用 13 个 AI agent，Claude Agent SDK 是首选，CLI 是降级方案。当前 adapter.py 已实现双路适配。
- **当前方案**: SDKAdapter 和 CLIAdapter 通过 AgentAdapter ABC 统一接口，SessionManager 管理会话续接。工厂函数 `create_adapter` 根据配置选择。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 启动时选择，全程固定 | 简单，行为可预测 | SDK 中途失败无法降级 |
  | B: 每次调用尝试 SDK，失败降级 CLI | 最大可用性 | 每次调用增加延迟（失败路径），日志混乱 |
  | C: SDK 优先，失败后切换为 CLI 且不再尝试 SDK（熔断模式） | 平衡可用性和性能 | 需要熔断状态管理 |
- **推荐**: 方案 C（熔断模式）
- **理由**: SDK 不可用通常是持续性问题（未安装、API key 失效），不需要每次重试。首次失败后记录状态，后续直接走 CLI。当前代码的工厂模式可以扩展为熔断：SDKAdapter._query 捕获 ImportError 后设置类级标记。
- **架构影响**: 低。在 SDKAdapter 内部增加 `_sdk_available: bool` 类变量即可，不改变外部接口。

### 2.2 aiosqlite 在高并发场景下的性能限制

- **背景**: 项目使用 aiosqlite 作为 SQLite 的异步包装。implement 阶段的并行 TDD 可能产生多个并发写入请求。
- **当前方案**: aiosqlite 在内部使用一个独立线程运行 sqlite3 连接，所有操作通过队列序列化到该线程。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 保持 aiosqlite + 外部 asyncio.Lock | 简单，已在代码中实现 | aiosqlite 内部已序列化，外部锁是双重保护 |
  | B: 改用 sqlite3 + asyncio.to_thread | 减少依赖 | 需要手动管理线程安全 |
  | C: 保持 aiosqlite，移除外部 asyncio.Lock | 减少锁竞争 | 违反 requirement 的并发模型设计 |
- **推荐**: 方案 A（保持现状）
- **理由**:
  1. aiosqlite 的内部线程序列化 + WAL 模式已经足够处理项目的并发规模（单用户，5-50 tasks）。
  2. 外部 asyncio.Lock 的目的不仅是保护 SQLite 写入，还保护调用方的读-改-写原子性（如更新 task 状态前检查当前状态）。
  3. requirement-v2.md 明确指定了两层锁模型：asyncio.Lock（协程级）+ threading.Lock（线程级，内建于 store/db.py）。
  4. 性能瓶颈不在 SQLite 层面 -- 每个 TDD 循环的 agent 调用耗时远超 DB 操作（分钟级 vs 毫秒级）。
- **架构影响**: 无。保持现有设计。需要确保 store/db.py 按 requirement 增加 threading.Lock（当前代码中尚未实现 C-3 要求）。

### 2.3 asyncio.gather 错误处理策略

- **背景**: 并行 TDD（Phase A/B）和三路审查都使用 asyncio.gather 进行并发调用。
- **当前方案**: 尚未实现并行调用逻辑。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: `return_exceptions=True` + 后处理 | 所有任务都能完成，不因一个失败中断其他 | 需要在结果中区分异常和正常返回 |
  | B: `return_exceptions=False`（默认） | 快速失败 | 一个任务异常导致其他已完成的结果丢失 |
  | C: `asyncio.TaskGroup`（Python 3.11+） | 结构化并发，异常传播清晰 | 一个失败会取消所有其他任务 |
- **推荐**: 方案 A（`return_exceptions=True`）
- **理由**:
  1. **三路审查场景**: 即使一个 reviewer 失败，其他两个的结果仍然有价值。code-review 失败不应丢失 security-review 的发现。
  2. **并行 TDD 场景**: 一个 task 的 RED 失败不应阻止其他 task 完成 RED。所有结果收集后统一判断。
  3. **与 BLOCKED 逻辑配合**: 失败的 task 标记为 BLOCKED，成功的继续。如果用方案 B/C，一个失败会中断所有任务。
  4. **后处理模式**: 收集结果后遍历，isinstance(result, BaseException) 判断失败，为每个失败任务记录 LVL 事件。
- **架构影响**: 低。影响 tdd/runner.py 的 run_parallel 和 review/pipeline.py 的并行审查实现。

### 2.4 GitHub Actions API 轮询 vs Webhook 的选择

- **背景**: CI 模式下，编排器需要等待 GitHub Actions workflow run 完成后获取结果。
- **当前方案**: checks/ci.py 为骨架代码，尚未实现 CI 等待逻辑。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: gh CLI 轮询 (`gh run watch`) | 简单，无需 webhook 基础设施 | 轮询间隔影响延迟，gh CLI 本身有 watch 命令 |
  | B: GitHub Webhook + 本地 HTTP 服务器 | 实时通知，无延迟 | 需要公网可达的 HTTP 端点，开发者本地部署困难 |
  | C: gh CLI 轮询 (`gh run list` + `gh run view`) | 可控的轮询频率 | 需要自行实现轮询循环 |
- **推荐**: 方案 A（`gh run watch`）
- **理由**:
  1. 编排器定位为本地开发工具，不需要 webhook 基础设施。
  2. `gh run watch <run_id>` 是 GitHub CLI 内建命令，阻塞直到 run 完成，自带进度输出。
  3. v1 已验证此方案可行（requirement.md 和 pitfalls.md 中的 CI 检查都基于 gh CLI）。
  4. 配合 `asyncio.to_thread` 包装（H-1/H-2 要求），不阻塞事件循环。
  5. ci_timeout 配置提供超时保护。
- **架构影响**: 低。checks/ci.py 的实现直接使用 subprocess 调用 gh CLI。

### 2.5 Wave UI 集成方案（是否保留）

- **背景**: v1 有 Wave 面板（3 个模块 1100 行），v2 将其独立到 ui/ 包。Constitution III 要求 ui/ 不被核心模块 import。
- **当前方案**: ui/wave.py 已存在（独立模块），核心模块通过 Notifier 接口解耦。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 保留 Wave 面板，P7 优先级实现 | 保持可视化监控能力 | Wave 库可能有兼容性问题，增加依赖 |
  | B: 移除 Wave，改用终端 Rich 面板 | 更轻量，无额外依赖 | 功能不如 Web 面板丰富 |
  | C: 保留但标记为 P3 低优先级 | 不阻塞核心功能 | 可能长期不完善 |
- **推荐**: 方案 A（保留，但严格按 P7 优先级实现）
- **理由**:
  1. spec.md User Story 9 明确列为 P3，requirement-v2.md Wave 5 中安排了 P7。
  2. 当前架构已通过 Notifier 接口解耦，Wave 面板的存在不影响核心功能。
  3. R18 指出续接运行时面板需要回填状态 -- 这是 UX 改进而非核心功能。
  4. 实现成本可控（< 200 行），且对开发者体验有实际价值。
- **架构影响**: 无。ui/ 包已独立，通过 Notifier 接口与核心交互。

### 2.6 pytest asyncio 测试模式最佳实践

- **背景**: 项目大量使用 async/await，测试需要 pytest-asyncio 支持。
- **当前方案**: 未看到 pytest-asyncio 的 mode 配置。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: `asyncio_mode = "auto"` 在 pyproject.toml/pytest.ini | 自动检测 async test 函数 | 可能意外将非 async fixture 当作 async |
  | B: `asyncio_mode = "strict"` + 显式 `@pytest.mark.asyncio` | 明确标记，不会误判 | 每个 async test 都需要装饰器 |
  | C: `asyncio_mode = "auto"` + conftest.py 中 `pytest_plugins = ["anyio"]` | 支持多种异步框架 | 增加依赖 |
- **推荐**: 方案 A（auto 模式）
- **理由**:
  1. 项目纯 asyncio，不涉及 trio/anyio，auto 模式最简洁。
  2. 减少样板代码 -- 项目会有大量 async 测试（store、runner、pipeline 等），每个都加 `@pytest.mark.asyncio` 冗余。
  3. 在 pyproject.toml 中配置 `[tool.pytest.ini_options]` 下 `asyncio_mode = "auto"`。
  4. 需要注意：auto 模式下，所有 async def test_* 函数会自动被 pytest-asyncio 处理，确保 conftest.py 中的 async fixture 也正确被识别。
- **架构影响**: 低。仅影响 pytest 配置文件。

### 2.7 frozen dataclass vs NamedTuple vs attrs 的选型

- **背景**: Constitution VII 要求所有 DTO 使用 `@dataclass(frozen=True)`。需要评估此选择是否最优。
- **当前方案**: 所有 models.py 中的 DTO 已使用 `@dataclass(frozen=True)`。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: frozen dataclass（当前） | 标准库，无依赖；支持默认值和 field()；IDE 支持好 | 性能低于 NamedTuple（内存、创建速度）|
  | B: NamedTuple | 内存占用小，创建快，支持元组解包 | 不支持默认值（3.6.1+ 支持）；继承受限；不支持 `field(default_factory=...)` |
  | C: attrs（@frozen） | 功能最强（validators、converters）；性能介于 A/B | 外部依赖；团队需要学习 attrs API |
- **推荐**: 方案 A（保持 frozen dataclass）
- **理由**:
  1. **Constitution VII 已明确规定** `@dataclass(frozen=True)`，变更需要修改 constitution。
  2. 当前代码已全面采用，一致性比微优化更重要。
  3. 项目的 DTO 需要 `field(default_factory=dict/tuple)`，NamedTuple 无法支持。
  4. 性能不是瓶颈 -- DTO 创建量很小（pipeline 级别几十到几百个对象）。
  5. attrs 引入外部依赖且学习曲线不值得。
- **架构影响**: 无。保持现状。

### 2.8 14 Agent 会话管理与资源控制

- **背景**: 编排器管理 13 个 agent（spec-writer, planner, clarifier, researcher, task-generator, implementer, code-reviewer, security-reviewer, brooks-reviewer, fixer, acceptor, tdd-guide, constitution-writer），每个可能有持续的 session。
- **当前方案**: SessionManager 用 dict 存储 agent_key -> session_id 映射，无过期机制。
- **可选方案**:
  | 方案 | 优点 | 缺点 |
  |------|------|------|
  | A: 基于时间的 TTL 过期 | 自动清理过时 session | 可能过早释放有用的 session |
  | B: 基于阶段的显式清理 | 精确控制 -- 每个阶段结束时清理该阶段 agent 的 session | 需要维护 agent-to-stage 映射 |
  | C: LRU 缓存 + 最大 session 数量限制 | 自动管理，防止无限增长 | 可能驱逐正在使用的 session |
- **推荐**: 方案 B（基于阶段的显式清理）
- **理由**:
  1. 编排器的阶段结构天然提供了 session 生命周期边界：spec-writer 和 clarifier 的 session 在 spec 阶段结束后不再需要。
  2. implement 阶段的 session 比较特殊：implementer 和 fixer 的 session 可能跨多个 task 复用（提供上下文连续性），应在 implement 阶段结束时清理。
  3. 不需要复杂的 TTL 或 LRU 机制。P0-A 要求的 `expire_session` 可实现为按 key 清理，`list_sessions` 返回当前活跃 session 列表。
  4. 资源控制：单个 pipeline run 最多 13 个并发 session（实际更少，因为阶段串行），不会有内存压力。
- **架构影响**: 低。在 StageABC 的 execute_with_gate 方法末尾添加阶段相关 session 清理逻辑。需要在 agent registry 中维护 agent-to-stage 的映射关系。

---

## 3. 风险与约束

### 3.1 已识别风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| aiosqlite 单线程写入瓶颈 | 低 -- agent 调用是真正的瓶颈（分钟级） | WAL 模式 + 批量提交减少 fsync；监控 DB 操作耗时 |
| Claude SDK API 变更 | 中 -- 可能导致 agent 调用全部失败 | CLI fallback 始终可用；adapter 抽象隔离 SDK 细节；熔断模式自动降级 |
| 并行 TDD 的 batch CI 无法区分单 task 失败 | 高 -- 一个 task 失败导致整组重试 | R14 建议的 per-task pytest -k 过滤；短期接受 batch 级别判断 |
| GitHub Actions API 速率限制 | 中 -- 频繁 CI 触发可能被限流 | gh CLI 自带速率限制处理；CI 调用间隔可配置 |
| 13 个 agent 知识文件格式不统一 | 中 -- P0-E 注册配置可能遇到解析问题 | 实现前验证所有 agent.md frontmatter 或创建统一的 agent.json |
| SQLite 文件锁在 Windows 上的行为差异 | 低 -- 单用户场景不太可能冲突 | 进程锁（H-5）防止并发实例；WAL 模式改善并发读取 |
| asyncio.gather 中一个 agent 长时间无响应 | 中 -- 阻塞整个 gather | idle_timeout 配置（C1 要求 600s）；asyncio.wait_for 包装每个协程 |
| 大型项目 tasks.md 解析性能 | 低 -- 50 tasks 以内 | parser.py 是纯文本解析，不会有性能问题 |

### 3.2 硬约束

- **Python 3.12+**: 使用了 `type X = ...`（type alias syntax 3.12+）、`X | None` 语法（3.10+）。
- **engine.py < 300 行**: 严格限制，任何业务逻辑必须委托到 stages/。
- **所有模块 < 450 行**: 400 行软限 + 50 行波动。超出必须拆分。
- **frozen dataclass for all DTOs**: Constitution VII 非协商条款。
- **v1 DB 兼容性**: 不得修改 v1 已有的 8 个表结构，只能新增表。
- **无裸 except**: 必须指定异常类型。
- **核心模块不 import ui/**: Constitution III 要求。
- **Knowledge Base 使用绝对路径**: agent 知识文件注入必须用绝对路径。
- **asyncio.Lock 由 engine.py 拥有和注入**: store 本身无锁，调用方负责协调。

---

## 4. 研究结论摘要

1. **无显式待定标记**: 项目文档质量高，spec.md 已解决所有歧义。但代码实现与设计文档存在 6 处差距（TaskStatus 缺失状态、EngineContext 未实现、SessionManager 不完整、defaults.yaml 缺配置、schema 版本差异、agent 数量引用不一致），均有明确的实现路径。

2. **技术栈确认**: 维持现有选型（aiosqlite + frozen dataclass + asyncio + gh CLI 轮询 + Wave UI 可选）。无需更换任何核心技术。

3. **关键设计决策**:
   - asyncio.gather 使用 `return_exceptions=True` 模式处理并行任务
   - Claude SDK 采用熔断降级模式（首次失败后切换 CLI，不反复尝试）
   - Session 生命周期绑定到 pipeline 阶段（阶段结束时清理）
   - pytest-asyncio 使用 auto 模式简化测试编写

4. **最高优先级实施项**:
   - P0-B1 EngineContext（所有 stage 实现的前置依赖）
   - P0-B2 CheckStrategy 异步化（CI 策略实现的前置）
   - P14 Schema 升级到 v3（LVL 事件体系的前置）
   - TaskStatus 枚举补全 DONE/BLOCKED（implement/resume/retry 的前置）

5. **风险可控**: 最高风险项是"并行 batch CI 无法区分单 task 失败"，但这是已知的 v1 设计决策（documented tradeoff），短期可接受，长期可通过 pytest -k 过滤优化。
