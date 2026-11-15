from __future__ import annotations

from openharness.engine.messages import (
    ConversationMessage,
    ImageBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    sanitize_conversation_messages,
    serialize_content_block,
)


def test_sanitize_conversation_messages_keeps_complete_tool_turn():
    messages = [
        ConversationMessage.from_user_text("edit the file"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="write_file:234", name="write_file", input={"path": "x"})],
        ),
        ConversationMessage(
            role="user",
            content=[ToolResultBlock(tool_use_id="write_file:234", content="ok", is_error=False)],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == messages


def test_sanitize_conversation_messages_drops_dangling_trailing_tool_use():
    messages = [
        ConversationMessage.from_user_text("edit the file"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="write_file:234", name="write_file", input={"path": "x"})],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == [ConversationMessage.from_user_text("edit the file")]


def test_sanitize_conversation_messages_drops_orphan_tool_results_but_keeps_user_text():
    messages = [
        ConversationMessage.from_user_text("hello"),
        ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="missing_call", content="stale", is_error=True),
                TextBlock(text="new prompt"),
            ],
        ),
    ]

    sanitized = sanitize_conversation_messages(messages)

    assert sanitized == [
        ConversationMessage.from_user_text("hello"),
        ConversationMessage(role="user", content=[TextBlock(text="new prompt")]),
    ]


def test_serialize_tool_result_block_with_images_for_all_providers():
    from openharness.api.codex_client import _convert_messages_to_codex
    from openharness.api.openai_client import (
        _convert_messages_to_openai,
        _convert_messages_to_responses_input,
    )

    image = ImageBlock(media_type="image/webp", data="YWJj", source_path="/home/user/tasks/t1/overview.jpg")
    tool_result = ToolResultBlock(
        tool_use_id="call_img_1",
        content="Binary file is readable in sandbox: /home/user/tasks/t1/overview.jpg",
        is_error=False,
        images=[image],
    )

    # 1. Anthropic format: tool_result content becomes [text, image]
    anthropic_serialized = serialize_content_block(tool_result)
    assert anthropic_serialized["type"] == "tool_result"
    assert isinstance(anthropic_serialized["content"], list)
    assert anthropic_serialized["content"][0] == {
        "type": "text",
        "text": "Binary file is readable in sandbox: /home/user/tasks/t1/overview.jpg",
    }
    assert anthropic_serialized["content"][1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/webp", "data": "YWJj"},
    }

    messages = [
        ConversationMessage.from_user_text("inspect storyboard"),
        ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="call_img_1", name="read_file", input={"path": "overview.jpg"})],
        ),
        ConversationMessage(role="user", content=[tool_result]),
    ]

    # 2. OpenAI Chat Completions: role="tool" followed by companion role="user" with image_url
    chat_items = _convert_messages_to_openai(messages, None)
    assert chat_items[2]["role"] == "tool"
    assert chat_items[2]["tool_call_id"] == "call_img_1"
    assert chat_items[3]["role"] == "user"
    assert any(part.get("type") == "image_url" for part in chat_items[3]["content"])

    # 3. OpenAI Responses API: function_call_output followed by role="user" with input_image
    responses_items = _convert_messages_to_responses_input(messages)
    assert responses_items[2]["type"] == "function_call_output"
    assert responses_items[2]["call_id"] == "call_img_1"
    assert responses_items[3]["role"] == "user"
    assert any(part.get("type") == "input_image" for part in responses_items[3]["content"])

    # 4. Codex Responses API: function_call_output followed by role="user" with input_image
    codex_items = _convert_messages_to_codex(messages)
    assert codex_items[2]["type"] == "function_call_output"
    assert codex_items[2]["call_id"] == "call_img_1"
    assert codex_items[3]["role"] == "user"
    assert any(part.get("type") == "input_image" for part in codex_items[3]["content"])

