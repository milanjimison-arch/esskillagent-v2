"""CLI entry point for the E+S Orchestrator — stub only.

This module is a minimal stub that exists solely to allow test imports to
succeed (ImportError-free RED state).  Every function raises NotImplementedError
so that tests fail on behaviour assertions, not on import errors.

Do NOT implement any logic here until the RED gate is confirmed.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Return an ArgumentParser with sub-commands registered. (stub)"""
    raise NotImplementedError("build_parser not implemented")


def check_git_repo(path=None) -> None:
    """Check that *path* (or cwd) is a git repository. (stub)"""
    raise NotImplementedError("check_git_repo not implemented")


def _build_engine(config=None):
    """Build and return a PipelineEngine instance. (stub)"""
    raise NotImplementedError("_build_engine not implemented")


async def _dispatch_run(engine, args):
    """Dispatch the 'run' sub-command to engine.run(). (stub)"""
    raise NotImplementedError("_dispatch_run not implemented")


async def _dispatch_resume(engine, args):
    """Dispatch the 'resume' sub-command to engine.resume(). (stub)"""
    raise NotImplementedError("_dispatch_resume not implemented")


async def _dispatch_retry(engine, args):
    """Dispatch the 'retry' sub-command to engine.retry(). (stub)"""
    raise NotImplementedError("_dispatch_retry not implemented")


def _dispatch_status(engine, args):
    """Dispatch the 'status' sub-command to engine.status(). (stub)"""
    raise NotImplementedError("_dispatch_status not implemented")


def main() -> None:
    """CLI entry point. (stub)"""
    raise NotImplementedError("main not implemented")
