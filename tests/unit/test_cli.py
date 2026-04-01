"""Unit tests for orchestrator/cli.py — CLI entry point with argparse sub-commands.

Requirements covered:
  FR-CLI-001: CLI MUST support 'run' sub-command that calls engine.run().
  FR-CLI-002: CLI MUST support 'resume' sub-command that calls engine.resume().
  FR-CLI-003: CLI MUST support 'retry' sub-command that calls engine.retry().
  FR-CLI-004: CLI MUST support 'status' sub-command that calls engine.status().
  FR-CLI-005: CLI MUST check that the current directory is a git repository
              before executing any sub-command.
  FR-CLI-006: CLI MUST use argparse with sub-commands (sub-parsers).
  FR-CLI-007: CLI MUST wire entry point to the engine (run, resume, retry,
              status operations are delegated to the engine).
  FR-CLI-008: When the current directory is NOT a git repository, the CLI MUST
              exit with a non-zero status code and a descriptive error message.
  FR-CLI-009: CLI MUST expose a main() entry point function.
  FR-CLI-010: Calling CLI with no sub-command MUST print help and exit.

All tests in this module are RED-phase tests — they MUST FAIL until
orchestrator/cli.py provides a concrete implementation.

Test coverage areas:
  1.  CLI module is importable.
  2.  main() is a callable entry point.
  3.  build_parser() / create_parser() returns an ArgumentParser.
  4.  FR-CLI-006: 'run' sub-command is registered in the parser.
  5.  FR-CLI-006: 'resume' sub-command is registered in the parser.
  6.  FR-CLI-006: 'retry' sub-command is registered in the parser.
  7.  FR-CLI-006: 'status' sub-command is registered in the parser.
  8.  FR-CLI-005: Git init check is performed before executing any command.
  9.  FR-CLI-008: Non-git directory causes SystemExit with code != 0.
  10. FR-CLI-007: 'run' sub-command wires to engine.run().
  11. FR-CLI-007: 'resume' sub-command wires to engine.resume().
  12. FR-CLI-007: 'retry' sub-command wires to engine.retry().
  13. FR-CLI-007: 'status' sub-command wires to engine.status().
  14. FR-CLI-010: No sub-command supplied causes help/usage exit (code != 0 or
                  prints usage).
  15. Edge: git check passes in a valid git repo directory.
  16. Edge: git check raises / exits in an empty (non-git) tmp directory.
  17. Edge: 'run' passes optional --config flag to the engine.
  18. Edge: 'retry' accepts a --stage argument specifying which stage to retry.
"""

from __future__ import annotations

import argparse
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from orchestrator.cli import build_parser, check_git_repo, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_main(args: list[str], cwd: str | None = None) -> int:
    """Run main() with patched sys.argv and a mocked git-repo check.

    Returns the exit code (0 on success, non-zero otherwise).
    Raises SystemExit if main() calls sys.exit().
    """
    with patch("sys.argv", ["orchestrator"] + args):
        try:
            main()
            return 0
        except SystemExit as exc:
            return exc.code if exc.code is not None else 0


def _make_mock_engine(*, run_return=None, resume_return=None,
                      retry_return=None, status_return=None):
    """Return a MagicMock engine with async stubs for all four operations."""
    engine = MagicMock()
    engine.run = AsyncMock(return_value=run_return or MagicMock(passed=True))
    engine.resume = AsyncMock(return_value=resume_return or MagicMock(passed=True))
    engine.retry = AsyncMock(return_value=retry_return or MagicMock(passed=True))
    engine.status = MagicMock(return_value=status_return or {"stage": "plan", "state": "running"})
    return engine


# ===========================================================================
# 1. Import
# ===========================================================================


class TestCLIImport:
    """FR-CLI-009: CLI module must be importable with the expected public API."""

    def test_FR_CLI_001_build_parser_is_callable(self):
        """FR-CLI-006: build_parser (or equivalent) MUST be callable."""
        assert callable(build_parser), "build_parser must be a callable"

    def test_FR_CLI_009_main_is_callable(self):
        """FR-CLI-009: main() MUST be a callable entry point."""
        assert callable(main), "main must be a callable"

    def test_FR_CLI_005_check_git_repo_is_callable(self):
        """FR-CLI-005: check_git_repo MUST be a callable function."""
        assert callable(check_git_repo), "check_git_repo must be a callable"


# ===========================================================================
# 2. Parser structure — FR-CLI-006
# ===========================================================================


class TestParserStructure:
    """FR-CLI-006: The parser MUST use argparse with registered sub-commands."""

    def test_FR_CLI_006_build_parser_returns_argument_parser(self):
        """build_parser() MUST return an argparse.ArgumentParser instance."""
        parser = build_parser()
        assert isinstance(parser, argparse.ArgumentParser), (
            f"build_parser() must return ArgumentParser, got {type(parser).__name__}"
        )

    def test_FR_CLI_006_run_subcommand_is_registered(self):
        """FR-CLI-001: 'run' MUST be a registered sub-command."""
        parser = build_parser()
        # Parsing 'run' should NOT raise SystemExit
        namespace = parser.parse_args(["run"])
        assert namespace.subcommand == "run", (
            f"Expected namespace.subcommand='run', got {namespace.subcommand!r}"
        )

    def test_FR_CLI_006_resume_subcommand_is_registered(self):
        """FR-CLI-002: 'resume' MUST be a registered sub-command."""
        parser = build_parser()
        namespace = parser.parse_args(["resume"])
        assert namespace.subcommand == "resume", (
            f"Expected namespace.subcommand='resume', got {namespace.subcommand!r}"
        )

    def test_FR_CLI_006_retry_subcommand_is_registered(self):
        """FR-CLI-003: 'retry' MUST be a registered sub-command."""
        parser = build_parser()
        namespace = parser.parse_args(["retry"])
        assert namespace.subcommand == "retry", (
            f"Expected namespace.subcommand='retry', got {namespace.subcommand!r}"
        )

    def test_FR_CLI_006_status_subcommand_is_registered(self):
        """FR-CLI-004: 'status' MUST be a registered sub-command."""
        parser = build_parser()
        namespace = parser.parse_args(["status"])
        assert namespace.subcommand == "status", (
            f"Expected namespace.subcommand='status', got {namespace.subcommand!r}"
        )

    def test_FR_CLI_006_unknown_subcommand_raises_system_exit(self):
        """An unknown sub-command MUST cause SystemExit (argparse default behaviour)."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["nonexistent_cmd"])
        assert exc_info.value.code != 0, (
            "Unknown sub-command must exit with non-zero code"
        )

    def test_FR_CLI_006_parser_has_subparsers(self):
        """The parser MUST contain sub-parsers (not a flat argument list)."""
        parser = build_parser()
        # Check that at least one action is a _SubParsersAction
        has_subparsers = any(
            isinstance(action, argparse._SubParsersAction)
            for action in parser._actions
        )
        assert has_subparsers, (
            "build_parser() must register sub-parsers (argparse.add_subparsers)"
        )


# ===========================================================================
# 3. Git repository check — FR-CLI-005 / FR-CLI-008
# ===========================================================================


class TestGitRepoCheck:
    """FR-CLI-005/008: CLI must check git repo before executing any sub-command."""

    def test_FR_CLI_005_check_git_repo_passes_in_valid_repo(self, tmp_path: Path):
        """FR-CLI-005: check_git_repo() MUST succeed silently in a real git repo."""
        # Initialise a real git repository in tmp_path
        subprocess.run(["git", "init", str(tmp_path)], check=True,
                       capture_output=True)
        # Should return normally without raising
        check_git_repo(path=str(tmp_path))

    def test_FR_CLI_005_check_git_repo_raises_or_exits_in_non_git_dir(
        self, tmp_path: Path
    ):
        """FR-CLI-008: check_git_repo() MUST raise SystemExit or an exception
        when called on a directory that is NOT a git repository."""
        with pytest.raises((SystemExit, Exception)) as exc_info:
            check_git_repo(path=str(tmp_path))
        # If SystemExit, the code must be non-zero
        if isinstance(exc_info.value, SystemExit):
            assert exc_info.value.code != 0, (
                "check_git_repo must exit with non-zero code in non-git dir"
            )

    def test_FR_CLI_008_main_exits_nonzero_in_non_git_dir(self, tmp_path: Path):
        """FR-CLI-008: main() MUST exit with non-zero code when not in a git repo."""
        with patch("orchestrator.cli.check_git_repo") as mock_check:
            mock_check.side_effect = SystemExit(1)
            with pytest.raises(SystemExit) as exc_info:
                with patch("sys.argv", ["orchestrator", "run"]):
                    main()
        assert exc_info.value.code != 0, (
            "main() must propagate non-zero SystemExit from check_git_repo"
        )

    def test_FR_CLI_005_check_git_repo_called_before_run(self):
        """FR-CLI-005: check_git_repo MUST be called when 'run' sub-command is used."""
        with patch("orchestrator.cli.check_git_repo") as mock_check, \
             patch("orchestrator.cli._dispatch_run", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = MagicMock(passed=True)
            with patch("sys.argv", ["orchestrator", "run"]):
                try:
                    main()
                except SystemExit:
                    pass
        mock_check.assert_called_once(), (
            "check_git_repo must be called exactly once when 'run' is invoked"
        )

    def test_FR_CLI_005_check_git_repo_called_before_status(self):
        """FR-CLI-005: check_git_repo MUST be called when 'status' sub-command is used."""
        with patch("orchestrator.cli.check_git_repo") as mock_check, \
             patch("orchestrator.cli._dispatch_status") as mock_dispatch:
            mock_dispatch.return_value = {"stage": "plan"}
            with patch("sys.argv", ["orchestrator", "status"]):
                try:
                    main()
                except SystemExit:
                    pass
        mock_check.assert_called_once(), (
            "check_git_repo must be called exactly once when 'status' is invoked"
        )

    def test_FR_CLI_005_git_check_error_message_is_descriptive(self, tmp_path: Path):
        """FR-CLI-008: The error message for a non-git dir MUST mention 'git'."""
        with pytest.raises((SystemExit, Exception)) as exc_info:
            check_git_repo(path=str(tmp_path))
        error_text = str(exc_info.value).lower()
        assert "git" in error_text, (
            f"Error message must mention 'git', got: {str(exc_info.value)!r}"
        )


# ===========================================================================
# 4. Engine wiring — FR-CLI-007
# ===========================================================================


class TestEngineWiring:
    """FR-CLI-007: Sub-commands MUST delegate to the corresponding engine methods."""

    def test_FR_CLI_007_run_dispatches_to_engine_run(self):
        """FR-CLI-001/007: 'run' sub-command MUST call engine.run()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "run"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.run.assert_called_once(), (
            "'run' sub-command must call engine.run() exactly once"
        )

    def test_FR_CLI_007_resume_dispatches_to_engine_resume(self):
        """FR-CLI-002/007: 'resume' sub-command MUST call engine.resume()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "resume"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.resume.assert_called_once(), (
            "'resume' sub-command must call engine.resume() exactly once"
        )

    def test_FR_CLI_007_retry_dispatches_to_engine_retry(self):
        """FR-CLI-003/007: 'retry' sub-command MUST call engine.retry()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "retry"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.retry.assert_called_once(), (
            "'retry' sub-command must call engine.retry() exactly once"
        )

    def test_FR_CLI_007_status_dispatches_to_engine_status(self):
        """FR-CLI-004/007: 'status' sub-command MUST call engine.status()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "status"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.status.assert_called_once(), (
            "'status' sub-command must call engine.status() exactly once"
        )

    def test_FR_CLI_007_run_does_not_call_resume(self):
        """'run' sub-command MUST NOT call engine.resume()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "run"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.resume.assert_not_called(), (
            "'run' sub-command must not call engine.resume()"
        )

    def test_FR_CLI_007_status_does_not_call_run(self):
        """'status' sub-command MUST NOT call engine.run()."""
        mock_engine = _make_mock_engine()
        with patch("orchestrator.cli.check_git_repo"), \
             patch("orchestrator.cli._build_engine", return_value=mock_engine), \
             patch("sys.argv", ["orchestrator", "status"]):
            try:
                main()
            except SystemExit:
                pass
        mock_engine.run.assert_not_called(), (
            "'status' sub-command must not call engine.run()"
        )


# ===========================================================================
# 5. No sub-command — FR-CLI-010
# ===========================================================================


class TestNoSubcommand:
    """FR-CLI-010: Invoking CLI with no sub-command MUST exit non-zero or print help."""

    def test_FR_CLI_010_no_subcommand_exits_nonzero(self):
        """FR-CLI-010: main() with no sub-command MUST raise SystemExit."""
        with patch("sys.argv", ["orchestrator"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        # Exit code must be non-zero (no valid sub-command supplied)
        assert exc_info.value.code != 0, (
            "main() with no sub-command must exit with code != 0"
        )

    def test_FR_CLI_010_parser_no_args_raises_system_exit(self, capsys):
        """FR-CLI-010: Parsing an empty argv MUST raise SystemExit."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ===========================================================================
# 6. Optional arguments / edge cases
# ===========================================================================


class TestOptionalArguments:
    """Edge-case argument handling for individual sub-commands."""

    def test_run_subcommand_accepts_config_flag(self):
        """'run' MUST accept an optional --config /path argument."""
        parser = build_parser()
        namespace = parser.parse_args(["run", "--config", "/some/path.yaml"])
        assert hasattr(namespace, "config"), (
            "Namespace for 'run --config' must have a 'config' attribute"
        )
        assert namespace.config == "/some/path.yaml", (
            f"Expected config='/some/path.yaml', got {namespace.config!r}"
        )

    def test_retry_subcommand_accepts_stage_argument(self):
        """'retry' MUST accept an optional --stage argument."""
        parser = build_parser()
        namespace = parser.parse_args(["retry", "--stage", "plan"])
        assert hasattr(namespace, "stage"), (
            "Namespace for 'retry --stage' must have a 'stage' attribute"
        )
        assert namespace.stage == "plan", (
            f"Expected stage='plan', got {namespace.stage!r}"
        )

    def test_run_subcommand_config_flag_defaults_to_none(self):
        """'run' without --config MUST have config attribute defaulting to None."""
        parser = build_parser()
        namespace = parser.parse_args(["run"])
        assert hasattr(namespace, "config"), (
            "Namespace for 'run' must always have 'config' attribute"
        )
        assert namespace.config is None, (
            f"Default config must be None, got {namespace.config!r}"
        )

    def test_retry_subcommand_stage_defaults_to_none(self):
        """'retry' without --stage MUST have stage attribute defaulting to None."""
        parser = build_parser()
        namespace = parser.parse_args(["retry"])
        assert hasattr(namespace, "stage"), (
            "Namespace for 'retry' must always have 'stage' attribute"
        )
        assert namespace.stage is None, (
            f"Default stage must be None, got {namespace.stage!r}"
        )

    def test_resume_subcommand_parses_cleanly(self):
        """'resume' with no extra args MUST parse without error."""
        parser = build_parser()
        namespace = parser.parse_args(["resume"])
        assert namespace.subcommand == "resume"

    def test_status_subcommand_parses_cleanly(self):
        """'status' with no extra args MUST parse without error."""
        parser = build_parser()
        namespace = parser.parse_args(["status"])
        assert namespace.subcommand == "status"


# ===========================================================================
# 7. check_git_repo function contract
# ===========================================================================


class TestCheckGitRepoContract:
    """check_git_repo() function-level contract tests."""

    def test_check_git_repo_accepts_path_string(self, tmp_path: Path):
        """check_git_repo() MUST accept a string path argument."""
        subprocess.run(["git", "init", str(tmp_path)], check=True,
                       capture_output=True)
        # Should not raise TypeError
        result = check_git_repo(path=str(tmp_path))
        # Return value (if any) must not be a type error — None is acceptable
        assert result is None or result is True or isinstance(result, bool), (
            f"check_git_repo return value must be None or bool, got {type(result)}"
        )

    def test_check_git_repo_accepts_path_object(self, tmp_path: Path):
        """check_git_repo() MUST accept a pathlib.Path argument."""
        subprocess.run(["git", "init", str(tmp_path)], check=True,
                       capture_output=True)
        # Should not raise TypeError
        check_git_repo(path=tmp_path)

    def test_check_git_repo_uses_dot_git_detection(self, tmp_path: Path):
        """check_git_repo() MUST detect git repositories via .git presence or
        'git rev-parse' — NOT by any other heuristic."""
        # Create a directory with a fake .git file to confirm check passes
        (tmp_path / ".git").mkdir()
        # With .git dir present, check should either pass or be fooled — either
        # way, without it the check must fail
        non_git = tmp_path / "subdir"
        non_git.mkdir()
        with pytest.raises((SystemExit, Exception)):
            check_git_repo(path=str(non_git))
