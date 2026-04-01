"""Unit tests for orchestrator.perception — NC/NR marker detection and
uncertainty heuristic scanner.

FR references (from spec User Story 1, scenario 3 and 4):
  FR-NC: Spec-writer output containing [NC:] markers MUST trigger the clarify
         agent before the pipeline proceeds.
  FR-NR: Planner output containing [NR:] markers MUST trigger the research
         agent before task generation.

These tests are RED-phase tests — they MUST FAIL until orchestrator/perception.py
provides concrete implementations of:
  - detect_nc_markers(text) -> list[str]
  - detect_nr_markers(text) -> list[str]
  - question_density(text) -> float
  - detect_tbd_todo(text) -> list[str]
  - detect_hedging(text) -> list[str]
  - analyse(text) -> dict
"""

from __future__ import annotations

import pytest

from orchestrator.perception import (
    analyse,
    detect_hedging,
    detect_nc_markers,
    detect_nr_markers,
    detect_tbd_todo,
    question_density,
)


# ---------------------------------------------------------------------------
# FR-NC: detect_nc_markers
# ---------------------------------------------------------------------------


class TestDetectNcMarkers:
    """FR-NC: detect_nc_markers MUST return a list of NC-tagged snippets."""

    def test_returns_list_for_empty_string(self):
        """FR-NC: Empty text yields an empty list, not None."""
        result = detect_nc_markers("")
        assert result == [], f"Expected [], got {result!r}"

    def test_detects_single_nc_marker(self):
        """FR-NC: A single [NC:] marker in text is detected and returned."""
        text = "We need more details. [NC: What is the preferred database?]"
        result = detect_nc_markers(text)
        assert len(result) == 1, f"Expected 1 match, got {len(result)}"

    def test_returned_snippet_contains_nc_tag(self):
        """FR-NC: The returned snippet MUST contain the [NC:] tag text."""
        text = "Unclear requirement. [NC: Define the SLA target.]"
        result = detect_nc_markers(text)
        assert any("[NC:" in item for item in result), (
            f"Expected result items to contain '[NC:', got {result!r}"
        )

    def test_detects_multiple_nc_markers(self):
        """FR-NC: Multiple [NC:] markers in the same text are all detected."""
        text = (
            "[NC: Clarify input format.] Some content. "
            "[NC: What is the timeout value?] More content."
        )
        result = detect_nc_markers(text)
        assert len(result) == 2, f"Expected 2 matches, got {len(result)}"

    def test_no_false_positive_without_nc_marker(self):
        """FR-NC: Text without [NC:] markers returns an empty list."""
        text = "This is a perfectly clear requirement with no ambiguity."
        result = detect_nc_markers(text)
        assert result == [], f"Expected [], got {result!r}"

    def test_nc_marker_content_is_captured(self):
        """FR-NC: The content after [NC: ...] is captured in the result."""
        marker_content = "What is the retry strategy?"
        text = f"[NC: {marker_content}]"
        result = detect_nc_markers(text)
        assert len(result) == 1
        assert marker_content in result[0], (
            f"Expected marker content '{marker_content}' in result, got {result[0]!r}"
        )

    def test_nc_marker_case_sensitive(self):
        """FR-NC: Detection is case-sensitive; [nc:] MUST NOT match [NC:]."""
        text = "[nc: lowercase marker should not match]"
        result = detect_nc_markers(text)
        assert result == [], (
            f"Lowercase [nc:] should not be detected, got {result!r}"
        )

    def test_nc_marker_without_colon_not_detected(self):
        """FR-NC: '[NC]' without a colon MUST NOT be detected as a marker."""
        text = "The [NC] tag without colon should not be detected."
        result = detect_nc_markers(text)
        assert result == [], (
            f"[NC] without colon should not be detected, got {result!r}"
        )

    def test_nc_marker_multiline_text(self):
        """FR-NC: Markers are detected across multi-line text."""
        text = (
            "Line one: description.\n"
            "[NC: What should the default be?]\n"
            "Line three: more content."
        )
        result = detect_nc_markers(text)
        assert len(result) == 1, f"Expected 1 match in multiline text, got {len(result)}"

    def test_returns_list_type(self):
        """FR-NC: Return type is always a list, never None."""
        result = detect_nc_markers("some text without markers")
        assert isinstance(result, list), f"Expected list, got {type(result)}"

    def test_nc_marker_with_special_characters_in_content(self):
        """FR-NC: Markers containing special chars (commas, slashes) are detected."""
        text = "[NC: Is it A/B or C, D?]"
        result = detect_nc_markers(text)
        assert len(result) == 1, f"Expected 1 match, got {len(result)}"


# ---------------------------------------------------------------------------
# FR-NR: detect_nr_markers
# ---------------------------------------------------------------------------


class TestDetectNrMarkers:
    """FR-NR: detect_nr_markers MUST return a list of NR-tagged snippets."""

    def test_returns_list_for_empty_string(self):
        """FR-NR: Empty text yields an empty list, not None."""
        result = detect_nr_markers("")
        assert result == [], f"Expected [], got {result!r}"

    def test_detects_single_nr_marker(self):
        """FR-NR: A single [NR:] marker in text is detected."""
        text = "We should check prior art. [NR: Research competitor pricing models.]"
        result = detect_nr_markers(text)
        assert len(result) == 1, f"Expected 1 match, got {len(result)}"

    def test_returned_snippet_contains_nr_tag(self):
        """FR-NR: The returned snippet MUST contain the [NR:] tag text."""
        text = "Needs investigation. [NR: Best practices for rate limiting.]"
        result = detect_nr_markers(text)
        assert any("[NR:" in item for item in result), (
            f"Expected result items to contain '[NR:', got {result!r}"
        )

    def test_detects_multiple_nr_markers(self):
        """FR-NR: Multiple [NR:] markers in the same text are all detected."""
        text = (
            "[NR: Research OAuth providers.] Some text. "
            "[NR: Investigate caching strategies.] More text."
        )
        result = detect_nr_markers(text)
        assert len(result) == 2, f"Expected 2 matches, got {len(result)}"

    def test_no_false_positive_without_nr_marker(self):
        """FR-NR: Text without [NR:] markers returns an empty list."""
        text = "All requirements are well-defined and researched already."
        result = detect_nr_markers(text)
        assert result == [], f"Expected [], got {result!r}"

    def test_nr_marker_content_is_captured(self):
        """FR-NR: The content after [NR: ...] is captured in the result."""
        marker_content = "Survey existing embedding libraries."
        text = f"[NR: {marker_content}]"
        result = detect_nr_markers(text)
        assert len(result) == 1
        assert marker_content in result[0], (
            f"Expected marker content '{marker_content}' in result, got {result[0]!r}"
        )

    def test_nr_marker_case_sensitive(self):
        """FR-NR: Detection is case-sensitive; [nr:] MUST NOT match [NR:]."""
        text = "[nr: lowercase marker should not match]"
        result = detect_nr_markers(text)
        assert result == [], (
            f"Lowercase [nr:] should not be detected, got {result!r}"
        )

    def test_nr_marker_without_colon_not_detected(self):
        """FR-NR: '[NR]' without a colon MUST NOT be detected."""
        text = "The [NR] tag without colon should not be detected."
        result = detect_nr_markers(text)
        assert result == [], (
            f"[NR] without colon should not be detected, got {result!r}"
        )

    def test_nr_marker_does_not_match_nc_marker(self):
        """FR-NR: [NR:] detection MUST NOT return [NC:] markers."""
        text = "[NC: Clarify the requirement.] [NR: Research the technology.]"
        result = detect_nr_markers(text)
        assert len(result) == 1, f"Expected 1 NR match, got {len(result)}"
        assert all("[NR:" in item for item in result), (
            f"Result should only contain NR markers, got {result!r}"
        )

    def test_nc_marker_does_not_match_nr_marker(self):
        """FR-NC/FR-NR: [NC:] detection MUST NOT return [NR:] markers."""
        text = "[NC: Clarify the requirement.] [NR: Research the technology.]"
        result = detect_nc_markers(text)
        assert len(result) == 1, f"Expected 1 NC match, got {len(result)}"
        assert all("[NC:" in item for item in result), (
            f"Result should only contain NC markers, got {result!r}"
        )

    def test_returns_list_type(self):
        """FR-NR: Return type is always a list, never None."""
        result = detect_nr_markers("some text without markers")
        assert isinstance(result, list), f"Expected list, got {type(result)}"


# ---------------------------------------------------------------------------
# Uncertainty: question_density
# ---------------------------------------------------------------------------


class TestQuestionDensity:
    """question_density MUST return the ratio of sentences containing '?'."""

    def test_returns_zero_for_empty_string(self):
        """Empty text has zero question density."""
        result = question_density("")
        assert result == 0.0, f"Expected 0.0 for empty string, got {result}"

    def test_returns_zero_for_no_questions(self):
        """Text with no question marks has density 0.0."""
        text = "This is a statement. Here is another statement. And a third."
        result = question_density(text)
        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_returns_one_for_all_questions(self):
        """Text where every sentence is a question has density 1.0."""
        text = "What is this? Who made it? When was it done?"
        result = question_density(text)
        assert result == 1.0, f"Expected 1.0 for all-question text, got {result}"

    def test_returns_float(self):
        """question_density always returns a float."""
        result = question_density("Is this a question?")
        assert isinstance(result, float), f"Expected float, got {type(result)}"

    def test_partial_question_density(self):
        """Two questions out of four sentences yields density 0.5."""
        text = "Statement one. Is this a question? Another statement. Really?"
        result = question_density(text)
        assert result == 0.5, f"Expected 0.5, got {result}"

    def test_single_question_sentence(self):
        """A single question sentence returns 1.0."""
        text = "Is this implemented correctly?"
        result = question_density(text)
        assert result == 1.0, f"Expected 1.0, got {result}"

    def test_single_statement_sentence(self):
        """A single non-question sentence returns 0.0."""
        text = "This is a clear statement."
        result = question_density(text)
        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_density_is_between_zero_and_one(self):
        """question_density MUST always return a value in [0.0, 1.0]."""
        texts = [
            "",
            "No questions here.",
            "Is this a question?",
            "One? Two. Three? Four.",
        ]
        for text in texts:
            result = question_density(text)
            assert 0.0 <= result <= 1.0, (
                f"Density {result} for text {text!r} is outside [0.0, 1.0]"
            )

    def test_text_with_only_question_marks_no_sentences(self):
        """Text that is purely question marks (edge case) does not crash."""
        result = question_density("???")
        assert isinstance(result, float), f"Expected float, got {type(result)}"


# ---------------------------------------------------------------------------
# Uncertainty: detect_tbd_todo
# ---------------------------------------------------------------------------


class TestDetectTbdTodo:
    """detect_tbd_todo MUST return a list of placeholder markers found in text."""

    def test_returns_empty_list_for_empty_string(self):
        """Empty text returns empty list."""
        result = detect_tbd_todo("")
        assert result == [], f"Expected [], got {result!r}"

    def test_detects_tbd_marker(self):
        """TBD anywhere in text is detected."""
        text = "The timeout value is TBD."
        result = detect_tbd_todo(text)
        assert len(result) >= 1, f"Expected at least 1 match for TBD, got {result!r}"

    def test_detects_todo_marker(self):
        """TODO anywhere in text is detected."""
        text = "TODO: implement the retry logic."
        result = detect_tbd_todo(text)
        assert len(result) >= 1, f"Expected at least 1 match for TODO, got {result!r}"

    def test_detects_fixme_marker(self):
        """FIXME anywhere in text is detected."""
        text = "FIXME: this approach breaks under load."
        result = detect_tbd_todo(text)
        assert len(result) >= 1, f"Expected at least 1 match for FIXME, got {result!r}"

    def test_detects_tbd_and_todo_together(self):
        """Both TBD and TODO in the same text are both detected."""
        text = "The rate limit is TBD and the caching strategy is TODO."
        result = detect_tbd_todo(text)
        assert len(result) == 2, f"Expected 2 matches, got {len(result)}: {result!r}"

    def test_no_false_positive_on_clean_text(self):
        """Clean text with no placeholders returns empty list."""
        text = "All requirements are fully specified and complete."
        result = detect_tbd_todo(text)
        assert result == [], f"Expected [], got {result!r}"

    def test_returns_list_type(self):
        """Return type is always list, never None."""
        result = detect_tbd_todo("no placeholders here")
        assert isinstance(result, list), f"Expected list, got {type(result)}"

    def test_tbd_is_case_sensitive(self):
        """'tbd' in lowercase MUST NOT be detected (markers are uppercase)."""
        text = "The value is tbd in the future."
        result = detect_tbd_todo(text)
        assert result == [], (
            f"Lowercase 'tbd' should not be detected, got {result!r}"
        )

    def test_todo_is_case_sensitive(self):
        """'todo' in lowercase MUST NOT be detected."""
        text = "I have a todo item in my notes."
        result = detect_tbd_todo(text)
        assert result == [], (
            f"Lowercase 'todo' should not be detected, got {result!r}"
        )

    def test_detects_tbd_inline_in_sentence(self):
        """TBD embedded in a longer sentence is still detected."""
        text = "The authentication mechanism (TBD) will be decided later."
        result = detect_tbd_todo(text)
        assert len(result) >= 1, f"Expected TBD to be detected inline, got {result!r}"

    def test_result_items_contain_marker_text(self):
        """Each result item MUST contain the placeholder keyword."""
        text = "Step 1: TODO. Step 2: TBD."
        result = detect_tbd_todo(text)
        assert len(result) == 2
        combined = " ".join(result)
        assert "TODO" in combined or "TBD" in combined, (
            f"Result items must reference detected markers, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Uncertainty: detect_hedging
# ---------------------------------------------------------------------------


class TestDetectHedging:
    """detect_hedging MUST return a list of hedging expressions found in text."""

    def test_returns_empty_list_for_empty_string(self):
        """Empty text returns empty list."""
        result = detect_hedging("")
        assert result == [], f"Expected [], got {result!r}"

    def test_detects_might(self):
        """'might' is a hedging expression and MUST be detected."""
        text = "This might cause performance issues."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'might' to be detected, got {result!r}"

    def test_detects_perhaps(self):
        """'perhaps' is a hedging expression and MUST be detected."""
        text = "Perhaps we should use a different approach."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'perhaps' to be detected, got {result!r}"

    def test_detects_possibly(self):
        """'possibly' is a hedging expression and MUST be detected."""
        text = "This could possibly lead to data loss."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'possibly' to be detected, got {result!r}"

    def test_detects_it_seems(self):
        """'it seems' is a hedging expression and MUST be detected."""
        text = "It seems the timeout is too low."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'it seems' to be detected, got {result!r}"

    def test_detects_not_sure(self):
        """'not sure' is a hedging expression and MUST be detected."""
        text = "I'm not sure whether to use REST or GraphQL."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'not sure' to be detected, got {result!r}"

    def test_detects_unclear(self):
        """'unclear' is a hedging expression and MUST be detected."""
        text = "It is unclear how the cache should be invalidated."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'unclear' to be detected, got {result!r}"

    def test_no_false_positive_on_confident_text(self):
        """Text with no hedging language returns an empty list."""
        text = "The system uses PostgreSQL. The API is RESTful. Authentication uses JWT."
        result = detect_hedging(text)
        assert result == [], f"Expected [], got {result!r}"

    def test_returns_list_type(self):
        """Return type is always list, never None."""
        result = detect_hedging("no hedging here")
        assert isinstance(result, list), f"Expected list, got {type(result)}"

    def test_detects_multiple_hedging_expressions(self):
        """Multiple hedging expressions in the same text are all detected."""
        text = "Perhaps this might work, but it is unclear and not sure."
        result = detect_hedging(text)
        assert len(result) >= 2, (
            f"Expected at least 2 hedging matches, got {len(result)}: {result!r}"
        )

    def test_hedging_detection_is_case_insensitive(self):
        """Hedging detection MUST work regardless of casing (Might, MIGHT, might)."""
        texts = [
            "This Might be an issue.",
            "PERHAPS we should reconsider.",
            "It Seems like the wrong approach.",
        ]
        for text in texts:
            result = detect_hedging(text)
            assert len(result) >= 1, (
                f"Expected hedging to be detected in {text!r}, got {result!r}"
            )

    def test_detects_maybe(self):
        """'maybe' is a hedging expression and MUST be detected."""
        text = "Maybe the timeout should be configurable."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'maybe' to be detected, got {result!r}"

    def test_detects_could_be(self):
        """'could be' is a hedging expression and MUST be detected."""
        text = "This could be a bottleneck under high load."
        result = detect_hedging(text)
        assert len(result) >= 1, f"Expected 'could be' to be detected, got {result!r}"

    def test_result_items_contain_matched_expression(self):
        """Each result item MUST contain or identify the hedging expression found."""
        text = "Perhaps this might not work."
        result = detect_hedging(text)
        assert len(result) >= 1
        # At minimum one item must carry meaningful content (not empty string)
        assert all(item.strip() != "" for item in result), (
            f"Result items must not be empty strings, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Combined analysis: analyse
# ---------------------------------------------------------------------------


class TestAnalyse:
    """analyse MUST return a structured dict with all perception findings."""

    def test_returns_dict(self):
        """analyse always returns a dict."""
        result = analyse("some text")
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    def test_result_has_nc_markers_key(self):
        """The result dict MUST have a 'nc_markers' key."""
        result = analyse("some text")
        assert "nc_markers" in result, (
            f"Expected 'nc_markers' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_nr_markers_key(self):
        """The result dict MUST have a 'nr_markers' key."""
        result = analyse("some text")
        assert "nr_markers" in result, (
            f"Expected 'nr_markers' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_question_density_key(self):
        """The result dict MUST have a 'question_density' key."""
        result = analyse("some text")
        assert "question_density" in result, (
            f"Expected 'question_density' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_tbd_todo_key(self):
        """The result dict MUST have a 'tbd_todo' key."""
        result = analyse("some text")
        assert "tbd_todo" in result, (
            f"Expected 'tbd_todo' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_hedging_key(self):
        """The result dict MUST have a 'hedging' key."""
        result = analyse("some text")
        assert "hedging" in result, (
            f"Expected 'hedging' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_needs_clarification_key(self):
        """The result dict MUST have a 'needs_clarification' boolean key."""
        result = analyse("some text")
        assert "needs_clarification" in result, (
            f"Expected 'needs_clarification' key in result, got keys: {list(result.keys())}"
        )

    def test_result_has_needs_research_key(self):
        """The result dict MUST have a 'needs_research' boolean key."""
        result = analyse("some text")
        assert "needs_research" in result, (
            f"Expected 'needs_research' key in result, got keys: {list(result.keys())}"
        )

    def test_nc_markers_value_is_list(self):
        """analyse result 'nc_markers' MUST be a list."""
        result = analyse("[NC: something]")
        assert isinstance(result["nc_markers"], list), (
            f"Expected list for 'nc_markers', got {type(result['nc_markers'])}"
        )

    def test_nr_markers_value_is_list(self):
        """analyse result 'nr_markers' MUST be a list."""
        result = analyse("[NR: something]")
        assert isinstance(result["nr_markers"], list), (
            f"Expected list for 'nr_markers', got {type(result['nr_markers'])}"
        )

    def test_question_density_value_is_float(self):
        """analyse result 'question_density' MUST be a float."""
        result = analyse("Is this working?")
        assert isinstance(result["question_density"], float), (
            f"Expected float for 'question_density', got {type(result['question_density'])}"
        )

    def test_tbd_todo_value_is_list(self):
        """analyse result 'tbd_todo' MUST be a list."""
        result = analyse("TBD")
        assert isinstance(result["tbd_todo"], list), (
            f"Expected list for 'tbd_todo', got {type(result['tbd_todo'])}"
        )

    def test_hedging_value_is_list(self):
        """analyse result 'hedging' MUST be a list."""
        result = analyse("maybe this works")
        assert isinstance(result["hedging"], list), (
            f"Expected list for 'hedging', got {type(result['hedging'])}"
        )

    def test_needs_clarification_true_when_nc_marker_present(self):
        """FR-NC: needs_clarification MUST be True when [NC:] markers are present."""
        text = "Some context. [NC: What is the expected throughput?]"
        result = analyse(text)
        assert result["needs_clarification"] is True, (
            f"Expected needs_clarification=True when NC marker present, "
            f"got {result['needs_clarification']}"
        )

    def test_needs_clarification_false_when_no_nc_marker(self):
        """FR-NC: needs_clarification MUST be False when no [NC:] markers exist."""
        text = "This requirement is fully specified."
        result = analyse(text)
        assert result["needs_clarification"] is False, (
            f"Expected needs_clarification=False for clean text, "
            f"got {result['needs_clarification']}"
        )

    def test_needs_research_true_when_nr_marker_present(self):
        """FR-NR: needs_research MUST be True when [NR:] markers are present."""
        text = "Some context. [NR: Research vector database options.]"
        result = analyse(text)
        assert result["needs_research"] is True, (
            f"Expected needs_research=True when NR marker present, "
            f"got {result['needs_research']}"
        )

    def test_needs_research_false_when_no_nr_marker(self):
        """FR-NR: needs_research MUST be False when no [NR:] markers exist."""
        text = "This is well-researched and complete."
        result = analyse(text)
        assert result["needs_research"] is False, (
            f"Expected needs_research=False for clean text, "
            f"got {result['needs_research']}"
        )

    def test_nc_markers_populated_from_text(self):
        """analyse 'nc_markers' MUST reflect detect_nc_markers result."""
        text = "[NC: What is the SLA?]"
        result = analyse(text)
        assert len(result["nc_markers"]) == 1, (
            f"Expected 1 NC marker in result, got {result['nc_markers']!r}"
        )

    def test_nr_markers_populated_from_text(self):
        """analyse 'nr_markers' MUST reflect detect_nr_markers result."""
        text = "[NR: Investigate cloud providers.]"
        result = analyse(text)
        assert len(result["nr_markers"]) == 1, (
            f"Expected 1 NR marker in result, got {result['nr_markers']!r}"
        )

    def test_analyse_empty_text_returns_clean_result(self):
        """analyse('') returns a dict with all zero/false/empty values."""
        result = analyse("")
        assert result["nc_markers"] == []
        assert result["nr_markers"] == []
        assert result["question_density"] == 0.0
        assert result["tbd_todo"] == []
        assert result["hedging"] == []
        assert result["needs_clarification"] is False
        assert result["needs_research"] is False

    def test_analyse_complex_text_aggregates_all_findings(self):
        """analyse on text with multiple signals aggregates all correctly."""
        text = (
            "[NC: What is the retry count?] "
            "[NR: Research rate limiting algorithms.] "
            "Maybe TBD. Is this clear? Perhaps not."
        )
        result = analyse(text)
        assert len(result["nc_markers"]) == 1
        assert len(result["nr_markers"]) == 1
        assert result["needs_clarification"] is True
        assert result["needs_research"] is True
        assert len(result["tbd_todo"]) >= 1
        assert len(result["hedging"]) >= 1
        assert result["question_density"] > 0.0

    def test_analyse_result_question_density_matches_text(self):
        """The question_density in analyse result matches stand-alone computation."""
        text = "Is this done? Yes it is."
        result = analyse(text)
        standalone = question_density(text)
        assert result["question_density"] == standalone, (
            f"analyse question_density {result['question_density']} != "
            f"standalone {standalone}"
        )
