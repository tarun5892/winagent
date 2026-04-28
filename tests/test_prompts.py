"""Prompt construction integrity + schema/few-shot agreement."""
from __future__ import annotations

import json

from winagent.prompts import FEW_SHOT, build_system_instruction, build_user_prompt
from winagent.schema import AgentResponse


def test_system_instruction_contains_schema_and_rules():
    s = build_system_instruction()
    assert "JSON" in s
    assert "actions" in s
    assert "memory_update" in s
    assert "destructive" in s.lower()


def test_user_prompt_includes_dynamic_fields():
    p = build_user_prompt(
        "open browser",
        (1920, 1080),
        {"recent_commands": ["x"], "recent_actions": [], "current_goal": "g", "notes": None},
    )
    assert "open browser" in p
    assert "1920x1080" in p
    assert '"current_goal": "g"' in p


def test_few_shot_examples_validate_against_schema():
    """Each example response must pass strict schema validation."""
    for ex in FEW_SHOT:
        AgentResponse.model_validate(ex["response"])


def test_few_shot_examples_serializable():
    for ex in FEW_SHOT:
        json.dumps(ex)


def test_user_prompt_handles_unicode():
    p = build_user_prompt("öpen", (800, 600), {"recent_commands": ["é"]})
    assert "öpen" in p and "é" in p
