from __future__ import annotations

from pathlib import Path

import pytest

from openharness.tools.base import ToolExecutionContext
from openharness.tools.deliver_artifact_tool import (
    DeliverArtifactInput,
    DeliverArtifactTool,
)


class FakeProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout_str = stdout


class FakeSandbox:
    is_running = True

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    async def read_file_binary(self, path: str) -> bytes:
        return self.files[path]

    async def exec_command(self, command: str):
        if "test -d '/home/user/reports'" in command:
            return FakeProcess("dir")
        if "find '/home/user/reports' -type f" in command:
            return FakeProcess("/home/user/reports/a.csv\n/home/user/reports/b.csv\n")
        return FakeProcess("")


class FakeHook:
    def __init__(self) -> None:
        self.artifacts: list[tuple[str, str]] = []

    async def on_artifact(self, file_path: str, reason: str, sandbox_session=None, url=None) -> None:
        del sandbox_session, url
        self.artifacts.append((file_path, reason))


@pytest.mark.asyncio
async def test_deliver_single_artifact_to_workspace(tmp_path: Path, monkeypatch):
    sandbox = FakeSandbox({"/home/user/result.md": b"# done\n"})
    hook = FakeHook()
    monkeypatch.setattr(
        "openharness.tools.deliver_artifact_tool.get_sandbox_session",
        lambda: sandbox,
    )

    result = await DeliverArtifactTool().execute(
        DeliverArtifactInput(sandbox_path="/home/user/result.md"),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": hook, "thread_id": "t1"}),
    )

    assert result.is_error is False
    assert (tmp_path / "result.md").read_bytes() == b"# done\n"
    assert hook.artifacts == [(str(tmp_path / "result.md"), "Delivered sandbox artifact: result.md")]


@pytest.mark.asyncio
async def test_deliver_multiple_artifacts_without_zip(tmp_path: Path, monkeypatch):
    sandbox = FakeSandbox({
        "/home/user/a.csv": b"a",
        "/home/user/b.csv": b"b",
    })
    hook = FakeHook()
    monkeypatch.setattr(
        "openharness.tools.deliver_artifact_tool.get_sandbox_session",
        lambda: sandbox,
    )

    result = await DeliverArtifactTool().execute(
        DeliverArtifactInput(paths=["/home/user/a.csv", "/home/user/b.csv"]),
        ToolExecutionContext(cwd=tmp_path, metadata={"hook": hook}),
    )

    assert result.is_error is False
    assert (tmp_path / "a.csv").read_bytes() == b"a"
    assert (tmp_path / "b.csv").read_bytes() == b"b"
    assert len(hook.artifacts) == 2


@pytest.mark.asyncio
async def test_deliver_directory_as_zip(tmp_path: Path, monkeypatch):
    sandbox = FakeSandbox({
        "/home/user/reports/a.csv": b"a",
        "/home/user/reports/b.csv": b"b",
    })
    monkeypatch.setattr(
        "openharness.tools.deliver_artifact_tool.get_sandbox_session",
        lambda: sandbox,
    )

    result = await DeliverArtifactTool().execute(
        DeliverArtifactInput(sandbox_path="/home/user/reports", filename="reports.zip"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is False
    assert (tmp_path / "reports.zip").exists()


@pytest.mark.asyncio
async def test_deliver_rejects_paths_outside_home_user(tmp_path: Path, monkeypatch):
    sandbox = FakeSandbox({})
    monkeypatch.setattr(
        "openharness.tools.deliver_artifact_tool.get_sandbox_session",
        lambda: sandbox,
    )

    result = await DeliverArtifactTool().execute(
        DeliverArtifactInput(sandbox_path="/etc/passwd"),
        ToolExecutionContext(cwd=tmp_path),
    )

    assert result.is_error is True
    assert "outside the sandbox user area" in result.output
