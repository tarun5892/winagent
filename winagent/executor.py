"""Action handler registry. One function per action type."""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any

from . import coding_tools
from .config import CONFIG
from .logger import get_logger
from .schema import (
    Action,
    ApplyPatchAction,
    ClickAction,
    ExcelAction,
    FileDeleteAction,
    FileEditAction,
    FileReadAction,
    FileWriteAction,
    FindFilesAction,
    GrepAction,
    HotkeyAction,
    ListDirAction,
    MoveAction,
    PowerShellAction,
    ScreenshotAction,
    ScrollAction,
    ShellAction,
    TypeAction,
    WaitAction,
)

log = get_logger("executor")

Handler = Callable[[Any], dict[str, Any]]


def _import_pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = CONFIG.pyautogui_pause_s
    return pyautogui


class Executor:
    """Dispatches validated ``Action`` objects to platform handlers."""

    def __init__(self, project_root: str | None = None) -> None:
        self.project_root: str = project_root or coding_tools.default_project_root()
        self._handlers: dict[type, Handler] = {
            ClickAction: self._click,
            MoveAction: self._move,
            TypeAction: self._type,
            HotkeyAction: self._hotkey,
            ScrollAction: self._scroll,
            WaitAction: self._wait,
            PowerShellAction: self._powershell,
            ExcelAction: self._excel,
            ScreenshotAction: self._screenshot,
            FileReadAction: self._file_read,
            FileWriteAction: self._file_write,
            FileEditAction: self._file_edit,
            FileDeleteAction: self._file_delete,
            ListDirAction: self._list_dir,
            ApplyPatchAction: self._apply_patch,
            ShellAction: self._shell,
            GrepAction: self._grep,
            FindFilesAction: self._find_files,
        }

    def run(self, actions: list[Action]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for a in actions:
            h = self._handlers.get(type(a))
            if not h:
                results.append(
                    {"ok": False, "type": getattr(a, "type", "?"), "error": "no handler"}
                )
                continue
            try:
                log.info("exec %s", a.model_dump())
                out = h(a)
                results.append({"ok": True, "type": a.type, "result": out})
            except Exception as e:  # noqa: BLE001
                log.exception("action failed: %s", a.type)
                results.append({"ok": False, "type": a.type, "error": str(e)})
        return results

    # ---- handlers ---------------------------------------------------------
    def _click(self, a: ClickAction) -> dict[str, Any]:
        pg = _import_pyautogui()
        pg.click(x=a.x, y=a.y, clicks=a.clicks, button=a.button)
        return {"x": a.x, "y": a.y}

    def _move(self, a: MoveAction) -> dict[str, Any]:
        pg = _import_pyautogui()
        pg.moveTo(a.x, a.y, duration=0.1)
        return {"x": a.x, "y": a.y}

    def _type(self, a: TypeAction) -> dict[str, Any]:
        pg = _import_pyautogui()
        pg.typewrite(a.text, interval=a.interval_ms / 1000.0)
        return {"len": len(a.text)}

    def _hotkey(self, a: HotkeyAction) -> dict[str, Any]:
        pg = _import_pyautogui()
        pg.hotkey(*a.keys)
        return {"keys": a.keys}

    def _scroll(self, a: ScrollAction) -> dict[str, Any]:
        pg = _import_pyautogui()
        pg.scroll(a.dy)
        return {"dy": a.dy}

    def _wait(self, a: WaitAction) -> dict[str, Any]:
        time.sleep(a.ms / 1000.0)
        return {"ms": a.ms}

    def _powershell(self, a: PowerShellAction) -> dict[str, Any]:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", a.command],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-1000:],
        }

    def _screenshot(self, _a: ScreenshotAction) -> dict[str, Any]:
        return {"note": "fresh screenshot will be captured on next cycle"}

    def _excel(self, a: ExcelAction) -> dict[str, Any]:
        import win32com.client  # type: ignore[import-not-found]

        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = True
        excel.DisplayAlerts = False
        op = a.operation
        wb = excel.ActiveWorkbook

        if op == "open":
            if not a.path:
                raise ValueError("excel.open requires path")
            wb = excel.Workbooks.Open(a.path)
            return {"op": op, "path": a.path}

        if op == "close":
            if wb:
                wb.Close(SaveChanges=False)
            return {"op": op}

        if op == "save":
            if wb is None:
                raise RuntimeError("no active workbook to save")
            wb.Save()
            return {"op": op}

        if op == "save_as":
            if wb is None or not a.path:
                raise ValueError("excel.save_as requires active workbook + path")
            wb.SaveAs(a.path)
            return {"op": op, "path": a.path}

        if op == "add_sheet":
            wb = wb or excel.Workbooks.Add()
            sh = wb.Worksheets.Add()
            if a.sheet:
                sh.Name = a.sheet
            return {"op": op, "sheet": sh.Name}

        if op == "select_sheet":
            if wb is None or not a.sheet:
                raise ValueError("excel.select_sheet requires sheet")
            wb.Worksheets(a.sheet).Activate()
            return {"op": op, "sheet": a.sheet}

        if op == "write_cell":
            if a.cell is None:
                raise ValueError("excel.write_cell requires cell")
            wb = wb or excel.Workbooks.Add()
            sh = wb.Worksheets(a.sheet) if a.sheet else wb.ActiveSheet
            sh.Range(a.cell).Value = a.value
            return {"op": op, "cell": a.cell}

        if op == "read_cell":
            if wb is None or a.cell is None:
                raise ValueError("excel.read_cell requires active workbook + cell")
            sh = wb.Worksheets(a.sheet) if a.sheet else wb.ActiveSheet
            return {"op": op, "cell": a.cell, "value": sh.Range(a.cell).Value}

        if op == "write_range":
            if not a.range or a.values is None:
                raise ValueError("excel.write_range requires range + values")
            wb = wb or excel.Workbooks.Add()
            sh = wb.Worksheets(a.sheet) if a.sheet else wb.ActiveSheet
            sh.Range(a.range).Value = a.values
            return {"op": op, "range": a.range}

        if op == "run_vba":
            if wb is None or not a.vba_code:
                raise ValueError("excel.run_vba requires active workbook + vba_code")
            vbproj = wb.VBProject
            mod = vbproj.VBComponents.Add(1)  # vbext_ct_StdModule
            mod.CodeModule.AddFromString(a.vba_code)
            try:
                excel.Run(f"{mod.Name}.WinAgentMain")
            finally:
                vbproj.VBComponents.Remove(mod)
            return {"op": op}

        raise ValueError(f"unsupported excel op: {op}")

    # ---- coding-agent handlers -------------------------------------------
    def _file_read(self, a: FileReadAction) -> dict[str, Any]:
        return coding_tools.file_read(a, self.project_root)

    def _file_write(self, a: FileWriteAction) -> dict[str, Any]:
        return coding_tools.file_write(a, self.project_root)

    def _file_edit(self, a: FileEditAction) -> dict[str, Any]:
        return coding_tools.file_edit(a, self.project_root)

    def _file_delete(self, a: FileDeleteAction) -> dict[str, Any]:
        return coding_tools.file_delete(a, self.project_root)

    def _list_dir(self, a: ListDirAction) -> dict[str, Any]:
        return coding_tools.list_dir(a, self.project_root)

    def _apply_patch(self, a: ApplyPatchAction) -> dict[str, Any]:
        return coding_tools.apply_patch(a, self.project_root)

    def _shell(self, a: ShellAction) -> dict[str, Any]:
        return coding_tools.shell_run(a, self.project_root)

    def _grep(self, a: GrepAction) -> dict[str, Any]:
        return coding_tools.grep_search(a, self.project_root)

    def _find_files(self, a: FindFilesAction) -> dict[str, Any]:
        return coding_tools.find_files(a, self.project_root)
