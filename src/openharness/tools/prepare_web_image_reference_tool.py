"""Prepare selected web image URLs as stable SaaS artifact references."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class PrepareWebImageReferenceInput(BaseModel):
    """Arguments for preparing one selected web image candidate."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="Selected public HTTP or HTTPS image URL from web_fetch image candidates.")
    source_page_url: str | None = Field(default=None, description="Page URL where the image candidate was discovered.")
    filename: str | None = Field(default=None, description="Optional user-facing filename for the registered image artifact.")
    role: Literal["edit_target", "style"] = Field(
        default="edit_target",
        description=(
            "Intended generate_image reference role. Use edit_target by default; use style only when the user "
            "explicitly asks to reference style/aesthetic only."
        ),
    )


class PrepareWebImageReferenceTool(BaseTool):
    """Delegate selected web image preparation to the SaaS backend."""

    name = "prepare_web_image_reference"
    description = (
        "Download one selected web image candidate through the SaaS security boundary, "
        "validate it, register it as a task artifact, and return a stable input_ref for generate_image. "
        "Use this only for URLs chosen from web_fetch image candidates; do not pass third-party image URLs "
        "directly to generate_image references."
    )
    input_model = PrepareWebImageReferenceInput
    display_name = "准备网页图片参考"
    default_start_message = "正在准备网页图片参考..."
    requires_sandbox = False

    async def execute(self, arguments: PrepareWebImageReferenceInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "prepare_web_image_reference"):
            return ToolResult(
                output="prepare_web_image_reference is only available through the SaaS backend.",
                is_error=True,
            )

        prepared_count = int(context.metadata.get("prepared_web_image_reference_count") or 0)
        if prepared_count >= 2:
            return ToolResult(
                output="prepare_web_image_reference failed: at most 2 web image references can be prepared per turn.",
                is_error=True,
                metadata={"code": "web_image_reference_limit_exceeded"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "prepare_web_image_reference",
                    "status": "running",
                    "message": "正在准备网页图片参考...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        result = await hook.prepare_web_image_reference(
            arguments.model_dump(mode="json"),
            {**context.metadata, "cwd": str(context.cwd)},
        )
        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "prepare_web_image_reference failed."),
                is_error=True,
                metadata=metadata,
            )

        context.metadata["prepared_web_image_reference_count"] = prepared_count + 1
        input_ref = str(metadata.get("input_ref") or "")
        public_url = str(metadata.get("public_url") or "")
        role = str(metadata.get("role") or arguments.role)
        return ToolResult(
            output=(
                "Prepared web image reference.\n"
                f"input_ref: {input_ref}\n"
                f"public_url: {public_url}\n"
                f"generate_image reference: input_ref={input_ref}, role={role}"
            ),
            metadata=metadata,
        )

    def is_read_only(self, arguments: BaseModel) -> bool:
        del arguments
        return False
