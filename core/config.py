"""Persistent configuration for Bedrock."""

import json
from pathlib import Path
from typing import Any


CONFIG_DIR = Path.home() / ".config" / "bedrock"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULTS: dict[str, Any] = {
    "last_vault": None,
    "recent_vaults": [],
    "window_geometry": None,
    "window_state": None,
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
