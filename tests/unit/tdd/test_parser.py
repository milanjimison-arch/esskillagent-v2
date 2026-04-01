"""Unit tests for orchestrator/tdd/parser.py — tasks.md parser.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/tdd/parser.py provides a complete implementation.

Requirements covered:
  FR-PARSER-01: Strict em-dash (—) format validation.
  FR-PARSER-02: Numeric sort of parsed tasks by task_id.
  FR-PARSER-03: [P] tasks without file_path are accepted; [S]/[US*] without
                file_path are rejected.
  FR-PARSER-04: Task grouping into setup / us / polish categories.

Test areas:
  1.  parse_line: happy-path [S] tag with file_path.
  2.  parse_line: happy-path [US1] tag with file_path.
  3.  parse_line: happy-path [P] tag without file_path (accepted).
  4.  parse_line: happy-path [P] tag with file_path (accepted).
  5.  parse_line: [S] tag missing file_path raises TaskParseError.
  6.  parse_line: [US2] tag missing file_path raises TaskParseError.
  7.  parse_line: hyphen (-) instead of em-dash raises TaskParseError.
  8.  parse_line: mixed separator (em-dash + hyphen) raises TaskParseError.
  9.  parse_line: empty string raises TaskParseError.
  10. parse_line: whitespace-only string raises TaskParseError.
  11. parse_line: missing tag section raises TaskParseError.
  12. parse_line: non-numeric ID raises TaskParseError.
  13. parse_line: Task.task_id is int, not string.
  14. parse_line: Task.tag is normalised (e.g. "S", "US1", "P").
  15. parse_line: Task.description is stripped of leading/trailing whitespace.
  16. parse_line: Task.file_path is None when not supplied.
  17. parse_line: leading whitespace on entire line is tolerated.
  18. parse_tasks: returns list sorted by task_id ascending.
  19. parse_tasks: out-of-order input is sorted correctly.
  20. parse_tasks: single task returns single-element list.
  21. parse_tasks: empty string returns empty list.
  22. parse_tasks: blank lines in content are skipped.
  23. parse_tasks: comment lines (starting with #) are skipped.
  24. parse_tasks: first malformed line raises TaskParseError.
  25. parse_tasks: duplicate task_ids raise TaskParseError.
  26. group_tasks: [S] tasks go to TaskGroup.setup.
  27. group_tasks: [US*] tasks go to TaskGroup.us.
  28. group_tasks: [P] tasks go to TaskGroup.polish.
  29. group_tasks: mixed tags are split into correct buckets.
  30. group_tasks: empty list yields empty TaskGroup.
  31. group_tasks: TaskGroup.us preserves order from input list.
  32. group_tasks: unknown tag raises TaskParseError.
  33. parse_line: large task_id (e.g. 9999) is handled correctly.
  34. parse_line: description with em-dash inside is handled (only first split).
  35. parse_line: US tag with multi-digit number (e.g. [US12]) is accepted.
"""

from __future__ import annotations

import pytest

from orchestrator.tdd.parser import (
    Task,
    TaskGroup,
    TaskParseError,
    group_tasks,
    parse_line,
    parse_tasks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EM = "\u2014"  # em-dash character used as the canonical separator


def _line(task_id: int, tag: str, description: str, file_path: str | None = None) -> str:
    """Build a well-formed task line using em-dashes."""
    base = f"{task_id} {EM} [{tag}] {description}"
    if file_path is not None:
        base += f" {EM} {file_path}"
    return base


# ===========================================================================
# 1. parse_line — happy paths
# ===========================================================================


class TestParseLineHappyPath:
    """FR-PARSER-01, FR-PARSER-03: valid lines parse without error."""

    def test_setup_tag_with_file_path(self):
        """FR-PARSER-01: [S] tag with file_path parses correctly."""
        task = parse_line(_line(1, "S", "Setup CI pipeline", "setup_ci.py"))
        assert task.task_id == 1
        assert task.tag == "S"
        assert task.description == "Setup CI pipeline"
        assert task.file_path == "setup_ci.py"

    def test_us_tag_with_file_path(self):
        """FR-PARSER-01: [US1] tag with file_path parses correctly."""
        task = parse_line(_line(2, "US1", "Implement login", "auth/login.py"))
        assert task.task_id == 2
        assert task.tag == "US1"
        assert task.description == "Implement login"
        assert task.file_path == "auth/login.py"

    def test_polish_tag_without_file_path_accepted(self):
        """FR-PARSER-03: [P] without file_path is explicitly allowed."""
        task = parse_line(_line(3, "P", "Polish documentation"))
        assert task.task_id == 3
        assert task.tag == "P"
        assert task.description == "Polish documentation"
        assert task.file_path is None

    def test_polish_tag_with_file_path_accepted(self):
        """FR-PARSER-03: [P] with file_path is also allowed."""
        task = parse_line(_line(4, "P", "Polish README", "README.md"))
        assert task.task_id == 4
        assert task.tag == "P"
        assert task.file_path == "README.md"

    def test_task_id_is_int(self):
        """FR-PARSER-01: task_id attribute is an integer, not a string."""
        task = parse_line(_line(5, "S", "Some task", "some.py"))
        assert isinstance(task.task_id, int)
        assert task.task_id == 5

    def test_tag_is_string(self):
        """FR-PARSER-01: tag attribute is a plain string without brackets."""
        task = parse_line(_line(1, "US1", "Desc", "file.py"))
        assert task.tag == "US1"
        assert "[" not in task.tag

    def test_description_stripped(self):
        """FR-PARSER-01: description has no leading/trailing whitespace."""
        raw = f"10 {EM} [S]   padded description   {EM} file.py"
        task = parse_line(raw)
        assert task.description == "padded description"

    def test_file_path_none_when_absent(self):
        """FR-PARSER-01: file_path is None when the third segment is missing."""
        task = parse_line(_line(6, "P", "No file"))
        assert task.file_path is None

    def test_leading_whitespace_on_line_tolerated(self):
        """FR-PARSER-01: a line with leading spaces is still parsed."""
        task = parse_line("  " + _line(7, "S", "Indented", "f.py"))
        assert task.task_id == 7

    def test_large_task_id_handled(self):
        """FR-PARSER-01: task_id values up to 9999 are supported."""
        task = parse_line(_line(9999, "US3", "Big ID task", "big.py"))
        assert task.task_id == 9999

    def test_description_with_em_dash_inside(self):
        """FR-PARSER-01: only the FIRST em-dash pair is used as separators;
        an em-dash appearing inside the description is kept verbatim."""
        desc = f"Setup{EM}something"
        task = parse_line(_line(11, "S", desc, "x.py"))
        assert EM in task.description

    def test_us_tag_multi_digit_number(self):
        """FR-PARSER-01: [US12] (multi-digit user-story number) is valid."""
        task = parse_line(_line(12, "US12", "Big story", "big_story.py"))
        assert task.tag == "US12"

    def test_file_path_stripped(self):
        """FR-PARSER-01: file_path has no surrounding whitespace."""
        raw = f"13 {EM} [S] Some task {EM}   spaced/path.py   "
        task = parse_line(raw)
        assert task.file_path == "spaced/path.py"


# ===========================================================================
# 2. parse_line — rejection paths
# ===========================================================================


class TestParseLineRejection:
    """FR-PARSER-01, FR-PARSER-03: invalid lines raise TaskParseError."""

    def test_setup_without_file_path_rejected(self):
        """FR-PARSER-03: [S] tag missing file_path raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(_line(1, "S", "Setup CI"))

    def test_us_without_file_path_rejected(self):
        """FR-PARSER-03: [US2] tag missing file_path raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(_line(2, "US2", "Login feature"))

    def test_hyphen_separator_rejected(self):
        """FR-PARSER-01: hyphens (-) instead of em-dashes raise TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line("1 - [S] Setup CI - setup_ci.py")

    def test_mixed_separator_rejected(self):
        """FR-PARSER-01: mixing em-dash and hyphen raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(f"1 {EM} [S] Setup CI - setup_ci.py")

    def test_empty_string_rejected(self):
        """FR-PARSER-01: empty string raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line("")

    def test_whitespace_only_rejected(self):
        """FR-PARSER-01: whitespace-only string raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line("   ")

    def test_missing_tag_section_rejected(self):
        """FR-PARSER-01: line without a [TAG] segment raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(f"1 {EM} No tag here {EM} file.py")

    def test_non_numeric_id_rejected(self):
        """FR-PARSER-01: non-numeric task ID raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(f"abc {EM} [S] Task {EM} file.py")

    def test_negative_id_rejected(self):
        """FR-PARSER-01: negative task ID raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(f"-1 {EM} [S] Task {EM} file.py")

    def test_zero_id_rejected(self):
        """FR-PARSER-01: task ID of zero raises TaskParseError."""
        with pytest.raises(TaskParseError):
            parse_line(f"0 {EM} [S] Task {EM} file.py")


# ===========================================================================
# 3. parse_tasks — happy paths
# ===========================================================================


class TestParseTasksHappyPath:
    """FR-PARSER-02: parse_tasks returns correctly sorted Task lists."""

    def test_single_task_returns_list(self):
        """FR-PARSER-02: single-task content yields one-element list."""
        content = _line(1, "S", "Only task", "only.py")
        result = parse_tasks(content)
        assert len(result) == 1
        assert result[0].task_id == 1

    def test_empty_content_returns_empty_list(self):
        """FR-PARSER-02: empty string yields empty list."""
        result = parse_tasks("")
        assert result == []

    def test_sorted_by_task_id_ascending(self):
        """FR-PARSER-02: tasks are returned sorted by task_id, ascending."""
        content = "\n".join([
            _line(3, "P", "Polish"),
            _line(1, "S", "Setup", "setup.py"),
            _line(2, "US1", "Login", "login.py"),
        ])
        result = parse_tasks(content)
        assert [t.task_id for t in result] == [1, 2, 3]

    def test_already_sorted_input_stays_sorted(self):
        """FR-PARSER-02: already-sorted input is unchanged in order."""
        content = "\n".join([
            _line(1, "S", "Setup", "s.py"),
            _line(2, "US1", "Feature", "f.py"),
        ])
        result = parse_tasks(content)
        assert [t.task_id for t in result] == [1, 2]

    def test_blank_lines_skipped(self):
        """FR-PARSER-02: blank lines between task lines are ignored."""
        content = "\n".join([
            _line(1, "S", "First", "first.py"),
            "",
            "   ",
            _line(2, "P", "Second"),
        ])
        result = parse_tasks(content)
        assert len(result) == 2

    def test_comment_lines_skipped(self):
        """FR-PARSER-02: lines starting with '#' are treated as comments."""
        content = "\n".join([
            "# This is a comment",
            _line(1, "S", "Real task", "real.py"),
            "# Another comment",
        ])
        result = parse_tasks(content)
        assert len(result) == 1
        assert result[0].task_id == 1

    def test_returns_task_objects(self):
        """FR-PARSER-02: each element of the returned list is a Task instance."""
        content = _line(1, "US1", "A task", "a.py")
        result = parse_tasks(content)
        assert isinstance(result[0], Task)


# ===========================================================================
# 4. parse_tasks — rejection paths
# ===========================================================================


class TestParseTasksRejection:
    """FR-PARSER-01: malformed lines inside multi-line content raise errors."""

    def test_malformed_line_raises_error(self):
        """FR-PARSER-01: a single malformed line in content raises TaskParseError."""
        content = "\n".join([
            _line(1, "S", "Good line", "good.py"),
            "not a valid task line",
        ])
        with pytest.raises(TaskParseError):
            parse_tasks(content)

    def test_duplicate_task_ids_raise_error(self):
        """FR-PARSER-02: duplicate task_ids in content raise TaskParseError."""
        content = "\n".join([
            _line(1, "S", "First", "first.py"),
            _line(1, "US1", "Duplicate ID", "dup.py"),
        ])
        with pytest.raises(TaskParseError):
            parse_tasks(content)

    def test_hyphen_line_in_multiline_raises_error(self):
        """FR-PARSER-01: a hyphen-format line among valid lines raises TaskParseError."""
        content = "\n".join([
            _line(1, "S", "Valid", "valid.py"),
            "2 - [US1] Bad format - bad.py",
        ])
        with pytest.raises(TaskParseError):
            parse_tasks(content)


# ===========================================================================
# 5. group_tasks — happy paths
# ===========================================================================


class TestGroupTasksHappyPath:
    """FR-PARSER-04: group_tasks splits tasks into setup / us / polish."""

    def _make_task(
        self,
        task_id: int,
        tag: str,
        description: str = "desc",
        file_path: str | None = None,
    ) -> Task:
        """Directly instantiate a Task for grouping tests."""
        t = object.__new__(Task)
        t.task_id = task_id
        t.tag = tag
        t.description = description
        t.file_path = file_path
        return t

    def test_setup_tasks_go_to_setup(self):
        """FR-PARSER-04: tasks tagged [S] appear in TaskGroup.setup."""
        task = self._make_task(1, "S", "Setup", "s.py")
        group = group_tasks([task])
        assert task in group.setup

    def test_us_tasks_go_to_us(self):
        """FR-PARSER-04: tasks tagged [US*] appear in TaskGroup.us."""
        task = self._make_task(2, "US1", "Feature", "f.py")
        group = group_tasks([task])
        assert task in group.us

    def test_polish_tasks_go_to_polish(self):
        """FR-PARSER-04: tasks tagged [P] appear in TaskGroup.polish."""
        task = self._make_task(3, "P", "Polish")
        group = group_tasks([task])
        assert task in group.polish

    def test_mixed_tags_split_correctly(self):
        """FR-PARSER-04: a mixed list is split into all three buckets."""
        s_task = self._make_task(1, "S", "Setup", "s.py")
        us_task = self._make_task(2, "US1", "Feature", "f.py")
        p_task = self._make_task(3, "P", "Polish")
        group = group_tasks([s_task, us_task, p_task])
        assert group.setup == [s_task]
        assert group.us == [us_task]
        assert group.polish == [p_task]

    def test_empty_list_yields_empty_group(self):
        """FR-PARSER-04: an empty input yields a TaskGroup with empty buckets."""
        group = group_tasks([])
        assert group.setup == []
        assert group.us == []
        assert group.polish == []

    def test_us_bucket_preserves_order(self):
        """FR-PARSER-04: order within TaskGroup.us matches the input order."""
        tasks = [
            self._make_task(2, "US2", "Second story", "b.py"),
            self._make_task(1, "US1", "First story", "a.py"),
        ]
        group = group_tasks(tasks)
        assert group.us[0].tag == "US2"
        assert group.us[1].tag == "US1"

    def test_multiple_us_tags_all_in_us_bucket(self):
        """FR-PARSER-04: US1, US2, US12 all land in TaskGroup.us."""
        tasks = [
            self._make_task(1, "US1", "Story 1", "a.py"),
            self._make_task(2, "US2", "Story 2", "b.py"),
            self._make_task(3, "US12", "Story 12", "c.py"),
        ]
        group = group_tasks(tasks)
        assert len(group.us) == 3
        assert group.setup == []
        assert group.polish == []

    def test_multiple_setup_tasks(self):
        """FR-PARSER-04: multiple [S] tasks all land in TaskGroup.setup."""
        tasks = [
            self._make_task(1, "S", "Setup A", "a.py"),
            self._make_task(2, "S", "Setup B", "b.py"),
        ]
        group = group_tasks(tasks)
        assert len(group.setup) == 2


# ===========================================================================
# 6. group_tasks — rejection paths
# ===========================================================================


class TestGroupTasksRejection:
    """FR-PARSER-04: group_tasks raises on unknown tags."""

    def _make_task(self, task_id: int, tag: str) -> Task:
        t = object.__new__(Task)
        t.task_id = task_id
        t.tag = tag
        t.description = "desc"
        t.file_path = None
        return t

    def test_unknown_tag_raises_error(self):
        """FR-PARSER-04: an unrecognised tag raises TaskParseError."""
        bad_task = self._make_task(1, "UNKNOWN")
        with pytest.raises(TaskParseError):
            group_tasks([bad_task])

    def test_lowercase_s_tag_raises_error(self):
        """FR-PARSER-04: tag 's' (lowercase) is not recognised."""
        bad_task = self._make_task(1, "s")
        with pytest.raises(TaskParseError):
            group_tasks([bad_task])

    def test_lowercase_p_tag_raises_error(self):
        """FR-PARSER-04: tag 'p' (lowercase) is not recognised."""
        bad_task = self._make_task(1, "p")
        with pytest.raises(TaskParseError):
            group_tasks([bad_task])


# ===========================================================================
# 7. Integration: parse_tasks + group_tasks round-trip
# ===========================================================================


class TestRoundTrip:
    """Integration: parse then group produces correct final structure."""

    def test_full_round_trip(self):
        """FR-PARSER-01..04: a real tasks.md content round-trips correctly."""
        content = "\n".join([
            _line(1, "S", "Setup CI pipeline", "setup_ci.py"),
            _line(2, "US1", "Implement login", "auth/login.py"),
            _line(3, "US2", "Implement registration", "auth/register.py"),
            _line(4, "P", "Polish documentation"),
            _line(5, "P", "Polish README", "README.md"),
        ])
        tasks = parse_tasks(content)
        group = group_tasks(tasks)

        assert len(group.setup) == 1
        assert group.setup[0].task_id == 1

        assert len(group.us) == 2
        assert [t.task_id for t in group.us] == [2, 3]

        assert len(group.polish) == 2
        assert {t.task_id for t in group.polish} == {4, 5}

    def test_round_trip_with_out_of_order_ids(self):
        """FR-PARSER-02: tasks are sorted before grouping."""
        content = "\n".join([
            _line(3, "P", "Last polish"),
            _line(1, "S", "First setup", "setup.py"),
            _line(2, "US1", "Middle story", "story.py"),
        ])
        tasks = parse_tasks(content)
        assert [t.task_id for t in tasks] == [1, 2, 3]

        group = group_tasks(tasks)
        assert group.setup[0].task_id == 1
        assert group.us[0].task_id == 2
        assert group.polish[0].task_id == 3
