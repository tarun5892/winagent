"""Modern tkinter UI for WinAgent.

Layout
------
+--------------------------------------------------------------+
| WinAgent       [● Ready]                          ⚙ Settings |
+----------------------+---------------------------------------+
| Quick actions        |  [INFO] orchestrator started          |
|                      |  [ACT ] file_read src/main.py         |
| - List files in src/ |  [ACT ] grep "TODO"                   |
| - Find every TODO    |  ...                                  |
| - Read README        |                                       |
| - Run the test suite |                                       |
| ...                  |                                       |
|                      |                                       |
+----------------------+---------------------------------------+
| > Type a command and press Enter           [   Submit   ]    |
| [x] Confirm before executing                                 |
+--------------------------------------------------------------+
"""
from __future__ import annotations

import logging
import queue
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

from .logger import LOG_QUEUE, setup_logging
from .orchestrator import Orchestrator

POLL_MS = 100
APIKEY_HELP_URL = "https://aistudio.google.com/app/apikey"

# Catppuccin-inspired dark palette
THEME = {
    "bg": "#1e1e2e",          # base
    "surface": "#313244",     # surface0
    "surface_alt": "#45475a", # surface1
    "border": "#585b70",      # surface2
    "text": "#cdd6f4",
    "text_dim": "#a6adc8",
    "accent": "#89b4fa",      # blue
    "accent_hover": "#b4befe",
    "ok": "#a6e3a1",          # green
    "warn": "#f9e2af",         # yellow
    "err": "#f38ba8",          # red/pink
    "act": "#cba6f7",          # mauve
}

QUICK_ACTIONS = [
    ("📁  List files", "list every python file in this project"),
    ("🔍  Find TODOs", "find every TODO comment and tell me which files have them"),
    ("📖  Read README", "open the README.md and summarize it in 3 sentences"),
    ("🧪  Run tests", "run pytest -q and tell me what failed"),
    ("🌿  Git status", "run git status and summarize what's changed"),
    ("✏️   Refactor", "add type hints to every function in src/main.py"),
]


def _apply_theme(root: tk.Misc) -> ttk.Style:
    """Apply the dark theme to a Tk root and return the configured ttk style."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # most consistent across platforms for custom styling
    except tk.TclError:
        pass
    bg = THEME["bg"]
    surf = THEME["surface"]
    txt = THEME["text"]
    accent = THEME["accent"]
    border = THEME["border"]

    root.configure(background=bg)  # type: ignore[call-arg]
    style.configure(".", background=bg, foreground=txt, fieldbackground=surf)
    style.configure("TFrame", background=bg)
    style.configure("Surface.TFrame", background=surf)
    style.configure("TLabel", background=bg, foreground=txt)
    style.configure("Surface.TLabel", background=surf, foreground=txt)
    style.configure("Header.TLabel", background=bg, foreground=txt, font=("Segoe UI", 16, "bold"))
    style.configure("Subtle.TLabel", background=bg, foreground=THEME["text_dim"])
    style.configure("Pill.TLabel", background=surf, foreground=THEME["ok"], padding=(10, 4))
    style.configure(
        "TButton",
        background=surf,
        foreground=txt,
        bordercolor=border,
        focusthickness=0,
        padding=(10, 6),
    )
    style.map(
        "TButton",
        background=[("active", THEME["surface_alt"])],
        foreground=[("active", txt)],
    )
    style.configure(
        "Accent.TButton",
        background=accent,
        foreground=THEME["bg"],
        font=("Segoe UI", 10, "bold"),
        padding=(16, 8),
    )
    style.map(
        "Accent.TButton",
        background=[("active", THEME["accent_hover"])],
        foreground=[("active", THEME["bg"])],
    )
    style.configure(
        "Quick.TButton",
        background=surf,
        foreground=txt,
        anchor="w",
        padding=(10, 8),
    )
    style.map(
        "Quick.TButton",
        background=[("active", THEME["surface_alt"])],
    )
    style.configure(
        "TEntry",
        fieldbackground=surf,
        foreground=txt,
        bordercolor=border,
        insertcolor=txt,
        padding=8,
    )
    style.configure(
        "TCheckbutton",
        background=bg,
        foreground=THEME["text_dim"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", bg)],
    )
    return style


# ---------------------------------------------------------------------------
# First-run API key dialog (themed)
# ---------------------------------------------------------------------------
def prompt_for_api_key(parent: tk.Misc | None = None) -> str | None:
    """First-run modal that asks the user for a Gemini API key.

    Returns the entered key (stripped) or ``None`` if the user cancelled.
    """
    owns_root = parent is None
    root = tk.Tk() if owns_root else tk.Toplevel(parent)
    _apply_theme(root)
    root.title("WinAgent — first-run setup")
    root.geometry("560x300")
    root.resizable(False, False)

    body = ttk.Frame(root, padding=24)
    body.pack(fill=tk.BOTH, expand=True)

    ttk.Label(body, text="Welcome to WinAgent", style="Header.TLabel").pack(pady=(0, 4))
    ttk.Label(
        body,
        text=(
            "Paste your free Gemini API key below.\n"
            "You only need to do this once — it's saved securely on this PC."
        ),
        style="Subtle.TLabel",
        justify="center",
    ).pack(pady=(0, 12))

    link = tk.Label(
        body,
        text="Get a free key at aistudio.google.com  →",
        bg=THEME["bg"],
        fg=THEME["accent"],
        cursor="hand2",
        font=("Segoe UI", 10, "underline"),
    )
    link.pack(pady=(0, 12))
    link.bind("<Button-1>", lambda _e: webbrowser.open(APIKEY_HELP_URL))

    var = tk.StringVar()
    entry = ttk.Entry(body, textvariable=var, show="•", width=50, font=("Consolas", 11))
    entry.pack(fill=tk.X, pady=(0, 16))
    entry.focus_set()

    result: dict[str, str | None] = {"key": None}

    def submit(_e: object | None = None) -> None:
        v = var.get().strip()
        if not v:
            messagebox.showwarning("WinAgent", "API key cannot be empty.", parent=root)
            return
        result["key"] = v
        root.destroy()

    def cancel() -> None:
        root.destroy()

    btns = ttk.Frame(body)
    btns.pack()
    ttk.Button(btns, text="Save & Continue", style="Accent.TButton", command=submit).pack(
        side=tk.LEFT, padx=6
    )
    ttk.Button(btns, text="Skip", command=cancel).pack(side=tk.LEFT, padx=6)
    entry.bind("<Return>", submit)

    root.protocol("WM_DELETE_WINDOW", cancel)
    if owns_root:
        root.mainloop()
    else:
        root.wait_window()
    return result["key"]


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
class WinAgentUI:
    """Modern themed tkinter UI."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        setup_logging()
        self.root = tk.Tk()
        _apply_theme(self.root)
        self.root.title("WinAgent")
        self.root.geometry("1080x680")
        self.root.minsize(840, 540)

        self._build_header()
        self._build_body()
        self._build_input_bar()
        self._build_status_bar()

        self.orch = orchestrator or Orchestrator(
            confirm_fn=self._confirm_dialog,
            confirmation_mode=True,
        )
        if not self.orch.is_alive():
            self.orch.start()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_MS, self._drain_logs)

    # -- layout -------------------------------------------------------------
    def _build_header(self) -> None:
        header = ttk.Frame(self.root, padding=(20, 16, 20, 8))
        header.pack(fill=tk.X)

        title_box = ttk.Frame(header)
        title_box.pack(side=tk.LEFT)
        ttk.Label(title_box, text="WinAgent", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            title_box,
            text="  • multimodal coding agent",
            style="Subtle.TLabel",
        ).pack(side=tk.LEFT, padx=(0, 0))

        right = ttk.Frame(header)
        right.pack(side=tk.RIGHT)

        self.status_pill = tk.Label(
            right,
            text="●  Ready",
            bg=THEME["surface"],
            fg=THEME["ok"],
            padx=12,
            pady=4,
            font=("Segoe UI", 10, "bold"),
        )
        self.status_pill.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(right, text="⚙  Settings", command=self._open_settings).pack(side=tk.LEFT)

    def _build_body(self) -> None:
        body = ttk.Frame(self.root, padding=(20, 0, 20, 8))
        body.pack(fill=tk.BOTH, expand=True)

        # Left: Quick actions
        left = ttk.Frame(body, style="Surface.TFrame", padding=14)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        ttk.Label(
            left,
            text="QUICK ACTIONS",
            style="Surface.TLabel",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        for label, command in QUICK_ACTIONS:
            self._add_quick_action(left, label, command)

        # Right: Log panel
        right = ttk.Frame(body, style="Surface.TFrame", padding=2)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.log = scrolledtext.ScrolledText(
            right,
            state=tk.DISABLED,
            font=("Consolas", 10),
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["text"],
            relief=tk.FLAT,
            borderwidth=0,
            padx=14,
            pady=12,
            wrap=tk.WORD,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        # Color-coded tags for log levels.
        self.log.tag_configure("INFO", foreground=THEME["text"])
        self.log.tag_configure("WARNING", foreground=THEME["warn"])
        self.log.tag_configure("ERROR", foreground=THEME["err"])
        self.log.tag_configure("ACTION", foreground=THEME["act"])
        self.log.tag_configure("ME", foreground=THEME["accent"])
        self.log.tag_configure("OK", foreground=THEME["ok"])

    def _build_input_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(20, 0, 20, 4))
        bar.pack(fill=tk.X)

        self.entry = ttk.Entry(bar, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self.entry.bind("<Return>", lambda _e: self._on_submit())
        self.entry.focus_set()

        self.submit_btn = ttk.Button(
            bar,
            text="Submit  →",
            style="Accent.TButton",
            command=self._on_submit,
        )
        self.submit_btn.pack(side=tk.LEFT, padx=(8, 0))

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(20, 4, 20, 12))
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.confirm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar,
            text="Confirm before executing",
            variable=self.confirm_var,
            command=self._toggle_confirm,
        ).pack(side=tk.LEFT)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status, style="Subtle.TLabel").pack(side=tk.RIGHT)

    def _add_quick_action(self, parent: ttk.Frame, label: str, command: str) -> None:
        ttk.Button(
            parent,
            text=label,
            style="Quick.TButton",
            width=22,
            command=lambda: self._fill_command(command),
        ).pack(fill=tk.X, pady=2)

    # -- handlers -----------------------------------------------------------
    def _fill_command(self, command: str) -> None:
        self.entry.delete(0, tk.END)
        self.entry.insert(0, command)
        self.entry.focus_set()

    def _on_submit(self) -> None:
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.entry.delete(0, tk.END)
        self._set_status("running", THEME["warn"], "●  Running")
        self._append_log(f"> {cmd}", "ME")
        self.orch.submit(cmd)

    def _toggle_confirm(self) -> None:
        self.orch.safety.confirmation_mode = self.confirm_var.get()

    def _reset_memory(self) -> None:
        self.orch.memory.reset()
        self._append_log("[ui] memory reset", "OK")

    def _confirm_dialog(self, summary: str) -> bool:
        return messagebox.askyesno(
            "Confirm plan",
            f"Execute these actions?\n\n{summary}",
        )

    def _open_settings(self) -> None:
        win = tk.Toplevel(self.root)
        _apply_theme(win)
        win.title("WinAgent — Settings")
        win.geometry("420x260")
        win.transient(self.root)
        body = ttk.Frame(win, padding=20)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Settings", style="Header.TLabel").pack(anchor="w", pady=(0, 12))

        def change_key() -> None:
            from . import user_config

            new = prompt_for_api_key(parent=win)
            if new:
                user_config.set_api_key(new)
                self._append_log("[ui] API key updated", "OK")

        ttk.Button(body, text="Change Gemini API key…", command=change_key).pack(
            fill=tk.X, pady=4
        )
        ttk.Button(body, text="Reset memory", command=self._reset_memory).pack(
            fill=tk.X, pady=4
        )
        ttk.Button(
            body,
            text="Open API key page",
            command=lambda: webbrowser.open(APIKEY_HELP_URL),
        ).pack(fill=tk.X, pady=4)
        ttk.Label(
            body,
            text="\nProject root and model are configured via environment variables.",
            style="Subtle.TLabel",
            wraplength=380,
        ).pack(anchor="w", pady=(12, 0))

    # -- log streaming ------------------------------------------------------
    def _drain_logs(self) -> None:
        try:
            while True:
                rec: logging.LogRecord = LOG_QUEUE.get_nowait()
                tag = self._tag_for(rec)
                self._append_log(self._format(rec), tag)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain_logs)

    @staticmethod
    def _tag_for(rec: logging.LogRecord) -> str:
        if rec.levelno >= logging.ERROR:
            return "ERROR"
        if rec.levelno >= logging.WARNING:
            return "WARNING"
        # Heuristic: messages starting with "action:" or "exec" → ACTION tag
        msg = rec.getMessage().lower()
        if msg.startswith(("act ", "action", "exec ", "running")):
            return "ACTION"
        if "completed" in msg or "ok" in msg.split():
            return "OK"
        return "INFO"

    @staticmethod
    def _format(rec: logging.LogRecord) -> str:
        return f"[{rec.levelname}] {rec.name}: {rec.getMessage()}"

    def _append_log(self, line: str, tag: str = "INFO") -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)
        # Reset status pill to Ready after each log line (LLM finished a step).
        self._set_status("ready", THEME["ok"], "●  Ready")

    def _set_status(self, key: str, color: str, label: str) -> None:
        self.status_pill.configure(text=label, fg=color)
        self.status.set({"ready": "Ready", "running": "Running…"}.get(key, key))

    def _on_close(self) -> None:
        self.orch.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
