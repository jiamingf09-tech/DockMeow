# Runtime hook: configure QtWebEngine before QApplication is created.
# Runs at frozen-app startup in the main thread.

import os
import sys


def _add_flag(flag: str) -> None:
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    parts = current.split()
    if flag not in parts:
        parts.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts).strip()


# ── Stability flags for unsigned PyInstaller .app on macOS ───────────────────
# --in-process-gpu : prevent Chromium from spawning a separate GPU subprocess.
#   Unsigned apps lack the entitlements macOS requires to spawn sandboxed helper
#   processes; the GPU subprocess dies immediately, crashing WebEngine on first
#   render call.  Running GPU in-process avoids this entirely.
# --no-sandbox : Chromium's sandbox also requires entitlements we don't have.
#   Disabling it is safe here because we only ever load inline HTML + local PDB
#   text — no arbitrary web content.
# --disable-renderer-accessibility : stop VoiceOver/AX from descending into the
#   Chromium AX tree, which causes hard crashes on some macOS versions.
# --disable-dev-shm-usage : /dev/shm is tiny on some macOS configs; use disk.
for _flag in [
    "--disable-renderer-accessibility",
    "--in-process-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]:
    _add_flag(_flag)

# ── Resource paths ────────────────────────────────────────────────────────────
if hasattr(sys, "_MEIPASS"):
    _meipass = sys._MEIPASS

    # Try _MEIPASS/webengine_resources first, then ../Resources/webengine_resources
    # (macOS .app bundles put resources in Contents/Resources/, not Contents/MacOS/)
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
