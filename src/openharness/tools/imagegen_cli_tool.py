"""Host-side wrapper for the bundled imagegen CLI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.bash_tool import _build_provider_tool_env
from openharness.tools.sandbox_workspace import get_e2b_task_session, to_sandbox_path, uses_e2b_task_workspace


GPT_IMAGE_2_MODEL = "gpt-image-2"


@dataclass(frozen=True)
class ImagegenCliCapabilities:
    n: bool = True
    size: bool = True
    aspect_ratio: bool = False
    quality: bool = False
    background: bool = False
    transparent_background: bool = False
    output_format: bool = False
    output_compression: bool = False
    moderation: bool = False
    input_fidelity: bool = False
    mask: bool = False


class ImagegenCliInput(BaseModel):
    """Arguments for running the bundled imagegen CLI on the host."""

    command: Literal["generate", "edit", "generate-batch"] = Field(
        default="generate",
        description="CLI subcommand to run.",
    )
    prompt: str | None = Field(default=None, description="Text prompt for generate/edit.")
    images: list[str] = Field(default_factory=list, description="Source images for edit.")
    mask: str | None = Field(default=None, description="Optional mask image for edit.")
    input_file: str | None = Field(default=None, description="JSONL input file for generate-batch.")
    out: str = Field(default="output/imagegen/output.png", description="Output file path.")
    out_dir: str | None = Field(default=None, description="Output directory for multiple images or batch jobs.")
    model: str | None = Field(default=None, description="Image model id. Uses the selected UI image model when omitted.")
    provider: str | None = Field(default=None, description="Optional provider hint; model id is preferred for routing.")
    n: int = Field(default=1, ge=1, le=10)
    num_images: int | None = Field(default=None, ge=1, le=10, description="Alias for n.")
    size: str = Field(default="auto")
    aspect_ratio: str | None = Field(default=None, description="Aspect ratio such as 1:1, 16:9, 9:16, 4:3, or 3:4.")
    quality: str = Field(default="medium")
    background: Literal["transparent", "opaque", "auto"] | None = Field(
        default=None,
        description="Image API background mode. Only use transparent, opaque, or auto; visual scene backgrounds belong in prompt/scene.",
    )
    output_format: str = Field(default="png")
    output_compression: int | None = Field(default=None, ge=0, le=100)
    moderation: str | None = Field(default=None)
    input_fidelity: str | None = Field(default=None)
    use_case: str | None = None
    scene: str | None = None
    subject: str | None = None
    style: str | None = None
    composition: str | None = None
    lighting: str | None = None
    palette: str | None = None
    materials: str | None = None
    text: str | None = None
    constraints: str | None = None
    negative: str | None = None
    dry_run: bool = False
    force: bool = False
    timeout_seconds: int = Field(default=600, ge=1, le=900)

    @field_validator("background", mode="before")
    @classmethod
    def normalize_background(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"", "none", "null", "default", "unspecified"}:
                return None
            if normalized in {"transparent", "opaque", "auto"}:
                return normalized
        return value


class ImagegenCliTool(BaseTool):
    """Run the imagegen skill's bundled CLI on the host and publish artifacts."""

    name = "imagegen_cli"
    description = (
        "Run the bundled imagegen scripts/image_gen.py CLI on the host. Use this after "
        "loading the imagegen skill; it avoids E2B dependency installation and publishes "
        "generated images as artifacts."
    )
    input_model = ImagegenCliInput
    requires_sandbox = False

    async def execute(self, arguments: ImagegenCliInput, context: ToolExecutionContext) -> ToolResult:
        script = _script_path()
        if not script.is_file():
            return ToolResult(output=f"imagegen CLI script not found: {script}", is_error=True)

        cwd = context.cwd.resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        arguments = _apply_context_defaults(arguments, context)
        if uses_e2b_task_workspace(context):
            return await _execute_e2b_imagegen(script, arguments, context, cwd)

        argv = _build_argv(script, arguments, cwd)
        env = os.environ.copy()
        env.update(_build_provider_tool_env(context) or {})

        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                cwd=str(cwd),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=arguments.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "").strip()
            return ToolResult(
                output=f"imagegen CLI timed out after {arguments.timeout_seconds}s.\n{output}".strip(),
                is_error=True,
            )

        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            return ToolResult(output=output or f"imagegen CLI failed with code {completed.returncode}", is_error=True)

        parsed_metadata = _parse_cli_metadata(output)
        artifacts = [] if arguments.dry_run else _expected_artifacts(arguments, cwd, parsed_metadata)
        missing = [path for path in artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return ToolResult(
                output=f"imagegen CLI completed, but expected output file(s) were missing:\n{missing_text}\n\n{output}",
                is_error=True,
            )

        hook = context.metadata.get("hook")
        if hook is not None:
            for artifact in artifacts:
                await _call_hook_on_artifact(
                    hook,
                    str(artifact),
                    reason=f"Generated image via imagegen CLI: {artifact.name}",
                    source_tool="imagegen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                    metadata={
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                )

        lines = [
            "imagegen CLI completed successfully and published artifact(s) to the UI.",
            "Delivery status: published; delivery_required=false. Do not call deliver_artifact for these image artifact(s) as standalone files; include them as members when the user requested a zip bundle.",
        ]
        if artifacts:
            lines.append("Published artifact paths:")
            lines.extend(f"- {path}" for path in artifacts)
        if output:
            lines.extend(["", "CLI output:", output])
        return ToolResult(
            output="\n".join(lines),
            metadata={
                **parsed_metadata,
                "artifact_paths": [str(path) for path in artifacts],
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )


async def _execute_e2b_imagegen(
    script: Path,
    arguments: ImagegenCliInput,
    context: ToolExecutionContext,
    host_cwd: Path,
) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_artifacts = _expected_sandbox_artifacts(arguments, context)
    except Exception as exc:
        return ToolResult(output=f"E2B imagegen workspace error: {exc}", is_error=True)

    if context.progress_callback is not None:
        await context.progress_callback(
            {
                "phase": "media_generate",
                "status": "running",
                "message": "正在生成图片...",
                "workspace": "e2b",
                "path": sandbox_artifacts[0] if sandbox_artifacts else None,
            }
        )

    with tempfile.TemporaryDirectory(prefix="openharness-imagegen-") as tmpdir:
        local_cwd = Path(tmpdir)
        try:
            local_arguments = await _prepare_e2b_arguments(arguments, context, session, local_cwd)
        except Exception as exc:
            return ToolResult(output=f"Failed to prepare E2B imagegen inputs: {exc}", is_error=True)

        argv = _build_argv(script, local_arguments, local_cwd)
        env = os.environ.copy()
        env.update(_build_provider_tool_env(context) or {})

        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                cwd=str(host_cwd),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=arguments.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "").strip()
            return ToolResult(
                output=f"imagegen CLI timed out after {arguments.timeout_seconds}s.\n{output}".strip(),
                is_error=True,
            )

        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            return ToolResult(output=output or f"imagegen CLI failed with code {completed.returncode}", is_error=True)

        parsed_metadata = _parse_cli_metadata(output)
        local_artifacts = [] if arguments.dry_run else _expected_artifacts(local_arguments, local_cwd, parsed_metadata)
        delivered_sandbox_artifacts = sandbox_artifacts if local_artifacts else []
        missing = [path for path in local_artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return ToolResult(
                output=f"imagegen CLI completed, but expected local output file(s) were missing:\n{missing_text}",
                is_error=True,
            )
        if len(sandbox_artifacts) != len(local_artifacts):
            sandbox_artifacts = _align_sandbox_artifacts(sandbox_artifacts, local_artifacts, context)
            delivered_sandbox_artifacts = sandbox_artifacts if local_artifacts else []

        if context.progress_callback is not None and local_artifacts:
            await context.progress_callback(
                {
                    "phase": "artifact_sync",
                    "status": "running",
                    "message": "正在同步图片到 E2B 沙箱...",
                    "workspace": "e2b",
                    "detail": "\n".join(sandbox_artifacts),
                }
            )

        for local_path, sandbox_path in zip(local_artifacts, sandbox_artifacts):
            await session.exec_command(f"mkdir -p {_shell_quote(posixpath.dirname(sandbox_path) or '/home/user')}")
            await session.write_file_binary(sandbox_path, local_path.read_bytes())

        hook = context.metadata.get("hook")
        if hook is not None:
            for local_path, sandbox_path in zip(local_artifacts, sandbox_artifacts):
                await _call_hook_on_artifact(
                    hook,
                    str(local_path),
                    reason=f"Generated image via imagegen CLI: {local_path.name}",
                    source_tool="imagegen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                    sandbox_path=sandbox_path,
                    sandbox_path_role="workspace_mirror",
                    metadata={
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                )

        if context.progress_callback is not None and delivered_sandbox_artifacts:
            await context.progress_callback(
                {
                    "phase": "artifact_ready",
                    "status": "success",
                    "message": "图片已生成并交付，副本已同步到 E2B 工作区。",
                    "workspace": "e2b",
                    "detail": "\n".join(delivered_sandbox_artifacts),
                    "metadata": {
                        "artifact_paths": delivered_sandbox_artifacts,
                        "sandbox_path_role": "workspace_mirror",
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                }
            )

        sanitized_output = _sanitize_cli_output(output, "IMAGEGEN_METADATA:", dict(zip(local_artifacts, sandbox_artifacts)))
        lines = [
            "imagegen CLI completed successfully and published artifact(s) to the UI.",
            "Delivery status: published; delivery_required=false.",
            "The E2B paths below are workspace mirrors for later editing. Do not call deliver_artifact for them as standalone files; include them as members when the user requested a zip bundle.",
        ]
        if delivered_sandbox_artifacts:
            lines.append("E2B workspace mirror paths:")
            lines.extend(f"- {path}" for path in delivered_sandbox_artifacts)
        if sanitized_output:
            lines.extend(["", "CLI output:", sanitized_output])
        return ToolResult(
            output="\n".join(lines),
            metadata={
                **parsed_metadata,
                "artifact_paths": delivered_sandbox_artifacts,
                "workspace": "e2b",
                "sandbox_path_role": "workspace_mirror",
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "bundled"
        / "content"
        / "imagegen"
        / "scripts"
        / "image_gen.py"
    )


def _build_argv(script: Path, arguments: ImagegenCliInput, cwd: Path) -> list[str]:
    capabilities = _capabilities_for_model(arguments.model)
    argv = [sys.executable, str(script), arguments.command]

    _add_value(argv, "--model", arguments.model)
    if capabilities.n:
        _add_value(argv, "--n", str(arguments.num_images or arguments.n))
    if capabilities.size:
        _add_value(argv, "--size", arguments.size)
    if capabilities.aspect_ratio:
        _add_value(argv, "--aspect-ratio", arguments.aspect_ratio)
    if capabilities.quality:
        _add_value(argv, "--quality", arguments.quality)
    if capabilities.output_format:
        _add_value(argv, "--output-format", arguments.output_format)
    if capabilities.output_compression and _supports_output_compression(arguments.output_format):
        _add_value(argv, "--output-compression", str(arguments.output_compression) if arguments.output_compression is not None else None)
    if capabilities.moderation:
        _add_value(argv, "--moderation", arguments.moderation)
    _add_value(argv, "--out", _as_cli_path(arguments.out, cwd))
    _add_value(argv, "--out-dir", _as_cli_path(arguments.out_dir, cwd) if arguments.out_dir else None)
    background = arguments.background
    if background == "transparent" and not capabilities.transparent_background:
        background = None
    if capabilities.background:
        _add_value(argv, "--background", background)
    _add_value(argv, "--use-case", arguments.use_case)
    _add_value(argv, "--scene", arguments.scene)
    _add_value(argv, "--subject", arguments.subject)
    _add_value(argv, "--style", arguments.style)
    _add_value(argv, "--composition", arguments.composition)
    _add_value(argv, "--lighting", arguments.lighting)
    _add_value(argv, "--palette", arguments.palette)
    _add_value(argv, "--materials", arguments.materials)
    _add_value(argv, "--text", arguments.text)
    _add_value(argv, "--constraints", arguments.constraints)
    _add_value(argv, "--negative", arguments.negative)

    if arguments.prompt:
        _add_value(argv, "--prompt", arguments.prompt)
    if arguments.force:
        argv.append("--force")
    if arguments.dry_run:
        argv.append("--dry-run")

    if arguments.command == "edit":
        for image in arguments.images:
            _add_value(argv, "--image", _as_cli_path(image, cwd))
        if capabilities.mask:
            _add_value(argv, "--mask", _as_cli_path(arguments.mask, cwd) if arguments.mask else None)
        if capabilities.input_fidelity:
            _add_value(argv, "--input-fidelity", arguments.input_fidelity)
    elif arguments.command == "generate-batch":
        _add_value(argv, "--input", _as_cli_path(arguments.input_file, cwd) if arguments.input_file else None)

    return argv


def _capabilities_for_model(model: str | None) -> ImagegenCliCapabilities:
    normalized = _normalize_model_id(model)
    if normalized.startswith("gpt-image-"):
        supports_gpt_image_2_only = normalized == GPT_IMAGE_2_MODEL or normalized.startswith(f"{GPT_IMAGE_2_MODEL}-")
        return ImagegenCliCapabilities(
            n=True,
            size=True,
            quality=True,
            background=True,
            transparent_background=not supports_gpt_image_2_only,
            output_format=True,
            output_compression=True,
            moderation=True,
            input_fidelity=not supports_gpt_image_2_only,
            mask=True,
        )
    if "banana" in normalized or "gemini" in normalized:
        return ImagegenCliCapabilities(
            n=False,
            size=True,
            aspect_ratio=True,
        )
    if "doubao" in normalized or "seedream" in normalized:
        return ImagegenCliCapabilities(
            n=True,
            size=True,
            aspect_ratio=True,
        )
    return ImagegenCliCapabilities(
        n=True,
        size=True,
        aspect_ratio=True,
    )


def _normalize_model_id(model: str | None) -> str:
    normalized = (model or GPT_IMAGE_2_MODEL).strip().lower()
    if normalized in {"", "auto", "default"}:
        return GPT_IMAGE_2_MODEL
    return normalized


def _supports_output_compression(output_format: str | None) -> bool:
    return (output_format or "").strip().lower() in {"jpeg", "jpg", "webp"}


async def _prepare_e2b_arguments(
    arguments: ImagegenCliInput,
    context: ToolExecutionContext,
    session,
    local_cwd: Path,
) -> ImagegenCliInput:
    updates: dict[str, object] = {}
    input_dir = local_cwd / "inputs"
    output_dir = local_cwd / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    if arguments.images:
        updates["images"] = [
            await _copy_sandbox_input(session, context, raw, input_dir, f"image_{index}")
            for index, raw in enumerate(arguments.images, start=1)
        ]
    if arguments.mask:
        updates["mask"] = await _copy_sandbox_input(session, context, arguments.mask, input_dir, "mask")
    if arguments.input_file:
        updates["input_file"] = await _copy_sandbox_input(session, context, arguments.input_file, input_dir, "batch_input")

    if arguments.out_dir:
        updates["out_dir"] = str(output_dir)
        updates["out"] = "image.png"
    else:
        sandbox_paths = _expected_sandbox_artifacts(arguments, context)
        suffix = Path(sandbox_paths[0]).suffix if sandbox_paths else ".png"
        updates["out"] = str(output_dir / f"imagegen_output{suffix or '.png'}")

    return arguments.model_copy(update=updates)


async def _copy_sandbox_input(session, context: ToolExecutionContext, raw: str, input_dir: Path, stem: str) -> str:
    sandbox_path = to_sandbox_path(context, raw)
    suffix = PurePosixPath(sandbox_path).suffix or ".bin"
    input_dir.mkdir(parents=True, exist_ok=True)
    local_path = input_dir / f"{stem}{suffix}"
    content = await session.read_file_binary(sandbox_path)
    local_path.write_bytes(_ensure_bytes(content))
    return str(local_path)


def _apply_context_defaults(arguments: ImagegenCliInput, context: ToolExecutionContext) -> ImagegenCliInput:
    updates: dict[str, object] = {}
    media_preferences = context.metadata.get("media_preferences")
    if not arguments.model and isinstance(media_preferences, dict) and not media_preferences.get("is_auto", True):
        preferred_model = str(media_preferences.get("image_model") or "").strip()
        if preferred_model:
            updates["model"] = preferred_model
    if not arguments.model and "model" not in updates:
        updates["model"] = "gpt-image-2"
    if arguments.num_images is not None:
        updates["n"] = arguments.num_images
    if not updates:
        return arguments
    return arguments.model_copy(update=updates)


def _add_value(argv: list[str], flag: str, value: str | None) -> None:
    if value is None or value == "":
        return
    argv.extend([flag, value])


def _as_cli_path(raw: str | None, cwd: Path) -> str | None:
    if raw is None:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path)
    return str((cwd / path).resolve())


def _expected_artifacts(arguments: ImagegenCliInput, cwd: Path, metadata: dict[str, object] | None = None) -> list[Path]:
    if metadata:
        paths = metadata.get("artifact_paths")
        if isinstance(paths, list):
            resolved = [Path(str(path)).expanduser() for path in paths if str(path).strip()]
            return [path if path.is_absolute() else (cwd / path).resolve() for path in resolved]
    output_format = (arguments.output_format or "png").lower()
    if output_format == "jpg":
        output_format = "jpeg"

    if arguments.command == "generate-batch":
        if not arguments.out_dir:
            return []
        out_dir = Path(_as_cli_path(arguments.out_dir, cwd) or arguments.out_dir)
        return sorted(
            path for path in out_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        )

    return _build_output_paths(arguments.out, output_format, arguments.num_images or arguments.n, arguments.out_dir, cwd)


def _build_output_paths(out: str, output_format: str, count: int, out_dir: str | None, cwd: Path) -> list[Path]:
    ext = "." + output_format
    if out_dir:
        out_base = Path(_as_cli_path(out_dir, cwd) or out_dir)
        return [out_base / f"image_{i}{ext}" for i in range(1, count + 1)]

    out_path = Path(_as_cli_path(out, cwd) or out)
    if out_path.exists() and out_path.is_dir():
        return [out_path / f"image_{i}{ext}" for i in range(1, count + 1)]

    if out_path.suffix == "":
        out_path = out_path.with_suffix(ext)

    if count == 1:
        return [out_path]
    return [out_path.with_name(f"{out_path.stem}-{i}{out_path.suffix}") for i in range(1, count + 1)]


def _expected_sandbox_artifacts(arguments: ImagegenCliInput, context: ToolExecutionContext) -> list[str]:
    output_format = (arguments.output_format or "png").lower()
    if output_format == "jpg":
        output_format = "jpeg"
    return _build_sandbox_output_paths(
        arguments.out,
        output_format,
        arguments.num_images or arguments.n,
        arguments.out_dir,
        context,
    )


def _build_sandbox_output_paths(
    out: str,
    output_format: str,
    count: int,
    out_dir: str | None,
    context: ToolExecutionContext,
) -> list[str]:
    ext = "." + output_format
    if out_dir:
        out_base = to_sandbox_path(context, out_dir, for_write=True)
        return [posixpath.join(out_base, f"image_{i}{ext}") for i in range(1, count + 1)]

    out_path = to_sandbox_path(context, out, for_write=True)
    suffix = PurePosixPath(out_path).suffix
    if not suffix:
        out_path = f"{out_path}{ext}"
    if count == 1:
        return [out_path]
    parsed = PurePosixPath(out_path)
    return [
        posixpath.join(str(parsed.parent), f"{parsed.stem}-{i}{parsed.suffix}")
        for i in range(1, count + 1)
    ]


def _align_sandbox_artifacts(
    sandbox_artifacts: list[str],
    local_artifacts: list[Path],
    context: ToolExecutionContext,
) -> list[str]:
    if len(sandbox_artifacts) == len(local_artifacts):
        return sandbox_artifacts
    if sandbox_artifacts:
        base_dir = posixpath.dirname(sandbox_artifacts[0])
    else:
        base_dir = to_sandbox_path(context, "output/imagegen", for_write=True)
    return [posixpath.join(base_dir, local_path.name) for local_path in local_artifacts]


def _sanitize_cli_output(output: str, metadata_prefix: str, path_map: dict[Path, str]) -> str:
    if not output:
        return ""
    replacements: dict[str, str] = {}
    for local_path, sandbox_path in path_map.items():
        replacements[str(local_path)] = sandbox_path
        replacements[local_path.as_posix()] = sandbox_path

    lines: list[str] = []
    for line in output.splitlines():
        if line.startswith(metadata_prefix):
            try:
                parsed = json.loads(line[len(metadata_prefix):])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                parsed["artifact_paths"] = list(path_map.values())
                lines.append(f"{metadata_prefix}{json.dumps(parsed, ensure_ascii=False, sort_keys=True)}")
            continue
        sanitized = line
        for host_path, sandbox_path in replacements.items():
            sanitized = sanitized.replace(host_path, sandbox_path)
        lines.append(sanitized)
    return "\n".join(lines).strip()


def _ensure_bytes(content) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray):
        return bytes(content)
    if isinstance(content, memoryview):
        return content.tobytes()
    if isinstance(content, str):
        return content.encode("utf-8")
    return bytes(content)


def _shell_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def _parse_cli_metadata(output: str) -> dict[str, object]:
    prefix = "IMAGEGEN_METADATA:"
    for line in reversed((output or "").splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            parsed = json.loads(line[len(prefix):])
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _context_tool_use_id(context: ToolExecutionContext) -> str | None:
    value = context.metadata.get("tool_use_id")
    return str(value) if value else None


async def _call_hook_on_artifact(hook, file_path: str, **kwargs) -> None:
    try:
        await hook.on_artifact(file_path, **kwargs)
    except TypeError:
        legacy_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in {"reason", "sandbox_session", "url"}
        }
        await hook.on_artifact(file_path, **legacy_kwargs)
