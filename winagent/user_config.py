"""Cross-platform persistent user config (e.g. saved Gemini API key).

Resolution order for a value (e.g. the API key):
1. The matching environment variable (e.g. ``GEMINI_API_KEY``)
2. The persisted JSON file at :func:`config_path`
3. ``None`` — caller decides whether to prompt the user.

The file is stored at ``%APPDATA%\\WinAgent\\config.json`` on Windows and
``~/.config/winagent/config.json`` elsewhere. Permissions are best-effort
restricted to the current user (``0o600``) on POSIX.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def config_dir() -> Path:
    """Return the directory in which ``config.json`` lives."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "WinAgent"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "winagent"


def config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict[str, Any]:
    """Return the persisted config. ``{}`` if the file is missing/unreadable."""
    p = config_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}


def save(data: dict[str, Any]) -> Path:
    """Atomically persist *data* to :func:`config_path` and return the path."""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)
    if sys.platform != "win32":
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return p


def get_api_key() -> str | None:
    """Resolve the Gemini API key: env var → saved config → ``None``."""
    env = os.environ.get("GEMINI_API_KEY")
    if env:
        return env
    saved = load().get("gemini_api_key")
    if isinstance(saved, str) and saved.strip():
        return saved.strip()
    return None


def set_api_key(key: str) -> Path:
    """Persist *key* to the on-disk config and refresh the env var."""
    key = key.strip()
    if not key:
        raise ValueError("API key cannot be empty")
    data = load()
    data["gemini_api_key"] = key
    path = save(data)
    os.environ["GEMINI_API_KEY"] = key
    return path
