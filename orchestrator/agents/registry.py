"""Agent registry with 14 agent directory loading, progressive knowledge injection,
and session continuation.

FR-027: Agent registry MUST load all 14 existing ESSKILLAGENT agent directories
        without requiring modifications to agent directories.
FR-028: Knowledge base injection MUST use absolute file paths and load
        progressively as stages advance.
FR-029: Session continuation MUST resume existing agent sessions rather than
        creating new ones.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

VALID_STAGES: list[str] = ["spec", "plan", "implement", "acceptance"]


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single registered agent."""

    name: str
    directory: str
    knowledge_paths: list[str]
    stages: list[str]


class AgentRegistry:
    """Registry for loading and managing agent directories."""

    def __init__(self, base_path: str) -> None:
        if not base_path:
            raise ValueError("base_path must not be empty")
        self.base_path = base_path
        self._agents: dict[str, AgentConfig] = {}
        self._sessions: dict[str, str] = {}
        # Store raw knowledge file specs per agent for stage filtering
        self._knowledge_specs: dict[str, list] = {}

    def load(self) -> None:
        """Scan base_path, read agent.json from each subdirectory, register agents."""
        base = self.base_path

        if not os.path.exists(base):
            raise FileNotFoundError(f"base_path does not exist: {base}")

        if not os.path.isdir(base):
            raise NotADirectoryError(f"base_path is not a directory: {base}")

        # Clear agents to ensure idempotency (replace, don't duplicate)
        # Sessions are preserved across reloads
        self._agents = {}
        self._knowledge_specs = {}

        for entry in os.scandir(base):
            if not entry.is_dir():
                continue
            self._try_load_agent(entry.path)

    def _try_load_agent(self, agent_dir: str) -> None:
        """Attempt to load a single agent from its directory. Skip on failure."""
        config_path = os.path.join(agent_dir, "agent.json")

        if not os.path.isfile(config_path):
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        name = data.get("name")
        if not name:
            return

        stages = data.get("stages", [])
        knowledge_files = data.get("knowledge_files", [])

        knowledge_paths = self._resolve_knowledge_paths(agent_dir, knowledge_files)

        cfg = AgentConfig(
            name=name,
            directory=agent_dir,
            knowledge_paths=knowledge_paths,
            stages=stages,
        )
        self._agents[name] = cfg
        self._knowledge_specs[name] = knowledge_files

    def _resolve_knowledge_paths(
        self, agent_dir: str, knowledge_files: list
    ) -> list[str]:
        """Resolve all knowledge file specs to absolute paths."""
        paths: list[str] = []
        for spec in knowledge_files:
            filename = self._extract_filename(spec)
            if filename:
                paths.append(os.path.join(agent_dir, filename))
        return paths

    def _extract_filename(self, spec: object) -> str:
        """Extract filename from a knowledge file spec (str or dict)."""
        if isinstance(spec, str):
            return spec
        if isinstance(spec, dict):
            return spec.get("file", "")
        return ""

    def get_agent(self, name: str) -> AgentConfig:
        """Lookup agent by name. Raises KeyError for unknown agents."""
        if name not in self._agents:
            raise KeyError(f"Agent not registered: {name!r}")
        return self._agents[name]

    def list_agents(self) -> list[str]:
        """Return all registered agent names."""
        return list(self._agents.keys())

    def get_knowledge_paths_for_stage(
        self, agent_name: str, stage: str
    ) -> list[str]:
        """Return absolute paths for knowledge files relevant to the given stage.

        Simple string specs are available in all stages.
        Object specs with 'stages' key are only available in listed stages.
        Raises KeyError for unknown agent, ValueError for unknown stage.
        """
        if agent_name not in self._agents:
            raise KeyError(f"Agent not registered: {agent_name!r}")
        if stage not in VALID_STAGES:
            raise ValueError(f"Unknown stage: {stage!r}. Valid stages: {VALID_STAGES}")

        cfg = self._agents[agent_name]
        knowledge_files = self._knowledge_specs.get(agent_name, [])

        paths: list[str] = []
        for spec in knowledge_files:
            if isinstance(spec, str):
                # Simple string: available in all stages
                paths.append(os.path.join(cfg.directory, spec))
            elif isinstance(spec, dict):
                filename = spec.get("file", "")
                allowed_stages = spec.get("stages", VALID_STAGES)
                if filename and stage in allowed_stages:
                    paths.append(os.path.join(cfg.directory, filename))

        return paths

    def save_session(self, agent_name: str, session_id: str) -> None:
        """Store session ID in memory for the given agent."""
        self._sessions[agent_name] = session_id

    def get_session(self, agent_name: str) -> str:
        """Return session ID or empty string if not saved."""
        return self._sessions.get(agent_name, "")

    def clear_session(self, agent_name: str) -> None:
        """Remove session for agent. No-op if not found."""
        self._sessions.pop(agent_name, None)
