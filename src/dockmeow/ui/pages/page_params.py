"""Step 4 — Docking parameters page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dockmeow.ui.i18n import t

_SPEED_VALUES = [8, 16, 32, 64]
_SPEED_LABELS = [
    "params.speed_fast",
    "params.speed_standard",
    "params.speed_fine",
    "params.speed_ultra",
]
# rough relative time multipliers for the estimate
_SPEED_MINUTES = [0.5, 1.0, 2.0, 4.0]


class ParamsPage(QWidget):
    """Slider-based exhaustiveness picker + collapsible advanced section."""

    params_ready = Signal(dict)
    view_result_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel(t("params.exhaustiveness_label"))
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        outer.addWidget(title)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 3)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(1)
        self._slider.setTickInterval(1)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider.setValue(1)  # default 标准
        self._slider.valueChanged.connect(self._refresh_labels)
        outer.addWidget(self._slider)

        ticks = QHBoxLayout()
        for k in _SPEED_LABELS:
            lbl = QLabel(t(k))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ticks.addWidget(lbl, 1)
        outer.addLayout(ticks)

        self._estimate = QLabel("")
        self._estimate.setStyleSheet("color: #A6ADC8;")
        outer.addWidget(self._estimate)

        self._run_status = QLabel("")
        self._run_status.setWordWrap(True)
        self._run_status.setStyleSheet("color: #A6ADC8;")
        outer.addWidget(self._run_status)

        # Advanced section
        self._advanced = QGroupBox(t("params.advanced_toggle"))
        self._advanced.setCheckable(True)
        self._advanced.setChecked(False)
        adv_form = QFormLayout(self._advanced)

        self._num_modes = QSpinBox()
        self._num_modes.setRange(1, 50)
        self._num_modes.setValue(9)
        adv_form.addRow(t("params.num_modes"), self._num_modes)

        self._energy_range = QDoubleSpinBox()
        self._energy_range.setRange(0.5, 10.0)
        self._energy_range.setSingleStep(0.5)
        self._energy_range.setValue(3.0)
        adv_form.addRow(t("params.energy_range"), self._energy_range)

        self._seed = QSpinBox()
        self._seed.setRange(0, 2_147_483_647)
        self._seed.setValue(42)
        adv_form.addRow(t("params.seed"), self._seed)

        outer.addWidget(self._advanced)

        outer.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._start_btn = QPushButton(t("params.start_btn"))
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.clicked.connect(self._emit_ready)
        btn_row.addWidget(self._start_btn)
        outer.addLayout(btn_row)

        self._result_ready = False
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        idx = self._slider.value()
        self._estimate.setText(t("params.estimate", minutes=str(_SPEED_MINUTES[idx])))

    def current_params(self) -> dict:
        idx = self._slider.value()
        return {
            "exhaustiveness": _SPEED_VALUES[idx],
            "num_modes": self._num_modes.value(),
            "energy_range": float(self._energy_range.value()),
            "seed": self._seed.value(),
        }

    def _emit_ready(self) -> None:
        # Hand off to the dedicated run page (progress shown there); navigation
        # is driven by MainWindow on params_ready.
        self.params_ready.emit(self.current_params())

    def set_docking_started(self, message: str) -> None:
        self._result_ready = False
        self._start_btn.setEnabled(False)
        self._start_btn.setText("启动中…")
        self._run_status.setText(message)

    def set_docking_progress(self, pct: int, message: str) -> None:
        pct = max(0, min(100, int(pct)))
        self._start_btn.setText(f"{pct}%")
        self._run_status.setText(message)

    def set_docking_finished(self, message: str = "对接完成。点击“查看结果”打开结果页。") -> None:
        self._result_ready = True
        self._start_btn.setEnabled(True)
        self._start_btn.setText("查看结果")
        self._run_status.setText(message)

    def set_docking_failed(self, message: str) -> None:
        self._result_ready = False
        self._start_btn.setEnabled(True)
        self._start_btn.setText(t("params.start_btn"))
        self._run_status.setText(message)

    def reset_docking_state(self) -> None:
        self._result_ready = False
        self._start_btn.setEnabled(True)
        self._start_btn.setText(t("params.start_btn"))
        self._run_status.setText("")
