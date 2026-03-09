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

    def highlight_tag(self, tag: str) -> None:
        """Select and scroll to the given tag; clear selection if tag is empty."""
        if not tag:
            self.list_widget.clearSelection()
            return
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == tag:
                self.list_widget.setCurrentItem(item)
                self.list_widget.scrollToItem(item)
                return

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag:
            self.tag_clicked.emit(tag)
