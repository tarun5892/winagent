"""Tests for the new coding-agent schema variants."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from winagent.schema import (
    AgentResponse,
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


def test_file_read_defaults():
    a = FileReadAction(type="file_read", path="src/main.py")
    assert a.offset == 0
    assert a.limit is None
    assert a.max_bytes == 200_000


def test_file_read_rejects_empty_path():
    with pytest.raises(ValidationError):
        FileReadAction(type="file_read", path="")


def test_file_write_default_content_empty():
    a = FileWriteAction(type="file_write", path="x.txt")
    assert a.content == ""
    assert a.create_dirs is True


def test_file_edit_requires_old_string():
    with pytest.raises(ValidationError):
        FileEditAction(type="file_edit", path="a.py", old_string="", new_string="x")


def test_apply_patch_min_one_edit():
    with pytest.raises(ValidationError):
        ApplyPatchAction(type="apply_patch", path="a.py", edits=[])


def test_apply_patch_max_64_edits():
    edits = [{"old_string": f"a{i}", "new_string": f"b{i}"} for i in range(65)]
    with pytest.raises(ValidationError):
        ApplyPatchAction(type="apply_patch", path="a.py", edits=edits)


def test_shell_command_required_and_bounded():
    with pytest.raises(ValidationError):
        ShellAction(type="shell", command="")
    with pytest.raises(ValidationError):
        ShellAction(type="shell", command="x" * 4001)


def test_shell_timeout_bounds():
    with pytest.raises(ValidationError):
        ShellAction(type="shell", command="ls", timeout_s=0)
    with pytest.raises(ValidationError):
        ShellAction(type="shell", command="ls", timeout_s=601)


def test_grep_output_mode_literal():
    with pytest.raises(ValidationError):
        GrepAction(type="grep", pattern="x", output_mode="bogus")


def test_find_files_defaults():
    a = FindFilesAction(type="find_files", pattern="*.py")
    assert a.path == "."
    assert a.max_results == 500


def test_list_dir_defaults():
    a = ListDirAction(type="list_dir", path=".")
    assert a.recursive is False
    assert a.max_entries == 200


def test_file_delete_path_required():
    with pytest.raises(ValidationError):
        FileDeleteAction(type="file_delete", path="")


def test_agent_response_with_coding_actions():
    r = AgentResponse.model_validate(
        {
            "actions": [
                {"type": "grep", "pattern": "x"},
                {"type": "file_read", "path": "a.py"},
                {
                    "type": "apply_patch",
                    "path": "a.py",
                    "edits": [{"old_string": "a", "new_string": "b"}],
                },
                {"type": "shell", "command": "echo hi"},
                {"type": "find_files", "pattern": "*.py"},
            ],
            "memory_update": None,
        }
    )
    assert len(r.actions) == 5
    assert r.actions[0].type == "grep"
    assert r.actions[2].type == "apply_patch"


def test_extra_fields_rejected_on_new_actions():
    with pytest.raises(ValidationError):
        FileReadAction(type="file_read", path="x", bogus=1)  # type: ignore[call-arg]
