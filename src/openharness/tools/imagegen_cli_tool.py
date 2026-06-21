"""Host-side wrapper for the bundled imagegen CLI."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.bash_tool import _build_forwarded_sandbox_env


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
        argv = _build_argv(script, arguments, cwd)
        env = os.environ.copy()
        env.update(_build_forwarded_sandbox_env(context) or {})

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
                await hook.on_artifact(
                    str(artifact),
                    reason=f"Generated image via imagegen CLI: {artifact.name}",
                )

        lines = ["imagegen CLI completed successfully."]
        if artifacts:
            lines.append("Artifacts:")
            lines.extend(f"- {path}" for path in artifacts)
        if output:
            lines.extend(["", "CLI output:", output])
        return ToolResult(
            output="\n".join(lines),
            metadata={
                **parsed_metadata,
                "artifact_paths": [str(path) for path in artifacts],
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
    argv = [sys.executable, str(script), arguments.command]

    _add_value(argv, "--model", arguments.model)
    _add_value(argv, "--n", str(arguments.num_images or arguments.n))
    _add_value(argv, "--size", arguments.size)
    _add_value(argv, "--aspect-ratio", arguments.aspect_ratio)
    _add_value(argv, "--quality", arguments.quality)
    _add_value(argv, "--output-format", arguments.output_format)
    _add_value(argv, "--out", _as_cli_path(arguments.out, cwd))
    _add_value(argv, "--out-dir", _as_cli_path(arguments.out_dir, cwd) if arguments.out_dir else None)
    _add_value(argv, "--background", arguments.background)
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
        _add_value(argv, "--mask", _as_cli_path(arguments.mask, cwd) if arguments.mask else None)
        _add_value(argv, "--input-fidelity", arguments.input_fidelity)
    elif arguments.command == "generate-batch":
        _add_value(argv, "--input", _as_cli_path(arguments.input_file, cwd) if arguments.input_file else None)

    return argv


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
