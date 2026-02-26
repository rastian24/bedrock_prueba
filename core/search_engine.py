"""Full-text search engine using Whoosh."""

from pathlib import Path

from whoosh import index
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.analysis import StemmingAnalyzer
from whoosh.highlight import UppercaseFormatter


SCHEMA = Schema(
    path=ID(stored=True, unique=True),
    title=TEXT(stored=True),
    content=TEXT(stored=True, analyzer=StemmingAnalyzer()),
)


class SearchEngine:
    """Whoosh-based full-text search over vault notes."""

    def __init__(self, index_dir: Path) -> None:
        self._index_dir = index_dir
        self._ix: index.Index | None = None

    def _ensure_index(self) -> index.Index:
        if self._ix is not None:
            return self._ix
        self._index_dir.mkdir(parents=True, exist_ok=True)
        if index.exists_in(str(self._index_dir)):
            self._ix = index.open_dir(str(self._index_dir))
        else:
            self._ix = index.create_in(str(self._index_dir), SCHEMA)
        return self._ix

    def build_index(self, notes: list[Path]) -> None:
        """Full rebuild of the search index."""
        ix = self._ensure_index()
        writer = ix.writer()
        for note in notes:
            try:
                content = note.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            writer.update_document(
                path=str(note),
                title=note.stem,
                content=content,
            )
        writer.commit()

    def update_note(self, note_path: Path) -> None:
        """Incrementally update a single note in the index."""
        ix = self._ensure_index()
        writer = ix.writer()
        try:
            content = note_path.read_text(encoding="utf-8")
            writer.update_document(
                path=str(note_path),
                title=note_path.stem,
                content=content,
            )
        except (OSError, UnicodeDecodeError):
            writer.delete_by_term("path", str(note_path))
        writer.commit()

    def remove_note(self, note_path: Path) -> None:
        """Remove a note from the index."""
        ix = self._ensure_index()
        writer = ix.writer()
        writer.delete_by_term("path", str(note_path))
        writer.commit()

    def search(self, query_str: str, limit: int = 50) -> list[dict]:
        """Search for notes matching the query.

        Returns list of {path, title, highlights} dicts.
        """
        ix = self._ensure_index()
        parser = MultifieldParser(["title", "content"], schema=ix.schema, group=OrGroup)
        try:
            query = parser.parse(query_str)
        except Exception:
            return []

        results = []
        with ix.searcher() as searcher:
            hits = searcher.search(query, limit=limit)
            hits.formatter = UppercaseFormatter()
            for hit in hits:
                results.append({
                    "path": hit["path"],
                    "title": hit["title"],
                    "highlights": hit.highlights("content", top=3) or "",
                })
        return results
