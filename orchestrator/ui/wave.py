"""Optional Wave panel UI and desktop notifications.

Zero core imports from ui/ — this module is a plugin/optional layer.
All classes degrade gracefully when optional dependencies are unavailable.
"""

from __future__ import annotations


class WavePanel:
    pass


class NullWavePanel:
    pass


class DesktopNotifier:
    pass


class NullDesktopNotifier:
    pass


def create_wave_panel(*args, **kwargs):
    raise NotImplementedError("not implemented")


def create_desktop_notifier(*args, **kwargs):
    raise NotImplementedError("not implemented")
