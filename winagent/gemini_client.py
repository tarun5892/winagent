"""Gemini 2.5 Pro multimodal call with strict JSON output (+ optional streaming)."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .config import CONFIG
from .logger import get_logger
from .prompts import build_system_instruction, build_user_prompt

log = get_logger("gemini")

# Optional UI hook: invoked with successive chunks of streamed text. Strict
# JSON cannot be parsed mid-stream, so we use this purely for "thinking..."
# progress feedback in the GUI.
StreamCallback = Callable[[str], None]


class GeminiClient:
    """Thin wrapper around ``google.generativeai`` enforcing JSON output."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        streaming: bool | None = None,
    ) -> None:
        import os

        import google.generativeai as genai

        from . import user_config

        # CONFIG is frozen at import time; fall back to current env / saved
        # config so a key supplied by the first-run dialog is honored.
        key = (
            api_key
            or CONFIG.gemini_api_key
            or os.environ.get("GEMINI_API_KEY", "")
            or (user_config.get_api_key() or "")
        )
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
        self.streaming: bool = CONFIG.streaming if streaming is None else streaming
        self._model = genai.GenerativeModel(
            model or CONFIG.gemini_model,
            system_instruction=build_system_instruction(),
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.2,
                "max_output_tokens": 2048,
            },
        )

    def plan(
        self,
        command: str,
        screenshot_jpeg: bytes | None,
        screen_size: tuple[int, int],
        memory: dict[str, Any],
        on_chunk: StreamCallback | None = None,
    ) -> dict[str, Any]:
        prompt = build_user_prompt(command, screen_size, memory)
        parts: list[Any] = []
        if screenshot_jpeg:
            parts.append({"mime_type": "image/jpeg", "data": screenshot_jpeg})
        parts.append(prompt)

        if self.streaming:
            text = self._generate_streaming(parts, on_chunk)
        else:
            text = self._generate_blocking(parts)

        text = text.strip()
        if not text:
            raise RuntimeError("empty Gemini response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error("invalid JSON from Gemini: %s", text[:500])
            raise RuntimeError(f"non-JSON response: {e}") from e

    # ---- internals -------------------------------------------------------
    def _generate_blocking(self, parts: list[Any]) -> str:
        resp = self._model.generate_content(
            parts,
            request_options={"timeout": CONFIG.api_timeout_s},
        )
        return getattr(resp, "text", "") or ""

    def _generate_streaming(
        self,
        parts: list[Any],
        on_chunk: StreamCallback | None,
    ) -> str:
        chunks: list[str] = []
        stream = self._model.generate_content(
            parts,
            stream=True,
            request_options={"timeout": CONFIG.api_timeout_s},
        )
        for ev in stream:
            piece = getattr(ev, "text", "") or ""
            if not piece:
                continue
            chunks.append(piece)
            if on_chunk:
                try:
                    on_chunk(piece)
                except Exception:  # noqa: BLE001
                    log.exception("stream callback raised; continuing")
        return "".join(chunks)
