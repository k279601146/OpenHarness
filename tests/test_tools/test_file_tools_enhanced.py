"""Unit tests for enhanced file read/write/edit/patch/search tools and repeat-tool guard."""

from __future__ import annotations

import posixpath
from pathlib import Path

import pytest

from openharness.engine.query import (
    CORE_TOOL_SCHEMA_NAMES,
    _WORKSPACE_WRITE_TOOL_NAMES,
    RepeatToolTracker,
)
from openharness.tools import create_default_tool_registry
from openharness.tools.apply_patch_tool import ApplyPatchTool, ApplyPatchToolInput
from openharness.tools.base import ToolExecutionContext
from openharness.tools.file_edit_tool import FileEditTool, FileEditToolInput
from openharness.tools.file_read_tool import FileReadTool, FileReadToolInput
from openharness.tools.file_write_tool import FileWriteTool, FileWriteToolInput
from openharness.tools.glob_tool import GlobTool, GlobToolInput
from openharness.tools.grep_tool import GrepTool, GrepToolInput


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""


class _FakePatchSandboxSession:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})

    async def read_file_binary(self, path: str) -> bytes:
        return self.files[path]

    async def write_file(self, path: str, content: str | bytes) -> None:
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else bytes(content)

    async def exec_command(self, command: str, **kwargs) -> _FakeProcess:
        import shlex

        if "test -d" in command and "test -f" in command:
            target = next(
                (tok.rstrip(";") for tok in shlex.split(command) if tok.startswith("/")),
                "/home/user",
            )
            if target in self.files:
                return _FakeProcess(b"file")
            if any(p.startswith(target.rstrip("/") + "/") for p in self.files):
                return _FakeProcess(b"dir")
            return _FakeProcess(b"missing")
        if "mv -f" in command:
            parts = shlex.split(command)
            mv_idx = parts.index("mv")
            src = parts[mv_idx + 2]
            dst = parts[mv_idx + 3]
            self.files[dst] = self.files.pop(src)
            return _FakeProcess()
        if command.startswith("rm -f "):
            parts = shlex.split(command)
            self.files.pop(parts[-1], None)
            return _FakeProcess()
        return _FakeProcess()


@pytest.mark.asyncio
async def test_read_file_line_and_byte_bounds_and_streaming(tmp_path: Path, monkeypatch) -> None:
    small = tmp_path / "small.txt"
    small.write_text("alpha\nbeta\n", encoding="utf-8")
    ctx = ToolExecutionContext(cwd=tmp_path)

    res = await FileReadTool().execute(FileReadToolInput(path="small.txt"), ctx)
    assert not res.is_error
    assert res.output.endswith("beta")
    assert "[Showing lines" not in res.output
    assert res.metadata["truncated"] is False

    # Out-of-range offset includes total_lines diagnostic
    oob = await FileReadTool().execute(FileReadToolInput(path="small.txt", offset=99), ctx)
    assert not oob.is_error
    assert "total_lines=2" in oob.output

    # Single overly long line is truncated cleanly
    long_line = tmp_path / "long.txt"
    long_line.write_text(("x" * 2500) + "\n", encoding="utf-8")
    long_res = await FileReadTool().execute(FileReadToolInput(path="long.txt"), ctx)
    assert "line truncated at 2000 chars" in long_res.output
    assert long_res.metadata["truncated"] is True

    # Byte-bounded slice (> 50 KB) triggers continuation footer with 0-based next offset
    wide = tmp_path / "wide.txt"
    wide.write_text("\n".join(f"line-{i:04d}-" + ("a" * 180) for i in range(400)), encoding="utf-8")
    wide_res = await FileReadTool().execute(
        FileReadToolInput(path="wide.txt", offset=0, limit=400),
        ctx,
    )
    assert wide_res.metadata["truncated_by_bytes"] is True
    next_off = wide_res.metadata["lines_returned"]
    assert f"Use offset={next_off} to continue reading." in wide_res.output

    # Streaming mode via lowered READ_STREAM_MIN_SIZE threshold
    import openharness.tools.file_state as file_state

    monkeypatch.setattr(file_state, "READ_STREAM_MIN_SIZE", 64)
    streamed = tmp_path / "streamed.txt"
    streamed.write_text("\r\n".join(f"row-{i}" for i in range(30)) + "\r\n", encoding="utf-8")
    stream_res = await FileReadTool().execute(
        FileReadToolInput(path="streamed.txt", offset=10, limit=5),
        ctx,
    )
    assert not stream_res.is_error
    assert stream_res.metadata["total_lines"] == 30
    assert "11\trow-10" in stream_res.output
    assert "Use offset=15 to continue reading." in stream_res.output


@pytest.mark.asyncio
async def test_edit_file_crlf_preservation_noop_and_observation_guards(tmp_path: Path) -> None:
    target = tmp_path / "win.py"
    target.write_bytes(b"def greet():\r\n    return 'hi'\r\n")
    ctx = ToolExecutionContext(cwd=tmp_path, metadata={"enforce_file_observation": True})

    # Unobserved edit rejected when enforce_file_observation is True
    unobserved = await FileEditTool().execute(
        FileEditToolInput(path="win.py", old_str="return 'hi'", new_str="return 'hello'"),
        ctx,
    )
    assert unobserved.is_error
    assert "FS_NOT_OBSERVED" in unobserved.output

    # Observe via read_file
    read_res = await FileReadTool().execute(FileReadToolInput(path="win.py"), ctx)
    assert not read_res.is_error

    # Identical old/new rejected
    noop = await FileEditTool().execute(
        FileEditToolInput(path="win.py", old_str="return 'hi'", new_str="return 'hi'"),
        ctx,
    )
    assert noop.is_error
    assert "identical" in noop.output

    # Edit succeeds with LF inputs while preserving CRLF on disk
    edited = await FileEditTool().execute(
        FileEditToolInput(
            path="win.py",
            old_str="def greet():\n    return 'hi'",
            new_str="def greet():\n    return 'hello'",
        ),
        ctx,
    )
    assert not edited.is_error
    assert target.read_bytes() == b"def greet():\r\n    return 'hello'\r\n"

    # External disk change invalidates prior observation -> FS_STALE_VERSION
    target.write_bytes(b"def greet():\r\n    return 'external'\r\n")
    stale = await FileEditTool().execute(
        FileEditToolInput(path="win.py", old_str="return 'external'", new_str="return 'new'"),
        ctx,
    )
    assert stale.is_error
    assert "FS_STALE_VERSION" in stale.output


@pytest.mark.asyncio
async def test_write_file_security_and_observation_guards(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "existing.txt").write_text("old", encoding="utf-8")
    ctx = ToolExecutionContext(cwd=tmp_path, metadata={"enforce_file_observation": True})

    # Blocks escape outside workspace and sensitive paths
    escape = await FileWriteTool().execute(
        FileWriteToolInput(path="../outside.txt", content="nope"),
        ctx,
    )
    assert escape.is_error
    assert "outside workspace" in escape.output

    env_block = await FileWriteTool().execute(
        FileWriteToolInput(path=".env.production", content="SECRET=1"),
        ctx,
    )
    assert env_block.is_error
    assert "sensitive" in env_block.output.lower()

    dir_block = await FileWriteTool().execute(
        FileWriteToolInput(path="subdir", content="nope"),
        ctx,
    )
    assert dir_block.is_error
    assert "directory" in dir_block.output.lower()

    # Creating a brand-new file succeeds without prior read
    created = await FileWriteTool().execute(
        FileWriteToolInput(path="brand_new.py", content="print('ok')\n"),
        ctx,
    )
    assert not created.is_error
    assert created.metadata["operation"] == "create"

    # Overwriting an unobserved existing file is blocked under enforce_file_observation
    overwrite_blocked = await FileWriteTool().execute(
        FileWriteToolInput(path="existing.txt", content="new"),
        ctx,
    )
    assert overwrite_blocked.is_error
    assert "FS_NOT_OBSERVED" in overwrite_blocked.output

    # Read then overwrite works
    await FileReadTool().execute(FileReadToolInput(path="existing.txt"), ctx)
    overwritten = await FileWriteTool().execute(
        FileWriteToolInput(path="existing.txt", content="new"),
        ctx,
    )
    assert not overwritten.is_error
    assert overwritten.metadata["operation"] == "update"


@pytest.mark.asyncio
async def test_apply_patch_preflight_fuzzy_crlf_move_delete_and_registration(tmp_path: Path) -> None:
    registry = create_default_tool_registry()
    assert registry.get("apply_patch") is not None
    assert "apply_patch" in CORE_TOOL_SCHEMA_NAMES
    assert "apply_patch" in _WORKSPACE_WRITE_TOOL_NAMES

    src_file = tmp_path / "mod.py"
    # Includes trailing whitespace & CRLF to exercise 4-pass seek_sequence + EOL preservation
    src_file.write_bytes(b"def alpha():   \r\n    return 'v1'\r\n\r\ndef keep():\r\n    return 1\r\n")
    gone_file = tmp_path / "obsolete.txt"
    gone_file.write_text("bye\n", encoding="utf-8")

    ctx = ToolExecutionContext(cwd=tmp_path)
    patch_text = """*** Begin Patch
*** Add File: created.txt
+hello world
+second line
*** Update File: mod.py
*** Move to: renamed_mod.py
@@ def alpha():
-    return 'v1'
+    return 'v2'
*** Delete File: obsolete.txt
*** End Patch"""

    res = await ApplyPatchTool().execute(ApplyPatchToolInput(patch=patch_text), ctx)
    assert not res.is_error, res.output
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "hello world\nsecond line\n"
    assert not src_file.exists()
    assert not gone_file.exists()
    assert (tmp_path / "renamed_mod.py").read_bytes() == (
        b"def alpha():   \r\n    return 'v2'\r\n\r\ndef keep():\r\n    return 1\r\n"
    )

    # Preflight rollback guarantee: if second hunk fails, first hunk must not write
    atomic_probe = tmp_path / "should_not_exist.txt"
    failing_patch = """*** Begin Patch
*** Add File: should_not_exist.txt
+never written
*** Update File: missing_target.py
@@
-foo
+bar
*** End Patch"""
    fail_res = await ApplyPatchTool().execute(ApplyPatchToolInput(patch=failing_patch), ctx)
    assert fail_res.is_error
    assert not atomic_probe.exists()


@pytest.mark.asyncio
async def test_apply_patch_e2b_routing(tmp_path: Path, monkeypatch) -> None:
    import openharness.tools.apply_patch_tool as apply_patch_mod

    session = _FakePatchSandboxSession({
        "/home/user/project/app.py": b"x = 1\n",
        "/home/user/project/old.txt": b"remove me\n",
    })

    async def _fake_get_session(_ctx):
        return session

    monkeypatch.setattr(apply_patch_mod, "get_e2b_task_session", _fake_get_session)
    ctx = ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "workspace_backend": "e2b",
            "sandbox_workspace": "/home/user",
        },
    )
    patch = """*** Begin Patch
*** Add File: project/new.py
+y = 2
*** Update File: project/app.py
@@
-x = 1
+x = 42
*** Delete File: project/old.txt
*** End Patch"""
    res = await ApplyPatchTool().execute(ApplyPatchToolInput(patch=patch), ctx)
    assert not res.is_error, res.output
    assert res.metadata["workspace"] == "e2b"
    assert session.files["/home/user/project/new.py"] == b"y = 2\n"
    assert session.files["/home/user/project/app.py"] == b"x = 42\n"
    assert posixpath.join("/home/user/project", "old.txt") not in session.files


@pytest.mark.asyncio
async def test_glob_and_grep_vcs_exclusion_sampling_and_line_cap(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.py").write_text("needle = 'git'\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "dep.py").write_text("needle = 'nm'\n", encoding="utf-8")

    # Many files in dir_a, one file in dir_b
    (tmp_path / "dir_a").mkdir()
    for i in range(6):
        (tmp_path / "dir_a" / f"a{i}.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_b" / "b0.py").write_text("needle = " + ("z" * 2400) + "\n", encoding="utf-8")

    ctx = ToolExecutionContext(cwd=tmp_path)

    # Force python fallback cleanly for deterministic check of VCS skipping + sampling
    monkeypatch.setattr("shutil.which", lambda _name: None)

    glob_res = await GlobTool().execute(GlobToolInput(pattern="**/*.py", limit=4), ctx)
    assert not glob_res.is_error
    assert ".git" not in glob_res.output
    assert "node_modules" not in glob_res.output
    # Fair top-level sampling should include dir_b/b0.py rather than starving behind 6 dir_a files
    assert "b0.py" in glob_res.output
    assert glob_res.metadata["truncated"] is True
    assert "Results truncated" in glob_res.output

    grep_res = await GrepTool().execute(GrepToolInput(pattern="needle", file_glob="**/*.py"), ctx)
    assert not grep_res.is_error
    assert ".git" not in grep_res.output
    assert "node_modules" not in grep_res.output
    assert "b0.py" in grep_res.output
    assert "... [truncated]" in grep_res.output


def test_repeat_tool_tracker_thresholds_and_key_order() -> None:
    tracker = RepeatToolTracker()
    assert tracker.record_call("read_file", {"path": "a.py", "offset": 0}) is None
    # Different key order produces same canonical signature
    assert tracker.record_call("read_file", {"offset": 0, "path": "a.py"}) is None
    third = tracker.record_call("read_file", {"path": "a.py", "offset": 0})
    assert third is not None and "Repeat Tool Notice" in third
    assert tracker.record_call("read_file", {"path": "a.py", "offset": 0}) is None
    fifth = tracker.record_call("read_file", {"path": "a.py", "offset": 0})
    assert fifth is not None and "Repeat Tool Warning" in fifth and "args=" in fifth

    # Changing args resets streak cleanly
    assert tracker.record_call("read_file", {"path": "b.py", "offset": 0}) is None
    assert tracker.streak == 1
