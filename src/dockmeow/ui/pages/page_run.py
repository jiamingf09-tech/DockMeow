"""Step 5 — Docking execution page."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.docking import DockingConfig
from dockmeow.ui.i18n import t
from dockmeow.workers.docking_worker import DockingWorker


class RunPage(QWidget):
    """Run docking + show progress, stage, log."""

    run_finished = Signal(object)  # DockingResult

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: DockingWorker | None = None
        self._start_time: float = 0.0
        self._log_lines: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        title = QLabel(t("run.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        outer.addWidget(title)

        # progress + stage row
        top = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setMinimumHeight(24)
        self._progress.setFormat("%p%")
        top.addWidget(self._progress, 1)

        right = QVBoxLayout()
        self._stage_label = QLabel(t("run.status_docking"))
        self._stage_label.setStyleSheet("font-size: 14px;")
        right.addWidget(self._stage_label)
        right.addStretch(1)
        self._cancel_btn = QPushButton(t("run.cancel_btn"))
        self._cancel_btn.setObjectName("DangerButton")
        self._cancel_btn.clicked.connect(self._cancel)
        right.addWidget(self._cancel_btn)
        top.addLayout(right, 1)

        outer.addLayout(top)

        self._log = QLabel("")
        self._log.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._log.setWordWrap(True)
        self._log.setStyleSheet(
            "font-family: Menlo, Monaco, monospace; font-size: 11px; "
            "padding: 10px; border: 1px solid #313244; border-radius: 4px;"
        )
        outer.addWidget(self._log, 1)

    # ------------------------------------------------------------------
    def start(self, config: DockingConfig) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # a docking run is already in progress
        self._clear_log()
        self._progress.setValue(0)
        self._stage_label.setText(t("run.status_docking"))
        self._cancel_btn.setEnabled(True)
        self._start_time = time.time()
        self._append_log(
            f"[start] exhaustiveness={config.exhaustiveness} "
            f"num_modes={config.num_modes}"
        )

        self._worker = DockingWorker(config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._append_log("[cancel] 用户请求取消…")
            self._stage_label.setText(t("run.cancelled"))
            self._cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, pct: int, msg: str) -> None:
        self._progress.setValue(pct)
        self._stage_label.setText(msg or stage)
        self._append_log(f"[{stage}] {pct}% {msg}")

    def _on_done(self, result) -> None:
        elapsed = time.time() - self._start_time
        self._progress.setValue(100)
        self._stage_label.setText(t("run.completed"))
        self._cancel_btn.setEnabled(False)
        self._append_log(
            f"[done] runtime={elapsed:.1f}s "
            f"poses={len(getattr(result, 'scores', []) or [])}"
        )
        self.run_finished.emit(result)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._stage_label.setText(user_message)
        self._stage_label.setStyleSheet("color: #F38BA8;")
        self._cancel_btn.setEnabled(False)
        self._append_log(f"[fail] {user_message}  {suggestion}")

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self._log.setText("")

    def _append_log(self, text: str) -> None:
        self._log_lines.append(text)
        self._log_lines = self._log_lines[-14:]
        self._log.setText("\n".join(self._log_lines))
