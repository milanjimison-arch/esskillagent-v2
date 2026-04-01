"""Unit tests for orchestrator/ui/wave.py — optional Wave panel and desktop notifications.

All tests in this module are RED-phase tests.  They MUST FAIL until
orchestrator/ui/wave.py provides a complete implementation.

Requirements covered:
  FR-WAVE-01: WavePanel class exists with update_status / update_stage / append_log
              / clear_log methods.
  FR-WAVE-02: NullWavePanel is a no-op implementation used when h2o wave is unavailable.
  FR-WAVE-03: DesktopNotifier class exists with notify / notify_stage_complete /
              notify_error methods.
  FR-WAVE-04: NullDesktopNotifier is a no-op implementation when plyer is unavailable.
  FR-WAVE-05: create_wave_panel() factory returns NullWavePanel when wave is absent.
  FR-WAVE-06: create_wave_panel() factory returns WavePanel when wave is available.
  FR-WAVE-07: create_desktop_notifier() factory returns NullDesktopNotifier when
              plyer is absent.
  FR-WAVE-08: create_desktop_notifier() factory returns DesktopNotifier when
              plyer is available.
  FR-WAVE-09: Zero core imports from ui/ — orchestrator core modules do NOT import
              from orchestrator.ui.
  FR-WAVE-10: Both null implementations satisfy the same interface as the real ones.
  FR-WAVE-11: WavePanel.update_status accepts a string status and does not raise.
  FR-WAVE-12: WavePanel.update_stage accepts stage name and progress value (0–100).
  FR-WAVE-13: WavePanel.append_log accepts a string message.
  FR-WAVE-14: WavePanel.clear_log clears all logged messages.
  FR-WAVE-15: DesktopNotifier.notify accepts title and message strings.
  FR-WAVE-16: DesktopNotifier.notify_stage_complete accepts stage_name string.
  FR-WAVE-17: DesktopNotifier.notify_error accepts error_message string.

Test areas:
  1.  WavePanel is importable.
  2.  NullWavePanel is importable.
  3.  DesktopNotifier is importable.
  4.  NullDesktopNotifier is importable.
  5.  create_wave_panel is importable.
  6.  create_desktop_notifier is importable.
  7.  WavePanel has update_status method.
  8.  WavePanel has update_stage method.
  9.  WavePanel has append_log method.
  10. WavePanel has clear_log method.
  11. NullWavePanel has the same four methods as WavePanel.
  12. NullWavePanel.update_status returns None (no-op).
  13. NullWavePanel.update_stage returns None (no-op).
  14. NullWavePanel.append_log returns None (no-op).
  15. NullWavePanel.clear_log returns None (no-op).
  16. DesktopNotifier has notify method.
  17. DesktopNotifier has notify_stage_complete method.
  18. DesktopNotifier has notify_error method.
  19. NullDesktopNotifier has the same three methods as DesktopNotifier.
  20. NullDesktopNotifier.notify returns None (no-op).
  21. NullDesktopNotifier.notify_stage_complete returns None (no-op).
  22. NullDesktopNotifier.notify_error returns None (no-op).
  23. create_wave_panel returns NullWavePanel when wave import is mocked unavailable.
  24. create_wave_panel returns WavePanel when wave import succeeds.
  25. create_desktop_notifier returns NullDesktopNotifier when plyer unavailable.
  26. create_desktop_notifier returns DesktopNotifier when plyer available.
  27. WavePanel and NullWavePanel are different classes.
  28. DesktopNotifier and NullDesktopNotifier are different classes.
  29. NullWavePanel is a subtype of the same protocol/ABC as WavePanel (duck-typed).
  30. NullDesktopNotifier is a subtype of the same protocol/ABC as DesktopNotifier.
  31. FR-WAVE-09: engine.py does not import from orchestrator.ui.
  32. FR-WAVE-09: config.py does not import from orchestrator.ui.
  33. FR-WAVE-09: stages/base.py does not import from orchestrator.ui.
  34. FR-WAVE-09: agents/adapter.py does not import from orchestrator.ui.
  35. WavePanel.update_status stores/displays the provided status string.
  36. WavePanel.update_stage accepts progress=0 (boundary).
  37. WavePanel.update_stage accepts progress=100 (boundary).
  38. WavePanel.update_stage raises ValueError for progress > 100.
  39. WavePanel.update_stage raises ValueError for progress < 0.
  40. WavePanel.append_log accumulates multiple messages.
  41. WavePanel.clear_log empties the log after appending.
  42. DesktopNotifier.notify sends notification without raising (mocked plyer).
  43. DesktopNotifier.notify_stage_complete uses stage_name in notification.
  44. DesktopNotifier.notify_error uses error_message in notification.
  45. create_wave_panel with no args uses dependency detection (no required params).
  46. create_desktop_notifier with no args uses dependency detection.
  47. NullWavePanel instantiates without arguments.
  48. NullDesktopNotifier instantiates without arguments.
  49. WavePanel.get_log returns a list of appended log messages.
  50. WavePanel.get_status returns the last set status string.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.ui.wave import (
    DesktopNotifier,
    NullDesktopNotifier,
    NullWavePanel,
    WavePanel,
    create_desktop_notifier,
    create_wave_panel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def null_wave() -> NullWavePanel:
    return NullWavePanel()


@pytest.fixture
def null_notifier() -> NullDesktopNotifier:
    return NullDesktopNotifier()


@pytest.fixture
def wave_panel() -> WavePanel:
    """WavePanel instance backed by a mocked h2o wave dependency."""
    with patch.dict(sys.modules, {"h2o_wave": MagicMock()}):
        panel = WavePanel()
    return panel


@pytest.fixture
def desktop_notifier() -> DesktopNotifier:
    """DesktopNotifier instance backed by a mocked plyer dependency."""
    with patch.dict(sys.modules, {"plyer": MagicMock(), "plyer.notification": MagicMock()}):
        notifier = DesktopNotifier()
    return notifier


# ---------------------------------------------------------------------------
# 1. Importability
# ---------------------------------------------------------------------------


class TestImportability:
    """All public names MUST be importable from orchestrator.ui.wave."""

    def test_wave_panel_is_importable(self):
        """FR-WAVE-01: WavePanel class must be importable."""
        assert WavePanel is not None

    def test_null_wave_panel_is_importable(self):
        """FR-WAVE-02: NullWavePanel class must be importable."""
        assert NullWavePanel is not None

    def test_desktop_notifier_is_importable(self):
        """FR-WAVE-03: DesktopNotifier class must be importable."""
        assert DesktopNotifier is not None

    def test_null_desktop_notifier_is_importable(self):
        """FR-WAVE-04: NullDesktopNotifier class must be importable."""
        assert NullDesktopNotifier is not None

    def test_create_wave_panel_is_importable(self):
        """FR-WAVE-05/06: create_wave_panel factory must be importable."""
        assert create_wave_panel is not None

    def test_create_desktop_notifier_is_importable(self):
        """FR-WAVE-07/08: create_desktop_notifier factory must be importable."""
        assert create_desktop_notifier is not None


# ---------------------------------------------------------------------------
# 2. WavePanel interface
# ---------------------------------------------------------------------------


class TestWavePanelInterface:
    """FR-WAVE-01/11/12/13/14: WavePanel must expose the required methods."""

    def test_wave_panel_has_update_status(self):
        """WavePanel MUST have an update_status method."""
        assert callable(getattr(WavePanel, "update_status", None)), (
            "WavePanel must have a callable update_status method"
        )

    def test_wave_panel_has_update_stage(self):
        """WavePanel MUST have an update_stage method."""
        assert callable(getattr(WavePanel, "update_stage", None)), (
            "WavePanel must have a callable update_stage method"
        )

    def test_wave_panel_has_append_log(self):
        """WavePanel MUST have an append_log method."""
        assert callable(getattr(WavePanel, "append_log", None)), (
            "WavePanel must have a callable append_log method"
        )

    def test_wave_panel_has_clear_log(self):
        """WavePanel MUST have a clear_log method."""
        assert callable(getattr(WavePanel, "clear_log", None)), (
            "WavePanel must have a callable clear_log method"
        )

    def test_wave_panel_has_get_log(self):
        """WavePanel MUST have a get_log method that returns logged messages."""
        assert callable(getattr(WavePanel, "get_log", None)), (
            "WavePanel must have a callable get_log method"
        )

    def test_wave_panel_has_get_status(self):
        """WavePanel MUST have a get_status method that returns the last status."""
        assert callable(getattr(WavePanel, "get_status", None)), (
            "WavePanel must have a callable get_status method"
        )


# ---------------------------------------------------------------------------
# 3. WavePanel behavior
# ---------------------------------------------------------------------------


class TestWavePanelBehavior:
    """FR-WAVE-11/12/13/14: WavePanel methods must behave correctly."""

    def test_update_status_stores_status(self, wave_panel: WavePanel):
        """FR-WAVE-11: update_status('running') must store 'running' as current status."""
        wave_panel.update_status("running")
        assert wave_panel.get_status() == "running"

    def test_update_status_overwrites_previous_status(self, wave_panel: WavePanel):
        """update_status called twice must return the second value."""
        wave_panel.update_status("running")
        wave_panel.update_status("complete")
        assert wave_panel.get_status() == "complete"

    def test_update_stage_accepts_progress_zero(self, wave_panel: WavePanel):
        """FR-WAVE-12: update_stage with progress=0 must not raise."""
        wave_panel.update_stage("spec", 0)  # must not raise

    def test_update_stage_accepts_progress_one_hundred(self, wave_panel: WavePanel):
        """FR-WAVE-12: update_stage with progress=100 must not raise."""
        wave_panel.update_stage("acceptance", 100)  # must not raise

    def test_update_stage_raises_for_progress_above_100(self, wave_panel: WavePanel):
        """FR-WAVE-12: update_stage with progress=101 MUST raise ValueError."""
        with pytest.raises(ValueError):
            wave_panel.update_stage("spec", 101)

    def test_update_stage_raises_for_negative_progress(self, wave_panel: WavePanel):
        """FR-WAVE-12: update_stage with progress=-1 MUST raise ValueError."""
        with pytest.raises(ValueError):
            wave_panel.update_stage("spec", -1)

    def test_append_log_accumulates_messages(self, wave_panel: WavePanel):
        """FR-WAVE-13: Multiple append_log calls must all be retained in order."""
        wave_panel.append_log("message one")
        wave_panel.append_log("message two")
        log = wave_panel.get_log()
        assert "message one" in log
        assert "message two" in log
        assert log.index("message one") < log.index("message two")

    def test_get_log_returns_list(self, wave_panel: WavePanel):
        """get_log must return a list."""
        result = wave_panel.get_log()
        assert isinstance(result, list)

    def test_clear_log_empties_messages(self, wave_panel: WavePanel):
        """FR-WAVE-14: clear_log must result in get_log() returning an empty list."""
        wave_panel.append_log("will be cleared")
        wave_panel.clear_log()
        assert wave_panel.get_log() == []

    def test_clear_log_on_empty_log_does_not_raise(self, wave_panel: WavePanel):
        """clear_log on an already-empty log MUST not raise."""
        wave_panel.clear_log()  # must not raise

    def test_get_status_returns_empty_string_initially(self, wave_panel: WavePanel):
        """get_status before any update_status call MUST return '' or None — not raise."""
        status = wave_panel.get_status()
        assert status == "" or status is None


# ---------------------------------------------------------------------------
# 4. NullWavePanel interface and behavior
# ---------------------------------------------------------------------------


class TestNullWavePanelInterface:
    """FR-WAVE-02/10: NullWavePanel must expose the same interface as WavePanel."""

    def test_null_wave_panel_has_update_status(self):
        """NullWavePanel MUST have an update_status method."""
        assert callable(getattr(NullWavePanel, "update_status", None))

    def test_null_wave_panel_has_update_stage(self):
        """NullWavePanel MUST have an update_stage method."""
        assert callable(getattr(NullWavePanel, "update_stage", None))

    def test_null_wave_panel_has_append_log(self):
        """NullWavePanel MUST have an append_log method."""
        assert callable(getattr(NullWavePanel, "append_log", None))

    def test_null_wave_panel_has_clear_log(self):
        """NullWavePanel MUST have a clear_log method."""
        assert callable(getattr(NullWavePanel, "clear_log", None))

    def test_null_wave_panel_has_get_log(self):
        """NullWavePanel MUST have a get_log method."""
        assert callable(getattr(NullWavePanel, "get_log", None))

    def test_null_wave_panel_has_get_status(self):
        """NullWavePanel MUST have a get_status method."""
        assert callable(getattr(NullWavePanel, "get_status", None))


class TestNullWavePanelBehavior:
    """NullWavePanel is a no-op implementation — all writes are silently ignored."""

    def test_update_status_returns_none(self, null_wave: NullWavePanel):
        """NullWavePanel.update_status must return None without raising."""
        result = null_wave.update_status("running")
        assert result is None

    def test_update_stage_returns_none(self, null_wave: NullWavePanel):
        """NullWavePanel.update_stage must return None without raising."""
        result = null_wave.update_stage("spec", 50)
        assert result is None

    def test_append_log_returns_none(self, null_wave: NullWavePanel):
        """NullWavePanel.append_log must return None without raising."""
        result = null_wave.append_log("any message")
        assert result is None

    def test_clear_log_returns_none(self, null_wave: NullWavePanel):
        """NullWavePanel.clear_log must return None without raising."""
        result = null_wave.clear_log()
        assert result is None

    def test_get_log_returns_empty_list(self, null_wave: NullWavePanel):
        """NullWavePanel.get_log must return an empty list (no-op storage)."""
        null_wave.append_log("ignored message")
        result = null_wave.get_log()
        assert result == []

    def test_get_status_returns_empty_string(self, null_wave: NullWavePanel):
        """NullWavePanel.get_status must return '' (no-op storage)."""
        null_wave.update_status("irrelevant")
        result = null_wave.get_status()
        assert result == ""

    def test_null_wave_panel_instantiates_without_arguments(self):
        """NullWavePanel() MUST be constructible with no arguments."""
        panel = NullWavePanel()
        assert panel is not None

    def test_null_wave_panel_is_different_class_from_wave_panel(self):
        """NullWavePanel and WavePanel MUST be distinct classes."""
        assert NullWavePanel is not WavePanel


# ---------------------------------------------------------------------------
# 5. DesktopNotifier interface
# ---------------------------------------------------------------------------


class TestDesktopNotifierInterface:
    """FR-WAVE-03/15/16/17: DesktopNotifier must expose the required methods."""

    def test_desktop_notifier_has_notify(self):
        """DesktopNotifier MUST have a notify method."""
        assert callable(getattr(DesktopNotifier, "notify", None))

    def test_desktop_notifier_has_notify_stage_complete(self):
        """DesktopNotifier MUST have a notify_stage_complete method."""
        assert callable(getattr(DesktopNotifier, "notify_stage_complete", None))

    def test_desktop_notifier_has_notify_error(self):
        """DesktopNotifier MUST have a notify_error method."""
        assert callable(getattr(DesktopNotifier, "notify_error", None))


# ---------------------------------------------------------------------------
# 6. DesktopNotifier behavior
# ---------------------------------------------------------------------------


class TestDesktopNotifierBehavior:
    """FR-WAVE-15/16/17: DesktopNotifier methods must invoke plyer correctly."""

    def test_notify_calls_plyer_notification(self, desktop_notifier: DesktopNotifier):
        """FR-WAVE-15: notify('Title', 'Body') must invoke plyer's notify without raising."""
        mock_plyer = MagicMock()
        with patch.dict(sys.modules, {"plyer": mock_plyer, "plyer.notification": mock_plyer.notification}):
            desktop_notifier.notify("Test Title", "Test message body")
        # Must not raise — actual invocation verified via spy on a fresh instance below

    def test_notify_sends_title_and_message(self):
        """FR-WAVE-15: The plyer notification MUST include the provided title and message."""
        mock_notification = MagicMock()
        mock_plyer = MagicMock()
        mock_plyer.notification = mock_notification
        with patch.dict(sys.modules, {"plyer": mock_plyer, "plyer.notification": mock_notification}):
            notifier = DesktopNotifier()
            notifier.notify("Pipeline Done", "All stages passed")
        # The underlying plyer notify must have been called with title and message
        assert mock_notification.notify.called or mock_plyer.notification.notify.called, (
            "Expected plyer.notification.notify to be called"
        )
        call_kwargs = (
            mock_notification.notify.call_args
            or mock_plyer.notification.notify.call_args
        )
        call_str = str(call_kwargs)
        assert "Pipeline Done" in call_str, f"Title not found in plyer call: {call_str}"
        assert "All stages passed" in call_str, f"Message not found in plyer call: {call_str}"

    def test_notify_stage_complete_uses_stage_name(self):
        """FR-WAVE-16: notify_stage_complete must include stage_name in the notification."""
        mock_notification = MagicMock()
        mock_plyer = MagicMock()
        mock_plyer.notification = mock_notification
        with patch.dict(sys.modules, {"plyer": mock_plyer, "plyer.notification": mock_notification}):
            notifier = DesktopNotifier()
            notifier.notify_stage_complete("implement")
        call_str = str(
            mock_notification.notify.call_args
            or mock_plyer.notification.notify.call_args
        )
        assert "implement" in call_str, (
            f"Stage name 'implement' not found in plyer call: {call_str}"
        )

    def test_notify_error_uses_error_message(self):
        """FR-WAVE-17: notify_error must include error_message in the notification."""
        mock_notification = MagicMock()
        mock_plyer = MagicMock()
        mock_plyer.notification = mock_notification
        with patch.dict(sys.modules, {"plyer": mock_plyer, "plyer.notification": mock_notification}):
            notifier = DesktopNotifier()
            notifier.notify_error("Database connection failed")
        call_str = str(
            mock_notification.notify.call_args
            or mock_plyer.notification.notify.call_args
        )
        assert "Database connection failed" in call_str, (
            f"Error message not found in plyer call: {call_str}"
        )


# ---------------------------------------------------------------------------
# 7. NullDesktopNotifier interface and behavior
# ---------------------------------------------------------------------------


class TestNullDesktopNotifierInterface:
    """FR-WAVE-04/10: NullDesktopNotifier must expose the same interface."""

    def test_null_desktop_notifier_has_notify(self):
        """NullDesktopNotifier MUST have a notify method."""
        assert callable(getattr(NullDesktopNotifier, "notify", None))

    def test_null_desktop_notifier_has_notify_stage_complete(self):
        """NullDesktopNotifier MUST have a notify_stage_complete method."""
        assert callable(getattr(NullDesktopNotifier, "notify_stage_complete", None))

    def test_null_desktop_notifier_has_notify_error(self):
        """NullDesktopNotifier MUST have a notify_error method."""
        assert callable(getattr(NullDesktopNotifier, "notify_error", None))


class TestNullDesktopNotifierBehavior:
    """NullDesktopNotifier is a no-op — all notifications are silently discarded."""

    def test_notify_returns_none(self, null_notifier: NullDesktopNotifier):
        """NullDesktopNotifier.notify must return None without raising."""
        result = null_notifier.notify("Title", "Body")
        assert result is None

    def test_notify_stage_complete_returns_none(self, null_notifier: NullDesktopNotifier):
        """NullDesktopNotifier.notify_stage_complete must return None."""
        result = null_notifier.notify_stage_complete("spec")
        assert result is None

    def test_notify_error_returns_none(self, null_notifier: NullDesktopNotifier):
        """NullDesktopNotifier.notify_error must return None."""
        result = null_notifier.notify_error("something went wrong")
        assert result is None

    def test_null_desktop_notifier_instantiates_without_arguments(self):
        """NullDesktopNotifier() MUST be constructible with no arguments."""
        notifier = NullDesktopNotifier()
        assert notifier is not None

    def test_null_desktop_notifier_is_different_class_from_desktop_notifier(self):
        """NullDesktopNotifier and DesktopNotifier MUST be distinct classes."""
        assert NullDesktopNotifier is not DesktopNotifier


# ---------------------------------------------------------------------------
# 8. create_wave_panel factory
# ---------------------------------------------------------------------------


class TestCreateWavePanelFactory:
    """FR-WAVE-05/06: create_wave_panel must return the correct implementation
    based on h2o wave availability."""

    def test_create_wave_panel_returns_null_when_wave_unavailable(self):
        """FR-WAVE-05: When h2o_wave import fails, factory MUST return NullWavePanel."""
        with patch.dict(sys.modules, {"h2o_wave": None}):
            panel = create_wave_panel()
        assert isinstance(panel, NullWavePanel), (
            f"Expected NullWavePanel when h2o_wave unavailable, got {type(panel)}"
        )

    def test_create_wave_panel_returns_wave_panel_when_wave_available(self):
        """FR-WAVE-06: When h2o_wave is importable, factory MUST return WavePanel."""
        with patch.dict(sys.modules, {"h2o_wave": MagicMock()}):
            panel = create_wave_panel()
        assert isinstance(panel, WavePanel), (
            f"Expected WavePanel when h2o_wave available, got {type(panel)}"
        )

    def test_create_wave_panel_accepts_no_required_arguments(self):
        """FR-WAVE-05: create_wave_panel() must be callable with zero arguments."""
        with patch.dict(sys.modules, {"h2o_wave": None}):
            panel = create_wave_panel()  # must not raise TypeError
        assert panel is not None

    def test_create_wave_panel_returns_object_with_update_status(self):
        """The returned panel (either type) MUST have update_status callable."""
        with patch.dict(sys.modules, {"h2o_wave": None}):
            panel = create_wave_panel()
        assert callable(getattr(panel, "update_status", None))

    def test_create_wave_panel_null_panel_has_full_interface(self):
        """NullWavePanel from factory MUST expose all four WavePanel methods."""
        with patch.dict(sys.modules, {"h2o_wave": None}):
            panel = create_wave_panel()
        for method_name in ("update_status", "update_stage", "append_log", "clear_log"):
            assert callable(getattr(panel, method_name, None)), (
                f"Expected method '{method_name}' on panel returned by create_wave_panel()"
            )


# ---------------------------------------------------------------------------
# 9. create_desktop_notifier factory
# ---------------------------------------------------------------------------


class TestCreateDesktopNotifierFactory:
    """FR-WAVE-07/08: create_desktop_notifier must return the correct implementation
    based on plyer availability."""

    def test_create_desktop_notifier_returns_null_when_plyer_unavailable(self):
        """FR-WAVE-07: When plyer import fails, factory MUST return NullDesktopNotifier."""
        with patch.dict(sys.modules, {"plyer": None, "plyer.notification": None}):
            notifier = create_desktop_notifier()
        assert isinstance(notifier, NullDesktopNotifier), (
            f"Expected NullDesktopNotifier when plyer unavailable, got {type(notifier)}"
        )

    def test_create_desktop_notifier_returns_desktop_notifier_when_plyer_available(self):
        """FR-WAVE-08: When plyer is importable, factory MUST return DesktopNotifier."""
        mock_plyer = MagicMock()
        with patch.dict(sys.modules, {"plyer": mock_plyer, "plyer.notification": mock_plyer.notification}):
            notifier = create_desktop_notifier()
        assert isinstance(notifier, DesktopNotifier), (
            f"Expected DesktopNotifier when plyer available, got {type(notifier)}"
        )

    def test_create_desktop_notifier_accepts_no_required_arguments(self):
        """FR-WAVE-07: create_desktop_notifier() must be callable with zero arguments."""
        with patch.dict(sys.modules, {"plyer": None, "plyer.notification": None}):
            notifier = create_desktop_notifier()  # must not raise TypeError
        assert notifier is not None

    def test_create_desktop_notifier_null_has_full_interface(self):
        """NullDesktopNotifier from factory MUST expose all three notify methods."""
        with patch.dict(sys.modules, {"plyer": None, "plyer.notification": None}):
            notifier = create_desktop_notifier()
        for method_name in ("notify", "notify_stage_complete", "notify_error"):
            assert callable(getattr(notifier, method_name, None)), (
                f"Expected method '{method_name}' on notifier returned by create_desktop_notifier()"
            )


# ---------------------------------------------------------------------------
# 10. FR-WAVE-09: Zero core imports from ui/
# ---------------------------------------------------------------------------


class TestZeroCoreImportsFromUI:
    """FR-WAVE-09: Core orchestrator modules MUST NOT import from orchestrator.ui.
    The ui module is a plugin/optional layer only."""

    def _get_module_source(self, module_path: str) -> str:
        """Read the source of a module file."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent.parent.parent / module_path
        return src.read_text(encoding="utf-8")

    def test_engine_py_does_not_import_orchestrator_ui(self):
        """FR-WAVE-09: orchestrator/engine.py MUST NOT contain 'from orchestrator.ui'
        or 'import orchestrator.ui'."""
        source = self._get_module_source("orchestrator/engine.py")
        assert "orchestrator.ui" not in source, (
            "engine.py must not import from orchestrator.ui (zero core imports rule)"
        )

    def test_config_py_does_not_import_orchestrator_ui(self):
        """FR-WAVE-09: orchestrator/config.py MUST NOT import from orchestrator.ui."""
        source = self._get_module_source("orchestrator/config.py")
        assert "orchestrator.ui" not in source, (
            "config.py must not import from orchestrator.ui (zero core imports rule)"
        )

    def test_stages_base_does_not_import_orchestrator_ui(self):
        """FR-WAVE-09: orchestrator/stages/base.py MUST NOT import from orchestrator.ui."""
        source = self._get_module_source("orchestrator/stages/base.py")
        assert "orchestrator.ui" not in source, (
            "stages/base.py must not import from orchestrator.ui (zero core imports rule)"
        )

    def test_agents_adapter_does_not_import_orchestrator_ui(self):
        """FR-WAVE-09: orchestrator/agents/adapter.py MUST NOT import from orchestrator.ui."""
        source = self._get_module_source("orchestrator/agents/adapter.py")
        assert "orchestrator.ui" not in source, (
            "agents/adapter.py must not import from orchestrator.ui (zero core imports rule)"
        )

    def test_cli_does_not_import_orchestrator_ui(self):
        """FR-WAVE-09: orchestrator/cli.py MUST NOT import from orchestrator.ui."""
        source = self._get_module_source("orchestrator/cli.py")
        assert "orchestrator.ui" not in source, (
            "cli.py must not import from orchestrator.ui (zero core imports rule)"
        )


# ---------------------------------------------------------------------------
# 11. Edge cases and boundary conditions
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases that implementations must handle correctly."""

    def test_wave_panel_append_empty_string(self, wave_panel: WavePanel):
        """append_log with an empty string MUST not raise and must store it."""
        wave_panel.append_log("")
        log = wave_panel.get_log()
        assert "" in log

    def test_wave_panel_update_status_with_empty_string(self, wave_panel: WavePanel):
        """update_status('') MUST not raise."""
        wave_panel.update_status("")  # must not raise

    def test_wave_panel_update_stage_with_unicode_name(self, wave_panel: WavePanel):
        """update_stage with a unicode stage name MUST not raise."""
        wave_panel.update_stage("阶段-spec", 50)  # must not raise

    def test_wave_panel_append_log_unicode_message(self, wave_panel: WavePanel):
        """append_log with unicode content MUST not raise and must store correctly."""
        wave_panel.append_log("日志消息 — log entry with emoji 🚀")
        log = wave_panel.get_log()
        assert any("日志消息" in entry for entry in log)

    def test_null_wave_panel_update_stage_accepts_any_progress_without_raising(
        self, null_wave: NullWavePanel
    ):
        """NullWavePanel.update_stage MUST silently accept any value — it is no-op."""
        null_wave.update_stage("spec", 999)  # must not raise — null impl ignores validation
        null_wave.update_stage("spec", -99)  # must not raise — null impl ignores validation

    def test_desktop_notifier_notify_with_special_characters(self):
        """DesktopNotifier.notify must handle special characters in title/message."""
        mock_notification = MagicMock()
        mock_plyer = MagicMock()
        mock_plyer.notification = mock_notification
        with patch.dict(
            sys.modules,
            {"plyer": mock_plyer, "plyer.notification": mock_notification},
        ):
            notifier = DesktopNotifier()
            notifier.notify("Stage: 'spec' & \"plan\"", "Error: <>&")  # must not raise

    def test_null_notifier_notify_with_special_characters(
        self, null_notifier: NullDesktopNotifier
    ):
        """NullDesktopNotifier.notify must accept special characters silently."""
        result = null_notifier.notify("Title <>&", "Message with 'quotes'")
        assert result is None

    def test_wave_panel_get_log_returns_copy_not_reference(self, wave_panel: WavePanel):
        """get_log MUST return a copy — mutating the returned list must not affect
        the internal log state."""
        wave_panel.append_log("entry one")
        log_copy = wave_panel.get_log()
        log_copy.append("injected externally")
        # Internal log must not have been affected
        assert "injected externally" not in wave_panel.get_log()

    def test_wave_panel_multiple_clear_log_calls_do_not_raise(
        self, wave_panel: WavePanel
    ):
        """Calling clear_log multiple times in succession MUST not raise."""
        wave_panel.clear_log()
        wave_panel.clear_log()  # second call — must not raise

    def test_create_wave_panel_called_multiple_times_returns_independent_instances(self):
        """Each call to create_wave_panel MUST return a distinct panel instance."""
        with patch.dict(sys.modules, {"h2o_wave": None}):
            panel_a = create_wave_panel()
            panel_b = create_wave_panel()
        assert panel_a is not panel_b

    def test_create_desktop_notifier_called_multiple_times_returns_independent_instances(
        self,
    ):
        """Each call to create_desktop_notifier MUST return a distinct notifier instance."""
        with patch.dict(sys.modules, {"plyer": None, "plyer.notification": None}):
            notifier_a = create_desktop_notifier()
            notifier_b = create_desktop_notifier()
        assert notifier_a is not notifier_b
