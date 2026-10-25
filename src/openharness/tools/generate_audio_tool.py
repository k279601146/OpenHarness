"""Canonical audio / TTS generation tool.

The tool is intentionally thin: it validates high-level audio intent and
delegates all paid media execution to the SaaS backend hook.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class AudioGenerationBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    character: str | None = None
    tone: str | None = None
    emotion: str | None = None
    scene: str | None = None
    constraints: str | None = None


class AudioGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str | None = Field(
        default=None,
        description="Target voice ID or name from voice catalog (e.g. from tts-prompter skill or voice clone).",
    )
    format: Literal["mp3", "wav", "pcm", "opus", "aac"] | None = Field(
        default="mp3",
        description="Audio format. Defaults to mp3.",
    )
    speed: float | None = Field(
        default=None,
        ge=0.25,
        le=4.0,
        description="Playback/speech speed multiplier (e.g. 0.8, 1.0, 1.25).",
    )
    emotion: str | None = Field(
        default=None,
        description="Emotional expression or style modifier (e.g. happy, sad, angry, fear, calm).",
    )
    pitch: int | None = Field(
        default=None,
        ge=-12,
        le=12,
        description="Pitch adjustment (-12 to 12).",
    )
    volume: float | None = Field(
        default=None,
        ge=-10.0,
        le=10.0,
        description="Volume gain in dB (-10.0 to 10.0).",
    )
    latency: Literal["normal", "balanced", "low"] | None = Field(
        default=None,
        description="Inference latency mode (for streaming/fast responses).",
    )


class GenerateAudioInput(BaseModel):
    """High-level audio request extracted from the tts-prompter skill."""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["generate", "tts", "dub", "dialogue"] = "generate"
    prompt: str = Field(
        description="Final speech text or formatted TTS prompt (formatted using tts-prompter guidelines: '{Style}: {Text}')."
    )
    voice_id: str | None = Field(
        default=None,
        description="Target voice ID or reference (e.g. '59cb5986671546eaa6ca8ae6f29f6d22' or 'default').",
    )
    brief: AudioGenerationBrief = Field(
        default_factory=AudioGenerationBrief,
        description='Optional production brief object such as {"tone": "gentle"} or {}. Never pass a quoted JSON string.',
    )
    output: AudioGenerationOutput = Field(
        default_factory=AudioGenerationOutput,
        description='Optional output intent object such as {"voice_id": "...", "format": "mp3", "speed": 1.0} or {}. Never pass a quoted JSON string.',
    )
    language: str | None = Field(
        default=None,
        description="Language code hint (e.g., 'zh', 'en', 'ja', 'es').",
    )
    instructions: str | None = Field(
        default=None,
        description="Optional director style instructions (if separated from prompt).",
    )
    model_id: str | None = Field(
        default=None,
        description="Optional logical audio model id (e.g., 'fish-audio-drama-3-preview', 'fish-audio-s2.1-pro', 'minimax-speech-2.8-hd', 'gpt-4o-mini-tts').",
    )

    @field_validator("prompt")
    @classmethod
    def require_prompt(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("prompt is required")
        if len(text) > 10000:
            raise ValueError("prompt is too long")
        return text


class GenerateAudioTool(BaseTool):
    """Delegate audio / speech generation to the SaaS media backend."""

    name = "generate_audio"
    description = (
        "Generate spoken audio / speech (TTS) from text, dialogue scripts, or formatted TTS prompts. "
        "The SaaS backend handles model routing, voice mapping, billing, provider execution, validation, and artifact delivery. "
        "Consult tts-prompter skill for optimal prompt structure ('{Style}: {Text}') and voice selection. "
        "Optional nested fields brief and output must be passed as objects. "
        "Use empty objects when there is no detail; never quote nested JSON."
    )
    input_model = GenerateAudioInput
    display_name = "语音生成"
    default_start_message = "正在生成语音..."
    requires_sandbox = False

    async def execute(self, arguments: GenerateAudioInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "generate_audio"):
            return ToolResult(
                output="Audio generation is only available through the SaaS media backend.",
                is_error=True,
                metadata={"media_billing_status": "skipped"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "media_generate",
                    "status": "running",
                    "message": "正在生成语音...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        backend_metadata = {
            **context.metadata,
            "cwd": str(context.cwd),
        }
        try:
            result = await hook.generate_audio(arguments.model_dump(mode="json"), backend_metadata)
        except Exception as exc:
            return ToolResult(
                output=f"Audio generation failed: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={},
            )

        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "Audio generation failed."),
                is_error=True,
                metadata=metadata,
            )

        artifact_payloads = metadata.get("artifact_payloads")
        count = len(artifact_payloads) if isinstance(artifact_payloads, list) else 0
        output = (
            f"generate_audio completed and published {count} audio artifact(s) to the UI. "
            "Do not call deliver_artifact for these audio artifact(s)."
        )
        if count > 0 and isinstance(artifact_payloads, list):
            ref_lines = []
            for idx, item in enumerate(artifact_payloads, start=1):
                if isinstance(item, dict):
                    art_id = item.get("artifact_id")
                    url = item.get("url") or item.get("public_url")
                    ref_lines.append(f"{idx}. input_ref: artifact:{art_id}\n   public_url: {url}")
            if ref_lines:
                output = f"{output}\n\nGenerated audio reference(s):\n" + "\n".join(ref_lines)

        return ToolResult(
            output=output,
            metadata={
                **metadata,
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )
