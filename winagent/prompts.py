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

[Desktop automation]
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

[Coding agent]
  {"type":"file_read", "path":str, "offset":int?, "limit":int?, "max_bytes":int?}
  {"type":"file_write", "path":str, "content":str, "create_dirs":bool?}
  {"type":"file_edit", "path":str, "old_string":str, "new_string":str, "replace_all":bool?}
  {"type":"file_delete", "path":str}
  {"type":"list_dir", "path":str, "recursive":bool?, "max_entries":int?}
  {"type":"apply_patch", "path":str, "edits":[{"old_string":str,"new_string":str,"replace_all":bool?}, ...]}
  {"type":"shell", "command":str, "cwd":str?, "timeout_s":int?}
  {"type":"grep", "pattern":str, "path":str?, "glob_pattern":str?, "case_insensitive":bool?,
                  "context_lines":int?, "output_mode":"content|files_with_matches|count"?, "max_results":int?}
  {"type":"find_files", "pattern":str, "path":str?, "max_results":int?}

Rules:
- Prefer **coding-agent actions** for software tasks; only use desktop actions
  when the user explicitly asks to drive a GUI app.
- Before editing a file, read or grep the relevant context first; never edit
  blindly. ``apply_patch`` is preferred over ``file_write`` for modifying code.
- Keep plans short (<= 8 actions). When verification is needed, request a
  ``screenshot`` (desktop) or a ``file_read``/``shell`` (coding) and stop —
  the next cycle will give you fresh state.
- Coordinates must be inside the visible screen.
- Prefer hotkeys (e.g. ["win"], ["ctrl","s"]) over hunting for buttons.
- Never output destructive shell commands (rm -rf, format, shutdown, etc.).
- Always populate ``memory_update.current_goal`` when starting a new task.
- All paths are resolved against the project root; do not use absolute paths
  outside the project unless explicitly told to.
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
    {
        "command": "find where MAX_RETRIES is defined and bump it to 5",
        "memory": {
            "recent_commands": [],
            "recent_actions": [],
            "current_goal": None,
            "notes": None,
        },
        "response": {
            "actions": [
                {
                    "type": "grep",
                    "pattern": r"\bMAX_RETRIES\s*=",
                    "path": ".",
                    "output_mode": "content",
                },
            ],
            "memory_update": {
                "current_goal": "Locate MAX_RETRIES then bump to 5",
                "notes": "Need grep results before editing.",
            },
        },
    },
    {
        "command": "now bump it",
        "memory": {
            "recent_commands": ["find where MAX_RETRIES is defined and bump it to 5"],
            "recent_actions": [
                {
                    "type": "grep",
                    "result": "src/config.py:14:MAX_RETRIES = 3",
                },
            ],
            "current_goal": "Locate MAX_RETRIES then bump to 5",
            "notes": None,
        },
        "response": {
            "actions": [
                {
                    "type": "apply_patch",
                    "path": "src/config.py",
                    "edits": [
                        {
                            "old_string": "MAX_RETRIES = 3",
                            "new_string": "MAX_RETRIES = 5",
                        }
                    ],
                },
                {
                    "type": "shell",
                    "command": "python -m pytest -q tests/test_config.py",
                    "timeout_s": 60,
                },
            ],
            "memory_update": {
                "current_goal": "Verify MAX_RETRIES bump",
                "notes": "Patched src/config.py:14; running config tests.",
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
        "You are WinAgent, a multimodal coding + desktop-automation agent. "
        "You can read/edit code, run shell commands, search a codebase, and "
        "(when needed) drive the Windows desktop or Excel. "
        "You see the user's screen and plan minimal, safe action sequences. "
        "Think step-by-step internally (ReAct), but OUTPUT ONLY valid JSON "
        "matching the schema.\n\n"
        f"{SCHEMA_TEXT}\n\nFEW-SHOT EXAMPLES:\n{examples}"
    )


def build_user_prompt(
    command: str,
    screen_size: tuple[int, int],
    memory: dict[str, Any],
    project_root: str | None = None,
) -> str:
    root_line = f"PROJECT_ROOT: {project_root}\n" if project_root else ""
    return (
        f"SCREEN_SIZE: {screen_size[0]}x{screen_size[1]} "
        f"(the screenshot is attached if present)\n"
        f"{root_line}"
        f"MEMORY: {json.dumps(memory, ensure_ascii=False)}\n"
        f"USER COMMAND: {command}\n"
        "Return only the JSON object."
    )
