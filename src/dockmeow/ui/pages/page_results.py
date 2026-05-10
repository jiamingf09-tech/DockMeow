"""Step 6 — Results page."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
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

    # ---- default viewer background color (matches viewer_3d.py HTML)
    _DEFAULT_BG = "#1E1E2E"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._receptor_info = None
        self._ligand_info = None
        self._result = None
        self._pdb_path: Path | None = None
        self._poses_sdf_blocks: list[str] = []
        self._auto_screenshot: Path | None = None  # pre-captured for PDF export
        self._viewer: Viewer3D | None = None
        self._ray_bg_color: str = self._DEFAULT_BG  # current Ray background color

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ---- left: viewer + Ray toolbar
        self._viewer_host = QWidget()
        self._viewer_layout = QVBoxLayout(self._viewer_host)
        self._viewer_layout.setContentsMargins(0, 0, 0, 0)
        self._viewer_layout.setSpacing(4)

        # Ray toolbar (above the viewer placeholder / viewer widget)
        ray_bar = QHBoxLayout()
        ray_bar.setContentsMargins(0, 0, 0, 0)
        self._ray_btn = QPushButton(t("results.ray_btn"))
        self._ray_btn.setToolTip("截取当前 3D 视图并保存为 PNG 图片")
        self._ray_btn.clicked.connect(self._on_ray_capture)
        ray_bar.addWidget(self._ray_btn)
        ray_bar.addSpacing(8)
        ray_bar.addWidget(QLabel(t("results.ray_bg_btn") + "："))
        self._bg_color_btn = QPushButton()
        self._bg_color_btn.setFixedSize(28, 22)
        self._bg_color_btn.setToolTip("选择 Ray 截图的背景颜色")
        self._bg_color_btn.clicked.connect(self._on_pick_bg_color)
        self._update_bg_color_btn()
        ray_bar.addWidget(self._bg_color_btn)
        ray_bar.addStretch(1)
        self._viewer_layout.addLayout(ray_bar)

        self._viewer_placeholder = QLabel("3D 预览将在有对接结果后初始化。")
        self._viewer_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewer_placeholder.setWordWrap(True)
        self._viewer_layout.addWidget(self._viewer_placeholder, 1)
        splitter.addWidget(self._viewer_host)

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
    def _ensure_viewer(self) -> Viewer3D:
        if self._viewer is None:
            self._viewer = Viewer3D()
            self._viewer_placeholder.hide()
            self._viewer_layout.addWidget(self._viewer, 1)
            # Apply current background choice to the newly created viewer
            if self._ray_bg_color != self._DEFAULT_BG:
                self._viewer.set_background_color(self._ray_bg_color)
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
        if self._pdb_path is None:
            return
        rows = self._table.selectionModel().selectedRows()
        idx = rows[0].row() if rows else 0
        if self._poses_sdf_blocks and 0 <= idx < len(self._poses_sdf_blocks):
            self._ensure_viewer().load_result_pose(
                self._pdb_path, self._poses_sdf_blocks[idx]
            )
        else:
            self._ensure_viewer().load_receptor(self._pdb_path)

    def set_context(self, receptor_info, ligand_info, pdb_path: Path) -> None:
        self._receptor_info = receptor_info
        self._ligand_info = ligand_info
        self._pdb_path = Path(pdb_path) if pdb_path else None
        if self._pdb_path:
            self._ensure_viewer().load_receptor(self._pdb_path)

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
                # loadBestPose render() fired; wait for GPU to flush several frames.
                # Extra headroom so on_page_enter (called by _go_to_page right after
                # set_result) doesn't overwrite this view before capture fires.
                QTimer.singleShot(
                    600, lambda: self._ensure_viewer().capture_png(_shot_path, callback=_auto_save)
                )

            self._ensure_viewer().load_best_pose_for_export(
                self._pdb_path,
                self._poses_sdf_blocks[0],
                on_ready=_do_capture,
            )

    # --- Ray / background helpers -----------------------------------------
    def _update_bg_color_btn(self) -> None:
        """Repaint the background-color swatch button."""
        c = self._ray_bg_color
        # Pick contrasting border so the button is visible on any theme
        lum = 0.299 * int(c[1:3], 16) + 0.587 * int(c[3:5], 16) + 0.114 * int(c[5:7], 16)
        border = "#888888" if lum > 128 else "#AAAAAA"
        self._bg_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c}; border: 1px solid {border}; border-radius: 3px; }}"
        )

    def _on_pick_bg_color(self) -> None:
        """Open colour dialog and apply the chosen background to the viewer."""
        initial = QColor(self._ray_bg_color)
        color = QColorDialog.getColor(initial, self, "选择 Ray 背景颜色")
        if not color.isValid():
            return
        self._ray_bg_color = color.name()  # '#RRGGBB'
        self._update_bg_color_btn()
        if self._viewer is not None:
            self._viewer.set_background_color(self._ray_bg_color)

    def _on_ray_capture(self) -> None:
        """Capture the current 3D view and save as PNG."""
        if self._viewer is None:
            QMessageBox.information(self, t("results.ray_btn"), "请先完成对接，再使用 Ray 截图。")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, t("results.ray_btn"), "dockmeow_view.png", "PNG 图片 (*.png)"
        )
        if not dest:
            return
        out_path = Path(dest)

        def _on_done(path: Path) -> None:
            if path.exists():
                QMessageBox.information(
                    self, t("results.ray_btn"),
                    t("results.ray_saved", path=str(path)),
                )
            else:
                QMessageBox.warning(
                    self, t("results.ray_btn"),
                    t("results.ray_failed", err="文件未生成"),
                )

        self._viewer.capture_png(out_path, callback=_on_done)

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
        if 0 <= idx < len(self._poses_sdf_blocks) and self._pdb_path:
            self._ensure_viewer().load_result_pose(
                self._pdb_path, self._poses_sdf_blocks[idx]
            )

    # --- exports -------------------------------------------------------
    def _export_sdf(self) -> None:
        if self._result is None:
            return
        src = Path(self._result.poses_sdf)
        if not src.exists():
            QMessageBox.warning(self, "导出 SDF", "SDF 文件不存在。")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, t("results.export_sdf"), "poses.sdf", "SDF (*.sdf)"
        )
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
                    50, lambda: self._ensure_viewer().capture_png(tmp_png, callback=_on_grab)
                )
            self._ensure_viewer().load_best_pose_for_export(
                self._pdb_path,
                self._poses_sdf_blocks[0],
                on_ready=_do_capture_slow,
            )
        else:
            self._ensure_viewer().capture_png(tmp_png, callback=_on_grab)
