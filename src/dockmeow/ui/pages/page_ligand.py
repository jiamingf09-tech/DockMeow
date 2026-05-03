"""Step 2 — Ligand (small molecule) input page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.drop_zone import DropZone
from dockmeow.utils.paths import user_workspace
from dockmeow.workers.prepare_worker import PrepareLigandWorker


_EXAMPLES: list[tuple[str, str]] = [
    ("阿司匹林", "CC(=O)Oc1ccccc1C(O)=O"),
    ("布洛芬", "CC(C)Cc1ccc(C(C)C(O)=O)cc1"),
    (
        "甲氨蝶呤",
        "CN(Cc1cnc2nc(N)nc(N)c2n1)c1ccc(C(=O)N[C@@H](CCC(O)=O)C(O)=O)cc1",
    ),
    (
        "ATP",
        "c1nc(N)c2ncnc2n1[C@@H]1O[C@H](COP(=O)(O)OP(=O)(O)OP(=O)(O)O)[C@@H](O)[C@H]1O",
    ),
]


class LigandPage(QWidget):
    """Tabbed input — SMILES / file / examples — with info panel."""

    ligand_ready = Signal(object)  # LigandInfo

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: PrepareLigandWorker | None = None
        self._ligand_info = None

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---- left: tabs
        left = QWidget()
        ll = QVBoxLayout(left)

        self._tabs = QTabWidget()
        ll.addWidget(self._tabs, 1)

        # SMILES tab
        smi_tab = QWidget()
        sl = QVBoxLayout(smi_tab)
        sl.addWidget(QLabel(t("ligand.smiles_label")))
        self._smiles_edit = QLineEdit()
        self._smiles_edit.setPlaceholderText("CCO")
        sl.addWidget(self._smiles_edit)
        smi_btn = QPushButton(t("ligand.parse_btn"))
        smi_btn.clicked.connect(self._on_parse_smiles)
        sl.addWidget(smi_btn)
        sl.addStretch(1)
        self._tabs.addTab(smi_tab, t("ligand.tab_smiles"))

        # File tab
        file_tab = QWidget()
        fl = QVBoxLayout(file_tab)
        self._file_drop = DropZone(
            t("ligand.file_hint"),
            ["sdf", "mol", "mol2"],
            self,
            file_dialog_filter="Molecule (*.sdf *.mol *.mol2);;All files (*)",
        )
        self._file_drop.file_dropped.connect(self._on_file)
        fl.addWidget(self._file_drop)
        fl.addStretch(1)
        self._tabs.addTab(file_tab, t("ligand.tab_file"))

        # Examples tab
        ex_tab = QWidget()
        el = QVBoxLayout(ex_tab)
        self._examples_list = QListWidget()
        for name, smi in _EXAMPLES:
            item = QListWidgetItem(f"{name}    {smi}")
            item.setData(0x0100 + 1, (name, smi))  # custom data
            self._examples_list.addItem(item)
        self._examples_list.itemDoubleClicked.connect(self._on_example_pick)
        el.addWidget(self._examples_list, 1)
        ex_btn = QPushButton(t("ligand.parse_btn"))
        ex_btn.clicked.connect(self._on_example_btn)
        el.addWidget(ex_btn)
        self._tabs.addTab(ex_tab, t("ligand.tab_examples"))

        root.addWidget(left, 2)

        # ---- right: info
        right = QWidget()
        rl = QVBoxLayout(right)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        rl.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        rl.addWidget(self._status)

        self._atoms_lbl = QLabel(t("ligand.info_atoms", n="-"))
        self._rot_lbl = QLabel(t("ligand.info_rotbonds", n="-"))
        self._smi_lbl = QLabel("SMILES: -")
        self._smi_lbl.setWordWrap(True)
        rl.addWidget(self._atoms_lbl)
        rl.addWidget(self._rot_lbl)
        rl.addWidget(self._smi_lbl)
        rl.addStretch(1)

        root.addWidget(right, 1)

    # ------------------------------------------------------------------
    def _start_smiles(self, smiles: str, name: str) -> None:
        self._begin()
        work_dir = user_workspace() / "ligand"
        work_dir.mkdir(parents=True, exist_ok=True)
        self._worker = PrepareLigandWorker(work_dir, smiles=smiles, name=name)
        self._wire_worker()
        self._worker.start()

    def _start_file(self, path: Path) -> None:
        self._begin()
        work_dir = user_workspace() / "ligand"
        work_dir.mkdir(parents=True, exist_ok=True)
        self._worker = PrepareLigandWorker(work_dir, file_path=path)
        self._wire_worker()
        self._worker.start()

    def _begin(self) -> None:
        self._status.setText(t("ligand.preparing"))
        self._status.setStyleSheet("")
        self._progress.setValue(0)
        self._progress.setVisible(True)

    def _wire_worker(self) -> None:
        assert self._worker is not None
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)

    # --- handlers ------------------------------------------------------
    def _on_parse_smiles(self) -> None:
        smi = self._smiles_edit.text().strip()
        if not smi:
            return
        self._start_smiles(smi, "ligand")

    def _on_file(self, path: Path) -> None:
        self._start_file(path)

    def _on_example_pick(self, item: QListWidgetItem) -> None:
        data = item.data(0x0100 + 1)
        if data:
            name, smi = data
            self._start_smiles(smi, name)

    def _on_example_btn(self) -> None:
        item = self._examples_list.currentItem()
        if item:
            self._on_example_pick(item)

    def _on_progress(self, stage: str, pct: int, msg: str) -> None:
        self._progress.setValue(int(pct))
        self._status.setText(msg or stage)

    def _on_done(self, info) -> None:
        self._ligand_info = info
        self._progress.setVisible(False)
        self._status.setText("配体准备完成。")
        self._atoms_lbl.setText(t("ligand.info_atoms", n=str(info.n_atoms)))
        self._rot_lbl.setText(t("ligand.info_rotbonds", n=str(info.n_rotatable)))
        self._smi_lbl.setText(f"SMILES: {info.smiles}")
        self.ligand_ready.emit(info)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._progress.setVisible(False)
        self._status.setText(f"{user_message}\n{suggestion}")
        self._status.setStyleSheet("color: #F38BA8;")
