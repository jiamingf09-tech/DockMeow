"""Step 3 — Binding pocket selection page."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.pocket import Pocket
from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.pocket_card import PocketCard
from dockmeow.ui.widgets.viewer_3d import Viewer3D
from dockmeow.workers.pocket_worker import PocketWorker

_WINDOWS_FPOCKET_WARNING = (
    '⚠️ Windows 版本暂不支持自动口袋检测。'
    '如本结构无共结晶配体，请选择“全蛋白盲对接”或手动指定坐标。'
)


class PocketPage(QWidget):
    """List pocket candidates (cards) + 3D box visualization."""

    pocket_selected = Signal(object)  # Pocket

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._receptor_info = None
        self._pdb_path: Path | None = None
        self._worker: PocketWorker | None = None
        self._cards: list[PocketCard] = []
        self._pockets: list[Pocket] = []
        self._selected_pocket: Pocket | None = None
        self._last_receptor_key: tuple[Path, Path] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(6)

        # ---- Windows platform notice (permanent, shown only when fpocket absent) ----
        if sys.platform == "win32":
            from dockmeow.utils.paths import fpocket_binary
            if not fpocket_binary().exists():
                warn_bar = QFrame()
                warn_bar.setObjectName("WinFpocketWarn")
                warn_bar.setStyleSheet(
                    "#WinFpocketWarn {"
                    "  background:#FEF3C7; border:1px solid #FCD34D;"
                    "  border-radius:4px; padding:0px;"
                    "}"
                )
                warn_layout = QHBoxLayout(warn_bar)
                warn_layout.setContentsMargins(10, 6, 10, 6)
                warn_label = QLabel(_WINDOWS_FPOCKET_WARNING)
                warn_label.setWordWrap(True)
                warn_label.setStyleSheet("color:#78350F; font-size:12px; background:transparent;")
                warn_layout.addWidget(warn_label)
                outer.addWidget(warn_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        # ---- left: list of cards
        left = QWidget()
        left.setMinimumWidth(360)
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ll = QVBoxLayout(left)
        ll.setSpacing(8)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        ll.addWidget(self._status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards_holder = QWidget()
        self._cards_holder.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._cards_layout = QVBoxLayout(self._cards_holder)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(8)
        self._scroll.setWidget(self._cards_holder)
        ll.addWidget(self._scroll, 1)

        self._custom_btn = QPushButton(t("pocket.custom_btn"))
        self._custom_btn.setEnabled(True)
        self._custom_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._custom_btn.clicked.connect(self._on_custom_box)
        ll.addWidget(self._custom_btn)

        splitter.addWidget(left)

        # ---- right: 3D viewer
        self._viewer = Viewer3D()
        splitter.addWidget(self._viewer)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 630])
        self._splitter = splitter

    # ------------------------------------------------------------------
    def set_receptor(self, receptor_info, pdb_path: Path) -> None:
        """Called by MainWindow when receptor is ready."""
        new_path = Path(pdb_path)
        new_key = (Path(getattr(receptor_info, "pdb_path")), new_path)
        if self._last_receptor_key == new_key and (self._cards or self._selected_pocket):
            return
        self._receptor_info = receptor_info
        self._pdb_path = new_path
        self._last_receptor_key = new_key
        if self._pdb_path:
            self._viewer.load_receptor(self._pdb_path)
        self._start_detection()

    def _start_detection(self) -> None:
        if self._receptor_info is None or self._pdb_path is None:
            return
        self._status.setText(t("pocket.detecting"))
        self._selected_pocket = None
        self._pockets = []
        self._clear_cards()
        self._worker = PocketWorker(self._receptor_info, self._pdb_path)
        self._worker.finished_ok.connect(self._on_pockets)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _clear_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards.clear()

    def _on_pockets(self, pockets: list[Pocket]) -> None:
        self._status.setText(f"找到 {len(pockets)} 个候选口袋。")
        self._clear_cards()
        self._pockets = list(pockets)

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

        if pockets:
            self._highlight_pocket(pockets[0])

    def _on_card_selected(self, pocket: Pocket) -> None:
        self._highlight_pocket(pocket)

    def _highlight_pocket(self, pocket: Pocket) -> None:
        self._selected_pocket = pocket
        for c in self._cards:
            c.set_selected(c.pocket().pocket_id == pocket.pocket_id
                           and c.pocket().source == pocket.source)

        if self._pdb_path is not None:
            pockets = self._pockets if self._pockets and pocket in self._pockets else [pocket]
            self._viewer.load_receptor_with_pockets(self._pdb_path, pockets, pocket)
        elif self._pockets and pocket in self._pockets:
            self._viewer.show_pockets(self._pockets, pocket)
        else:
            self._viewer.show_box(pocket)

    def get_selected_pocket(self) -> Pocket | None:
        """Return the pocket selected by the user or default highlight."""
        return self._selected_pocket

    def _on_custom_box(self) -> None:
        from dockmeow.ui.dialogs.custom_box_dialog import CustomBoxDialog

        if self._selected_pocket is not None:
            default_center = self._selected_pocket.center
            default_size = self._selected_pocket.size
        else:
            default_center = (0, 0, 0)
            default_size = (22.5, 22.5, 22.5)

        dialog = CustomBoxDialog(default_center, default_size, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            center, size = dialog.get_box()
            custom_pocket = Pocket(
                pocket_id=999,
                center=center,
                size=size,
                score=0.0,
                residues=[],
                source="custom",
                label="自定义盒子",
            )
            self._selected_pocket = custom_pocket
            for c in self._cards:
                c.set_selected(False)
            self._viewer.show_box(custom_pocket)
            self._status.setText(
                "已使用自定义盒子："
                f"中心 ({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f})；"
                f"大小 ({size[0]:.1f}, {size[1]:.1f}, {size[2]:.1f}) Å。"
            )

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._status.setText(f"{user_message}\n{suggestion}")
        self._status.setStyleSheet("color: #F38BA8;")
