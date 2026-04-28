"""Central configuration. Override via env vars."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
    memory_window: int = int(os.environ.get("WINAGENT_MEMORY_WINDOW", "5"))
    screenshot_max_width: int = int(os.environ.get("WINAGENT_SHOT_MAX_W", "1280"))
    screenshot_jpeg_quality: int = int(os.environ.get("WINAGENT_SHOT_Q", "70"))
    api_timeout_s: float = float(os.environ.get("WINAGENT_API_TIMEOUT", "45"))
    max_actions_per_cycle: int = 25
    pyautogui_pause_s: float = 0.15
    confirmation_default: bool = True


CONFIG = Config()
