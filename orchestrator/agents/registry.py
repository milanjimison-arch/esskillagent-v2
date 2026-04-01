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


class AgentConfig:
    """Configuration for a single registered agent. Stub — not implemented."""

    def __init__(self, name: str, directory: str, knowledge_paths: list[str], stages: list[str]) -> None:
        raise NotImplementedError("AgentConfig not implemented")


class AgentRegistry:
    """Registry for loading and managing agent directories. Stub — not implemented."""

    def __init__(self, base_path: str) -> None:
        raise NotImplementedError("AgentRegistry not implemented")

    def load(self) -> None:
        raise NotImplementedError("AgentRegistry.load not implemented")

    def get_agent(self, name: str) -> AgentConfig:
        raise NotImplementedError("AgentRegistry.get_agent not implemented")

    def list_agents(self) -> list[str]:
        raise NotImplementedError("AgentRegistry.list_agents not implemented")

    def get_knowledge_paths_for_stage(self, agent_name: str, stage: str) -> list[str]:
        raise NotImplementedError("AgentRegistry.get_knowledge_paths_for_stage not implemented")

    def save_session(self, agent_name: str, session_id: str) -> None:
        raise NotImplementedError("AgentRegistry.save_session not implemented")

    def get_session(self, agent_name: str) -> str:
        raise NotImplementedError("AgentRegistry.get_session not implemented")

    def clear_session(self, agent_name: str) -> None:
        raise NotImplementedError("AgentRegistry.clear_session not implemented")
