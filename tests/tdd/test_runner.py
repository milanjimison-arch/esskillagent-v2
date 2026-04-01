"""Tests for TaskRunner — TDD runner covering FR-016 through FR-020.

FR-016: Serial and parallel TDD task execution.
FR-017: Serial RED then GREEN sequentially.
FR-018: Parallel Phase A (RED) concurrent + batch commit.
FR-019: asyncio.gather with sequential store writes.
FR-020: git add scope limited to project source, excluding .workflow/.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.store.models import CheckResult, Task
from orchestrator.tdd.runner import TaskRunner


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def make_task(
    task_id: str = "T001",
    status: str = "pending",
    parallel: bool = False,
    file_path: str | None = "src/foo.py",
) -> Task:
    """Factory for Task frozen dataclasses."""
    return Task(
        id=task_id,
        phase_num=1,
        description=f"Implement {task_id}",
        file_path=file_path,
        story_ref="US1",
        parallel=parallel,
        depends_on=[],
        status=status,
        started_at=None,
        completed_at=None,
        tdd_phase=None,
        review_notes=None,
    )


def passing_check() -> CheckResult:
    return CheckResult(success=True, detail="ok")


def failing_check() -> CheckResult:
    return CheckResult(success=False, detail="tests still pass — RED not achieved")


def _noop_subprocess(cmd: list[str], **kwargs: Any) -> MagicMock:
    """Default subprocess mock: returns success with a dummy SHA."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = "abc123\n"
    result.stderr = ""
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_check_strategy():
    """Mock CheckStrategy that succeeds for both RED and GREEN phases."""
    strategy = MagicMock()
    strategy.tests_must_fail = AsyncMock(return_value=passing_check())
    strategy.tests_must_pass = AsyncMock(return_value=passing_check())
    return strategy


@pytest.fixture
def mock_store():
    """Mock store with async upsert_task."""
    store = MagicMock()
    store.upsert_task = AsyncMock()
    return store


@pytest.fixture
def mock_agent_adapter():
    """Mock agent adapter that simulates agent invocations."""
    adapter = MagicMock()
    adapter.invoke = AsyncMock(return_value="agent output")
    return adapter


@pytest.fixture
def store_lock():
    """asyncio.Lock for sequential store writes."""
    return asyncio.Lock()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal project directory with src/ and .workflow/."""
    (tmp_path / "src").mkdir()
    (tmp_path / ".workflow").mkdir()
    (tmp_path / "src" / "foo.py").write_text("# src file")
    (tmp_path / ".workflow" / "workflow.db").write_text("db content")
    return tmp_path


@pytest.fixture(autouse=True)
def mock_subprocess():
    """Auto-use fixture: prevent all tests from calling real git subprocess."""
    with patch(
        "orchestrator.tdd.runner.subprocess.run",
        side_effect=_noop_subprocess,
    ) as mock:
        yield mock


def make_runner(
    check_strategy=None,
    store=None,
    agent_adapter=None,
    store_lock=None,
    project_dir: str = "/tmp/proj",
    max_green_retries: int = 3,
) -> TaskRunner:
    """Construct a TaskRunner with all dependencies injected."""
    return TaskRunner(
        check_strategy=check_strategy or MagicMock(),
        store=store or MagicMock(),
        agent_adapter=agent_adapter or MagicMock(),
        store_lock=store_lock or asyncio.Lock(),
        project_dir=project_dir,
        max_green_retries=max_green_retries,
    )


# ===========================================================================
# FR-016: TaskRunner can be instantiated with injected dependencies
# ===========================================================================


class TestTaskRunnerConstruction:
    """FR-016: TaskRunner construction and dependency injection."""

    def test_fr016_runner_accepts_check_strategy_injection(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-016: TaskRunner must accept a CheckStrategy via constructor injection."""
        runner = TaskRunner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            project_dir="/tmp/proj",
            max_green_retries=3,
        )
        assert runner is not None

    def test_fr016_runner_stores_max_green_retries(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-016: TaskRunner must persist the max_green_retries configuration."""
        runner = TaskRunner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            project_dir="/tmp/proj",
            max_green_retries=5,
        )
        assert runner.max_green_retries == 5

    def test_fr016_runner_stores_project_dir(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-016: TaskRunner must store the project directory."""
        runner = TaskRunner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            project_dir="/my/project",
            max_green_retries=3,
        )
        assert runner.project_dir == "/my/project"


# ===========================================================================
# FR-017: run_serial — RED then GREEN sequentially
# ===========================================================================


class TestRunSerial:
    """FR-017: Serial RED→GREEN execution."""

    async def test_fr017_serial_calls_red_phase_first(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must invoke tests_must_fail (RED) before tests_must_pass."""
        call_order: list[str] = []

        async def record_red(*args: Any, **kwargs: Any) -> CheckResult:
            call_order.append("RED")
            return passing_check()

        async def record_green(*args: Any, **kwargs: Any) -> CheckResult:
            call_order.append("GREEN")
            return passing_check()

        mock_check_strategy.tests_must_fail = record_red
        mock_check_strategy.tests_must_pass = record_green

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        assert call_order.index("RED") < call_order.index("GREEN"), (
            "RED must be called before GREEN in serial execution"
        )

    async def test_fr017_serial_updates_task_status_to_red_then_green(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must update task status: pending→red→green."""
        status_updates: list[str] = []

        async def capture_upsert(task: Task) -> None:
            status_updates.append(task.status)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        assert "red" in status_updates, "Task must be marked 'red' during RED phase"
        assert "green" in status_updates, "Task must be marked 'green' after GREEN phase"
        red_idx = status_updates.index("red")
        green_idx = status_updates.index("green")
        assert red_idx < green_idx, "Status 'red' must appear before 'green'"

    async def test_fr017_serial_invokes_agent_for_red_phase(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must invoke the agent adapter during RED phase."""
        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        assert mock_agent_adapter.invoke.called, (
            "Agent adapter must be called to generate RED phase test"
        )

    async def test_fr017_serial_marks_task_failed_when_red_check_fails(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must mark task as 'failed' when RED check cannot be achieved."""
        mock_check_strategy.tests_must_fail = AsyncMock(return_value=failing_check())

        status_updates: list[str] = []

        async def capture_upsert(task: Task) -> None:
            status_updates.append(task.status)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        assert "failed" in status_updates, (
            "Task must be marked 'failed' when RED check cannot achieve failure"
        )

    async def test_fr017_serial_marks_task_failed_when_green_check_fails(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must mark task as 'failed' when GREEN check fails."""
        mock_check_strategy.tests_must_fail = AsyncMock(return_value=passing_check())
        mock_check_strategy.tests_must_pass = AsyncMock(return_value=failing_check())

        status_updates: list[str] = []

        async def capture_upsert(task: Task) -> None:
            status_updates.append(task.status)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        assert "failed" in status_updates, (
            "Task must be marked 'failed' when GREEN check fails"
        )

    async def test_fr017_serial_does_not_proceed_to_green_when_red_fails(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-017: run_serial must not enter GREEN phase if RED phase fails."""
        mock_check_strategy.tests_must_fail = AsyncMock(return_value=failing_check())
        mock_check_strategy.tests_must_pass = AsyncMock(return_value=passing_check())

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        task = make_task("T001")
        await runner.run_serial(task)

        mock_check_strategy.tests_must_pass.assert_not_called()


# ===========================================================================
# FR-018: run_parallel_group Phase A (RED) — concurrent + batch commit
# ===========================================================================


class TestRunParallelGroupPhaseA:
    """FR-018: Parallel Phase A (RED) concurrent execution + batch commit."""

    async def test_fr018_phase_a_runs_all_red_agents_concurrently(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-018: Phase A must invoke agents for all tasks, not just the first."""
        invoke_calls: list[str] = []

        async def capture_invoke(phase: str, task: Task, **kwargs: Any) -> str:
            invoke_calls.append(f"{phase}:{task.id}")
            return "output"

        mock_agent_adapter.invoke = capture_invoke

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
            make_task("T003", parallel=True, file_path="src/c.py"),
        ]
        await runner.run_parallel_group(tasks)

        red_calls = [c for c in invoke_calls if c.startswith("red:")]
        invoked_ids = {c.split(":")[1] for c in red_calls}
        assert invoked_ids == {"T001", "T002", "T003"}, (
            "All tasks must have their RED agent invoked in Phase A"
        )

    async def test_fr018_phase_a_batch_commits_after_all_red_agents(
        self,
        mock_check_strategy,
        mock_store,
        mock_agent_adapter,
        store_lock,
        mock_subprocess,
    ) -> None:
        """FR-018: Phase A must perform a single batch commit after all RED agents finish."""
        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        assert mock_subprocess.called, "batch commit must invoke subprocess for git operations"

    async def test_fr018_phase_a_all_tasks_transition_to_red_status(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-018: After Phase A succeeds, all tasks must have 'red' status written to store."""
        stored_statuses: dict[str, list[str]] = {}

        async def capture_upsert(task: Task) -> None:
            stored_statuses.setdefault(task.id, []).append(task.status)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        for task_id in ("T001", "T002"):
            statuses = stored_statuses.get(task_id, [])
            assert "red" in statuses, (
                f"Task {task_id} must have 'red' status written to store during Phase A"
            )

    async def test_fr018_phase_a_marks_failed_tasks_when_red_check_fails(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-018: Phase A must mark individual tasks as 'failed' when RED check fails."""
        call_count = 0

        async def alternating_red(*args: Any, **kwargs: Any) -> CheckResult:
            nonlocal call_count
            call_count += 1
            # First task RED check fails, second passes
            if call_count == 1:
                return failing_check()
            return passing_check()

        mock_check_strategy.tests_must_fail = alternating_red

        failed_ids: list[str] = []

        async def capture_upsert(task: Task) -> None:
            if task.status == "failed":
                failed_ids.append(task.id)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        assert len(failed_ids) >= 1, (
            "At least one task must be marked 'failed' when its RED check does not fail"
        )


# ===========================================================================
# FR-019: asyncio.gather with sequential store writes
# ===========================================================================


class TestSequentialStoreWrites:
    """FR-019: After asyncio.gather, store writes must execute sequentially."""

    async def test_fr019_store_writes_are_sequential_not_concurrent(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-019: Store writes must not happen concurrently — sequential for loop after gather."""
        write_times: list[tuple[str, float]] = []
        is_writing = False
        concurrent_writes_detected = False

        async def recording_upsert(task: Task) -> None:
            nonlocal is_writing, concurrent_writes_detected
            if is_writing:
                concurrent_writes_detected = True
            is_writing = True
            await asyncio.sleep(0.01)  # simulate async store write
            write_times.append((task.id, asyncio.get_event_loop().time()))
            is_writing = False

        mock_store.upsert_task = recording_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
            make_task("T003", parallel=True, file_path="src/c.py"),
        ]
        await runner.run_parallel_group(tasks)

        assert not concurrent_writes_detected, (
            "Store writes must be sequential (no concurrent writes detected)"
        )
        # Each task gets at minimum one write (red or failed)
        assert len(write_times) >= 3, "All 3 tasks must have their store writes executed"

    async def test_fr019_lock_is_acquired_during_store_writes(
        self, mock_check_strategy, mock_store, mock_agent_adapter
    ) -> None:
        """FR-019: store_lock must be acquired for each store write to prevent races."""
        lock = asyncio.Lock()
        lock_acquired_count = 0
        original_acquire = lock.acquire

        async def counting_acquire() -> bool:
            nonlocal lock_acquired_count
            result = await original_acquire()
            lock_acquired_count += 1
            return result

        lock.acquire = counting_acquire  # type: ignore[method-assign]

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        assert lock_acquired_count >= 2, (
            "store_lock must be acquired at least once per task store write"
        )


# ===========================================================================
# FR-020: git add scope excluding .workflow/
# ===========================================================================


class TestGitAddScope:
    """FR-020: git add must be scoped to project source, excluding .workflow/."""

    async def test_fr020_git_add_excludes_workflow_directory(
        self,
        mock_check_strategy,
        mock_store,
        mock_agent_adapter,
        store_lock,
        project_dir: Path,
    ) -> None:
        """FR-020: git add commands must never include .workflow/ in their scope."""
        git_add_args: list[list[str]] = []

        def capture_subprocess(cmd: list[str], **kwargs: Any) -> MagicMock:
            if "git" in cmd and "add" in cmd:
                git_add_args.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc123\n"
            result.stderr = ""
            return result

        with patch("orchestrator.tdd.runner.subprocess.run", side_effect=capture_subprocess):
            runner = make_runner(
                check_strategy=mock_check_strategy,
                store=mock_store,
                agent_adapter=mock_agent_adapter,
                store_lock=store_lock,
                project_dir=str(project_dir),
            )
            tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
            await runner.run_parallel_group(tasks)

        assert len(git_add_args) >= 1, "At least one git add must be executed"
        for add_cmd in git_add_args:
            # Verify the actual git add argument list doesn't contain ".workflow" as a
            # positively-added path. It may appear only in an exclusion argument.
            positive_args = [
                arg for arg in add_cmd
                if not arg.startswith(":(exclude)") and not arg.startswith(":!")
            ]
            positively_added = " ".join(positive_args)
            assert ".workflow" not in positively_added or any(
                ":!.workflow" in arg or ":(exclude).workflow" in arg
                for arg in add_cmd
            ), (
                f"git add must not positively include .workflow/: {add_cmd}"
            )

    async def test_fr020_git_add_excludes_workflow_in_serial_run(
        self,
        mock_check_strategy,
        mock_store,
        mock_agent_adapter,
        store_lock,
        project_dir: Path,
    ) -> None:
        """FR-020: git add in serial run must also exclude .workflow/."""
        git_add_args: list[list[str]] = []

        def capture_subprocess(cmd: list[str], **kwargs: Any) -> MagicMock:
            if "git" in cmd and "add" in cmd:
                git_add_args.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "abc123\n"
            result.stderr = ""
            return result

        with patch("orchestrator.tdd.runner.subprocess.run", side_effect=capture_subprocess):
            runner = make_runner(
                check_strategy=mock_check_strategy,
                store=mock_store,
                agent_adapter=mock_agent_adapter,
                store_lock=store_lock,
                project_dir=str(project_dir),
            )
            task = make_task("T001", file_path="src/a.py")
            await runner.run_serial(task)

        for add_cmd in git_add_args:
            positive_args = [
                arg for arg in add_cmd
                if not arg.startswith(":(exclude)") and not arg.startswith(":!")
            ]
            positively_added = " ".join(positive_args)
            assert ".workflow" not in positively_added or any(
                ":!.workflow" in arg or ":(exclude).workflow" in arg
                for arg in add_cmd
            ), (
                f"git add in serial run must not include .workflow/: {add_cmd}"
            )

    async def test_fr020_git_add_uses_explicit_path_exclusion(
        self,
        mock_check_strategy,
        mock_store,
        mock_agent_adapter,
        store_lock,
        project_dir: Path,
    ) -> None:
        """FR-020: git add must use explicit exclusion pattern for .workflow/."""
        git_add_args: list[list[str]] = []

        def capture_subprocess(cmd: list[str], **kwargs: Any) -> MagicMock:
            if "git" in cmd and "add" in cmd:
                git_add_args.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "def456\n"
            result.stderr = ""
            return result

        with patch("orchestrator.tdd.runner.subprocess.run", side_effect=capture_subprocess):
            runner = make_runner(
                check_strategy=mock_check_strategy,
                store=mock_store,
                agent_adapter=mock_agent_adapter,
                store_lock=store_lock,
                project_dir=str(project_dir),
            )
            tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
            await runner.run_parallel_group(tasks)

        assert len(git_add_args) >= 1
        for add_cmd in git_add_args:
            # Must NOT be a bare "git add ." without any exclusion
            bare_add_dot = (
                len(add_cmd) == 3
                and add_cmd[0] == "git"
                and add_cmd[1] == "add"
                and add_cmd[2] == "."
            )
            has_exclusion = any(
                ":!.workflow" in arg
                or ":(exclude).workflow" in arg
                or "exclude" in arg.lower()
                for arg in add_cmd
            )
            is_targeted = any(
                arg not in ("git", "add", ".", "-A", "--all")
                and not arg.startswith("-")
                for arg in add_cmd[2:]
            )
            assert not bare_add_dot or has_exclusion or is_targeted, (
                f"git add must not be a bare 'git add .' without .workflow/ exclusion: {add_cmd}"
            )


# ===========================================================================
# FR-019 + FR-020: Phase B (GREEN) concurrent + batch commit + retry loop
# ===========================================================================


class TestRunParallelGroupPhaseB:
    """FR-019 + FR-020: Phase B concurrent GREEN + batch commit + retry loop."""

    async def test_fr019_phase_b_runs_all_green_agents(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-019: Phase B must invoke agents for all tasks in the group."""
        invoke_calls: list[str] = []

        async def capture_invoke(phase: str, task: Task, **kwargs: Any) -> str:
            invoke_calls.append(f"{phase}:{task.id}")
            return "output"

        mock_agent_adapter.invoke = capture_invoke

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        green_calls = [c for c in invoke_calls if c.startswith("green:")]
        invoked_ids = {c.split(":")[1] for c in green_calls}
        assert invoked_ids == {"T001", "T002"}, (
            "Both tasks must have their GREEN agent invoked in Phase B"
        )

    async def test_fr020_phase_b_retries_failed_tasks_up_to_max(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-020: Phase B must retry failed GREEN tasks up to max_green_retries."""
        green_check_call_count = 0
        MAX_RETRIES = 2

        async def flaky_green(*args: Any, **kwargs: Any) -> CheckResult:
            nonlocal green_check_call_count
            green_check_call_count += 1
            return failing_check()

        mock_check_strategy.tests_must_pass = flaky_green

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            max_green_retries=MAX_RETRIES,
        )
        tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
        await runner.run_parallel_group(tasks)

        # Initial attempt + up to MAX_RETRIES retries = at least MAX_RETRIES calls
        assert green_check_call_count >= MAX_RETRIES, (
            f"GREEN check must be called at least {MAX_RETRIES} times "
            f"(initial + retries), got {green_check_call_count}"
        )

    async def test_fr020_phase_b_stops_retrying_after_success(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-020: Phase B retry loop must stop once all tasks succeed."""
        green_check_call_count = 0

        async def succeed_on_second(*args: Any, **kwargs: Any) -> CheckResult:
            nonlocal green_check_call_count
            green_check_call_count += 1
            if green_check_call_count <= 1:
                return failing_check()
            return passing_check()

        mock_check_strategy.tests_must_pass = succeed_on_second

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            max_green_retries=5,
        )
        tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
        await runner.run_parallel_group(tasks)

        # Should stop after success, not continue to max_green_retries
        assert green_check_call_count <= 3, (
            "Phase B retry loop must stop once GREEN succeeds, "
            f"but called green check {green_check_call_count} times"
        )

    async def test_fr020_phase_b_marks_exhausted_tasks_as_failed(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-020: Phase B must mark tasks as 'failed' when retries are exhausted."""
        mock_check_strategy.tests_must_pass = AsyncMock(return_value=failing_check())

        failed_ids: list[str] = []

        async def capture_upsert(task: Task) -> None:
            if task.status == "failed":
                failed_ids.append(task.id)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
            max_green_retries=1,
        )
        tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
        await runner.run_parallel_group(tasks)

        assert "T001" in failed_ids, (
            "Task must be marked 'failed' when GREEN retries are exhausted"
        )

    async def test_fr020_phase_b_marks_successful_tasks_as_green(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """FR-020: Phase B must mark tasks as 'green' when GREEN check passes."""
        mock_check_strategy.tests_must_pass = AsyncMock(return_value=passing_check())

        green_ids: list[str] = []

        async def capture_upsert(task: Task) -> None:
            if task.status == "green":
                green_ids.append(task.id)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        assert "T001" in green_ids, "T001 must be marked 'green' after successful GREEN check"
        assert "T002" in green_ids, "T002 must be marked 'green' after successful GREEN check"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: empty task groups, single tasks, etc."""

    async def test_empty_parallel_group_completes_without_error(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """Edge case: run_parallel_group with empty list must succeed without error."""
        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        # Must not raise
        await runner.run_parallel_group([])

    async def test_parallel_group_with_single_task_behaves_correctly(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """Edge case: single-task parallel group must still complete RED→GREEN."""
        green_ids: list[str] = []

        async def capture_upsert(task: Task) -> None:
            if task.status == "green":
                green_ids.append(task.id)

        mock_store.upsert_task = capture_upsert

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [make_task("T001", parallel=True, file_path="src/a.py")]
        await runner.run_parallel_group(tasks)

        assert "T001" in green_ids

    async def test_all_phase_a_failures_prevent_phase_b(
        self, mock_check_strategy, mock_store, mock_agent_adapter, store_lock
    ) -> None:
        """Edge case: if all tasks fail Phase A (RED), Phase B must not execute."""
        mock_check_strategy.tests_must_fail = AsyncMock(return_value=failing_check())
        mock_check_strategy.tests_must_pass = AsyncMock(return_value=passing_check())

        runner = make_runner(
            check_strategy=mock_check_strategy,
            store=mock_store,
            agent_adapter=mock_agent_adapter,
            store_lock=store_lock,
        )
        tasks = [
            make_task("T001", parallel=True, file_path="src/a.py"),
            make_task("T002", parallel=True, file_path="src/b.py"),
        ]
        await runner.run_parallel_group(tasks)

        mock_check_strategy.tests_must_pass.assert_not_called()
