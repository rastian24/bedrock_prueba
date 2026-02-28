"""Find-in-document bar shown below the editor."""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel, QPlainTextEdit, QTextEdit,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextDocument, QTextCursor, QTextCharFormat, QColor


MATCH_COLOR = QColor("#264f78")
CURRENT_MATCH_COLOR = QColor("#7f6df2")


class FindBar(QWidget):
    """Thin bar for find-in-note (Ctrl+F). Sits below the editor."""

    closed = Signal()

    def __init__(self, editor: QPlainTextEdit, parent=None) -> None:
        super().__init__(parent)
        self._editor = editor

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find in note…")
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.returnPressed.connect(self._find_next)
        layout.addWidget(self.search_input)

        self.match_label = QLabel("")
        self.match_label.setFixedWidth(80)
        self.match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.match_label)

        prev_btn = QPushButton("▲")
        prev_btn.setFixedWidth(32)
        prev_btn.setToolTip("Previous match")
        prev_btn.clicked.connect(self._find_prev)
        layout.addWidget(prev_btn)

        next_btn = QPushButton("▼")
        next_btn.setFixedWidth(32)
        next_btn.setToolTip("Next match")
        next_btn.clicked.connect(self._find_next)
        layout.addWidget(next_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(self._close)
        layout.addWidget(close_btn)

    def show_and_focus(self) -> None:
        self.setVisible(True)
        self.search_input.setFocus()
        self.search_input.selectAll()
        self._on_text_changed(self.search_input.text())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(event)

    def _close(self) -> None:
        self.setVisible(False)
        self._clear_highlights()
        self._editor.setFocus()
        self.closed.emit()

    def _on_text_changed(self, text: str) -> None:
        self._highlight_all(text)
        if text:
            # Jump to first match from start
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(text)

    def _find_next(self) -> None:
        query = self.search_input.text()
        if not query:
            return
        if not self._editor.find(query):
            # Wrap to start
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(query)

    def _find_prev(self) -> None:
        query = self.search_input.text()
        if not query:
            return
        if not self._editor.find(query, QTextDocument.FindFlag.FindBackward):
            # Wrap to end
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._editor.setTextCursor(cursor)
            self._editor.find(query, QTextDocument.FindFlag.FindBackward)

    def _highlight_all(self, query: str) -> None:
        if not query:
            self._clear_highlights()
            self.match_label.setText("")
            return

        doc = self._editor.document()
        highlights = []
        count = 0

        fmt = QTextCharFormat()
        fmt.setBackground(MATCH_COLOR)

        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(query, cursor)
            if cursor.isNull():
                break
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            highlights.append(sel)
            count += 1

        self._editor.setExtraSelections(highlights)
        self.match_label.setText(f"{count} match{'es' if count != 1 else ''}" if count else "No matches")
        # Tint label red when no matches
        self.match_label.setStyleSheet("color: #ff6b6b;" if count == 0 and query else "color: #999999;")

    def _clear_highlights(self) -> None:
        self._editor.setExtraSelections([])
        self.match_label.setText("")
