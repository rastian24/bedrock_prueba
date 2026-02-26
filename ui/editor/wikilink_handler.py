"""Wikilink detection, autocomplete, and navigation."""

from PySide6.QtWidgets import QPlainTextEdit, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QTextCursor

from core import patterns
from core.vault import Vault


class WikilinkCompleter:
    """Handles [[wikilink]] autocompletion popup."""

    def __init__(self, editor: QPlainTextEdit) -> None:
        self.editor = editor
        self.vault: Vault | None = None
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.ToolTip)
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setMaximumHeight(200)
        self.popup.setMinimumWidth(250)
        self.popup.itemClicked.connect(self._on_item_clicked)
        self._active = False
        self._start_pos = 0

    def set_vault(self, vault: Vault) -> None:
        self.vault = vault

    def handle_key(self, text: str, cursor: QTextCursor) -> bool:
        """Called on each key press. Returns True if the event was consumed."""
        if not self.vault:
            return False

        # Check if we just typed [[
        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        if not self._active:
            # Detect opening [[
            if col >= 2 and block_text[col-2:col] == "[[":
                self._active = True
                self._start_pos = cursor.position()
                self._update_popup("")
                return False
        else:
            # Check if we're still inside the [[...
            # Find the [[ before cursor
            prefix = block_text[:col]
            bracket_pos = prefix.rfind("[[")
            if bracket_pos == -1 or "]]" in prefix[bracket_pos:]:
                self.hide()
                return False

            query = prefix[bracket_pos + 2:]
            if "]]" in query:
                self.hide()
                return False
            self._update_popup(query)

        return False

    def accept_completion(self) -> bool:
        """Accept the selected completion. Returns True if handled."""
        if not self._active or not self.popup.isVisible():
            return False

        item = self.popup.currentItem()
        if not item:
            return False

        name = item.text()
        cursor = self.editor.textCursor()

        # Find the [[ and replace from there to cursor
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        prefix = block_text[:col]
        bracket_pos = prefix.rfind("[[")
        if bracket_pos == -1:
            self.hide()
            return False

        # Select from after [[ to current position
        cursor.setPosition(cursor.block().position() + bracket_pos + 2)
        cursor.setPosition(self.editor.textCursor().position(), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(f"{name}]]")
        self.editor.setTextCursor(cursor)
        self.hide()
        return True

    def _update_popup(self, query: str) -> None:
        if not self.vault:
            return

        names = self.vault.note_names()
        query_lower = query.lower()
        filtered = [n for n in names if query_lower in n.lower()] if query else names

        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        for name in filtered[:20]:
            self.popup.addItem(QListWidgetItem(name))
        self.popup.setCurrentRow(0)

        # Position popup below cursor
        cursor_rect = self.editor.cursorRect()
        global_pos = self.editor.mapToGlobal(cursor_rect.bottomLeft())
        self.popup.move(global_pos + QPoint(0, 4))
        self.popup.show()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self.accept_completion()

    def hide(self) -> None:
        self._active = False
        self.popup.hide()

    def is_active(self) -> bool:
        return self._active

    def move_selection(self, delta: int) -> None:
        """Move popup selection up or down."""
        if not self.popup.isVisible():
            return
        row = self.popup.currentRow() + delta
        row = max(0, min(row, self.popup.count() - 1))
        self.popup.setCurrentRow(row)


def find_wikilink_at_position(text: str, position: int) -> str | None:
    """Find the wikilink target at the given character position in text."""
    for m in patterns.WIKILINK.finditer(text):
        if m.start() <= position < m.end():
            return m.group(1).strip()
    return None
