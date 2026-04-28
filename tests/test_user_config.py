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
