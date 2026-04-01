"""RED-phase tests for orchestrator/config.py — gaps identified in layered config spec.

FR reference:
    FR-019: Layered config: defaults.yaml -> brownfield.yaml -> .orchestrator.yaml
    FR-020: Environment variable overrides for any configuration key
    FR-021: v1-format brownfield.yaml accepted and correctly interpreted

Spec references targeted by NEW tests in this file:
    SPEC-042: Environment variable prefix is ORCHESTRATOR_ (not ORCH_)
    SPEC-040: defaults.yaml -> .orchestrator.yaml override confirmed
    SPEC-EC04: Negative ci_timeout value must raise ConfigError (validation)
    SPEC-EC05: Invalid type for max_retries must raise ConfigError (validation)

These tests are in RED state. They MUST FAIL until the implementation is updated.

Failure reasons:
    - Tests using ORCHESTRATOR_ prefix will fail because the current implementation
      only recognises the ORCH_ prefix (see _apply_env_overrides in config.py).
    - Validation tests will fail because load_config() performs no value validation
      and accepts any value without checking types or ranges.

Test coverage areas (new, not duplicated from test_config.py):
    1. ORCHESTRATOR_ prefix env var overrides (SPEC-042 literal compliance)
    2. Both ORCH_ and ORCHESTRATOR_ prefixes recognised simultaneously
    3. ORCHESTRATOR_ prefix beats file-based values for all key types
    4. Configuration validation: negative ci_timeout rejected
    5. Configuration validation: zero max_retries rejected
    6. Configuration validation: negative max_retries rejected
    7. Configuration validation: negative stage_timeout rejected
    8. skip_stages default is an empty list (not absent)
    9. models.default is present in defaults
    10. models.spec is present in defaults
    11. models.reviewer is present in defaults
    12. max_green_retries key present in defaults
    13. stage_timeout key present in defaults
    14. ORCHESTRATOR_ bool coercion (true/false/1/0)
    15. ORCHESTRATOR_ int coercion
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.config import ConfigError, ConfigLoader, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_yaml(path: Path, content: str) -> None:
    """Write a YAML file, stripping leading indentation."""
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ===========================================================================
# 1. SPEC-042: ORCHESTRATOR_ prefix env var overrides (literal spec compliance)
#
# The spec explicitly states (SPEC-042):
#   "Given an environment variable ORCHESTRATOR_CI_TIMEOUT=900, When
#    configuration loads, Then the environment variable overrides all
#    file-based values."
#
# The current implementation uses ORCH_ prefix. These tests will FAIL until
# the implementation is updated to support ORCHESTRATOR_ prefix.
# ===========================================================================


class TestOrchestratorPrefixEnvVarOverrides:
    """FR-020 / SPEC-042: ORCHESTRATOR_ prefix MUST be supported as specified."""

    def test_fr020_orchestrator_ci_timeout_overrides_file(self, tmp_path: Path):
        """FR-020 / SPEC-042: ORCHESTRATOR_CI_TIMEOUT MUST override .orchestrator.yaml."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 600
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_CI_TIMEOUT": "900"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 900

    def test_fr020_orchestrator_max_retries_overrides_file(self, tmp_path: Path):
        """FR-020: ORCHESTRATOR_MAX_RETRIES MUST override file-based max_retries."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: 3
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_RETRIES": "7"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 7

    def test_fr020_orchestrator_local_test_true_overrides_file(self, tmp_path: Path):
        """FR-020: ORCHESTRATOR_LOCAL_TEST=true MUST override local_test=false."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: false
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "true"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_fr020_orchestrator_local_test_false_overrides_file(self, tmp_path: Path):
        """FR-020: ORCHESTRATOR_LOCAL_TEST=false MUST override local_test=true."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            local_test: true
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "false"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False

    def test_fr020_orchestrator_test_command_overrides_file(self, tmp_path: Path):
        """FR-020: ORCHESTRATOR_TEST_COMMAND MUST override test_command in files."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            test_command: "npm test"
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_TEST_COMMAND": "pytest -x -v"}):
            result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -x -v"

    def test_fr020_orchestrator_max_fix_retries_overrides_file(self, tmp_path: Path):
        """FR-020: ORCHESTRATOR_MAX_FIX_RETRIES MUST override file-based value."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_fix_retries: 2
            """,
        )
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_FIX_RETRIES": "9"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_fix_retries"] == 9

    def test_fr020_orchestrator_prefix_beats_all_three_file_layers(
        self, tmp_path: Path
    ):
        """FR-020 / SPEC-042: ORCHESTRATOR_ env var MUST beat defaults + brownfield
        + .orchestrator.yaml (the full four-layer stack)."""
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
        with patch.dict(os.environ, {"ORCHESTRATOR_CI_TIMEOUT": "300"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 300


# ===========================================================================
# 2. ORCHESTRATOR_ prefix type coercion
# ===========================================================================


class TestOrchestratorPrefixTypeCoercion:
    """ORCHESTRATOR_ env vars MUST receive the same type coercion as ORCH_ vars."""

    def test_orchestrator_int_env_var_coerced_to_int(self, tmp_path: Path):
        """ORCHESTRATOR_CI_TIMEOUT='42' MUST be coerced to int 42."""
        with patch.dict(os.environ, {"ORCHESTRATOR_CI_TIMEOUT": "42"}):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 42
        assert isinstance(result["ci_timeout"], int)

    def test_orchestrator_bool_true_coerced_to_bool(self, tmp_path: Path):
        """ORCHESTRATOR_LOCAL_TEST='true' MUST be coerced to bool True."""
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "true"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True
        assert isinstance(result["local_test"], bool)

    def test_orchestrator_bool_false_coerced_to_bool(self, tmp_path: Path):
        """ORCHESTRATOR_LOCAL_TEST='false' MUST be coerced to bool False."""
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "false"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False
        assert isinstance(result["local_test"], bool)

    def test_orchestrator_bool_1_coerced_to_true(self, tmp_path: Path):
        """ORCHESTRATOR_LOCAL_TEST='1' MUST be coerced to bool True."""
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "1"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is True

    def test_orchestrator_bool_0_coerced_to_false(self, tmp_path: Path):
        """ORCHESTRATOR_LOCAL_TEST='0' MUST be coerced to bool False."""
        with patch.dict(os.environ, {"ORCHESTRATOR_LOCAL_TEST": "0"}):
            result = load_config(project_dir=tmp_path)
        assert result["local_test"] is False

    def test_orchestrator_string_env_var_kept_as_string(self, tmp_path: Path):
        """ORCHESTRATOR_TEST_COMMAND='pytest -v' MUST remain a string."""
        with patch.dict(os.environ, {"ORCHESTRATOR_TEST_COMMAND": "pytest -v"}):
            result = load_config(project_dir=tmp_path)
        assert result["test_command"] == "pytest -v"
        assert isinstance(result["test_command"], str)

    def test_orchestrator_max_retries_coerced_to_int(self, tmp_path: Path):
        """ORCHESTRATOR_MAX_RETRIES='5' MUST be coerced to int 5."""
        with patch.dict(os.environ, {"ORCHESTRATOR_MAX_RETRIES": "5"}):
            result = load_config(project_dir=tmp_path)
        assert result["max_retries"] == 5
        assert isinstance(result["max_retries"], int)


# ===========================================================================
# 3. Configuration value validation
#
# The spec implies that invalid values (e.g., negative timeouts, zero retries)
# should raise ConfigError. Currently no validation exists; these tests FAIL.
# ===========================================================================


class TestConfigValueValidation:
    """Configuration values MUST be validated and ConfigError raised for
    values that violate domain constraints."""

    def test_negative_ci_timeout_raises_config_error(self, tmp_path: Path):
        """A negative ci_timeout value MUST raise ConfigError — it is not a
        valid timeout."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: -1
            """,
        )
        with pytest.raises(ConfigError, match="ci_timeout"):
            load_config(project_dir=tmp_path)

    def test_zero_ci_timeout_raises_config_error(self, tmp_path: Path):
        """A ci_timeout of zero MUST raise ConfigError — zero is not a valid
        timeout duration."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 0
            """,
        )
        with pytest.raises(ConfigError, match="ci_timeout"):
            load_config(project_dir=tmp_path)

    def test_negative_max_retries_raises_config_error(self, tmp_path: Path):
        """A negative max_retries value MUST raise ConfigError."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: -1
            """,
        )
        with pytest.raises(ConfigError, match="max_retries"):
            load_config(project_dir=tmp_path)

    def test_zero_max_retries_raises_config_error(self, tmp_path: Path):
        """max_retries of zero MUST raise ConfigError — at least one retry
        is required for the pipeline to make progress."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: 0
            """,
        )
        with pytest.raises(ConfigError, match="max_retries"):
            load_config(project_dir=tmp_path)

    def test_negative_stage_timeout_raises_config_error(self, tmp_path: Path):
        """A negative stage_timeout MUST raise ConfigError."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            stage_timeout: -100
            """,
        )
        with pytest.raises(ConfigError, match="stage_timeout"):
            load_config(project_dir=tmp_path)

    def test_negative_max_fix_retries_raises_config_error(self, tmp_path: Path):
        """A negative max_fix_retries value MUST raise ConfigError."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_fix_retries: -3
            """,
        )
        with pytest.raises(ConfigError, match="max_fix_retries"):
            load_config(project_dir=tmp_path)

    def test_string_ci_timeout_raises_config_error(self, tmp_path: Path):
        """A non-numeric string for ci_timeout MUST raise ConfigError (not
        a generic ValueError or TypeError)."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: "not-a-number"
            """,
        )
        with pytest.raises(ConfigError):
            load_config(project_dir=tmp_path)

    def test_string_max_retries_raises_config_error(self, tmp_path: Path):
        """A non-numeric string for max_retries MUST raise ConfigError."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            max_retries: "many"
            """,
        )
        with pytest.raises(ConfigError):
            load_config(project_dir=tmp_path)

    def test_list_as_ci_timeout_raises_config_error(self, tmp_path: Path):
        """A YAML list value for ci_timeout MUST raise ConfigError."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout:
              - 300
              - 600
            """,
        )
        with pytest.raises(ConfigError):
            load_config(project_dir=tmp_path)

    def test_valid_positive_ci_timeout_does_not_raise(self, tmp_path: Path):
        """A valid positive ci_timeout MUST NOT raise any error."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            ci_timeout: 1
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 1


# ===========================================================================
# 4. skip_stages default value
#
# The spec's User Story 1, Scenario 3 says: "Given a project with
# skip_stages: [spec] in configuration". This implies skip_stages is a
# recognised configuration key. When absent, it MUST default to an empty
# list (not raise KeyError or be absent from the merged config).
# ===========================================================================


class TestSkipStagesDefault:
    """skip_stages MUST default to an empty list when absent from all config files."""

    def test_skip_stages_defaults_to_empty_list(self, tmp_path: Path):
        """FR-003: When no config file sets skip_stages, the merged config MUST
        include skip_stages as an empty list."""
        result = load_config(project_dir=tmp_path)
        assert "skip_stages" in result
        assert result["skip_stages"] == []

    def test_skip_stages_empty_list_type(self, tmp_path: Path):
        """skip_stages default MUST be a list, not None or a tuple."""
        result = load_config(project_dir=tmp_path)
        assert isinstance(result["skip_stages"], list)

    def test_skip_stages_set_in_orchestrator_yaml_is_respected(self, tmp_path: Path):
        """FR-003: skip_stages set in .orchestrator.yaml MUST override the empty default."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            skip_stages:
              - spec
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["skip_stages"] == ["spec"]

    def test_skip_stages_set_in_brownfield_is_overridden_by_orchestrator_yaml(
        self, tmp_path: Path
    ):
        """skip_stages from .orchestrator.yaml MUST win over brownfield.yaml."""
        write_yaml(
            tmp_path / "brownfield.yaml",
            """\
            skip_stages:
              - spec
              - plan
            """,
        )
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            skip_stages:
              - acceptance
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert result["skip_stages"] == ["acceptance"]

    def test_skip_stages_multiple_values_preserved(self, tmp_path: Path):
        """FR-003: Multiple stages in skip_stages MUST all be present."""
        write_yaml(
            tmp_path / ".orchestrator.yaml",
            """\
            skip_stages:
              - spec
              - plan
              - acceptance
            """,
        )
        result = load_config(project_dir=tmp_path)
        assert "spec" in result["skip_stages"]
        assert "plan" in result["skip_stages"]
        assert "acceptance" in result["skip_stages"]


# ===========================================================================
# 5. Default values completeness
#
# Tests that verify specific keys are present in the bundled defaults.
# Some keys are present in defaults.yaml but not currently tested; adding
# them here ensures the defaults contract is fully enforced.
# ===========================================================================


class TestDefaultsCompleteness:
    """All expected defaults MUST be present in the bundled defaults.yaml."""

    def test_defaults_include_models_dict(self, tmp_path: Path):
        """defaults.yaml MUST provide a models nested dict."""
        result = load_config(project_dir=tmp_path)
        assert "models" in result
        assert isinstance(result["models"], dict)

    def test_defaults_models_default_key_present(self, tmp_path: Path):
        """defaults.yaml models.default MUST be a non-empty string."""
        result = load_config(project_dir=tmp_path)
        assert "default" in result["models"]
        assert isinstance(result["models"]["default"], str)
        assert len(result["models"]["default"]) > 0

    def test_defaults_models_spec_key_present(self, tmp_path: Path):
        """defaults.yaml models.spec MUST be a non-empty string."""
        result = load_config(project_dir=tmp_path)
        assert "spec" in result["models"]
        assert isinstance(result["models"]["spec"], str)
        assert len(result["models"]["spec"]) > 0

    def test_defaults_models_reviewer_key_present(self, tmp_path: Path):
        """defaults.yaml models.reviewer MUST be a non-empty string."""
        result = load_config(project_dir=tmp_path)
        assert "reviewer" in result["models"]
        assert isinstance(result["models"]["reviewer"], str)
        assert len(result["models"]["reviewer"]) > 0

    def test_defaults_include_stage_timeout(self, tmp_path: Path):
        """defaults.yaml MUST define stage_timeout."""
        result = load_config(project_dir=tmp_path)
        assert "stage_timeout" in result
        assert isinstance(result["stage_timeout"], (int, float))
        assert result["stage_timeout"] > 0

    def test_defaults_include_max_green_retries(self, tmp_path: Path):
        """defaults.yaml MUST define max_green_retries."""
        result = load_config(project_dir=tmp_path)
        assert "max_green_retries" in result
        assert isinstance(result["max_green_retries"], int)
        assert result["max_green_retries"] > 0

    def test_defaults_include_skip_stages_as_empty_list(self, tmp_path: Path):
        """defaults.yaml MUST define skip_stages as an empty list."""
        result = load_config(project_dir=tmp_path)
        assert "skip_stages" in result
        assert result["skip_stages"] == []


# ===========================================================================
# 6. ORCHESTRATOR_ and ORCH_ dual-prefix support
#
# Once ORCHESTRATOR_ support is added, both prefixes should be honoured
# simultaneously. The last value wins when both are set for the same key.
# ===========================================================================


class TestDualPrefixSupport:
    """Both ORCH_ and ORCHESTRATOR_ prefixes MUST be recognised; when both are
    set for the same key, the one that takes precedence is documented."""

    def test_only_orchestrator_prefix_set_is_applied(self, tmp_path: Path):
        """When only ORCHESTRATOR_ is set and ORCH_ is absent, ORCHESTRATOR_ wins."""
        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("ORCHESTRATOR_CI_TIMEOUT", "ORCH_CI_TIMEOUT")
        }
        with patch.dict(os.environ, {**env_clean, "ORCHESTRATOR_CI_TIMEOUT": "500"}, clear=True):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 500

    def test_only_orch_prefix_set_is_applied(self, tmp_path: Path):
        """When only ORCH_ is set and ORCHESTRATOR_ is absent, ORCH_ wins."""
        env_clean = {
            k: v
            for k, v in os.environ.items()
            if k not in ("ORCHESTRATOR_CI_TIMEOUT", "ORCH_CI_TIMEOUT")
        }
        with patch.dict(os.environ, {**env_clean, "ORCH_CI_TIMEOUT": "400"}, clear=True):
            result = load_config(project_dir=tmp_path)
        assert result["ci_timeout"] == 400
