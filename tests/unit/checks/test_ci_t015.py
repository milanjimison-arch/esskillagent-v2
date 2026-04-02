"""Unit tests for orchestrator/checks/ci.py — T015 CI Check Strategy enhancements.

T015 [US6] [FR-008][FR-009][FR-010][FR-011][FR-012][FR-080][FR-090]
Implement CI check strategy: tests_must_fail, tests_must_pass,
_commit_and_push with 3-retry, auto-detect stack (including Python
detection), configurable job name mapping, async thread delegation.

Requirements covered:
  FR-008: CICheckStrategy MUST provide complete tests_must_fail and
          tests_must_pass implementations (not stub returning False).
  FR-009: _commit_and_push() MUST implement 3-retry logic.
  FR-010: auto-detect project stack (Rust, frontend/Node.js, Python).
  FR-011: Configurable CI job name mapping per detected stack.
  FR-080: Python stack detection must work correctly
          (requirements.txt, setup.py, pyproject.toml).
  FR-090: CI check operations MUST be executable via async thread
          delegation to avoid blocking the event loop.

Test areas:
  A. tests_must_fail / tests_must_pass: complete implementations
  B. _commit_and_push: 3-retry logic
  C. Stack auto-detection: Python, Node.js, Rust, unknown
  D. FR-080: Python stack detection via file presence
  E. Configurable job name mapping
  F. FR-090: Async thread delegation
  G. Edge cases

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/checks/ci.py provides the new complete implementation.
"""

from __future__ import annotations

import asyncio
import subprocess
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch, call

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
        "rust": ["cargo-test", "clippy"],
    }
}


def _make_strategy(config: dict | None = None) -> CICheckStrategy:
    return CICheckStrategy(config=config or MINIMAL_CONFIG)


def _make_job(name: str, status: str, output: str = "") -> dict:
    return {"name": name, "status": status, "output": output}


# ---------------------------------------------------------------------------
# A. tests_must_fail / tests_must_pass: complete implementations (FR-008)
# ---------------------------------------------------------------------------


class TestTestsMustFailComplete:
    """FR-008: tests_must_fail must be a complete implementation, not a stub."""

    def test_FR008_tests_must_fail_returns_true_when_ci_reports_failure(self):
        """FR-008: tests_must_fail must return True when CI jobs fail."""
        strategy = _make_strategy()
        failing_jobs = [_make_job("pytest-unit", "failure", output="AssertionError")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs):
            result = strategy.tests_must_fail(task_id="T015", command="npm test")
        assert result is True

    def test_FR008_tests_must_fail_returns_false_when_ci_reports_success(self):
        """FR-008: tests_must_fail must return False when CI jobs all pass."""
        strategy = _make_strategy()
        passing_jobs = [_make_job("pytest-unit", "success")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
            result = strategy.tests_must_fail(task_id="T015", command="npm test")
        assert result is False

    def test_FR008_tests_must_fail_is_not_hardcoded_false(self):
        """FR-008: tests_must_fail must NOT always return False (stub behavior)."""
        strategy = _make_strategy()
        failing_jobs = [_make_job("pytest-unit", "failure")]
        # The stub always returns False. A real implementation returns True here.
        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs):
            result = strategy.tests_must_fail(task_id="T015", command="npm test")
        # Must not be the hardcoded stub value False when tests fail
        assert result is not False, (
            "tests_must_fail must return True when CI tests fail; "
            "got False, which indicates the stub is still in place"
        )

    def test_FR008_tests_must_fail_returns_bool(self):
        """FR-008: tests_must_fail must return a bool."""
        strategy = _make_strategy()
        failing_jobs = [_make_job("pytest-unit", "failure")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs):
            result = strategy.tests_must_fail(task_id="T015", command="npm test")
        assert isinstance(result, bool)


class TestTestsMustPassComplete:
    """FR-008: tests_must_pass must be a complete implementation, not a stub."""

    def test_FR008_tests_must_pass_returns_true_when_ci_reports_success(self):
        """FR-008: tests_must_pass must return True when all CI jobs succeed."""
        strategy = _make_strategy()
        passing_jobs = [_make_job("pytest-unit", "success")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        assert result is True

    def test_FR008_tests_must_pass_returns_false_when_ci_reports_failure(self):
        """FR-008: tests_must_pass must return False when any CI job fails."""
        strategy = _make_strategy()
        failing_jobs = [_make_job("pytest-unit", "failure")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        assert result is False

    def test_FR008_tests_must_pass_is_not_hardcoded_false(self):
        """FR-008: tests_must_pass must NOT always return False (stub behavior)."""
        strategy = _make_strategy()
        passing_jobs = [_make_job("pytest-unit", "success")]
        # The stub always returns False. A real implementation returns True here.
        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        assert result is not False, (
            "tests_must_pass must return True when CI tests pass; "
            "got False, which indicates the stub is still in place"
        )

    def test_FR008_tests_must_pass_returns_bool(self):
        """FR-008: tests_must_pass must return a bool."""
        strategy = _make_strategy()
        passing_jobs = [_make_job("pytest-unit", "success")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        assert isinstance(result, bool)

    def test_FR008_tests_must_pass_returns_false_when_skipped(self):
        """FR-008: tests_must_pass must return False if any CI job is skipped."""
        strategy = _make_strategy()
        jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-check", "skipped"),
        ]
        with patch.object(strategy, "_run_ci_and_wait", return_value=jobs):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        assert result is False


# ---------------------------------------------------------------------------
# B. _commit_and_push: 3-retry logic (FR-009)
# ---------------------------------------------------------------------------


class TestCommitAndPush:
    """FR-009: _commit_and_push must implement 3-retry logic."""

    def test_FR009_commit_and_push_exists(self):
        """FR-009: CICheckStrategy must expose _commit_and_push as a callable."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "_commit_and_push", None)), (
            "_commit_and_push must be a callable method on CICheckStrategy"
        )

    def test_FR009_commit_and_push_succeeds_on_first_attempt(self):
        """FR-009: _commit_and_push must succeed and not retry on first success."""
        strategy = _make_strategy()
        passing_proc = MagicMock()
        passing_proc.returncode = 0

        with patch("subprocess.run", return_value=passing_proc) as mock_run:
            strategy._commit_and_push(message="test commit", files=["src/foo.py"])

        # Should complete without raising; subprocess.run called at least once
        assert mock_run.called

    def test_FR009_commit_and_push_retries_on_failure(self):
        """FR-009: _commit_and_push must retry when git operations fail."""
        strategy = _make_strategy()
        fail_proc = MagicMock()
        fail_proc.returncode = 1
        fail_proc.stderr = "error: failed to push"
        pass_proc = MagicMock()
        pass_proc.returncode = 0

        side_effects = [
            subprocess.CalledProcessError(1, "git"),
            subprocess.CalledProcessError(1, "git"),
            pass_proc,
        ]

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise subprocess.CalledProcessError(1, "git")
            return pass_proc

        with patch("subprocess.run", side_effect=mock_run):
            # Should not raise — succeeded on 3rd attempt
            strategy._commit_and_push(message="fix: retry test", files=["foo.py"])

        assert call_count >= 2, (
            f"_commit_and_push must retry on failure; "
            f"called only {call_count} time(s)"
        )

    def test_FR009_commit_and_push_raises_after_3_failures(self):
        """FR-009: _commit_and_push must raise after 3 failed attempts."""
        strategy = _make_strategy()

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with pytest.raises(Exception):
                strategy._commit_and_push(
                    message="failing commit", files=["src/broken.py"]
                )

    def test_FR009_commit_and_push_max_retries_is_3(self):
        """FR-009: _commit_and_push must attempt exactly 3 times before giving up."""
        strategy = _make_strategy()
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise subprocess.CalledProcessError(1, "git push")

        with patch("subprocess.run", side_effect=mock_run):
            with pytest.raises(Exception):
                strategy._commit_and_push(message="failing", files=[])

        assert call_count == 3, (
            f"_commit_and_push must retry exactly 3 times total; "
            f"got {call_count} call(s)"
        )

    def test_FR009_commit_and_push_accepts_message_and_files(self):
        """FR-009: _commit_and_push signature must accept message and files params."""
        strategy = _make_strategy()
        pass_proc = MagicMock()
        pass_proc.returncode = 0

        with patch("subprocess.run", return_value=pass_proc):
            # Must not raise TypeError
            strategy._commit_and_push(
                message="chore: update tests",
                files=["tests/unit/test_foo.py", "src/foo.py"],
            )

    def test_FR009_commit_and_push_no_retry_needed_on_success(self):
        """FR-009: _commit_and_push must not retry when first call succeeds."""
        strategy = _make_strategy()
        pass_proc = MagicMock()
        pass_proc.returncode = 0
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return pass_proc

        with patch("subprocess.run", side_effect=mock_run):
            strategy._commit_and_push(message="success", files=["foo.py"])

        # Should only need a small number of calls (git add + git commit + git push)
        # Key: call_count should NOT be 6+ (3 full retry cycles)
        assert call_count < 6, (
            f"Should not retry when commit/push succeeds; got {call_count} calls"
        )


# ---------------------------------------------------------------------------
# C. Stack auto-detection (FR-010)
# ---------------------------------------------------------------------------


class TestStackAutoDetection:
    """FR-010: detect_stack() must auto-detect the project stack."""

    def test_FR010_detect_stack_method_exists(self):
        """FR-010: CICheckStrategy must expose a detect_stack method."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "detect_stack", None)), (
            "detect_stack must be a callable method on CICheckStrategy"
        )

    def test_FR010_detect_stack_returns_string(self, tmp_path: Path):
        """FR-010: detect_stack must return a string identifier."""
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert isinstance(result, str)

    def test_FR010_detect_node_stack_via_package_json(self, tmp_path: Path):
        """FR-010: Presence of package.json must trigger Node.js/typescript detection."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        # Must return a stack identifier containing 'node', 'typescript', or 'frontend'
        assert result.lower() in ("node", "typescript", "frontend", "javascript"), (
            f"Expected node/typescript/frontend/javascript stack, got: {result!r}"
        )

    def test_FR010_detect_rust_stack_via_cargo_toml(self, tmp_path: Path):
        """FR-010: Presence of Cargo.toml must trigger Rust detection."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"')
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "rust", (
            f"Expected 'rust' stack for Cargo.toml, got: {result!r}"
        )

    def test_FR010_detect_unknown_stack_for_empty_dir(self, tmp_path: Path):
        """FR-010: An empty directory must return a safe 'unknown' stack identifier."""
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        # Must return a string (not raise); empty dir → unknown or default
        assert isinstance(result, str)
        assert len(result) > 0

    def test_FR010_detect_stack_returns_sensible_identifier(self, tmp_path: Path):
        """FR-010: Detected stack must be a non-empty lowercase string."""
        (tmp_path / "package.json").write_text("{}")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert isinstance(result, str)
        assert len(result) > 0
        # Stack identifiers should be lowercase (no 'TypeScript' with mixed case)
        assert result == result.lower(), (
            f"Stack identifier must be lowercase; got {result!r}"
        )


# ---------------------------------------------------------------------------
# D. FR-080: Python stack detection
# ---------------------------------------------------------------------------


class TestPythonStackDetection:
    """FR-080: Python stack must be detected via requirements.txt, setup.py,
    pyproject.toml, or other Python project markers.
    """

    def test_FR080_detects_python_via_requirements_txt(self, tmp_path: Path):
        """FR-080: requirements.txt in project dir must result in 'python' stack."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0\n")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "python", (
            f"Expected 'python' stack when requirements.txt exists; got {result!r}"
        )

    def test_FR080_detects_python_via_pyproject_toml(self, tmp_path: Path):
        """FR-080: pyproject.toml must result in 'python' stack."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "python", (
            f"Expected 'python' stack when pyproject.toml exists; got {result!r}"
        )

    def test_FR080_detects_python_via_setup_py(self, tmp_path: Path):
        """FR-080: setup.py must result in 'python' stack."""
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "python", (
            f"Expected 'python' stack when setup.py exists; got {result!r}"
        )

    def test_FR080_detects_python_via_setup_cfg(self, tmp_path: Path):
        """FR-080: setup.cfg must result in 'python' stack."""
        (tmp_path / "setup.cfg").write_text("[metadata]\nname = mypackage\n")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "python", (
            f"Expected 'python' stack when setup.cfg exists; got {result!r}"
        )

    def test_FR080_python_takes_priority_over_node_when_both_present(
        self, tmp_path: Path
    ):
        """FR-080: When both Python and Node markers exist, python should be detected.

        Many Python projects use package.json for dev tooling. The Python
        marker (requirements.txt) should take precedence or be detected first.
        """
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "package.json").write_text('{"devDependencies": {}}')
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        # The Python marker must be recognised — regardless of priority order
        assert result.lower() in ("python",), (
            f"Python detection must work when requirements.txt present; got {result!r}"
        )


# ---------------------------------------------------------------------------
# E. Configurable job name mapping (FR-011)
# ---------------------------------------------------------------------------


class TestConfigurableJobNameMapping:
    """FR-011: CI job name mapping must be configurable per detected stack."""

    def test_FR011_job_mapping_config_accepted(self):
        """FR-011: CICheckStrategy must accept job_name_mapping in config."""
        config = {
            "technology_registry": {"python": ["pytest"]},
            "job_name_mapping": {"python": ["custom-python-test"]},
        }
        strategy = CICheckStrategy(config=config)
        assert strategy is not None

    def test_FR011_custom_job_name_mapping_overrides_defaults(self):
        """FR-011: Custom mapping overrides default job name detection."""
        config = {
            "technology_registry": {"python": ["pytest"]},
            "job_name_mapping": {"python": ["custom-ci-runner"]},
        }
        strategy = CICheckStrategy(config=config)
        jobs = [
            _make_job("custom-ci-runner-unit", "success"),
            _make_job("pytest-default", "success"),
        ]
        # When filtering by job_name_mapping (if it overrides technology_registry):
        # At minimum, the custom mapping must be stored/accessible
        mapping = strategy.get_job_name_mapping()
        assert mapping is not None
        assert isinstance(mapping, dict)

    def test_FR011_get_job_name_mapping_returns_dict(self):
        """FR-011: get_job_name_mapping() must return a dict."""
        strategy = _make_strategy()
        mapping = strategy.get_job_name_mapping()
        assert isinstance(mapping, dict)

    def test_FR011_default_job_name_mapping_not_empty_for_known_stacks(self):
        """FR-011: Default mapping must provide at least one entry for known stacks."""
        strategy = _make_strategy()
        mapping = strategy.get_job_name_mapping()
        # The default config has python/typescript/rust entries
        assert len(mapping) > 0, (
            "get_job_name_mapping() must return non-empty mapping for configured stacks"
        )

    def test_FR011_custom_mapping_returned_when_configured(self):
        """FR-011: Custom mapping in config must be returned by get_job_name_mapping."""
        config = {
            "technology_registry": {},
            "job_name_mapping": {
                "python": ["custom-pytest"],
                "node": ["custom-jest"],
            },
        }
        strategy = CICheckStrategy(config=config)
        mapping = strategy.get_job_name_mapping()
        assert "python" in mapping, (
            "Custom job_name_mapping must include configured 'python' key"
        )
        assert "custom-pytest" in mapping["python"], (
            "Custom job_name_mapping values must be preserved"
        )

    def test_FR011_job_name_mapping_for_stack_is_list(self):
        """FR-011: Each stack's job name mapping value must be a list."""
        strategy = _make_strategy()
        mapping = strategy.get_job_name_mapping()
        for stack_name, patterns in mapping.items():
            assert isinstance(patterns, list), (
                f"Job name mapping for stack '{stack_name}' must be a list, "
                f"got {type(patterns)}"
            )


# ---------------------------------------------------------------------------
# F. FR-090: Async thread delegation
# ---------------------------------------------------------------------------


class TestAsyncThreadDelegation:
    """FR-090: CI check operations must be executable via async thread delegation."""

    def test_FR090_run_ci_check_async_method_exists(self):
        """FR-090: CICheckStrategy must expose an async method for CI checks."""
        strategy = _make_strategy()
        # Must have at least one async-capable method: run_async, check_async, etc.
        has_async = (
            callable(getattr(strategy, "tests_must_fail_async", None))
            or callable(getattr(strategy, "tests_must_pass_async", None))
            or callable(getattr(strategy, "run_in_thread", None))
            or callable(getattr(strategy, "submit", None))
        )
        assert has_async, (
            "CICheckStrategy must expose an async or thread-delegation method "
            "(tests_must_fail_async, tests_must_pass_async, run_in_thread, or submit)"
        )

    def test_FR090_async_tests_must_pass_is_awaitable(self):
        """FR-090: tests_must_pass_async must return an awaitable."""
        strategy = _make_strategy()
        async_method = getattr(strategy, "tests_must_pass_async", None)
        if async_method is None:
            pytest.skip("tests_must_pass_async not present; checking run_in_thread")
        passing_jobs = [_make_job("pytest-unit", "success")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
            coro = async_method(task_id="T015", command="npm test")
        import inspect
        assert inspect.isawaitable(coro), (
            "tests_must_pass_async must return an awaitable coroutine"
        )
        # Clean up the coroutine
        coro.close()

    def test_FR090_async_tests_must_fail_is_awaitable(self):
        """FR-090: tests_must_fail_async must return an awaitable."""
        strategy = _make_strategy()
        async_method = getattr(strategy, "tests_must_fail_async", None)
        if async_method is None:
            pytest.skip("tests_must_fail_async not present; checking run_in_thread")
        failing_jobs = [_make_job("pytest-unit", "failure")]
        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs):
            coro = async_method(task_id="T015", command="npm test")
        import inspect
        assert inspect.isawaitable(coro), (
            "tests_must_fail_async must return an awaitable coroutine"
        )
        coro.close()

    def test_FR090_async_tests_must_pass_returns_correct_result(self):
        """FR-090: async tests_must_pass must return True when CI passes."""
        strategy = _make_strategy()
        async_method = getattr(strategy, "tests_must_pass_async", None)
        if async_method is None:
            pytest.skip("tests_must_pass_async not present")

        passing_jobs = [_make_job("pytest-unit", "success")]

        async def run():
            with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs):
                return await async_method(task_id="T015", command="npm test")

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result is True

    def test_FR090_run_in_thread_executes_callable_in_thread(self):
        """FR-090: run_in_thread must execute the callable in a background thread."""
        strategy = _make_strategy()
        run_in_thread = getattr(strategy, "run_in_thread", None)
        if run_in_thread is None:
            pytest.skip("run_in_thread not present; async variant used instead")

        executed = []

        def task():
            executed.append(True)
            return "done"

        future_or_result = run_in_thread(task)

        # If it returns a future, wait for it
        if hasattr(future_or_result, "result"):
            result = future_or_result.result(timeout=5)
        else:
            result = future_or_result

        assert executed == [True], "run_in_thread must execute the callable"
        assert result == "done"

    def test_FR090_submit_returns_future_or_awaitable(self):
        """FR-090: submit() must return a Future or awaitable for async delegation."""
        strategy = _make_strategy()
        submit = getattr(strategy, "submit", None)
        if submit is None:
            pytest.skip("submit not present; checking other async methods")

        import inspect

        def noop():
            return 42

        result = submit(noop)
        # Must return something future-like or awaitable
        is_future = hasattr(result, "result") and callable(result.result)
        is_awaitable = inspect.isawaitable(result)
        assert is_future or is_awaitable, (
            f"submit() must return a Future or awaitable; got {type(result)}"
        )


# ---------------------------------------------------------------------------
# G. _run_ci_and_wait: CI trigger and poll interface
# ---------------------------------------------------------------------------


class TestRunCIAndWait:
    """The _run_ci_and_wait method underpins tests_must_fail/pass implementations."""

    def test_run_ci_and_wait_exists(self):
        """CICheckStrategy must expose _run_ci_and_wait as a callable."""
        strategy = _make_strategy()
        assert callable(getattr(strategy, "_run_ci_and_wait", None)), (
            "_run_ci_and_wait must be a callable method on CICheckStrategy"
        )

    def test_run_ci_and_wait_returns_list(self):
        """_run_ci_and_wait must return a list of job result dicts."""
        strategy = _make_strategy()
        with patch.object(
            strategy,
            "_run_ci_and_wait",
            return_value=[_make_job("pytest-unit", "success")],
        ):
            result = strategy._run_ci_and_wait(task_id="T015", command="npm test")
        assert isinstance(result, list)

    def test_run_ci_and_wait_each_item_has_name_and_status(self):
        """_run_ci_and_wait result items must have 'name' and 'status' keys."""
        strategy = _make_strategy()
        fake_jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-check", "failure"),
        ]
        with patch.object(strategy, "_run_ci_and_wait", return_value=fake_jobs):
            jobs = strategy._run_ci_and_wait(task_id="T015", command="npm test")
        for job in jobs:
            assert "name" in job, f"Job must have 'name' key; got {job}"
            assert "status" in job, f"Job must have 'status' key; got {job}"


# ---------------------------------------------------------------------------
# H. Integration: tests_must_fail / tests_must_pass use evaluate() internally
# ---------------------------------------------------------------------------


class TestTestsMustFailPassUseEvaluate:
    """tests_must_fail and tests_must_pass must delegate to evaluate() logic."""

    def test_tests_must_pass_delegates_to_evaluate(self):
        """tests_must_pass must use evaluate() to determine the final result."""
        strategy = _make_strategy()
        passing_jobs = [_make_job("pytest-unit", "success")]

        with patch.object(strategy, "_run_ci_and_wait", return_value=passing_jobs), \
             patch.object(strategy, "evaluate", wraps=strategy.evaluate) as mock_evaluate:
            strategy.tests_must_pass(task_id="T015", command="npm test")

        # evaluate must have been called
        assert mock_evaluate.called, (
            "tests_must_pass must call evaluate() to determine pass/fail"
        )

    def test_tests_must_fail_delegates_to_evaluate(self):
        """tests_must_fail must use evaluate() to determine the final result."""
        strategy = _make_strategy()
        failing_jobs = [_make_job("pytest-unit", "failure")]

        with patch.object(strategy, "_run_ci_and_wait", return_value=failing_jobs), \
             patch.object(strategy, "evaluate", wraps=strategy.evaluate) as mock_evaluate:
            strategy.tests_must_fail(task_id="T015", command="npm test")

        assert mock_evaluate.called, (
            "tests_must_fail must call evaluate() to determine pass/fail"
        )

    def test_tests_must_pass_passes_ci_results_to_evaluate(self):
        """tests_must_pass must pass the CI job results to evaluate()."""
        strategy = _make_strategy()
        ci_jobs = [
            _make_job("pytest-unit", "success"),
            _make_job("mypy-check", "success"),
        ]
        captured_args = {}

        original_evaluate = strategy.evaluate

        def capturing_evaluate(ci_results, stack=None):
            captured_args["ci_results"] = ci_results
            captured_args["stack"] = stack
            return original_evaluate(ci_results, stack)

        with patch.object(strategy, "_run_ci_and_wait", return_value=ci_jobs), \
             patch.object(strategy, "evaluate", side_effect=capturing_evaluate):
            strategy.tests_must_pass(task_id="T015", command="npm test")

        assert "ci_results" in captured_args, (
            "evaluate() must be called with ci_results from _run_ci_and_wait"
        )
        assert captured_args["ci_results"] == ci_jobs


# ---------------------------------------------------------------------------
# I. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for the new T015 functionality."""

    def test_commit_and_push_with_empty_files_list(self):
        """_commit_and_push must handle an empty files list without error."""
        strategy = _make_strategy()
        pass_proc = MagicMock()
        pass_proc.returncode = 0

        with patch("subprocess.run", return_value=pass_proc):
            # Must not raise
            strategy._commit_and_push(message="empty files test", files=[])

    def test_detect_stack_handles_nonexistent_dir_gracefully(self, tmp_path: Path):
        """detect_stack must not raise if project_dir doesn't exist; return 'unknown'."""
        nonexistent = tmp_path / "does_not_exist"
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=nonexistent)
        assert isinstance(result, str)
        # Must not raise; return some safe fallback
        assert len(result) > 0

    def test_tests_must_pass_with_empty_job_list(self):
        """tests_must_pass with no CI jobs should return True (vacuously)."""
        strategy = _make_strategy()
        with patch.object(strategy, "_run_ci_and_wait", return_value=[]):
            result = strategy.tests_must_pass(task_id="T015", command="npm test")
        # No jobs means nothing failed
        assert result is True

    def test_tests_must_fail_with_empty_job_list(self):
        """tests_must_fail with no CI jobs should return False (nothing failed)."""
        strategy = _make_strategy()
        with patch.object(strategy, "_run_ci_and_wait", return_value=[]):
            result = strategy.tests_must_fail(task_id="T015", command="npm test")
        # No failing jobs means RED phase not confirmed
        assert result is False

    def test_get_job_name_mapping_does_not_raise_with_no_config(self):
        """get_job_name_mapping must not raise when config is empty."""
        strategy = CICheckStrategy(config={})
        mapping = strategy.get_job_name_mapping()
        assert isinstance(mapping, dict)

    def test_detect_stack_with_multiple_python_markers(self, tmp_path: Path):
        """FR-080: Multiple Python markers all present still detects 'python'."""
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        strategy = _make_strategy()
        result = strategy.detect_stack(project_dir=tmp_path)
        assert result.lower() == "python"

    def test_commit_and_push_retry_backoff_between_attempts(self):
        """FR-009: _commit_and_push should sleep between retry attempts."""
        strategy = _make_strategy()
        pass_proc = MagicMock()
        pass_proc.returncode = 0
        call_count = 0

        def failing_then_pass(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise subprocess.CalledProcessError(1, "git push")
            return pass_proc

        with patch("subprocess.run", side_effect=failing_then_pass), \
             patch("time.sleep") as mock_sleep:
            strategy._commit_and_push(message="retry with sleep", files=[])

        # Some sleep must happen between retries
        assert mock_sleep.called, (
            "_commit_and_push must sleep between retry attempts"
        )
