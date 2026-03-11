"""Wikilink and tag detection, autocomplete, and navigation."""

from collections.abc import Callable

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


class TagCompleter:
    """Handles #tag autocompletion popup."""

    def __init__(self, editor: QPlainTextEdit) -> None:
        self.editor = editor
        self._tag_source: Callable[[], list[str]] | None = None
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.ToolTip)
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setMaximumHeight(200)
        self.popup.setMinimumWidth(200)
        self.popup.itemClicked.connect(self._on_item_clicked)
        self._active = False

    def set_tag_source(self, source: Callable[[], list[str]]) -> None:
        """Set a callable that returns the list of known tags."""
        self._tag_source = source

    def handle_key(self, text: str, cursor: QTextCursor) -> None:
        """Called after each key press to manage the tag popup."""
        if not self._tag_source:
            return

        block_text = cursor.block().text()
        col = cursor.positionInBlock()

        if not self._active:
            # Detect a fresh # trigger
            if col >= 1 and block_text[col - 1] == "#":
                # Only activate if # is at start of word (preceded by whitespace or SOL)
                if col == 1 or not block_text[col - 2].isalnum():
                    self._active = True
                    self._update_popup("")
                    return
        else:
            # Find the # before cursor and extract the partial tag
            prefix = block_text[:col]
            hash_pos = self._find_tag_start(prefix)
            if hash_pos == -1:
                self.hide()
                return
            query = prefix[hash_pos + 1:]
            # If query has a space or is empty after deletion, close
            if " " in query:
                self.hide()
                return
            self._update_popup(query)

    def _find_tag_start(self, prefix: str) -> int:
        """Find the position of the # that started the current tag."""
        # Walk backwards to find the #
        for i in range(len(prefix) - 1, -1, -1):
            ch = prefix[i]
            if ch == "#":
                # Ensure it's a valid tag start (preceded by space or SOL)
                if i == 0 or not prefix[i - 1].isalnum():
                    return i
                return -1
            if not (ch.isalnum() or ch in "-_/"):
                return -1
        return -1

    def accept_completion(self) -> bool:
        """Accept the selected tag. Returns True if handled."""
        if not self._active or not self.popup.isVisible():
            return False

        item = self.popup.currentItem()
        if not item:
            return False

        tag_name = item.data(Qt.ItemDataRole.UserRole)
        cursor = self.editor.textCursor()

        # Find the # and replace from after it to cursor
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        prefix = block_text[:col]
        hash_pos = self._find_tag_start(prefix)
        if hash_pos == -1:
            self.hide()
            return False

        # Select from after # to current position and replace with tag name
        cursor.setPosition(cursor.block().position() + hash_pos + 1)
        cursor.setPosition(self.editor.textCursor().position(), QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(tag_name)
        self.editor.setTextCursor(cursor)
        self.hide()
        return True

    def _update_popup(self, query: str) -> None:
        if not self._tag_source:
            return

        tags = self._tag_source()
        query_lower = query.lower()
        filtered = [t for t in tags if query_lower in t.lower()] if query else tags

        if not filtered:
            self.popup.hide()
            return

        self.popup.clear()
        for tag in filtered[:20]:
            item = QListWidgetItem(f"#{tag}")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.popup.addItem(item)
        self.popup.setCurrentRow(0)

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
