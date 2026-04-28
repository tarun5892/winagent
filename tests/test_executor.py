"""Executor: verifies each handler dispatches correctly with mocked side-effects."""
from __future__ import annotations

import sys
from typing import Any

import pytest

from winagent.executor import Executor
from winagent.schema import (
    ClickAction,
    ExcelAction,
    HotkeyAction,
    MoveAction,
    PowerShellAction,
    ScreenshotAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)


@pytest.fixture
def executor() -> Executor:
    return Executor()


def _pg() -> Any:
    return sys.modules["pyautogui"]


def test_click_calls_pyautogui(executor: Executor) -> None:
    out = executor.run([ClickAction(type="click", x=10, y=20, clicks=2, button="right")])
    assert out[0]["ok"] is True
    call = _pg().calls[-1]
    assert call == {"fn": "click", "x": 10, "y": 20, "clicks": 2, "button": "right"}


def test_move(executor: Executor) -> None:
    executor.run([MoveAction(type="move", x=5, y=6)])
    assert _pg().calls[-1]["fn"] == "moveTo"


def test_type(executor: Executor) -> None:
    executor.run([TypeAction(type="type", text="hello", interval_ms=20)])
    c = _pg().calls[-1]
    assert c["fn"] == "typewrite" and c["text"] == "hello" and c["interval"] == 0.02


def test_hotkey(executor: Executor) -> None:
    executor.run([HotkeyAction(type="hotkey", keys=["ctrl", "s"])])
    assert _pg().calls[-1] == {"fn": "hotkey", "keys": ["ctrl", "s"]}


def test_scroll(executor: Executor) -> None:
    executor.run([ScrollAction(type="scroll", dy=-3)])
    assert _pg().calls[-1] == {"fn": "scroll", "dy": -3}


def test_wait_uses_time_sleep(executor: Executor, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}
    monkeypatch.setattr("winagent.executor.time.sleep", lambda s: seen.setdefault("s", s))
    executor.run([WaitAction(type="wait", ms=250)])
    assert seen["s"] == 0.25


def test_screenshot_is_noop_marker(executor: Executor) -> None:
    out = executor.run([ScreenshotAction(type="screenshot")])
    assert out[0]["ok"] is True
    assert "next cycle" in out[0]["result"]["note"]


def test_powershell_subprocess_called(
    executor: Executor, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        return _Result()

    monkeypatch.setattr("winagent.executor.subprocess.run", fake_run)
    out = executor.run([PowerShellAction(type="powershell", command="Get-Process")])
    assert out[0]["ok"] is True
    assert captured["cmd"][0] == "powershell"
    assert "Get-Process" in captured["cmd"]
    assert captured["kw"]["timeout"] == 60


def test_handler_exception_is_captured(
    executor: Executor, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**_):
        raise RuntimeError("nope")

    monkeypatch.setattr(_pg(), "click", boom, raising=False)
    out = executor.run([ClickAction(type="click", x=1, y=2)])
    assert out[0]["ok"] is False and "nope" in out[0]["error"]


# ---- Excel handler -------------------------------------------------------
def test_excel_write_cell_creates_workbook_if_needed(executor: Executor) -> None:
    out = executor.run([
        ExcelAction(type="excel", operation="write_cell", cell="A1", value="hi"),
    ])
    assert out[0]["ok"] is True
    app = sys.modules["win32com.client"].last_dispatch
    wb = app.ActiveWorkbook
    assert wb.ActiveSheet.cells["A1"] == "hi"
    assert app.Visible is True
    assert app.DisplayAlerts is False


def test_excel_write_range_atomic(executor: Executor) -> None:
    out = executor.run([
        ExcelAction(
            type="excel",
            operation="write_range",
            range="A1:B2",
            values=[["a", "b"], ["c", "d"]],
        ),
    ])
    assert out[0]["ok"] is True
    app = sys.modules["win32com.client"].last_dispatch
    assert app.ActiveWorkbook.ActiveSheet.cells["A1:B2"] == [["a", "b"], ["c", "d"]]


def test_excel_save_requires_active_workbook(executor: Executor) -> None:
    out = executor.run([ExcelAction(type="excel", operation="save")])
    assert out[0]["ok"] is False
    assert "no active workbook" in out[0]["error"].lower()


def test_excel_save_after_write(executor: Executor) -> None:
    out = executor.run([
        ExcelAction(type="excel", operation="write_cell", cell="A1", value="x"),
        ExcelAction(type="excel", operation="save"),
    ])
    assert all(r["ok"] for r in out)
    app = sys.modules["win32com.client"].last_dispatch
    assert app.ActiveWorkbook.saved is True


def test_excel_open_close(executor: Executor) -> None:
    out = executor.run([
        ExcelAction(type="excel", operation="open", path="C:\\tmp\\x.xlsx"),
        ExcelAction(type="excel", operation="close"),
    ])
    assert all(r["ok"] for r in out)
    app = sys.modules["win32com.client"].last_dispatch
    assert app._workbooks[0].closed is True
    assert app._workbooks[0].path == "C:\\tmp\\x.xlsx"


def test_excel_add_and_select_sheet(executor: Executor) -> None:
    out = executor.run([
        ExcelAction(type="excel", operation="add_sheet", sheet="People"),
        ExcelAction(type="excel", operation="select_sheet", sheet="People"),
    ])
    assert all(r["ok"] for r in out)
    app = sys.modules["win32com.client"].last_dispatch
    sheets = app.ActiveWorkbook.Worksheets._sheets
    assert any(s.Name == "People" and s.activated for s in sheets)


def test_excel_run_vba_injects_and_removes(executor: Executor) -> None:
    code = "Sub WinAgentMain()\n  MsgBox \"hi\"\nEnd Sub"
    out = executor.run([
        ExcelAction(type="excel", operation="add_sheet", sheet="S"),
        ExcelAction(type="excel", operation="run_vba", vba_code=code),
    ])
    assert all(r["ok"] for r in out)
    app = sys.modules["win32com.client"].last_dispatch
    wb = app.ActiveWorkbook
    # module added then removed (cleanup happens in `finally`)
    assert wb.VBProject.VBComponents.removed
    assert app.runs and app.runs[0].endswith(".WinAgentMain")


def test_excel_unsupported_op_is_error(executor: Executor) -> None:
    # bypass schema by constructing manually with a value Pydantic would refuse
    a = ExcelAction(type="excel", operation="save")
    object.__setattr__(a, "operation", "weird")  # type: ignore[arg-type]
    out = executor.run([a])
    assert out[0]["ok"] is False
