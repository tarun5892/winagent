"""Cross-platform persistent user config (provider, API keys, model).

Resolution order for the *Gemini* API key (PR #3 backwards compat):
1. ``GEMINI_API_KEY`` environment variable
2. The persisted JSON file (key ``gemini_api_key`` or ``providers.gemini.api_key``)
3. ``None`` — caller decides whether to prompt the user.

Resolution order for any provider's key (PR #4):
1. The provider's env var (e.g. ``OPENROUTER_API_KEY``)
2. The persisted JSON file under ``providers.<provider>.api_key``
3. The legacy ``gemini_api_key`` field (only when *provider* is ``"gemini"``)
4. ``None``

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

# Per-provider env var name. Keep in sync with
# :data:`winagent.llm_base.PROVIDER_KEY_ENV` (we duplicate here to avoid an
# import cycle: ``llm_base`` already imports this module).
PROVIDER_KEY_ENV: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


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


# ---------------------------------------------------------------------------
# Legacy single-provider API (Gemini-only, kept for backwards compatibility)
# ---------------------------------------------------------------------------
def get_api_key() -> str | None:
    """Resolve the Gemini API key: env var → saved config → ``None``.

    Kept for callers that predate multi-provider support.
    """
    return get_provider_api_key("gemini")


def set_api_key(key: str) -> Path:
    """Persist *key* as the Gemini API key and refresh the env var."""
    return set_provider_api_key("gemini", key)


# ---------------------------------------------------------------------------
# Multi-provider API
# ---------------------------------------------------------------------------
def get_provider() -> str:
    """Return the persisted provider, or ``"gemini"`` by default."""
    saved = load().get("provider")
    if isinstance(saved, str) and saved.strip():
        p = saved.strip().lower()
        if p in PROVIDER_KEY_ENV:
            return p
    return "gemini"


def set_provider(provider: str) -> Path:
    """Persist the active provider."""
    p = provider.strip().lower()
    if p not in PROVIDER_KEY_ENV:
        raise ValueError(f"unknown provider {provider!r}")
    data = load()
    data["provider"] = p
    return save(data)


def get_provider_api_key(provider: str) -> str | None:
    """Resolve the API key for *provider*: env var → saved config → ``None``."""
    p = provider.strip().lower()
    env_name = PROVIDER_KEY_ENV.get(p)
    if env_name:
        env_value = os.environ.get(env_name)
        if env_value:
            return env_value
    data = load()
    nested = data.get("providers")
    if isinstance(nested, dict):
        bucket = nested.get(p)
        if isinstance(bucket, dict):
            saved = bucket.get("api_key")
            if isinstance(saved, str) and saved.strip():
                return saved.strip()
    # Legacy: PR #3 stored Gemini key flat under ``gemini_api_key``.
    if p == "gemini":
        legacy = data.get("gemini_api_key")
        if isinstance(legacy, str) and legacy.strip():
            return legacy.strip()
    return None


def set_provider_api_key(provider: str, key: str) -> Path:
    """Persist *key* for *provider* and refresh the env var."""
    p = provider.strip().lower()
    if p not in PROVIDER_KEY_ENV:
        raise ValueError(f"unknown provider {provider!r}")
    key = key.strip()
    if not key:
        raise ValueError("API key cannot be empty")
    data = load()
    nested = data.get("providers")
    if not isinstance(nested, dict):
        nested = {}
    bucket = nested.get(p)
    if not isinstance(bucket, dict):
        bucket = {}
    bucket["api_key"] = key
    nested[p] = bucket
    data["providers"] = nested
    # Legacy mirror so older builds keep working.
    if p == "gemini":
        data["gemini_api_key"] = key
    path = save(data)
    env_name = PROVIDER_KEY_ENV[p]
    os.environ[env_name] = key
    return path


def get_provider_model(provider: str) -> str | None:
    """Return the persisted model override for *provider*, or ``None``."""
    p = provider.strip().lower()
    data = load()
    nested = data.get("providers")
    if isinstance(nested, dict):
        bucket = nested.get(p)
        if isinstance(bucket, dict):
            saved = bucket.get("model")
            if isinstance(saved, str) and saved.strip():
                return saved.strip()
    return None


def set_provider_model(provider: str, model: str) -> Path:
    """Persist a per-provider model override."""
    p = provider.strip().lower()
    if p not in PROVIDER_KEY_ENV:
        raise ValueError(f"unknown provider {provider!r}")
    model = model.strip()
    data = load()
    nested = data.get("providers")
    if not isinstance(nested, dict):
        nested = {}
    bucket = nested.get(p)
    if not isinstance(bucket, dict):
        bucket = {}
    if model:
        bucket["model"] = model
    else:
        bucket.pop("model", None)
    nested[p] = bucket
    data["providers"] = nested
    return save(data)
