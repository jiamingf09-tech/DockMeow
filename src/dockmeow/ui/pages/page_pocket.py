"""Step 3 — Binding pocket selection page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.pocket import Pocket
from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.pocket_card import PocketCard
from dockmeow.ui.widgets.viewer_3d import Viewer3D
from dockmeow.workers.pocket_worker import PocketWorker


class PocketPage(QWidget):
    """List pocket candidates (cards) + 3D box visualization."""

    pocket_selected = Signal(object)  # Pocket

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._receptor_info = None
        self._pdb_path: Path | None = None
        self._worker: PocketWorker | None = None
        self._cards: list[PocketCard] = []
        self._selected_pocket: Pocket | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- left: list of cards
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setSpacing(8)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        ll.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._cards_holder = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_holder)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(8)
        self._scroll.setWidget(self._cards_holder)
        ll.addWidget(self._scroll, 1)

        self._custom_btn = QPushButton(t("pocket.custom_btn"))
        self._custom_btn.setEnabled(False)  # Reserved for future custom-box dialog
        ll.addWidget(self._custom_btn)

        splitter.addWidget(left)

        # ---- right: 3D viewer
        self._viewer = Viewer3D()
        splitter.addWidget(self._viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def set_receptor(self, receptor_info, pdb_path: Path) -> None:
        """Called by MainWindow when receptor is ready."""
        self._receptor_info = receptor_info
        self._pdb_path = Path(pdb_path)
        if self._pdb_path:
            self._viewer.load_receptor(self._pdb_path)
        self._start_detection()

    def _start_detection(self) -> None:
        if self._receptor_info is None or self._pdb_path is None:
            return
        self._status.setText(t("pocket.detecting"))
        self._clear_cards()
        self._worker = PocketWorker(self._receptor_info, self._pdb_path)
        self._worker.finished_ok.connect(self._on_pockets)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _clear_cards(self) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()

    def _on_pockets(self, pockets: list[Pocket]) -> None:
        self._status.setText(f"找到 {len(pockets)} 个候选口袋。")
        self._clear_cards()

        # Show whole-protein "blind" warning hint
        any_blind = any(p.source == "whole" for p in pockets)
        if any_blind and len(pockets) <= 1:
            warn = QLabel(t("pocket.blind_warning"))
            warn.setStyleSheet("color: #F9E2AF;")
            warn.setWordWrap(True)
            self._cards_layout.addWidget(warn)

        for p in pockets:
            card = PocketCard(p, self._cards_holder)
            card.selected.connect(self._on_card_selected)
            self._cards_layout.addWidget(card)
            self._cards.append(card)

        # Auto-select first
        if pockets:
            self._on_card_selected(pockets[0])

    def _on_card_selected(self, pocket: Pocket) -> None:
        self._selected_pocket = pocket
        for c in self._cards:
            c.set_selected(c.pocket().pocket_id == pocket.pocket_id
                           and c.pocket().source == pocket.source)

        # Redraw box
        if self._pdb_path is not None:
            self._viewer.load_receptor(self._pdb_path)
        self._viewer.show_box(pocket.center, pocket.size)
        self.pocket_selected.emit(pocket)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._status.setText(f"{user_message}\n{suggestion}")
        self._status.setStyleSheet("color: #F38BA8;")
