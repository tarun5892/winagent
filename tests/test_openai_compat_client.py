"""OpenAI-compatible client (OpenRouter / Groq / Mistral): config, JSON parsing,
streaming, error paths, and code-fence stripping."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from winagent.openai_compat_client import OpenAICompatClient, _strip_code_fences


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate user_config writes/reads to a tmp dir and clear provider env."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for v in (
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)
    return tmp_path


def test_missing_api_key_raises(isolated_config: Path, fake_openai) -> None:
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenAICompatClient(provider="openrouter", api_key="")


def test_uses_explicit_api_key(isolated_config: Path, fake_openai) -> None:
    OpenAICompatClient(provider="openrouter", api_key="abc", model="m")
    assert fake_openai.last_client.api_key == "abc"
    assert fake_openai.last_client.base_url == "https://openrouter.ai/api/v1"


def test_falls_back_to_env(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch, fake_openai
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    OpenAICompatClient(provider="groq")
    assert fake_openai.last_client.api_key == "from-env"
    assert fake_openai.last_client.base_url == "https://api.groq.com/openai/v1"


def test_unknown_provider_raises(isolated_config: Path, fake_openai) -> None:
    with pytest.raises(RuntimeError, match="no base_url"):
        OpenAICompatClient(provider="totally-unknown", api_key="k", base_url="")


def test_blocking_plan_returns_parsed_json(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="openrouter", api_key="x", model="m", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = json.dumps(
        {"actions": [{"type": "wait", "ms": 5}], "memory_update": None}
    )
    out = c.plan("hi", None, (1024, 768), {"recent_commands": []})
    assert out["actions"][0]["type"] == "wait"


def test_screenshot_attached_as_image_url(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="mistral", api_key="x", model="m", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = '{"actions": []}'
    img = b"\xff\xd8\xff\x12\x34"
    c.plan("hi", img, (800, 600), {})
    call = fake_openai.last_client.chat.completions.calls[0]
    user_content = call["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "image_url"
    expected_b64 = base64.b64encode(img).decode("ascii")
    assert expected_b64 in user_content[0]["image_url"]["url"]
    # Text part contains command + screen size hint.
    text_part = user_content[1]
    assert text_part["type"] == "text"
    assert "hi" in text_part["text"]
    assert "800x600" in text_part["text"]


def test_passes_model_temperature_and_timeout(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="groq", api_key="x", model="llama-3.3-70b", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = '{"actions": []}'
    c.plan("x", None, (1, 1), {})
    call = fake_openai.last_client.chat.completions.calls[0]
    assert call["model"] == "llama-3.3-70b"
    assert call["temperature"] == 0.2
    assert call["timeout"] > 0
    assert call["response_format"] == {"type": "json_object"}


def test_streaming_concatenates_chunks(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="openrouter", api_key="x", model="m", streaming=True
    )
    fake_openai.last_client.chat.completions.next_chunks = [
        '{"actions"',
        ': [{"type"',
        ': "wait", "ms": 1}]',
        ', "memory_update": null}',
    ]
    seen: list[str] = []
    out = c.plan(
        "x", None, (1, 1), {}, on_chunk=lambda piece: seen.append(piece)
    )
    assert out["actions"][0]["type"] == "wait"
    assert "".join(seen) == "".join(
        fake_openai.last_client.chat.completions.next_chunks
    )


def test_empty_response_raises(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="openrouter", api_key="x", model="m", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = ""
    with pytest.raises(RuntimeError, match="empty"):
        c.plan("x", None, (1, 1), {})


def test_non_json_response_raises(isolated_config: Path, fake_openai) -> None:
    c = OpenAICompatClient(
        provider="groq", api_key="x", model="m", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = "not-json"
    with pytest.raises(RuntimeError, match="non-JSON"):
        c.plan("x", None, (1, 1), {})


def test_strip_code_fences_handles_json_block() -> None:
    raw = '```json\n{"actions": []}\n```'
    assert _strip_code_fences(raw) == '{"actions": []}'


def test_strip_code_fences_handles_plain_block() -> None:
    raw = "```\n{\"actions\": []}\n```"
    assert _strip_code_fences(raw) == '{"actions": []}'


def test_strip_code_fences_passthrough_on_no_fences() -> None:
    assert _strip_code_fences("{}") == "{}"


def test_provider_with_code_fenced_response(
    isolated_config: Path, fake_openai
) -> None:
    """Some providers wrap JSON in ```json ... ``` despite response_format."""
    c = OpenAICompatClient(
        provider="mistral", api_key="x", model="m", streaming=False
    )
    fake_openai.last_client.chat.completions.next_content = (
        '```json\n{"actions": [], "memory_update": null}\n```'
    )
    out = c.plan("x", None, (1, 1), {})
    assert out == {"actions": [], "memory_update": None}
