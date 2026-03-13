"""Main application window with three-panel layout."""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QStatusBar,
    QLabel, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray, QTimer
from PySide6.QtGui import QShortcut, QKeySequence

from core.config import Config
from core.vault import Vault
from core.backlinks import VaultIndex
from core.search_engine import SearchEngine
from ui.vault_selector import VaultSelectorDialog
from ui.file_tree import FileTree
from ui.editor.wysiwyg_editor import WysiwygEditor
from ui.backlinks_panel import BacklinksPanel
from ui.tag_panel import TagPanel
from ui.search_panel import SearchDialog, VaultSearchPanel
from ui.journal_panel import JournalPanel
from ui.settings_dialog import SettingsDialog
from ui.find_bar import FindBar
from ui.graph_view import GraphView
from ui.sidebar import SidebarPanel


class IndexWorker(QThread):
    """Background worker for building vault index."""
    finished = Signal()

    def __init__(self, vault: Vault, vault_index: VaultIndex, search_engine: SearchEngine):
        super().__init__()
        self.vault = vault
        self.vault_index = vault_index
        self.search_engine = search_engine

    def run(self) -> None:
        notes = self.vault.list_notes()
        self.vault_index.build(notes)
        self.search_engine.build_index(notes)
        self.finished.emit()


class MainWindow(QMainWindow):
    """Main Bedrock window with file tree, editor, and backlinks panel."""

    def __init__(self) -> None:
        super().__init__()
        self.config = Config()
        self.vault: Vault | None = None
        self.vault_index = VaultIndex()
        self.search_engine: SearchEngine | None = None
        self._index_worker: IndexWorker | None = None
        self._graph_saved_sizes: list[int] | None = None
        self._pre_todo_note: Path | None = None  # note open before switching to .TODO

        self.setWindowTitle("Bedrock")
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)

        self._setup_ui()
        self._setup_shortcuts()
        self._restore_geometry()

        # Open vault on start
        self._open_initial_vault()

    def _setup_ui(self) -> None:
        # Left sidebar
        self.left_sidebar = SidebarPanel()
        self.left_sidebar.setObjectName("sidebar_left")
        self.file_tree = FileTree()
        self.tag_panel = TagPanel()
        self.journal_panel = JournalPanel()
        self.left_sidebar.add_section("Explorer", self.file_tree)
        self.left_sidebar.add_section("Tags", self.tag_panel, expanded=False)
        self.left_sidebar.add_section("Journal", self.journal_panel)

        # Editor + find bar container
        self.editor_container = QWidget()
        editor_container = self.editor_container
        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        self.editor = WysiwygEditor()
        self.find_bar = FindBar(self.editor)
        self.find_bar.setVisible(False)
        editor_layout.addWidget(self.editor)
        editor_layout.addWidget(self.find_bar)

        # Right sidebar — Search starts collapsed
        self.right_sidebar = SidebarPanel()
        self.right_sidebar.setObjectName("sidebar_right")
        self.backlinks_panel = BacklinksPanel()
        self.vault_search_panel = VaultSearchPanel()
        self.graph_view = GraphView()
        self.right_sidebar.add_section("Backlinks", self.backlinks_panel)
        self.right_sidebar.add_section("Search", self.vault_search_panel, expanded=False)
        self.graph_section = self.right_sidebar.add_section("Graph", self.graph_view)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_sidebar)
        self.splitter.addWidget(editor_container)
        self.splitter.addWidget(self.right_sidebar)
        self.splitter.setSizes([250, 600, 280])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.setCentralWidget(self.splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.file_label = QLabel("No file open")
        self.word_count_label = QLabel("")
        self.save_status_label = QLabel("")
        self.status_bar.addWidget(self.file_label)
        self.status_bar.addWidget(self.word_count_label)
        self.status_bar.addPermanentWidget(self.save_status_label)

        # Connect signals
        self.file_tree.note_selected.connect(self._on_note_selected)
        self.file_tree.note_created.connect(self._on_note_selected)
        self.file_tree.note_moved.connect(self._on_note_moved)
        self.editor.saved.connect(self._on_note_saved)
        self.editor.content_changed.connect(self._update_word_count)
        self.editor.wikilink_clicked.connect(self._on_wikilink_clicked)
        self.editor.tag_at_cursor.connect(self._on_tag_at_cursor)
        self.backlinks_panel.note_clicked.connect(self._on_note_selected)
        self.tag_panel.tag_clicked.connect(self._on_tag_clicked)
        self.journal_panel.note_clicked.connect(self._on_note_selected)
        self.vault_search_panel.note_clicked.connect(self._on_note_selected)
        self.graph_view.note_clicked.connect(self._on_note_selected)
        self.graph_view.maximize_toggled.connect(self._on_graph_maximize)

    def _setup_shortcuts(self) -> None:
        self._shortcuts: dict[str, QShortcut] = {}
        self._apply_hotkeys(self.config.get_hotkeys())

    _HOTKEY_ACTIONS: dict[str, str] = {
        "toggle_left_sidebar": "_toggle_left_sidebar",
        "toggle_right_sidebar": "_toggle_right_sidebar",
        "new_note": "_new_note",
        "quick_open": "_quick_open",
        "vault_search": "_vault_search",
        "find": "_find_in_note",
        "change_vault": "_change_vault",
        "today_journal": "_open_today_journal",
        "settings": "_open_settings",
        "graph_maximize": "_graph_maximize_shortcut",
        "open_todo": "_open_todo",
    }

    def _apply_hotkeys(self, hotkeys: dict[str, str]) -> None:
        """Bind or rebind all shortcuts from the given hotkey map."""
        for action, method_name in self._HOTKEY_ACTIONS.items():
            seq = hotkeys.get(action, "")
            if action in self._shortcuts:
                self._shortcuts[action].setKey(QKeySequence(seq))
            else:
                sc = QShortcut(QKeySequence(seq), self)
                sc.activated.connect(getattr(self, method_name))
                self._shortcuts[action] = sc

    def _toggle_left_sidebar(self) -> None:
        self.left_sidebar.setVisible(not self.left_sidebar.isVisible())

    def _toggle_right_sidebar(self) -> None:
        self.right_sidebar.setVisible(not self.right_sidebar.isVisible())

    def _graph_maximize_shortcut(self) -> None:
        self.graph_view.toggle_maximize()

    def _on_graph_maximize(self, maximized: bool) -> None:
        if maximized:
            self._graph_saved_sizes = self.splitter.sizes()  # [left, editor, right]
            left_w, editor_w, right_w = self._graph_saved_sizes
            # Hide the entire graph section from the sidebar
            self.graph_section.hide()
            # Move graph_view into the center slot (replaces editor)
            self.splitter.insertWidget(1, self.graph_view)   # [left, graph, editor, right]
            self.graph_view.show()
            self.editor_container.hide()
            self.splitter.setSizes([left_w, editor_w, 0, right_w])
            QTimer.singleShot(0, self.right_sidebar._rebalance)
        else:
            # Move graph_view back into its CollapsibleSection and show the section
            self.graph_section.layout().addWidget(self.graph_view, stretch=1)
            self.graph_section.show()
            self.graph_section.set_expanded(True)
            self.editor_container.show()
            if self._graph_saved_sizes:
                self.splitter.setSizes(self._graph_saved_sizes)
            self._graph_saved_sizes = None
            QTimer.singleShot(0, self.right_sidebar._rebalance)
            QTimer.singleShot(0, self.graph_view._rebuild)

    def _expand_search_section(self) -> None:
        self.right_sidebar.expand_section(self.vault_search_panel)

    def _restore_geometry(self) -> None:
        geom = self.config.get("window_geometry")
        if geom:
            self.restoreGeometry(QByteArray.fromBase64(geom.encode()))
        state = self.config.get("window_state")
        if state:
            self.restoreState(QByteArray.fromBase64(state.encode()))

    def closeEvent(self, event) -> None:
        # Save current note before closing
        self.editor.save_now()
        # Save window geometry
        self.config.set("window_geometry", self.saveGeometry().toBase64().data().decode())
        self.config.set("window_state", self.saveState().toBase64().data().decode())
        self.config.save()
        super().closeEvent(event)

    # --- Vault management ---

    def _open_initial_vault(self) -> None:
        last = self.config.last_vault
        if last and Path(last).is_dir():
            self._open_vault(last)
        else:
            self._show_vault_selector()

    def _show_vault_selector(self) -> None:
        dialog = VaultSelectorDialog(self.config.recent_vaults, self)
        if dialog.exec():
            vault_path = dialog.selected_path
            if vault_path:
                self._open_vault(vault_path)
            else:
                # User cancelled, close app if no vault
                if not self.vault:
                    self.close()

    def _change_vault(self) -> None:
        self.editor.save_now()
        self._show_vault_selector()

    def _find_in_note(self) -> None:
        self.find_bar.show_and_focus()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        dialog.hotkeys_changed.connect(self._apply_hotkeys)
        dialog.exec()

    def _open_vault(self, path: str) -> None:
        self.vault = Vault(path)
        if not self.vault.exists():
            self.vault.create()

        self.config.last_vault = path
        self.setWindowTitle(f"Bedrock — {self.vault.name}")

        # Setup search engine
        self.search_engine = SearchEngine(self.vault.bedrock_dir / "index")

        # Set vault on components
        self.file_tree.set_vault(self.vault)
        self.editor.set_vault(self.vault)
        self.editor.tag_completer.set_tag_source(
            lambda: sorted(self.vault_index.get_all_tags().keys())
        )
        self.journal_panel.set_vault(self.vault)

        # Build index in background
        self._build_index()

        # Open today's journal
        self._open_today_journal()

    def _build_index(self) -> None:
        if not self.vault or not self.search_engine:
            return
        self.save_status_label.setText("Indexing...")
        self._index_worker = IndexWorker(self.vault, self.vault_index, self.search_engine)
        self._index_worker.finished.connect(self._on_index_built)
        self._index_worker.start()

    def _on_index_built(self) -> None:
        self.save_status_label.setText("Ready")
        self._update_backlinks()
        self._update_tags()
        self.journal_panel.refresh()
        if self.vault:
            self.graph_view.set_graph(self.vault, self.vault_index)
        self._update_todo_file()

    # --- Journal ---

    def _open_today_journal(self) -> None:
        """Open (or create) today's journal note."""
        if not self.vault:
            return
        journal_path = self.vault.ensure_journal_note()
        self.journal_panel.refresh()
        self._on_note_selected(journal_path)

    # --- Note operations ---

    def _on_note_selected(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return
        self.editor.save_now()
        self.editor.open_note(path)
        self.file_tree.select_note(path)
        self.file_label.setText(path.name)
        self._update_word_count()
        self._update_backlinks()
        self.graph_view.set_current_note(path)

    def _on_note_moved(self, old_path: str, new_path: str) -> None:
        """Update editor and indices when a note is moved via drag and drop."""
        if self.editor.current_note and str(self.editor.current_note) == old_path:
            self._on_note_selected(new_path)
        if self.vault_index:
            self.vault_index.remove_note(Path(old_path))
            self.vault_index.update_note(Path(new_path))
        if self.search_engine:
            self.search_engine.update_note(Path(new_path))

    def _on_note_saved(self, path: str) -> None:
        note_path = Path(path)
        self.save_status_label.setText("Saved ✓")
        # Incremental index update
        self.vault_index.update_note(note_path)
        if self.search_engine:
            self.search_engine.update_note(note_path)
        self._update_backlinks()
        self._update_tags()
        if self.vault:
            self.graph_view.set_graph(self.vault, self.vault_index)
        self._update_todo_file()

    def _update_word_count(self) -> None:
        text = self.editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        self.word_count_label.setText(f"{words} words")

    def _update_backlinks(self) -> None:
        current = self.editor.current_note
        if current:
            backlinks = self.vault_index.get_backlinks(current)
            self.backlinks_panel.set_backlinks(backlinks)
        else:
            self.backlinks_panel.set_backlinks([])

    def _update_tags(self) -> None:
        tags = self.vault_index.get_all_tags()
        self.tag_panel.set_tags(tags)

    def _update_todo_file(self) -> None:
        """Regenerate the .TODO file from all checkboxes in the vault."""
        if not self.vault:
            return
        from core.markdown_parser import extract_todos
        from datetime import datetime

        import re
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        todos_by_note: dict[Path, list[str]] = {}
        for note_path in self.vault.list_notes():
            try:
                text = note_path.read_text(encoding="utf-8")
                items = extract_todos(text)
                if items:
                    todos_by_note[note_path] = items
            except (OSError, UnicodeDecodeError):
                pass

        lines = ["# TODO", "", f"_Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
        if not todos_by_note:
            lines.append("_No se encontraron tareas en el vault._")
        else:
            non_journal = {p: items for p, items in todos_by_note.items() if not date_re.match(p.stem)}
            journal = {p: items for p, items in todos_by_note.items() if date_re.match(p.stem)}

            for note_path in sorted(non_journal, key=lambda p: p.stem.lower()):
                lines.append(f"#### [[{note_path.stem}]]")
                lines.append("")
                lines.extend(non_journal[note_path])
                lines.append("")

            for note_path in sorted(journal, key=lambda p: p.stem, reverse=True):
                lines.append(f"#### [[{note_path.stem}]]")
                lines.append("")
                lines.extend(journal[note_path])
                lines.append("")
        new_content = "\n".join(lines)

        # Only write and refresh if the content actually changed (ignoring the timestamp line)
        try:
            old_content = self.vault.todo_file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            old_content = ""

        # Strip the timestamp line for comparison so minute-by-minute changes don't cause reloads
        def _strip_timestamp(text: str) -> str:
            return "\n".join(
                line for line in text.splitlines()
                if not line.startswith("_Actualizado:")
            )

        if _strip_timestamp(new_content) == _strip_timestamp(old_content):
            return

        self.vault.write_todo_file(new_content)

        # Refresh the editor if .TODO is currently open, preserving scroll position
        if self.editor.current_note == self.vault.todo_file_path:
            scrollbar = self.editor.verticalScrollBar()
            scroll_pos = scrollbar.value() if scrollbar else 0
            self.editor.open_note(self.vault.todo_file_path)
            if scrollbar:
                scrollbar.setValue(scroll_pos)

    def _open_todo(self) -> None:
        """Toggle .TODO: open it if not current, or return to previous note if it is."""
        if not self.vault:
            return
        if self.editor.current_note == self.vault.todo_file_path:
            # Already viewing .TODO — go back to the previous note
            if self._pre_todo_note and self._pre_todo_note.exists():
                self._on_note_selected(self._pre_todo_note)
            self._pre_todo_note = None
        else:
            # Save current note as the one to return to
            self._pre_todo_note = self.editor.current_note
            self._update_todo_file()
            self._on_note_selected(self.vault.todo_file_path)

    def _on_wikilink_clicked(self, target: str) -> None:
        if not self.vault:
            return
        note_path = self.vault.resolve_note(target)
        if note_path is None:
            # Create the note
            note_path = self.vault.create_note(target)
            self.file_tree.refresh()
        self._on_note_selected(note_path)

    def _on_tag_clicked(self, tag: str) -> None:
        notes = self.vault_index.get_notes_for_tag(tag)
        if self.search_engine:
            self.vault_search_panel.set_search_engine(self.search_engine)
        self.vault_search_panel.show_tag_results(tag, notes)
        self.right_sidebar.setVisible(True)
        self._expand_search_section()

    def _on_tag_at_cursor(self, tag: str) -> None:
        """Update tag panel selection and (if Search is expanded) search results."""
        self.tag_panel.highlight_tag(tag)
        if not tag:
            return
        # Only update search panel if the Search section is already expanded
        search_section = next(
            (s for s in self.right_sidebar._sections if s.content is self.vault_search_panel),
            None,
        )
        if search_section and self.right_sidebar.isVisible():
            notes = self.vault_index.get_notes_for_tag(tag)
            if self.search_engine:
                self.vault_search_panel.set_search_engine(self.search_engine)
            self.vault_search_panel.show_tag_results(tag, notes)
            if not search_section.is_expanded:
                self._expand_search_section()

    # --- New note ---

    def _new_note(self) -> None:
        if not self.vault:
            return
        name, ok = QInputDialog.getText(self, "New Note", "Note name:")
        if ok and name.strip():
            note_path = self.vault.create_note(name.strip(), self.vault.path)
            self.file_tree.refresh()
            self._on_note_selected(note_path)

    # --- Search ---

    def _quick_open(self) -> None:
        if not self.vault:
            return
        dialog = SearchDialog(self.vault, self)
        dialog.note_selected.connect(self._on_note_selected)
        dialog.exec()

    def _vault_search(self) -> None:
        if not self.vault or not self.search_engine:
            return
        self.vault_search_panel.set_search_engine(self.search_engine)
        self.right_sidebar.setVisible(True)
        self._expand_search_section()
        self.vault_search_panel.focus_search()
