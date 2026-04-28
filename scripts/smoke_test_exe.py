"""Smoke test for the bundled winagent.exe.

Runs ``winagent.exe --check-only``: forces every heavy submodule to import
inside the bundled Python and exits with code 0. This catches the class of
bug where PyInstaller's bundle is broken at the import layer (relative
imports in the entry script, missing hidden imports, etc.).

Run:
    python scripts/smoke_test_exe.py dist/winagent.exe
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 30.0


def main(exe: str) -> int:
    p = Path(exe)
    if not p.exists():
        print(f"[smoke] FAIL: {exe} does not exist")
        return 2

    size_mb = p.stat().st_size / 1024 / 1024
    print(f"[smoke] launching '{p} --check-only' (size={size_mb:.1f} MB)")
    try:
        proc = subprocess.run(
            [str(p), "--check-only"],
            capture_output=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print(f"[smoke] FAIL: --check-only did not exit within {TIMEOUT_S}s")
        return 1

    print(f"[smoke] exit_code={proc.returncode}")
    if proc.stdout:
        print("--- stdout ---")
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        print("--- stderr ---")
        sys.stdout.buffer.write(proc.stderr)

    if proc.returncode != 0:
        print(f"[smoke] FAIL: non-zero exit code {proc.returncode}")
        return 1

    print("[smoke] OK: bundle imports cleanly")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: smoke_test_exe.py <path-to-winagent.exe>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
