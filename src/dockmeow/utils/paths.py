"""Cross-platform path resolution utilities.

Key functions:
    resource_path()  — locate bundled assets (PyInstaller-aware)
    user_workspace() — ~/DockMeow_Workspace  (job output files)
    app_data_dir()   — platform-specific app data dir (license, state)
    fpocket_binary() — path to the bundled fpocket executable
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def _resource_roots() -> list[Path]:
    roots: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))

    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin" and ".app/Contents/MacOS" in str(executable):
        contents = executable.parent.parent
        roots.extend([contents / "Resources", contents / "Frameworks"])
    elif getattr(sys, "frozen", False):
        roots.extend([executable.parent, executable.parent / "_internal"])

    roots.append(Path(__file__).parent.parent)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            key = root.resolve()
        except OSError:
            key = root
        if key not in seen:
            deduped.append(root)
            seen.add(key)
    return deduped


def resource_path(relative: str) -> Path:
    """Resolve a path relative to the package root, PyInstaller-aware.

    Args:
        relative: Path relative to the ``src/dockmeow/`` package directory.

    Returns:
        Absolute Path, whether running from source or a frozen bundle.
    """
    for root in _resource_roots():
        candidate = root / relative
        if candidate.exists():
            return candidate
    return _resource_roots()[0] / relative


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


def fpocket_candidates() -> list[Path]:
    """Return possible bundled fpocket executable paths for this platform."""
    if sys.platform == "win32":
        subdirs = ["windows"]
        name = "fpocket.exe"
    elif sys.platform == "darwin":
        machine = platform.machine().lower()
        subdirs = ["macos_arm64" if machine in {"arm64", "aarch64"} else "macos_x64"]
        name = "fpocket"
    else:
        subdirs = ["linux", "linux_x64"]
        name = "fpocket"

    candidates: list[Path] = []
    for root in _resource_roots():
        for sub in subdirs:
            candidates.append(root / "bundled" / "fpocket" / sub / name)
    return candidates


def is_usable_executable(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if sys.platform == "win32":
        return True
    if os.access(path, os.X_OK):
        return True
    try:
        path.chmod(path.stat().st_mode | 0o755)
    except OSError:
        return False
    return os.access(path, os.X_OK)


def fpocket_available() -> bool:
    return any(is_usable_executable(path) for path in fpocket_candidates())


def vina_binary() -> Path:
    """Return the bundled AutoDock Vina executable path for this platform."""
    if sys.platform == "win32":
        sub = "windows"
        name = "vina.exe"
    elif sys.platform == "darwin":
        sub = "macos_arm64" if platform.machine() == "arm64" else "macos_x64"
        name = "vina"
    else:
        sub = "linux"
        name = "vina"
    return resource_path(f"bundled/vina/{sub}/{name}")
