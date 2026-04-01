"""Optional Wave panel UI and desktop notifications.

Zero core imports from ui/ — this module is a plugin/optional layer.
All classes degrade gracefully when optional dependencies are unavailable.
"""

from __future__ import annotations


class WavePanel:
    """Real Wave panel implementation backed by h2o_wave."""

    def __init__(self) -> None:
        self._status: str = ""
        self._log: list[str] = []

    def update_status(self, status: str) -> None:
        self._status = status

    def get_status(self) -> str:
        return self._status

    def update_stage(self, stage: str, progress: int) -> None:
        if progress < 0 or progress > 100:
            raise ValueError(
                f"progress must be between 0 and 100 inclusive, got {progress}"
            )

    def append_log(self, message: str) -> None:
        self._log.append(message)

    def get_log(self) -> list[str]:
        return list(self._log)

    def clear_log(self) -> None:
        self._log = []


class NullWavePanel:
    """No-op Wave panel used when h2o_wave is unavailable."""

    def update_status(self, status: str) -> None:
        return None

    def get_status(self) -> str:
        return ""

    def update_stage(self, stage: str, progress: int) -> None:
        return None

    def append_log(self, message: str) -> None:
        return None

    def get_log(self) -> list[str]:
        return []

    def clear_log(self) -> None:
        return None


class DesktopNotifier:
    """Desktop notifier backed by plyer."""

    def notify(self, title: str, message: str) -> None:
        import plyer
        plyer.notification.notify(title=title, message=message)

    def notify_stage_complete(self, stage_name: str) -> None:
        import plyer
        plyer.notification.notify(
            title="Stage Complete",
            message=f"Stage '{stage_name}' completed successfully.",
        )

    def notify_error(self, error_message: str) -> None:
        import plyer
        plyer.notification.notify(
            title="Error",
            message=error_message,
        )


class NullDesktopNotifier:
    """No-op desktop notifier used when plyer is unavailable."""

    def notify(self, title: str, message: str) -> None:
        return None

    def notify_stage_complete(self, stage_name: str) -> None:
        return None

    def notify_error(self, error_message: str) -> None:
        return None


def create_wave_panel() -> WavePanel | NullWavePanel:
    """Return WavePanel if h2o_wave is available, else NullWavePanel."""
    try:
        import h2o_wave  # noqa: F401
        return WavePanel()
    except ImportError:
        return NullWavePanel()


def create_desktop_notifier() -> DesktopNotifier | NullDesktopNotifier:
    """Return DesktopNotifier if plyer is available, else NullDesktopNotifier."""
    try:
        import plyer  # noqa: F401
        return DesktopNotifier()
    except ImportError:
        return NullDesktopNotifier()
