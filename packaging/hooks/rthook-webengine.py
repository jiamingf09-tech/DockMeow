# Runtime hook: configure QtWebEngine before QApplication is created.
# Runs at frozen-app startup in the main thread.

import os
import sys

_IS_MACOS   = sys.platform == "darwin"
_IS_WINDOWS = sys.platform == "win32"


def _add_flag(flag: str) -> None:
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    parts = current.split()
    if flag not in parts:
        parts.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts).strip()


# ── Platform-specific Chromium stability flags ────────────────────────────────
# --disable-renderer-accessibility : stop VoiceOver/AX (macOS) or MSAA (Windows)
#   from descending into the Chromium AX tree, which causes crashes.
_add_flag("--disable-renderer-accessibility")

if _IS_MACOS:
    # --in-process-gpu : unsigned macOS .app bundles lack the entitlement to
    #   spawn the sandboxed GPU subprocess; keep GPU in-process instead.
    # --no-sandbox : same reason — no sandbox entitlement in unsigned bundle.
    # --disable-dev-shm-usage : /dev/shm is tiny on some macOS configs; use disk.
    for _flag in [
        "--in-process-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]:
        _add_flag(_flag)

if _IS_WINDOWS:
    # --no-sandbox : PyInstaller one-dir builds are not installed as a proper
    #   Windows service; Chromium's Win32 sandbox setup fails without it.
    # --disable-gpu : avoids GPU driver crashes on some Windows VMs / CI machines.
    #   Remove this if hardware-accelerated rendering is working on your system.
    for _flag in [
        "--no-sandbox",
        "--disable-gpu",
    ]:
        _add_flag(_flag)

# ── Resource paths ────────────────────────────────────────────────────────────
if hasattr(sys, "_MEIPASS"):
    _meipass = sys._MEIPASS

    # Candidate locations for webengine_resources (searched in order):
    #   1. _MEIPASS/webengine_resources        → Windows + Linux (COLLECT layout)
    #   2. ../Resources/webengine_resources    → macOS .app bundle
    #      (Contents/MacOS/_MEIPASS → Contents/Resources/)
    _candidates = [
        os.path.join(_meipass, "webengine_resources"),
        os.path.join(_meipass, "..", "Resources", "webengine_resources"),
    ]
    for _res in _candidates:
        _res = os.path.normpath(_res)
        if os.path.isdir(_res):
            os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", _res)
            _locales = os.path.join(_res, "qtwebengine_locales")
            if os.path.isdir(_locales):
                os.environ.setdefault("QTWEBENGINE_LOCALES_PATH", _locales)
            break
