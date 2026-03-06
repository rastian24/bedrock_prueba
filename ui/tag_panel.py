"""Tag panel showing all tags in the vault with occurrence counts."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Signal, Qt


class TagPanel(QWidget):
    """Panel displaying all tags found across the vault."""

    tag_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

    def set_tags(self, tags: dict[str, int]) -> None:
        """Update the tag list. tags is {tag_name: count}."""
        self.list_widget.clear()
        for tag, count in sorted(tags.items()):
            item = QListWidgetItem(f"#{tag}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setForeground(Qt.GlobalColor.yellow)
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag:
            self.tag_clicked.emit(tag)
