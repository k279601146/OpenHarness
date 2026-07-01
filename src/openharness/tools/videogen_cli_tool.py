"""Host-side wrapper for the bundled videogen CLI."""

from __future__ import annotations

import asyncio
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.bash_tool import _build_provider_tool_env
from openharness.tools.sandbox_workspace import get_e2b_task_session, to_sandbox_path, uses_e2b_task_workspace


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
        if uses_e2b_task_workspace(context):
            return await _execute_e2b_videogen(script, arguments, context, cwd)

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
                await _call_hook_on_artifact(
                    hook,
                    str(artifact),
                    reason=f"Generated video via videogen CLI: {artifact.name}",
                    source_tool="videogen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                )

        lines = ["videogen CLI completed successfully and published artifact(s)."]
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


async def _execute_e2b_videogen(
    script: Path,
    arguments: VideogenCliInput,
    context: ToolExecutionContext,
    host_cwd: Path,
) -> ToolResult:
    try:
        session = await get_e2b_task_session(context)
        sandbox_artifacts = _expected_sandbox_artifacts(arguments, context)
    except Exception as exc:
        return ToolResult(output=f"E2B videogen workspace error: {exc}", is_error=True)

    if context.progress_callback is not None:
        await context.progress_callback(
            {
                "phase": "media_generate",
                "status": "running",
                "message": "正在生成视频...",
                "workspace": "e2b",
                "path": sandbox_artifacts[0] if sandbox_artifacts else None,
            }
        )

    with tempfile.TemporaryDirectory(prefix="openharness-videogen-") as tmpdir:
        local_cwd = Path(tmpdir)
        try:
            local_arguments = await _prepare_e2b_arguments(arguments, context, session, local_cwd)
        except Exception as exc:
            return ToolResult(output=f"Failed to prepare E2B videogen inputs: {exc}", is_error=True)

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
                output=f"videogen CLI timed out after {arguments.timeout_seconds}s.\n{output}".strip(),
                is_error=True,
            )

        output = (completed.stdout or "").strip()
        if completed.returncode != 0:
            return ToolResult(output=output or f"videogen CLI failed with code {completed.returncode}", is_error=True)

        parsed_metadata = _parse_cli_metadata(output)
        local_artifacts = [] if arguments.dry_run else _expected_artifacts(local_arguments, local_cwd, parsed_metadata)
        delivered_sandbox_artifacts = sandbox_artifacts if local_artifacts else []
        missing = [path for path in local_artifacts if not path.is_file()]
        if missing:
            missing_text = "\n".join(f"- {path}" for path in missing)
            return ToolResult(
                output=f"videogen CLI completed, but expected local output file(s) were missing:\n{missing_text}",
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
                    "message": "正在同步视频到 E2B 沙箱...",
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
                    reason=f"Generated video via videogen CLI: {local_path.name}",
                    source_tool="videogen_cli",
                    tool_use_id=_context_tool_use_id(context),
                    origin="host_generated",
                    sandbox_path=sandbox_path,
                    sandbox_path_role="workspace_mirror",
                )

        if context.progress_callback is not None and delivered_sandbox_artifacts:
            await context.progress_callback(
                {
                    "phase": "artifact_ready",
                    "status": "success",
                    "message": "视频已生成并交付，副本已同步到 E2B 工作区。",
                    "workspace": "e2b",
                    "detail": "\n".join(delivered_sandbox_artifacts),
                    "metadata": {
                        "artifact_paths": delivered_sandbox_artifacts,
                        "sandbox_path_role": "workspace_mirror",
                    },
                }
            )

        sanitized_output = _sanitize_cli_output(output, "VIDEOGEN_METADATA:", dict(zip(local_artifacts, sandbox_artifacts)))
        lines = ["videogen CLI completed successfully and published artifact(s)."]
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


async def _prepare_e2b_arguments(
    arguments: VideogenCliInput,
    context: ToolExecutionContext,
    session,
    local_cwd: Path,
) -> VideogenCliInput:
    updates: dict[str, object] = {}
    input_dir = local_cwd / "inputs"
    output_dir = local_cwd / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    if arguments.images:
        updates["images"] = [
            await _copy_sandbox_input(session, context, raw, input_dir, f"image_{index}")
            for index, raw in enumerate(arguments.images, start=1)
        ]
    if arguments.videos:
        updates["videos"] = [
            await _copy_sandbox_input(session, context, raw, input_dir, f"video_{index}")
            for index, raw in enumerate(arguments.videos, start=1)
        ]
    if arguments.first_frame:
        updates["first_frame"] = await _copy_sandbox_input(session, context, arguments.first_frame, input_dir, "first_frame")
    if arguments.last_frame:
        updates["last_frame"] = await _copy_sandbox_input(session, context, arguments.last_frame, input_dir, "last_frame")
    if arguments.reference_files:
        updates["reference_files"] = [
            await _copy_sandbox_input(session, context, raw, input_dir, f"reference_{index}")
            for index, raw in enumerate(arguments.reference_files, start=1)
        ]

    if arguments.out_dir:
        updates["out_dir"] = str(output_dir)
        updates["out"] = "video.mp4"
    else:
        updates["out"] = str(output_dir / "videogen_output.mp4")

    return arguments.model_copy(update=updates)


async def _copy_sandbox_input(session, context: ToolExecutionContext, raw: str, input_dir: Path, stem: str) -> str:
    sandbox_path = to_sandbox_path(context, raw)
    suffix = PurePosixPath(sandbox_path).suffix or ".bin"
    input_dir.mkdir(parents=True, exist_ok=True)
    local_path = input_dir / f"{stem}{suffix}"
    content = await session.read_file_binary(sandbox_path)
    local_path.write_bytes(_ensure_bytes(content))
    return str(local_path)


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


def _expected_sandbox_artifacts(arguments: VideogenCliInput, context: ToolExecutionContext) -> list[str]:
    return _build_sandbox_output_paths(
        arguments.out,
        arguments.num_videos or arguments.n,
        arguments.out_dir,
        context,
    )


def _build_sandbox_output_paths(
    out: str,
    count: int,
    out_dir: str | None,
    context: ToolExecutionContext,
) -> list[str]:
    if out_dir:
        out_base = to_sandbox_path(context, out_dir, for_write=True)
        return [posixpath.join(out_base, f"video_{index}.mp4") for index in range(1, count + 1)]
    out_path = to_sandbox_path(context, out, for_write=True)
    if not PurePosixPath(out_path).suffix:
        out_path = f"{out_path}.mp4"
    if count == 1:
        return [out_path]
    parsed = PurePosixPath(out_path)
    return [
        posixpath.join(str(parsed.parent), f"{parsed.stem}-{index}{parsed.suffix}")
        for index in range(1, count + 1)
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
        base_dir = to_sandbox_path(context, "output/videogen", for_write=True)
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
