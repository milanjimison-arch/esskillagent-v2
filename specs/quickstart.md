# E+S Orchestrator v2 — Quick Start Guide

**Created**: 2026-04-01
**Related**: [spec.md](spec.md) | [plan.md](plan.md) | [data-model.md](data-model.md)

---

## 前置条件

- Python 3.12+
- Git（项目目录必须是 git 仓库）
- Claude Agent SDK（或 `claude` CLI 作为降级）
- `gh` CLI（仅 CI 模式需要，`local_test: true` 不需要）

## 目录结构

```
your-project/
├── .orchestrator.yaml       ← 项目级配置（可选）
├── brownfield.yaml          ← v1 兼容配置（可选）
├── .workflow/
│   ├── workflow.db          ← SQLite 持久化（自动创建）
│   ├── outputs/             ← 阶段产出
│   └── status.log           ← 运行日志
├── specs/
│   ├── spec.md              ← 规格说明（spec 阶段产出）
│   ├── plan.md              ← 实施计划（plan 阶段产出）
│   ├── tasks.md             ← TDD 任务列表（plan 阶段产出）
│   └── checklists/
│       └── traceability.md  ← 追溯矩阵（acceptance 阶段产出）
└── src/                     ← 你的项目源码
```

## 快速开始

### 1. 启动新流程

```bash
# 基本用法：传入需求文件
python -m orchestrator run /path/to/project --req-file requirement.md

# 或直接传入描述文字
python -m orchestrator run /path/to/project --req "Add user authentication with JWT"
```

系统将按顺序执行四阶段流水线：

1. **Spec** — constitution → specify → clarify → review
2. **Plan** — plan → research → tasks → review
3. **Implement** — TDD RED→GREEN → review → push+CI
4. **Acceptance** — 验收 → traceability matrix → review

### 2. 从中断恢复

```bash
# 从上次检查点恢复
python -m orchestrator resume /path/to/project
```

系统读取 `.workflow/workflow.db` 中的最后检查点，从下一个待完成步骤继续。

### 3. 重试单个失败任务

```bash
# 重试指定任务
python -m orchestrator retry /path/to/project T003
```

仅重跑 T003 的 TDD 循环，不影响其他任务。

### 4. 查看进度

```bash
# 查看当前流水线状态
python -m orchestrator status /path/to/project
```

输出示例：
```
Pipeline: implement (running)
  spec:       completed ✓
  plan:       completed ✓
  implement:  running   (12/17 tasks done)
  acceptance: pending

Tasks: 12/17 completed, 1 failed (T003), 4 pending
```

## 项目级配置

在项目根目录创建 `.orchestrator.yaml` 覆盖全局默认值：

```yaml
# .orchestrator.yaml — 项目级配置
local_test: true                          # 使用本地测试（不走 CI）
test_command: "cargo test -- --test-threads=1"  # 自定义测试命令
ci_timeout: 2400                          # CI 超时（秒）
max_green_retries: 5                      # GREEN 重试上限
skip_stages: []                           # 显式跳过阶段（慎用）

models:
  default: claude-sonnet-4-6
  spec: claude-opus-4-6
  reviewer: claude-opus-4-6
```

### 配置加载优先级

```
1. orchestrator/defaults.yaml    (内置默认 — 最低优先)
2. <project>/brownfield.yaml     (v1 兼容)
3. <project>/.orchestrator.yaml  (项目覆盖)
4. ORCHESTRATOR_* 环境变量       (运行时覆盖 — 最高优先)
```

后层覆盖前层同名键。

### 环境变量覆盖

```bash
# 格式: ORCHESTRATOR_<UPPER_KEY>
export ORCHESTRATOR_LOCAL_TEST=true
export ORCHESTRATOR_CI_TIMEOUT=3600
```

## 测试策略切换

### 本地测试模式 (`local_test: true`)

- 测试在本机运行
- 使用 `test_command` 配置的命令
- 适合开发阶段快速迭代

### CI 测试模式 (`local_test: false`)

- 代码 commit + push 后等待 GitHub Actions
- 自动匹配 commit SHA 到 CI run ID
- Stack scoping: 根据 file_path 只检查相关 job
- 错误反馈: per-job 结构化输出，2000 字符预算

切换只需改配置，**无需改任何代码**。

## tasks.md 格式规范

TDD 任务列表必须遵循以下格式：

```markdown
- [ ] T001 [US1] [FR-001] Set up project configuration — src/config.ts
- [ ] T002 [P] [US1] [FR-002] Implement auth service — src/auth/service.ts
- [ ] T003 [P] [US1] [FR-003] Implement auth middleware — src/auth/middleware.ts
- [ ] T004 [US2] [FR-005] Add user profile endpoint — src/api/profile.ts
```

- `[P]` = 并行标记（同组可并行执行，必须有 file_path）
- `[US*]` = 关联 User Story
- `[FR-###]` = 关联 Functional Requirement
- `—` (em dash) 分隔描述和主文件路径

## 常见问题

### Q: 可以跳过某个阶段吗？

可以，在 `.orchestrator.yaml` 中配置：
```yaml
skip_stages: [spec]  # 跳过 spec 阶段
```
但不推荐。所有项目默认执行完整四阶段流水线。

### Q: v1 的 brownfield.yaml 还能用吗？

能。v2 自动识别并加载 `brownfield.yaml`，优先级低于 `.orchestrator.yaml`。

### Q: 如何从 v1 的 workflow.db 恢复？

直接用 `orchestrator resume`。v2 兼容 v1 的全部 8 个表结构，可直接读取。

### Q: 并行任务 [P] 出现 git 冲突怎么办？

v2 内建安全检查：
1. 同组 [P] 任务的 file_path 不能重叠
2. 如果检测到重叠，自动降级为串行执行
3. Phase A/B 都使用 batch commit，一次提交所有并行 agent 的修改

### Q: Wave 面板是必须的吗？

不是。Wave 面板在 `ui/` 包中，完全独立。即使删除 `ui/` 包，核心编排器也正常运行。
