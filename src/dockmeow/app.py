"""Top-level QApplication setup and application lifecycle management."""

from __future__ import annotations

import logging as _logging
import os
import sys
import traceback as _traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dockmeow.utils.logging_setup import setup_logging
from dockmeow.utils.paths import resource_path


def _configure_webengine_flags() -> None:
    """Install Chromium flags before QtWebEngine is imported."""
    flag = "--disable-renderer-accessibility"
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    parts = current.split()
    if flag not in parts:
        parts.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts).strip()


def _force_pyside_eager_import() -> None:
    """Pre-import every PySide6 sub-module in the MAIN THREAD.

    Must be called AFTER QApplication is created (QtWebEngineWidgets requires it).

    In PyInstaller bundles PySide6 uses Shiboken lazy-import which calls
    ``dlopen`` the first time a sub-module is accessed.  When that access
    happens inside a QThread worker macOS dyld raises EXC_BAD_ACCESS
    (``mach_o::Header::forEachLoadCommand`` is not re-entrant from non-main
    threads).  Importing everything here converts future accesses to plain
    dict lookups – no dlopen needed.
    """
    _mods = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
    ]
    for _mod in _mods:
        try:
            __import__(_mod)
        except Exception:  # noqa: BLE001
            pass



def _install_excepthook() -> None:
    """Install a global exception handler that shows a dialog instead of crashing."""
    import sys as _sys

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
        _logging.getLogger("dockmeow").critical("未捕获异常:\n%s", tb_str)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None,
                    "发生意外错误",
                    f"软件遇到未预期的错误，已记录到日志。\n\n"
                    f"如反复出现，请将日志发送给客服。\n\n"
                    f"错误类型: {exc_type.__name__}\n"
                    f"详情: {exc_value}",
                )
        except Exception:
            pass

    _sys.excepthook = _excepthook


def create_app() -> QApplication:
    """Create and configure the QApplication instance."""
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("DockMeow")
    app.setOrganizationName("DockMeow")

    qss = resource_path("ui/resources/styles.qss")
    if qss.exists():
        try:
            app.setStyleSheet(qss.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass

    return app


def _check_license() -> dict | None:
    """Best-effort license check; returns the payload or None."""
    from dockmeow.core.exceptions import LicenseError
    from dockmeow.licensing.time_guard import check_clock_integrity
    from dockmeow.licensing.verifier import LicenseVerifier

    try:
        check_clock_integrity()
    except Exception:  # noqa: BLE001
        pass
    try:
        return LicenseVerifier().load_and_verify()
    except LicenseError:
        return None
    except Exception:  # noqa: BLE001
        return None


def run() -> int:
    """Full application lifecycle: create → license-check → main window → exec."""
    _configure_webengine_flags()
    setup_logging()
    _install_excepthook()
    _log = _logging.getLogger("dockmeow")
    _log.info("DockMeow startup: begin")

    # QApplication must exist before importing QtWebEngineWidgets.
    app = create_app()
    _log.info("DockMeow startup: QApplication ready")

    # Pre-import PySide6 sub-modules so worker QThreads never trigger
    # Shiboken lazy-import / dlopen (macOS PyInstaller dyld crash).
    # Scientific C-extensions are pre-loaded at module level in
    # receptor.py and ligand.py which are imported via main_window below.
    _force_pyside_eager_import()
    _log.info("DockMeow startup: PySide eager import finished")

    license_data = _check_license()
    _log.info("DockMeow startup: license check finished")

    from dockmeow.ui.main_window import MainWindow

    window = MainWindow(license_data)
    window.show()
    _log.info("DockMeow startup: main window shown")
    return app.exec()
