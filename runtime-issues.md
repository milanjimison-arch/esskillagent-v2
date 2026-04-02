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

---

## R19. 模块行数硬性约束导致不必要的拆分压力

**现象**：T020 的契约测试发现 `store/db.py` 和 `store/queries.py` 超过 400 行限制，但代码逻辑完整、测试通过，强行拆分反而破坏内聚性。

**根因**：CLAUDE.md 写的 "每个模块 < 400 行" 是硬性约束，agent 会严格检查并报告违规。但实际开发中，一个模块 420 行和 400 行没有本质区别。

**建议**：行数约束改为软性，允许 50 行波动范围（即 < 450 行为合格，> 450 行才需要拆分）。避免 agent 为了凑行数做不必要的拆分。

---

## R28. Claude CLI 子进程泄漏 — 200+ 僵尸进程占用 20GB+ 内存

**现象**：编排器运行一段时间后，系统中出现 200+ 个 python.exe 进程，每个约 109MB，总计超过 20GB 内存。用户报告"内存快满了"。

**根因**：SDK 模式下，`claude_agent_sdk.query()` 内部通过 `SubprocessCLITransport.connect()` 启动 `claude` CLI 子进程（`anyio.open_process`）。`_sdk_call` 消费完 async generator 后直接 return，没有调用 transport 的 `close()`/`disconnect()`。SDK 的 disconnect 方法有完整的 terminate→kill 清理链（等 5s → SIGTERM → 等 5s → SIGKILL），但因为没被调用，子进程变成孤儿。CLI 模式（`_cli_call`）的 `Popen.communicate()` 不受影响。

13 个 task 完成 × 每个 task 至少 2 次调用（RED + GREEN） × 部分有 retry = 30+ 次调用。加上 spec/plan 阶段的 agent 调用，累积到 200+ 个僵尸进程。

**影响**：
- 系统内存耗尽，可能导致后续 task 的 agent 调用 OOM 失败
- Windows 进程句柄泄漏
- 编排器长时间运行（20+ task）时必然触发

**修复（已应用）**：
1. `_sdk_call`: `try/finally: await asyncio.wait_for(gen.aclose(), timeout=30)` — 确保 generator 关闭触发 SDK transport cleanup，且 aclose 自身有超时保护防止二次卡死
2. `_cli_call`: tmpfile 清理移入 `finally` 块，确保所有异常路径都执行
3. `_cli_call_streaming`: 所有异常路径加 `proc.kill()` + `proc.wait(timeout=10)` 回收句柄
4. 全局 `_active_procs` 注册表 + `atexit.register(_cleanup_active_procs)` — Ctrl+C / 正常退出时强制 kill 所有残留子进程
5. 所有 Popen 创建后 `_active_procs.add(proc)`，完成/异常后 `_active_procs.discard(proc)`

**第二轮 Opus 对抗审核修复**：
6. `except (TimeoutError, Exception)` → `except BaseException` — 捕获 CancelledError 防止 aclose 被跳过（P0 级）
7. `_active_procs` 加 `threading.Lock` — `_register_proc/_unregister_proc/_cleanup_active_procs` 全部线程安全
8. `proc.communicate()` (无 timeout) → `proc.wait(timeout=10)` — 防止 communicate 永久阻塞
9. `_cli_call_streaming` 开头 `proc = None` — 防止异常路径 NameError
10. OSError handler 中 `if proc is not None:` 守卫 — 防止 Popen 构造失败时 NameError

**Opus 对抗审核遗留风险（已知但未修复）**：
- `taskkill /F` 强杀时 `atexit` 不执行，子进程仍成孤儿（OS 级限制，无法解决）
- Windows `shell=True` 的 `proc.kill()` 只 kill `cmd.exe` 不递归 kill 子进程树（需 `taskkill /T /PID`，暂不改）
- SDK 子进程不经过 `_active_procs`（依赖 `gen.aclose()` 清理，已用 `BaseException` 兜底）
- V2 的 `adapter.py` 也需要检查同样的问题

---

## R29. `gen.aclose()` 无超时保护 — 子进程挂死时二次卡死

**现象**：SDK `_sdk_call` 中 idle_timeout 触发后，`finally` 块调用 `gen.aclose()` 清理 generator。但 aclose 需要 SDK 内部的 `process_query` finally 块执行（关闭 transport/kill 子进程）。如果子进程处于不响应状态（正是超时的原因），aclose 自身也会卡住，导致整个 event loop 阻塞。

**根因**：超时的根因往往是子进程挂死，而 `aclose()` 的清理依赖同一个挂死的子进程响应。无超时保护的 `await gen.aclose()` 等于让清理操作继承了原问题。

**影响**：event loop 永久阻塞 → `asyncio.run()` 不返回 → `run.py` 的 `finally: engine.close()` 不执行 → 用户只能 `taskkill /F` → atexit 也不执行 → 全部子进程成孤儿。

**修复**：`await asyncio.wait_for(gen.aclose(), timeout=30)` + `except (TimeoutError, Exception): pass`。已应用到 R28 修复中。

---

## R30. `_cli_call_streaming` 异常路径子进程句柄泄漏

**现象**：CLI streaming 模式的 `subprocess.TimeoutExpired` 处理只有 `proc.kill()` 没有 `proc.wait()`，进程句柄未被回收。`OSError`/`SubprocessError` 异常路径完全没有 kill 子进程的逻辑。

**根因**：
- L319 `TimeoutExpired`: `proc.kill()` 后直接 `return`，没有 `proc.wait()` 回收句柄
- L328 `OSError`: timer 可能已 cancel，proc 可能仍在运行，但异常处理直接 return

**影响**：Windows 下未 wait 的 killed 进程变僵尸，进程句柄泄漏。与 R28 同类问题但在 CLI 路径。

**修复**：所有异常路径加 `proc.kill()` + `proc.wait(timeout=10)` + `_active_procs.discard(proc)`。已应用。

---

## R31. `_cli_call` agents tmpfile 异常路径泄漏

**现象**：`_cli_call` 中 agents JSON 临时文件用 `delete=False` 创建，清理代码在正常路径末尾。`FileNotFoundError` 和 `OSError` 异常路径 return 前未清理。

**根因**：tmpfile 清理代码不在 `try/finally` 中，early return 跳过了清理。

**影响**：`%TEMP%` 中累积孤儿 JSON 文件。单文件很小，但长期运行累积。

**修复**：tmpfile 清理移入 `finally` 块。已应用。

---

## R32. 无 atexit/signal 处理 — 异常终止时子进程全部成孤儿

**现象**：编排器没有注册 `atexit` 回调或 `signal` 处理器。Ctrl+C 时依赖 `asyncio.run` 的 cancel 传播，但如果 cancel 处理卡住（R29），子进程全部泄漏。

**根因**：`claude_adapter.py` 没有维护活跃子进程的注册表，`engine.close()` 只清理锁和 SQLite，不 kill 子进程。

**影响**：用户 Ctrl+C 或 `taskkill` 后，所有 SDK/CLI 子进程成为孤儿进程持续占用内存。

**修复**：
- 全局 `_active_procs: set[subprocess.Popen]` 注册表
- `atexit.register(_cleanup_active_procs)` 在正常退出/Ctrl+C 时 kill 所有残留进程
- 所有 Popen 创建后 add，完成/异常后 discard
- 已应用。注意 `taskkill /F` 强杀时 atexit 不执行，这是 OS 级限制。

---

## R33. `"."` 相对路径导致 workflow 创建在错误目录

**现象**：编排器从 spec 阶段重新开始，而不是从 implement 续接。DB 检查显示 spec=completed, implement=running 没有被重置。

**根因**：启动命令中项目路径用 `"."` 相对路径，但 PowerShell 当前目录不是项目目录（如在 `C:\Users\mixstyleman` 执行），导致 `"."` 解析到 home 目录，在那里创建了全新的 `.workflow/workflow.db`。

同样问题在 `launch.py` 的 Wave 模式中更隐蔽：`wsh run` 启动 bootstrap 脚本时，工作目录可能不继承终端的 cwd，`"."` 解析到错误位置。

**影响**：
- 看似 resume 不工作，实际是操作了错误的 workflow.db
- 在 home 目录下误创建 `.workflow/` 目录和文件
- 已完成的 14 个 task 进度"丢失"（实际未丢失，只是读错了 DB）

**修复**：启动命令必须使用完整绝对路径，不要用 `"."`。

**正确的启动命令**（从任意目录执行）：
```powershell
python "F:\claude\技能备份\E+S\launch.py" --auto --req-file requirement-v2.md "F:\claude\技能备份\ESSKILLAGENT-v2"
```

**建议**：`run.py` 和 `launch.py` 应将 `"."` 自动解析为绝对路径（`Path(cwd).resolve()`），或在检测到相对路径时打印 warning 显示实际解析到的目录。

---

## R27. agents-src/ 知识文件无对应适配任务

**现象**：T018 只改 `orchestrator/agents/registry.py`（注册代码），不改 `agents-src/` 下 14 个 agent 的知识文件。requirement-v2.md 的 A1-A10 agent 适配被压缩进了 registry 层面的 prompt 注入，实际 agent 行为模式（知识文件里的指令）没有 task 去修改。

**影响**：
- registry 注入 prompt 前缀只是"建议"，agent 自身知识文件的指令优先级更高
- R06（tdd-guide RED 阶段写了实现）根因就是知识文件没有 RED 约束，仅靠 prompt 注入不可靠
- R25（task-generator 用 `--` 而非 `—`）也是知识文件格式问题，已手动修复但不在 task 覆盖范围内
- spec-writer 的 NC 标记、planner 的 NR 标记、acceptor 的结构化输出等都需要写进知识文件才能生效

**涉及的 agent 知识文件**：
- `agents-src/tdd-guide/`: RED-only 约束（A1）
- `agents-src/spec-writer/`: NC 标记输出格式（A9）
- `agents-src/planner/`: NR 标记输出格式（A10）
- `agents-src/task-generator/`: FR 标签 + `--` 格式（A2，已手动修复）
- `agents-src/fixer/`: 依赖感知 + 前次失败注入（A5）
- `agents-src/acceptor/`: 结构化验收输出（A6）
- `agents-src/implementer/`: GREEN-only 约束
- `agents-src/code-reviewer/`, `security-reviewer/`, `brooks-reviewer/`: 结构化 verdict 格式

**建议**：补充一个独立 task 专门适配 agents-src/ 知识文件，或在 T018 执行时同步修改知识文件而非仅改 registry。

---

## R24. task-generator 的 [FR-###] 标签未覆盖所有 FR

**现象**：plan 阶段 coverage 检查报 `tasks.md 未覆盖 15 个 FR`，但底部 FR Coverage Matrix 表格显示这些 FR 实际有对应 task。

**根因**：coverage 检查只扫描 task 行中的 `[FR-###]` 标签（正则匹配），不读底部的 FR Coverage Matrix 表格。task-generator agent 在 task 描述中只标注了主要 FR，但部分 FR 被归入"隐式覆盖"写在底部矩阵中而非 task 行内。例如 T008 描述中标了 `[FR-026]~[FR-031]`，但 FR-033~039 只在底部矩阵写了 `T008 (implement/TDD runner integration)`。

**影响**：coverage 检查误报缺失，可能触发不必要的 gate 阻断或警告。

**建议**：
- task-generator prompt 中要求：每个 FR 必须出现在某个 task 行的 `[FR-###]` 标签中，不能只写在底部矩阵
- 或 coverage 检查同时扫描底部矩阵表格作为补充数据源

---

## R25. [P] 任务全部降级串行 — parser 不识别 `--` 分隔符

**现象**：implement 阶段所有 [P] 任务报 `[P] 但无 file_path，降级串行`，23 个任务全部串行执行。

**根因**：三方格式不一致：
- `task-generator` agent prompt (tasks-command.md) 第 109 行要求 em-dash `—` (U+2014)
- `task-generator` agent template (tasks-template.md) 示例里没有任何分隔符
- 实际 agent 输出使用了 `--`（双连字符），这是 LLM 最自然的输出
- V1 parser (`task_parser.py:_extract_file_path`) 只识别 em-dash `—` 和 en-dash `–`，不识别 `--`

这是 **pitfall #3**（parser 和 generator 格式漂移）的第二次重现。

**影响**：
- 所有 [P] 任务的 file_path 解析为空
- 并行任务全部降级为串行，执行时间成倍增长
- 并行文件冲突检测失效（无 file_path 可比较）

**修复**：
1. V1 parser `_extract_file_path` 新增策略 2：识别 `" -- "` 双连字符分隔（已修复）
2. agent prompt (tasks-command.md) 改为推荐 `--` 而非 em-dash，因为 LLM 输出 `--` 更可靠（已修复）
3. agent template (tasks-template.md) 示例统一添加 `-- file/path` 格式（已修复）

**教训**：LLM 生成的文本中，`--` 和 `—` 是不可互换的。Parser 必须兼容两者。Agent prompt 应使用 LLM 最自然输出的格式（`--`），而非排版格式（`—`）。

---

## R26. Context Rot — 审查/修复循环复用脏 session

**现象**：审查→修复→重新审查循环中，Round 2 的 reviewer 带着 Round 1 的完整对话历史，context 被前轮残留污染。fixer 多次 retry 也累积前次失败的冗余上下文。

**根因**：`_review_verify_fix` 的修复循环在调用 `_run_parallel_reviews()` 重新审查前，没有清除 reviewer 的 session。Session key `review_{agent_name}` 在 Round 1 和 Round 2 之间保持不变，SessionManager 自动续接了上轮对话。

同样，`_rerun_stage_content` 中 plan 阶段重跑后，`task_generator` 的 session 没有清理，导致 tasks.md 重新生成时带着上次错误输出的记忆。

**影响**：
- reviewer 可能因前轮残留而产生偏见（锚定效应）
- fixer 的 context 越来越长，后期修复质量下降
- task_generator 重试时受前次错误输出干扰

**修复**：
1. `_review_verify_fix` 重新审查前清除所有 reviewer + fixer 的 session（已修复）
2. `_rerun_stage_content` plan 分支重跑后清除 task_generator session（已修复）
3. RED 阶段 tdd-guide 和 GREEN 阶段 implementer 已按 task_id 隔离，无需额外处理

**教训**：session 续接只在"同一任务的重试"中有价值（如 GREEN retry），在"全新审查轮次"中是有害的。原则：**同任务重试 → 续接，新轮次 → 清除**。

---

## R20. 审查修复阶段 commit 消息中 task_id 为 "unknown"

**现象**：审查修复阶段的 commit 消息为 `green(unknown): implement to pass`，GitHub Actions 显示同样的标题。

**根因**：审查修复阶段调用 `_commit_and_push` 时传入的 `cfg` 没有 `task_id` 字段，`cfg.get("task_id", "unknown")` 回退到默认值。该阶段不是某个 task 的 RED/GREEN，而是整体审查后的修复提交。

**深层分析**：`_commit_and_push` 被三个场景复用，但 commit 消息模板只有一种：

| 场景 | 应该的 commit 消息 | 实际 |
|------|-------------------|------|
| task GREEN | `green(T001): implement to pass` | ✅ 正确 |
| 审查后 CI 验证 | `ci-check: post-review verification` | ❌ `green(unknown): implement to pass` |
| fixer 修复 | `fix(review): resolve H1 M3 issues` | ⚠️ agent 输出被直接当作消息，过长且非标准格式 |

`ci_tests_must_pass` 硬编码了 `green({task_id}): implement to pass` 消息模板。审查修复流程复用了该函数但传入的 cfg 没有 task_id 也没有自定义消息。fixer 的 commit 消息则是 `review_pipeline` 直接把 agent 输出文本塞进了 commit message（如 `fix(review): 所有审查问题已修复完成以下是变更摘要`）。

**影响**：
- git history 无法追溯提交对应的操作阶段
- fixer 的 commit 消息过长且包含非结构化中文，污染 git log
- CI 日志中 commit 标题无意义

**建议**：
- `_commit_and_push` 接受 `msg` 参数由调用者控制，不在 `ci_tests_must_pass` 内硬编码
- 审查 CI 验证用 `ci-check: post-review verification`
- fixer 修复用 `fix(review-attempt-N): resolve {severity_summary}`，不用 agent 原始输出
- commit 消息强制 < 72 字符，超出截断

---

## R21. review_pipeline severity 解析丢失 HIGH/MEDIUM 计数

**现象**：code-reviewer 的审查报告（`code_review.txt`）实际包含 H:2 M:3 L:2，但日志显示 `NEEDS_WORK (C:0 H:0 M:0 L:2)`，HIGH 和 MEDIUM 被完全丢失。

**对比**：

| 来源 | C | H | M | L |
|------|---|---|---|---|
| 日志（两轮均相同） | 0 | 0 | 0 | 2 |
| `code_review_r1.txt` | 0 | **2** | **3** | 2 |
| `code_review.txt` | 0 | **2** | **3** | 2 |

brooks-reviewer 的解析是正确的（Round 1: H:1 M:3 → Round 2: H:1 M:2，fixer 修了一个 MEDIUM）。

**根因**：`review_pipeline` 解析 agent 输出中的 severity 表格时，正则匹配只捕获到了 LOW 行的计数，HIGH 和 MEDIUM 行被跳过。可能是 agent 输出的表格格式（如 `**HIGH**` 加粗标记）与 pipeline 的正则不匹配。

**影响**：
- 编排器严重低估代码问题 — 2 个 HIGH 问题被当作 0 个
- fixer 可能未收到正确的修复优先级（不知道有 HIGH 需要修）
- 自动修复判断逻辑可能因计数错误而做出错误决策（如 "只有 LOW，不需要修复"）

**建议**：
- 审查报告应使用结构化输出（如 JSON verdict），而非从 markdown 表格正则解析
- 至少修复正则以兼容 `**HIGH**` 等加粗格式
- 添加校验：解析出的 severity 总数应等于报告中 findings 数量，不等则 warning

---

## R22. `_auto_fix` 的 fixer 拿不到完整审查报告

**现象**：fixer agent 修复时可能缺少完整的审查发现，只拿到摘要信息。

**根因**：`_review_verify_fix`（engine.py:1198）调用 `_get_review_issues("implement")`，读的是 `failure_history`（store 的历史摘要），不是审查输出文件。`_auto_fix` 内部只在 `error_text` 为空时才回退读三个审查文件（code_review.txt, security.txt, brooks_review.txt）。正常情况下 `failure_history` 不为空，fixer 拿到的是摘要而非完整报告。

**影响**：fixer 无法看到所有审查发现的详情，修复可能不完整。

**建议**：`_auto_fix` 应始终读取审查输出文件作为 fixer 的输入，`failure_history` 仅作为补充上下文。

---

## R23. `_auto_fix` 的 `no_critical` 检查读错文件导致永远失败

**现象**：`_auto_fix` 修复后的 `no_critical` 检查永远返回 `(False, "无审查输出可检查")`。

**根因**：`review_pipeline.py:492` 调用 `CHECKERS["no_critical"](self.cwd, self.config)`，`self.config` 是 brownfield.yaml 配置，没有 `output_file` 字段。`_get_output_path` 回退到 `last_output.txt`，该文件不存在。而 `_pre_push_review_pipeline:251` 的调用传入了正确的 `{"output_file": "code_review"}`。

**影响**：`_auto_fix` 返回 `tests_ok and crit_ok`，`crit_ok` 永远为 False，即使 fixer 修复正确、测试通过，auto_fix 仍返回 False，修复被误判为失败。

**修复建议**：将第 492 行改为 `CHECKERS["no_critical"](self.cwd, {"output_file": "code_review"})`，或直接只检查 tests 通过即可。
