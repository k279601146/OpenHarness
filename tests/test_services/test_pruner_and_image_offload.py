"""Tests for Optimization 3: token-budgeted spill, 0-token pruning, and image offload."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import pytest

from openharness.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
from openharness.api.usage import UsageSnapshot
from openharness.config.settings import PermissionSettings
from openharness.engine.messages import (
    ConversationMessage,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from openharness.engine.query import QueryContext, run_query
from openharness.engine.stream_events import ErrorEvent, StatusEvent
from openharness.permissions import PermissionChecker, PermissionMode
from openharness.services.compact import (
    AutoCompactState,
    auto_compact_if_needed,
    count_inline_images,
    extract_image_limit_from_error,
    is_image_limit_error,
    offload_oldest_images,
    prune_tool_results_for_compaction,
    try_context_collapse,
)
from openharness.services.token_estimation import (
    estimate_image_tokens,
    estimate_tokens,
    estimate_tool_result_tokens,
)
from openharness.services.tool_outputs import (
    prune_tool_result_text,
    retain_tool_output_preview,
    should_offload_tool_output,
)
from openharness.tools.base import ToolRegistry


def _sample_png_block(source_path: str = "") -> ImageBlock:
    raw = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image-payload").decode("ascii")
    return ImageBlock(media_type="image/png", data=raw, source_path=source_path)


def test_multimodal_and_dense_cjk_token_estimation():
    cjk_text = "中" * 4_000
    assert estimate_tokens(cjk_text) >= 2_000
    assert should_offload_tool_output(
        "bash",
        cjk_text,
        max_inline_chars=10_000,
        max_inline_tokens=1_500,
    )
    img = _sample_png_block()
    assert estimate_image_tokens(img) >= 1_600
    assert estimate_tool_result_tokens("ok", [img, img]) >= 3_200

    preview = retain_tool_output_preview(cjk_text, max_chars=5_000, max_tokens=200)
    assert estimate_tokens(preview) <= 220

    pruned = prune_tool_result_text("HEAD\n" + ("x" * 5000) + "\nTAIL", max_chars=800, max_tokens=150)
    assert "HEAD" in pruned and "TAIL" in pruned
    assert "pruned" in pruned


def test_deterministic_pruner_shrinks_older_results_and_preserves_images():
    img = _sample_png_block("/tmp/a.png")
    huge_payload = "START_MARKER\n" + ("line of verbose log output\n" * 400) + "END_MARKER"
    messages = [
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="t1", name="bash", input={"command": "echo hi"})],
        ),
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="t1",
                    content=huge_payload,
                    images=[img],
                    result_metadata={"exit_code": 0},
                )
            ],
        ),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="t2", name="read_file", input={"path": "a.py"})],
        ),
        ConversationMessage(
            role="user",
            content=[ToolResultBlock(tool_use_id="t2", content="recent small result")],
        ),
        ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
    ]

    pruned_messages, saved = prune_tool_results_for_compaction(
        messages,
        preserve_recent=3,
        max_result_tokens=200,
        max_result_chars=1_000,
    )
    assert saved > 0
    first_result = pruned_messages[1].content[0]
    assert isinstance(first_result, ToolResultBlock)
    assert "START_MARKER" in first_result.content
    assert "END_MARKER" in first_result.content
    assert len(first_result.content) < len(huge_payload)
    assert len(first_result.images) == 1
    assert first_result.result_metadata == {"exit_code": 0}


def test_try_context_collapse_preserves_tool_result_images():
    img = _sample_png_block()
    messages = [
        ConversationMessage.from_user_text("inspect"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="t1", name="bash", input={"command": "run"})],
        ),
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="t1",
                    content="A" * 4_000,
                    images=[img],
                    result_metadata={"k": "v"},
                )
            ],
        ),
        ConversationMessage.from_user_text("msg4"),
        ConversationMessage(role="assistant", content=[TextBlock(text="msg5")]),
        ConversationMessage.from_user_text("msg6"),
    ]
    collapsed = try_context_collapse(messages, preserve_recent=3)
    assert collapsed is not None
    result_block = collapsed[2].content[0]
    assert isinstance(result_block, ToolResultBlock)
    assert len(result_block.images) == 1
    assert result_block.result_metadata == {"k": "v"}


@pytest.mark.asyncio
async def test_auto_compact_skips_llm_call_after_deterministic_pruning():
    class _FailIfCalledClient:
        async def stream_message(self, request):
            raise AssertionError("LLM summarization should not be called when 0-token pruning suffices")
            yield  # pragma: no cover

    messages = [
        ConversationMessage.from_user_text("run build"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="t1", name="generate_image", input={"prompt": "test"})],
        ),
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="t1",
                    content="HEAD_OK\n" + ("log line 1234567890\n" * 500) + "TAIL_OK",
                )
            ],
        ),
        ConversationMessage.from_user_text("next"),
        ConversationMessage(role="assistant", content=[TextBlock(text="done")]),
    ]
    state = AutoCompactState()
    compacted, was_compacted = await auto_compact_if_needed(
        messages,
        api_client=_FailIfCalledClient(),
        model="claude-sonnet-4-5",
        state=state,
        preserve_recent=2,
        auto_compact_threshold_tokens=1_200,
    )
    assert was_compacted is True
    assert "HEAD_OK" in compacted[2].content[0].content


def test_offload_oldest_images_persists_bytes_and_handles_tool_results(tmp_path: Path):
    img1 = _sample_png_block()
    img2 = _sample_png_block(str(tmp_path / "existing.png"))
    messages = [
        ConversationMessage(role="user", content=[TextBlock(text="look"), img1]),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="t1", name="bash", input={"command": "shot"})],
        ),
        ConversationMessage(
            role="user",
            content=[ToolResultBlock(tool_use_id="t1", content="captured", images=[img2])],
        ),
    ]
    assert count_inline_images(messages) == 2

    offloaded = offload_oldest_images(
        messages,
        count=1,
        workspace_dir=tmp_path,
        expose_paths=True,
    )
    assert offloaded == 1
    assert count_inline_images(messages) == 1
    replaced_block = messages[0].content[1]
    assert isinstance(replaced_block, TextBlock)
    assert "[Image offloaded:" in replaced_block.text
    offload_files = list((tmp_path / ".openharness" / "image_offloads").glob("img_*"))
    assert len(offload_files) == 1

    offloaded_second = offload_oldest_images(messages, count=1, workspace_dir=tmp_path)
    assert offloaded_second == 1
    assert count_inline_images(messages) == 0
    tr = messages[2].content[0]
    assert isinstance(tr, ToolResultBlock)
    assert tr.images == []
    assert "existing.png" in tr.content


def test_image_limit_error_detection():
    err = RuntimeError("BadRequestError: request includes too many images (at most 5 images allowed)")
    assert is_image_limit_error(err)
    assert extract_image_limit_from_error(err) == 5


@dataclass
class _FakeResponse:
    message: ConversationMessage
    usage: UsageSnapshot


@pytest.mark.asyncio
async def test_run_query_transparently_retries_after_image_limit_error(tmp_path: Path):
    class _ImageLimitThenOkClient:
        def __init__(self) -> None:
            self.calls = 0

        async def stream_message(self, request):
            self.calls += 1
            if self.calls == 1:
                assert count_inline_images(request.messages) == 2
                raise RuntimeError("Invalid request: too many images; at most 1 image allowed per request")
            assert count_inline_images(request.messages) == 1
            reply = ConversationMessage(role="assistant", content=[TextBlock(text="recovered cleanly")])
            yield ApiTextDeltaEvent(text="recovered cleanly")
            yield ApiMessageCompleteEvent(
                message=reply,
                usage=UsageSnapshot(input_tokens=10, output_tokens=5),
                stop_reason="end_turn",
            )

    client = _ImageLimitThenOkClient()
    context = QueryContext(
        api_client=client,
        tool_registry=ToolRegistry(),
        permission_checker=PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO)),
        cwd=tmp_path,
        model="claude-sonnet-4-5",
        system_prompt="test",
        max_tokens=512,
    )
    messages = [
        ConversationMessage(
            role="user",
            content=[TextBlock(text="compare"), _sample_png_block(), _sample_png_block()],
        )
    ]

    events = [evt async for evt, _ in run_query(context, messages)]
    assert client.calls == 2
    assert not any(isinstance(e, ErrorEvent) for e in events)
    assert any(isinstance(e, StatusEvent) and "offloaded 1" in e.message.lower() for e in events)
