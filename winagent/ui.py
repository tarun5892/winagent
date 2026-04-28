"""tkinter UI: input, submit, confirm-mode toggle, scrollable log panel."""
from __future__ import annotations

import logging
import queue
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext

from .logger import LOG_QUEUE, setup_logging
from .orchestrator import Orchestrator

POLL_MS = 100
APIKEY_HELP_URL = "https://aistudio.google.com/app/apikey"


def prompt_for_api_key(parent: tk.Misc | None = None) -> str | None:
    """First-run modal that asks the user for a Gemini API key.

    Returns the entered key (stripped) or ``None`` if the user cancelled.
    """
    owns_root = parent is None
    root = tk.Tk() if owns_root else tk.Toplevel(parent)
    root.title("WinAgent — first-run setup")
    root.geometry("520x230")
    root.resizable(False, False)

    tk.Label(
        root,
        text="Welcome to WinAgent",
        font=("Segoe UI", 14, "bold"),
    ).pack(pady=(14, 4))
    tk.Label(
        root,
        text=(
            "Paste your free Gemini API key below.\n"
            "You only need to do this once — it's saved to:\n"
            "%APPDATA%\\WinAgent\\config.json"
        ),
        justify="center",
    ).pack(pady=(0, 6))

    link = tk.Label(
        root,
        text="Get a free key →",
        fg="#1a73e8",
        cursor="hand2",
    )
    link.pack()
    link.bind("<Button-1>", lambda _e: webbrowser.open(APIKEY_HELP_URL))

    var = tk.StringVar()
    entry = tk.Entry(root, textvariable=var, show="*", width=54)
    entry.pack(pady=10)
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

    btns = tk.Frame(root)
    btns.pack(pady=8)
    tk.Button(btns, text="Save & continue", width=16, command=submit).pack(side=tk.LEFT, padx=6)
    tk.Button(btns, text="Skip", width=10, command=cancel).pack(side=tk.LEFT, padx=6)
    entry.bind("<Return>", submit)

    root.protocol("WM_DELETE_WINDOW", cancel)
    if owns_root:
        root.mainloop()
    else:
        root.wait_window()
    return result["key"]


class WinAgentUI:
    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        setup_logging()
        self.root = tk.Tk()
        self.root.title("WinAgent")
        self.root.geometry("760x520")

        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=8, pady=6)
        tk.Label(top, text="Command:").pack(side=tk.LEFT)
        self.entry = tk.Entry(top)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.entry.bind("<Return>", lambda _e: self._on_submit())
        self.submit_btn = tk.Button(top, text="Submit", command=self._on_submit)
        self.submit_btn.pack(side=tk.LEFT)

        opts = tk.Frame(self.root)
        opts.pack(fill=tk.X, padx=8)
        self.confirm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opts,
            text="Confirm before executing",
            variable=self.confirm_var,
            command=self._toggle_confirm,
        ).pack(side=tk.LEFT)
        tk.Button(opts, text="Reset memory", command=self._reset_memory).pack(side=tk.RIGHT)

        self.log = scrolledtext.ScrolledText(
            self.root,
            height=24,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.log.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        self.status = tk.StringVar(value="ready")
        tk.Label(
            self.root,
            textvariable=self.status,
            anchor="w",
            relief=tk.SUNKEN,
        ).pack(fill=tk.X, side=tk.BOTTOM)

        self.orch = orchestrator or Orchestrator(
            confirm_fn=self._confirm_dialog,
            confirmation_mode=True,
        )
        if not self.orch.is_alive():
            self.orch.start()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(POLL_MS, self._drain_logs)

    def _on_submit(self) -> None:
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.entry.delete(0, tk.END)
        self.status.set(f"running: {cmd[:60]}")
        self.orch.submit(cmd)

    def _toggle_confirm(self) -> None:
        self.orch.safety.confirmation_mode = self.confirm_var.get()

    def _reset_memory(self) -> None:
        self.orch.memory.reset()
        self._append_log("[ui] memory reset")

    def _confirm_dialog(self, summary: str) -> bool:
        return messagebox.askyesno(
            "Confirm plan",
            f"Execute these actions?\n\n{summary}",
        )

    def _drain_logs(self) -> None:
        try:
            while True:
                rec: logging.LogRecord = LOG_QUEUE.get_nowait()
                self._append_log(self._format(rec))
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain_logs)

    @staticmethod
    def _format(rec: logging.LogRecord) -> str:
        return f"[{rec.levelname}] {rec.name}: {rec.getMessage()}"

    def _append_log(self, line: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)
        self.status.set("ready")

    def _on_close(self) -> None:
        self.orch.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
