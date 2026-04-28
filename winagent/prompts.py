"""Prompt construction with memory injection + few-shot examples."""
from __future__ import annotations

import json
from typing import Any

SCHEMA_TEXT = """\
Output ONE JSON object. No prose, no markdown fences. Schema:
{
  "actions": [ Action, ... ],
  "memory_update": { "current_goal": str?, "notes": str? } | null
}

Action variants (discriminated by "type"):
  {"type":"click", "x":int, "y":int, "button":"left|right|middle"?, "clicks":1..3?}
  {"type":"move", "x":int, "y":int}
  {"type":"type", "text":str, "interval_ms":int?}
  {"type":"hotkey", "keys":[str,...]}
  {"type":"scroll", "dy":int}        // +up, -down (clicks)
  {"type":"wait", "ms":int}
  {"type":"powershell", "command":str}
  {"type":"excel", "operation":"open|close|save|save_as|write_cell|read_cell|write_range|add_sheet|select_sheet|run_vba",
                   "path":str?, "sheet":str?, "cell":str?, "value":str?,
                   "range":str?, "values":[[str,...],...]?, "vba_code":str?}
  {"type":"screenshot"}

Rules:
- Coordinates must be inside the visible screen.
- Prefer hotkeys (e.g. ["win"], ["ctrl","s"]) over hunting for buttons.
- Keep plans short (<= 8 actions); request a fresh screenshot to verify state.
- Never output destructive shell commands (rm/format/shutdown/etc.).
- Always populate memory_update.current_goal when starting a new task.
"""

FEW_SHOT = [
    {
        "command": "open notepad and type 'Hello'",
        "memory": {
            "recent_commands": [],
            "recent_actions": [],
            "current_goal": None,
            "notes": None,
        },
        "response": {
            "actions": [
                {"type": "hotkey", "keys": ["win", "r"]},
                {"type": "wait", "ms": 300},
                {"type": "type", "text": "notepad"},
                {"type": "hotkey", "keys": ["enter"]},
                {"type": "wait", "ms": 600},
                {"type": "type", "text": "Hello"},
            ],
            "memory_update": {
                "current_goal": "Open Notepad and write greeting",
                "notes": "Used Win+R to launch reliably.",
            },
        },
    },
    {
        "command": "now save it as greeting.txt on the desktop",
        "memory": {
            "recent_commands": ["open notepad and type 'Hello'"],
            "recent_actions": [
                {"type": "hotkey", "keys": ["win", "r"]},
                {"type": "type", "text": "notepad"},
                {"type": "type", "text": "Hello"},
            ],
            "current_goal": "Open Notepad and write greeting",
            "notes": "Used Win+R to launch reliably.",
        },
        "response": {
            "actions": [
                {"type": "hotkey", "keys": ["ctrl", "s"]},
                {"type": "wait", "ms": 500},
                {"type": "type", "text": "%USERPROFILE%\\Desktop\\greeting.txt"},
                {"type": "hotkey", "keys": ["enter"]},
            ],
            "memory_update": {
                "current_goal": "Save greeting.txt on desktop",
                "notes": "Continuing previous Notepad task.",
            },
        },
    },
    {
        "command": "create a 3x2 table in Excel with headers Name, Age",
        "memory": {
            "recent_commands": [],
            "recent_actions": [],
            "current_goal": None,
            "notes": None,
        },
        "response": {
            "actions": [
                {"type": "excel", "operation": "add_sheet", "sheet": "People"},
                {
                    "type": "excel",
                    "operation": "write_range",
                    "sheet": "People",
                    "range": "A1:B4",
                    "values": [
                        ["Name", "Age"],
                        ["Alice", "30"],
                        ["Bob", "25"],
                        ["Cara", "41"],
                    ],
                },
                {"type": "excel", "operation": "save"},
            ],
            "memory_update": {
                "current_goal": "Populate People sheet",
                "notes": "Used write_range for atomic table fill.",
            },
        },
    },
]


def build_system_instruction() -> str:
    examples = "\n\n".join(
        f"USER COMMAND: {ex['command']}\nMEMORY: {json.dumps(ex['memory'])}\n"
        f"RESPONSE: {json.dumps(ex['response'])}"
        for ex in FEW_SHOT
    )
    return (
        "You are WinAgent, a Windows desktop automation planner. "
        "You see the user's screen and plan minimal, safe action sequences. "
        "Think step-by-step internally (ReAct), but OUTPUT ONLY valid JSON "
        "matching the schema.\n\n"
        f"{SCHEMA_TEXT}\n\nFEW-SHOT EXAMPLES:\n{examples}"
    )


def build_user_prompt(
    command: str,
    screen_size: tuple[int, int],
    memory: dict[str, Any],
) -> str:
    return (
        f"SCREEN_SIZE: {screen_size[0]}x{screen_size[1]} "
        f"(the screenshot is attached)\n"
        f"MEMORY: {json.dumps(memory, ensure_ascii=False)}\n"
        f"USER COMMAND: {command}\n"
        "Return only the JSON object."
    )
