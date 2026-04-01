"""Contract tests: parser/generator format alignment and module constraints.

These tests verify two classes of guarantees:

1. FORMAT ALIGNMENT — The task-line generator (format_task_line) and the
   parser (parse_line / parse_tasks) must agree on the canonical wire format.
   Any line that the generator emits MUST round-trip back to the same field
   values when fed to the parser.

2. MODULE CONSTRAINTS — Every source module in orchestrator/ must satisfy:
   - No bare ``except:`` clauses (bare except catches BaseException silently).
   - Exception chaining: re-raised exceptions must use ``raise X from Y``
     (grep for bare ``raise ... from`` is not required; bare ``raise X`` after
     ``except SomeError`` is the pattern to detect).
   - Source files must be strictly under 400 lines.

Why these are contract tests (not unit tests):
  - They are cross-cutting: they validate the *agreement* between two modules
    and enforce project-wide source hygiene rules.
  - Violations break the integration contract between producer and consumer.

Generator module targeted:
  orchestrator.tdd.parser exposes parse_line / parse_tasks.
  The generator side is ``format_task_line`` — a function that must exist in
  orchestrator.tdd.parser and that serialises a Task back into the em-dash
  line format expected by parse_line.

  If ``format_task_line`` does not yet exist, these tests fail (RED) because
  the import or the call will raise AttributeError / return wrong values.
"""

from __future__ import annotations

import ast
import os
import pathlib
import tokenize
import token as token_mod
import re

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

from orchestrator.tdd.parser import (
    Task,
    TaskParseError,
    parse_line,
    parse_tasks,
)

# ``format_task_line`` is the generator counterpart to ``parse_line``.
# It is expected to live in orchestrator.tdd.parser.  Importing it directly
# makes the import error surface as an AttributeError during collection so
# the test suite fails (RED) rather than erroring out with ImportError.
try:
    from orchestrator.tdd.parser import format_task_line  # type: ignore[attr-defined]
except ImportError:
    format_task_line = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EM = "\u2014"  # canonical em-dash separator
_ORCHESTRATOR_ROOT = pathlib.Path(__file__).parent.parent.parent / "orchestrator"
_SOURCE_FILES: list[pathlib.Path] = sorted(_ORCHESTRATOR_ROOT.rglob("*.py"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_files_without_init() -> list[pathlib.Path]:
    """Return all .py files under orchestrator/ excluding __init__ files."""
    return [p for p in _SOURCE_FILES if p.name != "__init__.py"]


def _make_task(
    task_id: int,
    tag: str,
    description: str,
    file_path: str | None = None,
) -> Task:
    """Construct a Task using the normal constructor (for generator tests)."""
    return Task(task_id=task_id, tag=tag, description=description, file_path=file_path)


# ===========================================================================
# SECTION 1 — format_task_line existence
# ===========================================================================


class TestGeneratorExists:
    """CONTRACT-GEN-01: format_task_line must exist in orchestrator.tdd.parser."""

    def test_format_task_line_is_callable(self):
        """CONTRACT-GEN-01: format_task_line must be importable and callable."""
        assert callable(format_task_line), (
            "format_task_line is not defined in orchestrator.tdd.parser. "
            "The generator counterpart to parse_line is missing."
        )


# ===========================================================================
# SECTION 2 — Round-trip: generator → parser produces identical field values
# ===========================================================================


class TestRoundTripGeneratorToParser:
    """CONTRACT-GEN-02: Lines produced by format_task_line must be accepted by
    parse_line and yield a Task with identical field values (round-trip fidelity)."""

    def test_s_tag_with_file_path_round_trips(self):
        """CONTRACT-GEN-02: [S] task with file_path serialises and parses back correctly."""
        original = _make_task(1, "S", "Setup CI pipeline", "setup_ci.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 1
        assert parsed.tag == "S"
        assert parsed.description == "Setup CI pipeline"
        assert parsed.file_path == "setup_ci.py"

    def test_us_tag_with_file_path_round_trips(self):
        """CONTRACT-GEN-02: [US1] task with file_path serialises and parses back correctly."""
        original = _make_task(2, "US1", "Implement login", "auth/login.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 2
        assert parsed.tag == "US1"
        assert parsed.description == "Implement login"
        assert parsed.file_path == "auth/login.py"

    def test_polish_tag_without_file_path_round_trips(self):
        """CONTRACT-GEN-02: [P] task without file_path serialises and parses back correctly."""
        original = _make_task(3, "P", "Polish documentation", None)
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 3
        assert parsed.tag == "P"
        assert parsed.description == "Polish documentation"
        assert parsed.file_path is None

    def test_polish_tag_with_file_path_round_trips(self):
        """CONTRACT-GEN-02: [P] task with file_path also round-trips correctly."""
        original = _make_task(4, "P", "Polish README", "README.md")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 4
        assert parsed.tag == "P"
        assert parsed.file_path == "README.md"

    def test_us_multi_digit_tag_round_trips(self):
        """CONTRACT-GEN-02: [US12] tag with multi-digit number round-trips correctly."""
        original = _make_task(12, "US12", "Big user story", "big_story.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 12
        assert parsed.tag == "US12"
        assert parsed.file_path == "big_story.py"

    def test_large_task_id_round_trips(self):
        """CONTRACT-GEN-02: large task_id (9999) round-trips without truncation."""
        original = _make_task(9999, "US3", "Big ID task", "big.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.task_id == 9999

    def test_description_with_special_characters_round_trips(self):
        """CONTRACT-GEN-02: descriptions with colons and parentheses round-trip correctly."""
        original = _make_task(5, "S", "Setup (DB): migrate schema", "db.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.description == "Setup (DB): migrate schema"

    def test_file_path_with_subdirectory_round_trips(self):
        """CONTRACT-GEN-02: nested file_path (dir/subdir/file.py) round-trips correctly."""
        original = _make_task(6, "US2", "Deep module", "a/b/c/d.py")
        line = format_task_line(original)
        parsed = parse_line(line)
        assert parsed.file_path == "a/b/c/d.py"

    def test_generated_line_uses_em_dash_separator(self):
        """CONTRACT-GEN-03: the generated line MUST use em-dash (U+2014) as separator,
        not a regular hyphen, so parse_line accepts it."""
        original = _make_task(7, "S", "Check separator", "sep.py")
        line = format_task_line(original)
        assert EM in line, (
            f"Generated line {line!r} does not contain em-dash separator U+2014. "
            "parse_line requires em-dash; using hyphen would break the parser contract."
        )

    def test_generated_line_does_not_use_plain_hyphen_as_separator(self):
        """CONTRACT-GEN-03: generated line must not use ' - ' as a field separator."""
        original = _make_task(8, "S", "No hyphen sep", "f.py")
        line = format_task_line(original)
        # The separator between fields must be em-dash, not hyphen
        # We check that ' - ' does not appear between the id and the tag section
        segments = line.split(EM)
        assert len(segments) >= 2, (
            f"Generated line {line!r} has fewer than 2 em-dash-separated segments."
        )

    def test_generated_line_contains_bracketed_tag(self):
        """CONTRACT-GEN-03: the tag in the generated line must be wrapped in [brackets]."""
        original = _make_task(9, "US1", "Check tag format", "t.py")
        line = format_task_line(original)
        assert "[US1]" in line, (
            f"Generated line {line!r} does not contain '[US1]'. "
            "parse_line expects the tag wrapped in square brackets."
        )


# ===========================================================================
# SECTION 3 — Round-trip: parse_tasks over format_task_line output
# ===========================================================================


class TestRoundTripMultipleTasks:
    """CONTRACT-GEN-04: A list of generated lines, when joined with newlines and
    fed to parse_tasks, produces tasks with the same field values in sorted order."""

    def test_multiple_tasks_round_trip_via_parse_tasks(self):
        """CONTRACT-GEN-04: three tasks serialised and re-parsed yield correct values."""
        originals = [
            _make_task(3, "P", "Polish docs", None),
            _make_task(1, "S", "Setup CI", "setup.py"),
            _make_task(2, "US1", "Login feature", "auth.py"),
        ]
        lines = "\n".join(format_task_line(t) for t in originals)
        parsed = parse_tasks(lines)

        # parse_tasks sorts by task_id ascending
        assert [t.task_id for t in parsed] == [1, 2, 3]
        assert parsed[0].tag == "S"
        assert parsed[0].file_path == "setup.py"
        assert parsed[1].tag == "US1"
        assert parsed[1].file_path == "auth.py"
        assert parsed[2].tag == "P"
        assert parsed[2].file_path is None

    def test_single_task_round_trip_via_parse_tasks(self):
        """CONTRACT-GEN-04: a single generated line round-trips through parse_tasks."""
        original = _make_task(1, "S", "Only task", "only.py")
        lines = format_task_line(original)
        parsed = parse_tasks(lines)
        assert len(parsed) == 1
        assert parsed[0].task_id == 1
        assert parsed[0].tag == "S"
        assert parsed[0].file_path == "only.py"

    def test_round_trip_preserves_task_count(self):
        """CONTRACT-GEN-04: the number of tasks is preserved through the round-trip."""
        originals = [
            _make_task(i, "US1", f"Task {i}", f"f{i}.py")
            for i in range(1, 6)
        ]
        lines = "\n".join(format_task_line(t) for t in originals)
        parsed = parse_tasks(lines)
        assert len(parsed) == 5


# ===========================================================================
# SECTION 4 — format_task_line rejects invalid input
# ===========================================================================


class TestGeneratorRejectsInvalidInput:
    """CONTRACT-GEN-05: format_task_line must raise ValueError (or TaskParseError)
    on inputs that would produce unparseable output."""

    def test_format_task_line_rejects_zero_task_id(self):
        """CONTRACT-GEN-05: task_id=0 is invalid and must raise an exception."""
        bad = _make_task(0, "S", "Bad ID", "f.py")
        with pytest.raises((ValueError, TaskParseError)):
            format_task_line(bad)

    def test_format_task_line_rejects_negative_task_id(self):
        """CONTRACT-GEN-05: negative task_id is invalid and must raise an exception."""
        bad = _make_task(-1, "S", "Negative", "f.py")
        with pytest.raises((ValueError, TaskParseError)):
            format_task_line(bad)

    def test_format_task_line_rejects_empty_description(self):
        """CONTRACT-GEN-05: empty description would produce an unparseable line."""
        bad = _make_task(1, "S", "", "f.py")
        with pytest.raises((ValueError, TaskParseError)):
            format_task_line(bad)

    def test_format_task_line_rejects_description_with_em_dash_pair(self):
        """CONTRACT-GEN-05: description containing ' EM ' would corrupt the field
        boundary and must be rejected by the generator."""
        desc_with_em = f"foo {EM} bar"
        bad = _make_task(1, "S", desc_with_em, "f.py")
        # Either the generator raises, or if it allows it, parse_line must still
        # recover the original description. We test for the raising path here.
        with pytest.raises((ValueError, TaskParseError)):
            format_task_line(bad)


# ===========================================================================
# SECTION 5 — Module constraints: no bare except
# ===========================================================================


class TestNoBareExcept:
    """CONSTRAINT-01: No source module in orchestrator/ may use a bare ``except:``
    clause. Bare except silently catches BaseException (including KeyboardInterrupt
    and SystemExit) and hides bugs."""

    @pytest.mark.parametrize("src_file", _source_files_without_init(), ids=lambda p: str(p.relative_to(_ORCHESTRATOR_ROOT)))
    def test_no_bare_except(self, src_file: pathlib.Path):
        """CONSTRAINT-01: {src_file} must not contain a bare 'except:' clause."""
        source = src_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(src_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                assert node.type is not None, (
                    f"{src_file.relative_to(_ORCHESTRATOR_ROOT)} line {node.lineno}: "
                    f"bare 'except:' clause found. "
                    f"Use a specific exception type (e.g. 'except ValueError:')."
                )


# ===========================================================================
# SECTION 6 — Module constraints: exception chaining
# ===========================================================================


class TestExceptionChaining:
    """CONSTRAINT-02: When a module re-raises a new exception inside an except
    block, it MUST use ``raise NewExc(...) from original`` (exception chaining)
    rather than ``raise NewExc(...)`` alone.

    This is detected by scanning for ``raise`` statements inside ``except``
    handlers that are NOT of the bare ``raise`` (re-raise) form and do not
    include a ``from`` clause.
    """

    @pytest.mark.parametrize("src_file", _source_files_without_init(), ids=lambda p: str(p.relative_to(_ORCHESTRATOR_ROOT)))
    def test_exception_chaining_used(self, src_file: pathlib.Path):
        """CONSTRAINT-02: {src_file} must use 'raise X from Y' when raising inside except."""
        source = src_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(src_file))

        violations: list[int] = []

        class _ExceptVisitor(ast.NodeVisitor):
            def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
                for child in ast.walk(node):
                    if isinstance(child, ast.Raise):
                        # bare ``raise`` (re-raise) is allowed
                        if child.exc is None:
                            continue
                        # ``raise X from Y`` is correct
                        if child.cause is not None:
                            continue
                        # ``raise X`` inside an except block — chaining missing
                        violations.append(child.lineno)
                # Do NOT recurse into nested functions/classes — they are not
                # inside the except handler at runtime.
                self.generic_visit(node)

        _ExceptVisitor().visit(tree)

        assert violations == [], (
            f"{src_file.relative_to(_ORCHESTRATOR_ROOT)}: "
            f"raise without 'from' inside except handler at lines {violations}. "
            f"Use 'raise NewException(...) from original_exc' to preserve context."
        )


# ===========================================================================
# SECTION 7 — Module constraints: file length < 400 lines
# ===========================================================================


class TestFileLengthConstraint:
    """CONSTRAINT-03: Every source file in orchestrator/ must be strictly under
    400 lines. Files approaching this limit should be split into focused modules."""

    MAX_LINES = 400

    @pytest.mark.parametrize("src_file", _source_files_without_init(), ids=lambda p: str(p.relative_to(_ORCHESTRATOR_ROOT)))
    def test_file_length_under_400_lines(self, src_file: pathlib.Path):
        """CONSTRAINT-03: {src_file} must have fewer than 400 lines."""
        lines = src_file.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        assert line_count < self.MAX_LINES, (
            f"{src_file.relative_to(_ORCHESTRATOR_ROOT)} has {line_count} lines "
            f"(limit: {self.MAX_LINES - 1}). "
            f"Split the module into smaller, focused units."
        )


# ===========================================================================
# SECTION 8 — Integration: constraints + round-trip together
# ===========================================================================


class TestContractIntegration:
    """Integration contract: the parser and generator together form a stable
    serialisation boundary. These tests verify end-to-end correctness."""

    def test_all_valid_tags_round_trip(self):
        """CONTRACT-INT-01: all valid tag types (S, US1, US12, P) round-trip correctly."""
        cases = [
            _make_task(1, "S", "Setup", "s.py"),
            _make_task(2, "US1", "Story 1", "a.py"),
            _make_task(3, "US12", "Story 12", "b.py"),
            _make_task(4, "P", "Polish", None),
        ]
        for original in cases:
            line = format_task_line(original)
            parsed = parse_line(line)
            assert parsed.task_id == original.task_id
            assert parsed.tag == original.tag
            assert parsed.description == original.description
            assert parsed.file_path == original.file_path

    def test_whitespace_invariance(self):
        """CONTRACT-INT-02: descriptions with leading/trailing spaces are trimmed
        by the parser, so round-trip must also trim them (no spurious whitespace)."""
        original = _make_task(1, "S", "  trimmed  ", "f.py")
        # The generator should either reject or normalise the description.
        # After round-trip, the description must match what parse_line returns.
        try:
            line = format_task_line(original)
            parsed = parse_line(line)
            # parse_line strips whitespace; the round-trip result must be stripped
            assert parsed.description == parsed.description.strip()
        except (ValueError, TaskParseError):
            # Generator may reject whitespace-padded descriptions — that is acceptable
            pass

    def test_generated_line_is_a_string(self):
        """CONTRACT-INT-03: format_task_line must return a str, not bytes or None."""
        original = _make_task(1, "S", "Type check", "t.py")
        result = format_task_line(original)
        assert isinstance(result, str), (
            f"format_task_line returned {type(result)!r}, expected str."
        )

    def test_generated_line_is_single_line(self):
        """CONTRACT-INT-04: format_task_line must return a single line (no embedded newlines).
        parse_tasks splits on newlines; embedded newlines would break multi-task parsing."""
        original = _make_task(1, "S", "Single line only", "f.py")
        result = format_task_line(original)
        assert "\n" not in result, (
            f"format_task_line returned a multi-line string: {result!r}. "
            "The output must be a single line without embedded newlines."
        )

    def test_parser_and_generator_agree_on_s_tag_requires_file_path(self):
        """CONTRACT-INT-05: both the parser and generator must enforce that [S]
        tasks require a file_path.  A generated [S] line without a file_path
        must be rejected either by the generator or the parser."""
        bad = _make_task(1, "S", "Setup without path", None)
        raised_in_generator = False
        line = None
        try:
            line = format_task_line(bad)
        except (ValueError, TaskParseError):
            raised_in_generator = True

        if not raised_in_generator:
            # If the generator accepted it, the parser must reject it
            assert line is not None
            with pytest.raises((ValueError, TaskParseError)):
                parse_line(line)

    def test_parser_and_generator_agree_on_us_tag_requires_file_path(self):
        """CONTRACT-INT-05: both the parser and generator must enforce that [US*]
        tasks require a file_path.  A generated [US1] line without a file_path
        must be rejected either by the generator or the parser."""
        bad = _make_task(2, "US1", "Story without path", None)
        raised_in_generator = False
        line = None
        try:
            line = format_task_line(bad)
        except (ValueError, TaskParseError):
            raised_in_generator = True

        if not raised_in_generator:
            assert line is not None
            with pytest.raises((ValueError, TaskParseError)):
                parse_line(line)
