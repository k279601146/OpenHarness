"""Tests for Optimization 2: Programmatic Tool Calling (run_code)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings
from openharness.engine.messages import ConversationMessage, TextBlock, ToolResultBlock, ToolUseBlock
from openharness.engine.query import CORE_TOOL_SCHEMA_NAMES, QueryContext, _execute_tool_call, run_query
from openharness.engine.stream_events import AssistantTurnComplete
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.tools import create_default_tool_registry
from openharness.tools.base import CancellationToken, ToolExecutionContext
from openharness.tools.run_code_tool import RunCodeInput, RunCodeTool


def test_run_code_registered_in_default_registry_and_core_schemas():
    registry = create_default_tool_registry()
    assert registry.get("run_code") is not None
    assert "run_code" in CORE_TOOL_SCHEMA_NAMES


@pytest.mark.asyncio
async def test_run_code_batches_tools_concurrently_via_query_pipeline(tmp_path: Path):
    (tmp_path / "alpha.txt").write_text("alpha=10\nstatus=ok\n", encoding="utf-8")
    (tmp_path / "beta.txt").write_text("beta=25\nstatus=ok\n", encoding="utf-8")

    registry = create_default_tool_registry()
    context = QueryContext(
        api_client=object(),  # not used by direct _execute_tool_call
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=1024,
    )

    script = """
import json, re

files_res = await tools.glob(pattern="*.txt", path=".")
paths = [line.strip() for line in files_res.lines() if line.strip()]
reads = await gather(*(tools.read_file(path=p) for p in sorted(paths)))
totals = {}
for p, r in zip(sorted(paths), reads):
    m = re.search(r"=(\\d+)", r.output)
    totals[p] = int(m.group(1)) if m else 0
print(json.dumps({"count": len(totals), "sum": sum(totals.values())}, sort_keys=True))
"""
    result = await _execute_tool_call(
        context,
        "run_code",
        "toolu_ptc_1",
        {"code": script},
    )
    assert not result.is_error
    payload = json.loads(result.content.split("\n\n[run_code completed")[0])
    assert payload == {"count": 2, "sum": 35}
    assert result.result_metadata["tool_calls_count"] == 3
    assert result.result_metadata["error_count"] == 0


@pytest.mark.asyncio
async def test_run_code_respects_permission_mode_and_plan_blocks(tmp_path: Path):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    registry = create_default_tool_registry()
    context = QueryContext(
        api_client=object(),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.PLAN)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=1024,
    )

    script = """
r = await tools.read_file(path="note.txt")
w = await tools.write_file(path="hacked.txt", content="nope")
return {"read_err": r.is_error, "write_err": w.is_error, "write_msg": w.output}
"""
    result = await _execute_tool_call(context, "run_code", "toolu_ptc_plan", {"code": script})
    assert not result.is_error
    body = json.loads(result.content.split("\n\n[run_code completed")[0])
    assert body["read_err"] is False
    assert body["write_err"] is True
    assert "plan mode" in body["write_msg"].lower()
    assert not (tmp_path / "hacked.txt").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_code,expected_substr",
    [
        ("import os\nprint(os.environ)", "not permitted"),
        ("x = ().__class__.__bases__", "denied"),
        ("await tools.run_code(code='print(1)')", "recursively"),
        ("while True:\n    pass", "step limit"),
    ],
)
async def test_run_code_blocks_unsafe_constructs_and_runaway_loops(
    tmp_path: Path,
    bad_code: str,
    expected_substr: str,
):
    registry = create_default_tool_registry()
    context = QueryContext(
        api_client=object(),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=1024,
    )
    result = await _execute_tool_call(context, "run_code", "toolu_ptc_bad", {"code": bad_code})
    assert result.is_error
    assert expected_substr in result.content.lower()


@pytest.mark.asyncio
async def test_run_code_enforces_max_tool_calls_and_cancellation(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    registry = create_default_tool_registry()
    context = QueryContext(
        api_client=object(),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=1024,
    )
    script = """
for i in range(5):
    await tools.read_file(path="a.txt")
"""
    result = await _execute_tool_call(
        context,
        "run_code",
        "toolu_ptc_cap",
        {"code": script, "max_tool_calls": 2},
    )
    assert result.is_error
    assert "max_tool_calls" in result.content

    token = CancellationToken()
    token.cancel("user_stop")
    tool = RunCodeTool()
    with pytest.raises(asyncio.CancelledError):
        await tool.execute(
            RunCodeInput(code="x = 1 + 1"),
            ToolExecutionContext(
                cwd=tmp_path,
                metadata={"ptc_tool_runner": lambda *a: None},
                cancellation_token=token,
            ),
        )


@dataclass
class _FakeResponse:
    message: ConversationMessage
    usage: UsageSnapshot


@pytest.mark.asyncio
async def test_run_query_executes_ptc_and_keeps_nested_results_out_of_messages(tmp_path: Path):
    (tmp_path / "secret_noise.txt").write_text("VERBOSE_INTERMEDIATE_NOISE_999\ntarget=42\n", encoding="utf-8")

    class _PtcModelClient:
        def __init__(self) -> None:
            self.turn = 0
            self.seen_messages: list[ConversationMessage] = []

        async def stream_message(self, request):
            self.turn += 1
            self.seen_messages = list(request.messages)
            if self.turn == 1:
                msg = ConversationMessage(
                    role="assistant",
                    content=[
                        ToolUseBlock(
                            id="toolu_ptc_turn",
                            name="run_code",
                            input={
                                "code": (
                                    "res = await tools.read_file(path='secret_noise.txt')\n"
                                    "for line in res.lines():\n"
                                    "    if 'target=' in line:\n"
                                    "        print(line.strip())\n"
                                )
                            },
                        )
                    ],
                )
            else:
                msg = ConversationMessage(role="assistant", content=[TextBlock(text="target is 42")])
                yield ApiTextDeltaEvent(text="target is 42")
            yield ApiMessageCompleteEvent(
                message=msg,
                usage=UsageSnapshot(input_tokens=20, output_tokens=10),
                stop_reason="tool_use" if self.turn == 1 else "end_turn",
            )

    client = _PtcModelClient()
    context = QueryContext(
        api_client=client,
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=1024,
    )
    messages = [ConversationMessage.from_user_text("extract target")]
    events = [evt async for evt, _ in run_query(context, messages)]
    assert any(isinstance(e, AssistantTurnComplete) for e in events)
    serialized = "\n".join(
        block.content
        for m in client.seen_messages
        for block in m.content
        if isinstance(block, ToolResultBlock)
    )
    assert "target=42" in serialized
    assert "VERBOSE_INTERMEDIATE_NOISE_999" not in serialized
