"""Persistent configuration for Bedrock."""

import json
from pathlib import Path
from typing import Any


CONFIG_DIR = Path.home() / ".config" / "bedrock"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_HOTKEYS: dict[str, str] = {
    "toggle_left_sidebar": "Ctrl+\\",
    "toggle_right_sidebar": "Ctrl+Shift+\\",
    "new_note": "Ctrl+N",
    "quick_open": "Ctrl+P",
    "vault_search": "Ctrl+Shift+F",
    "find": "Ctrl+F",
    "change_vault": "Ctrl+Shift+O",
    "today_journal": "Ctrl+D",
    "settings": "Ctrl+,",
    "graph_maximize": "Ctrl+G",
    "open_todo": "Ctrl+Ntilde",
}

HOTKEY_LABELS: dict[str, str] = {
    "toggle_left_sidebar": "Toggle left sidebar",
    "toggle_right_sidebar": "Toggle right sidebar",
    "new_note": "New note",
    "quick_open": "Quick open (by filename)",
    "vault_search": "Search in vault (full text)",
    "find": "Find / Search",
    "change_vault": "Change vault",
    "today_journal": "Open today's journal",
    "settings": "Open settings",
    "graph_maximize": "Toggle graph (maximize / restore)",
    "open_todo": "Open TODO",
}

_DEFAULTS: dict[str, Any] = {
    "last_vault": None,
    "recent_vaults": [],
    "window_geometry": None,
    "window_state": None,
    "hotkeys": {},
}


class Config:
    """Load/save application config from ~/.config/bedrock/config.json."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self._load()

    def _load(self) -> None:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    @property
    def last_vault(self) -> str | None:
        return self._data.get("last_vault")

    @last_vault.setter
    def last_vault(self, path: str | None) -> None:
        self._data["last_vault"] = path
        if path:
            recents = self._data.get("recent_vaults", [])
            if path in recents:
                recents.remove(path)
            recents.insert(0, path)
            self._data["recent_vaults"] = recents[:10]
        self.save()

    @property
    def recent_vaults(self) -> list[str]:
        return self._data.get("recent_vaults", [])

    def get_hotkeys(self) -> dict[str, str]:
        """Return effective hotkeys (user overrides merged with defaults)."""
        return {**DEFAULT_HOTKEYS, **self._data.get("hotkeys", {})}

    def set_hotkeys(self, hotkeys: dict[str, str]) -> None:
        """Save only user-overridden hotkeys (keys that differ from defaults)."""
        overrides = {k: v for k, v in hotkeys.items() if v != DEFAULT_HOTKEYS.get(k)}
        self._data["hotkeys"] = overrides
        self.save()
