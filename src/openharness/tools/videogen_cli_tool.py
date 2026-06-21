"""Host-side wrapper for the bundled videogen CLI."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.bash_tool import _build_forwarded_sandbox_env


class VideogenCliInput(BaseModel):
    """Arguments for running the bundled videogen CLI on the host."""

    command: Literal["generate", "image-to-video", "first-last-frame", "reference-to-video"] = Field(
        default="generate",
        description="Video generation mode.",
    )
    prompt: str | None = Field(default=None, description="Video prompt.")
    model: str | None = Field(default=None, description="Video model id. Uses the selected UI video model when omitted.")
    provider: str | None = Field(default=None, description="Optional provider hint; model id is preferred for routing.")
    images: list[str] = Field(default_factory=list, description="Input or reference images.")
    videos: list[str] = Field(default_factory=list, description="Input or reference videos for future providers.")
    first_frame: str | None = Field(default=None, description="First-frame image path.")
    last_frame: str | None = Field(default=None, description="Last-frame image path.")
    reference_files: list[str] = Field(default_factory=list, description="Reference image/video paths.")
    duration_seconds: int | None = Field(default=None, ge=1, le=60)
    aspect_ratio: str | None = Field(default=None, description="Aspect ratio such as 16:9, 9:16, or 1:1.")
    resolution: str | None = Field(default=None, description="Resolution such as 720p, 1080p, or 4k.")
    quality: str | None = Field(default=None)
    mode: str | None = Field(default=None)
    generate_audio: bool = False
    n: int = Field(default=1, ge=1, le=4)
    num_videos: int | None = Field(default=None, ge=1, le=4, description="Alias for n.")
    out: str = Field(default="output/videogen/output.mp4", description="Output video file path.")
    out_dir: str | None = Field(default=None, description="Output directory for multiple videos.")
    dry_run: bool = False
    force: bool = False
    timeout_seconds: int = Field(default=900, ge=1, le=1800)


class VideogenCliTool(BaseTool):
    """Run the videogen skill's bundled CLI on the host and publish artifacts."""

    name = "videogen_cli"
    description = (
        "Run the bundled videogen scripts/video_gen.py CLI on the host. Use this after "
        "loading the videogen skill; it routes Seedance, Veo/video3, and Kling/keling "
        "models and publishes generated videos as artifacts."
    )
    input_model = VideogenCliInput
    requires_sandbox = False

    async def execute(self, arguments: VideogenCliInput, context: ToolExecutionContext) -> ToolResult:
        script = _script_path()
        if not script.is_file():
            return ToolResult(output=f"videogen CLI script not found: {script}", is_error=True)

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
                output=f"videogen CLI timed out after {arguments.timeout_seconds}s.\n{output}".strip(),
                is_error=True,
            )

        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            return ToolResult(output=output or f"videogen CLI failed with code {completed.returncode}", is_error=True)

        parsed_metadata = _parse_cli_metadata(output)
        artifacts = [] if arguments.dry_run else _expected_artifacts(arguments, cwd, parsed_metadata)
        missing = [path for path in artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return ToolResult(
                output=f"videogen CLI completed, but expected output file(s) were missing:\n{missing_text}\n\n{output}",
                is_error=True,
            )

        hook = context.metadata.get("hook")
        if hook is not None:
            for artifact in artifacts:
                await hook.on_artifact(
                    str(artifact),
                    reason=f"Generated video via videogen CLI: {artifact.name}",
                )

        lines = ["videogen CLI completed successfully."]
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
        / "videogen"
        / "scripts"
        / "video_gen.py"
    )


def _build_argv(script: Path, arguments: VideogenCliInput, cwd: Path) -> list[str]:
    argv = [sys.executable, str(script), arguments.command]
    _add_value(argv, "--model", arguments.model)
    _add_value(argv, "--provider", arguments.provider)
    _add_value(argv, "--duration-seconds", str(arguments.duration_seconds) if arguments.duration_seconds else None)
    _add_value(argv, "--aspect-ratio", arguments.aspect_ratio)
    _add_value(argv, "--resolution", arguments.resolution)
    _add_value(argv, "--quality", arguments.quality)
    _add_value(argv, "--mode", arguments.mode)
    _add_value(argv, "--n", str(arguments.num_videos or arguments.n))
    _add_value(argv, "--out", _as_cli_path(arguments.out, cwd))
    _add_value(argv, "--out-dir", _as_cli_path(arguments.out_dir, cwd) if arguments.out_dir else None)
    if arguments.prompt:
        _add_value(argv, "--prompt", arguments.prompt)
    for image in arguments.images:
        _add_value(argv, "--image", _as_cli_path(image, cwd))
    for video in arguments.videos:
        _add_value(argv, "--video", _as_cli_path(video, cwd))
    _add_value(argv, "--first-frame", _as_cli_path(arguments.first_frame, cwd) if arguments.first_frame else None)
    _add_value(argv, "--last-frame", _as_cli_path(arguments.last_frame, cwd) if arguments.last_frame else None)
    for ref in arguments.reference_files:
        _add_value(argv, "--reference-file", _as_cli_path(ref, cwd))
    if arguments.generate_audio:
        argv.append("--generate-audio")
    if arguments.force:
        argv.append("--force")
    if arguments.dry_run:
        argv.append("--dry-run")
    return argv


def _apply_context_defaults(arguments: VideogenCliInput, context: ToolExecutionContext) -> VideogenCliInput:
    updates: dict[str, object] = {}
    media_preferences = context.metadata.get("media_preferences")
    if not arguments.model and isinstance(media_preferences, dict) and not media_preferences.get("is_auto", True):
        preferred_model = str(media_preferences.get("video_model") or "").strip()
        if preferred_model:
            updates["model"] = preferred_model
    if not arguments.model and "model" not in updates:
        updates["model"] = "doubao-seedance-2-0-260128"
    if arguments.num_videos is not None:
        updates["n"] = arguments.num_videos
    return arguments.model_copy(update=updates) if updates else arguments


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


def _expected_artifacts(arguments: VideogenCliInput, cwd: Path, metadata: dict[str, object] | None = None) -> list[Path]:
    if metadata:
        paths = metadata.get("artifact_paths")
        if isinstance(paths, list):
            resolved = [Path(str(path)).expanduser() for path in paths if str(path).strip()]
            return [path if path.is_absolute() else (cwd / path).resolve() for path in resolved]
    return _build_output_paths(arguments.out, arguments.num_videos or arguments.n, arguments.out_dir, cwd)


def _build_output_paths(out: str, count: int, out_dir: str | None, cwd: Path) -> list[Path]:
    if out_dir:
        out_base = Path(_as_cli_path(out_dir, cwd) or out_dir)
        return [out_base / f"video_{index}.mp4" for index in range(1, count + 1)]
    out_path = Path(_as_cli_path(out, cwd) or out)
    if out_path.exists() and out_path.is_dir():
        return [out_path / f"video_{index}.mp4" for index in range(1, count + 1)]
    if out_path.suffix == "":
        out_path = out_path.with_suffix(".mp4")
    if count == 1:
        return [out_path]
    return [out_path.with_name(f"{out_path.stem}-{index}{out_path.suffix}") for index in range(1, count + 1)]


def _parse_cli_metadata(output: str) -> dict[str, object]:
    prefix = "VIDEOGEN_METADATA:"
    for line in reversed((output or "").splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            parsed = json.loads(line[len(prefix):])
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
