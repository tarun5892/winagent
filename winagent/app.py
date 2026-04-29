"""Application entry point. Uses absolute imports so this module works whether
launched via ``python -m winagent`` (package context) or as the top-level
script bundled by PyInstaller (no package context).
"""
from __future__ import annotations

import os
import sys

from winagent import user_config
from winagent.llm_base import PROVIDER_KEY_ENV
from winagent.ui import WinAgentUI, prompt_for_provider_setup


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
            llm_base,
            logger,
            memory,
            openai_compat_client,
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

    # Resolve the active provider + key before constructing the orchestrator.
    # Env var > saved config > first-run popup.
    provider = user_config.get_provider()
    if not user_config.get_provider_api_key(provider):
        choice = prompt_for_provider_setup(initial_provider=provider)
        if choice is not None:
            new_provider, new_key, new_model = choice
            user_config.set_provider(new_provider)
            user_config.set_provider_api_key(new_provider, new_key)
            if new_model:
                user_config.set_provider_model(new_provider, new_model)
            provider = new_provider
        # If the user dismissed the dialog we still launch the UI; the first
        # plan() call surfaces a clear "<PROVIDER>_API_KEY not set" error in
        # the log, which is friendlier than crashing on launch.

    # Make sure the provider's env var is populated even if the value came
    # from disk (CONFIG was frozen at module-import time).
    saved_key = user_config.get_provider_api_key(provider)
    env_name = PROVIDER_KEY_ENV.get(provider, "")
    if saved_key and env_name and not os.environ.get(env_name):
        os.environ[env_name] = saved_key

    WinAgentUI().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
