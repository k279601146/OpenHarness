"""Tests for session persistence."""

from __future__ import annotations

import json
from pathlib import Path

from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.engine.events import build_session_event, stream_event_to_session_event
from openharness.engine.stream_events import ToolExecutionStarted
from openharness.services.session_storage import (
    append_session_event,
    export_session_markdown,
    get_session_event_log_path,
    get_project_session_dir,
    load_session_events,
    load_session_snapshot,
    save_session_snapshot,
)


def test_save_and_load_session_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = save_session_snapshot(
        cwd=project,
        model="claude-test",
        system_prompt="system",
        messages=[ConversationMessage(role="user", content=[TextBlock(text="hello")])],
        usage=UsageSnapshot(input_tokens=1, output_tokens=2),
        tool_metadata={
            "task_focus_state": {"goal": "Fix compact carry-over"},
            "recent_verified_work": ["Focused session storage test passed"],
        },
    )

    assert path.exists()
    snapshot = load_session_snapshot(project)
    assert snapshot is not None
    assert snapshot["model"] == "claude-test"
    assert snapshot["usage"]["output_tokens"] == 2
    assert snapshot["tool_metadata"]["task_focus_state"]["goal"] == "Fix compact carry-over"
    assert snapshot["tool_metadata"]["recent_verified_work"] == ["Focused session storage test passed"]


def test_export_session_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    path = export_session_markdown(
        cwd=project,
        messages=[
            ConversationMessage(role="user", content=[TextBlock(text="hello")]),
            ConversationMessage(role="assistant", content=[TextBlock(text="world")]),
        ],
    )

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "OpenHarness Session Transcript" in content
    assert "hello" in content
    assert "world" in content


def test_load_session_snapshot_sanitizes_legacy_empty_assistant_messages(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    target_dir = get_project_session_dir(project)
    payload = {
        "session_id": "legacy123",
        "cwd": str(project),
        "model": "claude-test",
        "system_prompt": "system",
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"role": "assistant", "content": None},
            {"role": "assistant", "content": []},
            {"role": "assistant", "content": [{"type": "text", "text": "world"}]},
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "tool_metadata": {},
        "created_at": 1.0,
        "summary": "hello",
        "message_count": 4,
    }
    (target_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_session_snapshot(project)
    assert snapshot is not None
    assert snapshot["message_count"] == 2
    assert [message["role"] for message in snapshot["messages"]] == ["user", "assistant"]
    assert snapshot["messages"][1]["content"][0]["text"] == "world"


def test_append_session_event_jsonl_redacts_sensitive_values(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENHARNESS_DATA_DIR", str(tmp_path / "data"))
    project = tmp_path / "repo"
    project.mkdir()

    event = build_session_event(
        "user_message_submitted",
        session_id="session/unsafe",
        payload={
            "prompt": "use Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "url": "https://example.test/path?token=secret",
            "cwd": str(project / "secret" / "file.txt"),
        },
    )

    path = append_session_event(cwd=project, session_id="session/unsafe", event=event)
    assert path == get_session_event_log_path(project, "session/unsafe")

    events = load_session_events(project, "session/unsafe")
    assert len(events) == 1
    serialized = json.dumps(events[0], ensure_ascii=False)
    assert "use Authorization" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "token=secret" not in serialized
    assert str(project) not in serialized
    assert events[0]["event_type"] == "user_message_submitted"


def test_tool_start_session_event_summarizes_input_shape_without_values():
    event = stream_event_to_session_event(
        ToolExecutionStarted(
            tool_name="generate_image",
            tool_use_id="toolu_1",
            tool_input={
                "prompt": "short confidential prompt",
                "output": {"count": 2, "path": "C:/private/result.png"},
            },
        ),
        session_id="session-event-test",
        fallback_turn_id="turn_123",
    )

    assert event is not None
    record = event.to_record()
    serialized = json.dumps(record, ensure_ascii=False)
    assert record["turn_id"] == "turn_123"
    assert "short confidential prompt" not in serialized
    assert "C:/private" not in serialized
    assert record["payload"]["tool_input"]["keys"] == ["output", "prompt"]
    assert record["payload"]["tool_input"]["shape"]["prompt"]["type"] == "str"
