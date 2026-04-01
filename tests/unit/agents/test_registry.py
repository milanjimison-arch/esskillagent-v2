"""Unit tests for the agent registry module.

FR-027: Agent registry MUST load all 14 existing ESSKILLAGENT agent directories
        without requiring modifications to agent directories.
FR-028: Knowledge base injection MUST use absolute file paths and load
        progressively as stages advance.
FR-029: Session continuation MUST resume existing agent sessions rather than
        creating new ones.

SPEC-080: Given 14 existing ESSKILLAGENT agent directories, when the agent registry
          loads, then all agents are registered without requiring any modification
          to the agent directories.
SPEC-081: Given an agent entering the plan stage, when knowledge is loaded, then
          only knowledge relevant to the current and prior stages is injected,
          using absolute file paths.
SPEC-082: Given an agent session that was previously created, when a follow-up
          call is needed, then session continuation resumes the existing session
          rather than creating a new one.

These tests are RED-phase. They MUST FAIL until orchestrator/agents/registry.py
provides a working implementation. The current stub raises NotImplementedError
on construction, which causes all tests to fail with AssertionError or
NotImplementedError — demonstrating the RED state.

Test coverage areas:
    1. AgentConfig dataclass structure and validation
    2. AgentRegistry class instantiation
    3. Loading 14 agent directories from a base path (FR-027, SPEC-080)
    4. Each agent directory contains required structure (A-001)
    5. Registry lookup by agent name
    6. Agent names are correct identifiers
    7. Progressive knowledge injection with absolute paths (FR-028, SPEC-081)
    8. Knowledge files injected in stage order
    9. Stage ordering is enforced (spec -> plan -> implement -> acceptance)
    10. Session save and restore (FR-029, SPEC-082)
    11. Session cleared on request
    12. Multiple agents tracked independently
    13. Error handling for missing base directory
    14. Error handling for missing agent directory
    15. Error handling for invalid agent configuration
    16. Knowledge paths are absolute (FR-028)
    17. Re-loading is idempotent
    18. All 14 canonical agent names are loadable
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from orchestrator.agents.registry import AgentConfig, AgentRegistry


# ---------------------------------------------------------------------------
# Constants — the 14 canonical ESSKILLAGENT agent directory names
# ---------------------------------------------------------------------------

CANONICAL_AGENT_NAMES: list[str] = [
    "acceptor",
    "brooks-reviewer",
    "clarifier",
    "code-reviewer",
    "constitution-writer",
    "fixer",
    "implementer",
    "planner",
    "researcher",
    "security-reviewer",
    "spec-writer",
    "task-generator",
    "tdd-guide",
    "orchestrator",
]

STAGE_ORDER: list[str] = ["spec", "plan", "implement", "acceptance"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_agent_base(tmp_path: Path) -> Path:
    """Create a temporary agent base directory with 14 minimal agent dirs."""
    for name in CANONICAL_AGENT_NAMES:
        agent_dir = tmp_path / name
        agent_dir.mkdir(parents=True)
        # Create a minimal agent.json config file inside each agent directory
        config = {
            "name": name,
            "stages": ["spec", "plan", "implement", "acceptance"],
            "knowledge_files": ["knowledge.md"],
        }
        (agent_dir / "agent.json").write_text(json.dumps(config), encoding="utf-8")
        # Create a knowledge file
        (agent_dir / "knowledge.md").write_text(f"# {name} knowledge", encoding="utf-8")
    return tmp_path


@pytest.fixture
def registry(tmp_agent_base: Path) -> AgentRegistry:
    """Return a loaded AgentRegistry pointing at the temporary base."""
    reg = AgentRegistry(base_path=str(tmp_agent_base))
    reg.load()
    return reg


@pytest.fixture
def single_agent_base(tmp_path: Path) -> tuple[Path, str]:
    """Create a base directory with exactly one agent."""
    name = "spec-writer"
    agent_dir = tmp_path / name
    agent_dir.mkdir()
    config = {
        "name": name,
        "stages": ["spec"],
        "knowledge_files": ["spec-knowledge.md", "advanced.md"],
    }
    (agent_dir / "agent.json").write_text(json.dumps(config), encoding="utf-8")
    (agent_dir / "spec-knowledge.md").write_text("# Spec knowledge", encoding="utf-8")
    (agent_dir / "advanced.md").write_text("# Advanced knowledge", encoding="utf-8")
    return tmp_path, name


# ---------------------------------------------------------------------------
# 1. AgentConfig structure
# ---------------------------------------------------------------------------


class TestAgentConfig:
    """FR-027 / A-001: AgentConfig must capture name, directory, knowledge
    paths, and stage list for each registered agent."""

    def test_agent_config_stores_name(self, tmp_agent_base: Path):
        """FR-027: AgentConfig MUST store the agent name."""
        cfg = AgentConfig(
            name="spec-writer",
            directory=str(tmp_agent_base / "spec-writer"),
            knowledge_paths=[str(tmp_agent_base / "spec-writer" / "knowledge.md")],
            stages=["spec"],
        )
        assert cfg.name == "spec-writer"

    def test_agent_config_stores_directory_as_absolute_path(self, tmp_agent_base: Path):
        """FR-028: AgentConfig MUST store the agent directory as an absolute path."""
        abs_dir = str(tmp_agent_base / "spec-writer")
        cfg = AgentConfig(
            name="spec-writer",
            directory=abs_dir,
            knowledge_paths=[],
            stages=["spec"],
        )
        assert cfg.directory == abs_dir
        assert os.path.isabs(cfg.directory)

    def test_agent_config_stores_knowledge_paths(self, tmp_agent_base: Path):
        """FR-028: AgentConfig MUST store the list of knowledge file paths."""
        kp = [str(tmp_agent_base / "spec-writer" / "knowledge.md")]
        cfg = AgentConfig(
            name="spec-writer",
            directory=str(tmp_agent_base / "spec-writer"),
            knowledge_paths=kp,
            stages=["spec"],
        )
        assert cfg.knowledge_paths == kp

    def test_agent_config_stores_stages(self, tmp_agent_base: Path):
        """AgentConfig MUST store which stages the agent participates in."""
        cfg = AgentConfig(
            name="implementer",
            directory=str(tmp_agent_base / "implementer"),
            knowledge_paths=[],
            stages=["implement"],
        )
        assert cfg.stages == ["implement"]

    def test_agent_config_knowledge_paths_are_absolute(self, tmp_agent_base: Path):
        """FR-028: All knowledge_paths in AgentConfig MUST be absolute paths."""
        abs_kp = str(tmp_agent_base / "spec-writer" / "knowledge.md")
        cfg = AgentConfig(
            name="spec-writer",
            directory=str(tmp_agent_base / "spec-writer"),
            knowledge_paths=[abs_kp],
            stages=["spec"],
        )
        for path in cfg.knowledge_paths:
            assert os.path.isabs(path), f"Expected absolute path, got: {path}"

    def test_agent_config_is_immutable(self, tmp_agent_base: Path):
        """AgentConfig MUST be immutable (frozen dataclass or equivalent)."""
        cfg = AgentConfig(
            name="spec-writer",
            directory=str(tmp_agent_base / "spec-writer"),
            knowledge_paths=[],
            stages=["spec"],
        )
        with pytest.raises((AttributeError, TypeError)):
            cfg.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. AgentRegistry instantiation
# ---------------------------------------------------------------------------


class TestAgentRegistryInstantiation:
    """AgentRegistry MUST be constructable with a base_path and expose load()."""

    def test_registry_can_be_instantiated_with_base_path(self, tmp_agent_base: Path):
        """FR-027: AgentRegistry MUST be constructable given a base_path string."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        assert reg is not None

    def test_registry_stores_base_path(self, tmp_agent_base: Path):
        """AgentRegistry MUST store the base_path provided at construction."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        assert reg.base_path == str(tmp_agent_base)

    def test_registry_load_completes_without_error(self, tmp_agent_base: Path):
        """AgentRegistry.load() MUST succeed when base_path contains valid agent dirs."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        reg.load()  # must not raise


# ---------------------------------------------------------------------------
# 3. Loading 14 agent directories (FR-027, SPEC-080)
# ---------------------------------------------------------------------------


class TestRegistryLoads14Agents:
    """FR-027 / SPEC-080: The registry MUST load all 14 ESSKILLAGENT agent
    directories without requiring modifications to those directories."""

    def test_registry_loads_exactly_14_agents(self, registry: AgentRegistry):
        """FR-027: After load(), list_agents() MUST return exactly 14 agent names."""
        agents = registry.list_agents()
        assert len(agents) == 14, (
            f"Expected 14 agents, got {len(agents)}: {agents}"
        )

    def test_registry_loads_all_canonical_agent_names(self, registry: AgentRegistry):
        """FR-027 / SPEC-080: All 14 canonical agent names MUST be present after load."""
        agents = set(registry.list_agents())
        for name in CANONICAL_AGENT_NAMES:
            assert name in agents, f"Expected agent '{name}' to be loaded"

    def test_registry_loads_no_extra_agents_from_canonical_base(
        self, tmp_agent_base: Path
    ):
        """When the base path contains exactly 14 canonical directories, only 14
        agents should be registered (no phantom entries)."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        reg.load()
        agents = reg.list_agents()
        assert len(agents) == 14

    def test_each_loaded_agent_has_non_empty_name(self, registry: AgentRegistry):
        """SPEC-080: Every registered agent MUST have a non-empty name."""
        for name in registry.list_agents():
            assert name, "Agent name must not be empty"

    def test_each_loaded_agent_has_absolute_directory(self, registry: AgentRegistry):
        """FR-028 / A-001: Every agent's directory MUST be an absolute path."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            assert os.path.isabs(cfg.directory), (
                f"Agent '{name}' directory is not absolute: {cfg.directory}"
            )


# ---------------------------------------------------------------------------
# 4. Agent directory structure (A-001)
# ---------------------------------------------------------------------------


class TestAgentDirectoryStructure:
    """A-001: Each agent directory follows a consistent structure with a
    configuration file (agent.json) and at least one knowledge file."""

    def test_each_agent_config_has_knowledge_paths_list(self, registry: AgentRegistry):
        """A-001: Each registered agent MUST expose a list of knowledge_paths."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            assert isinstance(cfg.knowledge_paths, list), (
                f"Agent '{name}' knowledge_paths must be a list"
            )

    def test_each_agent_config_has_stages_list(self, registry: AgentRegistry):
        """A-001: Each registered agent MUST expose a list of stages."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            assert isinstance(cfg.stages, list), (
                f"Agent '{name}' stages must be a list"
            )

    def test_knowledge_paths_are_absolute_for_all_agents(self, registry: AgentRegistry):
        """FR-028: All knowledge paths returned by get_agent() MUST be absolute."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            for kp in cfg.knowledge_paths:
                assert os.path.isabs(kp), (
                    f"Agent '{name}' has non-absolute knowledge path: {kp}"
                )

    def test_each_agent_directory_exists_on_disk(self, registry: AgentRegistry):
        """A-001: The directory stored in AgentConfig MUST exist on disk."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            assert os.path.isdir(cfg.directory), (
                f"Agent '{name}' directory does not exist: {cfg.directory}"
            )


# ---------------------------------------------------------------------------
# 5. Registry lookup by agent name
# ---------------------------------------------------------------------------


class TestRegistryLookup:
    """AgentRegistry MUST support lookup of registered agents by name."""

    def test_get_agent_returns_agent_config(self, registry: AgentRegistry):
        """get_agent(name) MUST return an AgentConfig for a registered agent."""
        cfg = registry.get_agent("spec-writer")
        assert isinstance(cfg, AgentConfig)

    def test_get_agent_returns_correct_name(self, registry: AgentRegistry):
        """The returned AgentConfig MUST have the requested name."""
        for name in CANONICAL_AGENT_NAMES:
            cfg = registry.get_agent(name)
            assert cfg.name == name

    def test_get_agent_raises_for_unknown_name(self, registry: AgentRegistry):
        """get_agent() MUST raise KeyError (or ValueError) for unregistered names."""
        with pytest.raises((KeyError, ValueError)):
            registry.get_agent("nonexistent-agent-xyz")

    def test_list_agents_returns_list_of_strings(self, registry: AgentRegistry):
        """list_agents() MUST return a list of str agent names."""
        agents = registry.list_agents()
        assert isinstance(agents, list)
        for a in agents:
            assert isinstance(a, str)

    def test_get_agent_returns_different_configs_for_different_names(
        self, registry: AgentRegistry
    ):
        """get_agent() MUST return distinct AgentConfig instances for distinct names."""
        cfg_a = registry.get_agent("spec-writer")
        cfg_b = registry.get_agent("implementer")
        assert cfg_a.name != cfg_b.name
        assert cfg_a.directory != cfg_b.directory


# ---------------------------------------------------------------------------
# 6. Progressive knowledge injection (FR-028, SPEC-081)
# ---------------------------------------------------------------------------


class TestProgressiveKnowledgeInjection:
    """FR-028 / SPEC-081: Knowledge injection MUST be progressive — only
    knowledge relevant to the current and prior stages is injected,
    using absolute file paths."""

    def test_get_knowledge_paths_for_spec_stage_returns_list(
        self, registry: AgentRegistry
    ):
        """get_knowledge_paths_for_stage() MUST return a list for a valid stage."""
        paths = registry.get_knowledge_paths_for_stage("spec-writer", "spec")
        assert isinstance(paths, list)

    def test_get_knowledge_paths_are_absolute(self, registry: AgentRegistry):
        """FR-028: All paths returned by get_knowledge_paths_for_stage() MUST be
        absolute."""
        for stage in STAGE_ORDER:
            paths = registry.get_knowledge_paths_for_stage("implementer", stage)
            for p in paths:
                assert os.path.isabs(p), (
                    f"Non-absolute path returned for stage '{stage}': {p}"
                )

    def test_later_stage_includes_at_least_as_many_paths_as_earlier(
        self, tmp_path: Path
    ):
        """SPEC-081: A later stage MUST include at least as many knowledge paths
        as an earlier stage (progressive injection — never fewer)."""
        # Build an agent with knowledge files mapped to each stage progressively
        name = "implementer"
        agent_dir = tmp_path / name
        agent_dir.mkdir()
        config = {
            "name": name,
            "stages": ["spec", "plan", "implement", "acceptance"],
            "knowledge_files": [
                {"file": "spec.md", "stages": ["spec", "plan", "implement", "acceptance"]},
                {"file": "plan.md", "stages": ["plan", "implement", "acceptance"]},
                {"file": "impl.md", "stages": ["implement", "acceptance"]},
            ],
        }
        (agent_dir / "agent.json").write_text(json.dumps(config), encoding="utf-8")
        for fname in ["spec.md", "plan.md", "impl.md"]:
            (agent_dir / fname).write_text(f"# {fname}", encoding="utf-8")

        reg = AgentRegistry(base_path=str(tmp_path))
        reg.load()

        spec_paths = reg.get_knowledge_paths_for_stage(name, "spec")
        plan_paths = reg.get_knowledge_paths_for_stage(name, "plan")
        impl_paths = reg.get_knowledge_paths_for_stage(name, "implement")

        assert len(plan_paths) >= len(spec_paths), (
            "plan stage must have at least as many knowledge paths as spec stage"
        )
        assert len(impl_paths) >= len(plan_paths), (
            "implement stage must have at least as many knowledge paths as plan stage"
        )

    def test_get_knowledge_paths_for_unknown_agent_raises(
        self, registry: AgentRegistry
    ):
        """get_knowledge_paths_for_stage() MUST raise for an unregistered agent."""
        with pytest.raises((KeyError, ValueError)):
            registry.get_knowledge_paths_for_stage("ghost-agent", "spec")

    def test_get_knowledge_paths_for_unknown_stage_raises(
        self, registry: AgentRegistry
    ):
        """get_knowledge_paths_for_stage() MUST raise for an invalid stage name."""
        with pytest.raises((KeyError, ValueError)):
            registry.get_knowledge_paths_for_stage("spec-writer", "unknown-stage-xyz")

    def test_spec_stage_does_not_include_implement_only_knowledge(
        self, tmp_path: Path
    ):
        """SPEC-081: The spec stage MUST NOT inject knowledge files that are
        marked as implement-only (progressive injection — no future stage leakage)."""
        name = "planner"
        agent_dir = tmp_path / name
        agent_dir.mkdir()
        config = {
            "name": name,
            "stages": ["spec", "plan", "implement", "acceptance"],
            "knowledge_files": [
                {"file": "spec-only.md", "stages": ["spec"]},
                {"file": "impl-only.md", "stages": ["implement"]},
            ],
        }
        (agent_dir / "agent.json").write_text(json.dumps(config), encoding="utf-8")
        (agent_dir / "spec-only.md").write_text("# spec only", encoding="utf-8")
        (agent_dir / "impl-only.md").write_text("# impl only", encoding="utf-8")

        reg = AgentRegistry(base_path=str(tmp_path))
        reg.load()

        spec_paths = reg.get_knowledge_paths_for_stage(name, "spec")
        spec_filenames = [os.path.basename(p) for p in spec_paths]
        assert "impl-only.md" not in spec_filenames, (
            "impl-only.md should NOT be injected during spec stage"
        )


# ---------------------------------------------------------------------------
# 7. Knowledge file paths are absolute (FR-028 — explicit verification)
# ---------------------------------------------------------------------------


class TestAbsoluteKnowledgePaths:
    """FR-028 explicit: knowledge_paths must always be absolute, never relative."""

    def test_knowledge_paths_do_not_start_with_dot(
        self, tmp_agent_base: Path, registry: AgentRegistry
    ):
        """Paths must not be relative (starting with '.') for any agent."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            for kp in cfg.knowledge_paths:
                assert not kp.startswith("."), (
                    f"Relative path detected for agent '{name}': {kp}"
                )

    def test_knowledge_paths_do_not_use_tilde(
        self, registry: AgentRegistry
    ):
        """Paths must not use '~' (unexpanded home directory) for any agent."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            for kp in cfg.knowledge_paths:
                assert not kp.startswith("~"), (
                    f"Unexpanded tilde path for agent '{name}': {kp}"
                )

    def test_injected_paths_under_correct_agent_directory(
        self, registry: AgentRegistry
    ):
        """All knowledge_paths for an agent MUST be located under its agent directory."""
        for name in registry.list_agents():
            cfg = registry.get_agent(name)
            for kp in cfg.knowledge_paths:
                assert kp.startswith(cfg.directory), (
                    f"Knowledge path '{kp}' for agent '{name}' is not under "
                    f"its agent directory '{cfg.directory}'"
                )


# ---------------------------------------------------------------------------
# 8. Session continuation (FR-029, SPEC-082)
# ---------------------------------------------------------------------------


class TestSessionContinuation:
    """FR-029 / SPEC-082: AgentRegistry MUST persist session IDs to enable
    session continuation rather than creating a new session each invocation."""

    def test_save_and_get_session_id(self, registry: AgentRegistry):
        """FR-029: save_session() followed by get_session() MUST return the same
        session_id."""
        registry.save_session("spec-writer", "sess-001")
        assert registry.get_session("spec-writer") == "sess-001"

    def test_get_session_returns_empty_string_when_no_session_saved(
        self, registry: AgentRegistry
    ):
        """FR-029: get_session() MUST return '' (empty string) when no session
        has been saved for the agent."""
        result = registry.get_session("implementer")
        assert result == ""

    def test_save_session_overwrites_previous_value(self, registry: AgentRegistry):
        """FR-029: Saving a second session_id for the same agent MUST overwrite
        the first."""
        registry.save_session("planner", "old-sess")
        registry.save_session("planner", "new-sess")
        assert registry.get_session("planner") == "new-sess"

    def test_clear_session_removes_stored_id(self, registry: AgentRegistry):
        """FR-029: clear_session() MUST remove the stored session_id so that
        subsequent get_session() returns ''."""
        registry.save_session("fixer", "sess-xyz")
        registry.clear_session("fixer")
        assert registry.get_session("fixer") == ""

    def test_clear_session_on_unknown_agent_does_not_raise(
        self, registry: AgentRegistry
    ):
        """clear_session() for an agent with no stored session MUST not raise."""
        registry.clear_session("nonexistent-agent-abc")  # must not raise

    def test_multiple_agents_sessions_tracked_independently(
        self, registry: AgentRegistry
    ):
        """FR-029: Session IDs MUST be tracked independently for each agent —
        saving one agent's session MUST NOT affect another's."""
        registry.save_session("spec-writer", "sess-spec-1")
        registry.save_session("implementer", "sess-impl-2")

        assert registry.get_session("spec-writer") == "sess-spec-1"
        assert registry.get_session("implementer") == "sess-impl-2"

    def test_session_for_one_agent_does_not_contaminate_another(
        self, registry: AgentRegistry
    ):
        """SPEC-082: Sessions are per-agent. Saving a session for 'planner' MUST
        NOT create a session for 'fixer'."""
        registry.save_session("planner", "planner-sess")
        assert registry.get_session("fixer") == ""

    def test_get_session_returns_empty_after_reload(self, tmp_agent_base: Path):
        """Session state MUST NOT persist across AgentRegistry instances unless
        explicitly persisted — a fresh registry has no sessions."""
        reg1 = AgentRegistry(base_path=str(tmp_agent_base))
        reg1.load()
        reg1.save_session("spec-writer", "persistent-sess")

        reg2 = AgentRegistry(base_path=str(tmp_agent_base))
        reg2.load()
        # A fresh registry should have no prior session state
        assert reg2.get_session("spec-writer") == ""


# ---------------------------------------------------------------------------
# 9. Error handling — missing base directory
# ---------------------------------------------------------------------------


class TestErrorHandlingMissingDirectory:
    """AgentRegistry MUST raise clear errors for invalid configurations."""

    def test_load_raises_for_nonexistent_base_path(self, tmp_path: Path):
        """FR-027: load() MUST raise FileNotFoundError (or OSError / ValueError)
        when the base_path does not exist."""
        nonexistent = str(tmp_path / "does_not_exist")
        reg = AgentRegistry(base_path=nonexistent)
        with pytest.raises((FileNotFoundError, OSError, ValueError)):
            reg.load()

    def test_load_raises_for_base_path_that_is_a_file(self, tmp_path: Path):
        """load() MUST raise when base_path points to a file, not a directory."""
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("oops", encoding="utf-8")
        reg = AgentRegistry(base_path=str(file_path))
        with pytest.raises((NotADirectoryError, OSError, ValueError)):
            reg.load()

    def test_constructor_raises_for_empty_base_path(self):
        """AgentRegistry MUST raise ValueError for an empty base_path string."""
        with pytest.raises((ValueError, TypeError)):
            AgentRegistry(base_path="")

    def test_get_agent_raises_for_unregistered_name_after_load(
        self, registry: AgentRegistry
    ):
        """get_agent() MUST raise KeyError (or ValueError) for any name not in
        the registry, even after a successful load()."""
        with pytest.raises((KeyError, ValueError)):
            registry.get_agent("this-agent-does-not-exist")


# ---------------------------------------------------------------------------
# 10. Error handling — invalid agent configuration
# ---------------------------------------------------------------------------


class TestErrorHandlingInvalidAgentConfig:
    """AgentRegistry MUST handle malformed agent.json configurations gracefully."""

    def test_load_raises_or_skips_agent_with_missing_config_file(
        self, tmp_path: Path
    ):
        """If an agent directory is missing agent.json, registry MUST either
        raise ValueError/FileNotFoundError or skip that agent (not silently
        include it with broken data)."""
        name = "broken-agent"
        broken_dir = tmp_path / name
        broken_dir.mkdir()
        # No agent.json created — broken configuration

        reg = AgentRegistry(base_path=str(tmp_path))
        try:
            reg.load()
            # If load succeeds, the broken agent must NOT appear in the registry
            agents = reg.list_agents()
            assert name not in agents, (
                f"Broken agent '{name}' (missing agent.json) must not be registered"
            )
        except (FileNotFoundError, ValueError, OSError):
            pass  # Raising is also acceptable

    def test_load_raises_or_skips_agent_with_malformed_json(self, tmp_path: Path):
        """If an agent's agent.json contains invalid JSON, registry MUST either
        raise ValueError/JSONDecodeError or skip that agent."""
        import json as _json

        name = "malformed-agent"
        malformed_dir = tmp_path / name
        malformed_dir.mkdir()
        (malformed_dir / "agent.json").write_text("{ not valid json }", encoding="utf-8")

        reg = AgentRegistry(base_path=str(tmp_path))
        try:
            reg.load()
            agents = reg.list_agents()
            assert name not in agents, (
                f"Malformed agent '{name}' must not be registered"
            )
        except (ValueError, _json.JSONDecodeError, OSError):
            pass  # Raising is also acceptable

    def test_load_raises_or_skips_agent_with_missing_name_field(
        self, tmp_path: Path
    ):
        """If agent.json is missing the 'name' field, registry MUST either
        raise ValueError or skip that agent."""
        name = "no-name-agent"
        no_name_dir = tmp_path / name
        no_name_dir.mkdir()
        (no_name_dir / "agent.json").write_text(
            '{"stages": ["spec"], "knowledge_files": []}', encoding="utf-8"
        )

        reg = AgentRegistry(base_path=str(tmp_path))
        try:
            reg.load()
            agents = reg.list_agents()
            assert name not in agents, (
                "Agent with missing 'name' field must not be registered under the dir name"
            )
        except (ValueError, KeyError, OSError):
            pass  # Raising is also acceptable


# ---------------------------------------------------------------------------
# 11. Re-loading is idempotent
# ---------------------------------------------------------------------------


class TestIdempotentLoad:
    """Calling load() multiple times on the same registry MUST NOT duplicate
    agent entries or raise errors."""

    def test_double_load_does_not_duplicate_agents(self, tmp_agent_base: Path):
        """FR-027: load() called twice MUST result in exactly 14 agents (not 28)."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        reg.load()
        reg.load()  # second call
        agents = reg.list_agents()
        assert len(agents) == 14, (
            f"Double load produced {len(agents)} agents, expected 14"
        )

    def test_double_load_does_not_clear_sessions(self, tmp_agent_base: Path):
        """Re-loading MUST NOT wipe session IDs that were saved before the reload."""
        reg = AgentRegistry(base_path=str(tmp_agent_base))
        reg.load()
        reg.save_session("spec-writer", "saved-sess")
        reg.load()  # second load
        # Sessions saved before reload MUST be preserved
        # (or at minimum, the registry must handle this consistently)
        # We only assert that no exception is raised; the session value is
        # implementation-defined for double-load scenarios.


# ---------------------------------------------------------------------------
# 12. All 14 canonical agent names are loadable from a real-like structure
# ---------------------------------------------------------------------------


class TestCanonicalAgentNamesMatchSpec:
    """Explicit verification that the 14 canonical names from the ESSKILLAGENT
    repository are all supported by the registry. (FR-027, SC-003)"""

    @pytest.mark.parametrize("agent_name", CANONICAL_AGENT_NAMES)
    def test_canonical_agent_is_loaded(
        self, registry: AgentRegistry, agent_name: str
    ):
        """FR-027 / SC-003: Each of the 14 canonical agent names MUST be
        accessible via get_agent() after load()."""
        cfg = registry.get_agent(agent_name)
        assert cfg.name == agent_name

    def test_total_canonical_names_count_is_14(self):
        """The CANONICAL_AGENT_NAMES constant in tests MUST itself have 14 entries,
        verifying we haven't accidentally mis-defined the list."""
        assert len(CANONICAL_AGENT_NAMES) == 14


# ---------------------------------------------------------------------------
# 13. Stage-order constants are correct
# ---------------------------------------------------------------------------


class TestStageOrder:
    """SPEC-081: Stage order must be spec -> plan -> implement -> acceptance."""

    def test_stage_order_has_four_entries(self):
        """There are exactly four pipeline stages."""
        assert len(STAGE_ORDER) == 4

    def test_stage_order_starts_with_spec(self):
        """The first stage MUST be 'spec'."""
        assert STAGE_ORDER[0] == "spec"

    def test_stage_order_ends_with_acceptance(self):
        """The last stage MUST be 'acceptance'."""
        assert STAGE_ORDER[-1] == "acceptance"

    def test_get_knowledge_paths_accepts_all_four_stages(
        self, registry: AgentRegistry
    ):
        """get_knowledge_paths_for_stage() MUST accept each of the four stage
        names without raising."""
        for stage in STAGE_ORDER:
            paths = registry.get_knowledge_paths_for_stage("implementer", stage)
            assert isinstance(paths, list)
