"""QThread workers for receptor and ligand preparation.

Runs the synchronous core preparation routines off the GUI thread so the
window stays responsive and progress can be streamed via signals.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dockmeow.core.exceptions import DockMeowError
from dockmeow.core.ligand import (
    prepare_ligand_from_file,
    prepare_ligand_from_smiles,
)
from dockmeow.core.receptor import prepare_receptor


class PrepareReceptorWorker(QThread):
    """Prepare a receptor PDB in a background thread."""

    progress = Signal(str, int, str)   # stage, percent, message
    finished_ok = Signal(object)       # ReceptorInfo
    failed = Signal(str, str)          # user_message, suggestion

    def __init__(self, input_pdb: Path, work_dir: Path) -> None:
        super().__init__()
        self._input_pdb = Path(input_pdb)
        self._work_dir = Path(work_dir)

    def run(self) -> None:
        try:
            def cb(stage: str, pct: int, msg: str) -> None:
                self.progress.emit(stage, int(pct), msg)

            info = prepare_receptor(
                self._input_pdb, self._work_dir, progress_callback=cb
            )
            self.finished_ok.emit(info)
        except DockMeowError as e:
            self.failed.emit(e.user_message, getattr(e, "suggestion", "") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"受体准备失败：{e}", "请检查 PDB 文件是否完整。")


class PrepareLigandWorker(QThread):
    """Prepare a ligand from SMILES or a file in a background thread.

    Pass exactly one of ``smiles=`` (with optional ``name=``) or ``file_path=``.
    """

    progress = Signal(str, int, str)
    finished_ok = Signal(object)       # LigandInfo
    failed = Signal(str, str)

    def __init__(
        self,
        work_dir: Path,
        *,
        smiles: str | None = None,
        name: str | None = None,
        file_path: Path | None = None,
    ) -> None:
        super().__init__()
        if (smiles is None) == (file_path is None):
            raise ValueError("Pass exactly one of smiles= or file_path=")
        self._work_dir = Path(work_dir)
        self._smiles = smiles
        self._name = name or "ligand"
        self._file_path = Path(file_path) if file_path else None

    def run(self) -> None:
        try:
            def cb(stage: str, pct: int, msg: str) -> None:
                self.progress.emit(stage, int(pct), msg)

            if self._smiles is not None:
                info = prepare_ligand_from_smiles(
                    self._smiles, self._name, self._work_dir, progress_callback=cb
                )
            else:
                info = prepare_ligand_from_file(
                    self._file_path, self._work_dir, progress_callback=cb
                )
            self.finished_ok.emit(info)
        except DockMeowError as e:
            self.failed.emit(e.user_message, getattr(e, "suggestion", "") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"配体准备失败：{e}", "请检查输入是否为有效的 SMILES 或分子文件。")
