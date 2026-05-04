"""Dialog for manually entering a docking box."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
)


class CustomBoxDialog(QDialog):
    """Let the user enter docking box center coordinates and dimensions."""

    def __init__(
        self,
        default_center: tuple[float, float, float] = (0, 0, 0),
        default_size: tuple[float, float, float] = (22.5, 22.5, 22.5),
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("自定义对接盒子")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        center_group = QGroupBox("盒子中心 (Å)")
        center_layout = QFormLayout(center_group)
        self.cx = QDoubleSpinBox()
        self.cx.setRange(-1000, 1000)
        self.cx.setDecimals(2)
        self.cx.setValue(default_center[0])
        self.cy = QDoubleSpinBox()
        self.cy.setRange(-1000, 1000)
        self.cy.setDecimals(2)
        self.cy.setValue(default_center[1])
        self.cz = QDoubleSpinBox()
        self.cz.setRange(-1000, 1000)
        self.cz.setDecimals(2)
        self.cz.setValue(default_center[2])
        center_layout.addRow("X:", self.cx)
        center_layout.addRow("Y:", self.cy)
        center_layout.addRow("Z:", self.cz)
        layout.addWidget(center_group)

        size_group = QGroupBox("盒子大小 (Å)")
        size_layout = QFormLayout(size_group)
        self.sx = QDoubleSpinBox()
        self.sx.setRange(5, 60)
        self.sx.setDecimals(1)
        self.sx.setValue(default_size[0])
        self.sy = QDoubleSpinBox()
        self.sy.setRange(5, 60)
        self.sy.setDecimals(1)
        self.sy.setValue(default_size[1])
        self.sz = QDoubleSpinBox()
        self.sz.setRange(5, 60)
        self.sz.setDecimals(1)
        self.sz.setValue(default_size[2])
        size_layout.addRow("X:", self.sx)
        size_layout.addRow("Y:", self.sy)
        size_layout.addRow("Z:", self.sz)
        layout.addWidget(size_group)

        hint = QLabel(
            "提示: 可以从 PyMOL/ChimeraX 的对接口袋测量结果获取坐标。\n"
            "推荐盒子大小: 20-25 Å (常见小分子配体)"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_box(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Return ``(center, size)`` for the docking box."""
        return (
            (self.cx.value(), self.cy.value(), self.cz.value()),
            (self.sx.value(), self.sy.value(), self.sz.value()),
        )
