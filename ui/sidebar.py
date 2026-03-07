"""Reusable sidebar panel with collapsible, resizable, drag-to-reorder sections."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint, QMimeData, QByteArray, QTimer
from PySide6.QtGui import QDrag


class SectionHeader(QPushButton):
    """Toggle button that triggers drag-to-reorder when the mouse is moved."""

    drag_initiated = Signal()
    _THRESHOLD = 8

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("section_toggle_btn")
        self.setCheckable(True)
        self.setChecked(True)
        self._press_pos: QPoint | None = None
        self._dragging = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_pos is not None:
            if (event.pos() - self._press_pos).manhattanLength() >= self._THRESHOLD:
                self._dragging = True
                self._press_pos = None
                self.drag_initiated.emit()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_dragging = self._dragging
        self._dragging = False
        self._press_pos = None
        if was_dragging:
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CollapsibleSection(QWidget):
    """Header button + collapsible content widget."""

    def __init__(self, label: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._expanded = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = SectionHeader(f"▼  {label}")
        layout.addWidget(self.header)

        self.content = content
        layout.addWidget(content, stretch=1)

    @property
    def label(self) -> str:
        return self._label

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, value: bool) -> None:
        self._expanded = value
        self.content.setVisible(value)
        self.header.setText(("▼" if value else "▶") + f"  {self._label}")
        self.header.setChecked(value)


class SidebarPanel(QWidget):
    """Sidebar panel whose sections are collapsible, resizable and drag-to-reorder."""

    _MIME = "application/x-bedrock-section"
    _HEADER_H = 30

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sections: list[CollapsibleSection] = []

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._splitter)

        self.setAcceptDrops(True)

    # ── public API ────────────────────────────────────────────────────────────

    def add_section(self, label: str, content: QWidget, expanded: bool = True) -> CollapsibleSection:
        """Append a new collapsible section to the panel."""
        section = CollapsibleSection(label, content)
        section.set_expanded(expanded)
        section.header.clicked.connect(lambda checked, s=section: self._on_toggle(s, checked))
        section.header.drag_initiated.connect(lambda s=section: self._start_drag(s))
        self._splitter.addWidget(section)
        self._sections.append(section)
        return section

    def expand_section(self, content: QWidget) -> None:
        """Ensure the section whose content widget is `content` is expanded."""
        for section in self._sections:
            if section.content is content and not section.is_expanded:
                section.set_expanded(True)
                QTimer.singleShot(0, self._rebalance)
                break

    # ── private ───────────────────────────────────────────────────────────────

    def _on_toggle(self, section: CollapsibleSection, checked: bool) -> None:
        if not checked:
            open_count = sum(1 for s in self._sections if s.is_expanded and s is not section)
            if open_count == 0:
                section.header.setChecked(True)
                return
        section.set_expanded(checked)
        QTimer.singleShot(0, self._rebalance)

    def _rebalance(self) -> None:
        """Redistribute splitter sizes: collapsed → header height, expanded → share rest."""
        if not self._sections:
            return
        total = self._splitter.height()
        visible = [s for s in self._sections if s.isVisible()]
        n_collapsed = sum(1 for s in visible if not s.is_expanded)
        avail = max(total - n_collapsed * self._HEADER_H, 0)
        n_expanded = len(visible) - n_collapsed
        per = avail // max(n_expanded, 1)
        sizes = [
            (per if s.is_expanded else self._HEADER_H) if s.isVisible() else 0
            for s in self._sections
        ]
        self._splitter.setSizes(sizes)

    def _start_drag(self, section: CollapsibleSection) -> None:
        idx = self._sections.index(section)
        drag = QDrag(section.header)
        mime = QMimeData()
        mime.setData(self._MIME, QByteArray(str(idx).encode()))
        drag.setMimeData(mime)
        pix = section.header.grab()
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(pix.width() // 2, pix.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

    # ── drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self._MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(self._MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(self._MIME):
            return

        src_idx = int(bytes(event.mimeData().data(self._MIME)).decode())
        drop_y = event.position().toPoint().y()

        # Determine insertion index from the vertical drop position
        target_idx = len(self._sections)
        for i, s in enumerate(self._sections):
            mid = s.mapTo(self, QPoint(0, s.height() // 2)).y()
            if drop_y < mid:
                target_idx = i
                break

        # No-op: dropped on itself or right after itself
        if target_idx in (src_idx, src_idx + 1):
            event.accept()
            return

        section = self._sections.pop(src_idx)
        insert_at = target_idx - 1 if target_idx > src_idx else target_idx
        self._sections.insert(insert_at, section)

        for i, s in enumerate(self._sections):
            self._splitter.insertWidget(i, s)

        event.acceptProposedAction()
