"""License activation dialog (.dmlic drop / browse)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from dockmeow.core.exceptions import DockMeowError
from dockmeow.licensing.verifier import LicenseVerifier, activate
from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.drop_zone import DropZone


class ActivationDialog(QDialog):
    """Drop-zone for .dmlic files with verification feedback."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.accepted_data: dict | None = None

        self.setWindowTitle(t("activation.title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._drop = DropZone(
            t("activation.drop_hint"), ["dmlic"], self,
            file_dialog_filter="License (*.dmlic);;All files (*)",
        )
        self._drop.file_dropped.connect(self._on_file)
        layout.addWidget(self._drop)

        row = QHBoxLayout()
        row.addStretch(1)
        browse = QPushButton(t("activation.browse_btn"))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        self._info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._info_label)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #F38BA8;")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _browse(self) -> None:
        # Reuse drop zone's file dialog click behaviour
        self._drop.mousePressEvent  # noqa: B018
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, t("activation.title"), "",
            "License (*.dmlic);;All files (*)",
        )
        if path:
            self._on_file(Path(path))

    def _on_file(self, path: Path) -> None:
        self._info_label.setText("")
        self._error_label.setText("")
        try:
            activate(path)
            data = LicenseVerifier().load_and_verify()
        except DockMeowError as e:
            self._error_label.setText(
                f"{e.user_message}\n{getattr(e, 'suggestion', '') or ''}"
            )
            return
        except Exception as e:  # noqa: BLE001
            self._error_label.setText(f"激活失败：{e}")
            return

        self.accepted_data = data
        info = "\n".join(
            [
                t("activation.success"),
                t("activation.license_no", no=str(data.get("license_no") or data.get("license_id", ""))),
                t("activation.email", email=str(data.get("email", ""))),
                t("activation.type", type=str(data.get("type", ""))),
            ]
        )
        self._info_label.setText(info)
        # Auto-accept after success.
        self.accept()
