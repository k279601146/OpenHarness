"""Helpers for stable SaaS artifact media references."""

from __future__ import annotations

from typing import Any

from openharness.tools.base import ToolExecutionContext, ToolResult


MEDIA_REF_GUIDANCE = (
    "This turn already includes stable media artifact reference(s). "
    "Do not search sandbox roots for old media filenames, do not download `/artifacts/...`, "
    "and do not treat public URLs as filesystem paths. Pass the `artifact:<id>` input_ref "
    "directly to imagegen_cli/videogen_cli so the SaaS artifact materializer can prepare "
    "a current sandbox input."
)

IMAGE_REUSE_WORDS = (
    "edit",
    "modify",
    "change",
    "replace",
    "reference",
    "use this",
    "based on",
    "from this",
    "修改",
    "改成",
    "改为",
    "换成",
    "替换",
    "参考",
    "基于",
    "这张",
    "上一轮",
    "上一次",
)


def mentioned_media_inputs(context: ToolExecutionContext, *media_types: str) -> list[dict[str, Any]]:
    raw_items = context.metadata.get("mentioned_media_inputs")
    if not isinstance(raw_items, list):
        return []
    wanted = {item.strip().lower() for item in media_types if item.strip()}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        artifact_type = str(item.get("artifact_type") or "").strip().lower()
        input_ref = str(item.get("input_ref") or "").strip()
        if not input_ref.startswith("artifact:"):
            continue
        if wanted and artifact_type not in wanted:
            continue
        if input_ref in seen:
            continue
        seen.add(input_ref)
        result.append(item)
    return result


def media_input_refs(context: ToolExecutionContext, *media_types: str) -> list[str]:
    return [str(item["input_ref"]) for item in mentioned_media_inputs(context, *media_types)]


def has_mentioned_media(context: ToolExecutionContext) -> bool:
    return bool(mentioned_media_inputs(context))


def looks_like_media_reuse_prompt(prompt: str | None) -> bool:
    text = str(prompt or "").strip().lower()
    return bool(text and any(word in text for word in IMAGE_REUSE_WORDS))


def artifact_lookup_guard_result(context: ToolExecutionContext, text: str) -> ToolResult | None:
    if not has_mentioned_media(context):
        return None
    normalized = str(text or "").replace("\\", "/").lower()
    if not _looks_like_wrong_artifact_lookup(normalized):
        return None
    refs = ", ".join(media_input_refs(context)) or "the mentioned artifact input_ref"
    return ToolResult(
        output=f"{MEDIA_REF_GUIDANCE} Available input_ref(s): {refs}",
        is_error=True,
        metadata={"artifact_reference_guard": True, "input_refs": media_input_refs(context)},
    )


def wrong_media_type_error(context: ToolExecutionContext, expected: str) -> ToolResult:
    refs = [
        f"{item.get('input_ref')} ({item.get('artifact_type') or 'unknown'})"
        for item in mentioned_media_inputs(context)
    ]
    return ToolResult(
        output=(
            f"The current media tool needs {expected} artifact input, but the mentioned "
            f"media artifact type does not match. Mentioned media: {', '.join(refs) or 'none'}."
        ),
        is_error=True,
        metadata={"artifact_reference_guard": True, "expected_media_type": expected},
    )


def _looks_like_wrong_artifact_lookup(text: str) -> bool:
    if "/artifacts/" in text:
        return True
    if "imagegen_output" in text or "videogen_output" in text:
        return True
    if "materialized" in text and ("glob" in text or "*" in text or "/inputs/materialized" in text):
        return True
    return ("curl" in text or "wget" in text) and "artifact" in text
