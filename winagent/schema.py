"""Strict action schema. Single source of truth for the LLM contract."""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClickAction(_StrictModel):
    type: Literal["click"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    button: Literal["left", "right", "middle"] = "left"
    clicks: int = Field(default=1, ge=1, le=3)


class MoveAction(_StrictModel):
    type: Literal["move"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class TypeAction(_StrictModel):
    type: Literal["type"]
    text: str = Field(max_length=4000)
    interval_ms: int = Field(default=15, ge=0, le=200)


class HotkeyAction(_StrictModel):
    type: Literal["hotkey"]
    keys: list[str] = Field(min_length=1, max_length=5)


class ScrollAction(_StrictModel):
    type: Literal["scroll"]
    dy: int


class WaitAction(_StrictModel):
    type: Literal["wait"]
    ms: int = Field(ge=0, le=10_000)


class PowerShellAction(_StrictModel):
    type: Literal["powershell"]
    command: str = Field(max_length=2000)


class ExcelAction(_StrictModel):
    type: Literal["excel"]
    operation: Literal[
        "open", "close", "save", "save_as",
        "write_cell", "read_cell", "write_range",
        "add_sheet", "select_sheet", "run_vba",
    ]
    path: str | None = None
    sheet: str | None = None
    cell: str | None = None
    value: str | None = None
    range: str | None = None
    values: list[list[str]] | None = None
    vba_code: str | None = None


class ScreenshotAction(_StrictModel):
    type: Literal["screenshot"]


Action = Union[  # noqa: UP007 — Pydantic v2 needs ``Union[...]`` for discriminated unions on some pythons
    ClickAction,
    MoveAction,
    TypeAction,
    HotkeyAction,
    ScrollAction,
    WaitAction,
    PowerShellAction,
    ExcelAction,
    ScreenshotAction,
]


class MemoryUpdate(_StrictModel):
    current_goal: str | None = Field(default=None, max_length=256)
    notes: str | None = Field(default=None, max_length=512)


class AgentResponse(BaseModel):
    """Top-level Gemini response. Uses discriminated union on ``type``."""

    model_config = ConfigDict(extra="forbid")

    actions: list[Action] = Field(default_factory=list, max_length=25)
    memory_update: MemoryUpdate | None = None
