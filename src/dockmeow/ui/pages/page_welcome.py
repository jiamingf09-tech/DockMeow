"""Welcome page — shown on first launch when no license is installed."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dockmeow.ui.dialogs.about_dialog import AboutDialog
from dockmeow.ui.dialogs.activation_dialog import ActivationDialog
from dockmeow.ui.i18n import t
from dockmeow.utils.paths import resource_path


class WelcomePage(QWidget):
    """Centered welcome screen with activation entry."""

    license_activated = Signal(dict)

    def __init__(self, license_data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self._license_data = license_data

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(18)

        # Logo (512px, scales down on small screens)
        logo_path = resource_path("ui/resources/icons/logo_512.png")
        if logo_path.exists():
            logo_lbl = QLabel()
            pix = QPixmap(str(logo_path)).scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            outer.addWidget(logo_lbl)

        title = QLabel(t("welcome.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 800;")
        outer.addWidget(title)

        subtitle = QLabel(t("about.tagline"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #A6ADC8;")
        outer.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(12)

        self._activate_btn = QPushButton(t("welcome.activate_btn"))
        self._activate_btn.setMinimumSize(180, 44)
        self._activate_btn.setObjectName("PrimaryButton")
        self._activate_btn.clicked.connect(self._on_activate)
        btn_row.addWidget(self._activate_btn)

        self._learn_btn = QPushButton(t("welcome.learn_more_btn"))
        self._learn_btn.setMinimumSize(180, 44)
        self._learn_btn.clicked.connect(self._on_learn)
        btn_row.addWidget(self._learn_btn)

        outer.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status)
        self._refresh_status()

    def set_license(self, data: dict | None) -> None:
        self._license_data = data
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self._license_data:
            email = str(self._license_data.get("email", ""))
            self._status.setText(t("status.activated", email=email))
            self._status.setStyleSheet("color: #A6E3A1;")
        else:
            self._status.setText(t("status.not_activated"))
            self._status.setStyleSheet("color: #F9E2AF;")

    def _on_activate(self) -> None:
        dlg = ActivationDialog(self)
        if dlg.exec() and dlg.accepted_data is not None:
            self._license_data = dlg.accepted_data
            self._refresh_status()
            self.license_activated.emit(dlg.accepted_data)

    def _on_learn(self) -> None:
        AboutDialog(self._license_data, self).exec()
