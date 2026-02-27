"""WYSIWYG Markdown editor with auto-save and keyboard shortcuts."""

from pathlib import Path

from PySide6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtCore import QRectF
from PySide6.QtGui import (
    QTextCursor, QFont, QKeyEvent, QMouseEvent,
    QPixmap, QPainter, QColor,
)

from core.vault import Vault
from core.patterns import IMAGE_LINK, CHECKLIST
from ui.editor.markdown_highlighter import MarkdownHighlighter
from ui.editor.wikilink_handler import WikilinkCompleter, find_wikilink_at_position

# Max width for rendered images (pixels)
IMAGE_MAX_WIDTH = 500
IMAGE_PADDING = 6


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
        self._pixmap_cache: dict[str, QPixmap | None] = {}
        self._image_block_heights: dict[int, int] = {}  # block_number -> image height

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

        # Update images on scroll
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

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
        self._pixmap_cache.clear()
        self._image_block_heights.clear()
        self._update_image_margins()
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
        self._update_image_margins()

    def _on_cursor_moved(self) -> None:
        block_num = self.textCursor().blockNumber()
        old_block = self.highlighter._cursor_block_number
        self.highlighter.set_cursor_block(block_num)
        # Update margins when cursor enters/leaves an image block
        if old_block != block_num:
            if old_block in self._image_block_heights or block_num in self._image_block_heights:
                self._update_image_margins()
                self.viewport().update()

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

            # Toggle checkbox on click
            check_m = CHECKLIST.match(block.text())
            if check_m:
                bracket_pos = len(check_m.group(1))
                # Click anywhere in the checkbox area (before content starts)
                if pos_in_block <= check_m.end():
                    self._toggle_checkbox(block, check_m)
                    return

            target = find_wikilink_at_position(block.text(), pos_in_block)
            if target:
                self.wikilink_clicked.emit(target)
                return
        super().mousePressEvent(event)

    def _toggle_checkbox(self, block, check_match) -> None:
        """Toggle a checklist item between [ ] and [x]."""
        prefix = check_match.group(1)
        old_state = check_match.group(2)
        new_state = " " if old_state.lower() == "x" else "x"
        # Replace the character inside the brackets
        cursor = QTextCursor(block)
        bracket_pos = len(prefix) + 1  # position of the space/x inside [_]
        cursor.movePosition(QTextCursor.MoveOperation.Right, n=bracket_pos)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, n=1)
        cursor.insertText(new_state)

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

    # --- Image rendering ---

    def _resolve_image_path(self, src: str) -> Path | None:
        """Resolve an image path relative to the current note."""
        if not self.current_note:
            return None
        path = (self.current_note.parent / src).resolve()
        if path.is_file():
            return path
        # Also try relative to vault root
        if self.vault:
            path = (self.vault.path / src).resolve()
            if path.is_file():
                return path
        return None

    def _get_pixmap(self, src: str) -> QPixmap | None:
        """Load and cache a pixmap for the given image source."""
        if src in self._pixmap_cache:
            return self._pixmap_cache[src]
        resolved = self._resolve_image_path(src)
        if resolved is None:
            self._pixmap_cache[src] = None
            return None
        pixmap = QPixmap(str(resolved))
        if pixmap.isNull():
            self._pixmap_cache[src] = None
            return None
        # Scale down if too wide
        max_w = min(IMAGE_MAX_WIDTH, self.viewport().width() - 20)
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
        self._pixmap_cache[src] = pixmap
        return pixmap

    def _update_image_margins(self) -> None:
        """Scan all blocks for image patterns and set bottom margins to reserve space.

        Cursor block gets no margin (shows raw markdown instead of image).
        """
        self.blockSignals(True)
        cursor_block = self.textCursor().blockNumber()
        doc = self.document()
        block = doc.begin()
        new_heights: dict[int, int] = {}
        while block.isValid():
            block_num = block.blockNumber()
            m = IMAGE_LINK.search(block.text())
            if m:
                pixmap = self._get_pixmap(m.group(2))
                if pixmap:
                    new_heights[block_num] = pixmap.height() + IMAGE_PADDING * 2
                    if block_num == cursor_block:
                        # Cursor on this line: no margin, show raw text
                        self._set_block_margin(block, 0)
                    else:
                        # Show image with reserved space
                        self._set_block_margin(block, new_heights[block_num])
                else:
                    self._set_block_margin(block, 0)
            else:
                self._set_block_margin(block, 0)
            block = block.next()
        self._image_block_heights = new_heights
        self.blockSignals(False)

    def _set_block_margin(self, block, margin: int) -> None:
        """Set bottom margin on a block (only if it changed)."""
        fmt = block.blockFormat()
        if int(fmt.bottomMargin()) != margin:
            cursor = QTextCursor(block)
            fmt.setBottomMargin(margin)
            cursor.setBlockFormat(fmt)

    def paintEvent(self, event) -> None:
        """Paint the editor content, then draw images and checkboxes."""
        super().paintEvent(event)
        cursor_block = self.textCursor().blockNumber()
        painter = QPainter(self.viewport())
        block = self.firstVisibleBlock()
        while block.isValid():
            geom = self.blockBoundingGeometry(block).translated(self.contentOffset())
            if geom.top() > self.viewport().height():
                break
            block_num = block.blockNumber()

            if block_num != cursor_block:
                text = block.text()

                # Draw checkbox for checklist items
                check_m = CHECKLIST.match(text)
                if check_m:
                    checked = check_m.group(2).lower() == "x"
                    symbol = "☑" if checked else "☐"
                    color = QColor("#7f6df2") if checked else QColor("#999999")
                    painter.save()
                    font = QFont(self.font())
                    font.setPointSize(14)
                    painter.setFont(font)
                    painter.setPen(color)
                    x = int(geom.left()) + 2
                    y = int(geom.top())
                    line_h = self.fontMetrics().height()
                    from PySide6.QtCore import Qt as QtNS
                    painter.drawText(
                        QRectF(x, y, 24, line_h),
                        int(QtNS.AlignmentFlag.AlignVCenter),
                        symbol,
                    )
                    painter.restore()

                # Draw inline image
                if block_num in self._image_block_heights:
                    m = IMAGE_LINK.search(text)
                    if m:
                        pixmap = self._get_pixmap(m.group(2))
                        if pixmap:
                            y = int(geom.top()) + IMAGE_PADDING
                            x = 10
                            painter.drawPixmap(x, y, pixmap)

            block = block.next()
        painter.end()
