"""Tests for the persistent user-config (Gemini API key on disk)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from winagent import user_config


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect APPDATA / XDG_CONFIG_HOME to a tmp dir and clear env."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return tmp_path


def test_config_dir_windows_uses_appdata(fake_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "platform", "win32")
    d = user_config.config_dir()
    assert d.parent.name == "appdata"
    assert d.name == "WinAgent"


def test_config_dir_posix_uses_xdg(fake_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "platform", "linux")
    d = user_config.config_dir()
    assert d.parent.name == "xdg"
    assert d.name == "winagent"


def test_load_returns_empty_when_missing(fake_home: Path):
    assert user_config.load() == {}


def test_load_returns_empty_when_corrupt(fake_home: Path):
    p = user_config.config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json", encoding="utf-8")
    assert user_config.load() == {}


def test_save_roundtrip(fake_home: Path):
    p = user_config.save({"gemini_api_key": "abc", "x": 1})
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8")) == {"gemini_api_key": "abc", "x": 1}
    assert user_config.load() == {"gemini_api_key": "abc", "x": 1}


def test_get_api_key_prefers_env_over_disk(fake_home: Path, monkeypatch: pytest.MonkeyPatch):
    user_config.save({"gemini_api_key": "from-disk"})
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert user_config.get_api_key() == "from-env"


def test_get_api_key_falls_back_to_disk(fake_home: Path):
    user_config.save({"gemini_api_key": "from-disk"})
    assert user_config.get_api_key() == "from-disk"


def test_get_api_key_returns_none_when_unset(fake_home: Path):
    assert user_config.get_api_key() is None


def test_set_api_key_persists_and_updates_env(fake_home: Path):
    p = user_config.set_api_key("  my-key  ")
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["gemini_api_key"] == "my-key"
    assert os.environ.get("GEMINI_API_KEY") == "my-key"


def test_set_api_key_rejects_empty(fake_home: Path):
    with pytest.raises(ValueError):
        user_config.set_api_key("   ")


def test_save_preserves_other_keys(fake_home: Path):
    user_config.save({"gemini_api_key": "k1", "extra": True})
    user_config.set_api_key("k2")
    data = user_config.load()
    assert data["gemini_api_key"] == "k2"
    assert data["extra"] is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_save_sets_user_only_perms(fake_home: Path):
    p = user_config.set_api_key("k")
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600


# ---------------------------------------------------------------------------
# Multi-provider helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_provider_env(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    for v in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    return fake_home


def test_get_provider_default(isolated_provider_env: Path):
    assert user_config.get_provider() == "gemini"


def test_set_and_get_provider_roundtrip(isolated_provider_env: Path):
    user_config.set_provider("groq")
    assert user_config.get_provider() == "groq"


def test_set_provider_rejects_unknown(isolated_provider_env: Path):
    with pytest.raises(ValueError):
        user_config.set_provider("nonsense")


def test_get_provider_falls_back_when_value_invalid(
    isolated_provider_env: Path,
):
    user_config.save({"provider": "garbage"})
    assert user_config.get_provider() == "gemini"


def test_set_and_get_provider_api_key_roundtrip(isolated_provider_env: Path):
    user_config.set_provider_api_key("openrouter", "  or-key  ")
    assert user_config.get_provider_api_key("openrouter") == "or-key"
    assert os.environ.get("OPENROUTER_API_KEY") == "or-key"


def test_set_provider_api_key_rejects_empty(isolated_provider_env: Path):
    with pytest.raises(ValueError):
        user_config.set_provider_api_key("groq", "   ")


def test_set_provider_api_key_rejects_unknown_provider(
    isolated_provider_env: Path,
):
    with pytest.raises(ValueError):
        user_config.set_provider_api_key("totally-unknown", "k")


def test_get_provider_api_key_env_wins_over_disk(
    isolated_provider_env: Path, monkeypatch: pytest.MonkeyPatch
):
    user_config.set_provider_api_key("groq", "from-disk")
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert user_config.get_provider_api_key("groq") == "from-env"


def test_legacy_gemini_field_still_resolves(isolated_provider_env: Path):
    """Old PR #3 configs stored ``gemini_api_key`` flat — must still load."""
    user_config.save({"gemini_api_key": "legacy"})
    assert user_config.get_provider_api_key("gemini") == "legacy"
    assert user_config.get_api_key() == "legacy"


def test_set_gemini_key_mirrors_legacy_field(isolated_provider_env: Path):
    """Setting the gemini key writes BOTH the nested + legacy field."""
    user_config.set_provider_api_key("gemini", "k")
    data = user_config.load()
    assert data["gemini_api_key"] == "k"
    assert data["providers"]["gemini"]["api_key"] == "k"


def test_set_and_get_provider_model_roundtrip(isolated_provider_env: Path):
    user_config.set_provider_model("groq", "llama-fast")
    assert user_config.get_provider_model("groq") == "llama-fast"


def test_provider_keys_are_independent(isolated_provider_env: Path):
    user_config.set_provider_api_key("openrouter", "or-key")
    user_config.set_provider_api_key("groq", "groq-key")
    user_config.set_provider_api_key("mistral", "mistral-key")
    assert user_config.get_provider_api_key("openrouter") == "or-key"
    assert user_config.get_provider_api_key("groq") == "groq-key"
    assert user_config.get_provider_api_key("mistral") == "mistral-key"
