"""Step 5 — Docking execution page."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dockmeow.core.docking import DockingConfig
from dockmeow.ui.i18n import t
from dockmeow.ui.widgets.log_console import LogConsole
from dockmeow.workers.docking_worker import DockingWorker


class _CircularProgress(QWidget):
    """Custom-painted ring progress widget."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._value = 0
        self.setMinimumSize(180, 180)

    def setValue(self, v: int) -> None:  # noqa: N802
        self._value = max(0, min(100, int(v)))
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)

        # Track
        pen = QPen(QColor("#313244"), 10)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        # Progress arc
        pen = QPen(QColor("#7C9EF8"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        span = int(-self._value * 360 / 100 * 16)
        p.drawArc(rect, 90 * 16, span)

        # Centre text
        font = QFont()
        font.setPointSize(28)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#CDD6F4"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._value}%")
        p.end()


class RunPage(QWidget):
    """Run docking + show progress, stage, log."""

    run_finished = Signal(object)  # DockingResult

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: DockingWorker | None = None
        self._start_time: float = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        title = QLabel(t("run.title"))
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        outer.addWidget(title)

        # progress + stage row
        top = QHBoxLayout()
        self._progress = _CircularProgress()
        top.addWidget(self._progress, 0, Qt.AlignmentFlag.AlignCenter)

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

        self._log = LogConsole()
        outer.addWidget(self._log, 1)

    # ------------------------------------------------------------------
    def start(self, config: DockingConfig) -> None:
        self._log.clear_log()
        self._progress.setValue(0)
        self._stage_label.setText(t("run.status_docking"))
        self._cancel_btn.setEnabled(True)
        self._start_time = time.time()
        self._log.append_line(f"[start] exhaustiveness={config.exhaustiveness} "
                              f"num_modes={config.num_modes}")

        self._worker = DockingWorker(config)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._log.append_line("[cancel] 用户请求取消…")
            self._stage_label.setText(t("run.cancelled"))
            self._cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, pct: int, msg: str) -> None:
        self._progress.setValue(pct)
        self._stage_label.setText(msg or stage)
        self._log.append_line(f"[{stage}] {pct}% {msg}")

    def _on_done(self, result) -> None:
        elapsed = time.time() - self._start_time
        self._progress.setValue(100)
        self._stage_label.setText(t("run.completed"))
        self._cancel_btn.setEnabled(False)
        self._log.append_line(f"[done] runtime={elapsed:.1f}s "
                              f"poses={len(getattr(result, 'scores', []) or [])}")
        self.run_finished.emit(result)

    def _on_failed(self, user_message: str, suggestion: str) -> None:
        self._stage_label.setText(user_message)
        self._stage_label.setStyleSheet("color: #F38BA8;")
        self._cancel_btn.setEnabled(False)
        self._log.append_line(f"[fail] {user_message}  {suggestion}")
