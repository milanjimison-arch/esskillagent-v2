# E+S Orchestrator v2

## Project Overview

E+S Orchestrator v2 是一个 Python 编排器，管理 AI agent 执行四阶段 TDD 工作流（spec → plan → implement → acceptance）。这是对 v1（`F:\claude\技能备份\E+S\`）的完全重写。

## 前代代码参考

v1 代码在 `F:\claude\技能备份\E+S\`，可参考其设计决策和实现模式，但不要直接复制。已知 bug 和设计缺陷已在 `requirement.md` 中列出。

Agent 知识文件在 `F:\claude\技能备份\ESSKILLAGENT\`（14 个 agent 目录），v2 必须兼容这些 agent 的加载。

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
├── engine.py           # 阶段流转（< 200 行）
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
- `pitfalls.md` — v1 编排器的 26 条踩坑记录（必读，避免重复犯错）

关键约束：
- 每个模块 < 400 行
- engine.py < 200 行
- 类型标注所有公开 API
- 无裸 except
- 不可变数据优先（frozen dataclass）
- 命名：模块小写下划线，类 PascalCase，方法动词开头
- 测试：pytest + fixture + 80%+ 覆盖率

## 设计文档索引

（由编排器 spec/plan 阶段自动生成到 `specs/` 目录）
