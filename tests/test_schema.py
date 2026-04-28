"""Schema validation: every action variant + invalid payloads."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from winagent.schema import (
    AgentResponse,
    ClickAction,
    ExcelAction,
    HotkeyAction,
    PowerShellAction,
    ScreenshotAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)


def test_click_defaults():
    a = ClickAction.model_validate({"type": "click", "x": 10, "y": 20})
    assert a.button == "left" and a.clicks == 1


def test_click_negative_coord_rejected():
    with pytest.raises(ValidationError):
        ClickAction.model_validate({"type": "click", "x": -1, "y": 0})


def test_type_max_len():
    with pytest.raises(ValidationError):
        TypeAction.model_validate({"type": "type", "text": "x" * 4001})


def test_hotkey_min_keys():
    with pytest.raises(ValidationError):
        HotkeyAction.model_validate({"type": "hotkey", "keys": []})


def test_scroll_dy_signed():
    assert ScrollAction.model_validate({"type": "scroll", "dy": -5}).dy == -5


def test_wait_bounds():
    assert WaitAction.model_validate({"type": "wait", "ms": 0}).ms == 0
    with pytest.raises(ValidationError):
        WaitAction.model_validate({"type": "wait", "ms": 10_001})


def test_powershell_max_len():
    with pytest.raises(ValidationError):
        PowerShellAction.model_validate({"type": "powershell", "command": "x" * 2001})


def test_excel_operation_validated():
    with pytest.raises(ValidationError):
        ExcelAction.model_validate({"type": "excel", "operation": "nuke"})


def test_excel_extra_fields_rejected():
    with pytest.raises(ValidationError):
        ExcelAction.model_validate(
            {"type": "excel", "operation": "save", "evil": True}
        )


def test_screenshot_action_minimal():
    assert ScreenshotAction.model_validate({"type": "screenshot"}).type == "screenshot"


def test_agent_response_full_roundtrip():
    payload = {
        "actions": [
            {"type": "hotkey", "keys": ["win", "r"]},
            {"type": "type", "text": "notepad"},
            {"type": "wait", "ms": 100},
            {"type": "click", "x": 5, "y": 5, "button": "right"},
            {"type": "powershell", "command": "Get-Process"},
            {
                "type": "excel",
                "operation": "write_range",
                "range": "A1:B2",
                "values": [["a", "b"], ["c", "d"]],
            },
            {"type": "screenshot"},
        ],
        "memory_update": {"current_goal": "g", "notes": "n"},
    }
    parsed = AgentResponse.model_validate(payload)
    assert len(parsed.actions) == 7
    assert parsed.memory_update is not None
    assert parsed.memory_update.current_goal == "g"


def test_agent_response_unknown_action_rejected():
    with pytest.raises(ValidationError):
        AgentResponse.model_validate({"actions": [{"type": "selfdestruct"}]})


def test_agent_response_too_many_actions():
    payload = {"actions": [{"type": "wait", "ms": 1}] * 26}
    with pytest.raises(ValidationError):
        AgentResponse.model_validate(payload)


def test_agent_response_extra_top_level_rejected():
    with pytest.raises(ValidationError):
        AgentResponse.model_validate({"actions": [], "rogue": 1})
