"""Unit tests for orchestrator/checks/ci.py — CICheckStrategy.

Requirements covered:
  FR-013: CICheckStrategy implements CheckStrategy for CI-based test execution.
  FR-015: Stack scoping — filters CI jobs to only those relevant to the task's
          technology stack.  (SPEC-032, SPEC-111)
  FR-016: CI job status 'skipped' or 'cancelled' MUST NOT be treated as passing;
          each status has a defined failure condition.  (SPEC-033)
  FR-017: CI error logs are structured per-job, max 2000 chars per job.
          (SPEC-034)
  FR-018: CI job name matching uses startswith prefix matching.  (SPEC-034)
  FR-045: Technology registry extensible via config (not hardcoded if-elif).
          (SPEC-113, SPEC-114)
  FR-046: File classification uses both extension and path prefix.  (SPEC-112)
  FR-047: CI job name mapping loaded from configuration.  (SPEC-114)

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/checks/ci.py provides a complete implementation.

Test areas:
  A. Import / ABC contract
  B. Instantiation with config
  C. Stack scoping — job filtering
  D. Extensible technology registry via config
  E. CI job name startswith matching
  F. Skipped / cancelled handling
  G. 2000-char per-job error budget
  H. evaluate() return contract
  I. tests_must_fail / tests_must_pass integration
  J. Edge cases
"""

from __future__ import annotations

import pytest

from orchestrator.checks.base import CheckStrategy
from orchestrator.checks.ci import CICheckStrategy


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

MINIMAL_CONFIG: dict = {
    "technology_registry": {
        "python": ["pytest", "mypy", "ruff"],
        "typescript": ["jest", "tsc", "eslint"],
    }
}

EXTENDED_CONFIG: dict = {
    "technology_registry": {
        "python": ["pytest", "mypy", "ruff"],
        "typescript": ["jest", "tsc", "eslint"],
        "rust": ["cargo-test", "clippy"],
        "go": ["go-test", "golangci-lint"],
    }
}


def _make_job(name: str, status: str, output: str = "") -> dict:
    """Helper to construct a CI job result dict."""
    return {"name": name, "status": status, "output": output}


def _make_strategy(config: dict | None = None) -> CICheckStrategy:
    """Construct a CICheckStrategy with the given config."""
    return CICheckStrategy(config=config or MINIMAL_CONFIG)


# ---------------------------------------------------------------------------
# A. Import / ABC contract
# ---------------------------------------------------------------------------


class TestCICheckStrategyImportAndABC:
    """FR-013: CICheckStrategy must be importable and satisfy CheckStrategy ABC."""

    def test_FR013_ci_check_strategy_is_importable(self):
        """CICheckStrategy must be importable from orchestrator.checks.ci."""
        # Import already happened at module level; reaching here confirms it
        assert CICheckStrategy is not None

    def test_FR013_ci_check_strategy_is_subclass_of_check_strategy(self):
        """CICheckStrategy must subclass CheckStrategy (Liskov substitution)."""
        assert issubclass(CICheckStrategy, CheckStrategy)

    def test_FR013_ci_check_strategy_instance_is_check_strategy(self):
        """An instance of CICheckStrategy must satisfy isinstance(CheckStrategy)."""
        strategy = _make_strategy()
        assert isinstance(strategy, CheckStrategy)

    def test_FR013_ci_check_strategy_has_tests_must_fail(self):
        """CICheckStrategy must expose tests_must_fail as a callable method."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "tests_must_fail", None))

    def test_FR013_ci_check_strategy_has_tests_must_pass(self):
        """CICheckStrategy must expose tests_must_pass as a callable method."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "tests_must_pass", None))

    def test_FR013_ci_check_strategy_has_evaluate(self):
        """CICheckStrategy must expose an evaluate() method."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "evaluate", None))


# ---------------------------------------------------------------------------
# B. Instantiation with config
# ---------------------------------------------------------------------------


class TestCICheckStrategyInstantiation:
    """CICheckStrategy must accept a config dict on construction."""

    def test_instantiation_with_minimal_config(self):
        """CICheckStrategy(config=MINIMAL_CONFIG) must not raise."""
        strategy = CICheckStrategy(config=MINIMAL_CONFIG)
        assert strategy is not None

    def test_instantiation_with_extended_config(self):
        """CICheckStrategy must accept configs with many technology entries."""
        strategy = CICheckStrategy(config=EXTENDED_CONFIG)
        assert strategy is not None

    def test_instantiation_with_empty_technology_registry(self):
        """Empty technology_registry in config must be accepted without error."""
        strategy = CICheckStrategy(config={"technology_registry": {}})
        assert strategy is not None

    def test_instantiation_stores_config(self):
        """The config passed at construction must be retrievable or influence behaviour."""
        strategy = CICheckStrategy(config=EXTENDED_CONFIG)
        # The strategy must at minimum support evaluate() without error
        result = strategy.evaluate(ci_results=[], stack="rust")
        # evaluate() must return a dict — confirms config was accepted
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# C. Stack scoping — job filtering (FR-015)
# ---------------------------------------------------------------------------


class TestStackScoping:
    """FR-015: evaluate() must filter CI jobs by stack scope."""

    def test_FR015_jobs_for_matching_stack_are_included(self):
        """Jobs whose name starts with a python pattern must appear in python results."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("jest-unit", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "pytest-unit" in job_names

    def test_FR015_jobs_for_other_stack_are_excluded(self):
        """Jobs not matching the requested stack must be excluded from evaluation."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("jest-unit", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "jest-unit" not in job_names

    def test_FR015_stack_none_evaluates_all_jobs(self):
        """When stack=None, all jobs must be evaluated (no filtering)."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("jest-unit", "success"),
            _make_job("cargo-test-unit", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack=None)
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 3

    def test_FR015_unknown_stack_evaluates_zero_jobs(self):
        """An unregistered stack name must result in zero jobs being evaluated."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="cobol")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 0

    def test_FR015_typescript_stack_filters_correctly(self):
        """Stack='typescript' must only include jest/tsc/eslint prefixed jobs."""
        strategy = _make_strategy()
        jobs = [
            _make_job("jest-unit", "success"),
            _make_job("tsc-check", "success"),
            _make_job("eslint-src", "success"),
            _make_job("pytest-unit", "success"),
            _make_job("mypy-src", "failure"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="typescript")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "jest-unit" in job_names
        assert "tsc-check" in job_names
        assert "eslint-src" in job_names
        assert "pytest-unit" not in job_names
        assert "mypy-src" not in job_names


# ---------------------------------------------------------------------------
# D. Extensible technology registry via config (FR-045, FR-047)
# ---------------------------------------------------------------------------


class TestExtensibleTechnologyRegistry:
    """FR-045, FR-047: Registry is driven by config, not hardcoded if-elif."""

    def test_FR045_new_technology_added_via_config_is_recognised(self):
        """A 'go' technology added in config must be handled without code change."""
        strategy = CICheckStrategy(config=EXTENDED_CONFIG)
        jobs = [
            _make_job("go-test-integration", "success"),
            _make_job("pytest-unit", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="go")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "go-test-integration" in job_names
        assert "pytest-unit" not in job_names

    def test_FR047_job_name_patterns_loaded_from_config_not_hardcoded(self):
        """Overriding a technology's patterns in config must change which jobs match."""
        custom_config = {
            "technology_registry": {
                "python": ["custom-py-runner"],  # overrides default "pytest" prefix
            }
        }
        strategy = CICheckStrategy(config=custom_config)
        jobs = [
            _make_job("custom-py-runner-unit", "success"),
            _make_job("pytest-standard", "success"),  # would match default, not custom
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "custom-py-runner-unit" in job_names
        assert "pytest-standard" not in job_names

    def test_FR045_rust_technology_in_config_filters_correctly(self):
        """rust stack from EXTENDED_CONFIG must filter cargo-test and clippy jobs."""
        strategy = CICheckStrategy(config=EXTENDED_CONFIG)
        jobs = [
            _make_job("cargo-test-release", "success"),
            _make_job("clippy-check", "success"),
            _make_job("jest-unit", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="rust")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "cargo-test-release" in job_names
        assert "clippy-check" in job_names
        assert "jest-unit" not in job_names

    def test_FR045_multiple_patterns_for_same_technology(self):
        """A technology with multiple patterns must match jobs starting with any."""
        strategy = _make_strategy()  # python: ["pytest", "mypy", "ruff"]
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-strict", "success"),
            _make_job("ruff-lint", "success"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 3


# ---------------------------------------------------------------------------
# E. CI job name startswith matching (FR-018)
# ---------------------------------------------------------------------------


class TestStartswithMatching:
    """FR-018: Job names must be matched using startswith, not substring."""

    def test_FR018_job_starting_with_pattern_matches(self):
        """'pytest-unit' starts with 'pytest' → must be included for python stack."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 1
        assert evaluated[0]["name"] == "pytest-unit"

    def test_FR018_job_containing_pattern_in_middle_does_not_match(self):
        """'run-pytest-unit' contains 'pytest' but does not start with it → excluded."""
        strategy = _make_strategy()
        jobs = [_make_job("run-pytest-unit", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 0

    def test_FR018_job_ending_with_pattern_does_not_match(self):
        """'unit-pytest' ends with 'pytest' but does not start with it → excluded."""
        strategy = _make_strategy()
        jobs = [_make_job("unit-pytest", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 0

    def test_FR018_exact_pattern_name_matches(self):
        """A job whose name equals the pattern exactly must match."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 1

    def test_FR018_startswith_is_case_sensitive(self):
        """'Pytest-unit' must NOT match pattern 'pytest' (case-sensitive startswith)."""
        strategy = _make_strategy()
        jobs = [_make_job("Pytest-unit", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert len(evaluated) == 0

    def test_FR018_multiple_patterns_each_use_startswith(self):
        """All patterns in a technology use startswith individually."""
        strategy = _make_strategy()  # python: ["pytest", "mypy", "ruff"]
        jobs = [
            _make_job("pytest-ci", "success"),      # starts with pytest → match
            _make_job("run-mypy", "success"),        # contains mypy but doesn't start → no match
            _make_job("ruff-check", "success"),      # starts with ruff → match
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job_names = [j["name"] for j in evaluated]
        assert "pytest-ci" in job_names
        assert "run-mypy" not in job_names
        assert "ruff-check" in job_names


# ---------------------------------------------------------------------------
# F. Skipped / cancelled handling (FR-016)
# ---------------------------------------------------------------------------


class TestSkippedCancelledHandling:
    """FR-016: 'skipped' and 'cancelled' jobs must NOT be treated as passing."""

    def test_FR016_skipped_job_does_not_count_as_passing(self):
        """A skipped job in scope must not contribute to an overall pass result."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "skipped")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is False

    def test_FR016_cancelled_job_does_not_count_as_passing(self):
        """A cancelled job in scope must not contribute to an overall pass result."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "cancelled")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is False

    def test_FR016_skipped_job_is_reported_in_result(self):
        """A skipped job must appear in the result with its status preserved."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "skipped")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert any(j["name"] == "pytest-unit" and j["status"] == "skipped"
                   for j in evaluated)

    def test_FR016_cancelled_job_is_reported_in_result(self):
        """A cancelled job must appear in the result with its status preserved."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "cancelled")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        assert any(j["name"] == "pytest-unit" and j["status"] == "cancelled"
                   for j in evaluated)

    def test_FR016_skipped_does_not_block_but_is_flagged(self):
        """Skipped job must not be classified the same as a successful job."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "skipped")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        # The job must not appear as "passed"
        evaluated = result["evaluated_jobs"]
        skipped_job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert skipped_job.get("status") != "success"

    def test_FR016_successful_job_alongside_skipped_still_not_passing_overall(self):
        """If any in-scope job is skipped, overall result is not fully passing."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-check", "skipped"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        # skipped prevents a clean pass
        assert result["passed"] is False

    def test_FR016_all_in_scope_success_jobs_pass(self):
        """All in-scope jobs with 'success' status → overall result is passed."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-check", "success"),
            _make_job("jest-ci", "failure"),  # out-of-scope for python
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is True

    def test_FR016_failed_job_marks_result_as_failed(self):
        """An in-scope job with 'failure' status must mark overall result as failed."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output="AssertionError: test failed")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# G. 2000-char per-job error budget (FR-017)
# ---------------------------------------------------------------------------


class TestPerJobErrorBudget:
    """FR-017: Error output per job must be capped at 2000 characters."""

    def test_FR017_short_output_is_preserved_unchanged(self):
        """Output under 2000 chars must be preserved fully."""
        short_output = "AssertionError: expected True, got False"
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output=short_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert short_output in job["output"]

    def test_FR017_long_output_is_truncated_to_2000_chars(self):
        """Output exceeding 2000 chars must be truncated to at most 2000 chars."""
        long_output = "E" * 5000
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output=long_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert len(job["output"]) <= 2000

    def test_FR017_output_at_exactly_2000_chars_is_not_truncated(self):
        """Output of exactly 2000 chars must be preserved without further truncation."""
        exact_output = "X" * 2000
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output=exact_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert len(job["output"]) == 2000

    def test_FR017_output_at_2001_chars_is_truncated(self):
        """Output of 2001 chars must be truncated to at most 2000 chars."""
        over_output = "Y" * 2001
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output=over_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert len(job["output"]) <= 2000

    def test_FR017_truncation_is_independent_per_job(self):
        """Each job has its own 2000-char budget, not a shared pool."""
        long_output = "Z" * 5000
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "failure", output=long_output),
            _make_job("mypy-check", "failure", output=long_output),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        for job in evaluated:
            assert len(job["output"]) <= 2000, (
                f"Job {job['name']} exceeded 2000-char budget"
            )

    def test_FR017_empty_output_is_preserved(self):
        """A job with empty output must remain empty after truncation logic."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output="")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert job["output"] == ""

    def test_FR017_success_job_output_also_capped(self):
        """Even successful jobs with verbose output must be capped at 2000 chars."""
        long_output = "." * 9999  # very verbose passing output
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "success", output=long_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unit")
        assert len(job["output"]) <= 2000


# ---------------------------------------------------------------------------
# H. evaluate() return contract
# ---------------------------------------------------------------------------


class TestEvaluateReturnContract:
    """evaluate() must return a structured dict with required keys."""

    def test_evaluate_returns_dict(self):
        """evaluate() must return a dict."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack="python")
        assert isinstance(result, dict)

    def test_evaluate_result_contains_passed_key(self):
        """evaluate() result must contain a 'passed' boolean key."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack="python")
        assert "passed" in result
        assert isinstance(result["passed"], bool)

    def test_evaluate_result_contains_evaluated_jobs_key(self):
        """evaluate() result must contain an 'evaluated_jobs' list key."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack="python")
        assert "evaluated_jobs" in result
        assert isinstance(result["evaluated_jobs"], list)

    def test_evaluate_empty_jobs_with_no_stack_returns_passed_true(self):
        """No jobs to evaluate and stack=None → passed=True (vacuously)."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack=None)
        assert result["passed"] is True

    def test_evaluate_empty_jobs_with_known_stack_returns_passed_true(self):
        """No matching jobs for a known stack → passed=True (nothing failed)."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack="python")
        assert result["passed"] is True

    def test_evaluate_each_evaluated_job_has_name_status_output(self):
        """Every entry in evaluated_jobs must carry 'name', 'status', 'output'."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "success", output="1 passed")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        for job in result["evaluated_jobs"]:
            assert "name" in job
            assert "status" in job
            assert "output" in job

    def test_evaluate_result_may_contain_summary_or_errors(self):
        """evaluate() result may optionally carry 'errors' or 'summary' keys."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "failure", output="test failed")]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        # Either 'errors' or a non-empty evaluated_jobs signals the failure
        has_errors_key = "errors" in result
        has_failing_job = any(
            j["status"] not in ("success",) for j in result["evaluated_jobs"]
        )
        assert has_errors_key or has_failing_job


# ---------------------------------------------------------------------------
# I. tests_must_fail / tests_must_pass integration
# ---------------------------------------------------------------------------


class TestTestsMustFailAndMustPass:
    """CICheckStrategy must honour the CheckStrategy ABC contract via evaluate()."""

    def test_tests_must_fail_returns_bool(self):
        """tests_must_fail must return a bool."""
        strategy = _make_strategy()
        # Provide a no-op command; implementation will use evaluate() internally
        result = strategy.tests_must_fail(task_id="T011", command="npm test")
        assert isinstance(result, bool)

    def test_tests_must_pass_returns_bool(self):
        """tests_must_pass must return a bool."""
        strategy = _make_strategy()
        result = strategy.tests_must_pass(task_id="T011", command="npm test")
        assert isinstance(result, bool)

    def test_tests_must_fail_accepts_task_id_and_command(self):
        """tests_must_fail signature must accept task_id and command kwargs."""
        strategy = _make_strategy()
        # Must not raise TypeError for these arguments
        strategy.tests_must_fail(task_id="T011", command="npm test")

    def test_tests_must_pass_accepts_task_id_and_command(self):
        """tests_must_pass signature must accept task_id and command kwargs."""
        strategy = _make_strategy()
        strategy.tests_must_pass(task_id="T011", command="npm test")


# ---------------------------------------------------------------------------
# J. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge and boundary cases for CICheckStrategy."""

    def test_empty_ci_results_list(self):
        """evaluate() must handle an empty ci_results list without raising."""
        strategy = _make_strategy()
        result = strategy.evaluate(ci_results=[], stack="python")
        assert isinstance(result, dict)

    def test_ci_results_with_no_matching_jobs_for_stack(self):
        """evaluate() with no matching jobs must return passed=True and empty list."""
        strategy = _make_strategy()
        jobs = [_make_job("jest-unit", "failure")]  # typescript, not python
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is True
        assert result["evaluated_jobs"] == []

    def test_large_number_of_jobs_does_not_raise(self):
        """evaluate() must handle 1000 jobs without error."""
        strategy = _make_strategy()
        jobs = [_make_job(f"pytest-job-{i}", "success") for i in range(1000)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is True
        assert len(result["evaluated_jobs"]) == 1000

    def test_job_with_unicode_output_is_handled(self):
        """Unicode characters in job output must be preserved (not mangled)."""
        unicode_output = "失败: 断言错误 — échec du test — エラー" * 50
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unicode", "failure", output=unicode_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-unicode")
        # Output must be a non-empty string (possibly truncated) and still valid
        assert isinstance(job["output"], str)
        assert len(job["output"]) > 0

    def test_job_output_with_special_characters(self):
        """SQL injection-style and shell metacharacters in output must be safe."""
        special_output = "'; DROP TABLE jobs; --\n$(rm -rf /)\n<script>alert(1)</script>"
        strategy = _make_strategy()
        jobs = [_make_job("pytest-special", "failure", output=special_output)]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        evaluated = result["evaluated_jobs"]
        job = next(j for j in evaluated if j["name"] == "pytest-special")
        # Must not raise; output preserved (possibly truncated)
        assert isinstance(job["output"], str)

    def test_stack_with_no_patterns_evaluates_zero_jobs(self):
        """A registered technology with an empty pattern list matches nothing."""
        config = {"technology_registry": {"empty-stack": []}}
        strategy = CICheckStrategy(config=config)
        jobs = [_make_job("anything-job", "success")]
        result = strategy.evaluate(ci_results=jobs, stack="empty-stack")
        assert result["evaluated_jobs"] == []

    def test_multiple_failed_jobs_all_appear_in_result(self):
        """All failing in-scope jobs must appear in evaluated_jobs."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "failure", output="fail1"),
            _make_job("mypy-check", "failure", output="fail2"),
            _make_job("ruff-lint", "failure", output="fail3"),
        ]
        result = strategy.evaluate(ci_results=jobs, stack="python")
        assert result["passed"] is False
        assert len(result["evaluated_jobs"]) == 3

    def test_config_without_technology_registry_key(self):
        """A config dict missing 'technology_registry' must not raise at construction."""
        strategy = CICheckStrategy(config={})
        # With no registry, evaluate must still return a valid dict
        result = strategy.evaluate(ci_results=[], stack=None)
        assert isinstance(result, dict)

    def test_evaluate_called_multiple_times_is_idempotent(self):
        """Calling evaluate() twice with the same args must return equal results."""
        strategy = _make_strategy()
        jobs = [_make_job("pytest-unit", "success", output="1 passed")]
        result1 = strategy.evaluate(ci_results=jobs, stack="python")
        result2 = strategy.evaluate(ci_results=jobs, stack="python")
        assert result1["passed"] == result2["passed"]
        assert len(result1["evaluated_jobs"]) == len(result2["evaluated_jobs"])
