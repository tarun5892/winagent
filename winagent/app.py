"""Application entry point. Uses absolute imports so this module works whether
launched via ``python -m winagent`` (package context) or as the top-level
script bundled by PyInstaller (no package context).
"""
from __future__ import annotations

import os
import sys

from winagent import user_config
from winagent.ui import WinAgentUI, prompt_for_api_key


def main(argv: list[str] | None = None) -> int:
    """Application entry point.

    Returns ``0`` on a clean exit. Accepts ``--check-only`` (or
    ``--smoke-test``) to import all heavy submodules and exit immediately —
    used by CI to catch broken PyInstaller bundles without launching the GUI.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("--check-only", "--smoke-test") for a in args):
        # Force-import every module the GUI would load so a broken bundle
        # surfaces here instead of when the user double-clicks.
        from winagent import (  # noqa: F401
            coding_tools,
            config,
            executor,
            gemini_client,
            logger,
            memory,
            orchestrator,
            prompts,
            safety,
            schema,
            ui,
            vision,
        )

        # Don't print to stdout: the windowed PyInstaller bundle has no
        # console attached, so print() can raise. Exit 0 is the signal.
        return 0

    # Resolve the Gemini API key before constructing the orchestrator so the
    # GeminiClient (lazy-loaded later) sees it. Env var > saved config > popup.
    if not user_config.get_api_key():
        key = prompt_for_api_key()
        if key:
            user_config.set_api_key(key)
        # If the user dismisses the dialog we still launch the UI; the first
        # plan() call will surface a clear "GEMINI_API_KEY not set" error in
        # the log, which is friendlier than crashing on launch.
    else:
        # Make sure the env var is populated even if the value came from disk,
        # since CONFIG was frozen at import time.
        saved = user_config.get_api_key()
        if saved and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = saved

    WinAgentUI().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
