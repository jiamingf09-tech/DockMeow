"""Step 6 — Results page."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
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
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # ---- left: viewer + Ray toolbar
        self._viewer_host = QWidget()
        self._viewer_host.setMinimumWidth(520)
        self._viewer_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
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
        right.setMinimumWidth(360)
        right.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        rl = QVBoxLayout(right)

        self._pose_list = QListWidget()
        self._pose_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._pose_list.setWordWrap(True)
        self._pose_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._pose_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._pose_list.setUniformItemSizes(False)
        self._pose_list.currentRowChanged.connect(self._on_pose_changed)
        rl.addWidget(self._pose_list, 1)

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

        # ---- PyMOL integration -------------------------------------------
        pymol_group = QGroupBox(t("results.pymol_group"))
        pg = QGridLayout(pymol_group)
        pg.setContentsMargins(10, 8, 10, 10)
        pg.setHorizontalSpacing(6)

        self._pymol_path_edit = QLineEdit()
        self._pymol_path_edit.setPlaceholderText(t("results.pymol_path_hint"))
        self._pymol_path_edit.setClearButtonEnabled(True)
        self._pymol_path_edit.editingFinished.connect(self._save_pymol_path)

        self._pymol_browse_btn = QPushButton(t("results.pymol_browse"))
        self._pymol_browse_btn.setToolTip(t("results.pymol_browse_tip"))
        self._pymol_browse_btn.clicked.connect(self._on_pymol_browse)

        self._pymol_auto_btn = QPushButton(t("results.pymol_auto"))
        self._pymol_auto_btn.setToolTip(t("results.pymol_auto_tip"))
        self._pymol_auto_btn.clicked.connect(self._on_pymol_auto)

        self._pymol_import_btn = QPushButton(t("results.pymol_import"))
        self._pymol_import_btn.setToolTip(t("results.pymol_import_tip"))
        self._pymol_import_btn.clicked.connect(self._on_pymol_import)

        pg.addWidget(QLabel(t("results.pymol_path_label")), 0, 0)
        pg.addWidget(self._pymol_path_edit, 0, 1)
        pg.addWidget(self._pymol_browse_btn, 0, 2)
        pg.addWidget(self._pymol_auto_btn, 0, 3)
        pg.addWidget(self._pymol_import_btn, 1, 0, 1, 4)
        pg.setColumnStretch(1, 1)
        rl.addWidget(pymol_group)

        # Restore the previously chosen PyMOL path, if any.
        saved_pymol = self._load_pymol_path()
        if saved_pymol:
            self._pymol_path_edit.setText(saved_pymol)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([720, 430])
        self._splitter = splitter

        # Hide Qt WebEngine's cold-start white frame and overlap viewer startup
        # with the earlier workflow steps.
        QTimer.singleShot(0, self._ensure_viewer)

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
        # Load the 3D only once the page is actually visible and laid out, so the
        # WebGL canvas has its real on-screen size.  Loading while hidden made
        # the molecule render stretched (wrong aspect) or not appear until a
        # pose was double-clicked.
        QTimer.singleShot(0, self._load_into_viewer)

    def _load_into_viewer(self) -> None:
        """(Re)load the receptor + current pose into a correctly-sized viewer."""
        if self._pdb_path and self._poses_sdf_blocks:
            idx = self._pose_list.currentRow()
            idx = 0 if idx < 0 else min(idx, len(self._poses_sdf_blocks) - 1)
            viewer = self._ensure_viewer()
            viewer.load_result_pose(self._pdb_path, self._poses_sdf_blocks[idx])
            # Refit after layout settles to lock in the correct aspect + zoom.
            QTimer.singleShot(80, viewer.refit)
            QTimer.singleShot(320, viewer.refit)
        elif self._pdb_path:
            viewer = self._ensure_viewer()
            viewer.load_receptor(self._pdb_path)
            QTimer.singleShot(80, viewer.refit)
            QTimer.singleShot(320, viewer.refit)

    def set_context(self, receptor_info, ligand_info, pdb_path: Path) -> None:
        self._receptor_info = receptor_info
        self._ligand_info = ligand_info
        self._pdb_path = Path(pdb_path) if pdb_path else None
        # Defer actual viewer loading to on_page_enter()/_load_into_viewer() so
        # it runs when the page is visible and sized.  Load now only if we're
        # already the visible page.
        if self._pdb_path and self.isVisible():
            self._load_into_viewer()

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

        self._pose_list.blockSignals(True)
        self._pose_list.clear()
        for i, s in enumerate(scores):
            lb = f"{rmsd_lb[i]:.2f}" if i < len(rmsd_lb) else "-"
            ub = f"{rmsd_ub[i]:.2f}" if i < len(rmsd_ub) else "-"
            self._pose_list.addItem(
                QListWidgetItem(
                    f"{t('results.pose')} {i + 1}    "
                    f"{t('results.affinity')}: {s:.2f}\n"
                    f"{t('results.rmsd_lb')}: {lb}    "
                    f"{t('results.rmsd_ub')}: {ub}"
                )
            )
        if scores:
            self._pose_list.setCurrentRow(0)
        self._pose_list.blockSignals(False)

        # Viewer loading is deferred to on_page_enter(); load now only if the
        # results page is already the visible one.
        if scores and self._pdb_path and self._poses_sdf_blocks and self.isVisible():
            self._load_into_viewer()

    # --- Ray / background helpers -----------------------------------------
    def _update_bg_color_btn(self) -> None:
        """Repaint the background-color swatch button."""
        c = self._ray_bg_color
        # Pick contrasting border so the button is visible on any theme
        lum = 0.299 * int(c[1:3], 16) + 0.587 * int(c[3:5], 16) + 0.114 * int(c[5:7], 16)
        border = "#888888" if lum > 128 else "#AAAAAA"
        self._bg_color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c}; "
            f"border: 1px solid {border}; border-radius: 3px; }}"
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

    # --- PyMOL integration ------------------------------------------------
    @staticmethod
    def _settings() -> QSettings:
        return QSettings("DockMeow", "DockMeow")

    def _load_pymol_path(self) -> str:
        return str(self._settings().value("pymol/executable", "", type=str) or "")

    def _save_pymol_path(self) -> None:
        self._settings().setValue("pymol/executable", self._pymol_path_edit.text().strip())

    def _on_pymol_browse(self) -> None:
        """Pick the PyMOL executable manually."""
        if sys.platform == "win32":
            filt = "PyMOL (PyMOLWin.exe pymol.exe);;可执行文件 (*.exe);;所有文件 (*)"
        else:
            filt = "所有文件 (*)"
        start = self._pymol_path_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, t("results.pymol_browse"), start, filt
        )
        if path:
            self._pymol_path_edit.setText(path)
            self._save_pymol_path()

    def _on_pymol_auto(self) -> None:
        """Auto-search common locations for a PyMOL executable."""
        from dockmeow.core.pymol_export import find_pymol

        found = find_pymol()
        if found:
            self._pymol_path_edit.setText(str(found))
            self._save_pymol_path()
            QMessageBox.information(
                self, t("results.pymol_group"), t("results.pymol_found", path=str(found))
            )
        else:
            QMessageBox.warning(
                self, t("results.pymol_group"), t("results.pymol_not_found")
            )

    def _on_pymol_import(self) -> None:
        """Open the receptor + every pose in PyMOL (one state per conformation)."""
        from dockmeow.core import pymol_export

        if self._result is None or not self._poses_sdf_blocks:
            QMessageBox.information(
                self, t("results.pymol_import"), t("results.pymol_no_result")
            )
            return
        if not self._pdb_path or not Path(self._pdb_path).is_file():
            QMessageBox.warning(
                self, t("results.pymol_import"), t("results.pymol_no_receptor")
            )
            return

        # Resolve the PyMOL executable: prefer the field, else auto-search.
        exe_text = self._pymol_path_edit.text().strip()
        if exe_text:
            if not pymol_export.is_valid_pymol(exe_text):
                QMessageBox.warning(
                    self, t("results.pymol_import"),
                    t("results.pymol_bad_path", path=exe_text),
                )
                return
            exe: Path | None = Path(exe_text)
        else:
            exe = pymol_export.find_pymol()
            if exe is None:
                QMessageBox.warning(
                    self, t("results.pymol_import"), t("results.pymol_not_found")
                )
                return
            self._pymol_path_edit.setText(str(exe))
            self._save_pymol_path()

        # Resolve the poses SDF — prefer the on-disk file, else rebuild it.
        poses_sdf = Path(self._result.poses_sdf)
        if not poses_sdf.is_file() or poses_sdf.stat().st_size == 0:
            tmp = Path(tempfile.mkstemp(suffix=".sdf")[1])
            tmp.write_text("".join(self._poses_sdf_blocks), encoding="utf-8")
            poses_sdf = tmp

        try:
            pymol_export.export_to_pymol(Path(self._pdb_path), poses_sdf, exe)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self, t("results.pymol_import"),
                t("results.pymol_launch_failed", err=str(exc)),
            )
            return

        QMessageBox.information(
            self, t("results.pymol_import"),
            t("results.pymol_launched", n=str(len(self._poses_sdf_blocks))),
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
        if not self._poses_sdf_blocks:
            return
        idx = self._pose_list.currentRow()
        if 0 <= idx < len(self._poses_sdf_blocks) and self._pdb_path:
            viewer = self._ensure_viewer()
            viewer.load_result_pose(self._pdb_path, self._poses_sdf_blocks[idx])
            QTimer.singleShot(60, viewer.refit)

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
