"""tkinter UI smoke test (skipped when no display is available)."""
from __future__ import annotations

import os
import time

import pytest

tk = pytest.importorskip("tkinter")

if not os.environ.get("DISPLAY"):
    pytest.skip("no DISPLAY available", allow_module_level=True)


def _make_orch():
    from winagent.executor import Executor
    from winagent.memory import MemoryManager
    from winagent.orchestrator import Orchestrator

    class StubClient:
        def plan(self, *a, **k):
            return {"actions": [], "memory_update": None}

    return Orchestrator(
        confirm_fn=lambda _t: True,
        confirmation_mode=False,
        client=StubClient(),
        capture_fn=lambda: (b"\xff\xd8\xff", (10, 10)),
        executor=Executor(),
        memory=MemoryManager(window=3),
    )


def test_ui_constructs_and_handles_submit():
    from winagent.ui import WinAgentUI

    ui = WinAgentUI(orchestrator=_make_orch())
    try:
        ui.entry.insert(0, "noop")
        ui._on_submit()
        ui.root.update()
        # process the queue worker
        time.sleep(0.2)
        ui.root.update()
        assert ui.status.get() != ""
    finally:
        ui._on_close()
