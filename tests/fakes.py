"""Fakes used across tests."""
from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Excel COM fake
# ---------------------------------------------------------------------------
class FakeRange:
    def __init__(self, sheet: FakeSheet, address: str) -> None:
        self._sheet = sheet
        self._address = address

    @property
    def Value(self) -> Any:  # noqa: N802
        return self._sheet.cells.get(self._address)

    @Value.setter
    def Value(self, v: Any) -> None:  # noqa: N802
        self._sheet.cells[self._address] = v


class FakeSheet:
    def __init__(self, name: str = "Sheet1") -> None:
        self.Name = name  # noqa: N815
        self.cells: dict[str, Any] = {}
        self.activated = False

    def Range(self, address: str) -> FakeRange:  # noqa: N802
        return FakeRange(self, address)

    def Activate(self) -> None:  # noqa: N802
        self.activated = True


class FakeWorksheets:
    def __init__(self, sheets: list[FakeSheet] | None = None) -> None:
        self._sheets = sheets if sheets is not None else [FakeSheet()]

    def __call__(self, key: Any) -> FakeSheet:
        if isinstance(key, int):
            return self._sheets[key - 1]
        for s in self._sheets:
            if s.Name == key:
                return s
        raise KeyError(key)

    def Add(self) -> FakeSheet:  # noqa: N802
        s = FakeSheet(f"Sheet{len(self._sheets) + 1}")
        self._sheets.append(s)
        return s


class FakeVBComponents:
    def __init__(self) -> None:
        self.components: list[Any] = []
        self.removed: list[str] = []

    def Add(self, kind: int) -> Any:  # noqa: N802
        class _Mod:
            def __init__(self, name: str) -> None:
                self.Name = name  # noqa: N815

                class _CM:
                    def __init__(self) -> None:
                        self.code = ""

                    def AddFromString(self, s: str) -> None:  # noqa: N802
                        self.code += s

                self.CodeModule = _CM()  # noqa: N815

        m = _Mod(f"Module{len(self.components) + 1}")
        self.components.append(m)
        return m

    def Remove(self, m: Any) -> None:  # noqa: N802
        self.removed.append(m.Name)
        self.components = [c for c in self.components if c is not m]


class FakeVBProject:
    def __init__(self) -> None:
        self.VBComponents = FakeVBComponents()  # noqa: N815


class FakeWorkbook:
    def __init__(self, app: FakeExcelApp, path: str | None = None) -> None:
        self.app = app
        self.path = path
        self.Worksheets = FakeWorksheets()  # noqa: N815
        self.ActiveSheet = self.Worksheets._sheets[0]  # noqa: N815
        self.VBProject = FakeVBProject()  # noqa: N815
        self.saved = False
        self.closed = False

    def Save(self) -> None:  # noqa: N802
        self.saved = True

    def SaveAs(self, path: str) -> None:  # noqa: N802
        self.path = path
        self.saved = True

    def Close(self, SaveChanges: bool = False) -> None:  # noqa: N802, N803
        self.closed = True


class FakeWorkbooks:
    def __init__(self, app: FakeExcelApp) -> None:
        self.app = app

    def Add(self) -> FakeWorkbook:  # noqa: N802
        wb = FakeWorkbook(self.app)
        self.app._workbooks.append(wb)
        self.app.ActiveWorkbook = wb
        return wb

    def Open(self, path: str) -> FakeWorkbook:  # noqa: N802
        wb = FakeWorkbook(self.app, path=path)
        self.app._workbooks.append(wb)
        self.app.ActiveWorkbook = wb
        return wb


class FakeExcelApp:
    def __init__(self) -> None:
        self.Visible = False  # noqa: N815
        self.DisplayAlerts = True  # noqa: N815
        self._workbooks: list[FakeWorkbook] = []
        self.ActiveWorkbook: FakeWorkbook | None = None  # noqa: N815
        self.Workbooks = FakeWorkbooks(self)  # noqa: N815
        self.runs: list[str] = []

    def Run(self, name: str) -> None:  # noqa: N802
        self.runs.append(name)


# ---------------------------------------------------------------------------
# Gemini fake (looks/feels like google.generativeai)
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeStream:
    """Iterator emitting incremental chunks then EOF."""

    def __init__(self, chunks: list[str]) -> None:
        self._iter = iter(_FakeResponse(c) for c in chunks)

    def __iter__(self) -> _FakeStream:
        return self

    def __next__(self) -> _FakeResponse:
        return next(self._iter)


class FakeGenerativeModel:
    def __init__(self, model: str, **_: Any) -> None:
        self.model = model
        self.calls: list[dict[str, Any]] = []
        self.next_response: str = json.dumps({"actions": [], "memory_update": None})
        # If set, streaming responses split next_response into these pieces;
        # otherwise the full text is delivered as one chunk.
        self.next_chunks: list[str] | None = None

    def generate_content(
        self, parts: Any, stream: bool = False, **kw: Any
    ) -> _FakeResponse | _FakeStream:
        self.calls.append({"parts": parts, "stream": stream, **kw})
        if stream:
            chunks = self.next_chunks if self.next_chunks is not None else [self.next_response]
            return _FakeStream(chunks)
        return _FakeResponse(self.next_response)


class FakeGenAI:
    """Mimics ``google.generativeai`` module surface."""

    def __init__(self) -> None:
        self.configured_with: str | None = None
        self.last_model: FakeGenerativeModel | None = None

    def configure(self, api_key: str = "", **_: Any) -> None:
        self.configured_with = api_key

    def GenerativeModel(  # noqa: N802 (mirroring upstream PascalCase)
        self,
        model: str,
        **kw: Any,
    ) -> FakeGenerativeModel:
        m = FakeGenerativeModel(model, **kw)
        self.last_model = m
        return m
