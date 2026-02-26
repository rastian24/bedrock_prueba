"""Cursor-aware Markdown syntax highlighter for QPlainTextEdit.

On lines WITHOUT the cursor, markup markers (**, *, `, [[, ]]) are painted
with the background color (invisible). On the cursor line, they show in gray.
"""

import re

from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument,
)
from PySide6.QtCore import Qt

from core import patterns

# Colors
BG_COLOR = QColor("#1e1e1e")
TEXT_COLOR = QColor("#dcddde")
ACCENT_COLOR = QColor("#7f6df2")
TAG_COLOR = QColor("#e5c07b")
GRAY_COLOR = QColor("#666666")
CODE_BG = QColor("#2a2a2a")
BLOCKQUOTE_COLOR = QColor("#999999")

# State constants
STATE_NORMAL = 0
STATE_CODE_FENCE = 1


class MarkdownHighlighter(QSyntaxHighlighter):
    """Applies visual Markdown formatting with cursor-aware marker hiding."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._cursor_block_number: int = -1

    def set_cursor_block(self, block_number: int) -> None:
        """Called by the editor when the cursor moves to a new line."""
        old = self._cursor_block_number
        self._cursor_block_number = block_number
        # Rehighlight the old and new cursor blocks
        doc = self.document()
        if doc:
            if old >= 0:
                block = doc.findBlockByNumber(old)
                if block.isValid():
                    self.rehighlightBlock(block)
            block = doc.findBlockByNumber(block_number)
            if block.isValid():
                self.rehighlightBlock(block)

    def highlightBlock(self, text: str) -> None:
        block_num = self.currentBlock().blockNumber()
        is_cursor_line = (block_num == self._cursor_block_number)

        # Handle code fence state
        prev_state = self.previousBlockState()
        if prev_state == STATE_CODE_FENCE:
            # Inside a code fence
            if patterns.CODE_FENCE.match(text):
                # Closing fence
                self._apply_code_format(text, 0, len(text), is_cursor_line)
                self.setCurrentBlockState(STATE_NORMAL)
            else:
                self._apply_code_format(text, 0, len(text), is_cursor_line)
                self.setCurrentBlockState(STATE_CODE_FENCE)
            return

        if patterns.CODE_FENCE.match(text):
            # Opening fence
            self._apply_code_format(text, 0, len(text), is_cursor_line)
            self.setCurrentBlockState(STATE_CODE_FENCE)
            return

        self.setCurrentBlockState(STATE_NORMAL)

        # Headings
        m = re.match(r'^(#{1,6})\s+(.*)$', text)
        if m:
            level = len(m.group(1))
            sizes = {1: 28, 2: 22, 3: 18, 4: 16, 5: 15, 6: 14}
            fmt = QTextCharFormat()
            fmt.setFontPointSize(sizes.get(level, 16))
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(TEXT_COLOR)
            # Apply to entire line
            self.setFormat(0, len(text), fmt)
            # Hide the # markers on non-cursor lines
            marker_fmt = QTextCharFormat(fmt)
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(0, len(m.group(1)) + 1, marker_fmt)
            # Still process inline formatting within headings
            self._apply_inline(text, is_cursor_line, start=m.start(2))
            return

        # Blockquote
        bq = re.match(r'^(>\s?)+', text)
        if bq:
            fmt = QTextCharFormat()
            fmt.setForeground(BLOCKQUOTE_COLOR)
            fmt.setFontItalic(True)
            self.setFormat(0, len(text), fmt)
            marker_fmt = QTextCharFormat(fmt)
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(0, bq.end(), marker_fmt)
            return

        # Horizontal rule
        if patterns.HORIZONTAL_RULE.match(text):
            fmt = QTextCharFormat()
            fmt.setForeground(GRAY_COLOR)
            self.setFormat(0, len(text), fmt)
            return

        # List items
        list_m = re.match(r'^(\s*)([-*+]|\d+\.)\s+', text)
        if list_m:
            fmt = QTextCharFormat()
            fmt.setForeground(ACCENT_COLOR)
            self.setFormat(list_m.start(2), len(list_m.group(2)), fmt)

        # Apply inline formatting
        self._apply_inline(text, is_cursor_line)

    def _apply_inline(self, text: str, is_cursor_line: bool, start: int = 0) -> None:
        """Apply inline formatting: bold, italic, code, wikilinks, tags, links."""
        region = text[start:]

        # Inline code (process first to avoid conflicts)
        for m in patterns.INLINE_CODE.finditer(region):
            abs_start = start + m.start()
            code_fmt = QTextCharFormat()
            code_fmt.setFontFamily("monospace")
            code_fmt.setBackground(CODE_BG)
            code_fmt.setForeground(TEXT_COLOR)
            self.setFormat(abs_start, m.end() - m.start(), code_fmt)
            # Hide backticks
            marker_fmt = QTextCharFormat(code_fmt)
            if not is_cursor_line:
                marker_fmt.setForeground(CODE_BG)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(abs_start, 1, marker_fmt)
            self.setFormat(abs_start + m.end() - m.start() - 1, 1, marker_fmt)

        # Bold
        for m in patterns.BOLD.finditer(region):
            abs_start = start + m.start()
            length = m.end() - m.start()
            marker_len = len(m.group(1))  # ** or __
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            fmt.setForeground(TEXT_COLOR)
            self.setFormat(abs_start, length, fmt)
            # Hide markers
            marker_fmt = QTextCharFormat(fmt)
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(abs_start, marker_len, marker_fmt)
            self.setFormat(abs_start + length - marker_len, marker_len, marker_fmt)

        # Italic
        for m in patterns.ITALIC.finditer(region):
            abs_start = start + m.start()
            length = m.end() - m.start()
            fmt = QTextCharFormat()
            fmt.setFontItalic(True)
            fmt.setForeground(TEXT_COLOR)
            self.setFormat(abs_start, length, fmt)
            # Hide markers
            marker_fmt = QTextCharFormat(fmt)
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(abs_start, 1, marker_fmt)
            self.setFormat(abs_start + length - 1, 1, marker_fmt)

        # Wikilinks
        for m in patterns.WIKILINK.finditer(region):
            abs_start = start + m.start()
            length = m.end() - m.start()
            fmt = QTextCharFormat()
            fmt.setForeground(ACCENT_COLOR)
            fmt.setFontUnderline(True)
            self.setFormat(abs_start, length, fmt)
            # Hide [[ and ]] markers
            marker_fmt = QTextCharFormat(fmt)
            marker_fmt.setFontUnderline(False)
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            self.setFormat(abs_start, 2, marker_fmt)
            self.setFormat(abs_start + length - 2, 2, marker_fmt)

        # Markdown links [text](url)
        for m in patterns.MD_LINK.finditer(region):
            abs_start = start + m.start()
            length = m.end() - m.start()
            text_start = abs_start + 1
            text_len = len(m.group(1))

            # Link text
            link_fmt = QTextCharFormat()
            link_fmt.setForeground(ACCENT_COLOR)
            link_fmt.setFontUnderline(True)
            self.setFormat(text_start, text_len, link_fmt)

            # Hide the markup around it
            marker_fmt = QTextCharFormat()
            if not is_cursor_line:
                marker_fmt.setForeground(BG_COLOR)
            else:
                marker_fmt.setForeground(GRAY_COLOR)
            # [ before text
            self.setFormat(abs_start, 1, marker_fmt)
            # ](url) after text
            rest_start = text_start + text_len
            rest_len = length - text_len - 1
            self.setFormat(rest_start, rest_len, marker_fmt)

        # Tags
        for m in patterns.TAG.finditer(region):
            abs_start = start + m.start()
            length = len(m.group(0))  # group(0) includes the #
            fmt = QTextCharFormat()
            fmt.setForeground(TAG_COLOR)
            self.setFormat(abs_start, length, fmt)

    def _apply_code_format(self, text: str, start: int, length: int, is_cursor_line: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontFamily("monospace")
        fmt.setBackground(CODE_BG)
        fmt.setForeground(QColor("#abb2bf"))
        self.setFormat(start, length, fmt)
