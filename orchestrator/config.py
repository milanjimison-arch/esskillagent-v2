"""Layered configuration loading for the orchestrator.

Load order (later sources override earlier ones):
  1. defaults.yaml  — bundled with the package
  2. brownfield.yaml — project root, optional (v1 compatibility)
  3. .orchestrator.yaml — project root, optional (project overrides)
  4. Environment variables with ORCH_ prefix
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

_DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"


class ConfigError(Exception):
    """Raised for all configuration-related failures."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict.

    - Nested dicts are merged recursively (siblings preserved).
    - Lists and scalars in *override* replace those in *base* wholesale.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> dict:
    """Load a YAML file and return a dict.

    - Missing file → returns {}
    - Empty / whitespace-only file → returns {}
    - Invalid YAML → raises ConfigError
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"Expected a YAML mapping in {path}, got {type(data).__name__}"
        )
    return data


def _coerce_env_value(raw: str, default_value: Any) -> Any:
    """Coerce *raw* string to the type implied by *default_value*."""
    if isinstance(default_value, bool):
        return raw.lower() in ("true", "1")
    if isinstance(default_value, int):
        return int(raw)
    return raw


def _apply_env_overrides(config: dict, defaults: dict) -> dict:
    """Return a new dict with ORCH_* env vars applied as top-level overrides."""
    result = dict(config)
    prefix = "ORCH_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        config_key = env_key[len(prefix):].lower()
        default_value = defaults.get(config_key)
        result[config_key] = _coerce_env_value(env_val, default_value)
    return result


# ---------------------------------------------------------------------------
# ConfigLoader
# ---------------------------------------------------------------------------


class ConfigLoader:
    """Loads and merges configuration from up to four sources."""

    def __init__(
        self,
        project_dir: str | Path,
        defaults_path: Path | None = None,
    ) -> None:
        self._project_dir = Path(project_dir)
        self._defaults_path = defaults_path if defaults_path is not None else _DEFAULTS_PATH
        self._config: dict = {}

    def load(self) -> dict:
        """Load all layers and return the merged configuration dict."""
        if not self._project_dir.exists():
            raise ConfigError(
                f"project_dir does not exist: {self._project_dir}"
            )

        # Layer 1: bundled defaults
        defaults = _load_yaml_file(self._defaults_path)

        # Layer 2: brownfield.yaml (v1 compat, optional)
        brownfield = _load_yaml_file(self._project_dir / "brownfield.yaml")

        # Layer 3: .orchestrator.yaml (project overrides, optional)
        project_override = _load_yaml_file(self._project_dir / ".orchestrator.yaml")

        # Merge layers
        merged = _deep_merge(defaults, brownfield)
        merged = _deep_merge(merged, project_override)

        # Layer 4: environment variable overrides
        merged = _apply_env_overrides(merged, defaults)

        self._config = merged
        return merged

    def get(self, key: str, default: Any = None) -> Any:
        """Return *key* from the loaded config, or *default* if absent."""
        return self._config.get(key, default)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(project_dir: str | Path) -> dict:
    """Load and return merged configuration for *project_dir*.

    Convenience wrapper around ConfigLoader.load().
    """
    return ConfigLoader(project_dir=project_dir).load()
