"""QThread worker for AutoDock Vina docking execution."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from dockmeow.core.docking import DockingConfig
from dockmeow.core.exceptions import DockMeowError


class DockingWorker(QThread):
    """Run docking in a background thread; supports cancellation."""

    progress = Signal(str, int, str)   # stage, percent, message
    finished_ok = Signal(object)       # DockingResult
    failed = Signal(str, str)          # user_message, suggestion

    def __init__(self, config: DockingConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        """Thread entry point — calls core.docking.run_docking with interrupt check."""
        from dockmeow.core.docking import run_docking

        try:
            def cb(stage: str, pct: int, msg: str) -> None:
                if self.isInterruptionRequested():
                    raise InterruptedError()
                self.progress.emit(stage, int(pct), msg)

            result = run_docking(self.config, progress_callback=cb)
            self.finished_ok.emit(result)
        except InterruptedError:
            return
        except DockMeowError as e:
            self.failed.emit(e.user_message, getattr(e, "suggestion", "") or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"对接失败：{e}", "请检查参数与输入文件后重试。")
