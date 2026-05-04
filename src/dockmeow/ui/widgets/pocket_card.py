"""Pocket info card widget shown in the pocket selection page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from dockmeow.core.pocket import Pocket


class PocketCard(QFrame):
    """Clickable card showing pocket label, score, and box geometry."""

    selected = Signal(object)  # emits the Pocket on click

    def __init__(self, pocket: Pocket, parent=None) -> None:
        super().__init__(parent)
        self._pocket = pocket
        self._is_selected = False
        self.setObjectName("PocketCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(pocket.label or f"口袋 {pocket.pocket_id}")
        title.setObjectName("PocketTitle")
        title.setStyleSheet("font-weight: 700; font-size: 14px;")
        title.setWordWrap(True)
        layout.addWidget(title)

        score_lbl = QLabel(f"评分：{pocket.score:.2f}  ·  来源：{pocket.source}")
        score_lbl.setStyleSheet("color: #A6ADC8;")
        score_lbl.setWordWrap(True)
        layout.addWidget(score_lbl)

        cx, cy, cz = pocket.center
        sx, sy, sz = pocket.size
        center_lbl = QLabel(f"中心：({cx:.1f}, {cy:.1f}, {cz:.1f})")
        center_lbl.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        center_lbl.setWordWrap(True)
        layout.addWidget(center_lbl)

        size_lbl = QLabel(f"盒子：{sx:.1f} × {sy:.1f} × {sz:.1f} Å")
        size_lbl.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        size_lbl.setWordWrap(True)
        layout.addWidget(size_lbl)

        self._refresh_style()

    def pocket(self) -> Pocket:
        return self._pocket

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        if self._is_selected:
            self.setStyleSheet(
                "QFrame#PocketCard {"
                "  background: #2E3450;"
                "  border: 2px solid #7C9EF8;"
                "  border-radius: 10px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame#PocketCard {"
                "  background: #252535;"
                "  border: 1px solid #45475A;"
                "  border-radius: 10px;"
                "}"
                "QFrame#PocketCard:hover {"
                "  border-color: #7C9EF8;"
                "}"
            )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._pocket)
        super().mousePressEvent(event)
