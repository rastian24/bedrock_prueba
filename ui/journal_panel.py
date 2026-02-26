"""Journal panel listing journal entries by date."""

import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QCalendarWidget,
)
from PySide6.QtCore import Signal, Qt, QDate
from PySide6.QtGui import QTextCharFormat, QColor

from core.vault import Vault


class JournalPanel(QWidget):
    """Panel showing a calendar, 'Today' button, and a list of journal entries."""

    note_clicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vault: Vault | None = None
        self._journal_dates: set[datetime.date] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Today button
        self.today_btn = QPushButton("Today")
        self.today_btn.setObjectName("journal_today_btn")
        self.today_btn.clicked.connect(self._open_today)
        layout.addWidget(self.today_btn)

        # Calendar
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.clicked.connect(self._on_date_clicked)
        self.calendar.activated.connect(self._on_date_activated)
        layout.addWidget(self.calendar)

        # List of journal entries
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

    def set_vault(self, vault: Vault) -> None:
        """Set the vault and populate journal entries."""
        self.vault = vault
        self.refresh()

    def refresh(self) -> None:
        """Rescan the journal folder and repopulate the list and calendar highlights."""
        self.list_widget.clear()
        self._journal_dates.clear()
        if not self.vault:
            return

        journal_dir = self.vault.path / "journal"
        if not journal_dir.is_dir():
            return

        # Collect journal .md files with date-parseable names
        entries: list[tuple[datetime.date, Path]] = []
        for f in journal_dir.glob("*.md"):
            try:
                date = datetime.date.fromisoformat(f.stem)
                entries.append((date, f))
                self._journal_dates.add(date)
            except ValueError:
                continue

        # Sort newest first
        entries.sort(key=lambda e: e[0], reverse=True)

        for date, path in entries:
            label = self._format_date(date)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list_widget.addItem(item)

        self._highlight_calendar_dates()

    def _highlight_calendar_dates(self) -> None:
        """Highlight dates that have journal entries on the calendar."""
        # Reset all dates to default format
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

        # Highlight dates with entries
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#3a3a5c"))
        fmt.setForeground(QColor("#7f6df2"))
        for date in self._journal_dates:
            qdate = QDate(date.year, date.month, date.day)
            self.calendar.setDateTextFormat(qdate, fmt)

    def _format_date(self, date: datetime.date) -> str:
        """Format a date as a human-readable Spanish string."""
        months = [
            "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        ]
        return f"{date.day} de {months[date.month]} de {date.year}"

    def _open_today(self) -> None:
        """Open or create today's journal note."""
        if not self.vault:
            return
        path = self.vault.ensure_journal_note()
        self.calendar.setSelectedDate(QDate.currentDate())
        self.refresh()
        self.note_clicked.emit(str(path))

    def _on_date_clicked(self, qdate: QDate) -> None:
        """Open a journal note if one exists for the clicked date."""
        if not self.vault:
            return
        date = datetime.date(qdate.year(), qdate.month(), qdate.day())
        if date in self._journal_dates:
            path = self.vault.path / "journal" / f"{date.isoformat()}.md"
            self.note_clicked.emit(str(path))

    def _on_date_activated(self, qdate: QDate) -> None:
        """Open or create a journal note for the double-clicked date."""
        if not self.vault:
            return
        date = datetime.date(qdate.year(), qdate.month(), qdate.day())
        path = self.vault.ensure_journal_note(date)
        self.refresh()
        self.note_clicked.emit(str(path))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.note_clicked.emit(path)
