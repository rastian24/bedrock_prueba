"""Unified vault index for backlinks, tags, and wikilink resolution."""

import threading
from pathlib import Path
from collections import defaultdict

from core.markdown_parser import extract_wikilinks, extract_tags


class VaultIndex:
    """Indexes all notes in a vault for backlinks, tags, and wikilinks.

    Thread-safe: all reads/writes go through a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # note_path -> list of wikilink targets (stems, lowercased)
        self._outgoing_links: dict[Path, list[str]] = {}
        # lowercased stem -> set of paths that link TO it
        self._backlinks: dict[str, set[Path]] = defaultdict(set)
        # note_path -> list of tags
        self._note_tags: dict[Path, list[str]] = {}
        # tag -> set of paths
        self._tag_index: dict[str, set[Path]] = defaultdict(set)

    def build(self, notes: list[Path]) -> None:
        """Full rebuild of the index from a list of note paths."""
        with self._lock:
            self._outgoing_links.clear()
            self._backlinks.clear()
            self._note_tags.clear()
            self._tag_index.clear()

            for note in notes:
                self._index_note_unlocked(note)

    def update_note(self, note_path: Path) -> None:
        """Incrementally update the index for a single note."""
        with self._lock:
            self._remove_note_unlocked(note_path)
            if note_path.exists():
                self._index_note_unlocked(note_path)

    def remove_note(self, note_path: Path) -> None:
        """Remove a note from the index."""
        with self._lock:
            self._remove_note_unlocked(note_path)

    def get_backlinks(self, note_path: Path) -> list[tuple[Path, str]]:
        """Get all notes that link to the given note, with context lines."""
        stem_lower = note_path.stem.lower()
        with self._lock:
            linking_paths = list(self._backlinks.get(stem_lower, set()))

        results = []
        for path in linking_paths:
            context = self._find_link_context(path, stem_lower)
            results.append((path, context))
        return sorted(results, key=lambda x: x[0].stem.lower())

    def get_all_tags(self) -> dict[str, int]:
        """Get all tags with their occurrence count."""
        with self._lock:
            return {tag: len(paths) for tag, paths in self._tag_index.items()}

    def get_notes_for_tag(self, tag: str) -> list[Path]:
        """Get all notes that contain a given tag."""
        with self._lock:
            return sorted(self._tag_index.get(tag, set()))

    def get_all_outgoing_links(self) -> dict[Path, list[str]]:
        """Return a snapshot of all outgoing links (note_path -> [target_stem])."""
        with self._lock:
            return {k: list(v) for k, v in self._outgoing_links.items()}

    def _index_note_unlocked(self, note_path: Path) -> None:
        """Index a single note (must be called with lock held)."""
        try:
            text = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return

        # Wikilinks
        wikilinks = extract_wikilinks(text)
        targets = [wl["target"].lower() for wl in wikilinks]
        self._outgoing_links[note_path] = targets
        for target in targets:
            self._backlinks[target].add(note_path)

        # Tags
        tags = extract_tags(text)
        self._note_tags[note_path] = tags
        for tag in tags:
            self._tag_index[tag].add(note_path)

    def _remove_note_unlocked(self, note_path: Path) -> None:
        """Remove a note from index (must be called with lock held)."""
        # Remove outgoing links
        old_targets = self._outgoing_links.pop(note_path, [])
        for target in old_targets:
            self._backlinks[target].discard(note_path)
            if not self._backlinks[target]:
                del self._backlinks[target]

        # Remove tags
        old_tags = self._note_tags.pop(note_path, [])
        for tag in old_tags:
            self._tag_index[tag].discard(note_path)
            if not self._tag_index[tag]:
                del self._tag_index[tag]

    @staticmethod
    def _find_link_context(note_path: Path, target_stem: str) -> str:
        """Find the first line containing a link to the target."""
        try:
            text = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

        for line in text.splitlines():
            if f"[[{target_stem}" in line.lower():
                return line.strip()
        return ""
