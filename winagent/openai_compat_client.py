"""OpenAI-compatible client used for OpenRouter, Groq, and Mistral.

All three providers expose an OpenAI-shaped ``/v1/chat/completions`` endpoint,
so we can drive them with one client and a per-provider ``base_url``. Multi-
modal input (screenshots) is included as an OpenAI ``image_url`` part with a
``data:image/jpeg;base64,...`` URI; providers that don't understand vision
will simply ignore it (and get a coding-only request, which is fine for the
Codex-alternative use case).

Strict JSON output is requested via ``response_format={"type": "json_object"}``
where supported; the prompt itself also instructs the model to output a single
JSON object, so providers that ignore the parameter still produce valid output
on every test we've run.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from .config import CONFIG
from .llm_base import (
    OPENAI_COMPAT_BASE_URLS,
    PROVIDER_KEY_ENV,
    StreamCallback,
    resolve_model,
)
from .logger import get_logger
from .prompts import build_system_instruction, build_user_prompt

log = get_logger("openai_compat")


class OpenAICompatClient:
    """OpenAI-compatible chat-completion client.

    Parameters
    ----------
    provider:
        One of ``"openrouter"``, ``"groq"``, ``"mistral"``. Used only to
        resolve the right env var / persisted key and base URL when those
        are not passed explicitly.
    api_key:
        Bearer token. Falls back to the per-provider env var, then to the
        persisted user config.
    model:
        Model identifier (e.g. ``"llama-3.3-70b-versatile"``). Falls back
        to :func:`winagent.llm_base.resolve_model`.
    streaming:
        If ``True``, requests a streamed response and forwards text chunks
        to ``on_chunk`` in :meth:`plan`.
    base_url:
        Base URL for the provider's OpenAI-compatible endpoint. Defaults to
        the entry in :data:`OPENAI_COMPAT_BASE_URLS` for *provider*.
    """

    def __init__(
        self,
        provider: str,
        api_key: str | None = None,
        model: str | None = None,
        streaming: bool | None = None,
        base_url: str | None = None,
    ) -> None:
        from openai import OpenAI

        from . import user_config

        self.provider = provider
        env_var = PROVIDER_KEY_ENV.get(provider, "")
        key = (
            api_key
            or os.environ.get(env_var, "")
            or user_config.get_provider_api_key(provider)
            or ""
        )
        if not key:
            raise RuntimeError(
                f"{env_var or provider.upper() + '_API_KEY'} not set"
            )
        self._base_url = base_url or OPENAI_COMPAT_BASE_URLS.get(provider, "")
        if not self._base_url:
            raise RuntimeError(f"no base_url known for provider {provider!r}")
        self._client = OpenAI(api_key=key, base_url=self._base_url)
        self.model = resolve_model(provider, model)
        self.streaming: bool = CONFIG.streaming if streaming is None else streaming

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan(
        self,
        command: str,
        screenshot_jpeg: bytes | None,
        screen_size: tuple[int, int],
        memory: dict[str, Any],
        on_chunk: StreamCallback | None = None,
    ) -> dict[str, Any]:
        """Return the parsed JSON plan for *command*."""
        prompt = build_user_prompt(command, screen_size, memory)
        user_content: list[dict[str, Any]] = []
        if screenshot_jpeg:
            b64 = base64.b64encode(screenshot_jpeg).decode("ascii")
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        user_content.append({"type": "text", "text": prompt})

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_instruction()},
            {"role": "user", "content": user_content},
        ]

        if self.streaming:
            text = self._chat_streaming(messages, on_chunk)
        else:
            text = self._chat_blocking(messages)

        text = (text or "").strip()
        if not text:
            raise RuntimeError(f"empty response from {self.provider}")
        # Some providers wrap JSON in ```json ... ``` fences despite the
        # response_format hint; strip those defensively before parsing.
        text = _strip_code_fences(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error("invalid JSON from %s: %s", self.provider, text[:500])
            raise RuntimeError(f"non-JSON response: {e}") from e

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _chat_blocking(self, messages: list[dict[str, Any]]) -> str:
        kwargs = self._common_kwargs(messages)
        resp = self._client.chat.completions.create(**kwargs)
        # ``resp.choices[0].message.content`` may be None on some providers
        # if the model emits a tool call instead; we treat that as empty.
        choice = resp.choices[0]
        content = getattr(choice.message, "content", None) or ""
        return content

    def _chat_streaming(
        self,
        messages: list[dict[str, Any]],
        on_chunk: StreamCallback | None,
    ) -> str:
        kwargs = self._common_kwargs(messages)
        kwargs["stream"] = True
        chunks: list[str] = []
        stream = self._client.chat.completions.create(**kwargs)
        for ev in stream:
            try:
                delta = ev.choices[0].delta
            except (AttributeError, IndexError):
                continue
            piece = getattr(delta, "content", None) or ""
            if not piece:
                continue
            chunks.append(piece)
            if on_chunk:
                try:
                    on_chunk(piece)
                except Exception:  # noqa: BLE001
                    log.exception("stream callback raised; continuing")
        return "".join(chunks)

    def _common_kwargs(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout": CONFIG.api_timeout_s,
        }
        # Mistral honours response_format json_object; OpenRouter forwards it
        # to the underlying model when supported; Groq supports it on most
        # models. Worst case the provider ignores the field — the prompt
        # itself already requires JSON output, which is robust enough.
        kwargs["response_format"] = {"type": "json_object"}
        return kwargs


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```json (or ```) fence and trailing ``` if present."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    # Drop the first line ("```json" or "```") and any trailing ```.
    first_newline = s.find("\n")
    if first_newline == -1:
        return s
    inner = s[first_newline + 1 :]
    if inner.endswith("```"):
        inner = inner[: -3]
    return inner.strip()
