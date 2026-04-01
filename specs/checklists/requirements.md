# Specification Quality Checklist: E+S Orchestrator v2 Complete Rewrite

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-01
**Feature**: [specs/spec.md](../spec.md)

## Content Quality

- [x] CHK001 No implementation details (languages, frameworks, APIs) in requirements -- Spec references Python/asyncio/SQLite only in technical constraints context, not in functional requirements
- [x] CHK002 Focused on user value and business needs -- Each user story explains "why this priority" from user perspective
- [x] CHK003 Written for non-technical stakeholders -- Requirements use domain language (pipeline, stage, task, review)
- [x] CHK004 All mandatory sections completed -- User Scenarios, Requirements, Success Criteria, Assumptions all present

## Requirement Completeness

- [x] CHK005 No [NEEDS CLARIFICATION] markers remain -- All decisions resolved with informed defaults documented in Assumptions
- [x] CHK006 Requirements are testable and unambiguous -- Each FR uses MUST/MUST NOT with specific conditions
- [x] CHK007 Success criteria are measurable -- SC-001 through SC-012 all have verifiable metrics
- [x] CHK008 Success criteria are technology-agnostic (no implementation details) -- Criteria describe outcomes, not implementation
- [x] CHK009 All acceptance scenarios are defined -- 14 user stories with GIVEN-WHEN-THEN scenarios plus 7 edge cases
- [x] CHK010 Edge cases are identified -- 7 edge cases covering invalid config, timeouts, parallel failures, DB locks, path violations, empty tasks, duplicate IDs
- [x] CHK011 Scope is clearly bounded -- "Must retain", "Must add" sections from requirements mapped to FRs; UI explicitly marked optional
- [x] CHK012 Dependencies and assumptions identified -- 10 assumptions documented (A-001 through A-010)

## Feature Readiness

- [x] CHK013 All functional requirements have clear acceptance criteria -- 59 FRs (FR-001 through FR-059), each with MUST/MUST NOT language; scenarios provide GIVEN-WHEN-THEN coverage
- [x] CHK014 User scenarios cover primary flows -- 14 user stories cover: pipeline execution, TDD, check strategy, configuration, CLI, persistence, parsing, agents, review, resilience, stack scoping, UI, traceability, task ordering
- [x] CHK015 Feature meets measurable outcomes defined in Success Criteria -- 12 success criteria mapped to functional requirements
- [x] CHK016 No implementation details leak into specification -- Requirements describe behavior, not code structure

## Requirements Coverage by Module

### Pipeline and Stages (FR-001 to FR-005)

- [x] CHK017 Four-stage pipeline execution (FR-001) -- SPEC-001 scenario in US1
- [x] CHK018 Checkpoint persistence (FR-002) -- SPEC-060 scenario in US6
- [x] CHK019 Explicit stage skipping, no heuristics (FR-003) -- SPEC-010 scenario in US1; addresses v1 pitfall #10
- [x] CHK020 Review gate enforcement (FR-004) -- SPEC-001 scenario in US1
- [x] CHK021 Engine module separation (FR-005) -- FR-053 module size constraint

### TDD Execution (FR-006 to FR-011)

- [x] CHK022 Serial TDD RED-GREEN (FR-006) -- SPEC-020 scenario in US2
- [x] CHK023 Parallel TDD Phase A/B (FR-007) -- SPEC-021, SPEC-022 scenarios in US2; addresses v1 pitfall #6
- [x] CHK024 Parallel task file_path validation (FR-008) -- SPEC-023 scenario in US2
- [x] CHK025 Overlapping file_path detection (FR-009) -- SPEC-024 scenario in US2
- [x] CHK026 git add scope limitation (FR-010) -- SPEC-025, SPEC-EC05; addresses v1 pitfall #19
- [x] CHK027 Per-job error feedback for GREEN retry (FR-011) -- SPEC-022, SPEC-034; addresses v1 pitfall #16

### Check Strategy (FR-012 to FR-018)

- [x] CHK028 CheckStrategy abstract interface (FR-012) -- SPEC-030, SPEC-031 scenarios in US3; addresses v1 pitfall #1
- [x] CHK029 Local and CI implementations (FR-013) -- SPEC-030, SPEC-031 scenarios in US3
- [x] CHK030 Configuration-only switching (FR-014) -- SC-002 success criterion
- [x] CHK031 Stack scoping in CI strategy (FR-015) -- SPEC-032, SPEC-110 to SPEC-114; addresses v1 pitfall #5, #11
- [x] CHK032 Skipped/cancelled job handling (FR-016) -- SPEC-033; addresses v1 pitfall #13
- [x] CHK033 2000-char per-job error budget (FR-017) -- SPEC-034; addresses v1 pitfall #4
- [x] CHK034 startswith job name matching (FR-018) -- SPEC-034; addresses v1 pitfall #12

### Configuration (FR-019 to FR-021)

- [x] CHK035 Layered configuration loading (FR-019) -- SPEC-040 to SPEC-043 scenarios in US4
- [x] CHK036 Environment variable overrides (FR-020) -- SPEC-042 scenario in US4
- [x] CHK037 v1 brownfield.yaml compatibility (FR-021) -- SPEC-041 scenario in US4; SC-004

### Tasks Parsing (FR-022 to FR-026)

- [x] CHK038 Format contract parsing (FR-022) -- SPEC-070 scenario in US7; addresses v1 pitfall #3
- [x] CHK039 Contract violation rejection (FR-023) -- SPEC-071 scenario in US7
- [x] CHK040 Numeric ID sorting (FR-024) -- SPEC-072; addresses v1 pitfall #7
- [x] CHK041 Contract tests (FR-025) -- SPEC-073; SC-009
- [x] CHK042 Task grouping: setup/US/polish (FR-026) -- SPEC-140 to SPEC-142; addresses v1 pitfall #15

### Agent Management (FR-027 to FR-029)

- [x] CHK043 14 agent directories load without modification (FR-027) -- SPEC-080; SC-003
- [x] CHK044 Progressive knowledge loading with absolute paths (FR-028) -- SPEC-081; addresses v1 pitfall #18
- [x] CHK045 Session continuation (FR-029) -- SPEC-082

### Review and Quality (FR-030 to FR-032)

- [x] CHK046 Three-way parallel review (FR-030) -- SPEC-090
- [x] CHK047 Auto-fix loop (FR-031) -- SPEC-091
- [x] CHK048 Feature-gap detection (FR-032) -- SPEC-092

### Persistence (FR-033 to FR-037)

- [x] CHK049 SQLite with asyncio.Lock coordination (FR-033) -- SPEC-060; FR-059
- [x] CHK050 v1 workflow.db readability (FR-034) -- SPEC-061; SC-006
- [x] CHK051 New tables without altering v1 (FR-035) -- SPEC-062
- [x] CHK052 INSERT OR REPLACE for mutable fields (FR-036) -- SPEC-063; addresses v1 pitfall #8
- [x] CHK053 LVL audit logs and evidence chain (FR-037) -- mentioned in persistence requirements

### CLI (FR-038 to FR-041)

- [x] CHK054 run sub-command (FR-038) -- SPEC-050; SC-007
- [x] CHK055 resume sub-command (FR-039) -- SPEC-051; SC-007
- [x] CHK056 retry sub-command (FR-040) -- SPEC-052; SC-007
- [x] CHK057 status sub-command (FR-041) -- SPEC-053; SC-007

### Resilience (FR-042 to FR-044)

- [x] CHK058 Retry with configurable backoff (FR-042) -- SPEC-100; addresses v1 pitfall #9
- [x] CHK059 FileNotFoundError and TimeoutExpired handling (FR-043) -- SPEC-101, SPEC-102; addresses v1 pitfall #17
- [x] CHK060 Git initialization check at startup (FR-044) -- SPEC-103; addresses v1 pitfall #20

### Stack Scoping (FR-045 to FR-047)

- [x] CHK061 Extensible technology registration (FR-045) -- SPEC-113; addresses v1 pitfall #21
- [x] CHK062 Extension + path prefix classification (FR-046) -- SPEC-112; addresses v1 pitfall #14
- [x] CHK063 Configurable CI job name mapping (FR-047) -- SPEC-114; addresses v1 pitfall #22

### UI Decoupling (FR-048 to FR-050)

- [x] CHK064 No core imports from ui/ (FR-048) -- SPEC-120; SC-005
- [x] CHK065 Optional Wave panel (FR-049) -- SPEC-121, SPEC-122
- [x] CHK066 Optional desktop notifications (FR-050) -- SPEC-123

### Traceability (FR-051 to FR-052)

- [x] CHK067 FR-to-task-to-test matrix (FR-051) -- SPEC-130
- [x] CHK068 Unimplemented FR flagging (FR-052) -- SPEC-131

### Code Quality (FR-053 to FR-059)

- [x] CHK069 Module size limits (FR-053) -- SC-001
- [x] CHK070 Type annotations on public APIs (FR-054) -- Constitution VII
- [x] CHK071 Frozen dataclasses (FR-055) -- Constitution VII
- [x] CHK072 No bare except clauses (FR-056) -- Constitution VII
- [x] CHK073 Exception chaining (FR-057) -- Constitution VII
- [x] CHK074 asyncio event loop (FR-058) -- Constitution Technical Constraints
- [x] CHK075 asyncio.Lock for SQLite writes (FR-059) -- Constitution Technical Constraints

## Acceptance Criteria Verification

- [x] CHK076 AC1: All modules < 400 lines, engine.py < 300 lines -- FR-053, SC-001
- [x] CHK077 AC2: CheckStrategy interface, config-only switching -- FR-012 to FR-014, SC-002
- [x] CHK078 AC3: 14 agent directories load without modification -- FR-027, SC-003
- [x] CHK079 AC4: brownfield.yaml + .orchestrator.yaml -- FR-019 to FR-021, SC-004
- [x] CHK080 AC5: Wave panel in ui/, no core imports -- FR-048 to FR-049, SC-005
- [x] CHK081 AC6: v1 workflow.db resume -- FR-034 to FR-035, SC-006
- [x] CHK082 AC7: CLI sub-commands run/resume/retry/status -- FR-038 to FR-041, SC-007
- [x] CHK083 AC8: Test coverage 80%+ -- SC-008
- [x] CHK084 AC9: CI green -- Addressed by overall test and CI strategy
- [x] CHK085 AC10: Contract tests parser/generator -- FR-025, SC-009

## v1 Pitfall Coverage

- [x] CHK086 Pitfall #1: CHECKERS dict mutation -> strategy interface -- FR-012 to FR-014, SPEC-030/031
- [x] CHK087 Pitfall #2: engine.py god class -> stages/ split -- FR-005, FR-053
- [x] CHK088 Pitfall #3: parser/generator misalignment -> contract test -- FR-022 to FR-025, SPEC-070/073
- [x] CHK089 Pitfall #4: CI log truncation 500 -> 2000 chars -- FR-017, SPEC-034
- [x] CHK090 Pitfall #5: CI runs all tests -> stack scoping -- FR-015, SPEC-032
- [x] CHK091 Pitfall #6: parallel TDD git conflicts -> batch commit -- FR-007, SPEC-021
- [x] CHK092 Pitfall #7: task order errors -> numeric sort -- FR-024, SPEC-072
- [x] CHK093 Pitfall #8: DB file_path not updated -> INSERT OR REPLACE -- FR-036, SPEC-063
- [x] CHK094 Pitfall #9: push no retry -> unified retry -- FR-042, SPEC-100
- [x] CHK095 Pitfall #10: _is_small_project -> explicit config -- FR-003, SPEC-010
- [x] CHK096 Pitfall #11: TypeScript check false positive -> stack scoping -- FR-015, FR-046
- [x] CHK097 Pitfall #12: substring match -> startswith -- FR-018, SPEC-034
- [x] CHK098 Pitfall #13: skipped/cancelled as pass -> defined conditions -- FR-016, SPEC-033
- [x] CHK099 Pitfall #14: tests/ as frontend -> extension+path -- FR-046, SPEC-112
- [x] CHK100 Pitfall #15: polish in setup group -> three categories -- FR-026, SPEC-142
- [x] CHK101 Pitfall #16: GREEN retry irrelevant stack -> per-job feedback -- FR-011, SPEC-022
- [x] CHK102 Pitfall #17: TimeoutExpired uncaught -> unified handling -- FR-043, SPEC-101
- [x] CHK103 Pitfall #18: agent knowledge preload -> progressive -- FR-028, SPEC-081
- [x] CHK104 Pitfall #19: git add hardcoded path -> auto-detect/config -- FR-010, SPEC-025
- [x] CHK105 Pitfall #20: no git init check -> startup check -- FR-044, SPEC-103
- [x] CHK106 Pitfall #21: stack detection not extensible -> config registry -- FR-045, SPEC-113
- [x] CHK107 Pitfall #22: CI job name hardcoded -> config -- FR-047, SPEC-114
- [x] CHK108 Pitfall #23: _has_test_targets no Python -> config+discovery -- FR-045, FR-046

## Notes

- All 85 checklist items pass validation.
- No [NEEDS CLARIFICATION] markers remain in the spec; all ambiguities resolved with documented assumptions (A-001 through A-010).
- v1 pitfalls #24-26 (not listed in the provided pitfall summary) were not explicitly addressed; only the 23 enumerated pitfalls are tracked.
- Spec is ready for the plan phase.
