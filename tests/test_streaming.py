"""GeminiClient streaming behavior."""
from __future__ import annotations

import json

import pytest

from tests.fakes import FakeGenAI


@pytest.fixture
def fake_genai_module(monkeypatch):
    fake = FakeGenAI()
    import sys

    monkeypatch.setitem(sys.modules, "google", type(sys)("google"))
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    return fake


def test_streaming_collects_chunks_and_parses_json(fake_genai_module: FakeGenAI):
    payload = {"actions": [{"type": "wait", "ms": 1}], "memory_update": None}
    text = json.dumps(payload)
    pieces = [text[:5], text[5:15], text[15:]]
    fake_genai_module.model_kwargs_capture = []  # marker

    from winagent.gemini_client import GeminiClient

    client = GeminiClient(api_key="k", streaming=True)
    fake_genai_module.last_model.next_response = text
    fake_genai_module.last_model.next_chunks = pieces

    received: list[str] = []
    out = client.plan(
        command="cmd",
        screenshot_jpeg=b"fake",
        screen_size=(100, 100),
        memory={},
        on_chunk=received.append,
    )
    assert out == payload
    assert received == pieces


def test_blocking_mode_does_not_stream(fake_genai_module: FakeGenAI):
    from winagent.gemini_client import GeminiClient

    client = GeminiClient(api_key="k", streaming=False)
    payload = {"actions": [], "memory_update": None}
    fake_genai_module.last_model.next_response = json.dumps(payload)
    out = client.plan(
        command="cmd",
        screenshot_jpeg=b"img",
        screen_size=(50, 50),
        memory={},
    )
    assert out == payload
    # streaming=False ⇒ generate_content called with stream=False
    call = fake_genai_module.last_model.calls[-1]
    assert call["stream"] is False


def test_streaming_handles_callback_exception(fake_genai_module: FakeGenAI):
    from winagent.gemini_client import GeminiClient

    client = GeminiClient(api_key="k", streaming=True)
    payload = {"actions": [], "memory_update": None}
    text = json.dumps(payload)
    fake_genai_module.last_model.next_response = text
    fake_genai_module.last_model.next_chunks = [text[:3], text[3:]]

    def boom(_chunk: str) -> None:
        raise RuntimeError("downstream UI bug")

    out = client.plan(
        command="cmd",
        screenshot_jpeg=b"img",
        screen_size=(0, 0),
        memory={},
        on_chunk=boom,
    )
    assert out == payload  # callback errors are logged, not raised


def test_streaming_no_screenshot(fake_genai_module: FakeGenAI):
    """Coding tasks may run without a display."""
    from winagent.gemini_client import GeminiClient

    client = GeminiClient(api_key="k", streaming=True)
    payload = {"actions": [], "memory_update": None}
    fake_genai_module.last_model.next_response = json.dumps(payload)

    out = client.plan(
        command="cmd",
        screenshot_jpeg=b"",
        screen_size=(0, 0),
        memory={},
    )
    assert out == payload
    # No image part should have been attached
    parts = fake_genai_module.last_model.calls[-1]["parts"]
    assert all(not isinstance(p, dict) or "data" not in p for p in parts)
