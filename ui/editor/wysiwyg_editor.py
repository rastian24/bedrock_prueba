"""WYSIWYG Markdown editor with auto-save and keyboard shortcuts."""

from pathlib import Path

from PySide6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QTextCursor, QFont, QKeyEvent, QMouseEvent, QFontDatabase,
)

from core.vault import Vault
from ui.editor.markdown_highlighter import MarkdownHighlighter
from ui.editor.wikilink_handler import WikilinkCompleter, find_wikilink_at_position


class WysiwygEditor(QPlainTextEdit):
    """Markdown WYSIWYG editor with cursor-aware highlighting and auto-save."""

    saved = Signal(str)  # Emits file path on save
    content_changed = Signal()
    wikilink_clicked = Signal(str)  # Emits target name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.vault: Vault | None = None
        self.current_note: Path | None = None
        self._modified = False

        # Font setup
        font = QFont("monospace", 16)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(32)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Highlighter
        self.highlighter = MarkdownHighlighter(self.document())

        # Wikilink completer
        self.completer = WikilinkCompleter(self)

        # Auto-save timer (2s debounce)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self.save_now)

        # Track cursor for highlighter
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.textChanged.connect(self._on_text_changed)

    def set_vault(self, vault: Vault) -> None:
        self.vault = vault
        self.completer.set_vault(vault)

    def open_note(self, path: Path) -> None:
        """Open a note file in the editor."""
        self.save_now()
        self.current_note = path
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        self.blockSignals(True)
        self.setPlainText(content)
        self.blockSignals(False)
        self._modified = False
        # Re-highlight with new cursor position
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        self.highlighter.set_cursor_block(0)
        self.setFocus()

    def save_now(self) -> None:
        """Save the current note immediately."""
        if self.current_note and self._modified and self.vault:
            try:
                self.vault.write_note(self.current_note, self.toPlainText())
                self._modified = False
                self.saved.emit(str(self.current_note))
            except OSError:
                pass

    def _on_text_changed(self) -> None:
        self._modified = True
        self._save_timer.start()
        self.content_changed.emit()

    def _on_cursor_moved(self) -> None:
        block_num = self.textCursor().blockNumber()
        self.highlighter.set_cursor_block(block_num)

    # --- Key handling ---

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        key = event.key()

        # Completer navigation
        if self.completer.is_active():
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Tab:
                if self.completer.accept_completion():
                    return
            elif key == Qt.Key.Key_Escape:
                self.completer.hide()
                return
            elif key == Qt.Key.Key_Down:
                self.completer.move_selection(1)
                return
            elif key == Qt.Key.Key_Up:
                self.completer.move_selection(-1)
                return

        # Keyboard shortcuts
        ctrl = modifiers & Qt.KeyboardModifier.ControlModifier
        shift = modifiers & Qt.KeyboardModifier.ShiftModifier

        if ctrl and not shift:
            if key == Qt.Key.Key_B:
                self._toggle_wrap("**")
                return
            elif key == Qt.Key.Key_I:
                self._toggle_wrap("*")
                return
            elif key == Qt.Key.Key_K:
                self._insert_md_link()
                return
            elif key == Qt.Key.Key_S:
                self.save_now()
                return
            elif key == Qt.Key.Key_L:
                self._insert_list("- ")
                return
            elif key == Qt.Key.Key_H:
                self._cycle_heading()
                return

        if ctrl and shift:
            if key == Qt.Key.Key_K:
                self._insert_wikilink()
                return
            elif key == Qt.Key.Key_L:
                self._insert_list("1. ")
                return
            elif key == Qt.Key.Key_C:
                self._insert_code_block()
                return

        super().keyPressEvent(event)

        # After processing the key, update completer
        self.completer.handle_key(event.text(), self.textCursor())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position().toPoint()
            cursor = self.cursorForPosition(click_pos)
            block = cursor.block()
            pos_in_block = cursor.positionInBlock()
            target = find_wikilink_at_position(block.text(), pos_in_block)
            if target:
                self.wikilink_clicked.emit(target)
                return
        super().mousePressEvent(event)

    # --- Formatting helpers ---

    def _toggle_wrap(self, marker: str) -> None:
        """Toggle a wrap marker (**, *) around the selection."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            if text.startswith(marker) and text.endswith(marker):
                cursor.insertText(text[len(marker):-len(marker)])
            else:
                cursor.insertText(f"{marker}{text}{marker}")
        else:
            cursor.insertText(f"{marker}{marker}")
            cursor.movePosition(QTextCursor.MoveOperation.Left, n=len(marker))
            self.setTextCursor(cursor)

    def _insert_md_link(self) -> None:
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertText(f"[{selected}](url)")
        else:
            cursor.insertText("[](url)")
            cursor.movePosition(QTextCursor.MoveOperation.Left, n=6)
            self.setTextCursor(cursor)

    def _insert_wikilink(self) -> None:
        cursor = self.textCursor()
        selected = cursor.selectedText()
        if selected:
            cursor.insertText(f"[[{selected}]]")
        else:
            cursor.insertText("[[]]")
            cursor.movePosition(QTextCursor.MoveOperation.Left, n=2)
            self.setTextCursor(cursor)

    def _insert_list(self, prefix: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.insertText(prefix)

    def _insert_code_block(self) -> None:
        cursor = self.textCursor()
        cursor.insertText("```\n\n```")
        cursor.movePosition(QTextCursor.MoveOperation.Up)
        self.setTextCursor(cursor)

    def _cycle_heading(self) -> None:
        """Cycle heading level: none -> H1 -> H2 -> H3 -> none."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        line = cursor.selectedText()

        import re
        m = re.match(r'^(#{1,3})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            if level < 3:
                cursor.insertText(f"{'#' * (level + 1)} {text}")
            else:
                cursor.insertText(text)
        else:
            text = line.lstrip()
            cursor.insertText(f"# {text}")
