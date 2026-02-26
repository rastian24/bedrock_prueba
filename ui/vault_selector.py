"""Vault selector dialog shown at startup."""

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFileDialog,
)
from PySide6.QtCore import Qt


class VaultSelectorDialog(QDialog):
    """Dialog to open or create a vault."""

    def __init__(self, recent_vaults: list[str], parent=None) -> None:
        super().__init__(parent)
        self.selected_path: str | None = None
        self.setWindowTitle("Bedrock — Open Vault")
        self.setFixedSize(480, 400)
        self._setup_ui(recent_vaults)

    def _setup_ui(self, recent_vaults: list[str]) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel("Bedrock")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #7f6df2;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Open or create a vault to get started")
        subtitle.setStyleSheet("color: #999999; font-size: 13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Buttons
        btn_layout = QHBoxLayout()

        open_btn = QPushButton("Open Existing Vault")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open_existing)
        btn_layout.addWidget(open_btn)

        create_btn = QPushButton("Create New Vault")
        create_btn.clicked.connect(self._create_new)
        btn_layout.addWidget(create_btn)

        layout.addLayout(btn_layout)

        # Recent vaults
        if recent_vaults:
            header = QLabel("RECENT VAULTS")
            header.setObjectName("section_header")
            layout.addWidget(header)

            self.recent_list = QListWidget()
            for vault_path in recent_vaults:
                p = Path(vault_path)
                if p.is_dir():
                    item = QListWidgetItem(f"{p.name}\n{vault_path}")
                    item.setData(Qt.ItemDataRole.UserRole, vault_path)
                    self.recent_list.addItem(item)
            self.recent_list.itemDoubleClicked.connect(self._on_recent_selected)
            layout.addWidget(self.recent_list)
        else:
            layout.addStretch()

    def _open_existing(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Vault Folder")
        if path:
            self.selected_path = path
            self.accept()

    def _create_new(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Location for New Vault")
        if path:
            self.selected_path = path
            self.accept()

    def _on_recent_selected(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).is_dir():
            self.selected_path = path
            self.accept()
