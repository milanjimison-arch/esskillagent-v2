"""Claude SDK/CLI dual adapter and session continuation manager.

R-004: adapter.py tries Claude Agent SDK first; on ImportError, falls back to
CLI subprocess invocation. The adapter exposes a unified interface.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentResult:
    """Unified return value for all adapter calls."""

    output: str
    session_id: str
    success: bool
    error: str | None


@dataclass(frozen=True)
class AdapterConfig:
    """Construction parameters for adapters."""

    use_sdk: bool
    cwd: str
    timeout: int

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if not self.cwd:
            raise ValueError("cwd must not be empty")


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class AgentAdapter(ABC):
    """Abstract base class enforcing the unified adapter interface."""

    @abstractmethod
    async def send_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        """Send a new prompt to the agent."""
        ...

    @abstractmethod
    async def continue_session(
        self, session_id: str, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        """Continue an existing agent session."""
        ...


# ---------------------------------------------------------------------------
# SDK stub (async generator)
# ---------------------------------------------------------------------------


async def _sdk_query(
    prompt: str,
    resume: str | None,
    cwd: str,
    timeout: int,
) -> AsyncGenerator[Any, None]:
    """Stub async generator for Claude Agent SDK queries.

    Tests mock this at orchestrator.agents.adapter._sdk_query.
    """
    yield  # pragma: no cover


# ---------------------------------------------------------------------------
# CLI Adapter
# ---------------------------------------------------------------------------


class CLIAdapter(AgentAdapter):
    """Invokes the Claude CLI via subprocess."""

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def _build_cmd(self, prompt: str) -> list[str]:
        return ["claude", "-p", prompt, "--output-format", "json"]

    def _build_resume_cmd(self, prompt: str, session_id: str) -> list[str]:
        return [
            "claude",
            "--resume",
            session_id,
            "-p",
            prompt,
            "--output-format",
            "json",
        ]

    def _parse_result(self, proc: Any) -> AgentResult:
        if proc.returncode != 0:
            stderr_text = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"CLI exited with code {proc.returncode}: {stderr_text}",
            )
        try:
            data = json.loads(proc.stdout)
            return AgentResult(
                output=data.get("result", ""),
                session_id=data.get("session_id", ""),
                success=True,
                error=None,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"Failed to parse CLI JSON output: {exc}",
            )

    async def send_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        cmd = self._build_cmd(prompt)
        return self._run(cmd)

    async def continue_session(
        self, session_id: str, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        cmd = self._build_resume_cmd(prompt, session_id)
        return self._run(cmd)

    def _run(self, cmd: list[str]) -> AgentResult:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.config.timeout,
                cwd=self.config.cwd,
            )
            return self._parse_result(proc)
        except FileNotFoundError as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"claude not found: {exc}",
            )
        except subprocess.TimeoutExpired as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"CLI timed out after {exc.timeout}s",
            )
        except OSError as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"OS error running CLI: {exc}",
            )


# ---------------------------------------------------------------------------
# SDK Adapter
# ---------------------------------------------------------------------------


class SDKAdapter(AgentAdapter):
    """Uses the Claude Agent SDK via the _sdk_query async generator."""

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    async def _query(self, prompt: str, resume: str | None) -> AgentResult:
        try:
            gen = _sdk_query(
                prompt=prompt,
                resume=resume,
                cwd=self.config.cwd,
                timeout=self.config.timeout,
            )
            msg = None
            async for item in gen:
                msg = item
                break
            if msg is None:
                return AgentResult(
                    output="",
                    session_id="",
                    success=False,
                    error="SDK returned no messages",
                )
            return AgentResult(
                output=msg.result,
                session_id=msg.session_id,
                success=True,
                error=None,
            )
        except ImportError as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"SDK not available: {exc}",
            )
        except TimeoutError as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"SDK timed out: {exc}",
            )
        except RuntimeError as exc:
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"SDK runtime error: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(
                output="",
                session_id="",
                success=False,
                error=f"Unexpected SDK error: {exc}",
            )

    async def send_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        return await self._query(prompt=prompt, resume=None)

    async def continue_session(
        self, session_id: str, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        return await self._query(prompt=prompt, resume=session_id)


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class SessionManager:
    """Tracks session IDs and routes calls to send_prompt or continue_session."""

    def __init__(self, adapter: AgentAdapter) -> None:
        self.adapter = adapter
        self._sessions: dict[str, str] = {}

    def get_session(self, key: str) -> str:
        """Return the stored session_id for key, or '' if not found."""
        return self._sessions.get(key, "")

    def save_session(self, key: str, session_id: str) -> None:
        """Store session_id for key."""
        self._sessions[key] = session_id

    def clear_session(self, key: str) -> None:
        """Remove session_id for key; no error if key is absent."""
        self._sessions.pop(key, None)

    async def send_with_session(
        self, agent_key: str, prompt: str, context: dict[str, Any]
    ) -> AgentResult:
        """Route to continue_session if a prior session exists, else send_prompt."""
        existing = self.get_session(agent_key)
        if existing:
            result = await self.adapter.continue_session(
                session_id=existing,
                prompt=prompt,
                context=context,
            )
        else:
            result = await self.adapter.send_prompt(prompt=prompt, context=context)

        if result.session_id:
            self.save_session(agent_key, result.session_id)

        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_adapter(config: AdapterConfig) -> AgentAdapter:
    """Return SDKAdapter if config.use_sdk, else CLIAdapter."""
    if config.use_sdk:
        return SDKAdapter(config)
    return CLIAdapter(config)
