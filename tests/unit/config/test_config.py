"""Unit tests for orchestrator/config.py — layered configuration loading.

FR-019: System MUST load configuration in layered order:
    defaults.yaml -> brownfield.yaml (v1 compatibility) -> .orchestrator.yaml
    (project override), with later sources overriding earlier ones.
FR-020: System MUST support environment variable overrides for any
    configuration key using the ORCH_ prefix.
FR-021: System MUST accept and correctly interpret v1-format brownfield.yaml.

Spec Reference:
    SPEC-040: defaults.yaml value overridden by .orchestrator.yaml value.
    SPEC-041: v1-format brownfield.yaml keys correctly interpreted.
    SPEC-042: ORCHESTRATOR_ env var overrides all file-based values.
    SPEC-043: Missing .orchestrator.yaml loads without error.

These are RED-phase tests. They MUST FAIL until orchestrator/config.py
implements the required classes and functions. The module does not exist yet,
so all tests will fail at import time — this is the intended RED state.

Test coverage areas:
    - load_config() returns a dict with merged configuration
    - Layer ordering: defaults < brownfield < .orchestrator.yaml < env vars
    - Deep merge of nested dicts (later keys win, but siblings are preserved)
    - v1 compatibility: brownfield.yaml legacy key mapping
    - Environment variable overrides with ORCH_ prefix
    - Type coercion: env var strings converted to int and bool as needed
    - Missing optional layers load without error
    - Invalid YAML raises descriptive ConfigError (not raw exception)
    - Required field validation raises ConfigError on missing fields
    - Empty config files are tolerated (treated as empty dict)
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test.
# orchestrator/config.py does not exist yet, so all tests will fail at
# collection time with ModuleNotFoundError — this is the intended RED state.
# ---------------------------------------------------------------------------
from orchestrator.config import ConfigError, ConfigLoader, load_config


# ===========================================================================
# Helpers
# ===========================================================================


def write_yaml(path: Path, content: str) -> None:
    """Write a YAML file, stripping leading indentation for readability."""
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ===========================================================================
# 1. load_config() — public API contract
# ===========================================================================


class TestLoadConfigPublicAPI:
    """load_config() is the primary entry point for configuration loading.
    It MUST accept a project_dir path and return a merged dict."""

    def test_load_config_returns_dict(self, tmp_path: Path):
        """SPEC-040: load_config MUST return a dict."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)

    def test_load_config_accepts_path_object(self, tmp_path: Path):
        """load_config MUST accept a pathlib.Path as project_dir."""
        result = load_config(project_dir=tmp_path)
        assert result is not None

    def test_load_config_accepts_string_path(self, tmp_path: Path):
        """load_config MUST accept a string path as project_dir."""
        result = load_config(project_dir=str(tmp_path))
        assert isinstance(result, dict)

    def test_load_config_with_no_config_files_returns_defaults(self, tmp_path: Path):
        """SPEC-043: With no config files present, load_config MUST return
        the built-in defaults without raising an error."""
        result = load_config(project_dir=tmp_path)
        # Should succeed with defaults — not raise
        assert isinstance(result, dict)

    def test_load_config_includes_ci_timeout_default(self, tmp_path: Path):
        """The result MUST include ci_timeout (a known required key)."""
        result = load_config(project_dir=tmp_path)
        assert "ci_timeout" in result

    def test_load_config_includes_max_retries_default(self, tmp_path: Path):
        """The result MUST include max_retries."""
        result = load_config(project_dir=tmp_path)
        assert "max_retries" in result

    def test_load_config_includes_local_test_default(self, tmp_path: Path):
        """The result MUST include local_test flag."""
        result = load_config(project_dir=tmp_path)
        assert "local_test" in result

    def test_load_config_includes_test_command_default(self, tmp_path: Path):
        """The result MUST include test_command."""
        result = load_config(project_dir=tmp_path)
        assert "test_command" in result


# ===========================================================================
# 2. ConfigError — structured error type
# ===========================================================================


class TestConfigError:
    """ConfigError MUST be raised for all configuration-related failures
    so callers can catch a single, well-typed exception."""

    def test_config_error_is_exception(self):
        """ConfigError MUST subclass Exception."""
        assert issubclass(ConfigError, Exception)

    def test_config_error_can_be_raised_with_message(self):
        """ConfigError MUST accept a descriptive message."""
        with pytest.raises(ConfigError, match="test error"):
            raise ConfigError("test error")

    def test_config_error_stores_message(self):
        """ConfigError.args[0] MUST contain the message string."""
        err = ConfigError("bad config")
        assert "bad config" in str(err)

    def test_invalid_yaml_raises_config_error(self, tmp_path: Path):
        """SPEC-EC01: A .orchestrator.yaml with invalid YAML MUST raise
        ConfigError, not yaml.YAMLError or another raw exception."""
        bad_yaml = tmp_path / ".orchestrator.yaml"
        bad_yaml.write_text("key: [unclosed bracket\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(project_dir=tmp_path)


# ===========================================================================
# 3. Layer 1: defaults.yaml loading
# ===========================================================================


class TestDefaultsYamlLayer:
    """defaults.yaml provides the base configuration values.
    It is loaded from the package directory (alongside config.py)."""

    def test_defaults_provide_ci_timeout_value(self, tmp_path: Path):
        """The bundled defaults.yaml MUST define ci_timeout with a numeric value."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result["ci_timeout"], (int, float))

    def test_defaults_provide_max_retries_value(self, tmp_path: Path):
        """The bundled defaults.yaml MUST define max_retries as a positive int."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result["max_retries"], int)
        assert result["max_retries"] > 0

    def test_defaults_provide_local_test_as_bool(self, tmp_path: Path):
        """The bundled defaults.yaml MUST define local_test as a bool."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result["local_test"], bool)

    def test_defaults_provide_test_command_as_string(self, tmp_path: Path):
        """The bundled defaults.yaml MUST define test_command as a non-empty string."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result["test_command"], str)
        assert len(result["test_command"]) > 0

    def test_defaults_provide_max_fix_retries(self, tmp_path: Path):
        """The bundled defaults.yaml MUST define max_fix_retries."""
        result = load_config(project_dir=tmp_path)
        assert "max_fix_retries" in result


# ===========================================================================
# 4. Layer 2: brownfield.yaml v1 compatibility
# ===========================================================================


class TestBrownfieldYamlLayer:
    """SPEC-041 / FR-021: brownfield.yaml (v1 format) MUST be loaded and
    its keys correctly mapped to v2 config keys."""

    def test_brownfield_ci_timeout_overrides_default(self, tmp_path: Path):
        """SPEC-041: brownfield.yaml ci_timeout MUST override the default."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 999
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 999

    def test_brownfield_max_retries_overrides_default(self, tmp_path: Path):
        """brownfield.yaml max_retries MUST override the default."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            max_retries: 7
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 7

    def test_brownfield_local_test_overrides_default(self, tmp_path: Path):
        """brownfield.yaml local_test MUST override the default."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            local_test: true
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_brownfield_test_command_overrides_default(self, tmp_path: Path):
        """brownfield.yaml test_command MUST override the default."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            test_command: "pytest -x"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -x"

    def test_brownfield_max_fix_retries_overrides_default(self, tmp_path: Path):
        """brownfield.yaml max_fix_retries MUST override the default."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            max_fix_retries: 5
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["max_fix_retries"] == 5

    def test_brownfield_models_nested_dict_is_loaded(self, tmp_path: Path):
        """brownfield.yaml nested models dict MUST be merged into config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            models:
              default: "claude-opus-4"
              spec: "claude-opus-4-6"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert "models" in result
        assert result["models"]["default"] == "claude-opus-4"

    def test_missing_brownfield_yaml_loads_without_error(self, tmp_path: Path):
        """SPEC-043: If brownfield.yaml is absent, load_config MUST succeed."""
        # No brownfield.yaml in tmp_path
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)

    def test_empty_brownfield_yaml_is_tolerated(self, tmp_path: Path):
        """An empty brownfield.yaml MUST be treated as an empty override (no error)."""
        (tmp_path / "brownfield.yaml").write_text("", encoding="utf-8")
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)

    def test_brownfield_v1_coverage_command_key_is_loaded(self, tmp_path: Path):
        """FR-021: v1 key coverage_command MUST be present in loaded config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            coverage_command: "npm run test:cov"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["coverage_command"] == "npm run test:cov"

    def test_brownfield_v1_coverage_threshold_is_loaded(self, tmp_path: Path):
        """FR-021: v1 key coverage_threshold MUST be present in loaded config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            coverage_threshold: 90
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["coverage_threshold"] == 90

    def test_brownfield_v1_stages_list_is_loaded(self, tmp_path: Path):
        """FR-021: v1 stages list MUST be loaded and available."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            stages:
              - id: spec
                name: "规格"
              - id: plan
                name: "计划"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert "stages" in result
        assert isinstance(result["stages"], list)
        assert result["stages"][0]["id"] == "spec"


# ===========================================================================
# 5. Layer 3: .orchestrator.yaml (project-level overrides)
# ===========================================================================


class TestOrchestratorYamlLayer:
    """SPEC-040: .orchestrator.yaml in the project directory MUST override
    both defaults.yaml and brownfield.yaml values."""

    def test_orchestrator_yaml_overrides_default_ci_timeout(self, tmp_path: Path):
        """SPEC-040: .orchestrator.yaml ci_timeout MUST win over default."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 600
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 600

    def test_orchestrator_yaml_overrides_brownfield_ci_timeout(self, tmp_path: Path):
        """SPEC-040: .orchestrator.yaml MUST override brownfield.yaml value."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 300
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 600
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 600

    def test_orchestrator_yaml_overrides_max_retries(self, tmp_path: Path):
        """max_retries in .orchestrator.yaml MUST override brownfield value."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            max_retries: 3
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: 10
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 10

    def test_orchestrator_yaml_overrides_local_test(self, tmp_path: Path):
        """local_test in .orchestrator.yaml MUST override brownfield value."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            local_test: false
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: true
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_orchestrator_yaml_overrides_test_command(self, tmp_path: Path):
        """test_command in .orchestrator.yaml MUST override brownfield value."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            test_command: "npm test"
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            test_command: "pytest -v"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -v"

    def test_missing_orchestrator_yaml_loads_without_error(self, tmp_path: Path):
        """SPEC-043: If .orchestrator.yaml is absent, load_config MUST succeed."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 300
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 300

    def test_empty_orchestrator_yaml_is_tolerated(self, tmp_path: Path):
        """An empty .orchestrator.yaml MUST not raise an error."""
        (tmp_path / ".orchestrator.yaml").write_text("", encoding="utf-8")
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)


# ===========================================================================
# 6. Layer ordering: all three layers together
# ===========================================================================


class TestLayerOrdering:
    """Verify the precedence chain: defaults < brownfield < .orchestrator.yaml."""

    def test_three_layer_override_chain_for_ci_timeout(self, tmp_path: Path):
        """Full stack: .orchestrator.yaml beats brownfield.yaml beats defaults."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 1000
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 2000
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 2000

    def test_brownfield_beats_defaults_when_no_project_override(self, tmp_path: Path):
        """When only brownfield.yaml sets a key, it MUST win over defaults."""
        default_result = load_config(project_dir=tmp_path)
        default_ci_timeout = default_result["ci_timeout"]

        write_yaml(
            tmp_path / "brownfield.yaml",
            f"""\
            ci_timeout: {default_ci_timeout + 500}
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == default_ci_timeout + 500

    def test_unset_key_in_project_layer_falls_back_to_brownfield(self, tmp_path: Path):
        """A key set in brownfield.yaml but not in .orchestrator.yaml MUST
        retain the brownfield value."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            max_fix_retries: 9
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 300
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["max_fix_retries"] == 9

    def test_unset_key_falls_back_to_defaults_when_absent_everywhere(
        self, tmp_path: Path
    ):
        """A key defined only in defaults.yaml MUST appear in the final result."""
        # No brownfield, no .orchestrator.yaml
        result = load_config(project_dir=tmp_path)
        # ci_timeout must come from defaults
        assert "ci_timeout" in result


# ===========================================================================
# 7. Deep merge of nested dicts
# ===========================================================================


class TestDeepMerge:
    """Later layers MUST deeply merge nested dicts rather than replace them
    wholesale. Sibling keys in a nested object that are only present in an
    earlier layer MUST be preserved."""

    def test_nested_models_default_key_preserved_when_project_adds_spec_key(
        self, tmp_path: Path
    ):
        """When brownfield sets models.default and .orchestrator.yaml sets
        models.spec, both MUST be present in the final config (deep merge)."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            models:
              default: "claude-sonnet-4-6"
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            models:
              spec: "claude-opus-4"
            """,
        )
        result = load_config(project_dir=tmp_path)
        # Both keys must be present (deep merge, not replacement)
        assert result["models"]["default"] == "claude-sonnet-4-6"
        assert result["models"]["spec"] == "claude-opus-4"

    def test_nested_key_overridden_by_later_layer(self, tmp_path: Path):
        """When both brownfield and .orchestrator.yaml set the same nested key,
        the later layer MUST win."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            models:
              default: "claude-sonnet-4-6"
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            models:
              default: "claude-opus-4"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["models"]["default"] == "claude-opus-4"

    def test_deeply_nested_sibling_preserved(self, tmp_path: Path):
        """Siblings at depth > 1 MUST be preserved during deep merge."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            retry:
              base_delay: 2
              multiplier: 2
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            retry:
              max_attempts: 5
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["retry"]["base_delay"] == 2
        assert result["retry"]["multiplier"] == 2
        assert result["retry"]["max_attempts"] == 5

    def test_non_dict_value_replaced_not_merged(self, tmp_path: Path):
        """A scalar value in a later layer MUST replace (not merge with)
        a scalar in an earlier layer."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 300
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 600
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 600

    def test_list_value_replaced_by_later_layer(self, tmp_path: Path):
        """Lists MUST be replaced wholesale by the later layer (not appended)."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            skip_stages:
              - spec
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            skip_stages:
              - plan
              - acceptance
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["skip_stages"] == ["plan", "acceptance"]


# ===========================================================================
# 8. Environment variable overrides
# ===========================================================================


class TestEnvVarOverrides:
    """SPEC-042 / FR-020: Environment variables with the ORCH_ prefix MUST
    override all file-based configuration values."""

    def test_orch_ci_timeout_overrides_all_files(self, tmp_path: Path):
        """SPEC-042: ORCH_CI_TIMEOUT env var MUST override .orchestrator.yaml."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 600
            """,
        )
        with patch.dict(os.environ, {"ORCH_CI_TIMEOUT": "900"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 900

    def test_orch_max_retries_overrides_file(self, tmp_path: Path):
        """ORCH_MAX_RETRIES env var MUST override file-based max_retries."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: 3
            """,
        )
        with patch.dict(os.environ, {"ORCH_MAX_RETRIES": "5"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 5

    def test_orch_local_test_true_overrides_file(self, tmp_path: Path):
        """ORCH_LOCAL_TEST=true MUST override local_test=false in files."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: false
            """,
        )
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "true"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_orch_local_test_false_overrides_file(self, tmp_path: Path):
        """ORCH_LOCAL_TEST=false MUST override local_test=true in files."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: true
            """,
        )
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "false"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False

    def test_orch_test_command_overrides_file(self, tmp_path: Path):
        """ORCH_TEST_COMMAND env var MUST override test_command in files."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            test_command: "npm test"
            """,
        )
        with patch.dict(os.environ, {"ORCH_TEST_COMMAND": "pytest -x -v"}):
            result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -x -v"

    def test_orch_max_fix_retries_overrides_file(self, tmp_path: Path):
        """ORCH_MAX_FIX_RETRIES env var MUST override max_fix_retries in files."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_fix_retries: 2
            """,
        )
        with patch.dict(os.environ, {"ORCH_MAX_FIX_RETRIES": "8"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_fix_retries"] == 8

    def test_env_var_not_present_does_not_affect_config(self, tmp_path: Path):
        """When ORCH_CI_TIMEOUT is not set, the file value MUST be used."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 777
            """,
        )
        # Ensure env var is absent
        env_without_key = {k: v for k, v in os.environ.items() if k != "ORCH_CI_TIMEOUT"}
        with patch.dict(os.environ, env_without_key, clear=True):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 777

    def test_env_var_priority_beats_all_three_file_layers(self, tmp_path: Path):
        """Env var MUST beat defaults + brownfield + .orchestrator.yaml."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 100
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 200
            """,
        )
        with patch.dict(os.environ, {"ORCH_CI_TIMEOUT": "300"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 300


# ===========================================================================
# 9. Type coercion for environment variables
# ===========================================================================


class TestEnvVarTypeCoercion:
    """Environment variable values arrive as strings. The loader MUST coerce
    them to the appropriate Python types (int, bool) based on context."""

    def test_int_env_var_coerced_to_int(self, tmp_path: Path):
        """ORCH_CI_TIMEOUT='42' MUST be coerced to int 42, not string '42'."""
        with patch.dict(os.environ, {"ORCH_CI_TIMEOUT": "42"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 42
        assert isinstance(result["ci_timeout"], int)

    def test_bool_true_env_var_coerced_to_bool(self, tmp_path: Path):
        """ORCH_LOCAL_TEST='true' MUST be coerced to bool True."""
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "true"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True
        assert isinstance(result["local_test"], bool)

    def test_bool_false_env_var_coerced_to_bool(self, tmp_path: Path):
        """ORCH_LOCAL_TEST='false' MUST be coerced to bool False."""
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "false"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False
        assert isinstance(result["local_test"], bool)

    def test_bool_1_env_var_coerced_to_true(self, tmp_path: Path):
        """ORCH_LOCAL_TEST='1' MUST be coerced to bool True."""
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "1"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_bool_0_env_var_coerced_to_false(self, tmp_path: Path):
        """ORCH_LOCAL_TEST='0' MUST be coerced to bool False."""
        with patch.dict(os.environ, {"ORCH_LOCAL_TEST": "0"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False

    def test_string_env_var_kept_as_string(self, tmp_path: Path):
        """ORCH_TEST_COMMAND='pytest -v' MUST remain a string."""
        with patch.dict(os.environ, {"ORCH_TEST_COMMAND": "pytest -v"}):
            result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -v"
        assert isinstance(result["test_command"], str)

    def test_int_max_retries_env_var_coerced_to_int(self, tmp_path: Path):
        """ORCH_MAX_RETRIES='3' MUST be coerced to int 3."""
        with patch.dict(os.environ, {"ORCH_MAX_RETRIES": "3"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 3
        assert isinstance(result["max_retries"], int)


# ===========================================================================
# 10. v1 compatibility: key mapping
# ===========================================================================


class TestV1Compatibility:
    """FR-021 / SPEC-041: v1 brownfield.yaml uses specific key names.
    The config loader MUST interpret these keys correctly so existing
    brownfield projects continue to work without modification."""

    def test_v1_full_brownfield_yaml_loads_without_error(self, tmp_path: Path):
        """Loading a real v1-format brownfield.yaml MUST succeed."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            name: "E+S 棕地 TDD 工作流"
            version: "1.0"
            models:
              default: "claude-sonnet-4-6"
              spec: "claude-opus-4-6"
              reviewer: "claude-opus-4-6"
            test_command: "npm test"
            coverage_command: "npm test -- --coverage"
            coverage_threshold: 80
            ci_timeout: 1800
            max_ci_retries: 3
            max_fix_retries: 2
            local_test: false
            force_constitution: true
            stage_timeout: 3600
            global_timeout: 14400
            max_retries: 3
            stages:
              - id: spec
                name: "规格"
                outputs: ["specs/spec.md"]
                review_target: "specs/spec.md"
                gate: auto
              - id: plan
                name: "计划"
                outputs: ["specs/plan.md", "specs/tasks.md"]
                review_target: "specs/plan.md"
                gate: auto
              - id: implement
                name: "实施"
                gate: auto
              - id: acceptance
                name: "验收"
                gate: user_approval
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)

    def test_v1_ci_timeout_is_available(self, tmp_path: Path):
        """v1 ci_timeout key MUST be present in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            ci_timeout: 1800
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 1800

    def test_v1_max_ci_retries_is_available(self, tmp_path: Path):
        """v1 max_ci_retries key MUST be present in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            max_ci_retries: 3
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["max_ci_retries"] == 3

    def test_v1_force_constitution_is_available(self, tmp_path: Path):
        """v1 force_constitution key MUST be present in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            force_constitution: true
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["force_constitution"] is True

    def test_v1_stage_timeout_is_available(self, tmp_path: Path):
        """v1 stage_timeout key MUST be present in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            stage_timeout: 3600
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["stage_timeout"] == 3600

    def test_v1_global_timeout_is_available(self, tmp_path: Path):
        """v1 global_timeout key MUST be present in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            global_timeout: 14400
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["global_timeout"] == 14400

    def test_v1_models_nested_dict_preserved(self, tmp_path: Path):
        """v1 models nested dict MUST be available in merged config."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            models:
              default: "claude-sonnet-4-6"
              spec: "claude-opus-4-6"
              reviewer: "claude-opus-4-6"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["models"]["default"] == "claude-sonnet-4-6"
        assert result["models"]["spec"] == "claude-opus-4-6"
        assert result["models"]["reviewer"] == "claude-opus-4-6"

    def test_v1_stages_list_with_full_shape_is_loaded(self, tmp_path: Path):
        """v1 stages list with outputs/review_target/gate MUST load intact."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            stages:
              - id: spec
                name: "规格"
                outputs: ["specs/spec.md"]
                review_target: "specs/spec.md"
                gate: auto
            """,
        )
        result = load_config(project_dir=tmp_path)
        stage = result["stages"][0]
        assert stage["id"] == "spec"
        assert stage["gate"] == "auto"
        assert "specs/spec.md" in stage["outputs"]


# ===========================================================================
# 11. ConfigLoader class (programmatic API)
# ===========================================================================


class TestConfigLoader:
    """ConfigLoader provides the programmatic API used internally by load_config().
    It MUST be instantiable and expose a load() method."""

    def test_config_loader_can_be_instantiated(self, tmp_path: Path):
        """ConfigLoader(project_dir=...) MUST not raise on construction."""
        loader = ConfigLoader(project_dir=tmp_path)
        assert loader is not None

    def test_config_loader_load_returns_dict(self, tmp_path: Path):
        """ConfigLoader.load() MUST return a dict."""
        loader = ConfigLoader(project_dir=tmp_path)
        result = loader.load()
        assert isinstance(result, dict)

    def test_config_loader_load_is_consistent_with_load_config(self, tmp_path: Path):
        """ConfigLoader.load() and load_config() MUST return the same result."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 42
            """,
        )
        loader_result = ConfigLoader(project_dir=tmp_path).load()
        function_result = load_config(project_dir=tmp_path)
        assert loader_result["ci_timeout"] == function_result["ci_timeout"]

    def test_config_loader_accepts_custom_defaults_path(self, tmp_path: Path):
        """ConfigLoader MUST accept an optional defaults_path to override the
        bundled defaults.yaml (useful for testing)."""
        custom_defaults = tmp_path / "custom_defaults.yaml"
        write_yaml(
            custom_defaults,
            """\
            ci_timeout: 1234
            max_retries: 1
            local_test: false
            test_command: "echo test"
            max_fix_retries: 1
            """,
        )
        loader = ConfigLoader(project_dir=tmp_path, defaults_path=custom_defaults)
        result = loader.load()
        assert result["ci_timeout"] == 1234

    def test_config_loader_get_method_returns_value(self, tmp_path: Path):
        """ConfigLoader.get(key, default) MUST return the configured value."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 555
            """,
        )
        loader = ConfigLoader(project_dir=tmp_path)
        loader.load()
        assert loader.get("ci_timeout") == 555

    def test_config_loader_get_method_returns_default_for_missing_key(
        self, tmp_path: Path
    ):
        """ConfigLoader.get(key, default) MUST return default for an absent key."""
        loader = ConfigLoader(project_dir=tmp_path)
        loader.load()
        result = loader.get("nonexistent_key_xyz", "fallback")
        assert result == "fallback"


# ===========================================================================
# 12. Edge cases and error handling
# ===========================================================================


class TestEdgeCases:
    """Cover edge cases: null values, special characters, Unicode, non-string keys."""

    def test_null_yaml_value_is_loaded_as_none(self, tmp_path: Path):
        """A YAML null value MUST be represented as Python None."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            custom_key: null
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result.get("custom_key") is None

    def test_unicode_string_values_are_preserved(self, tmp_path: Path):
        """Unicode values (e.g., Chinese characters) in YAML MUST be preserved."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            project_name: "E+S 棕地工作流"
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["project_name"] == "E+S 棕地工作流"

    def test_integer_zero_value_is_loaded_correctly(self, tmp_path: Path):
        """YAML integer 0 MUST be loaded as int 0, not falsy-omitted."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            retry_base_delay: 0
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["retry_base_delay"] == 0

    def test_float_value_loaded_correctly(self, tmp_path: Path):
        """YAML float values MUST be loaded as Python float."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            retry_multiplier: 1.5
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["retry_multiplier"] == pytest.approx(1.5)
        assert isinstance(result["retry_multiplier"], float)

    def test_boolean_true_loaded_as_python_true(self, tmp_path: Path):
        """YAML true MUST be loaded as Python True."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: true
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_boolean_false_loaded_as_python_false(self, tmp_path: Path):
        """YAML false MUST be loaded as Python False."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: false
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False

    def test_deeply_nested_custom_config_is_accessible(self, tmp_path: Path):
        """Deeply nested custom keys MUST be accessible after merge."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            agents:
              specifier:
                model: "claude-opus-4"
                timeout: 120
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["agents"]["specifier"]["model"] == "claude-opus-4"
        assert result["agents"]["specifier"]["timeout"] == 120

    def test_config_with_only_whitespace_yaml_treated_as_empty(self, tmp_path: Path):
        """A .orchestrator.yaml containing only whitespace MUST be treated as empty."""
        (tmp_path / ".orchestrator.yaml").write_text("   \n\n   \n", encoding="utf-8")
        result = load_config(project_dir=tmp_path)
        assert isinstance(result, dict)

    def test_nonexistent_project_dir_raises_config_error(self, tmp_path: Path):
        """If project_dir does not exist, load_config MUST raise ConfigError."""
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises((ConfigError, FileNotFoundError, OSError)):
            load_config(project_dir=nonexistent)
