"""Dialog shown when the license machine fingerprint does not match."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from dockmeow.licensing.machine import get_machine_id
from dockmeow.ui.i18n import t


class MachineMismatchDialog(QDialog):
    """Show machine mismatch warning with current machine ID."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("mismatch.title"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(t("mismatch.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        msg = QLabel(t("mismatch.message"))
        msg.setWordWrap(True)
        layout.addWidget(msg)

        try:
            mid = get_machine_id()
        except Exception:  # noqa: BLE001
            mid = "(unavailable)"
        mid_lbl = QLabel(t("mismatch.machine_id", mid=mid))
        mid_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        mid_lbl.setStyleSheet("font-family: Menlo, monospace; color: #A6ADC8;")
        layout.addWidget(mid_lbl)

        buttons = QDialogButtonBox()
        contact_btn = buttons.addButton(
            t("common.contact"), QDialogButtonBox.ButtonRole.ActionRole
        )
        close_btn = buttons.addButton(
            t("common.close"), QDialogButtonBox.ButtonRole.RejectRole
        )
        contact_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("mailto:support@dockmeow.app?subject=License%20rebind")
            )
        )
        close_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)
