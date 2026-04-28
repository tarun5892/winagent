"""MemoryManager: rolling window, summarization, threading."""
from __future__ import annotations

import threading

import pytest

from winagent.memory import MemoryManager


def test_rolling_window_caps():
    m = MemoryManager(window=3)
    for i in range(10):
        m.add_command(f"cmd{i}")
    snap = m.snapshot()
    assert snap["recent_commands"] == ["cmd7", "cmd8", "cmd9"]


def test_actions_summarized_long_type_truncated():
    m = MemoryManager(window=5)
    m.add_actions([{"type": "type", "text": "x" * 200}])
    a = m.snapshot()["recent_actions"][0]
    assert a["text"].endswith("…")
    assert len(a["text"]) <= 61


def test_powershell_command_truncated():
    m = MemoryManager()
    m.add_actions([{"type": "powershell", "command": "Get-Process " * 50}])
    a = m.snapshot()["recent_actions"][0]
    assert len(a["command"]) <= 80


def test_excel_summary_compact():
    m = MemoryManager()
    m.add_actions([
        {
            "type": "excel",
            "operation": "write_range",
            "values": [["x"] * 10] * 10,
            "range": "A1:J10",
            "sheet": "S",
        }
    ])
    a = m.snapshot()["recent_actions"][0]
    assert a == {"type": "excel", "operation": "write_range", "cell": None, "sheet": "S"}


def test_update_goal_and_notes_truncated():
    m = MemoryManager()
    m.update({"current_goal": "g" * 1000, "notes": "n" * 1000})
    s = m.snapshot()
    assert len(s["current_goal"]) == 256
    assert len(s["notes"]) == 512


def test_update_none_is_noop():
    m = MemoryManager()
    m.update(None)
    m.update({})
    assert m.snapshot()["current_goal"] is None


def test_reset_clears_all():
    m = MemoryManager()
    m.add_command("a")
    m.add_actions([{"type": "click", "x": 1, "y": 2}])
    m.update({"current_goal": "g"})
    m.reset()
    s = m.snapshot()
    assert s == {
        "recent_commands": [],
        "recent_actions": [],
        "current_goal": None,
        "notes": None,
    }


def test_invalid_window_rejected():
    with pytest.raises(ValueError):
        MemoryManager(window=0)


def test_thread_safe_concurrent_writes():
    m = MemoryManager(window=1000)

    def writer(i: int) -> None:
        for j in range(50):
            m.add_command(f"t{i}-c{j}")
            m.add_actions([{"type": "wait", "ms": j}])

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = m.snapshot()
    assert len(snap["recent_commands"]) == 400
    assert len(snap["recent_actions"]) == 400
