"""QThread worker for binding pocket detection."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dockmeow.core.exceptions import DockMeowError
from dockmeow.core.pocket import detect_pockets
from dockmeow.core.receptor import ReceptorInfo


class PocketWorker(QThread):
    """Run fpocket / co-crystal detection in a background thread."""

    progress = Signal(str, int, str)
    finished_ok = Signal(object)    # list[Pocket]
    failed = Signal(str, str)

    def __init__(self, receptor_info: ReceptorInfo, pdb_path: Path) -> None:
        super().__init__()
        self._receptor_info = receptor_info
        self._pdb_path = Path(pdb_path)

    def run(self) -> None:
        try:
            self.progress.emit("pocket", 10, "检测结合口袋…")
            original_pdb = (
                getattr(self._receptor_info, "original_pdb_path", None)
                or self._pdb_path
            )
            pockets = detect_pockets(self._receptor_info, original_pdb)
            self.progress.emit("pocket", 100, "口袋检测完成")
            self.finished_ok.emit(pockets)
        except DockMeowError as e:
            self.failed.emit(e.user_message, getattr(e, "suggestion", "") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"口袋检测失败：{e}", "可使用全蛋白盲对接继续。")
