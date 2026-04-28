# WinAgent

A lightweight, multimodal **Windows desktop AI agent**. Type a command,
WinAgent screenshots your desktop, sends image + command + short-term memory
to **Gemini 2.5 Pro**, and executes the returned plan via PyAutoGUI,
PowerShell, and Excel COM automation.

## Highlights

- Strict JSON action schema (Pydantic-validated) — no free-form code execution.
- Short-term memory (rolling deque) injected into every prompt for multi-step continuity.
- Safety layer blocks destructive shell ops; optional confirmation dialog.
- Modular, event-driven; easy to add new action types.
- ~10 modules, no heavyweight frameworks.

## Architecture

```
tkinter UI ──submit──▶ Orchestrator (worker thread)
                        │
                        ├─▶ Vision (MSS) ──▶ Gemini 2.5 Pro ──▶ JSON
                        │                                       │
                        │                            Pydantic validation
                        │                                       │
                        ├─▶ Memory (deque + goal) ◀──update────┤
                        │                                       │
                        └─▶ Safety ──▶ Executor (pyautogui / PowerShell / Excel COM)
```

## Install

Requires Python 3.10+ on Windows.

```powershell
git clone <repo-url> winagent
cd winagent
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Run

```powershell
$env:GEMINI_API_KEY="your_key"
python -m winagent
```

## Action schema

```jsonc
{
  "actions": [
    {"type": "click", "x": 500, "y": 300},
    {"type": "type",  "text": "Hello"},
    {"type": "hotkey", "keys": ["ctrl", "s"]},
    {"type": "powershell", "command": "Get-Process"},
    {"type": "excel", "operation": "write_cell", "cell": "A1", "value": "Test"}
  ],
  "memory_update": {"current_goal": "...", "notes": "..."}
}
```

Full list: `click`, `move`, `type`, `hotkey`, `scroll`, `wait`,
`powershell`, `excel`, `screenshot`. See `winagent/schema.py`.

## Development

```bash
pip install -e ".[dev]"
ruff check winagent tests
mypy winagent
pytest -q
```

The test suite uses fakes for `pyautogui`, `win32com`, `google.generativeai`,
so it runs cross-platform without touching your desktop or making API calls.
Live integration on Windows requires a real `GEMINI_API_KEY` and a real desktop.

## Safety

- Destructive PowerShell commands (`shutdown`, `Format-Volume`, `Remove-Item -Recurse`,
  `Restart-Computer`, `diskpart`, `Iex … Net.WebClient …`, etc.) are blocked
  before execution. Extend the regex list in `winagent/safety.py` as needed.
- Confirmation mode (default ON): the GUI prompts before executing any plan.
- PyAutoGUI failsafe is enabled — flick the mouse to a screen corner to abort.

## License

MIT — see `LICENSE`.
