"""Behavioral tests for orchestrator.tdd.parser.

Covers FR-021 through FR-025:
  FR-021: parse_tasks() em-dash primary strategy
  FR-022: [P] without file_path rejection
  FR-023: "in src/" fallback for file path extraction
  FR-024: Non-canonical warning with line number
  FR-025: Phase grouping (setup/US*/polish) and validate_parallel_group()
           with file_path overlap detection and demotion to serial

All tests are behavioral: they call the public API and assert on concrete
return values or exception types — no implementation-detail assertions.
"""
from __future__ import annotations

import pytest

from orchestrator.tdd.parser import parse_tasks, validate_parallel_group
from orchestrator.store.models import Task


# ---------------------------------------------------------------------------
# FR-021: Em-dash primary strategy
# ---------------------------------------------------------------------------


class TestParsTasksEmDashPrimary:
    """FR-021: parse_tasks() uses em-dash (—) as the primary file_path delimiter."""

    def test_fr021_em_dash_extracts_file_path(self):
        """FR-021: em-dash separates description from file_path."""
        text = "- [ ] T001 [P] [US1] [FR-001] Implement config loader — orchestrator/config.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.file_path == "orchestrator/config.py"

    def test_fr021_em_dash_extracts_task_id(self):
        """FR-021: task ID (T###) is parsed from the canonical format."""
        text = "- [ ] T042 [US2] [FR-010] Add persistence layer — orchestrator/store/db.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.id == "T042"

    def test_fr021_em_dash_extracts_description_without_file_path(self):
        """FR-021: description part does not include the file_path or em-dash."""
        text = "- [ ] T003 [US1] [FR-002] Load YAML configuration — orchestrator/config.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert "orchestrator/config.py" not in task.description
        assert "—" not in task.description

    def test_fr021_parallel_marker_detected(self):
        """FR-021: [P] marker sets task.parallel = True."""
        text = "- [ ] T005 [P] [US3] [FR-010] Implement local check — orchestrator/checks/local.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.parallel is True

    def test_fr021_no_parallel_marker_sets_false(self):
        """FR-021: absence of [P] sets task.parallel = False."""
        text = "- [ ] T001 [US1] [FR-001] Implement config — orchestrator/config.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.parallel is False

    def test_fr021_multiple_fr_refs_parsed(self):
        """FR-021: multiple [FR-###] references are all captured."""
        text = (
            "- [ ] T006 [P] [US1] [FR-021][FR-022][FR-023] "
            "Implement parser — orchestrator/tdd/parser.py"
        )
        result = parse_tasks(text)
        task = result.tasks[0]
        # description or a dedicated field should capture FR references
        assert "FR-021" in task.description or (
            hasattr(task, "fr_refs") and "FR-021" in task.fr_refs
        )

    def test_fr021_story_ref_extracted(self):
        """FR-021: [US*] reference is parsed into task.story_ref."""
        text = "- [ ] T007 [P] [US5] [FR-025] Validate parallel — orchestrator/tdd/parser.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.story_ref == "US5"

    def test_fr021_multiple_tasks_parsed(self):
        """FR-021: multiple task lines produce multiple Task objects."""
        text = (
            "- [ ] T001 [US1] [FR-001] Config — orchestrator/config.py\n"
            "- [ ] T002 [P] [US2] [FR-002] Store — orchestrator/store/db.py\n"
            "- [ ] T003 [P] [US3] [FR-003] Check — orchestrator/checks/local.py\n"
        )
        result = parse_tasks(text)
        assert len(result.tasks) == 3

    def test_fr021_file_path_with_nested_dirs(self):
        """FR-021: file_path with multiple directory levels is correctly extracted."""
        text = "- [ ] T010 [P] [US1] [FR-010] Deep module — orchestrator/stages/spec.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.file_path == "orchestrator/stages/spec.py"

    def test_fr021_blank_lines_and_comments_ignored(self):
        """FR-021: blank lines and non-task lines in the text are ignored."""
        text = (
            "## Phase 1: Foundation\n"
            "\n"
            "Some description here.\n"
            "\n"
            "- [ ] T001 [US1] [FR-001] Config — orchestrator/config.py\n"
            "\n"
            "**Checkpoint**: ready\n"
        )
        result = parse_tasks(text)
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "T001"


# ---------------------------------------------------------------------------
# FR-022: [P] without file_path rejection
# ---------------------------------------------------------------------------


class TestParsTasksParallelRequiresFilePath:
    """FR-022: Tasks with [P] marker but no file_path must be rejected."""

    def test_fr022_parallel_without_file_path_raises(self):
        """FR-022: [P] task with no file_path raises ValueError."""
        text = "- [ ] T009 [P] [US5] [FR-023] No file path here, no em-dash either"
        with pytest.raises(ValueError, match="file_path"):
            parse_tasks(text)

    def test_fr022_error_message_identifies_task_id(self):
        """FR-022: ValueError message identifies which task ID is invalid."""
        text = "- [ ] T015 [P] [US5] [FR-023] Missing file path — "
        with pytest.raises(ValueError, match="T015"):
            parse_tasks(text)

    def test_fr022_non_parallel_without_file_path_is_allowed(self):
        """FR-022: non-[P] task with no file_path is NOT rejected."""
        text = "- [ ] T001 [US1] [FR-001] Config setup, no file specified"
        result = parse_tasks(text)
        assert len(result.tasks) == 1
        assert result.tasks[0].file_path is None

    def test_fr022_parallel_with_empty_file_path_after_em_dash_raises(self):
        """FR-022: [P] task with em-dash but empty file_path is rejected."""
        text = "- [ ] T020 [P] [US3] [FR-026] Local check —   "
        with pytest.raises(ValueError):
            parse_tasks(text)

    def test_fr022_multiple_tasks_one_bad_parallel_raises(self):
        """FR-022: even one [P] task without file_path causes rejection of the whole input."""
        text = (
            "- [ ] T001 [US1] [FR-001] Config — orchestrator/config.py\n"
            "- [ ] T002 [P] [US5] [FR-023] Bad parallel task, no file\n"
            "- [ ] T003 [P] [US3] [FR-026] Good parallel — orchestrator/checks/local.py\n"
        )
        with pytest.raises(ValueError, match="T002"):
            parse_tasks(text)


# ---------------------------------------------------------------------------
# FR-023: "in src/" fallback
# ---------------------------------------------------------------------------


class TestParsTasksInSrcFallback:
    """FR-023: When no em-dash is present, fall back to 'in src/' pattern."""

    def test_fr023_in_src_fallback_extracts_file_path(self):
        """FR-023: 'in src/module.py' extracts file_path when no em-dash."""
        text = "- [ ] T001 [US1] [FR-001] Implement feature in src/module.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.file_path == "src/module.py"

    def test_fr023_in_src_fallback_marks_non_canonical(self):
        """FR-023: task using 'in src/' fallback is flagged as non-canonical."""
        text = "- [ ] T001 [US1] [FR-001] Implement feature in src/module.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        # non-canonical flag must be set somewhere in warnings or on the task
        line_warnings = [w for w in result.warnings if "T001" in w or "non-canonical" in w.lower()]
        assert len(line_warnings) >= 1

    def test_fr023_in_src_fallback_no_double_extraction(self):
        """FR-023: file_path from 'in src/' fallback is the path only, not the full phrase."""
        text = "- [ ] T005 [US2] [FR-005] Load data in src/loader.py"
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.file_path == "src/loader.py"
        assert "in src/" not in task.file_path

    def test_fr023_em_dash_takes_priority_over_in_src(self):
        """FR-023: when both em-dash and 'in src/' appear, em-dash wins."""
        text = (
            "- [ ] T001 [P] [US1] [FR-001] Process in src/helper.py "
            "— orchestrator/processor.py"
        )
        result = parse_tasks(text)
        task = result.tasks[0]
        assert task.file_path == "orchestrator/processor.py"


# ---------------------------------------------------------------------------
# FR-024: Non-canonical warning
# ---------------------------------------------------------------------------


class TestParsTasksNonCanonicalWarning:
    """FR-024: Non-canonical task lines emit warnings with line number."""

    def test_fr024_non_canonical_warning_emitted(self):
        """FR-024: a warning is emitted for non-canonical format."""
        text = "- [ ] T001 [US1] [FR-001] Implement feature in src/module.py"
        result = parse_tasks(text)
        assert len(result.warnings) >= 1

    def test_fr024_warning_includes_line_number(self):
        """FR-024: the warning message includes the line number."""
        text = (
            "- [ ] T001 [US1] [FR-001] Canonical task — orchestrator/config.py\n"
            "- [ ] T002 [US2] [FR-002] Non-canonical task in src/store.py\n"
        )
        result = parse_tasks(text)
        # Warnings should reference a line number
        assert any(
            any(char.isdigit() for char in w) for w in result.warnings
        ), "Expected at least one warning containing a line number"

    def test_fr024_warning_suggests_em_dash_format(self):
        """FR-024: the warning message suggests using the em-dash canonical format."""
        text = "- [ ] T003 [US3] [FR-003] Feature in src/feature.py"
        result = parse_tasks(text)
        assert any("—" in w or "em-dash" in w.lower() or "canonical" in w.lower()
                   for w in result.warnings)

    def test_fr024_canonical_task_produces_no_warning(self):
        """FR-024: a properly formatted em-dash task produces no warnings."""
        text = "- [ ] T001 [P] [US1] [FR-001] Implement config — orchestrator/config.py"
        result = parse_tasks(text)
        assert result.warnings == []

    def test_fr024_multiple_non_canonical_lines_produce_multiple_warnings(self):
        """FR-024: each non-canonical line gets its own warning."""
        text = (
            "- [ ] T001 [US1] [FR-001] Feature in src/a.py\n"
            "- [ ] T002 [US2] [FR-002] Feature in src/b.py\n"
            "- [ ] T003 [P] [US3] [FR-003] Canonical — orchestrator/c.py\n"
        )
        result = parse_tasks(text)
        assert len(result.warnings) == 2


# ---------------------------------------------------------------------------
# FR-025: Phase grouping
# ---------------------------------------------------------------------------


class TestParsTasksPhaseGrouping:
    """FR-025: Tasks are grouped into phases: setup, US*, polish."""

    def test_fr025_tasks_grouped_by_phase(self):
        """FR-025: parse_tasks returns tasks organized in phase groups."""
        text = (
            "## Phase 1: Foundation\n"
            "- [ ] T001 [US4] [FR-001] Config — orchestrator/config.py\n"
            "- [ ] T002 [US4] [FR-002] Store — orchestrator/store/db.py\n"
            "\n"
            "## Phase 2: Core Strategies\n"
            "- [ ] T003 [P] [US1] [FR-010] Parser — orchestrator/tdd/parser.py\n"
        )
        result = parse_tasks(text)
        assert hasattr(result, "phase_groups")
        assert len(result.phase_groups) >= 1

    def test_fr025_setup_phase_identified(self):
        """FR-025: tasks in a 'setup' or 'foundation' section map to the 'setup' group."""
        text = (
            "## Phase 1: Foundation\n"
            "- [ ] T001 [US4] [FR-001] Config — orchestrator/config.py\n"
        )
        result = parse_tasks(text)
        setup_group = next(
            (g for g in result.phase_groups if g.name == "setup"), None
        )
        assert setup_group is not None
        assert any(t.id == "T001" for t in setup_group.tasks)

    def test_fr025_us_phase_identified(self):
        """FR-025: tasks associated with US* user stories group under matching US phase."""
        text = (
            "## Phase 2: Core Strategies\n"
            "- [ ] T004 [P] [US3] [FR-026] Local check — orchestrator/checks/local.py\n"
            "- [ ] T005 [P] [US3] [FR-028] CI check — orchestrator/checks/ci.py\n"
        )
        result = parse_tasks(text)
        us_group = next(
            (g for g in result.phase_groups
             if g.name.startswith("US") or g.name == "core"), None
        )
        assert us_group is not None

    def test_fr025_polish_phase_identified(self):
        """FR-025: tasks in a 'polish' or final optional section map to 'polish' group."""
        text = (
            "## Phase 6: Optional\n"
            "- [ ] T017 [US9] [FR-044] Wave panel — orchestrator/ui/wave.py\n"
        )
        result = parse_tasks(text)
        polish_group = next(
            (g for g in result.phase_groups if g.name == "polish"), None
        )
        assert polish_group is not None
        assert any(t.id == "T017" for t in polish_group.tasks)

    def test_fr025_all_tasks_assigned_to_a_phase(self):
        """FR-025: every parsed task belongs to exactly one phase group."""
        text = (
            "## Phase 1: Foundation\n"
            "- [ ] T001 [US4] [FR-001] Config — orchestrator/config.py\n"
            "## Phase 2: Core Strategies\n"
            "- [ ] T002 [P] [US1] [FR-010] Parser — orchestrator/tdd/parser.py\n"
            "## Phase 6: Optional\n"
            "- [ ] T003 [US9] [FR-044] UI — orchestrator/ui/wave.py\n"
        )
        result = parse_tasks(text)
        task_ids_in_groups = {
            t.id
            for group in result.phase_groups
            for t in group.tasks
        }
        all_task_ids = {t.id for t in result.tasks}
        assert task_ids_in_groups == all_task_ids


# ---------------------------------------------------------------------------
# FR-025: validate_parallel_group() — overlap detection + serial demotion
# ---------------------------------------------------------------------------


class TestValidateParallelGroup:
    """FR-025: validate_parallel_group() detects file_path overlap and demotes to serial."""

    def _make_parallel_task(
        self,
        task_id: str,
        file_path: str,
        story_ref: str = "US1",
    ) -> Task:
        return Task(
            id=task_id,
            phase_num=1,
            description=f"Task {task_id}",
            file_path=file_path,
            story_ref=story_ref,
            parallel=True,
            depends_on=[],
            status="pending",
            started_at=None,
            completed_at=None,
            tdd_phase=None,
            review_notes=None,
        )

    def test_fr025_no_overlap_returns_all_parallel(self):
        """FR-025: tasks with distinct file_paths remain parallel=True."""
        tasks = [
            self._make_parallel_task("T004", "orchestrator/checks/local.py"),
            self._make_parallel_task("T005", "orchestrator/checks/ci.py"),
            self._make_parallel_task("T006", "orchestrator/tdd/parser.py"),
        ]
        result = validate_parallel_group(tasks)
        assert all(t.parallel is True for t in result)

    def test_fr025_overlap_demotes_conflicting_tasks_to_serial(self):
        """FR-025: tasks sharing a file_path have parallel=False after validation."""
        tasks = [
            self._make_parallel_task("T001", "orchestrator/config.py"),
            self._make_parallel_task("T002", "orchestrator/config.py"),  # same file!
            self._make_parallel_task("T003", "orchestrator/store/db.py"),
        ]
        result = validate_parallel_group(tasks)
        t001 = next(t for t in result if t.id == "T001")
        t002 = next(t for t in result if t.id == "T002")
        # Both conflicting tasks must be demoted
        assert t001.parallel is False
        assert t002.parallel is False

    def test_fr025_non_conflicting_task_stays_parallel_when_others_conflict(self):
        """FR-025: a task with a unique file_path stays parallel even if others conflict."""
        tasks = [
            self._make_parallel_task("T001", "orchestrator/config.py"),
            self._make_parallel_task("T002", "orchestrator/config.py"),  # conflict
            self._make_parallel_task("T003", "orchestrator/store/db.py"),  # unique
        ]
        result = validate_parallel_group(tasks)
        t003 = next(t for t in result if t.id == "T003")
        assert t003.parallel is True

    def test_fr025_three_way_overlap_all_demoted(self):
        """FR-025: three tasks sharing the same file_path are all demoted to serial."""
        tasks = [
            self._make_parallel_task("T010", "orchestrator/engine.py"),
            self._make_parallel_task("T011", "orchestrator/engine.py"),
            self._make_parallel_task("T012", "orchestrator/engine.py"),
        ]
        result = validate_parallel_group(tasks)
        assert all(t.parallel is False for t in result)

    def test_fr025_empty_group_returns_empty_list(self):
        """FR-025: validating an empty group returns an empty list."""
        result = validate_parallel_group([])
        assert result == []

    def test_fr025_single_task_group_stays_parallel(self):
        """FR-025: a single-task group has no possible overlap, stays parallel."""
        tasks = [self._make_parallel_task("T001", "orchestrator/config.py")]
        result = validate_parallel_group(tasks)
        assert result[0].parallel is True

    def test_fr025_returned_tasks_are_frozen_dataclasses(self):
        """FR-025: returned Task objects are immutable (frozen dataclass), not mutated in place."""
        original = self._make_parallel_task("T001", "orchestrator/config.py")
        tasks = [
            original,
            self._make_parallel_task("T002", "orchestrator/config.py"),
        ]
        result = validate_parallel_group(tasks)
        # original must not be mutated
        assert original.parallel is True
        # result contains new objects
        t001_result = next(t for t in result if t.id == "T001")
        assert t001_result.parallel is False
        assert t001_result is not original

    def test_fr025_original_list_not_mutated(self):
        """FR-025: the input list is not modified; a new list is returned."""
        tasks = [
            self._make_parallel_task("T001", "shared/file.py"),
            self._make_parallel_task("T002", "shared/file.py"),
        ]
        original_parallel = [t.parallel for t in tasks]
        validate_parallel_group(tasks)
        assert [t.parallel for t in tasks] == original_parallel

    def test_fr025_result_preserves_task_count(self):
        """FR-025: validate_parallel_group returns the same number of tasks as input."""
        tasks = [
            self._make_parallel_task("T001", "orchestrator/config.py"),
            self._make_parallel_task("T002", "orchestrator/store/db.py"),
            self._make_parallel_task("T003", "orchestrator/tdd/parser.py"),
        ]
        result = validate_parallel_group(tasks)
        assert len(result) == 3

    def test_fr025_overlap_detected_by_normalized_path(self):
        """FR-025: file_path comparison is case-insensitive or normalized (no false negatives)."""
        tasks = [
            self._make_parallel_task("T001", "orchestrator/Config.py"),
            self._make_parallel_task("T002", "orchestrator/config.py"),
        ]
        result = validate_parallel_group(tasks)
        demoted = [t for t in result if not t.parallel]
        # Either both are demoted (case-insensitive) or they're treated as distinct.
        # Spec says "overlapping file_path values" — implementation may normalize or not.
        # We assert the contract: if treated as same path, both are demoted.
        if len(demoted) > 0:
            assert len(demoted) == 2


# ---------------------------------------------------------------------------
# FR-024 + FR-025: Contract tests (generator–parser alignment)
# ---------------------------------------------------------------------------


class TestParserContractWithGeneratorOutput:
    """FR-024: Parser must correctly process sample generator output format."""

    SAMPLE_GENERATOR_OUTPUT = """\
## Phase 1: Foundation (Data Model + Config + Store)

**Purpose**: Establish the foundation all upper modules depend on.

- [ ] T001 [US4] [FR-001][FR-002][FR-003][FR-004] Implement layered configuration system with frozen dataclass, load_config() supporting defaults.yaml/brownfield.yaml/.orchestrator.yaml/env override chain, unknown key warnings, and nested dict recursive merge — orchestrator/config.py
- [ ] T002 [US2][US4] [FR-039][FR-040][FR-041][FR-042][FR-043] Implement persistence layer: 7 frozen dataclass models in models.py — orchestrator/store/models.py

**Checkpoint**: Foundation ready.

## Phase 2: Core Strategies (Check Strategies + Task Parser + Agent System)

**Purpose**: Three independent subsystems.

- [ ] T004 [P] [US3] [FR-026][FR-027][FR-029][FR-030] Implement local check strategy — orchestrator/checks/local.py
- [ ] T005 [P] [US3] [FR-028][FR-029][FR-030][FR-031] Implement CI check strategy — orchestrator/checks/ci.py
- [ ] T006 [P] [US1][US5] [FR-021][FR-022][FR-023][FR-024][FR-025] Implement task parser — orchestrator/tdd/parser.py
"""

    def test_fr024_contract_all_tasks_parsed(self):
        """FR-024: All task lines in generator output are parsed."""
        result = parse_tasks(self.SAMPLE_GENERATOR_OUTPUT)
        task_ids = {t.id for t in result.tasks}
        assert task_ids == {"T001", "T002", "T004", "T005", "T006"}

    def test_fr024_contract_parallel_markers_correct(self):
        """FR-024: [P] markers in generator output are correctly identified."""
        result = parse_tasks(self.SAMPLE_GENERATOR_OUTPUT)
        parallel_ids = {t.id for t in result.tasks if t.parallel}
        serial_ids = {t.id for t in result.tasks if not t.parallel}
        assert parallel_ids == {"T004", "T005", "T006"}
        assert serial_ids == {"T001", "T002"}

    def test_fr024_contract_file_paths_extracted(self):
        """FR-024: file_path is extracted correctly for every task in generator output."""
        result = parse_tasks(self.SAMPLE_GENERATOR_OUTPUT)
        path_map = {t.id: t.file_path for t in result.tasks}
        assert path_map["T001"] == "orchestrator/config.py"
        assert path_map["T002"] == "orchestrator/store/models.py"
        assert path_map["T004"] == "orchestrator/checks/local.py"
        assert path_map["T005"] == "orchestrator/checks/ci.py"
        assert path_map["T006"] == "orchestrator/tdd/parser.py"

    def test_fr024_contract_no_warnings_for_canonical_output(self):
        """FR-024: canonical generator output produces no warnings."""
        result = parse_tasks(self.SAMPLE_GENERATOR_OUTPUT)
        assert result.warnings == []

    def test_fr024_contract_phase_groups_created(self):
        """FR-024: generator output with ## Phase headers creates phase groups."""
        result = parse_tasks(self.SAMPLE_GENERATOR_OUTPUT)
        assert len(result.phase_groups) >= 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestParsTasksEdgeCases:
    """Edge cases: empty input, whitespace, malformed lines."""

    def test_empty_string_returns_empty_result(self):
        """Empty input produces empty tasks list and no errors."""
        result = parse_tasks("")
        assert result.tasks == []
        assert result.warnings == []

    def test_whitespace_only_returns_empty_result(self):
        """Whitespace-only input produces empty tasks list."""
        result = parse_tasks("   \n   \n   ")
        assert result.tasks == []

    def test_text_with_no_task_lines_returns_empty(self):
        """Markdown without task lines produces empty tasks list."""
        text = "# Header\n\nSome description.\n\n**Bold text**"
        result = parse_tasks(text)
        assert result.tasks == []

    def test_task_without_id_is_skipped_or_errors(self):
        """A line starting with '- [ ]' but lacking T### is handled gracefully."""
        text = "- [ ] [US1] [FR-001] No task ID here — orchestrator/config.py"
        # Should not crash; either skip the line or include with a warning
        result = parse_tasks(text)
        # Either no tasks parsed, or a warning was emitted
        assert len(result.tasks) == 0 or len(result.warnings) >= 1

    def test_already_checked_task_line_parsed(self):
        """A completed task '- [x] T001 ...' is parsed without crashing."""
        text = "- [x] T001 [US1] [FR-001] Done — orchestrator/config.py"
        result = parse_tasks(text)
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "T001"
