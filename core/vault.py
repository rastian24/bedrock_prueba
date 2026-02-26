"""Vault management — read/write/list .md files in a folder."""

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

    def rename(self, old_path: Path, new_name: str) -> Path:
        """Rename a file or folder."""
        new_path = old_path.parent / new_name
        old_path.rename(new_path)
        return new_path
