"""Gemini 2.5 Pro multimodal call with strict JSON output."""
from __future__ import annotations

import json
from typing import Any

from .config import CONFIG
from .logger import get_logger
from .prompts import build_system_instruction, build_user_prompt

log = get_logger("gemini")


class GeminiClient:
    """Thin wrapper around ``google.generativeai`` enforcing JSON output."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import google.generativeai as genai

        key = api_key or CONFIG.gemini_api_key
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
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
        screenshot_jpeg: bytes,
        screen_size: tuple[int, int],
        memory: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = build_user_prompt(command, screen_size, memory)
        parts = [
            {"mime_type": "image/jpeg", "data": screenshot_jpeg},
            prompt,
        ]
        resp = self._model.generate_content(
            parts,
            request_options={"timeout": CONFIG.api_timeout_s},
        )
        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            raise RuntimeError("empty Gemini response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            log.error("invalid JSON from Gemini: %s", text[:500])
            raise RuntimeError(f"non-JSON response: {e}") from e
