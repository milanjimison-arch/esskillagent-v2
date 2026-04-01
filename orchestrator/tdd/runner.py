"""TDD task runner — TaskRunner with serial and parallel group execution.

FR-016: Serial and parallel TDD task execution.
FR-017: run_serial executes RED then GREEN sequentially.
FR-018: run_parallel_group Phase A (RED) — concurrent agents + batch commit.
FR-019: asyncio.gather for concurrent execution; sequential store writes after gather.
FR-020: git add scope limited to project source, excluding .workflow/.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import subprocess
from pathlib import Path
from typing import Any

from orchestrator.checks.base import CheckStrategy
from orchestrator.store.models import CheckResult, Task

logger = logging.getLogger(__name__)


class TaskRunner:
    """Runs TDD tasks through RED→GREEN cycles, serially or in parallel groups.

    Dependencies are injected via constructor so that tests can substitute
    mocks without patching module globals (CheckStrategy ABC pattern).
    """

    def __init__(
        self,
        check_strategy: CheckStrategy,
        store: Any,
        agent_adapter: Any,
        store_lock: asyncio.Lock,
        project_dir: str,
        max_green_retries: int = 3,
    ) -> None:
        self._check = check_strategy
        self._store = store
        self._agent = agent_adapter
        self._lock = store_lock
        self.project_dir = project_dir
        self.max_green_retries = max_green_retries

    # ------------------------------------------------------------------
    # FR-017: Serial RED → GREEN
    # ------------------------------------------------------------------

    async def run_serial(self, task: Task) -> None:
        """Execute a single task through RED then GREEN phases sequentially.

        FR-017: RED (test must fail) before GREEN (test must pass).
        FR-020: git add excludes .workflow/.
        """
        # ---- RED phase ----
        await self._agent.invoke("red", task)
        red_result = await self._check.tests_must_fail(
            self.project_dir, task.id, task.file_path
        )
        if not red_result.success:
            logger.warning("RED check failed for %s: %s", task.id, red_result.detail)
            await self._write_task_status(task, "failed")
            return

        await self._write_task_status(task, "red")

        # Commit the test file so CI / local runner sees it
        self._batch_commit([task], phase="red")

        # ---- GREEN phase ----
        await self._agent.invoke("green", task)
        green_result = await self._check.tests_must_pass(
            self.project_dir, task.id, task.file_path
        )
        if not green_result.success:
            logger.warning("GREEN check failed for %s: %s", task.id, green_result.detail)
            await self._write_task_status(task, "failed")
            return

        self._batch_commit([task], phase="green")
        await self._write_task_status(task, "green")

    # ------------------------------------------------------------------
    # FR-018 + FR-019 + FR-020: Parallel group RED + GREEN + retry
    # ------------------------------------------------------------------

    async def run_parallel_group(self, tasks: list[Task]) -> None:
        """Execute a group of tasks in parallel through RED then GREEN phases.

        Phase A (RED):
          - FR-018: invoke agents concurrently via asyncio.gather
          - FR-018: batch commit all results together
          - FR-019: write results to store sequentially after gather

        Phase B (GREEN):
          - FR-019: invoke agents concurrently via asyncio.gather
          - FR-019: batch commit all results together
          - FR-019: write results to store sequentially after gather
          - FR-020: retry loop up to max_green_retries for any failures
        """
        if not tasks:
            return

        # ---- Phase A: RED ----
        red_results = await asyncio.gather(
            *[self._run_red_agent(task) for task in tasks],
            return_exceptions=True,
        )

        # Collect which tasks achieved valid RED state
        red_passed: list[Task] = []
        red_failed: list[Task] = []
        for task, result in zip(tasks, red_results):
            if isinstance(result, Exception):
                logger.error("RED agent raised exception for %s: %s", task.id, result)
                red_failed.append(task)
            elif result.success:  # type: ignore[union-attr]
                red_passed.append(task)
            else:
                logger.warning(
                    "RED check did not achieve failure for %s: %s",
                    task.id,
                    result.detail,  # type: ignore[union-attr]
                )
                red_failed.append(task)

        # Batch commit RED artefacts (tests files) for tasks that passed RED
        if red_passed:
            self._batch_commit(red_passed, phase="red")

        # Sequential store writes after gather (FR-019)
        for task in red_passed:
            await self._write_task_status(task, "red")
        for task in red_failed:
            await self._write_task_status(task, "failed")

        # Do not proceed to GREEN if no tasks passed RED
        if not red_passed:
            return

        # ---- Phase B: GREEN ----
        remaining = list(red_passed)
        attempt = 0
        while remaining and attempt <= self.max_green_retries:
            green_results = await asyncio.gather(
                *[self._run_green_agent(task) for task in remaining],
                return_exceptions=True,
            )

            still_failing: list[Task] = []
            passed_this_round: list[Task] = []
            for task, result in zip(remaining, green_results):
                if isinstance(result, Exception):
                    logger.error(
                        "GREEN agent raised exception for %s: %s", task.id, result
                    )
                    still_failing.append(task)
                elif result.success:  # type: ignore[union-attr]
                    passed_this_round.append(task)
                else:
                    logger.warning(
                        "GREEN check failed for %s (attempt %d): %s",
                        task.id,
                        attempt + 1,
                        result.detail,  # type: ignore[union-attr]
                    )
                    still_failing.append(task)

            # Batch commit passing GREEN artefacts
            if passed_this_round:
                self._batch_commit(passed_this_round, phase="green")

            # Sequential store writes (FR-019)
            for task in passed_this_round:
                await self._write_task_status(task, "green")

            remaining = still_failing
            attempt += 1

        # Tasks still in `remaining` have exhausted retries
        for task in remaining:
            await self._write_task_status(task, "failed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_red_agent(self, task: Task) -> CheckResult:
        """Invoke agent for RED phase and run the check."""
        await self._agent.invoke("red", task)
        return await self._check.tests_must_fail(
            self.project_dir, task.id, task.file_path
        )

    async def _run_green_agent(self, task: Task) -> CheckResult:
        """Invoke agent for GREEN phase and run the check."""
        await self._agent.invoke("green", task)
        return await self._check.tests_must_pass(
            self.project_dir, task.id, task.file_path
        )

    async def _write_task_status(self, task: Task, status: str) -> None:
        """Write a task status update to the store under the lock (FR-019)."""
        updated = dataclasses.replace(task, status=status)
        async with self._lock:
            await self._store.upsert_task(updated)

    def _batch_commit(self, tasks: list[Task], phase: str) -> None:
        """Stage and commit artefacts for the given tasks.

        FR-020: git add is scoped to the project source directory using a
        pathspec that explicitly excludes .workflow/ so that orchestrator-
        internal files are never committed alongside implementation code.

        Uses the pathspec magic-word ':(exclude).workflow' which is
        supported by git >= 2.13 and works on all platforms.
        """
        if not tasks:
            return

        cwd = self.project_dir
        task_ids = ", ".join(t.id for t in tasks)

        # Stage all tracked changes except anything inside .workflow/
        # ':(exclude).workflow' is a git pathspec magic-word that tells git to
        # include everything ('.') while excluding the named path prefix.
        git_add_cmd = [
            "git",
            "add",
            ".",
            ":(exclude).workflow",
            ":(exclude).workflow/**",
        ]
        result = subprocess.run(
            git_add_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "git add failed for %s phase %s: %s",
                task_ids,
                phase,
                result.stderr,
            )

        commit_msg = f"[{phase.upper()}] batch commit: {task_ids}"
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg, "--allow-empty"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if commit_result.returncode != 0:
            logger.warning(
                "git commit failed for %s phase %s: %s",
                task_ids,
                phase,
                commit_result.stderr,
            )
