"""Filesystem / shell / search tools for the coding-agent action set.

All paths are resolved against ``project_root`` (the orchestrator/config setting)
and prevented from escaping it. This is *not* a security boundary — it's a
guard rail against the LLM accidentally touching unrelated parts of the disk.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .logger import get_logger
from .schema import (
    ApplyPatchAction,
    FileDeleteAction,
    FileEditAction,
    FileReadAction,
    FileWriteAction,
    FindFilesAction,
    GrepAction,
    ListDirAction,
    ShellAction,
)

log = get_logger("coding_tools")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _resolve(path: str, project_root: str) -> Path:
    root = Path(project_root).expanduser().resolve()
    p = Path(path).expanduser()
    candidate = (p if p.is_absolute() else (root / p)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise PermissionError(
            f"path escapes project root: {candidate} not under {root}"
        ) from e
    return candidate


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def file_read(a: FileReadAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists():
        raise FileNotFoundError(p)
    if not p.is_file():
        raise IsADirectoryError(p)
    raw = p.read_bytes()[: a.max_bytes]
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if a.offset or a.limit:
        end = a.offset + (a.limit or len(lines))
        sliced = lines[a.offset : end]
        text = "\n".join(sliced)
        return {
            "path": str(p),
            "lines": len(sliced),
            "from": a.offset,
            "to": a.offset + len(sliced),
            "content": text,
        }
    return {
        "path": str(p),
        "lines": len(lines),
        "bytes": len(raw),
        "content": text,
    }


def file_write(a: FileWriteAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if a.create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a.content, encoding="utf-8")
    return {"path": str(p), "bytes": len(a.content.encode("utf-8"))}


def file_edit(a: FileEditAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    count = text.count(a.old_string)
    if count == 0:
        raise ValueError(f"old_string not found in {p}")
    if count > 1 and not a.replace_all:
        raise ValueError(
            f"old_string occurs {count}x in {p}; pass replace_all=true or "
            "supply more context"
        )
    if a.replace_all:
        new_text = text.replace(a.old_string, a.new_string)
    else:
        new_text = text.replace(a.old_string, a.new_string, 1)
    p.write_text(new_text, encoding="utf-8")
    return {"path": str(p), "replaced": count if a.replace_all else 1}


def file_delete(a: FileDeleteAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.is_dir():
        raise IsADirectoryError(f"refusing to delete directory {p}; use shell")
    p.unlink()
    return {"path": str(p), "deleted": True}


def list_dir(a: ListDirAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists() or not p.is_dir():
        raise NotADirectoryError(p)
    entries: list[dict[str, Any]] = []
    iterator = p.rglob("*") if a.recursive else p.iterdir()
    for entry in iterator:
        try:
            stat = entry.stat()
        except OSError:
            continue
        entries.append(
            {
                "path": str(entry.relative_to(p)),
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else None,
            }
        )
        if len(entries) >= a.max_entries:
            break
    return {"path": str(p), "count": len(entries), "entries": entries}


def apply_patch(a: ApplyPatchAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    applied = 0
    for edit in a.edits:
        count = text.count(edit.old_string)
        if count == 0:
            raise ValueError(
                f"edit {applied + 1}/{len(a.edits)}: old_string not found in {p}"
            )
        if count > 1 and not edit.replace_all:
            raise ValueError(
                f"edit {applied + 1}/{len(a.edits)}: old_string occurs {count}x; "
                "pass replace_all or add context"
            )
        if edit.replace_all:
            text = text.replace(edit.old_string, edit.new_string)
        else:
            text = text.replace(edit.old_string, edit.new_string, 1)
        applied += 1
    p.write_text(text, encoding="utf-8")
    return {"path": str(p), "edits_applied": applied}


def shell_run(a: ShellAction, project_root: str) -> dict[str, Any]:
    cwd = _resolve(a.cwd, project_root) if a.cwd else Path(project_root).resolve()
    is_windows = sys.platform == "win32"
    if is_windows:
        cmd: list[str] = ["powershell", "-NoProfile", "-NonInteractive", "-Command", a.command]
    else:
        cmd = ["/bin/sh", "-c", a.command]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=a.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": None,
            "timed_out": True,
            "stdout": (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))[-2000:],
            "stderr": (e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))[-1000:],
            "command": a.command,
        }
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "command": a.command,
        "cwd": str(cwd),
    }


def grep_search(a: GrepAction, project_root: str) -> dict[str, Any]:
    p = _resolve(a.path, project_root)
    if not p.exists():
        raise FileNotFoundError(p)
    rg = shutil.which("rg")
    if rg:
        return _grep_via_ripgrep(rg, a, p)
    return _grep_pure_python(a, p)


def _grep_via_ripgrep(rg: str, a: GrepAction, root: Path) -> dict[str, Any]:
    args: list[str] = [rg, "--no-config", "--json"]
    if a.case_insensitive:
        args.append("-i")
    if a.context_lines:
        args.extend(["-C", str(a.context_lines)])
    if a.glob_pattern:
        args.extend(["-g", a.glob_pattern])
    if a.output_mode == "files_with_matches":
        args.append("-l")
    if a.output_mode == "count":
        args.append("-c")
    args.append("--")
    args.append(a.pattern)
    args.append(str(root))
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        return {"timed_out": True, "matches": []}
    # ripgrep --json emits NDJSON; parsing it would be heavy. For simplicity,
    # call again without --json for a flat result (this keeps the tool simple).
    args_plain = [a_ for a_ in args if a_ != "--json"]
    proc = subprocess.run(args_plain, capture_output=True, text=True, timeout=30, check=False)
    out = proc.stdout.splitlines()[: a.max_results]
    return {
        "tool": "ripgrep",
        "returncode": proc.returncode,
        "match_count": len(out),
        "matches": out,
    }


def _grep_pure_python(a: GrepAction, root: Path) -> dict[str, Any]:
    flags = re.IGNORECASE if a.case_insensitive else 0
    try:
        regex = re.compile(a.pattern, flags)
    except re.error as e:
        raise ValueError(f"invalid regex: {e}") from e

    files: list[Path]
    if root.is_file():
        files = [root]
    else:
        if a.glob_pattern:
            files = [f for f in root.rglob(a.glob_pattern) if f.is_file()]
        else:
            files = [f for f in root.rglob("*") if f.is_file()]

    matches: list[str] = []
    files_with: set[str] = set()
    counts: dict[str, int] = {}
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                rel = fp.relative_to(root) if root.is_dir() else fp.name
                files_with.add(str(rel))
                counts[str(rel)] = counts.get(str(rel), 0) + 1
                if a.output_mode == "content":
                    matches.append(f"{rel}:{i}:{line}")
                if len(matches) >= a.max_results:
                    break
        if len(matches) >= a.max_results:
            break

    if a.output_mode == "files_with_matches":
        return {"tool": "python", "files": sorted(files_with)}
    if a.output_mode == "count":
        return {"tool": "python", "counts": counts}
    return {"tool": "python", "match_count": len(matches), "matches": matches}


def find_files(a: FindFilesAction, project_root: str) -> dict[str, Any]:
    root = _resolve(a.path, project_root)
    if not root.exists():
        raise FileNotFoundError(root)
    base = root if root.is_dir() else root.parent
    pattern = a.pattern
    results: list[str] = []
    for fp in base.rglob("*"):
        if not fp.is_file():
            continue
        rel = fp.relative_to(base).as_posix()
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(fp.name, pattern):
            results.append(rel)
            if len(results) >= a.max_results:
                break
    return {"path": str(base), "count": len(results), "results": results}


# ---------------------------------------------------------------------------
# Lightweight shell-command safety helper
# ---------------------------------------------------------------------------
_SHELL_DESTRUCTIVE = re.compile(
    r"""
    (?:
        \brm\s+[^\n]*(?:-[a-z]*r[a-z]*|--recursive|-[a-z]*f[a-z]*|--force)\b   # rm -rf, -fr, -Rf, --recursive, etc.
      | \bsudo\s+rm\b
      | \bmkfs\b
      | \bdd\s+if=                                  # dd if=...
      | :\s*\(\s*\)\s*\{\s*:\s*\|\s*:?\s*&\s*\}\s*;\s*:    # fork bomb (any spacing)
      | \b(?:reboot|halt|shutdown|poweroff)\b
      | \binit\s+[0-6]\b                            # init 0/6 (halt/reboot)
      | \btelinit\s+[0-6]\b
      | \bchmod\s+(?:-R\s+)?0?[0-7]{0,2}[0-7]\s+/   # chmod NNN /  (000, 777, etc.)
      | \bchown\s+(?:-R\s+)?\S+\s+/(?:\s|$)         # chown ... /
      | (?<![<>])>\s*/dev/(?:sd[a-z]|hd[a-z]|nvme\d+n\d+|disk\d+)\b   # > /dev/sda, > /dev/nvme0n1
      | (?:wget|curl)\s+[^\n]*\|\s*(?:sh|bash|zsh|ksh)\b              # curl|sh, wget|bash
      | \bmv\s+[^\n]+\s+/dev/null\b                  # mv ... /dev/null (data loss)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


def is_shell_destructive(command: str) -> bool:
    return bool(_SHELL_DESTRUCTIVE.search(command))


def quote_for_log(command: str) -> str:
    return shlex.quote(command)[:160]


# ---------------------------------------------------------------------------
# Compatibility export: project_root accessor (so tests can patch easily)
# ---------------------------------------------------------------------------
def default_project_root() -> str:
    from .config import CONFIG

    return CONFIG.project_root or os.getcwd()
