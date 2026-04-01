# E+S Orchestrator v1 踩坑记录

本文档记录 v1 编排器开发和运行中发现的所有问题，供 v2 重构参考。

---

## 1. CHECKERS dict mutation 模式

**问题**：`ci_checks.py` 的 `activate()` 在运行时替换 `checks.CHECKERS` dict 中的函数引用，依赖 Python 模块缓存的 dict 引用共享。

**后果**：
- `ci_tests_must_fail` 和 `ci_tests_must_pass` 有各自独立的 job 检查逻辑，容易漂移
- 测试时必须保存/恢复全局状态
- IDE 无法静态分析实际调用的是哪个实现

**v2 方案**：`CheckStrategy` 抽象接口，构造时注入，编译期多态。

---

## 2. engine.py 上帝类

**问题**：engine.py 1249 行，包含配置加载、阶段流转、TDD 调度、文件查找、Git 操作、Gate 控制等多个关注点。

**后果**：
- 改一个阶段的逻辑需要在 1000+ 行文件中导航
- `_run_tdd_task` 搬到 `task_runner.py` 后，engine.py 仍有悬空引用（`_run_tdd_loop` 在 `_review_verify_fix` 中被调用）

**v2 方案**：engine.py < 300 行纯阶段流转 + stages/ 子包。

---

## 3. task_parser 与 task-generator 格式不对齐

**问题**：parser 期望 `Description — file_path` 格式（em dash 分隔），generator 实际输出 `...implement Foo in src/foo.ts, and...`（路径嵌入描述中间）。

**后果**：所有 task 的 `file_path` 解析为空，[P] 并行标记全部降级串行。

**修复**：
- parser 增加 "in src/..." 回退提取
- generator 的 tasks-command.md 强制 em dash 格式
- 但治本需要契约测试

**v2 方案**：强制 em dash 格式 + `tests/contract/test_task_format.py` 契约测试。

---

## 4. CI 错误日志截断（500 字符）

**问题**：`ci_tests_must_pass` 失败时只取 CI 日志末尾 500 字符传给 retry agent。

**后果**：多 job 失败时（TypeScript Check + Frontend Tests + Rust Tests），agent 每次只看到一个 job 的错误，修了一个又冒出另一个（打地鼠效应）。T001 三次 GREEN 重试全失败。

**修复**：改为按 job 结构化提取，2000 字符预算，按 job 分段。

**v2 方案**：`_get_failed_log` 按 job 分段 + 仅包含相关 stack 的 job。

---

## 5. CI 跑全部测试，不区分 task 范围

**问题**：GREEN 验证时 CI 运行 `npm test`（全部测试），包括其他 task 的 RED stub 测试。

**后果**：T001 自己的 108 个测试全过了，但 T011/T012 的 84 个 RED stub 失败导致 Frontend Tests job 失败 → T001 GREEN 被误判为失败。

**修复**：Stack scoping — 根据 task 的 file_path 判断 rust/frontend，只检查相关 job。

**v2 方案**：Stack scoping 内建于 `CICheckStrategy`，RED 和 GREEN 共用 `_evaluate_red` / `_evaluate_green`。

---

## 6. Clippy -D warnings 阻断 dead_code

**问题**：CI 的 Clippy 步骤用 `-D warnings` 把所有 warning 升级为 error，包括 `dead_code`。

**后果**：TDD 中先写函数后接线是正常的，但 Clippy 判定为"未使用代码" → 编译失败。T001 第三次 GREEN 因此失败。

**修复**：`cargo clippy -- -D warnings -A dead_code`。

**v2 方案**：CI workflow 模板中默认允许 dead_code。

---

## 7. 并行 TDD git 冲突

**问题**：`_run_parallel_group` Phase A 让多个 agent 并行写文件，然后逐个 `_commit_and_push`。但 `git add -u` 会把所有 agent 写的文件都 stage 进第一个 task 的 commit。

**后果**：T002 的 commit 包含了 T003 的文件，T003 "nothing to commit"。

**修复**：改为 batch commit — 所有并行 agent 完成后一次性 commit+push+CI。

**v2 方案**：Phase A 和 Phase B 都是 batch 模式，一次 commit 包含所有并行 task 的文件。

---

## 8. 任务执行顺序错乱

**问题**：`sorted(phases.items())` 按字母排序，`"US11"` 排在 `"US3"` 前面。

**后果**：T011（Phase 4）先于 T001（Phase 1）执行。

**修复**：`_phase_sort_key` 按数字排序 + setup 优先 + polish 最后。

**v2 方案**：`_group_by_phase` 区分 setup/US*/polish，数字排序。

---

## 9. DB 中 file_path 不更新

**问题**：`store.import_tasks()` 用 `INSERT OR IGNORE`，已存在的 task 不会更新 file_path。parser 修复后新提取的 file_path 无法写入 DB。

**后果**：恢复运行时 task 的 file_path 仍为空。

**修复**：新增 `store.refresh_task_metadata()` 在 import 后 UPDATE。

**v2 方案**：`import_tasks` 用 `INSERT OR REPLACE` 或分离的 `upsert_tasks`。

---

## 10. push 网络失败无重试

**问题**：`_git_push` 没有重试机制，网络波动直接导致 task 永久失败。

**后果**：T012 因一次 GitHub 连接超时被标记为 failed。

**修复**：`_git_push` 加 3 次重试 + 5 秒间隔。

**v2 方案**：所有网络操作（git push, gh CLI）统一重试策略。

---

## 11. `_is_small_project` 误判

**问题**：用 `len(self.requirement) < 200` 判断是否小项目。当 `--req-file` 传入文件路径但文件内容未正确展开时，短路径字符串被误判为"小项目"。

**后果**：14266 字符的需求文档被跳过 constitution 生成。

**修复**：
- 阈值从 200 提升到 500
- 增加路径检测（含 `/` 或 `\` 且无换行 → 不判定为小项目）
- 增加 `##` 标题计数作为结构化特征

**v2 方案**：`_is_small_project` 应该基于结构化特征（标题数、FR 数、US 数），而非原始字符长度。

---

## 12. TypeScript Check 失败误判为无效 RED

**问题**：`ci_tests_must_fail` 把 TypeScript Check 失败当作"类型错误 = 编译错误 = 无效 RED"。

**后果**：RED 阶段写的测试引用未实现的类型，TS 报错是正常的，但被拒绝。

**修复**：RED 阶段忽略 TS Check 结果，只看 Test job。Frontend task 的 TS 失败视为有效 RED。

**v2 方案**：Stack scoping 内建，RED 阶段对 frontend task 只看 Frontend Tests job。

---

## 13. `_get_failed_log` 子串匹配 job 名

**问题**：`if job_name in line` 用子串匹配，可能误匹配。

**后果**：理论上 "Rust Tests" 会匹配包含 "Rust Tests" 文本的其他 job 日志行。

**修复**：改为 `line.startswith(job_name + "\t")`。

**v2 方案**：用 `startswith(prefix)` 精确匹配。

---

## 14. skipped/cancelled job 被当作通过

**问题**：`_relevant_jobs_pass` 只检查 `conclusion == "failure"`，skipped/cancelled 不算失败。

**后果**：GREEN 阶段如果 test job 被跳过（没实际跑测试），会误判为通过。

**修复**：GREEN 阶段 skipped/cancelled = failure；RED 阶段 skipped = acceptable。

**v2 方案**：`_evaluate_green` 和 `_evaluate_red` 分别定义失败条件。

---

## 15. `tests/` 目录被归为 frontend

**问题**：`_detect_task_stack` 把 `tests/` 目录统一归为 frontend。

**后果**：Rust 集成测试 `tests/integration_test.rs` 会被误分类为 frontend，导致检查错误的 CI job。

**修复**：按文件扩展名区分：`.rs` → rust，其余 → frontend。

**v2 方案**：`detect_stack` 用扩展名 + 路径前缀双重判断。

---

## 16. T017 (polish) 归入 setup 组

**问题**：`_group_by_phase` 把没有 `[US*]` 标签的 task 统一归入 "setup"。

**后果**：T017（Phase 6 polish）和 T001-T003（Phase 1 setup）在同一组，执行顺序混乱。

**修复**：检测 task 位置 — 在最后一个 US task 之后的无标签 task 归入 "polish"。

**v2 方案**：`_group_by_phase` 支持 setup/US*/polish 三类分组。

---

## 17. GREEN retry 日志包含不相关 stack

**问题**：GREEN 失败后 `_get_failed_log` 返回所有 failed job 的日志，包括其他 stack 的。

**后果**：retry agent 收到不相关的错误信息，浪费 token，可能误导修复方向。

**修复**：`_get_failed_log` 接受 `relevant_jobs` 参数，只返回相关 stack 的日志。

**v2 方案**：`CICheckStrategy` 内部处理，retry detail 只包含相关 stack。

---

## 18. `activate()` 未捕获 TimeoutExpired

**问题**：`gh auth status` 超时时 `activate()` 崩溃。

**后果**：编排器启动失败。

**修复**：except 加 `subprocess.TimeoutExpired`。

**v2 方案**：所有 subprocess 调用统一捕获 `(FileNotFoundError, subprocess.TimeoutExpired)`。

---

## 19. Agent 知识文件预加载 vs 渐进式

**问题**：`agent_registry.py` 的 `build_agents()` 把所有 `source_files` 一次性拼接进 prompt。

**后果**：brooks-reviewer 7 个文件全加载约 20K tokens，但 Mode 1 只需 3 个。

**修复**：`_build_prompt` 只加载 source_files 中的核心文件，其余通过 Knowledge Base 路径注入，agent 运行时按需 Read。

**v2 方案**：保持渐进式加载模式。`source_files` 只放核心指令，Knowledge Base 路径自动注入。

---

## 20. `_is_small_project` 跳过逻辑不可靠且不应存在

**问题**：`_is_small_project` 试图根据 requirement 文本长度和结构特征自动跳过 constitution 阶段。多次修复后仍然误判（阈值调整、路径检测、特征计数都没彻底解决）。

**根本原因**：`self.requirement` 的内容取决于传入方式（`--req-file` 文件内容 vs 命令行参数 vs 空字符串），不同入口路径导致的 requirement 内容不确定。

**v2 方案**：**删除 `_is_small_project` 逻辑。所有项目无论大小都执行完整的四阶段流水线。** 不做任何阶段跳过的自动判断。如果用户要跳过某阶段，通过配置显式指定（如 `skip_stages: [constitution]`），而不是编排器自作主张。

---

## 21. 编排器代码和 agent 知识文件耦合

**问题**：agent 的 `agent.md` 中引用的文件名（如 "Read `spec-template.md`"）需要和实际文件路径匹配。Knowledge Base 注入绝对路径后，agent 需要把短文件名映射到绝对路径。

**后果**：如果 agent 直接用短文件名调用 Read tool，会因为找不到文件而失败。

**修复**：Knowledge Base 注入时加 IMPORTANT 提示 "use the full absolute path from the list above"。

**v2 方案**：Knowledge Base 注入格式保持一致，每个文件列出绝对路径。

---

## 22. `_commit_and_push` git add 路径硬编码

**问题**：`_commit_and_push` 中 `git add` 的目标目录硬编码为 `src/`, `src-tauri/`, `tests/` 等，不覆盖 Python 项目的 `orchestrator/` 等目录。

**后果**：Python 项目的所有文件改动无法被 stage，导致 "nothing to commit or push"，所有 task 的 RED 阶段全部失败。

**修复**：改为自动扫描 `cwd` 下的顶层目录（排除 `.git`, `.workflow`, `node_modules` 等已知非源码目录），动态 `git add`。

**v2 方案**：`_commit_and_push` 应自动检测项目目录结构，或从配置读取 `source_dirs` 列表。

---

## 23. 项目未初始化 git 仓库

**问题**：编排器假设 `cwd` 已经是 git 仓库且有 GitHub remote，但新项目目录可能既无 `.git` 也无 remote。

**后果**：所有 git 操作（add, commit, push）静默失败，编排器报 "nothing to commit or push" 而非真正原因。

**修复**：手动 `git init` + `gh repo create` + 推送初始 commit。

**v2 方案**：编排器启动时检查 git 状态，若无 `.git` 则报错并提示用户初始化；若无 remote 则自动提示或创建。

---

## 24. `_detect_task_stack` 不支持 Python 项目

**问题**：`_detect_task_stack` 只识别 `rust` 和 `frontend` 两种技术栈，`.py` 文件返回 `None`。

**后果**：Python task 走 "unknown stack — check all jobs" 逻辑，会检查不存在的 Rust/Frontend job，导致误判。

**修复**：增加 `"python"` stack，`.py` 文件扩展名匹配返回 `"python"`。

**v2 方案**：`detect_stack()` 应支持可扩展的技术栈注册（rust/frontend/python/go 等），而非 if-elif 硬编码。

---

## 25. CI job 名称硬编码不支持多语言

**问题**：`_relevant_jobs_pass` 和 RED/GREEN 检查逻辑硬编码了 `"Rust Tests"`, `"Rust Build Check"`, `"Frontend Tests"`, `"TypeScript Check"` 四个 job 名。

**后果**：Python 项目的 CI job（`"Python Tests"`, `"Coverage Check"`）不在检查范围内，编排器无法正确评估 CI 结果。

**修复**：增加 `python_jobs = ("Python Tests", "Coverage Check")` 及对应分支逻辑。

**v2 方案**：CI job 映射应从配置读取（如 `ci_jobs: {python: ["Python Tests", "Coverage Check"]}`），而非代码硬编码。

---

## 26. `_has_test_targets` 不检测 Python 项目

**问题**：`_has_test_targets` 只检查 `src-tauri/Cargo.toml` 和 `package.json`，Python 项目没有这些文件。

**后果**：CI 模式下 Python 项目被判定为"无测试目标"，直接跳过 CI 检查，RED/GREEN 阶段不执行。

**修复**：增加 `pytest.ini`, `pyproject.toml`, `setup.py`, `setup.cfg` 检测，以及 `tests/` 目录存在性检查。

**v2 方案**：测试目标检测应基于配置 + 自动发现（扫描常见测试配置文件和目录），而非硬编码文件列表。

---

## 27. RED 阶段 agent 同时写了测试和实现

**问题**：`_call_red_agent` 的 prompt 只包含任务描述和文件路径，没有明确约束"只写测试，禁止写实现"。`tdd-guide` agent 的定义包含完整 RED-GREEN-REFACTOR 流程，agent 自动跑完了整个循环。

**后果**：RED 阶段 agent 同时写了 873 行测试 + 257 行实现代码，CI 全部 PASSED，编排器判定为"无效 RED"（测试没有失败）。

**修复**：RED prompt 开头增加明确约束：`## 阶段\nRED — 只写测试，禁止写实现代码`，以及详细的约束条件（只创建测试文件、被测模块仅空 stub、测试必须因断言失败而非 ImportError 失败）。

**v2 方案**：RED/GREEN prompt 模板应分离，RED 模板包含 "ONLY write tests" 硬约束，GREEN 模板包含 "implement to pass existing tests" 硬约束。
