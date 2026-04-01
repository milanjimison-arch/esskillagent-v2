"""Unit tests for Claude SDK/CLI dual adapter and session continuation manager.

FR-027: Agent registry MUST load all 14 existing ESSKILLAGENT agent directories
        without requiring modifications to agent directories.
FR-029: Session continuation MUST resume existing agent sessions rather than
        creating new ones.

Spec Reference (from specs/spec.md):
    SPEC-082: Given an agent session that was previously created, when a follow-up
              call is needed, then session continuation resumes the existing session
              rather than creating a new one.

R-004 (from specs/plan.md): adapter.py tries Claude Agent SDK first; on ImportError,
      falls back to CLI subprocess invocation. The adapter exposes a unified interface.

These are RED-phase tests. They MUST FAIL until orchestrator/agents/adapter.py
implements the required classes and functions. The stub currently raises
NotImplementedError on import, which will cause all tests to fail at collection
time — demonstrating the RED state.

Test coverage areas:
    - AgentAdapter abstract interface contract enforcement
    - CLIAdapter subprocess invocation with correct arguments
    - SDKAdapter API call with correct parameters
    - SessionManager session ID tracking and continuation
    - create_adapter() factory function returning correct adapter type
    - Error handling for invalid configurations
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.
# The stub raises NotImplementedError on import, so the entire test module
# will be collected but all tests will error at the fixture/import stage —
# this is the intended RED state.
# ---------------------------------------------------------------------------
from orchestrator.agents.adapter import (
    AdapterConfig,
    AgentAdapter,
    AgentResult,
    CLIAdapter,
    SDKAdapter,
    SessionManager,
    create_adapter,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_config() -> AdapterConfig:
    """AdapterConfig that selects the CLI adapter."""
    return AdapterConfig(use_sdk=False, cwd="/tmp/project", timeout=300)


@pytest.fixture
def sdk_config() -> AdapterConfig:
    """AdapterConfig that selects the SDK adapter."""
    return AdapterConfig(use_sdk=True, cwd="/tmp/project", timeout=300)


@pytest.fixture
def cli_adapter(cli_config: AdapterConfig) -> CLIAdapter:
    return CLIAdapter(cli_config)


@pytest.fixture
def sdk_adapter(sdk_config: AdapterConfig) -> SDKAdapter:
    return SDKAdapter(sdk_config)


@pytest.fixture
def session_manager(cli_adapter: CLIAdapter) -> SessionManager:
    return SessionManager(adapter=cli_adapter)


# ---------------------------------------------------------------------------
# 1. AgentAdapter abstract interface contract
# ---------------------------------------------------------------------------


class TestAgentAdapterIsABC:
    """FR-027 / R-004: AgentAdapter MUST be an abstract base class that
    enforces the unified interface for both SDK and CLI backends."""

    def test_agent_adapter_cannot_be_instantiated_directly(self):
        """Instantiating AgentAdapter directly MUST raise TypeError."""
        with pytest.raises(TypeError):
            AgentAdapter()  # type: ignore[abstract]

    def test_agent_adapter_is_a_class(self):
        """AgentAdapter must be a class."""
        import inspect
        assert inspect.isclass(AgentAdapter)

    def test_agent_adapter_inherits_from_abc(self):
        """AgentAdapter MUST subclass abc.ABC."""
        import abc
        assert issubclass(AgentAdapter, abc.ABC)

    def test_send_prompt_is_abstract(self):
        """send_prompt MUST be listed in __abstractmethods__."""
        assert "send_prompt" in AgentAdapter.__abstractmethods__

    def test_continue_session_is_abstract(self):
        """continue_session MUST be listed in __abstractmethods__."""
        assert "continue_session" in AgentAdapter.__abstractmethods__

    def test_abstract_methods_set_is_exactly_two(self):
        """AgentAdapter has exactly send_prompt and continue_session as
        abstract methods (no unexpected extras, no missing ones)."""
        expected = {"send_prompt", "continue_session"}
        assert set(AgentAdapter.__abstractmethods__) == expected

    def test_concrete_subclass_missing_send_prompt_cannot_be_instantiated(self):
        """A subclass implementing only continue_session MUST still raise
        TypeError on instantiation."""

        class Partial(AgentAdapter):
            async def continue_session(
                self, session_id: str, prompt: str, context: dict[str, Any]
            ) -> AgentResult:
                return AgentResult(output="", session_id=session_id, success=True, error=None)

        with pytest.raises(TypeError):
            Partial()

    def test_concrete_subclass_missing_continue_session_cannot_be_instantiated(self):
        """A subclass implementing only send_prompt MUST still raise
        TypeError on instantiation."""

        class Partial(AgentAdapter):
            async def send_prompt(
                self, prompt: str, context: dict[str, Any]
            ) -> AgentResult:
                return AgentResult(output="", session_id="", success=True, error=None)

        with pytest.raises(TypeError):
            Partial()

    def test_concrete_subclass_implementing_both_methods_can_be_instantiated(self):
        """A complete subclass must instantiate without TypeError."""

        class Concrete(AgentAdapter):
            async def send_prompt(
                self, prompt: str, context: dict[str, Any]
            ) -> AgentResult:
                return AgentResult(output="ok", session_id="s1", success=True, error=None)

            async def continue_session(
                self, session_id: str, prompt: str, context: dict[str, Any]
            ) -> AgentResult:
                return AgentResult(output="ok", session_id=session_id, success=True, error=None)

        instance = Concrete()
        assert isinstance(instance, AgentAdapter)


# ---------------------------------------------------------------------------
# 2. AgentResult dataclass
# ---------------------------------------------------------------------------


class TestAgentResult:
    """AgentResult is the unified return value for all adapter calls."""

    def test_agent_result_has_output_field(self):
        """AgentResult MUST expose an 'output' field."""
        result = AgentResult(output="hello", session_id="abc", success=True, error=None)
        assert result.output == "hello"

    def test_agent_result_has_session_id_field(self):
        """AgentResult MUST expose a 'session_id' field."""
        result = AgentResult(output="", session_id="sess-42", success=True, error=None)
        assert result.session_id == "sess-42"

    def test_agent_result_has_success_field(self):
        """AgentResult MUST expose a boolean 'success' field."""
        ok = AgentResult(output="out", session_id="", success=True, error=None)
        fail = AgentResult(output="", session_id="", success=False, error="timeout")
        assert ok.success is True
        assert fail.success is False

    def test_agent_result_has_error_field(self):
        """AgentResult MUST expose an optional 'error' field."""
        result = AgentResult(output="", session_id="", success=False, error="not found")
        assert result.error == "not found"

    def test_agent_result_error_is_none_on_success(self):
        """error field MUST be None when the call succeeds."""
        result = AgentResult(output="ok", session_id="s", success=True, error=None)
        assert result.error is None

    def test_agent_result_is_immutable(self):
        """AgentResult must be a frozen dataclass (immutable)."""
        result = AgentResult(output="out", session_id="s", success=True, error=None)
        with pytest.raises((AttributeError, TypeError)):
            result.output = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. AdapterConfig dataclass
# ---------------------------------------------------------------------------


class TestAdapterConfig:
    """AdapterConfig holds construction parameters for adapters."""

    def test_adapter_config_stores_use_sdk_flag(self):
        """AdapterConfig MUST store use_sdk as a bool."""
        cfg = AdapterConfig(use_sdk=True, cwd="/p", timeout=60)
        assert cfg.use_sdk is True

    def test_adapter_config_stores_cwd(self):
        """AdapterConfig MUST store the working directory."""
        cfg = AdapterConfig(use_sdk=False, cwd="/tmp/project", timeout=60)
        assert cfg.cwd == "/tmp/project"

    def test_adapter_config_stores_timeout(self):
        """AdapterConfig MUST store the timeout in seconds."""
        cfg = AdapterConfig(use_sdk=False, cwd="/p", timeout=5400)
        assert cfg.timeout == 5400

    def test_adapter_config_is_immutable(self):
        """AdapterConfig must be frozen (immutable)."""
        cfg = AdapterConfig(use_sdk=False, cwd="/p", timeout=60)
        with pytest.raises((AttributeError, TypeError)):
            cfg.use_sdk = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. CLIAdapter — subprocess invocation
# ---------------------------------------------------------------------------


class TestCLIAdapterSendPrompt:
    """FR-029 / R-004: CLIAdapter MUST invoke the Claude CLI subprocess
    with the correct arguments when send_prompt is called."""

    @pytest.mark.asyncio
    async def test_send_prompt_invokes_subprocess(self, cli_adapter: CLIAdapter):
        """send_prompt MUST invoke a subprocess (not call the SDK)."""
        mock_proc_output = b'{"result": "Answer text", "session_id": "cli-sess-1"}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_proc_output,
                stderr=b"",
            )
            result = await cli_adapter.send_prompt(
                prompt="What is 2+2?",
                context={},
            )
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_prompt_passes_p_flag(self, cli_adapter: CLIAdapter):
        """CLIAdapter MUST pass the -p flag to the claude CLI."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "ok", "session_id": "s"}',
                stderr=b"",
            )
            await cli_adapter.send_prompt(prompt="Hello", context={})

        call_args = mock_run.call_args
        cmd = call_args[0][0]  # First positional arg is the command list
        assert "-p" in cmd, f"Expected '-p' in CLI command, got: {cmd}"

    @pytest.mark.asyncio
    async def test_send_prompt_passes_output_format_json(self, cli_adapter: CLIAdapter):
        """CLIAdapter MUST request JSON output via --output-format json."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "ok", "session_id": "s"}',
                stderr=b"",
            )
            await cli_adapter.send_prompt(prompt="Hello", context={})

        cmd = mock_run.call_args[0][0]
        assert "--output-format" in cmd, "Expected '--output-format' in CLI command"
        fmt_idx = cmd.index("--output-format")
        assert cmd[fmt_idx + 1] == "json", "Expected 'json' after '--output-format'"

    @pytest.mark.asyncio
    async def test_send_prompt_returns_agent_result_with_output(
        self, cli_adapter: CLIAdapter
    ):
        """send_prompt MUST return an AgentResult with the CLI result text."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "Answer text", "session_id": "cli-sess-1"}',
                stderr=b"",
            )
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert isinstance(result, AgentResult)
        assert result.output == "Answer text"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_prompt_captures_session_id_from_cli_output(
        self, cli_adapter: CLIAdapter
    ):
        """CLIAdapter MUST extract session_id from the CLI JSON response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "Answer", "session_id": "cli-sess-42"}',
                stderr=b"",
            )
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert result.session_id == "cli-sess-42"

    @pytest.mark.asyncio
    async def test_send_prompt_returns_failure_on_nonzero_exit(
        self, cli_adapter: CLIAdapter
    ):
        """A non-zero subprocess exit code MUST produce success=False."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout=b"",
                stderr=b"error: unknown flag",
            )
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_prompt_handles_file_not_found(self, cli_adapter: CLIAdapter):
        """If the claude binary is not found, send_prompt MUST return
        success=False with a descriptive error (not raise)."""
        with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")):
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None
        assert "claude" in result.error.lower() or "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_prompt_handles_timeout(self, cli_adapter: CLIAdapter):
        """A subprocess.TimeoutExpired MUST produce success=False (not raise)."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300),
        ):
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# 5. CLIAdapter — continue_session (session resumption)
# ---------------------------------------------------------------------------


class TestCLIAdapterContinueSession:
    """FR-029: Session continuation MUST pass --resume <session_id> to the CLI."""

    @pytest.mark.asyncio
    async def test_continue_session_passes_resume_flag(self, cli_adapter: CLIAdapter):
        """continue_session MUST include --resume <session_id> in the CLI command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "Continued", "session_id": "cli-sess-42"}',
                stderr=b"",
            )
            await cli_adapter.continue_session(
                session_id="cli-sess-42",
                prompt="Follow-up question",
                context={},
            )

        cmd = mock_run.call_args[0][0]
        assert "--resume" in cmd, "Expected '--resume' flag in CLI command"
        resume_idx = cmd.index("--resume")
        assert cmd[resume_idx + 1] == "cli-sess-42", (
            f"Expected session_id 'cli-sess-42' after '--resume', got: {cmd[resume_idx + 1]}"
        )

    @pytest.mark.asyncio
    async def test_continue_session_returns_agent_result(self, cli_adapter: CLIAdapter):
        """continue_session MUST return an AgentResult."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "Continued output", "session_id": "cli-sess-42"}',
                stderr=b"",
            )
            result = await cli_adapter.continue_session(
                session_id="cli-sess-42",
                prompt="Follow-up",
                context={},
            )

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.output == "Continued output"

    @pytest.mark.asyncio
    async def test_continue_session_preserves_session_id_in_result(
        self, cli_adapter: CLIAdapter
    ):
        """The returned AgentResult MUST carry the session_id from the response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b'{"result": "out", "session_id": "cli-sess-99"}',
                stderr=b"",
            )
            result = await cli_adapter.continue_session(
                session_id="cli-sess-99",
                prompt="Next",
                context={},
            )

        assert result.session_id == "cli-sess-99"


# ---------------------------------------------------------------------------
# 6. SDKAdapter — SDK API call
# ---------------------------------------------------------------------------


class TestSDKAdapterSendPrompt:
    """R-004: SDKAdapter MUST use the Claude Agent SDK (not subprocess)."""

    @pytest.mark.asyncio
    async def test_send_prompt_calls_sdk_query(self, sdk_adapter: SDKAdapter):
        """send_prompt MUST invoke the SDK query function, not subprocess.run."""
        mock_result_msg = MagicMock()
        mock_result_msg.result = "SDK answer"
        mock_result_msg.session_id = "sdk-sess-1"

        async def fake_aiter():
            yield mock_result_msg

        with patch(
            "orchestrator.agents.adapter._sdk_query",
            return_value=fake_aiter(),
        ) as mock_query:
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        mock_query.assert_called_once()
        assert result.success is True
        assert result.output == "SDK answer"

    @pytest.mark.asyncio
    async def test_send_prompt_returns_session_id_from_sdk(
        self, sdk_adapter: SDKAdapter
    ):
        """SDKAdapter MUST capture the session_id emitted by the SDK."""
        mock_msg = MagicMock()
        mock_msg.result = "output text"
        mock_msg.session_id = "sdk-sess-77"

        async def fake_aiter():
            yield mock_msg

        with patch(
            "orchestrator.agents.adapter._sdk_query",
            return_value=fake_aiter(),
        ):
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        assert result.session_id == "sdk-sess-77"

    @pytest.mark.asyncio
    async def test_send_prompt_returns_failure_when_sdk_unavailable(
        self, sdk_adapter: SDKAdapter
    ):
        """If the SDK import raises ImportError, send_prompt MUST fall back
        to returning success=False with a clear error (not propagate ImportError)."""
        with patch(
            "orchestrator.agents.adapter._sdk_query",
            side_effect=ImportError("claude_agent_sdk not installed"),
        ):
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_prompt_returns_failure_on_sdk_timeout(
        self, sdk_adapter: SDKAdapter
    ):
        """An asyncio.TimeoutError from the SDK MUST produce success=False."""
        with patch(
            "orchestrator.agents.adapter._sdk_query",
            side_effect=asyncio.TimeoutError,
        ):
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# 7. SDKAdapter — continue_session
# ---------------------------------------------------------------------------


class TestSDKAdapterContinueSession:
    """FR-029: SDKAdapter MUST pass the resume parameter to the SDK query."""

    @pytest.mark.asyncio
    async def test_continue_session_passes_resume_to_sdk(
        self, sdk_adapter: SDKAdapter
    ):
        """continue_session MUST pass session_id as the resume parameter
        to the SDK query call."""
        mock_msg = MagicMock()
        mock_msg.result = "Resumed output"
        mock_msg.session_id = "sdk-sess-42"

        async def fake_aiter():
            yield mock_msg

        with patch(
            "orchestrator.agents.adapter._sdk_query",
            return_value=fake_aiter(),
        ) as mock_query:
            await sdk_adapter.continue_session(
                session_id="sdk-sess-42",
                prompt="Follow-up",
                context={},
            )

        call_kwargs = mock_query.call_args[1] if mock_query.call_args[1] else {}
        call_args_flat = mock_query.call_args
        # The session_id / resume kwarg must have been forwarded
        assert "sdk-sess-42" in str(call_args_flat), (
            "Expected session_id 'sdk-sess-42' to be forwarded to SDK query"
        )

    @pytest.mark.asyncio
    async def test_continue_session_returns_agent_result(
        self, sdk_adapter: SDKAdapter
    ):
        """continue_session MUST return an AgentResult."""
        mock_msg = MagicMock()
        mock_msg.result = "Resumed"
        mock_msg.session_id = "sdk-sess-42"

        async def fake_aiter():
            yield mock_msg

        with patch(
            "orchestrator.agents.adapter._sdk_query",
            return_value=fake_aiter(),
        ):
            result = await sdk_adapter.continue_session(
                session_id="sdk-sess-42",
                prompt="Follow-up",
                context={},
            )

        assert isinstance(result, AgentResult)
        assert result.success is True


# ---------------------------------------------------------------------------
# 8. SessionManager — session ID tracking and continuation
# ---------------------------------------------------------------------------


class TestSessionManagerTracking:
    """FR-029 / SPEC-082: SessionManager MUST track session IDs so that
    subsequent calls can resume the same session."""

    def test_session_manager_starts_with_no_sessions(
        self, session_manager: SessionManager
    ):
        """A fresh SessionManager has no stored sessions."""
        assert session_manager.get_session("agent-a") == "" or \
               session_manager.get_session("agent-a") is None

    def test_save_and_get_session_id(self, session_manager: SessionManager):
        """save_session followed by get_session MUST return the same session_id."""
        session_manager.save_session("agent-a", "sess-001")
        assert session_manager.get_session("agent-a") == "sess-001"

    def test_get_session_returns_empty_string_for_unknown_key(
        self, session_manager: SessionManager
    ):
        """get_session MUST return an empty string (not None/KeyError) for
        an unregistered agent key."""
        result = session_manager.get_session("nonexistent-agent")
        assert result == ""

    def test_save_session_overwrites_previous_value(
        self, session_manager: SessionManager
    ):
        """Saving a new session_id for the same key MUST replace the old value."""
        session_manager.save_session("agent-b", "old-sess")
        session_manager.save_session("agent-b", "new-sess")
        assert session_manager.get_session("agent-b") == "new-sess"

    def test_clear_session_removes_stored_id(self, session_manager: SessionManager):
        """clear_session MUST remove the session_id so get_session returns ''."""
        session_manager.save_session("agent-c", "sess-xyz")
        session_manager.clear_session("agent-c")
        assert session_manager.get_session("agent-c") == ""

    def test_clear_session_on_unknown_key_does_not_raise(
        self, session_manager: SessionManager
    ):
        """Clearing a session that does not exist MUST not raise any exception."""
        session_manager.clear_session("ghost-agent")  # must not raise

    def test_multiple_agents_tracked_independently(
        self, session_manager: SessionManager
    ):
        """SessionManager MUST track sessions per-agent independently."""
        session_manager.save_session("specifier", "sess-spec-1")
        session_manager.save_session("reviewer", "sess-rev-2")

        assert session_manager.get_session("specifier") == "sess-spec-1"
        assert session_manager.get_session("reviewer") == "sess-rev-2"


# ---------------------------------------------------------------------------
# 9. SessionManager — send_with_session (auto-continuation)
# ---------------------------------------------------------------------------


class TestSessionManagerSendWithSession:
    """FR-029 / SPEC-082: SessionManager.send_with_session MUST automatically
    use continue_session when a prior session_id is stored, and save the new
    session_id from the response."""

    @pytest.mark.asyncio
    async def test_send_with_session_calls_send_prompt_when_no_prior_session(
        self, session_manager: SessionManager
    ):
        """When no session_id is stored for the agent key, send_with_session
        MUST call adapter.send_prompt (fresh call)."""
        mock_result = AgentResult(
            output="First response",
            session_id="new-sess-1",
            success=True,
            error=None,
        )
        session_manager.adapter.send_prompt = AsyncMock(return_value=mock_result)
        session_manager.adapter.continue_session = AsyncMock()

        await session_manager.send_with_session(
            agent_key="specifier",
            prompt="Initial task",
            context={},
        )

        session_manager.adapter.send_prompt.assert_awaited_once()
        session_manager.adapter.continue_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_with_session_saves_returned_session_id(
        self, session_manager: SessionManager
    ):
        """After a successful send_prompt, the returned session_id MUST be
        stored in SessionManager for later continuation."""
        mock_result = AgentResult(
            output="First response",
            session_id="new-sess-42",
            success=True,
            error=None,
        )
        session_manager.adapter.send_prompt = AsyncMock(return_value=mock_result)

        await session_manager.send_with_session(
            agent_key="specifier",
            prompt="Initial task",
            context={},
        )

        assert session_manager.get_session("specifier") == "new-sess-42"

    @pytest.mark.asyncio
    async def test_send_with_session_calls_continue_session_when_prior_session_exists(
        self, session_manager: SessionManager
    ):
        """When a session_id is already stored for the agent key,
        send_with_session MUST call adapter.continue_session (resume call)."""
        session_manager.save_session("reviewer", "existing-sess-7")

        mock_result = AgentResult(
            output="Resumed response",
            session_id="existing-sess-7",
            success=True,
            error=None,
        )
        session_manager.adapter.continue_session = AsyncMock(return_value=mock_result)
        session_manager.adapter.send_prompt = AsyncMock()

        await session_manager.send_with_session(
            agent_key="reviewer",
            prompt="Follow-up review",
            context={},
        )

        session_manager.adapter.continue_session.assert_awaited_once()
        # The existing session_id must have been passed to continue_session
        call_kwargs = session_manager.adapter.continue_session.call_args
        assert "existing-sess-7" in str(call_kwargs)
        session_manager.adapter.send_prompt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_with_session_returns_agent_result(
        self, session_manager: SessionManager
    ):
        """send_with_session MUST return the AgentResult from the adapter."""
        mock_result = AgentResult(
            output="Expected output",
            session_id="s",
            success=True,
            error=None,
        )
        session_manager.adapter.send_prompt = AsyncMock(return_value=mock_result)

        result = await session_manager.send_with_session(
            agent_key="planner",
            prompt="Plan this",
            context={},
        )

        assert isinstance(result, AgentResult)
        assert result.output == "Expected output"

    @pytest.mark.asyncio
    async def test_send_with_session_does_not_save_empty_session_id(
        self, session_manager: SessionManager
    ):
        """If the adapter returns an empty session_id, SessionManager MUST NOT
        overwrite a previously saved session_id with an empty string."""
        session_manager.save_session("specifier", "good-sess")

        mock_result = AgentResult(
            output="Out",
            session_id="",  # empty — no update expected
            success=True,
            error=None,
        )
        session_manager.adapter.continue_session = AsyncMock(return_value=mock_result)

        await session_manager.send_with_session(
            agent_key="specifier",
            prompt="Follow-up",
            context={},
        )

        assert session_manager.get_session("specifier") == "good-sess"


# ---------------------------------------------------------------------------
# 10. create_adapter() factory function
# ---------------------------------------------------------------------------


class TestCreateAdapterFactory:
    """R-004: create_adapter(config) MUST return CLIAdapter when use_sdk=False
    and SDKAdapter when use_sdk=True."""

    def test_create_adapter_returns_cli_adapter_when_use_sdk_false(self):
        """create_adapter with use_sdk=False MUST return a CLIAdapter instance."""
        config = AdapterConfig(use_sdk=False, cwd="/tmp", timeout=300)
        adapter = create_adapter(config)
        assert isinstance(adapter, CLIAdapter)

    def test_create_adapter_returns_sdk_adapter_when_use_sdk_true(self):
        """create_adapter with use_sdk=True MUST return an SDKAdapter instance."""
        config = AdapterConfig(use_sdk=True, cwd="/tmp", timeout=300)
        adapter = create_adapter(config)
        assert isinstance(adapter, SDKAdapter)

    def test_create_adapter_returns_agent_adapter_subclass(self):
        """The returned adapter MUST be an instance of AgentAdapter (both variants)."""
        cli = create_adapter(AdapterConfig(use_sdk=False, cwd="/tmp", timeout=60))
        sdk = create_adapter(AdapterConfig(use_sdk=True, cwd="/tmp", timeout=60))
        assert isinstance(cli, AgentAdapter)
        assert isinstance(sdk, AgentAdapter)

    def test_create_adapter_injects_config_into_cli_adapter(self):
        """The CLIAdapter returned by create_adapter MUST hold the provided config."""
        config = AdapterConfig(use_sdk=False, cwd="/workspace", timeout=900)
        adapter = create_adapter(config)
        assert isinstance(adapter, CLIAdapter)
        assert adapter.config.cwd == "/workspace"
        assert adapter.config.timeout == 900

    def test_create_adapter_injects_config_into_sdk_adapter(self):
        """The SDKAdapter returned by create_adapter MUST hold the provided config."""
        config = AdapterConfig(use_sdk=True, cwd="/workspace", timeout=1800)
        adapter = create_adapter(config)
        assert isinstance(adapter, SDKAdapter)
        assert adapter.config.timeout == 1800


# ---------------------------------------------------------------------------
# 11. Error handling for invalid configurations
# ---------------------------------------------------------------------------


class TestAdapterConfigValidation:
    """AdapterConfig MUST validate its inputs and raise descriptive errors
    on invalid configurations."""

    def test_negative_timeout_raises_value_error(self):
        """A timeout of 0 or negative MUST raise ValueError."""
        with pytest.raises(ValueError, match="timeout"):
            AdapterConfig(use_sdk=False, cwd="/tmp", timeout=0)

    def test_empty_cwd_raises_value_error(self):
        """An empty cwd string MUST raise ValueError."""
        with pytest.raises(ValueError, match="cwd"):
            AdapterConfig(use_sdk=False, cwd="", timeout=300)

    def test_valid_config_does_not_raise(self):
        """A well-formed config MUST construct without error."""
        cfg = AdapterConfig(use_sdk=False, cwd="/valid/path", timeout=300)
        assert cfg is not None


class TestCLIAdapterErrorHandling:
    """CLIAdapter MUST not propagate unexpected exceptions as unhandled raises;
    they MUST be wrapped in an AgentResult with success=False."""

    @pytest.mark.asyncio
    async def test_send_prompt_wraps_os_error(self, cli_adapter: CLIAdapter):
        """An OSError from the subprocess MUST produce success=False."""
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_prompt_handles_malformed_json_output(
        self, cli_adapter: CLIAdapter
    ):
        """If the CLI outputs non-JSON text, CLIAdapter MUST still return
        an AgentResult (either with the raw text as output, or success=False
        with a parse error), not raise JSONDecodeError."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b"plain text response (not JSON)",
                stderr=b"",
            )
            result = await cli_adapter.send_prompt(prompt="Q", context={})

        assert isinstance(result, AgentResult)
        # Either parsed as raw text or reported as failure — but MUST not raise


class TestSDKAdapterErrorHandling:
    """SDKAdapter MUST gracefully handle SDK-level errors."""

    @pytest.mark.asyncio
    async def test_send_prompt_wraps_generic_sdk_exception(
        self, sdk_adapter: SDKAdapter
    ):
        """Any unexpected exception from the SDK MUST be caught and produce
        success=False (not propagate)."""
        with patch(
            "orchestrator.agents.adapter._sdk_query",
            side_effect=RuntimeError("SDK internal error"),
        ):
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_send_prompt_returns_failure_when_sdk_returns_empty_result(
        self, sdk_adapter: SDKAdapter
    ):
        """If the SDK emits no messages with a 'result' attribute,
        send_prompt MUST return success=False."""

        async def empty_gen():
            return
            yield  # make it a generator

        with patch(
            "orchestrator.agents.adapter._sdk_query",
            return_value=empty_gen(),
        ):
            result = await sdk_adapter.send_prompt(prompt="Q", context={})

        assert result.success is False
        assert result.error is not None
