"""Tests for the coding-agent action handlers (file/shell/grep/find/patch)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from winagent import coding_tools
from winagent.executor import Executor
from winagent.schema import (
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


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Lay out a small project tree."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "MAX_RETRIES = 3\n\ndef hello():\n    return 'hi'\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "utils.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text(
        "from src.main import hello\n\n"
        "def test_hello(): assert hello() == 'hi'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def ex(tmp_project: Path) -> Executor:
    return Executor(project_root=str(tmp_project))


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------
def test_file_read_full(ex: Executor, tmp_project: Path):
    res = ex.run([FileReadAction(type="file_read", path="src/main.py")])
    assert res[0]["ok"]
    assert "MAX_RETRIES = 3" in res[0]["result"]["content"]


def test_file_read_with_offset_limit(ex: Executor):
    res = ex.run([FileReadAction(type="file_read", path="src/main.py", offset=2, limit=1)])
    assert res[0]["ok"]
    assert res[0]["result"]["content"].rstrip() == "def hello():"


def test_file_read_missing(ex: Executor):
    res = ex.run([FileReadAction(type="file_read", path="src/nope.py")])
    assert not res[0]["ok"]
    assert "nope.py" in res[0]["error"]


def test_file_read_outside_project_blocked(tmp_project: Path):
    ex = Executor(project_root=str(tmp_project))
    res = ex.run([FileReadAction(type="file_read", path="/etc/hosts")])
    assert not res[0]["ok"]
    assert "escapes project root" in res[0]["error"]


# ---------------------------------------------------------------------------
# file_write
# ---------------------------------------------------------------------------
def test_file_write_creates_file_and_dirs(ex: Executor, tmp_project: Path):
    res = ex.run(
        [
            FileWriteAction(
                type="file_write",
                path="src/new/created.py",
                content="x = 1\n",
            )
        ]
    )
    assert res[0]["ok"]
    assert (tmp_project / "src" / "new" / "created.py").read_text(encoding="utf-8") == "x = 1\n"


def test_file_write_overwrites(ex: Executor, tmp_project: Path):
    ex.run([FileWriteAction(type="file_write", path="README.md", content="# new\n")])
    assert (tmp_project / "README.md").read_text(encoding="utf-8") == "# new\n"


# ---------------------------------------------------------------------------
# file_edit
# ---------------------------------------------------------------------------
def test_file_edit_unique_replace(ex: Executor, tmp_project: Path):
    res = ex.run(
        [
            FileEditAction(
                type="file_edit",
                path="src/main.py",
                old_string="MAX_RETRIES = 3",
                new_string="MAX_RETRIES = 5",
            )
        ]
    )
    assert res[0]["ok"]
    assert "MAX_RETRIES = 5" in (tmp_project / "src" / "main.py").read_text(encoding="utf-8")


def test_file_edit_old_string_missing(ex: Executor):
    res = ex.run(
        [
            FileEditAction(
                type="file_edit",
                path="src/main.py",
                old_string="DOES_NOT_EXIST",
                new_string="x",
            )
        ]
    )
    assert not res[0]["ok"]
    assert "not found" in res[0]["error"]


def test_file_edit_ambiguous_requires_replace_all(ex: Executor, tmp_project: Path):
    (tmp_project / "src" / "main.py").write_text("a = 1\na = 1\n", encoding="utf-8")
    res = ex.run(
        [
            FileEditAction(
                type="file_edit",
                path="src/main.py",
                old_string="a = 1",
                new_string="a = 2",
            )
        ]
    )
    assert not res[0]["ok"]
    assert "occurs 2x" in res[0]["error"]

    res2 = ex.run(
        [
            FileEditAction(
                type="file_edit",
                path="src/main.py",
                old_string="a = 1",
                new_string="a = 2",
                replace_all=True,
            )
        ]
    )
    assert res2[0]["ok"]
    assert (tmp_project / "src" / "main.py").read_text(encoding="utf-8") == "a = 2\na = 2\n"


# ---------------------------------------------------------------------------
# file_delete
# ---------------------------------------------------------------------------
def test_file_delete_removes_file(ex: Executor, tmp_project: Path):
    p = tmp_project / "src" / "utils.py"
    assert p.exists()
    res = ex.run([FileDeleteAction(type="file_delete", path="src/utils.py")])
    assert res[0]["ok"]
    assert not p.exists()


def test_file_delete_refuses_directory(ex: Executor):
    res = ex.run([FileDeleteAction(type="file_delete", path="src")])
    assert not res[0]["ok"]
    assert "directory" in res[0]["error"].lower()


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------
def test_list_dir_non_recursive(ex: Executor):
    res = ex.run([ListDirAction(type="list_dir", path="src")])
    assert res[0]["ok"]
    names = [e["path"] for e in res[0]["result"]["entries"]]
    assert "main.py" in names
    assert "utils.py" in names


def test_list_dir_recursive(ex: Executor):
    res = ex.run([ListDirAction(type="list_dir", path=".", recursive=True)])
    assert res[0]["ok"]
    paths = [e["path"] for e in res[0]["result"]["entries"]]
    # rglob may use os.sep; normalise for the assertion
    paths = [p.replace(os.sep, "/") for p in paths]
    assert any(p == "src/main.py" for p in paths)
    assert any(p == "tests/test_main.py" for p in paths)


# ---------------------------------------------------------------------------
# apply_patch
# ---------------------------------------------------------------------------
def test_apply_patch_sequential_edits(ex: Executor, tmp_project: Path):
    res = ex.run(
        [
            ApplyPatchAction(
                type="apply_patch",
                path="src/main.py",
                edits=[
                    {"old_string": "MAX_RETRIES = 3", "new_string": "MAX_RETRIES = 5"},
                    {"old_string": "return 'hi'", "new_string": "return 'hello'"},
                ],
            )
        ]
    )
    assert res[0]["ok"]
    text = (tmp_project / "src" / "main.py").read_text(encoding="utf-8")
    assert "MAX_RETRIES = 5" in text
    assert "return 'hello'" in text


def test_apply_patch_atomic_failure(ex: Executor, tmp_project: Path):
    # second edit fails ⇒ first edit must NOT persist
    original = (tmp_project / "src" / "main.py").read_text(encoding="utf-8")
    res = ex.run(
        [
            ApplyPatchAction(
                type="apply_patch",
                path="src/main.py",
                edits=[
                    {"old_string": "MAX_RETRIES = 3", "new_string": "MAX_RETRIES = 5"},
                    {"old_string": "MISSING_TOKEN", "new_string": "x"},
                ],
            )
        ]
    )
    assert not res[0]["ok"]
    assert (tmp_project / "src" / "main.py").read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only smoke")
def test_shell_runs_command(ex: Executor, tmp_project: Path):
    res = ex.run([ShellAction(type="shell", command="echo hello && ls")])
    assert res[0]["ok"]
    out = res[0]["result"]
    assert out["returncode"] == 0
    assert "hello" in out["stdout"]
    assert "src" in out["stdout"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only smoke")
def test_shell_respects_cwd(ex: Executor, tmp_project: Path):
    res = ex.run([ShellAction(type="shell", command="pwd", cwd="src")])
    assert res[0]["ok"]
    assert (tmp_project / "src").resolve().samefile(res[0]["result"]["stdout"].strip())


def test_shell_destructive_blocked_by_safety_helper():
    assert coding_tools.is_shell_destructive("rm -rf /")
    assert coding_tools.is_shell_destructive("sudo rm /etc/passwd")
    assert coding_tools.is_shell_destructive("dd if=/dev/zero of=/dev/sda")
    assert coding_tools.is_shell_destructive("shutdown -h now")
    assert coding_tools.is_shell_destructive("chmod -R 777 /")
    assert not coding_tools.is_shell_destructive("ls -la")
    assert not coding_tools.is_shell_destructive("python -m pytest")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only smoke")
def test_shell_timeout(ex: Executor):
    res = ex.run([ShellAction(type="shell", command="sleep 5", timeout_s=1)])
    assert res[0]["ok"]  # outer wrapper records timeout as a structured result
    assert res[0]["result"].get("timed_out")


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------
def test_grep_finds_matches(ex: Executor):
    res = ex.run([GrepAction(type="grep", pattern=r"MAX_RETRIES", path=".")])
    assert res[0]["ok"]
    matches = res[0]["result"]["matches"]
    assert any("MAX_RETRIES" in m for m in matches)


def test_grep_files_with_matches_mode(ex: Executor):
    res = ex.run(
        [
            GrepAction(
                type="grep",
                pattern=r"hello",
                path=".",
                output_mode="files_with_matches",
            )
        ]
    )
    assert res[0]["ok"]
    # ripgrep returns a list of matching file paths in 'matches' or 'files'
    payload = res[0]["result"]
    files = payload.get("files") or payload.get("matches") or []
    joined = "\n".join(files)
    assert "main.py" in joined
    assert "test_main.py" in joined


def test_grep_glob_filter(ex: Executor):
    res = ex.run(
        [
            GrepAction(
                type="grep",
                pattern=r"hello",
                path=".",
                glob_pattern="*.py",
                output_mode="files_with_matches",
            )
        ]
    )
    assert res[0]["ok"]


# ---------------------------------------------------------------------------
# find_files
# ---------------------------------------------------------------------------
def test_find_files_glob(ex: Executor):
    res = ex.run([FindFilesAction(type="find_files", pattern="*.py", path=".")])
    assert res[0]["ok"]
    results = res[0]["result"]["results"]
    assert any(r.endswith("main.py") for r in results)
    assert any(r.endswith("test_main.py") for r in results)


def test_find_files_no_match(ex: Executor):
    res = ex.run([FindFilesAction(type="find_files", pattern="*.rs", path=".")])
    assert res[0]["ok"]
    assert res[0]["result"]["results"] == []


# ---------------------------------------------------------------------------
# Path-escape guard
# ---------------------------------------------------------------------------
def test_resolve_blocks_escape(tmp_project: Path):
    with pytest.raises(PermissionError):
        coding_tools._resolve("../outside.txt", str(tmp_project))


def test_resolve_allows_subpath(tmp_project: Path):
    p = coding_tools._resolve("src/main.py", str(tmp_project))
    assert p.is_file()
