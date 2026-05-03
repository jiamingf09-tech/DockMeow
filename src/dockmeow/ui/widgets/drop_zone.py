"""Generic drag-and-drop file zone widget.

Emits ``file_dropped(Path)`` when a file with one of the accepted extensions
is dropped or selected via the file dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QLabel


class DropZone(QLabel):
    """Drag-and-drop file zone with hover state and click-to-browse fallback."""

    file_dropped = Signal(Path)

    def __init__(
        self,
        hint: str,
        accepted_extensions: list[str],
        parent=None,
        file_dialog_filter: str | None = None,
    ) -> None:
        super().__init__(hint, parent)
        self._hint = hint
        self._accepted = [e.lower().lstrip(".") for e in accepted_extensions]
        self._file_filter = file_dialog_filter or self._build_filter()
        self._hover = False

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setWordWrap(True)
        self.setObjectName("DropZone")
        self._apply_style()

    def _build_filter(self) -> str:
        if not self._accepted:
            return "All files (*)"
        patterns = " ".join(f"*.{e}" for e in self._accepted)
        return f"Supported ({patterns});;All files (*)"

    def _apply_style(self) -> None:
        border = "#7C9EF8" if self._hover else "#6C7086"
        bg = "#2A2A3E" if self._hover else "#252535"
        self.setStyleSheet(
            f"QLabel#DropZone {{"
            f"  border: 2px dashed {border};"
            f"  border-radius: 12px;"
            f"  background: {bg};"
            f"  color: #CDD6F4;"
            f"  padding: 24px;"
            f"  font-size: 14px;"
            f"}}"
        )

    # --- Drag & drop -------------------------------------------------------
    def _is_acceptable(self, path: Path) -> bool:
        if not self._accepted:
            return True
        return path.suffix.lower().lstrip(".") in self._accepted

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and self._is_acceptable(Path(url.toLocalFile())):
                    event.acceptProposedAction()
                    self._hover = True
                    self._apply_style()
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._apply_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._hover = False
        self._apply_style()
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if self._is_acceptable(p):
                event.acceptProposedAction()
                self.file_dropped.emit(p)
                return
        event.ignore()

    # --- Click to browse ---------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, self._hint, "", self._file_filter
            )
            if path:
                self.file_dropped.emit(Path(path))
        super().mousePressEvent(event)
