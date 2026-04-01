"""RED-phase tests for orchestrator/context.py — EngineContext frozen dataclass.

FR-003: EngineContext MUST be a frozen dataclass providing an immutable
        container for all shared runtime dependencies.

All tests in this module MUST FAIL until orchestrator/context.py provides a
proper @dataclass(frozen=True) implementation with the correct fields and
defaults.

Test coverage areas:
    1.  EngineContext is importable and instantiable with required fields.
    2.  FR-003: EngineContext is frozen — setting attributes raises an error.
    3.  EngineContext fields are accessible after construction.
    4.  run_id is a non-empty string.
    5.  db_path is a Path object.
    6.  stages defaults to the four standard stage names.
    7.  adapter and store fields are stored as provided.
    8.  config stores a mapping.
    9.  Two EngineContext instances with same data compare equal (dataclass eq).
    10. EngineContext repr contains the class name (dataclass repr).
    11. Instantiation without required fields raises TypeError.
    12. stages can be overridden at construction time.
    13. run_id must be a non-empty string — empty string is rejected.
    14. db_path must be a Path — providing a raw string is rejected or coerced.
    15. Fixture integration: tmp_db, mock_adapter, mock_store work together.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.context import EngineContext

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

_DEFAULT_STAGES = ("spec", "plan", "implement", "acceptance")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    run_id: str = "run-001",
    db_path: Path | None = None,
    adapter: object = None,
    store: object = None,
    stages: tuple | None = None,
    config: dict | None = None,
) -> EngineContext:
    """Construct an EngineContext with sensible defaults for testing."""
    kwargs: dict = {
        "run_id": run_id,
        "db_path": db_path if db_path is not None else Path("/tmp/test.db"),
        "adapter": adapter if adapter is not None else MagicMock(name="adapter"),
        "store": store if store is not None else MagicMock(name="store"),
    }
    if stages is not None:
        kwargs["stages"] = stages
    if config is not None:
        kwargs["config"] = config
    return EngineContext(**kwargs)


# ---------------------------------------------------------------------------
# 1. Import and instantiation
# ---------------------------------------------------------------------------


class TestEngineContextImport:
    """EngineContext must be importable and instantiable."""

    def test_FR003_engine_context_is_a_class(self):
        """FR-003: EngineContext must be a class."""
        import inspect
        assert inspect.isclass(EngineContext)

    def test_FR003_engine_context_is_a_dataclass(self):
        """FR-003: EngineContext MUST be decorated with @dataclass."""
        assert dataclasses.is_dataclass(EngineContext), (
            "EngineContext must be a dataclass; currently it is a plain class"
        )

    def test_FR003_engine_context_can_be_instantiated(self):
        """FR-003: EngineContext MUST instantiate without error given required fields."""
        ctx = _make_context()
        assert ctx is not None

    def test_FR003_engine_context_instance_type(self):
        """FR-003: Instantiated object MUST be an instance of EngineContext."""
        ctx = _make_context()
        assert isinstance(ctx, EngineContext)


# ---------------------------------------------------------------------------
# 2. FR-003: Frozen — immutability enforcement
# ---------------------------------------------------------------------------


class TestEngineContextFrozen:
    """FR-003: EngineContext MUST be immutable after creation."""

    def test_FR003_setting_run_id_raises(self):
        """Attempting to set run_id after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.run_id = "new-run-id"

    def test_FR003_setting_db_path_raises(self):
        """Attempting to set db_path after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.db_path = Path("/other/path.db")

    def test_FR003_setting_adapter_raises(self):
        """Attempting to set adapter after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.adapter = MagicMock()

    def test_FR003_setting_store_raises(self):
        """Attempting to set store after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.store = MagicMock()

    def test_FR003_setting_stages_raises(self):
        """Attempting to set stages after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.stages = ("spec",)

    def test_FR003_setting_config_raises(self):
        """Attempting to set config after construction MUST raise FrozenInstanceError."""
        ctx = _make_context(config={"key": "value"})
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.config = {"key": "changed"}

    def test_FR003_deleting_field_raises(self):
        """Attempting to delete a field after construction MUST raise FrozenInstanceError."""
        ctx = _make_context()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            del ctx.run_id


# ---------------------------------------------------------------------------
# 3. Field accessibility
# ---------------------------------------------------------------------------


class TestEngineContextFields:
    """All declared fields MUST be accessible on the instance."""

    def test_run_id_is_accessible(self):
        """run_id field MUST be readable after construction."""
        ctx = _make_context(run_id="run-abc")
        assert ctx.run_id == "run-abc"

    def test_db_path_is_accessible(self):
        """db_path field MUST be readable after construction."""
        p = Path("/some/db.sqlite")
        ctx = _make_context(db_path=p)
        assert ctx.db_path == p

    def test_adapter_is_accessible(self):
        """adapter field MUST be readable after construction."""
        adapter = MagicMock(name="my_adapter")
        ctx = _make_context(adapter=adapter)
        assert ctx.adapter is adapter

    def test_store_is_accessible(self):
        """store field MUST be readable after construction."""
        store = MagicMock(name="my_store")
        ctx = _make_context(store=store)
        assert ctx.store is store

    def test_stages_is_accessible(self):
        """stages field MUST be readable after construction."""
        ctx = _make_context()
        # Access must not raise; value must be iterable
        _ = ctx.stages
        assert hasattr(ctx.stages, "__iter__")

    def test_config_is_accessible_when_provided(self):
        """config field MUST be readable when explicitly set."""
        cfg = {"max_retries": 3}
        ctx = _make_context(config=cfg)
        assert ctx.config == cfg


# ---------------------------------------------------------------------------
# 4. run_id validation
# ---------------------------------------------------------------------------


class TestEngineContextRunId:
    """run_id MUST be a non-empty string."""

    def test_run_id_is_a_string(self):
        """FR-003: run_id stored value MUST be a str."""
        ctx = _make_context(run_id="run-xyz")
        assert isinstance(ctx.run_id, str), (
            f"run_id should be str, got {type(ctx.run_id)}"
        )

    def test_run_id_value_matches(self):
        """run_id MUST store exactly the value passed at construction."""
        ctx = _make_context(run_id="my-unique-run-123")
        assert ctx.run_id == "my-unique-run-123"

    def test_empty_run_id_is_rejected(self):
        """Passing an empty string as run_id MUST raise ValueError."""
        with pytest.raises(ValueError, match="run_id"):
            _make_context(run_id="")

    def test_whitespace_run_id_is_rejected(self):
        """Passing a whitespace-only run_id MUST raise ValueError."""
        with pytest.raises(ValueError, match="run_id"):
            _make_context(run_id="   ")


# ---------------------------------------------------------------------------
# 5. db_path validation
# ---------------------------------------------------------------------------


class TestEngineContextDbPath:
    """db_path MUST be a Path object."""

    def test_db_path_is_a_path_object(self):
        """FR-003: db_path stored value MUST be a pathlib.Path instance."""
        p = Path("/data/orchestrator.db")
        ctx = _make_context(db_path=p)
        assert isinstance(ctx.db_path, Path), (
            f"db_path should be Path, got {type(ctx.db_path)}"
        )

    def test_db_path_value_matches(self):
        """db_path MUST store exactly the Path value passed at construction."""
        p = Path("/tmp/orch.db")
        ctx = _make_context(db_path=p)
        assert ctx.db_path == p

    def test_raw_string_db_path_is_rejected(self):
        """Passing a plain string instead of Path for db_path MUST raise TypeError."""
        with pytest.raises(TypeError):
            EngineContext(
                run_id="run-001",
                db_path="/tmp/db.sqlite",   # string, not Path
                adapter=MagicMock(),
                store=MagicMock(),
            )


# ---------------------------------------------------------------------------
# 6. stages default value
# ---------------------------------------------------------------------------


class TestEngineContextStagesDefault:
    """stages MUST default to the four canonical pipeline stage names."""

    def test_stages_default_is_the_four_canonical_stages(self):
        """FR-003: When stages is not provided, it MUST default to the four canonical stages."""
        ctx = _make_context()
        assert ctx.stages == _DEFAULT_STAGES, (
            f"Expected stages={_DEFAULT_STAGES!r}, got {ctx.stages!r}"
        )

    def test_stages_default_is_a_tuple(self):
        """stages default MUST be a tuple (immutable sequence)."""
        ctx = _make_context()
        assert isinstance(ctx.stages, tuple), (
            f"stages should be tuple, got {type(ctx.stages)}"
        )

    def test_stages_default_length_is_four(self):
        """stages default MUST have exactly four elements."""
        ctx = _make_context()
        assert len(ctx.stages) == 4, (
            f"Expected 4 stages, got {len(ctx.stages)}: {ctx.stages!r}"
        )

    def test_stages_default_contains_spec(self):
        """Default stages MUST contain 'spec' as the first element."""
        ctx = _make_context()
        assert ctx.stages[0] == "spec"

    def test_stages_default_contains_plan(self):
        """Default stages MUST contain 'plan' as the second element."""
        ctx = _make_context()
        assert ctx.stages[1] == "plan"

    def test_stages_default_contains_implement(self):
        """Default stages MUST contain 'implement' as the third element."""
        ctx = _make_context()
        assert ctx.stages[2] == "implement"

    def test_stages_default_contains_acceptance(self):
        """Default stages MUST contain 'acceptance' as the fourth element."""
        ctx = _make_context()
        assert ctx.stages[3] == "acceptance"

    def test_stages_can_be_overridden(self):
        """stages MUST accept an explicit override at construction time."""
        custom = ("spec", "plan")
        ctx = _make_context(stages=custom)
        assert ctx.stages == custom


# ---------------------------------------------------------------------------
# 7. Dataclass equality and repr
# ---------------------------------------------------------------------------


class TestEngineContextDataclassBehavior:
    """Frozen dataclass MUST exhibit standard equality and repr behavior."""

    def test_two_contexts_with_same_data_are_equal(self):
        """Two EngineContext instances with identical field values MUST compare equal."""
        adapter = MagicMock(name="shared_adapter")
        store = MagicMock(name="shared_store")
        db = Path("/tmp/same.db")
        cfg = {"k": "v"}

        ctx1 = EngineContext(
            run_id="same-run",
            db_path=db,
            adapter=adapter,
            store=store,
            config=cfg,
        )
        ctx2 = EngineContext(
            run_id="same-run",
            db_path=db,
            adapter=adapter,
            store=store,
            config=cfg,
        )
        assert ctx1 == ctx2

    def test_repr_contains_class_name(self):
        """repr(EngineContext(...)) MUST include 'EngineContext'."""
        ctx = _make_context()
        r = repr(ctx)
        assert "EngineContext" in r, f"repr did not contain 'EngineContext': {r!r}"

    def test_repr_contains_run_id(self):
        """repr(EngineContext(...)) MUST include the run_id value."""
        ctx = _make_context(run_id="repr-test-run")
        r = repr(ctx)
        assert "repr-test-run" in r, f"repr did not contain run_id: {r!r}"


# ---------------------------------------------------------------------------
# 8. Missing required fields
# ---------------------------------------------------------------------------


class TestEngineContextRequiredFields:
    """Instantiation without required fields MUST raise TypeError."""

    def test_missing_run_id_raises_type_error(self):
        """Omitting run_id MUST raise TypeError."""
        with pytest.raises(TypeError):
            EngineContext(
                db_path=Path("/tmp/x.db"),
                adapter=MagicMock(),
                store=MagicMock(),
            )

    def test_missing_db_path_raises_type_error(self):
        """Omitting db_path MUST raise TypeError."""
        with pytest.raises(TypeError):
            EngineContext(
                run_id="run-001",
                adapter=MagicMock(),
                store=MagicMock(),
            )

    def test_missing_adapter_raises_type_error(self):
        """Omitting adapter MUST raise TypeError."""
        with pytest.raises(TypeError):
            EngineContext(
                run_id="run-001",
                db_path=Path("/tmp/x.db"),
                store=MagicMock(),
            )

    def test_missing_store_raises_type_error(self):
        """Omitting store MUST raise TypeError."""
        with pytest.raises(TypeError):
            EngineContext(
                run_id="run-001",
                db_path=Path("/tmp/x.db"),
                adapter=MagicMock(),
            )


# ---------------------------------------------------------------------------
# 9. Fixture integration
# ---------------------------------------------------------------------------


class TestConfTestFixtures:
    """Shared fixtures from conftest.py MUST integrate correctly with EngineContext."""

    def test_tmp_db_is_a_path(self, tmp_db):
        """tmp_db fixture MUST yield a Path object."""
        assert isinstance(tmp_db, Path), (
            f"tmp_db should be Path, got {type(tmp_db)}"
        )

    def test_tmp_db_filename(self, tmp_db):
        """tmp_db fixture path MUST end with the expected filename."""
        assert tmp_db.name == "test_orchestrator.db"

    def test_mock_adapter_has_complete(self, mock_adapter):
        """mock_adapter fixture MUST expose a 'complete' callable."""
        assert callable(mock_adapter.complete)

    def test_mock_adapter_has_embed(self, mock_adapter):
        """mock_adapter fixture MUST expose an 'embed' callable."""
        assert callable(mock_adapter.embed)

    def test_mock_store_has_save(self, mock_store):
        """mock_store fixture MUST expose a 'save' callable."""
        assert callable(mock_store.save)

    def test_mock_store_has_load(self, mock_store):
        """mock_store fixture MUST expose a 'load' callable."""
        assert callable(mock_store.load)

    def test_mock_store_has_exists(self, mock_store):
        """mock_store fixture MUST expose an 'exists' callable."""
        assert callable(mock_store.exists)

    def test_mock_store_has_delete(self, mock_store):
        """mock_store fixture MUST expose a 'delete' callable."""
        assert callable(mock_store.delete)

    def test_engine_context_with_fixtures(self, tmp_db, mock_adapter, mock_store):
        """EngineContext MUST accept tmp_db, mock_adapter, and mock_store as fields."""
        ctx = EngineContext(
            run_id="fixture-run",
            db_path=tmp_db,
            adapter=mock_adapter,
            store=mock_store,
        )
        assert ctx.run_id == "fixture-run"
        assert ctx.db_path == tmp_db
        assert ctx.adapter is mock_adapter
        assert ctx.store is mock_store

    def test_engine_context_frozen_with_fixtures(self, tmp_db, mock_adapter, mock_store):
        """EngineContext built from fixtures MUST still be frozen."""
        ctx = EngineContext(
            run_id="fixture-frozen-run",
            db_path=tmp_db,
            adapter=mock_adapter,
            store=mock_store,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.run_id = "mutated"
