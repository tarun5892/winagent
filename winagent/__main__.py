from . import user_config
from .ui import WinAgentUI, prompt_for_api_key


def main() -> None:
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
        import os

        saved = user_config.get_api_key()
        if saved and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = saved

    WinAgentUI().run()


if __name__ == "__main__":
    main()
