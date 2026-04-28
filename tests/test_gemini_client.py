"""GeminiClient: configuration, JSON parsing, error paths."""
from __future__ import annotations

import json

import pytest

from winagent.gemini_client import GeminiClient


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch, fake_genai) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiClient(api_key="")


def test_configures_and_attaches_screenshot(fake_genai) -> None:
    c = GeminiClient(api_key="x", model="gemini-2.5-pro")
    fake_genai.last_model.next_response = json.dumps(
        {"actions": [{"type": "wait", "ms": 1}], "memory_update": None}
    )
    out = c.plan("hi", b"\xff\xd8\xff", (800, 600), {"recent_commands": []})
    assert out["actions"][0]["type"] == "wait"
    call = fake_genai.last_model.calls[0]
    assert call["parts"][0]["mime_type"] == "image/jpeg"
    assert call["parts"][0]["data"] == b"\xff\xd8\xff"
    # user prompt is the second part and contains the command
    assert "hi" in call["parts"][1]
    assert "800x600" in call["parts"][1]


def test_empty_response_raises(fake_genai) -> None:
    c = GeminiClient(api_key="x")
    fake_genai.last_model.next_response = ""
    with pytest.raises(RuntimeError, match="empty"):
        c.plan("x", b"x", (1, 1), {})


def test_non_json_response_raises(fake_genai) -> None:
    c = GeminiClient(api_key="x")
    fake_genai.last_model.next_response = "not-json"
    with pytest.raises(RuntimeError, match="non-JSON"):
        c.plan("x", b"x", (1, 1), {})


def test_passes_timeout(fake_genai) -> None:
    c = GeminiClient(api_key="x")
    fake_genai.last_model.next_response = "{\"actions\": []}"
    c.plan("x", b"x", (1, 1), {})
    assert "request_options" in fake_genai.last_model.calls[0]
    assert fake_genai.last_model.calls[0]["request_options"]["timeout"] > 0
