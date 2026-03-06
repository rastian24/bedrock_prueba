"""Backlinks panel showing notes that link to the current note."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Signal, Qt


class BacklinksPanel(QWidget):
    """Panel displaying backlinks for the currently open note."""

    note_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self._empty_label = QLabel("No backlinks found")
        self._empty_label.setStyleSheet("color: #666666; padding: 16px;")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

    def set_backlinks(self, backlinks: list[tuple[Path, str]]) -> None:
        """Update the backlinks list. Each item is (note_path, context_line)."""
        self.list_widget.clear()
        self._empty_label.setVisible(len(backlinks) == 0)
        self.list_widget.setVisible(len(backlinks) > 0)

        for note_path, context in backlinks:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, str(note_path))
            # Truncate context
            ctx = context[:80] + "..." if len(context) > 80 else context
            item.setText(f"{note_path.stem}\n  {ctx}")
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_clicked.emit(path)
