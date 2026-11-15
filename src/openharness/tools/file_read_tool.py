"""File reading tool."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from openharness.engine.messages import ImageBlock, sniff_image_media_type
from openharness.tools.artifact_reference_guard import artifact_lookup_guard_result
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.sandbox_workspace import (
    ensure_sandbox_skill_path,
    get_e2b_task_session,
    sandbox_file_size,
    sandbox_path_status,
    to_sandbox_path,
    uses_e2b_task_workspace,
)
from openharness.utils.paths import normalize_host_path

IMAGE_READABLE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
}

BINARY_READABLE_EXTENSIONS = {
    *IMAGE_READABLE_EXTENSIONS, ".avif",
    ".mp4", ".webm", ".mov", ".mp3", ".wav", ".m4a",
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".zip",
}

MAX_IMAGE_READ_BYTES = 20 * 1024 * 1024


def _build_image_read_result(
    *,
    raw_bytes: bytes,
    display_path: str,
    suffix: str,
    size: int,
    in_sandbox: bool,
) -> ToolResult | None:
    if not raw_bytes or len(raw_bytes) > MAX_IMAGE_READ_BYTES:
        return None
    try:
        image_block, img_meta = ImageBlock.from_bytes_with_metadata(
            raw_bytes,
            source_path=display_path,
        )
    except Exception:
        return None

    w = int(img_meta.get("width") or 0)
    h = int(img_meta.get("height") or 0)
    orig_w = int(img_meta.get("original_width") or 0)
    orig_h = int(img_meta.get("original_height") or 0)
    dim_line = ""
    if w > 0 and h > 0:
        if (w, h) != (orig_w, orig_h) and orig_w > 0:
            scale = orig_w / w
            dim_line = (
                f"Dimensions: {w}x{h} px (downscaled from {orig_w}x{orig_h} px; "
                f"multiply reported coordinates by {scale:.2f} to map to original image)\n"
            )
        else:
            dim_line = f"Dimensions: {w}x{h} px\n"

    header = (
        f"Binary file is readable in sandbox: {display_path}"
        if in_sandbox
        else f"Binary file is readable: {display_path}"
    )
    footer = (
        "Image content has been attached for visual inspection. Use deliver_artifact for user-needed files."
        if in_sandbox
        else "Image content has been attached for visual inspection."
    )
    metadata: dict[str, object] = {
        "path": display_path,
        "size_bytes": size,
        "binary": True,
        "image": True,
        "media_type": image_block.media_type,
    }
    if w > 0 and h > 0:
        metadata["width"] = w
        metadata["height"] = h
        metadata["original_width"] = orig_w
        metadata["original_height"] = orig_h
    if in_sandbox:
        metadata["workspace"] = "e2b"
    return ToolResult(
        output=(
            f"{header}\n"
            f"Type: {suffix or image_block.media_type} ({image_block.media_type})\n"
            f"Size: {size} bytes\n"
            f"{dim_line}"
            f"{footer}"
        ),
        metadata=metadata,
        images=[image_block],
    )


class FileReadToolInput(BaseModel):
    """Arguments for the file read tool."""

    path: str = Field(description="Path of the file to read")
    offset: int = Field(default=0, ge=0, description="Zero-based starting line")
    limit: int = Field(default=200, ge=1, le=2000, description="Number of lines to return")


class FileReadTool(BaseTool):
    """Read a UTF-8 text file or inspect an image file from the workspace."""

    name = "read_file"
    description = "Read a text file or inspect an image file (.png, .jpg, .jpeg, .webp, .gif) from the workspace."
    input_model = FileReadToolInput
    requires_sandbox = False

    def is_read_only(self, arguments: FileReadToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: FileReadToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        guard_result = artifact_lookup_guard_result(context, arguments.path)
        if guard_result is not None:
            return guard_result
        if uses_e2b_task_workspace(context):
            return await _read_sandbox_file(arguments, context)

        path = _resolve_path(Path(context.cwd), arguments.path)
        suffix = path.suffix.lower()
        if suffix in BINARY_READABLE_EXTENSIONS:
            allowed, error_msg = _validate_readable_binary_path(path, Path(context.cwd))
            if not allowed:
                return ToolResult(output=error_msg, is_error=True)
            if not path.exists():
                return ToolResult(output=f"File not found: {path}", is_error=True)
            if path.is_dir():
                return ToolResult(output=f"Cannot read directory: {path}", is_error=True)
            size = path.stat().st_size
            if suffix in IMAGE_READABLE_EXTENSIONS and 0 < size <= MAX_IMAGE_READ_BYTES:
                try:
                    image_result = _build_image_read_result(
                        raw_bytes=path.read_bytes(),
                        display_path=str(path),
                        suffix=suffix,
                        size=size,
                        in_sandbox=False,
                    )
                    if image_result is not None:
                        return image_result
                except Exception:
                    pass
            return ToolResult(
                output=(
                    f"Binary file is readable: {path}\n"
                    f"Type: {suffix or 'unknown'}\n"
                    f"Size: {size} bytes\n"
                    "Use a media-aware tool or pass this path as an attachment/reference; "
                    "read_file only returns text or image contents."
                ),
                metadata={"path": str(path), "size_bytes": size, "binary": True},
            )
        from openharness.tools.safe_file_validator import validate_safe_file_operation

        is_safe, error_msg = validate_safe_file_operation(
            str(path),
            str(context.cwd),
            operation="read",
        )
        if not is_safe:
            return ToolResult(output=error_msg, is_error=True)

        if not path.exists():
            return ToolResult(output=f"File not found: {path}", is_error=True)
        if path.is_dir():
            return ToolResult(output=f"Cannot read directory: {path}", is_error=True)

        from openharness.tools.file_state import (
            BINARY_SNIFF_BYTES,
            READ_STREAM_MIN_SIZE,
            format_read_window,
            host_file_version,
            host_observation_key,
            observe_file,
            stream_host_text_window,
        )

        file_size = path.stat().st_size
        if file_size >= READ_STREAM_MIN_SIZE:
            with path.open("rb") as probe_handle:
                header_sample = probe_handle.read(BINARY_SNIFF_BYTES)
            if b"\x00" not in header_sample:
                window = stream_host_text_window(
                    path,
                    offset=arguments.offset,
                    limit=arguments.limit,
                )
                version = host_file_version(path)
                if version is not None:
                    observe_file(context, host_observation_key(path), version)
                return ToolResult(
                    output=window.output,
                    metadata={
                        "path": str(path),
                        "workspace": "host",
                        "total_lines": window.total_lines,
                        "offset": arguments.offset,
                        "lines_returned": window.lines_returned,
                        "truncated": window.truncated,
                        "truncated_by_bytes": window.truncated_by_bytes,
                    },
                )
            if file_size > 50 * 1024 * 1024:
                return ToolResult(
                    output=f"Cannot read oversized binary file ({file_size} bytes): {path}",
                    is_error=True,
                )

        raw = path.read_bytes()
        if b"\x00" in raw:
            if sniff_image_media_type(raw) is not None and len(raw) <= MAX_IMAGE_READ_BYTES:
                image_result = _build_image_read_result(
                    raw_bytes=raw,
                    display_path=str(path),
                    suffix=suffix,
                    size=len(raw),
                    in_sandbox=False,
                )
                if image_result is not None:
                    return image_result
            return ToolResult(output=f"Binary file cannot be read as text: {path}", is_error=True)

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        window = format_read_window(
            lines,
            offset=arguments.offset,
            limit=arguments.limit,
            display_path=str(path),
        )
        version = host_file_version(path)
        if version is not None:
            observe_file(context, host_observation_key(path), version)
        return ToolResult(
            output=window.output,
            metadata={
                "path": str(path),
                "workspace": "host",
                "total_lines": window.total_lines,
                "offset": arguments.offset,
                "lines_returned": window.lines_returned,
                "truncated": window.truncated,
                "truncated_by_bytes": window.truncated_by_bytes,
            },
        )


def _resolve_path(base: Path, candidate: str) -> Path:
    return normalize_host_path(base, candidate)


def _validate_readable_binary_path(path: Path, cwd: Path) -> tuple[bool, str]:
    try:
        resolved = path.resolve()
        workspace = cwd.resolve()
        resolved.relative_to(workspace)
    except ValueError:
        return False, f"Security restriction: cannot read files outside the workspace: {path}"
    except Exception as exc:
        return False, f"Path validation failed: {exc}"
    dangerous = {".ssh", ".env", ".git", "credentials", "secrets", ".aws", ".azure", ".gcp", "private"}
    if set(resolved.parts) & dangerous:
        return False, f"Security restriction: cannot access sensitive path: {path}"
    return True, ""


async def _read_sandbox_file(arguments: FileReadToolInput, context: ToolExecutionContext) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_path = to_sandbox_path(context, arguments.path)
        await ensure_sandbox_skill_path(context, session, sandbox_path)
    except Exception as exc:
        return ToolResult(output=f"Sandbox workspace error: {exc}", is_error=True)

    status = await sandbox_path_status(session, sandbox_path)
    if status == "missing":
        return ToolResult(output=f"File not found in sandbox: {sandbox_path}", is_error=True)
    if status == "dir":
        return ToolResult(output=f"Cannot read sandbox directory: {sandbox_path}", is_error=True)
    if status != "file":
        return ToolResult(output=f"Cannot read non-file sandbox path: {sandbox_path}", is_error=True)

    suffix = Path(sandbox_path).suffix.lower()
    if suffix in BINARY_READABLE_EXTENSIONS:
        size = await sandbox_file_size(session, sandbox_path)
        if suffix in IMAGE_READABLE_EXTENSIONS and 0 < size <= MAX_IMAGE_READ_BYTES:
            try:
                raw_img = await session.read_file_binary(sandbox_path)
                img_bytes = (
                    raw_img.encode("latin1")
                    if isinstance(raw_img, str)
                    else bytes(raw_img)
                )
                image_result = _build_image_read_result(
                    raw_bytes=img_bytes,
                    display_path=sandbox_path,
                    suffix=suffix,
                    size=size,
                    in_sandbox=True,
                )
                if image_result is not None:
                    return image_result
            except Exception:
                pass
        return ToolResult(
            output=(
                f"Binary file is readable in sandbox: {sandbox_path}\n"
                f"Type: {suffix or 'unknown'}\n"
                f"Size: {size} bytes\n"
                "Use deliver_artifact for user-needed files; read_file only returns text or image contents."
            ),
            metadata={"path": sandbox_path, "size_bytes": size, "binary": True, "workspace": "e2b"},
        )

    try:
        raw = await session.read_file_binary(sandbox_path)
    except Exception as exc:
        return ToolResult(output=f"Failed to read sandbox file {sandbox_path}: {exc}", is_error=True)
    data = bytes(raw) if isinstance(raw, (bytearray, memoryview)) else raw
    if isinstance(data, str):
        text = data
    else:
        if b"\x00" in data:
            if sniff_image_media_type(data) is not None and len(data) <= MAX_IMAGE_READ_BYTES:
                image_result = _build_image_read_result(
                    raw_bytes=data,
                    display_path=sandbox_path,
                    suffix=suffix,
                    size=len(data),
                    in_sandbox=True,
                )
                if image_result is not None:
                    return image_result
            return ToolResult(output=f"Binary file cannot be read as text in sandbox: {sandbox_path}", is_error=True)
        text = data.decode("utf-8", errors="replace")

    from openharness.tools.file_state import (
        bytes_version,
        format_read_window,
        observe_file,
        sandbox_observation_key,
    )

    lines = text.splitlines()
    window = format_read_window(
        lines,
        offset=arguments.offset,
        limit=arguments.limit,
        display_path=sandbox_path,
    )
    observe_file(context, sandbox_observation_key(sandbox_path), bytes_version(raw))
    return ToolResult(
        output=window.output,
        metadata={
            "path": sandbox_path,
            "workspace": "e2b",
            "total_lines": window.total_lines,
            "offset": arguments.offset,
            "lines_returned": window.lines_returned,
            "truncated": window.truncated,
            "truncated_by_bytes": window.truncated_by_bytes,
        },
    )
