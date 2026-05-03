"""Step 6 — Results page."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.viewer_3d import Viewer3D


class ResultsPage(QWidget):
    """Display poses table + 3D viewer + export buttons."""

    new_docking_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._receptor_info = None
        self._ligand_info = None
        self._result = None
        self._pdb_path: Path | None = None
        self._poses_sdf_blocks: list[str] = []
        self._auto_screenshot: Path | None = None  # pre-captured for PDF export

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- left: viewer
        self._viewer = Viewer3D()
        splitter.addWidget(self._viewer)

        # ---- right: table + buttons
        right = QWidget()
        rl = QVBoxLayout(right)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels([
            t("results.pose"),
            t("results.affinity"),
            t("results.rmsd_lb"),
            t("results.rmsd_ub"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._on_pose_changed)
        rl.addWidget(self._table, 1)

        btns = QHBoxLayout()
        self._sdf_btn = QPushButton(t("results.export_sdf"))
        self._pdb_btn = QPushButton(t("results.export_pdb"))
        self._pdf_btn = QPushButton(t("results.export_pdf"))
        self._new_btn = QPushButton(t("results.new_docking"))
        self._sdf_btn.clicked.connect(self._export_sdf)
        self._pdb_btn.clicked.connect(self._export_pdb)
        self._pdf_btn.clicked.connect(self._export_pdf)
        self._new_btn.clicked.connect(self.new_docking_requested.emit)
        for b in (self._sdf_btn, self._pdb_btn, self._pdf_btn, self._new_btn):
            btns.addWidget(b)
        rl.addLayout(btns)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

    # ------------------------------------------------------------------
    def set_context(self, receptor_info, ligand_info, pdb_path: Path) -> None:
        self._receptor_info = receptor_info
        self._ligand_info = ligand_info
        self._pdb_path = Path(pdb_path) if pdb_path else None
        if self._pdb_path:
            self._viewer.load_receptor(self._pdb_path)

    def set_result(self, result) -> None:
        self._result = result
        self._auto_screenshot = None  # reset for this docking session
        self._poses_sdf_blocks = self._split_sdf(
            Path(result.poses_sdf).read_text(encoding="utf-8", errors="replace")
            if Path(result.poses_sdf).exists() else ""
        )

        scores = list(result.scores or [])
        rmsd_lb = list(result.rmsd_lb or [0.0] * len(scores))
        rmsd_ub = list(result.rmsd_ub or [0.0] * len(scores))

        self._table.setRowCount(len(scores))
        for i, s in enumerate(scores):
            self._table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._table.setItem(i, 1, QTableWidgetItem(f"{s:.2f}"))
            self._table.setItem(
                i, 2, QTableWidgetItem(f"{rmsd_lb[i]:.2f}" if i < len(rmsd_lb) else "-"),
            )
            self._table.setItem(
                i, 3, QTableWidgetItem(f"{rmsd_ub[i]:.2f}" if i < len(rmsd_ub) else "-"),
            )
        if scores:
            self._table.selectRow(0)

        # Pre-capture receptor + best pose screenshot for later PDF export.
        # Use the on_ready callback so capture fires only after loadBestPose() JS
        # returns (models loaded + render() issued) — avoids fixed-timer race.
        if self._pdb_path and self._poses_sdf_blocks:
            _shot_path = Path(tempfile.mkstemp(suffix="_dm_pdf.png")[1])

            def _auto_save(path: Path) -> None:
                if path.exists():
                    self._auto_screenshot = path

            def _do_capture() -> None:
                # loadBestPose render() fired; wait one RAF frame (≈16 ms) then grab.
                QTimer.singleShot(
                    50, lambda: self._viewer.capture_png(_shot_path, callback=_auto_save)
                )

            self._viewer.load_best_pose_for_export(
                self._pdb_path,
                self._poses_sdf_blocks[0],
                on_ready=_do_capture,
            )

    @staticmethod
    def _split_sdf(text: str) -> list[str]:
        if not text:
            return []
        blocks: list[str] = []
        current: list[str] = []
        for line in text.splitlines(keepends=True):
            current.append(line)
            if line.startswith("$$$$"):
                blocks.append("".join(current))
                current = []
        if current and any(s.strip() for s in current):
            blocks.append("".join(current))
        return blocks

    def _on_pose_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows or not self._poses_sdf_blocks:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._poses_sdf_blocks):
            if self._pdb_path:
                self._viewer.load_receptor(self._pdb_path)
            self._viewer.load_ligand_pose(self._poses_sdf_blocks[idx])

    # --- exports -------------------------------------------------------
    def _export_sdf(self) -> None:
        if self._result is None:
            return
        src = Path(self._result.poses_sdf)
        if not src.exists():
            QMessageBox.warning(self, "导出 SDF", "SDF 文件不存在。")
            return
        dest, _ = QFileDialog.getSaveFileName(self, t("results.export_sdf"), "poses.sdf", "SDF (*.sdf)")
        if dest:
            shutil.copy2(src, dest)

    def _export_pdb(self) -> None:
        if self._result is None:
            return
        src = Path(self._result.poses_pdbqt)
        if not src.exists():
            QMessageBox.warning(self, "导出 PDB", "PDBQT 文件不存在。")
            return
        dest, _ = QFileDialog.getSaveFileName(self, t("results.export_pdb"), "poses.pdbqt",
                                              "PDBQT (*.pdbqt);;PDB (*.pdb)")
        if dest:
            shutil.copy2(src, dest)

    def _export_pdf(self) -> None:
        if self._result is None:
            return
        from dockmeow.core.report import generate_report

        dest, _ = QFileDialog.getSaveFileName(self, t("results.export_pdf"),
                                              "report.pdf", "PDF (*.pdf)")
        if not dest:
            return

        def _generate(screenshot: Path | None) -> None:
            try:
                generate_report(
                    self._receptor_info,
                    self._ligand_info,
                    self._result,
                    Path(dest),
                    screenshot_path=screenshot if screenshot and screenshot.exists() else None,
                )
                QMessageBox.information(self, "PDF", f"已生成：{dest}")
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "PDF", f"PDF 生成失败：{e}")

        # Fast path: reuse the pre-captured screenshot taken when results loaded.
        if self._auto_screenshot and self._auto_screenshot.exists():
            _generate(self._auto_screenshot)
            return

        # Slow path: reload best pose using callback chain — no fixed timer.
        tmp_png = Path(tempfile.mkstemp(suffix=".png")[1])

        def _on_grab(path: Path) -> None:
            _generate(path)

        if self._pdb_path and self._poses_sdf_blocks:
            def _do_capture_slow() -> None:
                QTimer.singleShot(
                    50, lambda: self._viewer.capture_png(tmp_png, callback=_on_grab)
                )
            self._viewer.load_best_pose_for_export(
                self._pdb_path,
                self._poses_sdf_blocks[0],
                on_ready=_do_capture_slow,
            )
        else:
            self._viewer.capture_png(tmp_png, callback=_on_grab)
