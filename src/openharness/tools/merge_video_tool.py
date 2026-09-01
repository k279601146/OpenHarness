"""通用视频合成工具（FFmpeg 后端）。

该工具仅做 Schema 校验和委派，所有 FFmpeg 执行均在 SaaS 后端 merge_video_service 中完成。
遵循三层架构：Tool → Hook → Service。

支持能力：
- 多视频拼接（自动统一分辨率/FPS/编码/Pixel Format/音频采样率）
- 视频裁剪（start / duration）
- 视频缩放与画布适配（scale + pad / crop）
- 视频淡入淡出（FFmpeg fade/afade）
- 视频静音 / 音量调整
- 多音频轨道（BGM 添加、音量、循环、裁剪、淡入淡出）
- 视频原声保留 / 移除
- 音视频混合（amix）
- 视频旋转
- 缩略图生成
- 最终视频编码（H.264/libx264 默认，可配置）
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


def _is_stable_media_ref(value: str) -> bool:
    """校验是否为稳定的 artifact/upload/public 引用。"""
    text = str(value or "").strip()
    if not text:
        return False
    if "\\" in text or any(ch.isspace() for ch in text):
        return False
    if text.startswith("artifact:"):
        rest = text.split(":", 1)[1].strip()
        return bool(rest)
    if text.startswith("/artifacts/") or text.startswith("/uploads/"):
        return ".." not in text
    return False


class VideoClip(BaseModel):
    """单个视频片段描述。asset_id 必须是稳定引用。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(
        description=(
            "视频稳定引用，格式：artifact:<id>、/artifacts/... 或 /uploads/...。"
            "禁止传入沙箱路径（/home/user/...）或宿主机绝对路径。"
        )
    )
    start: float = Field(
        default=0.0,
        ge=0.0,
        description="从视频的哪一秒开始截取（秒），默认 0。",
    )
    duration: float | None = Field(
        default=None,
        gt=0.0,
        description="截取时长（秒）。None 表示截取到视频结尾。",
    )
    volume: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="视频原声音量缩放系数 [0, 2]，默认 1.0（保持原始）。",
    )
    mute: bool = Field(
        default=False,
        description="为 true 时静音该视频原声，等同于 volume=0。",
    )
    fade_in: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="视频（画面+音频）淡入时长（秒），0 表示无淡入。",
    )
    fade_out: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="视频（画面+音频）淡出时长（秒），0 表示无淡出。",
    )
    rotate: Literal[0, 90, 180, 270] | None = Field(
        default=None,
        description="顺时针旋转角度（度）：90 / 180 / 270。None 表示不旋转。",
    )

    @field_validator("asset_id")
    @classmethod
    def require_stable_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("asset_id is required")
        if not _is_stable_media_ref(text):
            raise ValueError(
                f"asset_id must be a stable reference (artifact:<id>, /artifacts/..., /uploads/...); "
                f"got: {text!r}"
            )
        return text


class AudioTrack(BaseModel):
    """额外音频轨道（BGM 等）。"""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(
        description=(
            "音频稳定引用，格式：artifact:<id>、/artifacts/... 或 /uploads/...。"
        )
    )
    start: float = Field(
        default=0.0,
        ge=0.0,
        description="从音频文件的哪一秒开始截取，默认 0。",
    )
    duration: float | None = Field(
        default=None,
        gt=0.0,
        description="截取时长（秒）。None 时后端自动裁剪/循环到视频总时长。",
    )
    volume: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="音量缩放系数 [0, 2]。",
    )
    loop: bool = Field(
        default=False,
        description="为 true 时循环播放该音频，直到视频总时长结束。",
    )
    fade_in: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="音频淡入时长（秒）。",
    )
    fade_out: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="音频淡出时长（秒）。",
    )
    delay: float = Field(
        default=0.0,
        ge=0.0,
        description="该音轨在混合时间线中的延迟偏移（秒），默认 0 表示从头开始。",
    )

    @field_validator("asset_id")
    @classmethod
    def require_stable_ref(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("asset_id is required")
        if not _is_stable_media_ref(text):
            raise ValueError(
                f"asset_id must be a stable reference (artifact:<id>, /artifacts/..., /uploads/...); "
                f"got: {text!r}"
            )
        return text


class VideoOutput(BaseModel):
    """输出参数。"""

    model_config = ConfigDict(extra="forbid")

    format: str = Field(
        default="mp4",
        description="输出封装格式，默认 mp4。",
    )
    width: int | None = Field(
        default=None,
        gt=0,
        description="目标宽度（像素）。None 时自动取最大输入宽度（对齐到 2 的倍数）。",
    )
    height: int | None = Field(
        default=None,
        gt=0,
        description="目标高度（像素）。None 时自动取最大输入高度（对齐到 2 的倍数）。",
    )
    fps: float | None = Field(
        default=None,
        gt=0.0,
        description="目标帧率。None 时自动取最大输入帧率。",
    )
    video_codec: str = Field(
        default="libx264",
        description="视频编码器，如 libx264、libx265、vp9。默认 libx264。",
    )
    audio_codec: str = Field(
        default="aac",
        description="音频编码器，如 aac、mp3、opus。默认 aac。",
    )
    crf: int | None = Field(
        default=None,
        ge=0,
        le=51,
        description="画质因子 [0,51]，值越小画质越好，libx264 默认 23。None 时使用 FFmpeg 默认值。",
    )
    preset: str | None = Field(
        default=None,
        description="x264/x265 编码预设，如 ultrafast、fast、medium、slow。None 时使用 FFmpeg 默认。",
    )
    video_bitrate: str | None = Field(
        default=None,
        description="视频目标码率，如 '4000k'、'2M'。设置后 crf 失效。",
    )
    audio_bitrate: str | None = Field(
        default=None,
        description="音频目标码率，如 '128k'、'192k'。",
    )
    fit_mode: Literal["pad", "crop", "stretch"] = Field(
        default="pad",
        description=(
            "多视频分辨率统一策略。"
            "pad：缩放后黑边填充（不裁切，保持画面完整，默认）；"
            "crop：缩放后居中裁切（去除黑边，可能裁掉画面边缘）；"
            "stretch：直接拉伸（可能变形）。"
        ),
    )
    pad_color: str = Field(
        default="black",
        description="fit_mode=pad 时的背景填充色，如 black、white，或 #rrggbb。",
    )
    pixel_format: str = Field(
        default="yuv420p",
        description="Pixel format，默认 yuv420p（浏览器兼容性最好）。",
    )


class Transition(BaseModel):
    """两段视频之间的转场描述。"""

    model_config = ConfigDict(extra="forbid")

    between: list[int] = Field(
        min_length=2,
        max_length=2,
        description=(
            "转场位于第几个和第几个片段之间，从 0 开始计数。"
            "例如 [0, 1] 表示第 1 和第 2 个视频之间。"
        ),
    )
    type: Literal["none", "fade"] = Field(
        default="fade",
        description="转场类型。none=直接拼接；fade=交叉淡入淡出。",
    )
    duration: float = Field(
        default=0.5,
        gt=0.0,
        le=5.0,
        description="转场时长（秒），仅 type=fade 时有意义，默认 0.5。",
    )

    @model_validator(mode="after")
    def validate_between(self) -> "Transition":
        if not isinstance(self.between, (list, tuple)) or len(self.between) != 2:
            raise ValueError("transition.between 必须包含恰好两个片段序号，如 [0, 1]")
        a, b = int(self.between[0]), int(self.between[1])
        if b != a + 1:
            raise ValueError(
                f"transition.between must be consecutive clip indices, e.g. (0, 1); got ({a}, {b})"
            )
        return self


class ThumbnailSpec(BaseModel):
    """缩略图生成参数。"""

    model_config = ConfigDict(extra="forbid")

    at: float = Field(
        default=0.0,
        ge=0.0,
        description="从最终视频哪一秒提取缩略图，默认 0。",
    )
    format: Literal["png", "jpeg"] = Field(
        default="jpeg",
        description="缩略图格式。",
    )


class MergeVideoInput(BaseModel):
    """merge_video_tool 规范化输入。所有嵌套字段必须传对象，不能传 JSON 字符串。"""

    model_config = ConfigDict(extra="forbid")

    videos: list[VideoClip] = Field(
        description=(
            "视频片段列表，按照拼接顺序排列。至少 1 个。"
            "每个元素必须是对象，不能传 JSON 字符串。"
        )
    )
    audio_tracks: list[AudioTrack] = Field(
        default_factory=list,
        description=(
            "额外音频轨道（BGM 等），可选。"
            "每个元素必须是对象，不能传 JSON 字符串。"
        ),
    )
    output: VideoOutput = Field(
        description=(
            "输出参数对象，必填。"
            "使用默认值时传 {} 即可，不能传 JSON 字符串。"
        )
    )
    transitions: list[Transition] = Field(
        default_factory=list,
        description=(
            "视频片段之间的转场，可选。"
            "不指定时所有片段直接拼接（无转场）。"
        ),
    )
    thumbnail: ThumbnailSpec | None = Field(
        default=None,
        description="缩略图生成参数，可选。None 时不生成缩略图。",
    )

    @field_validator("videos")
    @classmethod
    def require_at_least_one_video(cls, value: list[VideoClip]) -> list[VideoClip]:
        if not value:
            raise ValueError("videos must contain at least one VideoClip")
        if len(value) > 50:
            raise ValueError("videos must contain at most 50 clips")
        return value

    @model_validator(mode="after")
    def validate_transitions(self) -> "MergeVideoInput":
        n = len(self.videos)
        for tr in self.transitions:
            a, b = int(tr.between[0]), int(tr.between[1])
            if a < 0 or b >= n:
                raise ValueError(
                    f"transition.between ({a}, {b}) is out of range for {n} video clip(s)"
                )
        return self


class MergeVideoTool(BaseTool):
    """将多个视频片段（及可选音轨）通过 FFmpeg 合成为一个视频的通用工具。

    SaaS 后端负责：资源解析、FFmpeg Pipeline 构建与执行、artifact 注册与发布。
    """

    name = "merge_video_tool"
    description = (
        "使用 FFmpeg 将多个视频片段合成为一个完整视频，支持裁剪、缩放、分辨率统一、"
        "FPS 统一、原声保留/静音/音量调整、BGM 添加（循环/裁剪/淡入淡出）、"
        "音视频混合、视频淡入淡出、旋转、字幕烧录（环境支持时）、最终 H.264 MP4 输出、"
        "缩略图生成等。"
        "所有嵌套字段（output 等）必须传真正的对象，不能传带引号的 JSON 字符串。"
        "不要调用 deliver_artifact 交付此工具生成的视频，后端会自动发布。"
    )
    input_model = MergeVideoInput
    display_name = "视频合成"
    default_start_message = "正在合成视频..."
    requires_sandbox = False

    async def execute(self, arguments: MergeVideoInput, context: ToolExecutionContext) -> ToolResult:
        hook = context.metadata.get("hook")
        if hook is None or not hasattr(hook, "merge_video"):
            return ToolResult(
                output="merge_video_tool 仅在 SaaS 后端环境中可用。",
                is_error=True,
                metadata={"media_billing_status": "skipped"},
            )

        if context.progress_callback is not None:
            await context.progress_callback(
                {
                    "phase": "merge_video",
                    "status": "running",
                    "message": "正在合成视频...",
                    "tool_name": self.name,
                    "tool_use_id": context.metadata.get("tool_use_id"),
                }
            )

        backend_metadata = {
            **context.metadata,
            "cwd": str(context.cwd),
        }
        try:
            result = await hook.merge_video(arguments.model_dump(mode="json"), backend_metadata)
        except Exception as exc:
            return ToolResult(
                output=f"视频合成失败: {type(exc).__name__}: {exc}",
                is_error=True,
                metadata={},
            )

        metadata = result if isinstance(result, dict) else {}
        if metadata.get("error"):
            return ToolResult(
                output=str(metadata.get("message") or "视频合成失败。"),
                is_error=True,
                metadata=metadata,
            )

        payloads = metadata.get("artifact_payloads") or []
        count = len(payloads)

        # 构建 Agent 可复用的稳定引用列表
        lines: list[str] = [
            f"merge_video_tool 完成，已发布 {count} 个视频 artifact 到 UI。",
            "不要再调用 deliver_artifact 交付这些视频。",
        ]
        for i, p in enumerate(payloads, start=1):
            if not isinstance(p, dict):
                continue
            artifact_id = str(p.get("artifact_id") or "").strip()
            public_url = str(p.get("url") or p.get("public_url") or "").strip()
            if artifact_id:
                lines.append(f"{i}. input_ref: artifact:{artifact_id}")
                if public_url:
                    lines.append(f"   public_url: {public_url}")
            elif public_url:
                lines.append(f"{i}. public_url: {public_url}")

        # 缩略图引用
        thumb_payloads = metadata.get("thumbnail_payloads") or []
        for tp in thumb_payloads:
            if not isinstance(tp, dict):
                continue
            thumb_id = str(tp.get("artifact_id") or "").strip()
            if thumb_id:
                lines.append(f"缩略图 input_ref: artifact:{thumb_id}")

        return ToolResult(
            output="\n".join(lines),
            metadata={
                **metadata,
                "publish_state": "published",
                "published_artifact": True,
                "delivery_required": False,
                "do_not_deliver_artifact": True,
            },
        )
