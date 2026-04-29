"""LLM provider abstraction.

The orchestrator only ever sees an :class:`LLMClient` — a tiny Protocol with a
single :meth:`plan` method that returns the parsed JSON response. Concrete
implementations live in:

* :mod:`winagent.gemini_client` — Google's ``google.generativeai`` SDK
* :mod:`winagent.openai_compat_client` — the OpenAI-compatible chat-completion
  API used by OpenRouter, Groq, and Mistral

Provider selection is driven by a single string ("gemini" / "openrouter" /
"groq" / "mistral"). Resolution order, highest priority first:

1. The ``provider`` argument passed to :func:`make_client`
2. ``WINAGENT_PROVIDER`` environment variable
3. The ``provider`` field in the persisted user config
4. The default (``"gemini"`` — preserves backwards compatibility)
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

# A short, ordered list of every provider the app understands.
PROVIDERS: tuple[str, ...] = ("gemini", "openrouter", "groq", "mistral")

# Stable, free-tier-friendly defaults per provider. The user may override
# these in the Settings dialog or via ``WINAGENT_MODEL`` / per-provider env
# vars (``OPENROUTER_MODEL`` etc.).
DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    # OpenRouter has many free routes; this one performs strongly on code.
    "openrouter": "deepseek/deepseek-chat-v3-0324:free",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-large-latest",
}

# Base URLs for the three OpenAI-compatible providers.
OPENAI_COMPAT_BASE_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}

# Friendly UI labels.
PROVIDER_LABELS: dict[str, str] = {
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter (300+ models, incl. free)",
    "groq": "Groq (fast, free tier)",
    "mistral": "Mistral",
}

# Direct links to each provider's API key page, used by the first-run dialog.
PROVIDER_KEY_URLS: dict[str, str] = {
    "gemini": "https://aistudio.google.com/app/apikey",
    "openrouter": "https://openrouter.ai/keys",
    "groq": "https://console.groq.com/keys",
    "mistral": "https://console.mistral.ai/api-keys/",
}

# Per-provider env var name for the API key. ``GEMINI_API_KEY`` is kept for
# backwards compatibility with PR #1/#2/#3 setups.
PROVIDER_KEY_ENV: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


# A streamed text chunk callback. Strict JSON cannot be parsed mid-stream, so
# this is purely for "thinking..." progress feedback in the GUI.
StreamCallback = Callable[[str], None]


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface every provider client must satisfy."""

    streaming: bool

    def plan(
        self,
        command: str,
        screenshot_jpeg: bytes | None,
        screen_size: tuple[int, int],
        memory: dict[str, Any],
        on_chunk: StreamCallback | None = None,
    ) -> dict[str, Any]:
        """Return the parsed JSON plan for *command*."""
        ...


def normalize_provider(provider: str | None) -> str:
    """Coerce *provider* to a known value (defaulting to ``gemini``)."""
    if not provider:
        return "gemini"
    p = provider.strip().lower()
    if p not in PROVIDERS:
        return "gemini"
    return p


def resolve_provider(explicit: str | None = None) -> str:
    """Pick the active provider using the documented resolution order."""
    if explicit:
        return normalize_provider(explicit)
    env = os.environ.get("WINAGENT_PROVIDER")
    if env:
        return normalize_provider(env)
    # Lazy import: avoids a circular import at module load time.
    from . import user_config

    saved = user_config.load().get("provider")
    if isinstance(saved, str) and saved.strip():
        return normalize_provider(saved)
    return "gemini"


def resolve_model(provider: str, explicit: str | None = None) -> str:
    """Pick the active model for *provider*."""
    if explicit:
        return explicit.strip()
    # Per-provider env overrides (e.g. ``OPENROUTER_MODEL``).
    per_provider_env = os.environ.get(f"{provider.upper()}_MODEL")
    if per_provider_env:
        return per_provider_env.strip()
    # Generic override.
    generic_env = os.environ.get("WINAGENT_MODEL")
    if generic_env:
        return generic_env.strip()
    # Persisted per-provider model.
    from . import user_config

    saved = user_config.get_provider_model(provider)
    if saved:
        return saved
    # Last-resort default.
    return DEFAULT_MODELS.get(provider, DEFAULT_MODELS["gemini"])


def make_client(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    streaming: bool | None = None,
) -> LLMClient:
    """Build the right client for the active provider.

    All arguments are optional — when omitted, values are resolved from env
    vars and the persisted user config (see module docstring).
    """
    p = resolve_provider(provider)
    m = resolve_model(p, model)
    if p == "gemini":
        from .gemini_client import GeminiClient

        return GeminiClient(api_key=api_key, model=m, streaming=streaming)

    # All other providers share one OpenAI-compatible implementation.
    from .openai_compat_client import OpenAICompatClient

    return OpenAICompatClient(
        provider=p,
        api_key=api_key,
        model=m,
        streaming=streaming,
        base_url=OPENAI_COMPAT_BASE_URLS[p],
    )
