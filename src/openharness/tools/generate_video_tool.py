"""Canonical video generation tool.

The tool is intentionally thin: it validates high-level video intent and
delegates all paid media execution to the SaaS backend hook.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class VideoGenerationBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    subject: str | None = None
    scene: str | None = None
    motion: str | None = None
    camera: str | None = None
    lighting: str | None = None
    audio: str | None = None
    constraints: str | None = None


class VideoGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    aspect_ratio: str | None = None
    resolution: str | None = None
    mode: str | None = None
    count: int | None = Field(default=None, ge=1, le=10)
    generate_audio: bool | None = None
    watermark: bool | None = None


class VideoGenerationReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ref: str = Field(description="Stable artifact/upload video or image reference.")
    role: Literal[
        "first_frame",
        "last_frame",
        "identity",
        "style",
        "motion",
        "environment",
        "audio",
        "video_reference",
    ]

    @field_validator("input_ref")
    @classmethod
    def require_stable_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("input_ref is required")
        return text


class GenerateVideoInput(BaseModel):
    """High-level video request extracted from the video_gen skill."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["generate", "animate", "interpolate", "reference"] = "generate"
    prompt: str = Field(description="Final video generation instruction.")
    brief: VideoGenerationBrief = Field(
        description='Required production brief object such as {"subject": "..."} or {}. Never pass a quoted JSON string.',
    )
    output: VideoGenerationOutput = Field(
        description='Required output intent object such as {"duration_seconds": 5, "aspect_ratio": "16:9"} or {}. Never pass a quoted JSON string.',
    )
    references: list[VideoGenerationReference] = Field(default_factory=list)
    model_id: str | None = Field(default=None, description="Optional logical video model id.")

    @field_validator("prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("prompt is required")
        if len(text) > 12000:
            raise ValueError("prompt is too long")
        return text


class GenerateVideoTool(BaseTool):
    """Delegate video generation to the SaaS media backend."""

    name = "generate_video"
    description = (
        "Generate, animate, interpolate, or reference-generate videos from high-level video intent. "
        "The SaaS backend handles model routing, billing, provider execution, validation, and artifact delivery. "
        "Required nested fields brief and output must be passed as objects. "
        "Use empty objects when there is no detail; never quote nested JSON."
    )
    input_model = GenerateVideoInput
    display_name = "视频生成"
    default_start_message = "正在生成视频..."
    requires_sandbox = False

    async def execute(self, arguments: GenerateVideoInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "generate_video"):
            return ToolResult(
                output="Video generation is only available through the SaaS media backend.",
                is_error=True,
                metadata={"media_billing_status": "skipped"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "media_generate",
                    "status": "running",
                    "message": "正在生成视频...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        backend_metadata = {
            **context.metadata,
            "cwd": str(context.cwd),
        }
        try:
            result = await hook.generate_video(arguments.model_dump(mode="json"), backend_metadata)
        except Exception as exc:
            return ToolResult(
                output=f"Video generation failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={},
            )

        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "Video generation failed."),
                is_error=True,
                metadata=metadata,
            )

        count = len(metadata.get("artifact_payloads") or [])
        return ToolResult(
            output=(
                f"generate_video completed and published {count} video artifact(s) to the UI. "
                "Do not call deliver_artifact for these video artifact(s)."
            ),
            metadata={
                **metadata,
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )
