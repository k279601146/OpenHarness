"""Host-side wrapper for the bundled imagegen CLI."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from openharness.tools.artifact_reference_guard import (
    looks_like_media_reuse_prompt,
    media_input_refs,
    wrong_media_type_error,
)
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.bash_tool import _build_provider_tool_env
from openharness.tools.media_gateway_runtime import run_media_subprocess
from openharness.tools.sandbox_workspace import get_e2b_task_session, to_sandbox_path, uses_e2b_task_workspace


GPT_IMAGE_2_MODEL = "gpt-image-2"
IMAGEGEN_METADATA_PREFIX = "IMAGEGEN_METADATA:"
IMAGEGEN_METADATA_PATH_ENV = "OPENHARNESS_IMAGEGEN_METADATA_PATH"


@dataclass(frozen=True)
class ImagegenCliCapabilities:
    n: bool = True
    resolution: bool = True
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
    resolution: str | None = Field(default=None, description="Image resolution tier such as 0.5K, 1K, 2K, or 4K.")
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
            return await _media_billing_error_result(context, f"imagegen CLI script not found: {script}")

        cwd = context.cwd.resolve()
        cwd.mkdir(parents=True, exist_ok=True)
        arguments = _apply_context_defaults(arguments, context)
        guard_error = _validate_image_artifact_inputs(arguments, context)
        if guard_error is not None:
            return guard_error
        if uses_e2b_task_workspace(context):
            return await _execute_e2b_imagegen(script, arguments, context, cwd)

        argv = _build_argv(script, arguments, cwd)
        env = os.environ.copy()
        env.update(_build_provider_tool_env(context) or {})

        with tempfile.TemporaryDirectory(prefix="openharness-imagegen-metadata-") as tmpdir:
            metadata_path = Path(tmpdir) / "metadata.json"
            env[IMAGEGEN_METADATA_PATH_ENV] = str(metadata_path)
            completed = await run_media_subprocess(
                argv=argv,
                cwd=str(cwd),
                env=env,
                timeout_seconds=arguments.timeout_seconds,
                context=context,
                kind="image",
            )
            file_metadata = _read_cli_metadata_file(metadata_path)
        output = completed.output.strip()
        if completed.returncode != 0:
            sanitized_error = _sanitize_cli_output(output, IMAGEGEN_METADATA_PREFIX, {})
            return await _media_billing_error_result(
                context,
                sanitized_error or f"imagegen CLI failed with code {completed.returncode}",
                {**file_metadata, **completed.metadata},
            )

        parsed_metadata = {**_parse_cli_metadata(output), **file_metadata, **completed.metadata}
        artifacts = [] if arguments.dry_run else _expected_artifacts(arguments, cwd, parsed_metadata)
        missing = [path for path in artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return await _media_billing_error_result(
                context,
                f"imagegen CLI completed, but expected output file(s) were missing:\n{missing_text}\n\n{_sanitize_cli_output(output, IMAGEGEN_METADATA_PREFIX, {})}",
                parsed_metadata,
            )

        billing_error, billing_metadata, finalized = await _finalize_media_artifacts(context, artifacts, parsed_metadata)
        if billing_error is not None:
            return billing_error

        hook = context.metadata.get("hook")
        if hook is not None and not finalized:
            artifact_metadata = context.metadata.get("media_artifact_metadata")
            artifact_metadata = artifact_metadata if isinstance(artifact_metadata, dict) else {}
            for artifact in artifacts:
                await _call_hook_on_artifact(
                    hook,
                    str(artifact),
                    reason=f"Generated image via imagegen CLI: {artifact.name}",
                    source_tool="imagegen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                    metadata={
                        **artifact_metadata,
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                )

        sanitized_output = _sanitize_cli_output(output, IMAGEGEN_METADATA_PREFIX, {})
        lines = [
            "imagegen CLI completed successfully and published artifact(s) to the UI.",
            "Delivery status: published; delivery_required=false. Do not call deliver_artifact for these image artifact(s) as standalone files; include them as members when the user requested a zip bundle.",
        ]
        if artifacts:
            lines.append("Published artifact paths:")
            lines.extend(f"- {path}" for path in artifacts)
        if sanitized_output:
            lines.extend(["", "CLI output:", sanitized_output])
        return ToolResult(
            output="\n".join(lines),
            metadata={
                **parsed_metadata,
                **billing_metadata,
                "artifact_paths": [str(path) for path in artifacts],
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )


def _requires_e2b_imagegen_session(
    arguments: ImagegenCliInput,
) -> bool:
    """Acquire E2B only when the host-side CLI must read task workspace inputs."""
    return bool(
        arguments.images
        or arguments.mask
        or arguments.input_file
        or arguments.command in {"edit", "generate-batch"}
    )


async def _execute_e2b_imagegen(
    script: Path,
    arguments: ImagegenCliInput,
    context: ToolExecutionContext,
    host_cwd: Path,
) -> ToolResult:
    session = None
    if _requires_e2b_imagegen_session(arguments):
        try:
            session = await get_e2b_task_session(context)
        except Exception as exc:
            return await _media_billing_error_result(context, f"E2B imagegen workspace error: {exc}")

    execution_workspace = "e2b" if session is not None else "host"

    if context.progress_callback is not None:
        await context.progress_callback(
            {
                "phase": "media_generate",
                "status": "running",
                "message": "正在生成图片...",
                "workspace": execution_workspace,
            }
        )

    with tempfile.TemporaryDirectory(prefix="openharness-imagegen-") as tmpdir:
        local_cwd = Path(tmpdir)
        try:
            local_arguments = await _prepare_e2b_arguments(arguments, context, session, local_cwd)
        except Exception as exc:
            return await _media_billing_error_result(context, f"Failed to prepare E2B imagegen inputs: {exc}")

        argv = _build_argv(script, local_arguments, local_cwd)
        env = os.environ.copy()
        env.update(_build_provider_tool_env(context) or {})
        metadata_path = local_cwd / "metadata.json"
        env[IMAGEGEN_METADATA_PATH_ENV] = str(metadata_path)

        completed = await run_media_subprocess(
            argv=argv,
            cwd=str(host_cwd),
            env=env,
            timeout_seconds=arguments.timeout_seconds,
            context=context,
            kind="image",
        )
        output = completed.output.strip()
        file_metadata = _read_cli_metadata_file(metadata_path)
        if completed.returncode != 0:
            sanitized_error = _sanitize_cli_output(output, IMAGEGEN_METADATA_PREFIX, {})
            return await _media_billing_error_result(
                context,
                sanitized_error or f"imagegen CLI failed with code {completed.returncode}",
                {**file_metadata, **completed.metadata},
            )

        parsed_metadata = {**_parse_cli_metadata(output), **file_metadata, **completed.metadata}
        local_artifacts = [] if arguments.dry_run else _expected_artifacts(local_arguments, local_cwd, parsed_metadata)
        missing = [path for path in local_artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return await _media_billing_error_result(context, f"imagegen CLI completed, but expected local output file(s) were missing:\n{missing_text}", parsed_metadata)

        billing_error, billing_metadata, finalized = await _finalize_media_artifacts(context, local_artifacts, parsed_metadata)
        if billing_error is not None:
            return billing_error

        hook = context.metadata.get("hook")
        if hook is not None and not finalized:
            artifact_metadata = context.metadata.get("media_artifact_metadata")
            artifact_metadata = artifact_metadata if isinstance(artifact_metadata, dict) else {}
            for local_path in local_artifacts:
                await _call_hook_on_artifact(
                    hook,
                    str(local_path),
                    reason=f"Generated image via imagegen CLI: {local_path.name}",
                    source_tool="imagegen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                    metadata={
                        **artifact_metadata,
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                )

        if context.progress_callback is not None and local_artifacts:
            await context.progress_callback(
                {
                    "phase": "artifact_ready",
                    "status": "success",
                    "message": "图片已生成并交付。",
                    "workspace": execution_workspace,
                    "detail": "\n".join(str(path) for path in local_artifacts),
                    "metadata": {
                        "artifact_paths": [str(path) for path in local_artifacts],
                        "publish_state": "published",
                        "published_artifact": True,
                        "delivery_required": False,
                        "do_not_deliver_artifact": True,
                    },
                }
            )

        sanitized_output = _sanitize_cli_output(output, IMAGEGEN_METADATA_PREFIX, {})
        lines = [
            "imagegen CLI completed successfully and published artifact(s) to the UI.",
            "Delivery status: published; delivery_required=false.",
        ]
        if local_artifacts:
            lines.append("Published artifact paths:")
            lines.extend(f"- {path}" for path in local_artifacts)
        if sanitized_output:
            lines.extend(["", "CLI output:", sanitized_output])
        return ToolResult(
            output="\n".join(lines),
            metadata={
                **parsed_metadata,
                **billing_metadata,
                "artifact_paths": [str(path) for path in local_artifacts],
                "workspace": execution_workspace,
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
    if capabilities.resolution:
        _add_value(argv, "--resolution", arguments.resolution)
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
    if _normalize_model_id(arguments.model) == GPT_IMAGE_2_MODEL and background == "opaque":
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


def _normalize_openai_sdk_base_url(base_url: str | None) -> str | None:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        return None
    return value if value.endswith("/v1") else f"{value}/v1"


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
    host_path = _existing_host_input_path(context, raw)
    if host_path is not None:
        suffix = host_path.suffix or ".bin"
        input_dir.mkdir(parents=True, exist_ok=True)
        local_path = input_dir / f"{stem}{suffix}"
        local_path.write_bytes(host_path.read_bytes())
        return str(local_path)

    sandbox_path = await _materialize_or_sandbox_path(session, context, raw)
    suffix = PurePosixPath(sandbox_path).suffix or ".bin"
    input_dir.mkdir(parents=True, exist_ok=True)
    local_path = input_dir / f"{stem}{suffix}"
    content = await session.read_file_binary(sandbox_path)
    local_path.write_bytes(_ensure_bytes(content))
    return str(local_path)


def _existing_host_input_path(context: ToolExecutionContext, raw: str) -> Path | None:
    value = str(raw or "").strip()
    if not value or _looks_like_artifact_reference(value):
        return None
    try:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = Path(context.cwd) / candidate
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    if not resolved.is_file():
        return None
    if not _is_allowed_host_input_path(context, resolved):
        raise ValueError(f"Host imagegen input is outside allowed roots: {resolved}")
    return resolved


def _is_allowed_host_input_path(context: ToolExecutionContext, path: Path) -> bool:
    resolved = path.resolve()
    return any(_is_relative_to_path(resolved, root) for root in _allowed_host_input_roots(context))


def _allowed_host_input_roots(context: ToolExecutionContext) -> list[Path]:
    roots = [Path(context.cwd).resolve()]

    extra_roots = context.metadata.get("allowed_host_input_roots")
    if isinstance(extra_roots, (list, tuple, set)):
        roots.extend(Path(str(root)).expanduser().resolve() for root in extra_roots if str(root).strip())

    project_root = Path(__file__).resolve().parents[4]
    web_public_root = project_root / "apps" / "web" / "public"
    artifacts_root = web_public_root / "artifacts"
    if artifacts_root.is_dir():
        roots.append(artifacts_root.resolve())
    user_id = context.metadata.get("user_id")
    if user_id is not None:
        uploads_root = web_public_root / "uploads" / str(user_id)
        if uploads_root.is_dir():
            roots.append(uploads_root.resolve())

    return roots


def _is_relative_to_path(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


async def _materialize_or_sandbox_path(session, context: ToolExecutionContext, raw: str) -> str:
    materializer = context.metadata.get("artifact_materializer")
    if callable(materializer):
        try:
            result = materializer(str(raw), sandbox_session=session)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("sandbox_path"):
                return str(result["sandbox_path"])
        except Exception:
            if _looks_like_artifact_reference(raw):
                raise
    return to_sandbox_path(context, raw)


def _looks_like_artifact_reference(raw: str) -> bool:
    value = str(raw or "").strip()
    return (
        value.startswith("artifact:")
        or value.startswith("/artifacts/")
        or value.startswith("artifacts/")
        or value.startswith("/uploads/")
        or value.startswith("uploads/")
        or "/api/v1/tasks/files" in value
    )


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
    image_refs = media_input_refs(context, "image")
    if image_refs and not arguments.images:
        if arguments.command == "edit":
            updates["images"] = image_refs
        elif arguments.command == "generate" and looks_like_media_reuse_prompt(arguments.prompt):
            updates["command"] = "edit"
            updates["images"] = image_refs
    if not updates:
        return arguments
    return arguments.model_copy(update=updates)


def _validate_image_artifact_inputs(arguments: ImagegenCliInput, context: ToolExecutionContext) -> ToolResult | None:
    if arguments.command != "edit" or arguments.images:
        return None
    if media_input_refs(context):
        return wrong_media_type_error(context, "image")
    return None


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


def _parse_cli_metadata(output: str) -> dict[str, object]:
    prefix = IMAGEGEN_METADATA_PREFIX
    for line in reversed((output or "").splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            parsed = json.loads(line[len(prefix):])
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _read_cli_metadata_file(path: Path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _context_tool_use_id(context: ToolExecutionContext) -> str | None:
    value = context.metadata.get("tool_use_id")
    return str(value) if value else None


async def _media_billing_error_result(
    context: ToolExecutionContext,
    output: str,
    metadata: dict[str, object] | None = None,
) -> ToolResult:
    billing_metadata = dict(metadata or {})
    if context.metadata.get("media_billing_defer_failure_release"):
        return ToolResult(output=output, is_error=True, metadata=billing_metadata)
    hook = context.metadata.get("hook")
    reservation = context.metadata.get("media_billing_reservation")
    if hook is not None and reservation and hasattr(hook, "release_media_tool_usage"):
        try:
            billing_metadata.update(
                hook.release_media_tool_usage(
                    reservation if isinstance(reservation, dict) else {},
                    reason="media_tool_failed",
                    tool_metadata={"error": output},
                )
            )
        except Exception as exc:
            return ToolResult(
                output=f"Media billing release failed after imagegen error: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata=billing_metadata,
            )
    return ToolResult(output=output, is_error=True, metadata=billing_metadata)


async def _finalize_media_artifacts(
    context: ToolExecutionContext,
    artifacts: list[Path],
    metadata: dict[str, object] | None = None,
) -> tuple[ToolResult | None, dict[str, object], bool]:
    billing_metadata = dict(metadata or {})
    hook = context.metadata.get("hook")
    reservation = context.metadata.get("media_billing_reservation")
    if hook is None or not reservation or not hasattr(hook, "commit_media_tool_usage"):
        return None, {}, False
    try:
        if hasattr(hook, "finalize_media_artifacts"):
            artifact_metadata = context.metadata.get("media_artifact_metadata")
            artifact_metadata = artifact_metadata if isinstance(artifact_metadata, dict) else {}
            settled = await hook.finalize_media_artifacts(
                reservation if isinstance(reservation, dict) else {},
                [
                    {
                        "file_path": str(artifact),
                        "reason": f"Generated image via imagegen CLI: {artifact.name}",
                        "source_tool": "imagegen_cli",
                        "tool_use_id": _context_tool_use_id(context),
                        "origin": "host_generated",
                        "metadata": {
                            **artifact_metadata,
                            "publish_state": "published",
                            "published_artifact": True,
                            "delivery_required": False,
                            "do_not_deliver_artifact": True,
                        },
                    }
                    for artifact in artifacts
                ],
                billing_metadata,
            )
            return None, settled if isinstance(settled, dict) else {}, True
        settled = hook.commit_media_tool_usage(reservation if isinstance(reservation, dict) else {}, billing_metadata)
        return None, settled if isinstance(settled, dict) else {}, False
    except Exception as exc:
        return (
            ToolResult(
                output=f"Media billing commit failed before image artifact publish: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata=billing_metadata,
            ),
            {},
            False,
        )


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
