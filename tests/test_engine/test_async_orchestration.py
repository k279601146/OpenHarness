"""Focused unit tests for async subagents, rolling tool pool, step steering, and DAG task board."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings
from openharness.coordinator.subagent_runtime import SubagentRuntime
from openharness.coordinator.task_board import TaskBoard, TaskBoardError
from openharness.engine.inbox import AgentInbox
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock
from openharness.engine.query import QueryContext, _tool_schemas_for_context
from openharness.engine.query_engine import QueryEngine
from openharness.engine.stream_events import AgentProgressEvent, AssistantTurnComplete
from openharness.permissions.checker import PermissionChecker
from openharness.permissions.modes import PermissionMode
from openharness.tools import create_default_tool_registry
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResult


class _EchoToolInput(BaseModel):
    label: str
    delay: float = 0.02
    fail: bool = False


class _TrackedParallelTool(BaseTool):
    name = "tracked_read"
    description = "Concurrency-safe tracked read tool"
    input_model = _EchoToolInput
    parallel_safe = True

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.events: list[str] = []

    def is_read_only(self, arguments: _EchoToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: _EchoToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.events.append(f"start:{arguments.label}")
        try:
            await asyncio.sleep(arguments.delay)
            self.events.append(f"end:{arguments.label}")
            return ToolResult(output=f"read:{arguments.label}")
        finally:
            self.active -= 1


class _TrackedBarrierTool(BaseTool):
    name = "tracked_barrier"
    description = "Exclusive barrier tool"
    input_model = _EchoToolInput
    parallel_safe = False
    execution_group = "barrier_test"

    def __init__(self, reader: _TrackedParallelTool) -> None:
        self._reader = reader
        self.overlap_detected = False

    async def execute(self, arguments: _EchoToolInput, context: ToolExecutionContext) -> ToolResult:
        del context
        if self._reader.active > 0:
            self.overlap_detected = True
        self._reader.events.append(f"barrier_start:{arguments.label}")
        await asyncio.sleep(arguments.delay)
        self._reader.events.append(f"barrier_end:{arguments.label}")
        return ToolResult(output=f"barrier:{arguments.label}")


class _MockStreamingClient:
    """Deterministic scripted API client keyed by system/user messages."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.requests: list[ApiMessageRequest] = []

    async def stream_message(self, request: ApiMessageRequest):
        self.requests.append(request)
        msg = await self._handler(request)
        yield ApiMessageCompleteEvent(
            message=msg,
            usage=UsageSnapshot(input_tokens=10, output_tokens=5),
            stop_reason="end_turn",
        )


@pytest.mark.asyncio
async def test_inbox_steer_and_wait_wakeup():
    inbox = AgentInbox()
    seen = inbox.next_step_ids()

    async def _delayed_push():
        await asyncio.sleep(0.03)
        await inbox.steer("focus on tests first", source="user")

    task = asyncio.create_task(_delayed_push())
    woken = await inbox.wait_for_next_step(seen_ids=seen, timeout_seconds=1.0)
    await task

    assert woken is True
    claimed = inbox.claim_next_step()
    assert len(claimed) == 1
    assert claimed[0].content == "focus on tests first"
    assert inbox.claim_next_step() == []


@pytest.mark.asyncio
async def test_rolling_parallel_pool_and_exclusive_barrier_ordering(tmp_path: Path):
    reader = _TrackedParallelTool()
    barrier = _TrackedBarrierTool(reader)
    registry = ToolRegistry()
    registry.register(reader)
    registry.register(barrier)

    step = 0

    async def _handler(_request: ApiMessageRequest) -> ConversationMessage:
        nonlocal step
        step += 1
        if step == 1:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(id="t1", name="tracked_read", input={"label": "a", "delay": 0.04}),
                    ToolUseBlock(id="t2", name="tracked_read", input={"label": "b", "delay": 0.04}),
                    ToolUseBlock(id="t3", name="tracked_read", input={"label": "c", "delay": 0.04}),
                    ToolUseBlock(id="t4", name="tracked_barrier", input={"label": "w", "delay": 0.02}),
                    ToolUseBlock(id="t5", name="tracked_read", input={"label": "d", "delay": 0.02}),
                ],
            )
        return ConversationMessage(role="assistant", content=[TextBlock(text="all done")])

    engine = QueryEngine(
        api_client=_MockStreamingClient(_handler),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="sys",
        max_parallel_tool_calls=2,
    )

    events = [event async for event in engine.submit_message("run mixed batch")]

    assert reader.max_active == 2
    assert barrier.overlap_detected is False
    # Barrier must run strictly after initial reads (a,b,c) and before trailing read (d).
    b_start = reader.events.index("barrier_start:w")
    assert b_start > reader.events.index("end:c")
    assert reader.events.index("start:d") > reader.events.index("barrier_end:w")

    dispatch_events = [
        e for e in events if isinstance(e, AgentProgressEvent) and e.phase == "tool_dispatch"
    ]
    assert len(dispatch_events) == 1
    assert dispatch_events[0].metadata["execution_group"] == "barrier_test"

    # Model-order tool results must match tool call order t1..t5.
    tool_result_msgs = [
        m for m in engine.messages if m.role == "user" and any(b.type == "tool_result" for b in m.content)
    ]
    assert [b.tool_use_id for b in tool_result_msgs[-1].content if b.type == "tool_result"] == [
        "t1",
        "t2",
        "t3",
        "t4",
        "t5",
    ]


@pytest.mark.asyncio
async def test_mid_turn_steer_poller_and_engine_steer_inject_at_step_boundary(tmp_path: Path):
    reader = _TrackedParallelTool()
    registry = ToolRegistry()
    registry.register(reader)

    polled_once = False

    async def _poller() -> list[str]:
        nonlocal polled_once
        if not polled_once:
            polled_once = True
            return ["also inspect logs"]
        return []

    seen_prompts: list[str] = []
    step = 0

    async def _handler(request: ApiMessageRequest) -> ConversationMessage:
        nonlocal step
        step += 1
        seen_prompts.append("\n".join(m.text for m in request.messages))
        if step == 1:
            await engine.steer("prioritize security checks")
            return ConversationMessage(
                role="assistant",
                content=[ToolUseBlock(id="t1", name="tracked_read", input={"label": "step1", "delay": 0.01})],
            )
        return ConversationMessage(role="assistant", content=[TextBlock(text="steered done")])

    engine = QueryEngine(
        api_client=_MockStreamingClient(_handler),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="sys",
        steer_poller=_poller,
    )

    events = [event async for event in engine.submit_message("start")]
    assert "also inspect logs" in seen_prompts[0]
    assert "prioritize security checks" in seen_prompts[1]
    steer_events = [
        e for e in events if isinstance(e, AgentProgressEvent) and e.phase == "steer_applied"
    ]
    assert len(steer_events) == 2


@pytest.mark.asyncio
async def test_task_board_dag_cas_and_scope_overlap():
    board = TaskBoard()
    created = await board.batch_create(
        [
            {"ref": "api", "subject": "Update API", "write_scopes": ["apps/api/"]},
            {"ref": "web", "subject": "Update Web", "blocked_by": ["api"], "write_scopes": ["apps/api/tests/"]},
        ]
    )
    assert len(created) == 2
    t_api_id = created[0]["id"]
    t_web_id = created[1]["id"]
    # Overlapping write scope warning recorded on creation.
    assert created[1]["write_scope_warnings"]

    # Blocked task cannot be claimed yet.
    with pytest.raises(TaskBoardError):
        await board.claim_task(task_id=t_web_id, owner="worker-web")

    # Cycle detection rejects circular blocked_by.
    with pytest.raises(TaskBoardError):
        await board.update_task(task_id=t_api_id, blocked_by=[t_web_id])

    claimed = await board.claim_task(task_id=t_api_id, owner="worker-api")
    assert claimed["status"] == "in_progress"
    assert claimed["revision"] == 2

    # CAS mismatch raises TaskBoardError.
    with pytest.raises(TaskBoardError):
        await board.update_task(task_id=t_api_id, status="completed", expected_revision=1)

    await board.update_task(
        task_id=t_api_id,
        status="completed",
        result_summary="API done",
        expected_revision=2,
    )
    # Completing t_api unblocks t_web cleanly.
    ready = await board.claim_task(task_id=t_web_id, owner="worker-web")
    assert ready["status"] == "in_progress"


@pytest.mark.asyncio
async def test_subagent_runtime_spawn_steer_cold_resume_wait_interrupt_and_depth(tmp_path: Path):
    registry = create_default_tool_registry()

    # Empty metadata preserves heavy-tool pruning regression check.
    empty_ctx = QueryContext(
        api_client=_MockStreamingClient(lambda _: asyncio.sleep(0)),
        tool_registry=registry,
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-test",
        system_prompt="sys",
        max_tokens=1024,
        tool_metadata={},
    )
    assert "agent" not in {s["name"] for s in _tool_schemas_for_context(empty_ctx)}

    # Enabled metadata exposes async coordination suite.
    enabled_ctx = QueryContext(
        api_client=empty_ctx.api_client,
        tool_registry=registry,
        permission_checker=empty_ctx.permission_checker,
        cwd=tmp_path,
        model="claude-test",
        system_prompt="sys",
        max_tokens=1024,
        tool_metadata={"enable_subagents": True, "subagent_depth": 0, "subagent_max_depth": 2},
    )
    enabled_names = {s["name"] for s in _tool_schemas_for_context(enabled_ctx)}
    assert {"agent", "wait_agent", "send_message", "list_agents", "interrupt_agent", "task_board"}.issubset(
        enabled_names
    )

    # At max_depth, "agent" schema is hidden so workers cannot infinitely recurse.
    max_depth_ctx = QueryContext(
        api_client=empty_ctx.api_client,
        tool_registry=registry,
        permission_checker=empty_ctx.permission_checker,
        cwd=tmp_path,
        model="claude-test",
        system_prompt="sys",
        max_tokens=1024,
        tool_metadata={"enable_subagents": True, "subagent_depth": 2, "subagent_max_depth": 2},
    )
    assert "agent" not in {s["name"] for s in _tool_schemas_for_context(max_depth_ctx)}

    lead_steps = 0

    async def _scripted_model(request: ApiMessageRequest) -> ConversationMessage:
        nonlocal lead_steps
        sys_txt = request.system_prompt if isinstance(request.system_prompt, str) else ""
        joined_user = "\n".join(m.text for m in request.messages)

        # Child agent behavior
        if "You are subagent `slow-worker`" in sys_txt:
            await asyncio.sleep(0.5)
            return ConversationMessage(role="assistant", content=[TextBlock(text="slow finished")])

        if "You are subagent `worker-a`" in sys_txt:
            if "[Message from lead]" in joined_user:
                await asyncio.sleep(0.15)
                return ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="worker-a cold-resumed result")],
                )
            return ConversationMessage(role="assistant", content=[TextBlock(text="worker-a initial result")])

        # Lead behavior: spawn worker-a and slow-worker, interrupt slow-worker, wait for worker-a, then cold-resume worker-a
        lead_steps += 1
        if lead_steps == 1:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(
                        id="spawn_a",
                        name="agent",
                        input={"name": "worker-a", "description": "Task A", "prompt": "do A"},
                    ),
                    ToolUseBlock(
                        id="spawn_slow",
                        name="agent",
                        input={"name": "slow-worker", "description": "Slow", "prompt": "hang"},
                    ),
                ],
            )
        if lead_steps == 2:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(id="int_slow", name="interrupt_agent", input={"agent_id": "slow-worker"}),
                    ToolUseBlock(id="list_now", name="list_agents", input={"only_direct_children": True}),
                    ToolUseBlock(id="wait_a", name="wait_agent", input={"agent_ids": ["worker-a"], "timeout_seconds": 5.0}),
                ],
            )
        if lead_steps == 3:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(
                        id="resume_a",
                        name="send_message",
                        input={"task_id": "worker-a", "message": "now finish part 2"},
                    )
                ],
            )
        # On lead_steps == 4, return empty tool_uses while resumed worker-a runs -> auto_drain waits!
        if lead_steps == 4:
            return ConversationMessage(role="assistant", content=[TextBlock(text="waiting...")])
        # lead_steps == 5 fires after auto-drain delivers worker-a's cold-resumed <task-notification>!
        return ConversationMessage(
            role="assistant",
            content=[TextBlock(text=f"synthesized: {'worker-a cold-resumed result' in joined_user}")],
        )

    client = _MockStreamingClient(_scripted_model)
    root_inbox = AgentInbox()
    task_board = TaskBoard()
    perm_checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
    runtime = SubagentRuntime(
        api_client=client,
        tool_registry=registry,
        permission_checker=perm_checker,
        cwd=tmp_path,
        default_model="claude-test",
        max_depth=2,
        root_inbox=root_inbox,
        task_board=task_board,
        base_tool_metadata={"enable_subagents": True},
    )

    engine = QueryEngine(
        api_client=client,
        tool_registry=registry,
        permission_checker=perm_checker,
        cwd=tmp_path,
        model="claude-test",
        system_prompt="Lead coordinator",
        tool_metadata={
            "enable_subagents": True,
            "subagent_runtime": runtime,
            "task_board": task_board,
            "subagent_depth": 0,
            "subagent_max_depth": 2,
            "subagent_inbox": root_inbox,
        },
        inbox=root_inbox,
    )

    events = [event async for event in engine.submit_message("orchestrate")]
    await runtime.shutdown_all()

    turns = [e for e in events if isinstance(e, AssistantTurnComplete)]
    assert turns[-1].message.text == "synthesized: True"

    agents_by_id = {item["agent_id"]: item for item in runtime.list_agents()}
    assert agents_by_id["worker-a"]["status"] == "completed"
    assert agents_by_id["slow-worker"]["status"] in {"interrupted", "completed"}
    assert runtime.total_usage()["agent_count"] == 2
    assert runtime.total_usage()["input_tokens"] > 0

    with pytest.raises(ValueError):
        await runtime.spawn(description="too deep", prompt="nope", parent_depth=2)


def test_delegation_prompt_teaches_current_async_tools() -> None:
    from openharness.prompts.context import _build_delegation_section

    section = _build_delegation_section()
    assert "inherit_context=False" in section
    assert "inherit_context=True" in section
    assert "task_board" in section
    assert "wait_agent" in section
    assert "interrupt_agent" in section
    assert "/agents" not in section
    assert "task_output" not in section


@pytest.mark.asyncio
async def test_agent_inherit_context_forks_completed_history_without_dangling_tool_use(
    tmp_path: Path,
) -> None:
    registry = create_default_tool_registry()
    captured_child_requests: dict[str, list[ConversationMessage]] = {}
    lead_step = 0

    async def _scripted_model(request: ApiMessageRequest) -> ConversationMessage:
        nonlocal lead_step
        sys_txt = request.system_prompt if isinstance(request.system_prompt, str) else ""

        if "You are subagent `forked`" in sys_txt:
            captured_child_requests["forked"] = [m.model_copy(deep=True) for m in request.messages]
            joined = "\n".join(m.text for m in request.messages)
            return ConversationMessage(
                role="assistant",
                content=[TextBlock(text=f"fork-sees-secret:{'ALPHA-42' in joined}")],
            )

        if "You are subagent `isolated`" in sys_txt:
            captured_child_requests["isolated"] = [m.model_copy(deep=True) for m in request.messages]
            joined = "\n".join(m.text for m in request.messages)
            return ConversationMessage(
                role="assistant",
                content=[TextBlock(text=f"isolated-sees-secret:{'ALPHA-42' in joined}")],
            )

        lead_step += 1
        if lead_step == 1:
            return ConversationMessage(role="assistant", content=[TextBlock(text="Noted ALPHA-42.")])
        if lead_step == 2:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(
                        id="call_fork",
                        name="agent",
                        input={
                            "name": "forked",
                            "description": "Fork review",
                            "prompt": "Recall any secret codeword from earlier turns.",
                            "inherit_context": True,
                        },
                    ),
                    ToolUseBlock(
                        id="call_iso",
                        name="agent",
                        input={
                            "name": "isolated",
                            "description": "Isolated check",
                            "prompt": "Recall any secret codeword from earlier turns.",
                            "inherit_context": False,
                        },
                    ),
                ],
            )
        if lead_step == 3:
            return ConversationMessage(
                role="assistant",
                content=[
                    ToolUseBlock(
                        id="call_wait",
                        name="wait_agent",
                        input={"agent_ids": ["forked", "isolated"], "timeout_seconds": 5.0},
                    )
                ],
            )
        joined = "\n".join(m.text for m in request.messages)
        return ConversationMessage(
            role="assistant",
            content=[
                TextBlock(
                    text=(
                        f"done fork={('fork-sees-secret:True' in joined)} "
                        f"iso={('isolated-sees-secret:False' in joined)}"
                    )
                )
            ],
        )

    client = _MockStreamingClient(_scripted_model)
    root_inbox = AgentInbox()
    task_board = TaskBoard()
    perm_checker = PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
    runtime = SubagentRuntime(
        api_client=client,
        tool_registry=registry,
        permission_checker=perm_checker,
        cwd=tmp_path,
        default_model="claude-test",
        max_depth=2,
        root_inbox=root_inbox,
        task_board=task_board,
        base_tool_metadata={"enable_subagents": True},
    )

    engine = QueryEngine(
        api_client=client,
        tool_registry=registry,
        permission_checker=perm_checker,
        cwd=tmp_path,
        model="claude-test",
        system_prompt="Lead coordinator",
        tool_metadata={
            "enable_subagents": True,
            "subagent_runtime": runtime,
            "task_board": task_board,
            "subagent_depth": 0,
            "subagent_max_depth": 2,
            "subagent_inbox": root_inbox,
        },
        inbox=root_inbox,
    )

    [event async for event in engine.submit_message("Remember secret ALPHA-42.")]
    parent_count_after_turn1 = len(engine.messages)
    events_turn2 = [event async for event in engine.submit_message("Delegate fork and isolated check.")]
    await runtime.shutdown_all()

    turns2 = [e for e in events_turn2 if isinstance(e, AssistantTurnComplete)]
    assert turns2[-1].message.text == "done fork=True iso=True"

    forked_msgs = captured_child_requests["forked"]
    # Must contain completed turn 1 + turn 2 user message merged cleanly with strict role alternation.
    assert [m.role for m in forked_msgs] == ["user", "assistant", "user"]
    # In-flight ToolUseBlock ("call_fork" / "call_iso") must NEVER leak into forked child history.
    assert all(not m.tool_uses for m in forked_msgs)
    assert "ALPHA-42" in forked_msgs[0].text
    assert "[Forked Subtask Assignment]" in forked_msgs[-1].text

    isolated_msgs = captured_child_requests["isolated"]
    assert [m.role for m in isolated_msgs] == ["user"]
    assert "ALPHA-42" not in isolated_msgs[0].text

    # Parent completed turns after turn 1 must remain intact and unaffected by child execution.
    assert len(engine.messages) > parent_count_after_turn1
    assert engine.messages[0].text == "Remember secret ALPHA-42."
    assert engine.messages[1].text == "Noted ALPHA-42."
    assert "parent_completed_messages" not in engine._tool_metadata  # type: ignore[attr-defined]
