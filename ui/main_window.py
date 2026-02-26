"""Main application window with three-panel layout."""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QWidget, QVBoxLayout, QStatusBar,
    QLabel, QMessageBox, QInputDialog, QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray
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

        self.setWindowTitle("Bedrock")
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)

        self._setup_ui()
        self._setup_shortcuts()
        self._restore_geometry()

        # Open vault on start
        self._open_initial_vault()

    def _setup_ui(self) -> None:
        # Left sidebar with tabs
        self.left_sidebar = QTabWidget()
        self.left_sidebar.setObjectName("sidebar_left")

        # Explorer tab (file tree + tags)
        explorer_tab = QWidget()
        explorer_layout = QVBoxLayout(explorer_tab)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        explorer_layout.setSpacing(0)
        self.file_tree = FileTree()
        self.tag_panel = TagPanel()
        explorer_layout.addWidget(self.file_tree, stretch=3)
        explorer_layout.addWidget(self.tag_panel, stretch=1)

        # Journal tab
        self.journal_panel = JournalPanel()

        self.left_sidebar.addTab(explorer_tab, "Explorer")
        self.left_sidebar.addTab(self.journal_panel, "Journal")

        # Editor
        self.editor = WysiwygEditor()

        # Right sidebar
        self.right_sidebar = QWidget()
        self.right_sidebar.setObjectName("sidebar_right")
        right_layout = QVBoxLayout(self.right_sidebar)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.backlinks_panel = BacklinksPanel()
        right_layout.addWidget(self.backlinks_panel)

        # Vault search panel (hidden initially, replaces right sidebar content)
        self.vault_search_panel = VaultSearchPanel()
        self.vault_search_panel.setVisible(False)
        right_layout.addWidget(self.vault_search_panel)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_sidebar)
        self.splitter.addWidget(self.editor)
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
        self.editor.saved.connect(self._on_note_saved)
        self.editor.content_changed.connect(self._update_word_count)
        self.editor.wikilink_clicked.connect(self._on_wikilink_clicked)
        self.backlinks_panel.note_clicked.connect(self._on_note_selected)
        self.tag_panel.tag_clicked.connect(self._on_tag_clicked)
        self.journal_panel.note_clicked.connect(self._on_note_selected)
        self.vault_search_panel.note_clicked.connect(self._on_note_selected)

    def _setup_shortcuts(self) -> None:
        # Toggle left sidebar
        QShortcut(QKeySequence("Ctrl+\\"), self, self._toggle_left_sidebar)
        # Toggle right sidebar
        QShortcut(QKeySequence("Ctrl+Shift+\\"), self, self._toggle_right_sidebar)
        # New note
        QShortcut(QKeySequence("Ctrl+N"), self, self._new_note)
        # Quick open
        QShortcut(QKeySequence("Ctrl+P"), self, self._quick_open)
        # Vault search
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, self._vault_search)
        # Change vault
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, self._change_vault)
        # Open today's journal
        QShortcut(QKeySequence("Ctrl+D"), self, self._open_today_journal)

    def _toggle_left_sidebar(self) -> None:
        self.left_sidebar.setVisible(not self.left_sidebar.isVisible())

    def _toggle_right_sidebar(self) -> None:
        self.right_sidebar.setVisible(not self.right_sidebar.isVisible())

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
        self.file_label.setText(path.name)
        self._update_word_count()
        self._update_backlinks()

    def _on_note_saved(self, path: str) -> None:
        note_path = Path(path)
        self.save_status_label.setText("Saved ✓")
        # Incremental index update
        self.vault_index.update_note(note_path)
        if self.search_engine:
            self.search_engine.update_note(note_path)
        self._update_backlinks()
        self._update_tags()

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
        self.vault_search_panel.show_tag_results(tag, notes)
        self.vault_search_panel.setVisible(True)
        self.backlinks_panel.setVisible(False)
        self.right_sidebar.setVisible(True)

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
        self.vault_search_panel.setVisible(True)
        self.backlinks_panel.setVisible(False)
        self.right_sidebar.setVisible(True)
        self.vault_search_panel.focus_search()
