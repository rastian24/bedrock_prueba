"""Settings dialog with configurable hotkeys."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QKeySequenceEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence

from core.config import Config, HOTKEY_LABELS, DEFAULT_HOTKEYS

_DUPLICATE_STYLE = "QKeySequenceEdit { background-color: #5c2020; border: 1px solid #ff4444; }"
_NORMAL_STYLE = ""


class SettingsDialog(QDialog):
    """Settings dialog — hotkey configuration."""

    hotkeys_changed = Signal(dict)  # emits {action: keyseq_string}

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumSize(480, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QLabel("Keyboard Shortcuts")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Table: Action | Shortcut
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 180)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Hint label for duplicate warning
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #ff6b6b; font-size: 12px; padding: 2px 4px;")
        self.hint_label.setVisible(False)
        layout.addWidget(self.hint_label)

        # Buttons
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        # Track last known valid sequence per action (for revert on duplicate)
        self._prev_seqs: dict[str, str] = {}
        self._populate(config.get_hotkeys())

    def _populate(self, hotkeys: dict[str, str]) -> None:
        self.table.setRowCount(0)
        self._prev_seqs.clear()
        for action in DEFAULT_HOTKEYS:
            seq = hotkeys.get(action, DEFAULT_HOTKEYS[action])
            self._prev_seqs[action] = seq

            row = self.table.rowCount()
            self.table.insertRow(row)

            label_item = QTableWidgetItem(HOTKEY_LABELS.get(action, action))
            label_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            label_item.setData(Qt.ItemDataRole.UserRole, action)
            self.table.setItem(row, 0, label_item)

            editor = QKeySequenceEdit(QKeySequence(seq))
            editor.keySequenceChanged.connect(self._on_sequence_changed)
            self.table.setCellWidget(row, 1, editor)

        self._check_duplicates()

    def _on_sequence_changed(self, _=None) -> None:
        self._check_duplicates()

    def _check_duplicates(self) -> None:
        """Mark duplicate sequences red; update prev_seqs for valid rows."""
        seq_rows: dict[str, list[int]] = {}
        for row in range(self.table.rowCount()):
            seq = self.table.cellWidget(row, 1).keySequence().toString()
            if seq:
                seq_rows.setdefault(seq, []).append(row)

        has_duplicate = False
        for row in range(self.table.rowCount()):
            editor: QKeySequenceEdit = self.table.cellWidget(row, 1)
            seq = editor.keySequence().toString()
            is_dup = bool(seq and len(seq_rows.get(seq, [])) > 1)
            if is_dup:
                editor.setStyleSheet(_DUPLICATE_STYLE)
                editor.setToolTip("Already used by another action — will be reverted on save")
                has_duplicate = True
            else:
                editor.setStyleSheet(_NORMAL_STYLE)
                editor.setToolTip("")
                # Only update prev for non-duplicate rows
                if seq:
                    action = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    self._prev_seqs[action] = seq

        self.hint_label.setVisible(has_duplicate)
        if has_duplicate:
            self.hint_label.setText(
                "Shortcuts highlighted in red are duplicates and will be reverted on save."
            )

    def _reset_to_defaults(self) -> None:
        self._populate(DEFAULT_HOTKEYS)

    def _save(self) -> None:
        # Revert any still-duplicate entries to their previous valid value
        for row in range(self.table.rowCount()):
            editor: QKeySequenceEdit = self.table.cellWidget(row, 1)
            if editor.styleSheet() == _DUPLICATE_STYLE:
                action = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                prev = self._prev_seqs.get(action, DEFAULT_HOTKEYS.get(action, ""))
                editor.setKeySequence(QKeySequence(prev))

        hotkeys = {
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole):
            self.table.cellWidget(row, 1).keySequence().toString()
            for row in range(self.table.rowCount())
        }
        self.config.set_hotkeys(hotkeys)
        self.hotkeys_changed.emit(hotkeys)
        self.accept()
