"""Persistent user preferences via QSettings.

Stores ordinary UI preferences (last output directory, exhaustiveness preset, etc.).
License data and time-guard state are stored separately in licensing/state.py.
"""

from __future__ import annotations

# QSettings is imported lazily to keep this importable without a QApplication.
_DEFAULTS: dict[str, object] = {
    "last_output_dir": "",
    "exhaustiveness_preset": 1,   # 0=快速 1=标准 2=精细 3=极精细
    "show_advanced_params": False,
    "window_geometry": b"",
}


def get(key: str):
    """Read a preference value.

    Args:
        key: Settings key (must be in _DEFAULTS).

    Returns:
        Stored value, or the default if not yet set.

    Raises:
        NotImplementedError: until Stage 3.
    """
    raise NotImplementedError


def set(key: str, value) -> None:
    """Write a preference value.

    Raises:
        NotImplementedError: until Stage 3.
    """
    raise NotImplementedError
