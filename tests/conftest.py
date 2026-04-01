"""Shared pytest fixtures for all test suites.

Provides:
- tmp_db:       a temporary SQLite database path (Path object)
- mock_adapter: a mock AI adapter with a minimal async interface
- mock_store:   a mock artifact store with a minimal async interface
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# tmp_db — temporary SQLite database path
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a Path pointing to a temporary SQLite database file.

    The file itself is not created; callers that need an actual database
    should use aiosqlite.connect(tmp_db) which creates the file on connect.
    The path is guaranteed to be inside a unique temporary directory that
    pytest cleans up after the test session.
    """
    return tmp_path / "test_orchestrator.db"


# ---------------------------------------------------------------------------
# mock_adapter — mock AI adapter
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_adapter() -> MagicMock:
    """Return a mock AI adapter.

    The mock exposes the methods that the orchestrator engine expects from an
    adapter:
    - complete(prompt: str) -> str   (async)
    - embed(text: str) -> list[float]  (async)

    Tests that need specific return values should override these on the
    returned mock directly, e.g. mock_adapter.complete.return_value = "ok".
    """
    adapter = MagicMock(name="MockAdapter")
    adapter.complete = AsyncMock(return_value="mock completion")
    adapter.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return adapter


# ---------------------------------------------------------------------------
# mock_store — mock artifact store
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store() -> MagicMock:
    """Return a mock artifact store.

    The mock exposes the methods that the orchestrator engine expects from an
    artifact store:
    - save(key: str, value: object) -> None  (async)
    - load(key: str) -> object               (async)
    - exists(key: str) -> bool               (async)
    - delete(key: str) -> None               (async)

    Tests that need specific return values should override these on the
    returned mock directly.
    """
    store = MagicMock(name="MockStore")
    store.save = AsyncMock(return_value=None)
    store.load = AsyncMock(return_value=None)
    store.exists = AsyncMock(return_value=False)
    store.delete = AsyncMock(return_value=None)
    return store
