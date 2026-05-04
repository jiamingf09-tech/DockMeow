"""Top-level QApplication setup and application lifecycle management."""

from __future__ import annotations

import sys
import logging as _logging
import traceback as _traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dockmeow.utils.paths import resource_path


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
    _install_excepthook()
    app = create_app()
    license_data = _check_license()

    from dockmeow.ui.main_window import MainWindow

    window = MainWindow(license_data)
    window.show()
    return app.exec()
