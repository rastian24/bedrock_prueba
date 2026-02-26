"""Markdown parsing and extraction of wikilinks/tags."""

from core import patterns


def extract_wikilinks(text: str) -> list[dict[str, str]]:
    """Extract all wikilinks from text. Returns list of {target, alias}."""
    results = []
    for match in patterns.WIKILINK.finditer(text):
        target = match.group(1).strip()
        alias = match.group(2)
        results.append({
            "target": target,
            "alias": alias.strip() if alias else None,
        })
    return results


def extract_tags(text: str) -> list[str]:
    """Extract all #tags from text."""
    return [m.group(1) for m in patterns.TAG.finditer(text)]
