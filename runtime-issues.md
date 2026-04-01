# E+S Orchestrator v1 运行时问题记录（v2 构建期间）

本文档记录用 v1 编排器构建 v2 项目时发现的运行时问题，供后续迭代参考。

---

## R01. git 仓库未初始化

**现象**：所有 task 的 RED 阶段报 `push failed: nothing to commit or push`。

**根因**：编排器假设 `cwd` 是已有 git 仓库，但新项目目录无 `.git`，所有 git 命令静默失败。

**修复**：手动 `git init` + `gh repo create`。

**建议**：编排器启动时检测 `.git` 是否存在，不存在则报错退出并提示用户初始化。

---

## R02. `_commit_and_push` git add 路径硬编码

**现象**：Python 项目的文件改动无法被 stage，始终 "nothing to commit"。

**根因**：`ci_checks.py` 的 `_commit_and_push` 硬编码 `git add -- src/ src-tauri/ tests/`，不包含 `orchestrator/` 等 Python 项目目录。

**修复**：改为自动扫描 `cwd` 下的顶层目录（排除 `.git`, `.workflow`, `__pycache__` 等）。

**建议**：从配置读取 `source_dirs` 列表，或自动检测。

---

## R03. `_detect_task_stack` 不识别 Python

**现象**：Python task 走 "unknown stack — check all jobs"，检查不存在的 Rust/Frontend job。

**根因**：`_detect_task_stack` 只有 `rust` 和 `frontend` 两种 stack，`.py` 文件返回 `None`。

**修复**：增加 `"python"` stack，`.py` 扩展名匹配。

**建议**：stack 检测做成可扩展注册表，支持 rust/frontend/python/go 等。

---

## R04. CI job 名称硬编码

**现象**：Python 项目的 CI job（`Python Tests`, `Coverage Check`）不在检查范围内。

**根因**：`_relevant_jobs_pass` 和 RED/GREEN 逻辑硬编码了 `Rust Tests`, `Frontend Tests` 等 job 名。

**修复**：增加 `python_jobs` 元组及对应分支。

**建议**：CI job 映射从配置读取，如 `ci_jobs: {python: ["Python Tests", "Coverage Check"]}`。

---

## R05. `_has_test_targets` 不检测 Python 项目

**现象**：CI 模式下 Python 项目被判定为"无测试目标"，跳过 CI 检查。

**根因**：只检查 `Cargo.toml` 和 `package.json`，无 Python 项目文件检测。

**修复**：增加 `pytest.ini`, `pyproject.toml`, `setup.py` 检测及 `tests/` 目录检查。

**建议**：基于配置 + 自动发现（扫描常见测试配置文件和目录）。

---

## R06. RED 阶段 agent 同时写了测试和实现

**现象**：T001 RED 阶段 CI 全 PASSED（测试没有失败），编排器判定 "not valid RED"。

**根因**：`_call_red_agent` 的 prompt 没有明确约束"只写测试"。`tdd-guide` agent 自动走完 RED-GREEN-REFACTOR 全流程，同时写了 257 行实现 + 873 行测试。

**修复**：RED prompt 开头增加 `## 阶段\nRED — 只写测试，禁止写实现代码` 及详细约束。

**建议**：RED/GREEN prompt 模板分离，RED 包含 "ONLY write tests" 硬约束。

---

## R07. CI 环境缺依赖导致 GREEN 3 次重试全失败

**现象**：T002 GREEN 3 次重试都报 `ModuleNotFoundError: No module named 'yaml'`。

**根因**：`ci.yml` 只安装了 `pytest pytest-cov pytest-asyncio`，未安装 `pyyaml`。项目无 `requirements.txt`。

**修复**：创建 `requirements.txt` 添加 `pyyaml>=6.0`，CI 已有 `if [ -f requirements.txt ]; then pip install -r requirements.txt; fi`。

**建议**：
- 编排器在生成 CI workflow 时自动扫描项目依赖
- GREEN 重试时区分"环境问题"和"代码问题"，环境问题不应消耗重试次数

---

## R08. GREEN 重试 agent 无法修复 CI 环境问题

**现象**：重试 2/3 和 3/3 报 `nothing to commit or push`，agent 没有实际修改。

**根因**：GREEN 重试的逻辑是让 agent 修改代码再 push，但 `ModuleNotFoundError` 是 CI 环境缺包，agent 改代码解决不了。且 agent 没有权限修改 `ci.yml` 或 `requirements.txt`。

**建议**：
- 重试前分析失败日志，区分 `ImportError/ModuleNotFoundError`（环境）vs `AssertionError`（逻辑）
- 环境问题应提示用户修复，不消耗重试次数

---

## R09. 编排器无 task 跳过逻辑

**现象**：恢复运行时已完成的 task 会被重新执行。

**根因**：`_execute_single_task` 和 `_run_parallel_group` 入口不检查 task 状态，遍历所有 task 无条件执行。

**修复**：
- `_execute_single_task` 入口检查 `status == "completed"` 则跳过
- `_run_parallel_group` 过滤已完成 task

**建议**：所有 task 执行入口统一检查状态，支持从断点恢复。

---

## R10. CLAUDE.md 设计文档索引指向已删除文件

**现象**：项目重置后 CLAUDE.md 仍引用 `specs/*.md` 文件。

**根因**：编排器在 spec/plan 阶段生成文件后会更新 CLAUDE.md 的索引，但重置时只清了文件没更新索引。

**建议**：CLAUDE.md 的设计文档索引应标注为"由编排器自动生成"，或编排器重置时自动清理。

---

## R11. Agent 引入新依赖但未更新 requirements.txt

**现象**：T003 GREEN 首次 CI 报 `ModuleNotFoundError: No module named 'aiosqlite'`，重试后 agent 自行修复。

**根因**：Agent 写了 `import aiosqlite` 但没同步更新 `requirements.txt`。编排器在 commit 前无依赖一致性检查。

**责任归属**：Agent 是直接责任（漏加依赖），编排器应兜底检查。

**修复**：agent 重试时自行补上了 `aiosqlite>=0.20.0`。

**建议**：
- RED/GREEN prompt 增加约束："引入新第三方依赖时必须同时更新 requirements.txt"
- 编排器在 `_commit_and_push` 前做轻量检查：扫描 diff 中的新 import，比对 requirements.txt + stdlib，发现缺失则 warning
- 注意 import 名和 pip 名不一致的情况（如 `import yaml` → `pyyaml`）

---

## R12. implement 阶段 stage_timeout 一刀切导致超时

**现象**：T016 RED 阶段刚开始就触发 `[implement] XX timeout — 阶段超时 (3600s)`，整个 implement 阶段终止。

**根因**：E+S 编排器用 `stage_timeout: 3600`（1 小时）覆盖整个 implement 阶段。20 个 task 串行执行，每个 task 的 RED+GREEN+CI 约 10-15 分钟，7 个 task 就用完了 1 小时。

**对比 brownfield-orchestrator 的设计**：
- brownfield 没有 `stage_timeout` 概念
- 每个 agent 调用有独立的 `idle_timeout`（600s/10min）
- CI 等待有独立的 `ci_timeout`（1800s/30min）
- 只有 `global_timeout`（14400s/4h）做总兜底
- 每个步骤独立超时，不因步骤数量多而累加超限

**修复**：
- implement 阶段取消 `stage_timeout`，改为每个 task 独立 timeout
- 只保留 `global_timeout`（14400s）做总兜底
- 参考 brownfield：idle_timeout（agent 调用）+ ci_timeout（CI 等待）+ global_timeout（总兜底）

**建议**：v2 应采用 brownfield 的三层超时架构（idle_timeout / ci_timeout / global_timeout），而非 stage_timeout 一刀切。

---

## R13. 并行利用率低 — 大部分 task 实际串行执行

**现象**：20 个 task 中只有 6 个标记 `parallel=1`，且分散在不同 story_ref 组中。实际能并行的只有 US3（T010+T011）和 polish（T018+T019）两组各 2 个 task，其余全部串行。

**根因**：
1. **plan agent 标记保守**：US2 的 3 个 task（parser/validator/runner）虽然文件不重叠，但 agent 判断有逻辑依赖，标为串行。合理但偏保守。
2. **并行组被 story_ref 割裂**：T012(US8) 和 T013(US9) 各自 `parallel=1` 但组内只有 1 个 task，并行标记无意义。跨 story_ref 组不能并行。
3. **CI 串行瓶颈**：即使 agent 并行写代码，CI 验证仍是 batch commit → 等一次 CI。每次 CI 等待 3-5 分钟，串行 20 个 task 仅 CI 等待就需要 2+ 小时。

**影响**：20 个 task 全程约 3-4 小时，其中大部分时间在等 CI。

**建议**：
- plan agent 的 tasks prompt 应引导更多并行：文件不重叠的 task 默认标 `[P]`，仅有显式 import 依赖时才串行
- 允许跨 story_ref 并行：同一 implement 阶段内，不同 US 组的 `[P]` task 若文件不重叠可以合并为一个并行 batch
- 极端优化：本地 pytest 预检（秒级）+ CI 仅做最终验证，减少 CI 往返

---

## R14. 并行 batch CI 验证粒度不足

**现象**：并行组（如 T010+T011）共用一次 CI 验证 RED/GREEN，无法区分单个 task 的通过/失败。

**具体风险**：
- RED 阶段：如果其中一个 task 的 agent 偷写了实现（如 R06），batch CI 仍报 failure，该 task 被误判为 "valid RED"
- GREEN 阶段：如果一个 task 通过但另一个失败，CI 整体 failure，所有 task 被重试，已通过的 task 白白重跑

**根因**：batch commit 将多个 task 的文件合并为一次 CI 运行，编排器只看 CI 整体 pass/fail，没有 per-task 粒度。

**建议**：
- plan 阶段应预估 CI 调用次数：串行 task 每个 2 次 CI（RED+GREEN），并行组每组 2 次 CI，总数写入 `specs/plan.md` 供用户评估
- RED 验证改进：batch CI 失败后，解析 pytest 输出按测试文件归属 task，逐个判断是否 "valid RED"
- GREEN 验证改进：batch CI 失败后，识别哪些 task 的测试通过了，只对失败的 task 重试 GREEN
- 考虑每个 task 独立 CI（牺牲速度换精度），或通过 pytest `-k` 参数只跑单个 task 的测试子集

---

## R15. batch GREEN 不写 LVL 记录 — 证据链缺失

**现象**：T005/T006（并行 batch）和 T010/T011（并行 batch）的 task 状态为 `completed`/`green_done`，LVL 表中只有 RED 记录，无 GREEN 记录。串行 task（T002-T004, T014-T016 等）都有完整的 GREEN lvl 记录。

**根因**：`_run_parallel_group` 的 Phase B（GREEN）batch CI 通过后，直接 `mark_task_completed` 但没调用 `store.log_lvl()` 记录 GREEN 证据。串行模式的 `_run_tdd_task` 在 GREEN 通过后会写 lvl。

**影响**：
- 证据链不完整，无法追溯并行 task 的 GREEN 验证时间、commit SHA
- 恢复运行时无法判断 GREEN 是否真的通过了（只能看 task status，不能看 lvl 证据）

**建议**：`_run_parallel_group` Phase B 通过后，为每个 task 写入 GREEN lvl 记录，包含 batch commit 的 git_sha。

---

## R16. 手动修改 task 状态导致 LVL 与 status 矛盾

**现象**：T001 的 LVL 记录为 `RED fail`（CI passed, not valid RED），但 task status 为 `completed`。

**根因**：T001 的 RED 阶段 agent 同时写了测试和实现（R06），CI 通过被判定为无效 RED。后来人工分析代码正确，手动在 DB 中标记 `completed`，但没有补充 lvl 记录。

**影响**：审计时 LVL 显示 T001 从未通过任何阶段，但 task 已 completed，矛盾。

**建议**：
- 手动修改 task 状态时应同时写入 lvl 记录（如 `manual_override` method）
- 或编排器提供 `force-complete` 命令，自动补写 lvl + 更新 status

---

## R17. 重跑 task 的旧 LVL 记录未标记 superseded

**现象**：T002 有两套 RED 记录 — 第一次运行（id=11, sha=69f59fbc）和第二次运行（id=15, sha=a0f13771），以及第一次运行的 3 条 GREEN 失败记录（id=12-14），全部 `superseded=0`。

**根因**：编排器重置 task 状态后重跑，新的 RED/GREEN 记录追加到 LVL，但旧记录没有被标记为 `superseded=1`。

**影响**：
- 同一 task 有多条 RED pass 记录，查询"T002 的 RED 结果"会返回多条
- 旧的 GREEN 失败记录（pyyaml 缺失）仍然活跃，污染统计

**建议**：
- task 重跑时，先将该 task 的所有旧 lvl 记录标记 `superseded=1`
- 或在 `mark_task_running` 时自动 supersede 前序记录

---

## R18. 续接运行后 Wave 面板进度显示不正确

**现象**：编排器从 implement 阶段断点续接后，Wave 面板显示：
- Stage Overview 显示 `Progress: 2/4 stages completed`（spec + plan），implement 未标记为 running
- acceptance 仍显示 `○ pending`
- implement 阶段的 task 进度条未反映已完成的 task（T001-T006 等）

**根因**：Wave 面板在启动时从 DB 读取状态渲染，但续接模式下：
1. implement 的 stage_progress 是手动设为 `running`，Wave 可能未正确刷新
2. 已完成的 task 在面板上没有回填显示
3. 面板的 task 列表可能只显示当前 session 的 task，不含历史完成的

**影响**：用户无法通过面板了解真实进度，只能看日志。

**建议**：
- Wave 面板启动时应扫描 DB 中所有 task 状态，回填已完成的 task 进度
- 续接运行时 implement 阶段应显示 `● running (resumed)`
- task 进度应显示 `8/20 completed` 而非从 0 开始
