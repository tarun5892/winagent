"""Tests for the application entry-point and the --check-only flag."""
from __future__ import annotations

import subprocess
import sys

import pytest

# tkinter is part of stdlib on Windows/macOS but on minimal Linux CI images
# it may be absent. Skip the import-heavy tests there; the same code paths
# are still exercised on Windows by the .exe smoke-test job.
tk = pytest.importorskip("tkinter")


def test_check_only_imports_cleanly_via_python_m_winagent():
    """Top-level smoke test: ``python -m winagent --check-only`` returns 0
    after force-importing every submodule the GUI would load."""
    proc = subprocess.run(
        [sys.executable, "-m", "winagent", "--check-only"],
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"--check-only failed:\n--- stdout ---\n{proc.stdout.decode()}\n"
        f"--- stderr ---\n{proc.stderr.decode()}"
    )


def test_run_winagent_script_uses_absolute_imports():
    """The PyInstaller entry script must not contain any relative imports."""
    src = open("run_winagent.py", encoding="utf-8").read()
    # Search for `from .` lines (relative imports). Module-level only.
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("from .") or s.startswith("import ."):
            raise AssertionError(f"relative import in run_winagent.py: {line!r}")


def test_app_module_uses_absolute_imports():
    src = open("winagent/app.py", encoding="utf-8").read()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("from .") or s.startswith("import ."):
            raise AssertionError(f"relative import in winagent/app.py: {line!r}")


def test_check_only_via_app_main_returns_zero():
    """Calling ``app.main(['--check-only'])`` directly returns 0."""
    from winagent.app import main

    assert main(["--check-only"]) == 0
    assert main(["--smoke-test"]) == 0
