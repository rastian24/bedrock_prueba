"""Vault management — read/write/list .md files in a folder."""

import datetime
import locale
from pathlib import Path


class Vault:
    """Wrapper around a vault directory with CRUD operations for notes and folders."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self._bedrock_dir = self.path / ".bedrock"

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def bedrock_dir(self) -> Path:
        self._bedrock_dir.mkdir(parents=True, exist_ok=True)
        return self._bedrock_dir

    def exists(self) -> bool:
        return self.path.is_dir()

    def create(self) -> None:
        """Create the vault directory if it doesn't exist."""
        self.path.mkdir(parents=True, exist_ok=True)
        self.bedrock_dir  # ensure .bedrock exists

    def list_notes(self) -> list[Path]:
        """Return all .md files in the vault, excluding .bedrock/."""
        notes = []
        for p in self.path.rglob("*.md"):
            if ".bedrock" not in p.parts:
                notes.append(p)
        return sorted(notes)

    def note_names(self) -> list[str]:
        """Return list of note names (stems) for autocomplete."""
        return [p.stem for p in self.list_notes()]

    def resolve_note(self, name: str) -> Path | None:
        """Resolve a wikilink name to a file path (case-insensitive)."""
        name_lower = name.lower().strip()
        for note in self.list_notes():
            if note.stem.lower() == name_lower:
                return note
        return None

    def create_note(self, name: str, folder: Path | None = None) -> Path:
        """Create a new .md file and return its path."""
        if not name.endswith(".md"):
            name = f"{name}.md"
        parent = folder if folder and folder.is_dir() else self.path
        note_path = parent / name
        note_path.touch()
        return note_path

    def create_folder(self, name: str, parent: Path | None = None) -> Path:
        """Create a new folder inside the vault."""
        base = parent if parent and parent.is_dir() else self.path
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def read_note(self, path: Path) -> str:
        """Read and return the contents of a note."""
        return path.read_text(encoding="utf-8")

    def write_note(self, path: Path, content: str) -> None:
        """Write content to a note file."""
        path.write_text(content, encoding="utf-8")

    def delete_note(self, path: Path) -> None:
        """Delete a note file."""
        if path.exists():
            path.unlink()

    def delete_folder(self, path: Path) -> None:
        """Delete a folder and its contents."""
        import shutil
        if path.exists() and path.is_dir():
            shutil.rmtree(path)

    def ensure_journal_note(self, date: datetime.date | None = None) -> Path:
        """Ensure a journal note exists for the given date and return its path.

        Creates the .journal/ directory and YYYY-MM-DD.md file if they don't exist.
        """
        if date is None:
            date = datetime.date.today()

        journal_dir = self.path / ".journal"
        journal_dir.mkdir(exist_ok=True)

        filename = date.strftime("%Y-%m-%d") + ".md"
        note_path = journal_dir / filename

        if not note_path.exists():
            # Format heading like "# 26 de febrero de 2026"
            try:
                old_locale = locale.getlocale(locale.LC_TIME)
                locale.setlocale(locale.LC_TIME, ("es_ES", "UTF-8"))
                heading = date.strftime("# %-d de %B de %Y")
                locale.setlocale(locale.LC_TIME, old_locale)
            except (locale.Error, ValueError):
                # Fallback: manual Spanish month names
                months = [
                    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
                ]
                heading = f"# {date.day} de {months[date.month]} de {date.year}"

            note_path.write_text(f"{heading}\n\n", encoding="utf-8")

        return note_path

    def rename(self, old_path: Path, new_name: str) -> Path:
        """Rename a file or folder."""
        new_path = old_path.parent / new_name
        old_path.rename(new_path)
        return new_path
