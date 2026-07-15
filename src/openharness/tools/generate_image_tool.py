"""Manus-style image generation tool.

The tool is intentionally thin: it validates high-level intent and delegates
all paid media execution to the SaaS backend hook.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class ImageGenerationBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    medium: str | None = None
    subject: str | None = None
    composition: str | None = None
    style: str | None = None
    text: str | None = None
    constraints: str | None = None


class ImageGenerationReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ref: str = Field(description="Stable artifact/upload/public image reference.")
    role: Literal["edit_target", "style", "identity", "product", "composition", "mask"] = "style"

    @field_validator("input_ref")
    @classmethod
    def require_stable_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("input_ref is required")
        return text


class ImageGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_ratio: str | None = None
    size_tier: Literal["512px", "1K", "2K", "4K"] | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    quality_goal: Literal["draft", "balanced", "high_quality", "text_accuracy"] | None = None
    count: int | None = Field(default=None, ge=1, le=10)
    transparent_background: bool | None = None


class ImageGenerationEditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preserve_identity: bool = True
    preserve_composition: bool = True
    allow_crop: bool = False
    allow_outpaint: bool = True


class ImageGenerationTextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["none", "embedded", "exact", "avoid_text"] | None = None
    exact_text: str | None = None
    language: str | None = None
    text_accuracy_required: bool = False


class GenerateImageInput(BaseModel):
    """High-level image request extracted from the imagegen skill."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["generate", "edit", "restore", "variation"] = "generate"
    scenario: Literal[
        "website_or_landing_page",
        "product_or_commerce",
        "marketing_or_social",
        "ui_or_app_mockup",
        "logo_or_icon",
        "game_or_asset_pack",
        "character_or_portrait",
        "diagram_or_infographic",
        "precise_image_edit",
        "image_upscale_or_restore",
        "poster",
        "product",
        "ui_mockup",
        "transparent_asset",
        "edit",
        "restore",
        "infographic",
        "general",
    ] = "general"
    prompt: str = Field(description="Final image prompt or edit instruction.")
    brief: ImageGenerationBrief = Field(
        description='Required production brief object. Pass as {"purpose": "..."} or {}, never as a quoted JSON string.',
    )
    output: ImageGenerationOutput = Field(
        description='Required output intent object such as {"width": 1200, "height": 628, "count": 1} or {}. Never pass a quoted JSON string.',
    )
    edit_policy: ImageGenerationEditPolicy = Field(
        description='Required edit behavior object such as {"allow_crop": false} or {}. Never pass a quoted JSON string.',
    )
    text_policy: ImageGenerationTextPolicy = Field(
        description='Required text rendering policy object such as {"mode": "avoid_text"} or {}. Never pass a quoted JSON string.',
    )
    model_id: str | None = Field(default=None, description="Optional logical image model id.")
    references: list[ImageGenerationReference] = Field(default_factory=list)

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
        "Generate, edit, restore, or vary raster images from high-level image intent. "
        "The SaaS backend handles model routing, billing, provider execution, validation, and artifact delivery. "
        "Required nested fields brief, output, edit_policy, and text_policy must be passed as objects. "
        "Use empty objects when there is no detail; never quote nested JSON."
    )
    input_model = GenerateImageInput
    display_name = "图片生成"
    default_start_message = "正在生成图片..."
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
