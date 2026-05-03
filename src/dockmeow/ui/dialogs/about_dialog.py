"""About dialog — version, license summary, third-party credits."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from dockmeow.ui.i18n import t
from dockmeow.utils.paths import resource_path
from dockmeow.version import __version__


class AboutDialog(QDialog):
    """Displays app metadata and acknowledgements."""

    def __init__(self, license_data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("about.title"))
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Logo
        logo_path = resource_path("ui/resources/icons/logo_128.png")
        if logo_path.exists():
            logo_lbl = QLabel()
            pix = QPixmap(str(logo_path)).scaled(
                128, 128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(logo_lbl)

        title = QLabel(t("app.title"))
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel(t("about.tagline")))
        layout.addWidget(QLabel(t("about.version", ver=__version__)))

        if license_data:
            layout.addWidget(
                QLabel(t("status.activated", email=str(license_data.get("email", ""))))
            )
        else:
            layout.addWidget(QLabel(t("status.not_activated")))

        credits = QLabel(t("about.credits"))
        credits.setWordWrap(True)
        credits.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        layout.addWidget(credits)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
