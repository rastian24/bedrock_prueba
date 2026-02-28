"""Search panels: Quick Open (Ctrl+P) and Vault Search (Ctrl+Shift+F)."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QWidget, QLabel,
)
from PySide6.QtCore import Signal, Qt, QTimer

from core.vault import Vault
from core.search_engine import SearchEngine


def fuzzy_match(query: str, text: str) -> tuple[bool, int]:
    """Subsequence fuzzy match with scoring.

    Returns (is_match, score). Higher score = better match.
    """
    query_lower = query.lower()
    text_lower = text.lower()

    if not query_lower:
        return True, 0

    qi = 0
    score = 0
    prev_match = -2
    for ti, ch in enumerate(text_lower):
        if qi < len(query_lower) and ch == query_lower[qi]:
            # Bonus for consecutive matches
            if ti == prev_match + 1:
                score += 10
            # Bonus for word boundary
            if ti == 0 or text[ti - 1] in " _-./":
                score += 5
            score += 1
            prev_match = ti
            qi += 1

    if qi < len(query_lower):
        return False, 0
    return True, score


class SearchDialog(QDialog):
    """Quick Open dialog (Ctrl+P) — fuzzy file name search."""

    note_selected = Signal(str)

    def __init__(self, vault: Vault, parent=None) -> None:
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Quick Open")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(500, 350)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search notes by name...")
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.itemActivated.connect(self._on_item_activated)
        self.results_list.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self.results_list)

        self._notes = vault.list_notes()
        self._populate("")
        self.search_input.setFocus()

        # Center on parent
        if parent:
            geo = parent.geometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.top() + 100,
            )

    def _on_text_changed(self, text: str) -> None:
        self._populate(text)

    def _populate(self, query: str) -> None:
        self.results_list.clear()
        scored = []
        for note in self._notes:
            match, score = fuzzy_match(query, note.stem)
            if match:
                scored.append((score, note))

        scored.sort(key=lambda x: -x[0])
        for _, note in scored[:30]:
            rel = note.stem
            item = QListWidgetItem(rel)
            item.setData(Qt.ItemDataRole.UserRole, str(note))
            self.results_list.addItem(item)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_selected.emit(path)
            self.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.results_list.keyPressEvent(event)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current = self.results_list.currentItem()
            if current:
                self._on_item_activated(current)
        else:
            super().keyPressEvent(event)


class VaultSearchPanel(QWidget):
    """Full-text search panel (Ctrl+Shift+F) in the right sidebar."""

    note_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search_engine: SearchEngine | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("SEARCH")
        header.setObjectName("section_header")
        layout.addWidget(header)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in vault...")
        self.search_input.setStyleSheet("margin: 4px 8px;")
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.results_list)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_search)

    def set_search_engine(self, engine: SearchEngine) -> None:
        self.search_engine = engine

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def show_tag_results(self, tag: str, notes: list[Path]) -> None:
        """Show notes matching a tag (used by tag panel)."""
        self.search_input.setText(f"#{tag}")
        self.results_list.clear()
        for note in notes:
            item = QListWidgetItem(note.stem)
            item.setData(Qt.ItemDataRole.UserRole, str(note))
            self.results_list.addItem(item)

    def _on_text_changed(self, text: str) -> None:
        self._debounce.start()

    def _do_search(self) -> None:
        query = self.search_input.text().strip()
        if not query or not self.search_engine:
            self.results_list.clear()
            return

        # Skip tag-prefixed queries (handled by show_tag_results)
        if query.startswith("#"):
            return

        results = self.search_engine.search(query)
        self.results_list.clear()
        for result in results:
            title = result["title"]
            highlights = result.get("highlights", "")
            text = f"{title}\n  {highlights[:80]}" if highlights else title
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, result["path"])
            self.results_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_clicked.emit(path)
