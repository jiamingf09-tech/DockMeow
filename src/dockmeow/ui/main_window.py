"""Main application window.

Layout::

    ┌──────────────────────────────────────────┐
    │  Menu bar (文件 / 帮助 / 关于)              │
    ├────────────┬─────────────────────────────┤
    │  Step nav  │  QStackedWidget (pages)      │
    │  (left)    │                             │
    ├────────────┴─────────────────────────────┤
    │  status bar (license info / version)     │
    └──────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.docking import DockingConfig
from dockmeow.ui.dialogs.about_dialog import AboutDialog
from dockmeow.ui.dialogs.activation_dialog import ActivationDialog
from dockmeow.ui.i18n import t
from dockmeow.utils.paths import resource_path
from dockmeow.ui.pages.page_ligand import LigandPage
from dockmeow.ui.pages.page_params import ParamsPage
from dockmeow.ui.pages.page_pocket import PocketPage
from dockmeow.ui.pages.page_receptor import ReceptorPage
from dockmeow.ui.pages.page_results import ResultsPage
from dockmeow.ui.pages.page_run import RunPage
from dockmeow.version import __version__


class MainWindow(QMainWindow):
    """Top-level window; wires together all pages and the license layer."""

    _STEPS = ["receptor", "ligand", "pocket", "params", "run", "results"]

    def __init__(self, license_data: dict | None = None) -> None:
        super().__init__()
        self._license_data = license_data
        self._receptor_info = None
        self._pdb_path: Path | None = None
        self._ligand_info = None
        self._pocket = None
        self._params: dict | None = None
        self._docking_result = None

        self._build_ui()
        self._connect_signals()
        self._update_license_status()
        self._go_to_page(0)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle(t("app.title"))
        self.resize(1200, 800)

        # App icon (shows in Dock, window title bar, Alt+Tab switcher)
        icon_path = resource_path("ui/resources/icons/logo_256.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Menu bar
        mb = self.menuBar()
        file_menu = mb.addMenu(t("menu.file"))
        act_activate = file_menu.addAction(t("menu.activate"))
        act_activate.triggered.connect(self._open_activation)
        file_menu.addSeparator()
        act_exit = file_menu.addAction(t("menu.exit"))
        act_exit.triggered.connect(self.close)

        help_menu = mb.addMenu(t("menu.help"))
        act_about = help_menu.addAction(t("menu.about"))
        act_about.triggered.connect(self._open_about)

        # Central widget
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setFixedWidth(150)
        self._nav.setObjectName("StepNav")
        for step in self._STEPS:
            QListWidgetItem(t(f"nav.{step}"), self._nav)
        self._nav.currentRowChanged.connect(self._on_nav_changed)

        self._stack = QStackedWidget()
        self._receptor_page = ReceptorPage()
        self._ligand_page = LigandPage()
        self._pocket_page = PocketPage()
        self._params_page = ParamsPage()
        self._run_page = RunPage()
        self._results_page = ResultsPage()
        for p in (
            self._receptor_page,
            self._ligand_page,
            self._pocket_page,
            self._params_page,
            self._run_page,
            self._results_page,
        ):
            self._stack.addWidget(p)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._stack, 1)

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(12, 8, 12, 8)
        nav_row.addStretch(1)
        self._prev_btn = QPushButton(t("nav.prev"))
        self._next_btn = QPushButton(t("nav.next"))
        self._next_btn.setObjectName("PrimaryButton")
        self._prev_btn.clicked.connect(self._on_prev_clicked)
        self._next_btn.clicked.connect(self._on_next_clicked)
        nav_row.addWidget(self._prev_btn)
        nav_row.addWidget(self._next_btn)
        content_layout.addLayout(nav_row)

        layout.addWidget(self._nav)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        # Status bar
        self._status_label = QLabel("")
        self.statusBar().addWidget(self._status_label, 1)
        self.statusBar().addPermanentWidget(QLabel(f"v{__version__}"))

    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._receptor_page.receptor_ready.connect(self._on_receptor_ready)
        self._ligand_page.ligand_ready.connect(self._on_ligand_ready)
        self._params_page.params_ready.connect(self._on_params_ready)
        self._run_page.run_finished.connect(self._on_run_finished)
        self._results_page.new_docking_requested.connect(self._reset_to_start)

    # --- nav -----------------------------------------------------------
    def _go_to_page(self, idx: int) -> None:
        idx = max(0, min(idx, self._stack.count() - 1))
        if idx == 2:
            self._prepare_pocket_page()
        self._stack.setCurrentIndex(idx)
        self._nav.blockSignals(True)
        self._nav.setCurrentRow(idx)
        self._nav.blockSignals(False)
        max_unlocked = self._max_unlocked_page()
        for i in range(self._nav.count()):
            item = self._nav.item(i)
            flags = item.flags()
            if i <= max_unlocked:
                item.setFlags(flags | Qt.ItemFlag.ItemIsEnabled)
            else:
                item.setFlags(flags & ~Qt.ItemFlag.ItemIsEnabled)
        self._update_next_button_enabled()

    def _on_nav_changed(self, idx: int) -> None:
        if idx < 0:
            return
        if idx <= self._max_unlocked_page():
            self._go_to_page(idx)

    def _max_unlocked_page(self) -> int:
        if self._docking_result is not None:
            return 5
        if self._params is not None:
            return 4
        if self._pocket is not None:
            return 3
        if self._ligand_info is not None:
            return 2
        if self._receptor_info is not None:
            return 1
        return 0

    def _update_next_button_enabled(self) -> None:
        idx = self._stack.currentIndex()
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setVisible(idx in (0, 1, 2))
        if idx == 0:
            self._next_btn.setEnabled(self._receptor_info is not None)
        elif idx == 1:
            self._next_btn.setEnabled(self._ligand_info is not None)
        elif idx == 2:
            self._next_btn.setEnabled(
                self._receptor_info is not None and self._ligand_info is not None
            )
        else:
            self._next_btn.setEnabled(False)

    def _on_prev_clicked(self) -> None:
        self._go_to_page(self._stack.currentIndex() - 1)

    def _on_next_clicked(self) -> None:
        idx = self._stack.currentIndex()
        if idx == 0:
            if self._receptor_info is None:
                QMessageBox.warning(self, t("app.title"), "请先完成受体准备。")
                return
            self._go_to_page(1)
        elif idx == 1:
            if self._ligand_info is None:
                QMessageBox.warning(self, t("app.title"), "请先完成配体准备。")
                return
            self._prepare_pocket_page()
            self._go_to_page(2)
        elif idx == 2:
            pocket = self._pocket_page.get_selected_pocket()
            if pocket is None:
                QMessageBox.warning(self, t("app.title"), "请先选择或自定义一个口袋。")
                return
            self._pocket = pocket
            self._go_to_page(3)

    def _prepare_pocket_page(self) -> None:
        if self._receptor_info is not None and self._pdb_path is not None:
            self._pocket_page.set_receptor(self._receptor_info, self._pdb_path)

    # --- page handlers -------------------------------------------------
    def _on_receptor_ready(self, receptor_info, pdb_path) -> None:
        self._receptor_info = receptor_info
        self._pdb_path = Path(pdb_path) if pdb_path else None
        self._update_next_button_enabled()

    def _on_ligand_ready(self, ligand_info) -> None:
        self._ligand_info = ligand_info
        self._prepare_pocket_page()
        self._update_next_button_enabled()

    def _on_params_ready(self, params: dict) -> None:
        self._params = params
        if not self._can_run():
            QMessageBox.warning(self, t("app.title"),
                                "请先完成受体、配体、口袋的准备。")
            return

        cfg = DockingConfig(
            receptor_pdbqt=self._receptor_info.pdbqt_path,
            ligand_pdbqt=self._ligand_info.pdbqt_path,
            center=self._pocket.center,
            size=self._pocket.size,
            exhaustiveness=int(params["exhaustiveness"]),
            num_modes=int(params["num_modes"]),
            energy_range=float(params["energy_range"]),
            seed=int(params["seed"]),
        )
        self._go_to_page(4)
        self._run_page.start(cfg)

    def _on_run_finished(self, result) -> None:
        self._docking_result = result
        self._results_page.set_context(
            self._receptor_info, self._ligand_info, self._pdb_path
        )
        self._results_page.set_result(result)
        self._go_to_page(5)

    def _reset_to_start(self) -> None:
        self._go_to_page(0)

    def _can_run(self) -> bool:
        return all(
            x is not None
            for x in (self._receptor_info, self._ligand_info, self._pocket)
        )

    # --- license / dialogs --------------------------------------------
    def _open_activation(self) -> None:
        dlg = ActivationDialog(self)
        if dlg.exec() and dlg.accepted_data is not None:
            self._license_data = dlg.accepted_data
            self._update_license_status()

    def _open_about(self) -> None:
        AboutDialog(self._license_data, self).exec()

    def _update_license_status(self) -> None:
        if self._license_data:
            email = str(self._license_data.get("email", ""))
            self._status_label.setText(t("status.activated", email=email))
        else:
            self._status_label.setText(t("status.not_activated"))
