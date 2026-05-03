"""Dialog shown when the loaded license has expired."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from dockmeow.ui.i18n import t


class LicenseExpiredDialog(QDialog):
    """Inform the user the license has expired."""

    def __init__(self, license_data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._license_data = license_data or {}
        self.setWindowTitle(t("expired.title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(t("expired.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        msg = QLabel(t("expired.message"))
        msg.setWordWrap(True)
        layout.addWidget(msg)

        buttons = QDialogButtonBox()
        contact_btn = buttons.addButton(
            t("common.contact"), QDialogButtonBox.ButtonRole.ActionRole
        )
        close_btn = buttons.addButton(
            t("common.close"), QDialogButtonBox.ButtonRole.RejectRole
        )
        contact_btn.clicked.connect(self._open_mail)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _open_mail(self) -> None:
        QDesktopServices.openUrl(
            QUrl("mailto:support@dockmeow.app?subject=License%20renewal")
        )
