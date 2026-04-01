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
