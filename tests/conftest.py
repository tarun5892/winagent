"""Test scaffolding. Stubs Windows-only / network-only deps so the suite runs on Linux."""
from __future__ import annotations

import sys
import types
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Lightweight module stubs for pyautogui, win32com, google.generativeai, mss
# ---------------------------------------------------------------------------

class _RecordingPyAutoGUI(types.ModuleType):
    """Stub of pyautogui that records calls instead of touching a desktop."""

    def __init__(self) -> None:
        super().__init__("pyautogui")
        self.calls: list[dict[str, Any]] = []
        self.FAILSAFE = False
        self.PAUSE = 0.0

    def click(self, **kw: Any) -> None:
        self.calls.append({"fn": "click", **kw})

    def moveTo(self, x: int, y: int, duration: float = 0) -> None:  # noqa: N802
        self.calls.append({"fn": "moveTo", "x": x, "y": y, "duration": duration})

    def typewrite(self, text: str, interval: float = 0) -> None:
        self.calls.append({"fn": "typewrite", "text": text, "interval": interval})

    def hotkey(self, *keys: str) -> None:
        self.calls.append({"fn": "hotkey", "keys": list(keys)})

    def scroll(self, dy: int) -> None:
        self.calls.append({"fn": "scroll", "dy": dy})


class _StubWin32ComClient(types.ModuleType):
    """Singleton-style Excel.Application stub matching win32com behavior."""

    def __init__(self) -> None:
        super().__init__("win32com.client")
        self._apps: dict[str, Any] = {}
        self.last_dispatch: Any = None

    def Dispatch(self, name: str) -> Any:  # noqa: N802
        from tests.fakes import FakeExcelApp

        if name not in self._apps:
            self._apps[name] = FakeExcelApp()
        app = self._apps[name]
        self.last_dispatch = app
        return app

    def reset(self) -> None:
        self._apps.clear()
        self.last_dispatch = None


@pytest.fixture(autouse=True)
def stub_pyautogui(monkeypatch: pytest.MonkeyPatch) -> _RecordingPyAutoGUI:
    mod = _RecordingPyAutoGUI()
    monkeypatch.setitem(sys.modules, "pyautogui", mod)
    return mod


@pytest.fixture(autouse=True)
def stub_win32com(monkeypatch: pytest.MonkeyPatch):
    pkg = types.ModuleType("win32com")
    client = _StubWin32ComClient()
    pkg.client = client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32com", pkg)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    yield client
    client.reset()


@pytest.fixture
def fake_genai(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake ``google.generativeai`` module."""
    from tests.fakes import FakeGenAI

    fake = FakeGenAI()
    pkg = types.ModuleType("google")
    pkg.generativeai = fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    return fake
