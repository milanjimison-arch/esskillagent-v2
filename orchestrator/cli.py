"""CLI entry point for the E+S Orchestrator."""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Return an ArgumentParser with sub-commands registered."""
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="E+S Orchestrator CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.required = True

    # run sub-command
    run_parser = subparsers.add_parser("run", help="Run the pipeline")
    run_parser.add_argument("--config", default=None, help="Path to config file")

    # resume sub-command
    subparsers.add_parser("resume", help="Resume the pipeline")

    # retry sub-command
    retry_parser = subparsers.add_parser("retry", help="Retry the pipeline")
    retry_parser.add_argument("--stage", default=None, help="Stage to retry")

    # status sub-command
    subparsers.add_parser("status", help="Show pipeline status")

    return parser


def check_git_repo(path=None) -> None:
    """Check that path (or cwd) is a git repository.

    Raises SystemExit with non-zero code if the directory is not a git repo.
    """
    check_path = Path(path) if path is not None else Path.cwd()

    # Fast path: check for .git directory or file
    if (check_path / ".git").exists():
        return None

    # Fallback: use git rev-parse to verify
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(check_path),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        sys.exit(
            f"Error: '{check_path}' is not a git repository. "
            "Please run from within a git repository."
        )

    return None


def _build_engine(config=None):
    """Build and return a PipelineEngine instance."""
    from orchestrator.engine import PipelineEngine
    engine_config = config if isinstance(config, dict) else {}
    return PipelineEngine(stages={}, config=engine_config)


async def _dispatch_run(engine, args):
    """Dispatch the 'run' sub-command to engine.run()."""
    return await engine.run()


async def _dispatch_resume(engine, args):
    """Dispatch the 'resume' sub-command to engine.resume()."""
    return await engine.resume()


async def _dispatch_retry(engine, args):
    """Dispatch the 'retry' sub-command to engine.retry()."""
    return await engine.retry()


def _dispatch_status(engine, args):
    """Dispatch the 'status' sub-command to engine.status()."""
    return engine.status()


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    check_git_repo()
    engine = _build_engine(config=getattr(args, "config", None))

    if args.subcommand == "run":
        asyncio.run(_dispatch_run(engine, args))
    elif args.subcommand == "resume":
        asyncio.run(_dispatch_resume(engine, args))
    elif args.subcommand == "retry":
        asyncio.run(_dispatch_retry(engine, args))
    elif args.subcommand == "status":
        _dispatch_status(engine, args)
    else:
        parser.print_help()
        sys.exit(1)
