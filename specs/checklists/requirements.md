# Specification Quality Checklist: E+S Orchestrator v2

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-02
**Feature**: [specs/spec.md](../spec.md)

## Content Quality

- [x] CHK001 No implementation details (languages, frameworks, APIs) in requirements
- [x] CHK002 Focused on user value and business needs
- [x] CHK003 Written for non-technical stakeholders
- [x] CHK004 All mandatory sections completed (User Scenarios, Requirements, Success Criteria)

## Requirement Completeness

- [x] CHK005 No [NEEDS CLARIFICATION] markers remain
- [x] CHK006 Requirements are testable and unambiguous
- [x] CHK007 Success criteria are measurable
- [x] CHK008 Success criteria are technology-agnostic (no implementation details)
- [x] CHK009 All acceptance scenarios are defined
- [x] CHK010 Edge cases are identified
- [x] CHK011 Scope is clearly bounded
- [x] CHK012 Dependencies and assumptions identified

## Feature Readiness

- [x] CHK013 All functional requirements have clear acceptance criteria (via GIVEN-WHEN-THEN scenarios)
- [x] CHK014 User scenarios cover primary flows
- [x] CHK015 Feature meets measurable outcomes defined in Success Criteria
- [x] CHK016 No implementation details leak into specification

## Requirement Traceability

| 需求ID | 需求描述 | 关联规格 | 状态 |
|---------|----------|----------|------|
| P0-A | SessionManager 扩展 (expire_session, list_sessions, session 续接) | FR-001, FR-002 | Covered |
| P0-B1 | EngineContext frozen dataclass (< 50 行) | FR-003, FR-004 | Covered |
| P0-B2 | CheckStrategy 异步化 (CheckResult) | FR-005, FR-006 | Covered |
| P0-B3 | stages/base.py 补充 (_run_agent, _check_output, ctx) | FR-007 | Covered |
| P0-C | checks/ci.py CI 策略 (commit_and_push, detect_stack, job 映射) | FR-008, FR-009, FR-010, FR-011, FR-012 | Covered |
| P0-D | review/pipeline.py 三路审查 | FR-013, FR-014, FR-015 | Covered |
| P0-E | 14 个 agent 注册配置 | FR-016 | Covered |
| P1 | stages/plan.py (plan → research → tasks → review) | FR-020, FR-021, FR-024, FR-025 | Covered |
| P2 | stages/implement.py (TDD + review + fix + feature-gap) | FR-026, FR-027, FR-028, FR-029, FR-030, FR-031 | Covered |
| P3 | tdd/runner.py (RED-GREEN, batch commit, convergence) | FR-032, FR-033, FR-034, FR-035, FR-036, FR-037, FR-038, FR-039 | Covered |
| P4 | checks/common.py (file_exists, coverage_above 等) | FR-040, FR-041 | Covered |
| P5 | engine.py (resume, retry, status, 进程锁) | FR-042, FR-043, FR-044, FR-045, FR-046 | Covered |
| P6 | 集成测试 | FR-047 | Covered |
| P7 | launch.py Wave 面板 | FR-048 | Covered |
| P8 | stages/acceptance.py (acceptor + traceability matrix) | FR-049, FR-050, FR-051 | Covered |
| P9 | cli.py 子命令 (run/resume/retry/status) | FR-052 | Covered |
| P10 | stages/spec.py (constitution → specify → clarify → review) | FR-017, FR-018, FR-019 | Covered |
| P11 | store/lvl.py (append_event, verify_chain 等) | FR-053, FR-054 | Covered |
| P12 | store/artifacts.py (register, freeze, staleness, cascade) | FR-055, FR-056 | Covered |
| P13 | store/models.py (ArtifactRecord, LvlEventRecord) | FR-057 | Covered |
| P14 | store/_schema.py (schema_version=3) | FR-058 | Covered |
| P15 | monitor.py (规则驱动, Observation, 写入 lvl_events) | FR-063, FR-064, FR-065, FR-066, FR-067 | Covered |
| A1 | tdd-guide RED prompt 适应 | FR-068 | Covered |
| A2 | task-generator CI 预估规则 | FR-069 | Covered |
| A6 | fixer 依赖感知 | FR-070 | Covered |
| A7 | implementer GREEN prompt 适应 | FR-071 | Covered |
| A8 | acceptor 结构化输出 | FR-072 | Covered |
| A9 | spec-writer [NC:] 触发标记 | FR-073 | Covered |
| A10 | planner [NR:] 触发标记 | FR-074 | Covered |
| C1 | defaults.yaml 更新 (timeout 配置) | FR-075 | Covered |
| C2 | CI workflow 适配 | FR-076 | Covered |
| C3 | agents-src 相对路径 | FR-077 | Covered |
| R01 | 启动检测 .git | FR-078 | Covered |
| R02 | git add 自动检测目录 | FR-079 | Covered |
| R03-R05 | stack 检测支持 python | FR-080 | Covered |
| R06 | RED prompt "只写测试" | FR-081 | Covered |
| R07 | 环境问题区分 | FR-082 | Covered |
| R08 | 环境问题额外重试 | FR-083 | Covered |
| R09 | 已完成 task 跳过 | FR-084 | Covered |
| R12 | implement 用 global_timeout | FR-085 | Covered |
| R21 | severity 正则兼容加粗 | FR-086 | Covered |
| C-1 | LLM 路径白名单校验 | FR-087 | Covered |
| C-2 | Windows shell=True 用 list2cmdline | FR-088 | Covered |
| C-3 | SQLite 写入 threading.Lock | FR-089 | Covered |
| H-1/H-2 | CI 检查用 asyncio.to_thread | FR-090 | Covered |
| H-4 | 密钥检查在 stage_project_files 后 | FR-091 | Covered |
| INV-1 | 阶段完成不变量 | FR-059 | Covered |
| INV-2 | 阶段启动不变量 | FR-060 | Covered |
| INV-3 | 事件链不变量 | FR-061 | Covered |
| INV-4 | RED-before-GREEN 不变量 | FR-062 | Covered |
| Clarify | 智能条件触发 (双向: agent 自报 + 编排器检测) | FR-018, FR-022 | Covered |
| Research | 智能条件触发 (双向: agent 自报 + 编排器检测) | FR-021, FR-023 | Covered |
| BLOCKED-单 | 单 task BLOCKED → 跳过继续 | FR-026 (User Story 5) | Covered |
| BLOCKED-多 | 多 task BLOCKED → 暂停回退 | FR-063, FR-065 (User Story 5) | Covered |
| BLOCKED-阶段 | 阶段 BLOCKED → 人工干预/降级 | User Story 5 | Covered |

## Notes

- All 91 functional requirements (FR-001 through FR-091) are mapped to source requirements
- All checklist items pass validation; spec is ready for the plan phase
- No [NEEDS CLARIFICATION] markers remain; all ambiguities resolved via assumptions
- R10, R11, R13-R20, R22-R23 are not explicitly listed in the requirement document's detail sections; they are assumed to be covered by the general runtime constraints or not applicable to this version
- H-3 (if it exists) and H-5 are not mentioned in the source requirements; M-8 is not referenced in the provided requirement text
- Agent count: the requirement lists 14 agents by name, with tdd-guide appearing once; the 14th agent identity is assumed per the Assumptions section
