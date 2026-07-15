"""Manus-style image generation tool.

The tool is intentionally thin: it validates high-level intent and delegates
all paid media execution to the SaaS backend hook.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ImageGenerationBrief(BaseModel):
    purpose: str | None = None
    medium: str | None = None
    subject: str | None = None
    composition: str | None = None
    style: str | None = None
    text: str | None = None
    constraints: str | None = None


class ImageGenerationReference(BaseModel):
    input_ref: str = Field(description="Stable artifact/upload/public image reference.")
    role: Literal["edit_target", "style", "identity", "product", "composition", "mask"] = "style"

    @field_validator("input_ref")
    @classmethod
    def require_stable_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("input_ref is required")
        return text


class GenerateImageInput(BaseModel):
    """High-level image request extracted from the imagegen skill."""

    intent: Literal["generate", "edit", "restore", "variation"] = "generate"
    prompt: str = Field(description="Final image prompt or edit instruction.")
    brief: ImageGenerationBrief = Field(default_factory=ImageGenerationBrief)
    model_id: str | None = Field(default=None, description="Optional logical image model id.")
    references: list[ImageGenerationReference] = Field(default_factory=list)
    aspect_ratio: str | None = None
    size: str | None = None
    resolution: str | None = None
    quality: str | None = None
    transparent_background: bool = False
    output_count: int = Field(default=1, ge=1, le=10)

    @field_validator("prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("prompt is required")
        if len(text) > 12000:
            raise ValueError("prompt is too long")
        return text


class GenerateImageTool(BaseTool):
    """Delegate image generation to the SaaS media backend."""

    name = "generate_image"
    description = (
        "Generate, edit, restore, or vary raster images from a high-level creative brief. "
        "Use after loading the imagegen skill. This tool does not call providers directly; "
        "the SaaS backend handles model routing, billing, media gateways, and artifact delivery."
    )
    input_model = GenerateImageInput
    requires_sandbox = False

    async def execute(self, arguments: GenerateImageInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "generate_image"):
            return ToolResult(
                output="Image generation is only available through the SaaS media backend.",
                is_error=True,
                metadata={"media_billing_status": "skipped"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "media_generate",
                    "status": "running",
                    "message": "正在生成图片...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        backend_metadata = {
            **context.metadata,
            "cwd": str(context.cwd),
        }
        try:
            result = await hook.generate_image(arguments.model_dump(mode="json"), backend_metadata)
        except Exception as exc:
            return ToolResult(
                output=f"Image generation failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={},
            )

        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "Image generation failed."),
                is_error=True,
                metadata=metadata,
            )

        count = len(metadata.get("artifact_payloads") or [])
        return ToolResult(
            output=(
                f"generate_image completed and published {count} image artifact(s) to the UI. "
                "Do not call deliver_artifact for these image artifact(s)."
            ),
            metadata={
                **metadata,
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )
