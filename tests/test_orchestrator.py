"""Orchestrator end-to-end with mocks."""
from __future__ import annotations

from typing import Any

from winagent.executor import Executor
from winagent.memory import MemoryManager
from winagent.orchestrator import Job, Orchestrator


class StubClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_call: dict[str, Any] = {}

    def plan(self, command, screenshot_jpeg, screen_size, memory):
        self.last_call = dict(
            command=command,
            screenshot_jpeg=screenshot_jpeg,
            screen_size=screen_size,
            memory=memory,
        )
        return self.response


def _capture():
    return b"\xff\xd8\xff", (800, 600)


def _make(orch_kwargs=None, response=None):
    response = response or {"actions": [], "memory_update": None}
    client = StubClient(response)
    o = Orchestrator(
        confirm_fn=lambda _t: True,
        confirmation_mode=False,
        client=client,
        capture_fn=_capture,
        executor=Executor(),
        memory=MemoryManager(window=5),
        **(orch_kwargs or {}),
    )
    return o, client


def test_cycle_executes_simple_plan_and_updates_memory():
    o, client = _make(response={
        "actions": [
            {"type": "hotkey", "keys": ["win", "r"]},
            {"type": "type", "text": "notepad"},
        ],
        "memory_update": {"current_goal": "open notepad"},
    })
    o.run_cycle(Job(command="open notepad"))
    snap = o.memory.snapshot()
    assert snap["recent_commands"] == ["open notepad"]
    assert snap["current_goal"] == "open notepad"
    assert len(snap["recent_actions"]) == 2
    # memory was passed to client
    assert client.last_call["memory"]["recent_commands"] == ["open notepad"]


def test_cycle_drops_destructive_powershell_and_runs_rest():
    o, _ = _make(response={
        "actions": [
            {"type": "type", "text": "safe"},
            {"type": "powershell", "command": "shutdown /s"},
        ]
    })
    o.run_cycle(Job(command="x"))
    snap = o.memory.snapshot()
    types = [a["type"] for a in snap["recent_actions"]]
    assert types == ["type"]


def test_cycle_aborts_on_invalid_schema():
    o, _ = _make(response={"actions": [{"type": "selfdestruct"}]})
    o.run_cycle(Job(command="x"))
    snap = o.memory.snapshot()
    # command recorded but no actions executed
    assert snap["recent_commands"] == ["x"]
    assert snap["recent_actions"] == []


def test_cycle_aborts_when_user_declines():
    declined = {"v": False}
    o, _ = _make(orch_kwargs={})
    o.safety._confirm = lambda _t: declined.update(v=True) or False  # type: ignore[attr-defined]
    o.safety.confirmation_mode = True
    # use a response with actions so the confirm dialog is reached
    o._client.response = {"actions": [{"type": "wait", "ms": 1}]}  # type: ignore[attr-defined]
    o.run_cycle(Job(command="x"))
    assert declined["v"] is True
    assert o.memory.snapshot()["recent_actions"] == []


def test_cycle_handles_plan_exception_gracefully():
    class Boom:
        def plan(self, *a, **k):
            raise RuntimeError("api down")

    o = Orchestrator(
        confirm_fn=lambda _t: True,
        confirmation_mode=False,
        client=Boom(),
        capture_fn=_capture,
    )
    # should not raise
    o.run_cycle(Job(command="x"))
    assert o.memory.snapshot()["recent_actions"] == []


def test_thread_runs_and_processes_queue():
    import time

    o, _ = _make(response={"actions": [{"type": "wait", "ms": 1}]})
    o.start()
    try:
        o.submit("c1")
        # Poll for the command to land in memory
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if o.memory.snapshot()["recent_commands"] == ["c1"]:
                break
            time.sleep(0.05)
    finally:
        o.stop()
        o.join(timeout=2.0)
    assert not o.is_alive()


def test_on_busy_callback_fires_around_each_job():
    """The orchestrator should mark itself busy=True before run_cycle and
    busy=False after, on every queued job — so the UI can disable inputs
    while a request is in flight."""
    import time

    busy_log: list[bool] = []
    o, _ = _make(
        orch_kwargs={"on_busy": busy_log.append},
        response={"actions": [{"type": "wait", "ms": 1}]},
    )
    o.start()
    try:
        o.submit("hello")
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if busy_log[-2:] == [True, False]:
                break
            time.sleep(0.02)
    finally:
        o.stop()
        o.join(timeout=2.0)
    # We expect at least one True followed by False; the trailing stop()
    # may or may not push more True/False depending on timing — just check
    # that the first job produced the expected pair.
    assert busy_log[:2] == [True, False], busy_log


def test_on_busy_callback_runs_even_on_plan_exception():
    """If the LLM blows up, busy=False must still fire so the UI doesn't
    stick on 'Working on it…' forever."""

    class BoomClient:
        def plan(self, *_a, **_kw):
            raise RuntimeError("simulated network failure")

    busy_log: list[bool] = []
    o = Orchestrator(
        confirm_fn=lambda _t: True,
        confirmation_mode=False,
        client=BoomClient(),
        capture_fn=_capture,
        executor=Executor(),
        memory=MemoryManager(window=5),
        on_busy=busy_log.append,
    )
    import time

    o.start()
    try:
        o.submit("hello")
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if busy_log[-2:] == [True, False]:
                break
            time.sleep(0.02)
    finally:
        o.stop()
        o.join(timeout=2.0)
    assert busy_log[:2] == [True, False], busy_log
