"""Scrolling log console widget (QPlainTextEdit, monospace, auto-scroll)."""

from __future__ import annotations

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class LogConsole(QPlainTextEdit):
    """Read-only log display that auto-scrolls to the bottom on append."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.setFont(font)
        self.setMaximumBlockCount(2000)
        self.setObjectName("LogConsole")

    def append_line(self, text: str) -> None:
        """Append one log line and scroll to bottom."""
        self.appendPlainText(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_log(self) -> None:
        self.clear()
