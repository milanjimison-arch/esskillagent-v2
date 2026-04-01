# E+S Orchestrator v2

## Project Overview

E+S Orchestrator v2 是一个 Python 编排器，管理 AI agent 执行四阶段 TDD 工作流（spec → plan → implement → acceptance）。这是对 v1（`F:\claude\技能备份\E+S\`）的完全重写。

## 前代代码参考

v1 代码在 `F:\claude\技能备份\E+S\`，**仅作设计决策参考，禁止直接复制代码**。必须用 v2 的架构模式（CheckStrategy 接口、Stage ABC、frozen dataclass、EngineContext）重新表达。

Agent 知识文件副本在 `agents-src/`（14 个 agent 目录），v2 必须兼容这些 agent 的加载。

## 需求文档

- **当前需求**：`requirement-v2.md`（Phase 2 完成需求，包含 P0-P15 任务 + A1-A10 agent 适配 + LVL 证据链体系）
- 运行时问题：`runtime-issues.md`（R01-R23，23 条运行时经验）
- 踩坑记录：`pitfalls.md`（27 条 v1 踩坑）
- 旧需求（已废弃）：`requirement.md`（Phase 1 需求，仅供参考）

## Tech Stack

- Python 3.12+
- asyncio（异步 I/O）
- SQLite（状态持久化）
- Claude Agent SDK + CLI 降级
- GitHub Actions CI（可选，通过 CheckStrategy 切换）

## Architecture

```
orchestrator/
├── cli.py              # 入口
├── config.py           # 配置分层
├── engine.py           # 阶段流转（< 400 行）
├── stages/             # 四阶段具体逻辑
├── tdd/                # TDD 执行引擎
├── review/             # 审查 + 修复
├── checks/             # 测试策略（local/CI）
├── agents/             # Agent 注册 + 调用
├── store/              # SQLite 持久化
├── ui/                 # Wave 面板（可选）
└── defaults.yaml       # 全局默认配置
```

## Build & Test

```bash
# 本地无需安装额外依赖（纯 Python + Claude SDK）
python -m orchestrator run <project_path> --req-file <requirement.md>

# 测试
python -m pytest tests/ -v
```

## Coding Standards

参考文档（必读）：

- `reference/python-patterns.md` — Python 编码模式（类型标注、错误处理、不可变数据、函数式风格等）
- `reference/python-testing.md` — Python 测试规范（pytest、fixture、mock、覆盖率等）
- `pitfalls.md` — v1 编排器的 27 条踩坑记录（必读，避免重复犯错）
- `runtime-issues.md` — v2 构建期间发现的 23 条运行时问题（必读）

关键约束：
- 每个模块 < 450 行（400 行软约束 + 50 行波动）
- engine.py < 300 行
- 类型标注所有公开 API
- 无裸 except
- 不可变数据优先（frozen dataclass）
- 命名：模块小写下划线，类 PascalCase，方法动词开头
- 测试：pytest + fixture + 80%+ 覆盖率

## 设计文档索引

（由编排器 spec/plan 阶段自动生成到 `specs/` 目录）

## 设计文档索引
<!-- E+S:DOCS_INDEX -->

- [requirements.md](specs\checklists\requirements.md)
- [constitution.md](specs\constitution.md)
- [data-model.md](specs\data-model.md)
- [plan.md](specs\plan.md)
- [quickstart.md](specs\quickstart.md)
- [research.md](specs\research.md)
- [spec.md](specs\spec.md)
- [tasks.md](specs\tasks.md)
<!-- /E+S:DOCS_INDEX -->
