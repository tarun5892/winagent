# WinAgent

A lightweight, multimodal **coding agent + Windows desktop automation agent**
powered by your choice of **Gemini, OpenRouter, Groq, or Mistral**. Type a
command and WinAgent reads/edits your codebase, runs shell commands, searches
with grep, and (optionally) screenshots and drives the Windows desktop or Excel.

## Highlights

- **Multi-provider LLM**: Gemini, OpenRouter (300+ models incl. free routes
  like DeepSeek-V3), Groq (fast Llama 3.3), Mistral. Switch providers from
  the in-app Settings dialog.
- **Coding-agent toolset**: `file_read` / `file_write` / `file_edit` /
  `apply_patch` / `file_delete` / `list_dir` / `shell` / `grep` / `find_files`.
- **Desktop automation**: `click` / `type` / `hotkey` / `scroll` / `wait` /
  `powershell` / `excel` / `screenshot`.
- **Streaming responses** for snappy feedback (every supported provider).
- **Strict JSON schema** (Pydantic) — no free-form code execution.
- **Short-term rolling memory** (deque) injected into every prompt for
  multi-step continuity.
- **Per-action safety policy**: read-only actions auto-allow, mutating
  actions confirm, destructive shell hard-blocked, project-root sandbox.
- Modular, event-driven; easy to add new action types.

## Architecture

```
tkinter UI ──submit──▶ Orchestrator (worker thread)
                        │
                        ├─▶ Vision (MSS, optional) ──▶ LLM (Gemini / OpenRouter / Groq / Mistral) ──▶ JSON
                        │                                                            │
                        │                                              Pydantic validation
                        │                                                            │
                        ├─▶ Memory (deque + goal) ◀───────update────────────────────┤
                        │                                                            │
                        └─▶ Safety ──▶ Executor
                                          │
                                          ├─ coding tools (file/shell/grep/patch)
                                          ├─ desktop tools (pyautogui/PowerShell)
                                          └─ Excel COM (pywin32)
```

## Download (Windows)

Pre-built **`winagent.exe`** is produced by GitHub Actions on every push to
`main`. No Python install required.

1. Go to the **[Actions tab](https://github.com/tarun5892/winagent/actions/workflows/build.yml)**.
2. Click the latest successful run.
3. Under **Artifacts**, download `winagent-windows-x64`.
4. Unzip → double-click `winagent.exe`.
5. On first launch a popup asks you to pick a provider and paste an API
   key. The settings are saved to `%APPDATA%\WinAgent\config.json` so you
   only enter them once. Where to get a free key for each provider:
   - **Gemini** — <https://aistudio.google.com/app/apikey>
   - **OpenRouter** — <https://openrouter.ai/keys> (free models available)
   - **Groq** — <https://console.groq.com/keys> (generous free tier)
   - **Mistral** — <https://console.mistral.ai/api-keys/>

Tagged releases (`git tag v0.2.0 && git push --tags`) also attach
`winagent.exe` to a [GitHub Release](https://github.com/tarun5892/winagent/releases).

## Install from source

Requires Python 3.10+.

```powershell
git clone https://github.com/tarun5892/winagent.git
cd winagent
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```powershell
# Option 1 (recommended): just launch and use the first-run popup
python -m winagent

# Option 2: pre-set the key as an env var (per provider)
$env:GEMINI_API_KEY="your_key"        # or OPENROUTER_API_KEY / GROQ_API_KEY / MISTRAL_API_KEY
$env:WINAGENT_PROVIDER="openrouter"   # gemini | openrouter | groq | mistral
$env:WINAGENT_MODEL="anthropic/claude-3.5-sonnet"  # optional override
python -m winagent
```

### Provider defaults

| Provider | Default model | Free tier |
|---|---|---|
| Gemini | `gemini-2.5-flash` | ~1500 req/day |
| OpenRouter | `deepseek/deepseek-chat-v3-0324:free` | yes (free models) |
| Groq | `llama-3.3-70b-versatile` | yes (generous) |
| Mistral | `mistral-large-latest` | small free tier |

To build the Windows .exe locally:

```powershell
pip install pyinstaller==6.10.0
pyinstaller --noconfirm --clean winagent.spec
# Output: dist\winagent.exe
```

## Action schema

```jsonc
{
  "actions": [
    // Coding agent
    {"type": "grep", "pattern": "MAX_RETRIES"},
    {"type": "file_read", "path": "src/config.py"},
    {"type": "apply_patch", "path": "src/config.py",
     "edits": [{"old_string": "MAX_RETRIES = 3", "new_string": "MAX_RETRIES = 5"}]},
    {"type": "shell", "command": "python -m pytest -q"},

    // Desktop / Excel
    {"type": "click", "x": 500, "y": 300},
    {"type": "hotkey", "keys": ["ctrl", "s"]},
    {"type": "excel", "operation": "write_cell", "cell": "A1", "value": "Test"}
  ],
  "memory_update": {"current_goal": "...", "notes": "..."}
}
```

Full list: `click`, `move`, `type`, `hotkey`, `scroll`, `wait`,
`powershell`, `excel`, `screenshot`, `file_read`, `file_write`, `file_edit`,
`file_delete`, `list_dir`, `apply_patch`, `shell`, `grep`, `find_files`.
See `winagent/schema.py`.

### Project root

Coding-agent actions resolve paths against `WINAGENT_PROJECT_ROOT`
(defaults to the current working directory). Paths that escape the project
root raise `PermissionError`. Set the env var to your repo to scope the
agent: `set WINAGENT_PROJECT_ROOT=C:\path\to\your\project`.

## Development

```bash
pip install -e ".[dev]"
ruff check winagent tests
mypy winagent
pytest -q
```

The test suite uses fakes for `pyautogui`, `win32com`, `google.generativeai`,
so it runs cross-platform without touching your desktop or making API calls.
Live integration on Windows requires a real provider API key (Gemini, OpenRouter,
Groq, or Mistral) and — for desktop actions — a real Windows desktop.

## Safety

- **Hard-blocked commands** (`shutdown`, `Format-Volume`, `Remove-Item -Recurse`,
  `rm -rf /`, `dd if=/dev/...`, `chmod -R 777 /`, fork bombs, etc.) are
  filtered out before execution. Extend the regex lists in
  `winagent/safety.py` and `winagent/coding_tools.py` as needed.
- **Per-action confirmation policy**:
  - Read-only actions (`file_read`, `list_dir`, `grep`, `find_files`):
    auto-allowed even when confirmation mode is on.
  - Mutating actions (`file_write`, `file_edit`, `apply_patch`,
    `file_delete`, plus all desktop/Excel/shell actions): require
    confirmation when the dialog is enabled.
- **Project-root sandbox**: every coding action's path is resolved relative
  to `project_root` and rejected if it escapes.
- **PyAutoGUI failsafe** is enabled — flick the mouse to a screen corner
  to abort runaway desktop automation.

## License

MIT — see `LICENSE`.
