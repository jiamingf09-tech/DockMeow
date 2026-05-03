"""Cross-platform path resolution utilities.

Key functions:
    resource_path()  — locate bundled assets (PyInstaller-aware)
    user_workspace() — ~/DockMeow_Workspace  (job output files)
    app_data_dir()   — platform-specific app data dir (license, state)
    fpocket_binary() — path to the bundled fpocket executable
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve a path relative to the package root, PyInstaller-aware.

    Args:
        relative: Path relative to the ``src/dockmeow/`` package directory.

    Returns:
        Absolute Path, whether running from source or a frozen bundle.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).parent.parent / relative


def user_workspace() -> Path:
    """Return (and create) the user-facing job output directory.

    Returns:
        ``~/DockMeow_Workspace`` — always exists after this call.
    """
    p = Path.home() / "DockMeow_Workspace"
    p.mkdir(exist_ok=True)
    return p


def app_data_dir() -> Path:
    """Return (and create) the platform-specific application data directory.

    Used for the license file and encrypted state file.

    Platform paths:
        macOS   — ~/Library/Application Support/DockMeow
        Windows — %APPDATA%/DockMeow
        Linux   — ~/.config/dockmeow
    """
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Roaming" / "DockMeow"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "DockMeow"
    else:
        base = Path.home() / ".config" / "dockmeow"
    base.mkdir(parents=True, exist_ok=True)
    return base


def fpocket_binary() -> Path:
    """Return the path to the bundled fpocket executable for the current platform.

    Returns:
        Absolute path; does not verify the binary exists (caller must check).
    """
    if sys.platform == "win32":
        sub = "windows"
        name = "fpocket.exe"
    elif sys.platform == "darwin":
        sub = "macos_arm64" if platform.machine() == "arm64" else "macos_x64"
        name = "fpocket"
    else:
        sub = "linux"
        name = "fpocket"
    return resource_path(f"bundled/fpocket/{sub}/{name}")
