"""Top-level QApplication setup and application lifecycle management."""

from __future__ import annotations

import sys
import logging as _logging
import traceback as _traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dockmeow.utils.paths import resource_path


def _force_pyside_eager_import() -> None:
    """Pre-import every PySide6 sub-module we use in the MAIN THREAD.

    In PyInstaller bundles PySide6 uses Shiboken lazy-import which calls
    ``dlopen`` the first time a sub-module is accessed.  When that first
    access happens inside a QThread worker macOS dyld raises EXC_BAD_ACCESS
    (``mach_o::Header::forEachLoadCommand`` is not re-entrant from non-main
    threads).  Importing everything here, before any worker is started,
    converts all future accesses into simple dict lookups – no dlopen needed.
    """
    try:
        import PySide6.QtCore          # noqa: F401
        import PySide6.QtGui           # noqa: F401
        import PySide6.QtWidgets       # noqa: F401
        import PySide6.QtWebEngineCore     # noqa: F401
        import PySide6.QtWebEngineWidgets  # noqa: F401
        import PySide6.QtNetwork       # noqa: F401
        import PySide6.QtOpenGL        # noqa: F401
        import PySide6.QtOpenGLWidgets # noqa: F401
        import PySide6.QtPrintSupport  # noqa: F401
    except Exception:  # noqa: BLE001
        # Non-fatal: if a sub-module is absent (e.g. minimal Qt build), skip it
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
    # Must be first: pre-import PySide6 submodules in the main thread so that
    # worker QThreads never trigger Shiboken lazy-import / dlopen (macOS crash).
    _force_pyside_eager_import()
    _install_excepthook()
    app = create_app()
    license_data = _check_license()

    from dockmeow.ui.main_window import MainWindow

    window = MainWindow(license_data)
    window.show()
    return app.exec()
