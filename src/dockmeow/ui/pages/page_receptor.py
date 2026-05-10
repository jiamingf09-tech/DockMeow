"""Step 1 — Receptor (protein PDB) selection and preparation page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.receptor import detect_nucleic_acid_chains
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
        self._viewer: Viewer3D | None = None

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
        self._viewer_host = QWidget()
        self._viewer_layout = QVBoxLayout(self._viewer_host)
        self._viewer_layout.setContentsMargins(0, 0, 0, 0)
        self._viewer_placeholder = QLabel("3D 预览将在载入受体后初始化。")
        self._viewer_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewer_placeholder.setWordWrap(True)
        self._viewer_layout.addWidget(self._viewer_placeholder)
        splitter.addWidget(self._viewer_host)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    def _ensure_viewer(self) -> Viewer3D:
        if self._viewer is None:
            self._viewer = Viewer3D()
            self._viewer_placeholder.hide()
            self._viewer_layout.addWidget(self._viewer)
        return self._viewer

    def _destroy_viewer(self) -> None:
        if self._viewer is None:
            return
        viewer = self._viewer
        self._viewer = None
        viewer.suspend_for_page_hide()
        self._viewer_layout.removeWidget(viewer)
        viewer.setParent(None)
        viewer.deleteLater()
        self._viewer_placeholder.show()

    def on_page_leave(self) -> None:
        self._destroy_viewer()

    def on_page_enter(self) -> None:
        if self._receptor_info is not None:
            self._ensure_viewer().load_receptor(Path(self._receptor_info.pdb_path))

    def _on_file(self, path: Path) -> None:
        self._pdb_path = path
        self._hetero_list.clear()
        self._warnings.clear()

        # Quick pre-scan for nucleic acid chains (no PDBFixer needed)
        na_chains = detect_nucleic_acid_chains(path)
        strip_na = False
        if na_chains:
            chains_str = ", ".join(na_chains)
            reply = QMessageBox.question(
                self,
                "检测到 DNA/RNA 链",
                f"PDB 文件包含核酸链：{chains_str}\n\n"
                f"分子对接通常只针对蛋白质部分。是否自动移除核酸链？\n\n"
                f"• 选「是」：移除 DNA/RNA，对接蛋白质部分（推荐）\n"
                f"• 选「否」：保留全部（可能导致后续处理失败）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            strip_na = reply == QMessageBox.StandardButton.Yes

        self._status.setText(t("receptor.preparing"))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        work_dir = user_workspace() / "receptor"
        work_dir.mkdir(parents=True, exist_ok=True)

        self._worker = PrepareReceptorWorker(path, work_dir, strip_nucleic_acids=strip_na)
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
        na_chains = getattr(info, "nucleic_acid_chains", [])
        if na_chains:
            self._status.setText(f"受体准备完成。（核酸链 {', '.join(na_chains)} 已处理）")
        else:
            self._status.setText("受体准备完成。")

        stripped_chains = set(getattr(info, "nucleic_acid_chains", []) or [])
        for h in getattr(info, "hetero_groups", []) or []:
            if getattr(h, "chain", None) in stripped_chains:
                continue
            tag = "★ " if getattr(h, "is_likely_ligand", False) else ""
            self._hetero_list.addItem(
                f"{tag}{h.resname}  chain={h.chain}  resi={h.resi}"
            )
        for w in getattr(info, "warnings", []) or []:
            self._warnings.addItem(w)

        prepared_pdb = Path(info.pdb_path)
        self._ensure_viewer().load_receptor(prepared_pdb)

        self.receptor_ready.emit(info, prepared_pdb)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._progress.setVisible(False)
        self._status.setText(f"{user_message}\n{suggestion}")
        self._status.setStyleSheet("color: #F38BA8;")
