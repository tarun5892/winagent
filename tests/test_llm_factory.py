"""Tests for the LLM provider factory: provider/model resolution and
selection of the right client class."""
from __future__ import annotations

from pathlib import Path

import pytest

from winagent import llm_base


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate user_config writes/reads to a tmp dir and clear provider env."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for v in (
        "WINAGENT_PROVIDER",
        "WINAGENT_MODEL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "MISTRAL_API_KEY",
        "MISTRAL_MODEL",
    ):
        monkeypatch.delenv(v, raising=False)
    return tmp_path


# -----------------------------------------------------------------------------
# normalize / resolve_provider
# -----------------------------------------------------------------------------
def test_normalize_provider_known() -> None:
    assert llm_base.normalize_provider("openrouter") == "openrouter"
    assert llm_base.normalize_provider("OpenRouter") == "openrouter"


def test_normalize_provider_unknown_falls_back_to_gemini() -> None:
    assert llm_base.normalize_provider("nonsense") == "gemini"
    assert llm_base.normalize_provider("") == "gemini"
    assert llm_base.normalize_provider(None) == "gemini"


def test_resolve_provider_explicit_wins(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WINAGENT_PROVIDER", "groq")
    assert llm_base.resolve_provider("mistral") == "mistral"


def test_resolve_provider_env_then_disk_then_default(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from winagent import user_config

    # 1. Default
    assert llm_base.resolve_provider() == "gemini"

    # 2. From disk
    user_config.set_provider("openrouter")
    assert llm_base.resolve_provider() == "openrouter"

    # 3. Env wins over disk
    monkeypatch.setenv("WINAGENT_PROVIDER", "groq")
    assert llm_base.resolve_provider() == "groq"


# -----------------------------------------------------------------------------
# resolve_model
# -----------------------------------------------------------------------------
def test_resolve_model_default(isolated_config: Path) -> None:
    assert llm_base.resolve_model("gemini") == llm_base.DEFAULT_MODELS["gemini"]
    assert llm_base.resolve_model("groq") == llm_base.DEFAULT_MODELS["groq"]


def test_resolve_model_explicit_wins(isolated_config: Path) -> None:
    assert llm_base.resolve_model("groq", "my-model") == "my-model"


def test_resolve_model_per_provider_env(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.5")
    assert llm_base.resolve_model("openrouter") == "anthropic/claude-3.5"


def test_resolve_model_generic_env(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WINAGENT_MODEL", "global-default")
    assert llm_base.resolve_model("groq") == "global-default"


def test_resolve_model_per_provider_env_beats_generic(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WINAGENT_MODEL", "global-default")
    monkeypatch.setenv("MISTRAL_MODEL", "mistral-specific")
    assert llm_base.resolve_model("mistral") == "mistral-specific"


def test_resolve_model_disk_persisted(isolated_config: Path) -> None:
    from winagent import user_config

    user_config.set_provider_model("groq", "llama-fast")
    assert llm_base.resolve_model("groq") == "llama-fast"


# -----------------------------------------------------------------------------
# make_client
# -----------------------------------------------------------------------------
def test_make_client_returns_gemini(
    isolated_config: Path, fake_genai, monkeypatch: pytest.MonkeyPatch
) -> None:
    from winagent.gemini_client import GeminiClient

    client = llm_base.make_client(
        provider="gemini", api_key="key", model="models/x"
    )
    assert isinstance(client, GeminiClient)


def test_make_client_returns_openai_compat_for_openrouter(
    isolated_config: Path, fake_openai
) -> None:
    from winagent.openai_compat_client import OpenAICompatClient

    client = llm_base.make_client(
        provider="openrouter", api_key="key", model="any-model"
    )
    assert isinstance(client, OpenAICompatClient)
    assert fake_openai.last_client.base_url == "https://openrouter.ai/api/v1"


def test_make_client_returns_openai_compat_for_groq(
    isolated_config: Path, fake_openai
) -> None:
    from winagent.openai_compat_client import OpenAICompatClient

    client = llm_base.make_client(provider="groq", api_key="key")
    assert isinstance(client, OpenAICompatClient)
    assert fake_openai.last_client.base_url == "https://api.groq.com/openai/v1"


def test_make_client_returns_openai_compat_for_mistral(
    isolated_config: Path, fake_openai
) -> None:
    from winagent.openai_compat_client import OpenAICompatClient

    client = llm_base.make_client(provider="mistral", api_key="key")
    assert isinstance(client, OpenAICompatClient)
    assert fake_openai.last_client.base_url == "https://api.mistral.ai/v1"


def test_make_client_default_uses_resolved_provider(
    isolated_config: Path, fake_openai, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``make_client()`` with no args should pick the persisted provider."""
    from winagent import user_config

    user_config.set_provider("groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")

    from winagent.openai_compat_client import OpenAICompatClient

    client = llm_base.make_client()
    assert isinstance(client, OpenAICompatClient)
