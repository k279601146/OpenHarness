"""Canonical hand-drawn story video composition tool.

The tool is intentionally thin: it validates high-level story/video intent and
delegates all host-side rendering and artifact publication to the SaaS backend.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


def _is_stable_media_reference(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if "\\" in text:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return False
    if text.startswith("artifact:"):
        artifact_id = text.split(":", 1)[1].strip()
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", artifact_id))
    parsed = urlparse(text)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return False
    normalized = parsed.path
    if not (normalized.startswith("/artifacts/") or normalized.startswith("/uploads/")):
        return False
    return all(part not in {"", ".", ".."} for part in normalized.split("/")[1:])


def _is_bgm_library_reference(value: str) -> bool:
    text = str(value or "").strip()
    if not text.startswith("bgm:"):
        return False
    track_id = text.split(":", 1)[1].strip()
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", track_id))


class HanddrawStoryCrop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scale: float = Field(default=1.0, ge=1.0, le=2.0)
    x: float = Field(default=0.0, ge=-360.0, le=360.0)
    y: float = Field(default=0.0, ge=-480.0, le=480.0)


class HanddrawStoryPropText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[str] = Field(min_length=1, max_length=3)
    x: float = Field(default=360.0, ge=0.0, le=720.0)
    y: float = Field(default=600.0, ge=0.0, le=960.0)
    rotation: float = Field(default=0.0, ge=-30.0, le=30.0)
    font_size: int = Field(default=18, ge=10, le=40)
    line_gap: int | None = Field(default=None, ge=8, le=56)
    show_at: float = Field(default=1.5, ge=0.0, le=5.0)

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, value: list[str]) -> list[str]:
        normalized = [str(line).strip() for line in value if str(line).strip()]
        if not 1 <= len(normalized) <= 3:
            raise ValueError("prop_text.lines must contain 1-3 non-empty lines")
        for line in normalized:
            if len(line) > 18:
                raise ValueError("prop_text lines must be 18 characters or fewer")
        return normalized


class HanddrawStoryScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable scene id, for example scene-01.")
    duration: float = Field(ge=1.0, le=10.0, description="Scene duration in seconds.")
    caption_lines: list[str] = Field(default_factory=list, max_length=3)
    color_image_ref: str = Field(description="Stable color mother image reference.")
    visual_note: str | None = Field(default=None, max_length=1000)
    prop_text: HanddrawStoryPropText | None = Field(default=None)
    crop: HanddrawStoryCrop = Field(
        default_factory=HanddrawStoryCrop,
        description='Optional controlled crop object such as {"scale": 1}. Never pass a quoted JSON string.',
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("scene id is required")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", text):
            raise ValueError("scene id must be short and stable")
        return text

    @field_validator("caption_lines")
    @classmethod
    def validate_caption_lines(cls, value: list[str]) -> list[str]:
        normalized = [str(line).strip() for line in value if str(line).strip()]
        if len(normalized) > 3:
            raise ValueError("caption_lines must contain at most 3 lines")
        for line in normalized:
            if len(line) > 18:
                raise ValueError("caption lines must be 18 characters or fewer")
        return normalized

    @field_validator("color_image_ref")
    @classmethod
    def validate_color_image_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not _is_stable_media_reference(text):
            raise ValueError("color_image_ref must be artifact:<id>, /artifacts/..., or /uploads/...")
        return text


class HanddrawStoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: Literal[720] = 720
    height: Literal[960] = 960
    fps: Literal[30] = 30
    format: Literal["mp4"] = "mp4"
    duration_seconds: float | None = Field(default=None, ge=35.0, le=45.0)


class HanddrawStoryCaptionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    top_safe_area_px: int = Field(default=48, ge=32, le=160)
    max_lines: Literal[3] = 3


class HanddrawStoryBgm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "library", "upload"] = "none"
    mood: str | None = Field(default=None, max_length=64)
    ref: str | None = Field(default=None, max_length=180)
    volume: Literal["soft", "normal"] = "soft"
    fade_in_seconds: float = Field(default=1.0, ge=0.0, le=5.0)
    fade_out_seconds: float = Field(default=1.5, ge=0.0, le=5.0)
    loop: bool = True

    @field_validator("mood", "ref")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    @model_validator(mode="after")
    def validate_bgm_reference(self) -> "HanddrawStoryBgm":
        if self.mode == "none":
            if self.ref or self.mood:
                raise ValueError("bgm mode none cannot include ref or mood")
            return self
        if self.mode == "library":
            if self.ref and not _is_bgm_library_reference(self.ref):
                raise ValueError("library bgm ref must use bgm:<track_id>")
            return self
        if not self.ref:
            raise ValueError("upload bgm mode requires ref")
        if not _is_stable_media_reference(self.ref):
            raise ValueError("upload bgm ref must be artifact:<id>, /artifacts/..., or /uploads/...")
        return self


class CreateHanddrawStoryVideoInput(BaseModel):
    """High-level hand-drawn story video composition request."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=500)
    scenes: list[HanddrawStoryScene] = Field(min_length=7, max_length=9)
    output: HanddrawStoryOutput = Field(
        description='Required output object. Use {} for the default 720x960, 30 fps MP4. Never pass a quoted JSON string.',
    )
    caption_policy: HanddrawStoryCaptionPolicy = Field(
        description='Required caption behavior object. Use {} for defaults. Never pass a quoted JSON string.',
    )
    bgm: HanddrawStoryBgm | None = Field(
        default=None,
        description=(
            'Optional BGM object. Use {"mode":"library","mood":"warm"} for a registered library track, '
            '{"mode":"upload","ref":"artifact:<id>"} for uploaded audio, or {"mode":"none"}. '
            "Never pass a quoted JSON string."
        ),
    )
    bgm_ref: str | None = Field(
        default=None,
        description="Legacy optional stable uploaded audio reference. Do not use together with bgm.",
    )
    style_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("title", "topic")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("value is required")
        return text

    @field_validator("bgm_ref")
    @classmethod
    def validate_bgm_ref(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if not _is_stable_media_reference(text):
            raise ValueError("bgm_ref must be artifact:<id>, /artifacts/..., or /uploads/...")
        return text

    @model_validator(mode="after")
    def validate_story_timing(self) -> "CreateHanddrawStoryVideoInput":
        if self.bgm is not None and self.bgm_ref:
            raise ValueError("use either bgm or bgm_ref, not both")
        scene_ids = [scene.id for scene in self.scenes]
        if len(set(scene_ids)) != len(scene_ids):
            raise ValueError("scene ids must be unique")
        refs = [scene.color_image_ref for scene in self.scenes]
        if len(set(refs)) != len(refs):
            raise ValueError("each scene must use a distinct color_image_ref")
        duration = sum(float(scene.duration) for scene in self.scenes)
        if not 35.0 <= duration <= 45.0:
            raise ValueError("scene durations must total 35-45 seconds")
        if self.output.duration_seconds is not None and abs(float(self.output.duration_seconds) - duration) > 0.25:
            raise ValueError("output.duration_seconds must match total scene duration")
        return self


class CreateHanddrawStoryVideoTool(BaseTool):
    """Delegate hand-drawn story video composition to the SaaS backend."""

    name = "create_handdraw_story_video"
    description = (
        "Compose a 35-45 second vertical hand-drawn story video from 7-9 existing color mother image artifacts. "
        "The SaaS backend resolves stable image references, extracts aligned line art, renders left-to-right line and color reveal, "
        "optionally mixes registered or uploaded BGM, registers the MP4 artifact, and publishes it to the UI. "
        "Nested fields output, caption_policy, bgm, scene.crop, and scene.prop_text must be passed as objects, never quoted JSON. "
        "Use only stable media references such as artifact:<id>, /artifacts/..., /uploads/..., or registered BGM refs such as bgm:<track_id>. "
        "Do not pass provider fields, API keys, URLs, prices, billing units, or local paths."
    )
    input_model = CreateHanddrawStoryVideoInput
    display_name = "手绘故事成片"
    default_start_message = "正在合成手绘故事视频..."
    requires_sandbox = False

    async def execute(self, arguments: CreateHanddrawStoryVideoInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "create_handdraw_story_video"):
            return ToolResult(
                output="Hand-drawn story video composition is only available through the SaaS backend.",
                is_error=True,
                metadata={"media_billing_status": "skipped", "handdraw_story_video_status": "skipped"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "handdraw_story_video",
                    "status": "running",
                    "message": "正在合成手绘故事视频...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        backend_metadata = {
            **context.metadata,
            "cwd": str(context.cwd),
        }
        try:
            result = await hook.create_handdraw_story_video(arguments.model_dump(mode="json"), backend_metadata)
        except Exception:
            return ToolResult(
                output="Hand-drawn story video composition failed in the SaaS backend.",
                is_error=True,
                metadata={"media_billing_status": "skipped", "handdraw_story_video_status": "failed"},
            )

        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "Hand-drawn story video composition failed."),
                is_error=True,
                metadata=metadata,
            )

        artifacts = metadata.get("artifact_payloads") if isinstance(metadata.get("artifact_payloads"), list) else []
        artifact_summaries = [
            {
                "artifact_id": item.get("artifact_id"),
                "url": item.get("url"),
                "type": item.get("type"),
            }
            for item in artifacts
            if isinstance(item, dict)
        ]
        artifact_summaries = [
            {key: value for key, value in item.items() if value is not None}
            for item in artifact_summaries
        ]
        artifact_id = artifact_summaries[0].get("artifact_id") if artifact_summaries else None

        result_metadata = {
            "publish_state": "published",
            "published_artifact": True,
            "delivery_required": False,
            "do_not_deliver_artifact": True,
            "media_billing_status": metadata.get("media_billing_status") or "skipped",
            "handdraw_story_video_status": "published",
            "bgm_status": metadata.get("bgm_status") or "none",
            "artifact_id": artifact_id,
            "artifact_count": len(artifact_summaries),
            "artifact_payloads": artifact_summaries,
        }
        for key in ("bgm_mode", "bgm_track_id", "bgm_title"):
            if metadata.get(key) is not None:
                result_metadata[key] = metadata[key]

        return ToolResult(
            output=(
                f"create_handdraw_story_video completed and published {len(artifact_summaries)} video artifact(s) to the UI. "
                "Do not call deliver_artifact for these video artifact(s)."
            ),
            metadata=result_metadata,
        )
