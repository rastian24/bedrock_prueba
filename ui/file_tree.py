"""File explorer sidebar with tree view."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QMenu, QInputDialog,
    QMessageBox, QLabel,
)
from PySide6.QtCore import (
    Qt, Signal, QSortFilterProxyModel, QModelIndex,
)
from PySide6.QtWidgets import QFileSystemModel
from PySide6.QtGui import QAction

from core.vault import Vault


class VaultFilterProxy(QSortFilterProxyModel):
    """Filter to show only .md files and directories, hiding .bedrock/."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, QFileSystemModel):
            return True
        idx = model.index(source_row, 0, source_parent)
        path = Path(model.filePath(idx))
        name = path.name

        # Hide hidden dirs (especially .bedrock)
        if name.startswith("."):
            return False

        # Accept directories
        if path.is_dir():
            return True

        # Accept only .md files
        return name.endswith(".md")


class FileTree(QWidget):
    """File explorer tree view for the vault."""

    note_selected = Signal(str)
    note_created = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vault: Vault | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("EXPLORER")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Tree view
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.clicked.connect(self._on_clicked)
        layout.addWidget(self.tree)

        # Model
        self.fs_model = QFileSystemModel()
        self.fs_model.setReadOnly(False)
        self.fs_model.setNameFilterDisables(False)

        self.proxy = VaultFilterProxy()
        self.proxy.setSourceModel(self.fs_model)
        self.tree.setModel(self.proxy)

    def set_vault(self, vault: Vault) -> None:
        """Set the vault and populate the tree."""
        self.vault = vault
        root_path = str(vault.path)
        self.fs_model.setRootPath(root_path)
        source_root = self.fs_model.index(root_path)
        proxy_root = self.proxy.mapFromSource(source_root)
        self.tree.setRootIndex(proxy_root)

        # Hide all columns except name
        for col in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(col)

    def select_note(self, path: Path) -> None:
        """Select and reveal a note in the tree."""
        source_idx = self.fs_model.index(str(path))
        proxy_idx = self.proxy.mapFromSource(source_idx)
        if proxy_idx.isValid():
            self.tree.setCurrentIndex(proxy_idx)
            self.tree.scrollTo(proxy_idx)

    def current_folder(self) -> Path | None:
        """Return the currently selected folder, or vault root."""
        idx = self.tree.currentIndex()
        if not idx.isValid():
            return self.vault.path if self.vault else None

        source_idx = self.proxy.mapToSource(idx)
        path = Path(self.fs_model.filePath(source_idx))
        return path if path.is_dir() else path.parent

    def refresh(self) -> None:
        """Force refresh of the model."""
        if self.vault:
            self.set_vault(self.vault)

    def _on_clicked(self, proxy_index: QModelIndex) -> None:
        source_idx = self.proxy.mapToSource(proxy_index)
        path = Path(self.fs_model.filePath(source_idx))
        if path.is_file() and path.suffix == ".md":
            self.note_selected.emit(str(path))

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)

        new_note_action = QAction("New Note", self)
        new_note_action.triggered.connect(self._new_note)
        menu.addAction(new_note_action)

        new_folder_action = QAction("New Folder", self)
        new_folder_action.triggered.connect(self._new_folder)
        menu.addAction(new_folder_action)

        menu.addSeparator()

        idx = self.tree.indexAt(pos)
        if idx.isValid():
            rename_action = QAction("Rename", self)
            rename_action.triggered.connect(lambda: self._rename(idx))
            menu.addAction(rename_action)

            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(lambda: self._delete(idx))
            menu.addAction(delete_action)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _new_note(self) -> None:
        if not self.vault:
            return
        name, ok = QInputDialog.getText(self, "New Note", "Note name:")
        if ok and name.strip():
            folder = self.current_folder()
            path = self.vault.create_note(name.strip(), folder)
            self._refresh_proxy()
            self.note_created.emit(str(path))

    def _new_folder(self) -> None:
        if not self.vault:
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            folder = self.current_folder()
            self.vault.create_folder(name.strip(), folder)
            self._refresh_proxy()

    def _rename(self, proxy_index: QModelIndex) -> None:
        if not self.vault:
            return
        source_idx = self.proxy.mapToSource(proxy_index)
        path = Path(self.fs_model.filePath(source_idx))
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=path.name)
        if ok and new_name.strip():
            self.vault.rename(path, new_name.strip())
            self._refresh_proxy()

    def _delete(self, proxy_index: QModelIndex) -> None:
        if not self.vault:
            return
        source_idx = self.proxy.mapToSource(proxy_index)
        path = Path(self.fs_model.filePath(source_idx))
        reply = QMessageBox.question(
            self, "Delete",
            f"Are you sure you want to delete '{path.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if path.is_dir():
                self.vault.delete_folder(path)
            else:
                self.vault.delete_note(path)
            self._refresh_proxy()

    def _refresh_proxy(self) -> None:
        """Force the proxy filter to re-evaluate so new/removed files appear immediately."""
        self.proxy.invalidateFilter()
