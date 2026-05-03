"""Step 1 — Receptor (protein PDB) selection and preparation page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.drop_zone import DropZone
from dockmeow.ui.widgets.viewer_3d import Viewer3D
from dockmeow.utils.paths import user_workspace
from dockmeow.workers.prepare_worker import PrepareReceptorWorker


class ReceptorPage(QWidget):
    """Drag-and-drop PDB loader running PrepareReceptorWorker."""

    receptor_ready = Signal(object, object)  # ReceptorInfo, Path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: PrepareReceptorWorker | None = None
        self._pdb_path: Path | None = None
        self._receptor_info = None

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- left panel
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setSpacing(8)

        self._drop = DropZone(
            t("receptor.drop_hint"),
            ["pdb", "ent"],
            self,
            file_dialog_filter="PDB (*.pdb *.ent);;All files (*)",
        )
        self._drop.file_dropped.connect(self._on_file)
        ll.addWidget(self._drop)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        ll.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        ll.addWidget(self._status)

        ll.addWidget(QLabel(t("receptor.hetero_groups")))
        self._hetero_list = QListWidget()
        ll.addWidget(self._hetero_list, 1)

        ll.addWidget(QLabel(t("receptor.warnings")))
        self._warnings = QListWidget()
        ll.addWidget(self._warnings, 1)

        splitter.addWidget(left)

        # ---- right panel
        self._viewer = Viewer3D()
        splitter.addWidget(self._viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def _on_file(self, path: Path) -> None:
        self._pdb_path = path
        self._hetero_list.clear()
        self._warnings.clear()
        self._status.setText(t("receptor.preparing"))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        work_dir = user_workspace() / "receptor"
        work_dir.mkdir(parents=True, exist_ok=True)

        self._worker = PrepareReceptorWorker(path, work_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stage: str, pct: int, msg: str) -> None:
        self._progress.setValue(int(pct))
        self._status.setText(msg or stage)

    def _on_done(self, info) -> None:
        self._receptor_info = info
        self._progress.setVisible(False)
        self._status.setText("受体准备完成。")

        for h in getattr(info, "hetero_groups", []) or []:
            tag = "★ " if getattr(h, "is_likely_ligand", False) else ""
            self._hetero_list.addItem(
                f"{tag}{h.resname}  chain={h.chain}  resi={h.resi}"
            )
        for w in getattr(info, "warnings", []) or []:
            self._warnings.addItem(w)

        # Display the original PDB (with HETATM) in the viewer.
        if self._pdb_path is not None:
            self._viewer.load_receptor(self._pdb_path)

        self.receptor_ready.emit(info, self._pdb_path)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._progress.setVisible(False)
        self._status.setText(f"{user_message}\n{suggestion}")
        self._status.setStyleSheet("color: #F38BA8;")
