"""Tests for detailed subagent execution step telemetry."""

from __future__ import annotations

from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings
from openharness.coordinator.subagent_runtime import SubagentRuntime, _summarize_tool_input
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.tools import create_default_tool_registry


def test_summarize_tool_input_masks_sensitive_keys():
    raw = {
        "path": "notes.txt",
        "api_key": "sk-secret-12345",
        "auth_token": "tok-abc",
        "password": "hunter2",
    }
    summary = _summarize_tool_input(raw)
    assert "notes.txt" in summary
    assert "sk-secret-12345" not in summary
    assert "tok-abc" not in summary
    assert "hunter2" not in summary


@pytest.mark.asyncio
async def test_subagent_runtime_emits_step_timeline_events(tmp_path: Path):
    (tmp_path / "info.txt").write_text("line1=hello\n", encoding="utf-8")

    class _TwoStepClient:
        def __init__(self) -> None:
            self.calls = 0

        async def stream_message(self, request):
            del request
            self.calls += 1
            if self.calls == 1:
                msg = ConversationMessage(
                    role="assistant",
                    content=[
                        TextBlock(text="Let me read info.txt first."),
                        ToolUseBlock(
                            id="toolu_sub_1",
                            name="read_file",
                            input={"path": "info.txt"},
                        ),
                    ],
                )
                stop = "tool_use"
            else:
                msg = ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="All done: line1=hello")],
                )
                yield ApiTextDeltaEvent(text="All done: line1=hello")
                stop = "end_turn"
            yield ApiMessageCompleteEvent(
                message=msg,
                usage=UsageSnapshot(input_tokens=15, output_tokens=8),
                stop_reason=stop,
            )

    runtime = SubagentRuntime(
        api_client=_TwoStepClient(),
        tool_registry=create_default_tool_registry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        default_model="claude-sonnet-4-5",
    )
    record = await runtime.spawn(
        description="Read info.txt",
        prompt="Inspect info.txt and report line1.",
        name="inspector",
    )
    await runtime.wait_for_agents(agent_ids=[record.agent_id], timeout_seconds=5.0)
    events = runtime.drain_events()
    phases = [e.phase for e in events]

    assert "subagent_started" in phases
    assert "subagent_tool" in phases
    assert "subagent_tool_result" in phases
    assert "subagent_turn" in phases
    assert "subagent_completed" in phases

    started_evt = next(e for e in events if e.phase == "subagent_started")
    assert started_evt.metadata["prompt_preview"] == "Inspect info.txt and report line1."

    tool_start_evt = next(e for e in events if e.phase == "subagent_tool")
    assert "info.txt" in tool_start_evt.metadata["tool_input_preview"]

    tool_res_evt = next(e for e in events if e.phase == "subagent_tool_result")
    assert tool_res_evt.metadata["is_error"] is False
    assert "line1=hello" in tool_res_evt.metadata["output_preview"]
    assert isinstance(tool_res_evt.metadata.get("duration_ms"), int)

    turn_evts = [e for e in events if e.phase == "subagent_turn"]
    assert len(turn_evts) == 2
    assert turn_evts[0].metadata["turn_index"] == 1
    assert "Let me read info.txt first." in turn_evts[0].metadata["text_preview"]

    completed_evt = next(e for e in events if e.phase == "subagent_completed")
    assert "All done: line1=hello" in completed_evt.metadata["output_detail"]
