"""
视频生成工具集
=============
包含四个视频工具：
1. CreativeVideoTool         - 纯文生视频
2. AnimateFirstFrameTool     - 图生视频（首帧推演）
3. VideoInterpolationTool    - 图生视频（首尾帧插值）
4. VideoWithReferenceTool    - 特征参考生视频
"""

import os
import uuid
from typing import List

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.media_generation_tools._engines import (
    load_image_as_base64,
    run_video_generation,
)
from openharness.tools.media_generation_tools._models import (
    DEFAULT_VIDEO_MODEL,
    resolve_video_model,
)


def _get_api_credentials() -> tuple[str, str]:
    """获取视频生成专用的 API Key 和 Base URL。"""
    api_key = os.getenv("VIDEO_GEN_API_KEY", "")
    base_url = os.getenv("VIDEO_GEN_BASE_URL", "https://api.packyapi.com")
    return api_key, base_url


def _resolve_video_model_from_context(arguments_model: str, context: ToolExecutionContext) -> tuple[str, str]:
    """
    综合前端偏好和工具参数，确定最终使用的视频 provider 和 api_model。
    优先级：工具调用参数 > 前端全局偏好（非 Auto 模式）> 默认值
    """
    prefs = context.metadata.get("media_preferences", {})
    if not prefs.get("is_auto", True):
        model_id = prefs.get("video_model", DEFAULT_VIDEO_MODEL)
    else:
        model_id = arguments_model or DEFAULT_VIDEO_MODEL

    cfg = resolve_video_model(model_id)
    return cfg["provider"], cfg["api_model"]


# ===================================================================
# 工具 1：纯文生视频
# ===================================================================

class CreativeVideoInput(BaseModel):
    scene_prompt: str = Field(
        description="[必填] 视频分镜描述。可描述运镜方式、角色动作、音效背景等。"
    )
    duration: int = Field(default=5, description="时长（秒），最大建议 10s。")
    aspect_ratio: str = Field(default="16:9", description="宽高比，可选：16:9, 9:16, 1:1")
    model: str = Field(
        default=DEFAULT_VIDEO_MODEL,
        description=(
            "指定视频生成模型 ID。"
            "可选值：veo-3.1, veo-3.1-lite, "
            "doubao-seedance-2-0-260128, doubao-seedance-2-0-fast-260128, "
            "doubao-seedance-1-5-pro-251215"
        ),
    )


class CreativeVideoTool(BaseTool):
    """[纯文生视频] 从文本描述生成带音效和配音的高质量有声视频。"""

    name = "gen_creative_video"
    description = (
        "从零生成带音效和配音的高质量有声视频（不支持图片输入）。"
        "可指定模型；若未指定则由系统根据用户偏好自动选择。"
    )
    input_model = CreativeVideoInput

    async def execute(self, arguments: CreativeVideoInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"vid_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_video_model_from_context(arguments.model, context)

        duration = min(arguments.duration, 10)

        if provider == "veo":
            payload = {
                "instances": [{"prompt": arguments.scene_prompt}],
                "parameters": {
                    "aspectRatio": arguments.aspect_ratio,
                    "durationSeconds": str(duration),
                },
            }
        else:  # seedance
            payload = {
                "model": api_model,
                "content": [{"type": "text", "text": arguments.scene_prompt}],
                "ratio": arguments.aspect_ratio,
                "duration": duration,
                "generate_audio": True,
            }

        return await run_video_generation(
            task_id=task_id,
            prompt=arguments.scene_prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 工具 2：图生视频（首帧推演）
# ===================================================================

class AnimateFirstFrameInput(BaseModel):
    source_image_path: str = Field(description="[必填] 首帧图片的物理路径。")
    scene_prompt: str = Field(description="[必填] 描述首帧之后的镜头变幻或动作。")
    duration: int = Field(default=5, description="时长（秒）。")
    aspect_ratio: str = Field(default="16:9", description="宽高比，可选：16:9, 9:16, 1:1")
    model: str = Field(
        default=DEFAULT_VIDEO_MODEL,
        description="指定视频模型 ID，同 gen_creative_video。",
    )


class AnimateFirstFrameTool(BaseTool):
    """[图生视频·首帧推演] 以指定图片为起点，让画面按提示词动起来。"""

    name = "animate_first_frame"
    description = "使用指定图片作为起点让画面动起来，支持提示词控制运镜和音效。"
    input_model = AnimateFirstFrameInput

    async def execute(self, arguments: AnimateFirstFrameInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"anim_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_video_model_from_context(arguments.model, context)

        try:
            img_data = load_image_as_base64(arguments.source_image_path, "gemini")
            raw_b64 = img_data["inlineData"]["data"]
            mime = img_data["inlineData"]["mimeType"].split("/")[-1]
        except Exception as e:
            return ToolResult(output=f"载入首帧图片失败: {e}", is_error=True)

        duration = min(arguments.duration, 10)

        if provider == "veo":
            payload = {
                "instances": [{"prompt": arguments.scene_prompt, "image": img_data}],
                "parameters": {
                    "aspectRatio": arguments.aspect_ratio,
                    "durationSeconds": str(duration),
                },
            }
        else:  # seedance
            payload = {
                "model": api_model,
                "content": [
                    {"type": "text", "text": arguments.scene_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{raw_b64}"},
                        "role": "first_frame",
                    },
                ],
                "ratio": arguments.aspect_ratio,
                "duration": duration,
                "generate_audio": True,
            }

        return await run_video_generation(
            task_id=task_id,
            prompt=arguments.scene_prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 工具 3：图生视频（首尾帧插值）
# ===================================================================

class VideoInterpolationInput(BaseModel):
    first_frame_path: str = Field(description="[必填] 起始帧图片的物理路径。")
    last_frame_path: str = Field(description="[必填] 结束帧图片的物理路径。")
    scene_prompt: str = Field(description="[必填] 描述中间演变过程的提示词。")
    duration: int = Field(default=5, description="时长（秒）。")
    aspect_ratio: str = Field(default="16:9", description="宽高比，可选：16:9, 9:16, 1:1")
    model: str = Field(
        default=DEFAULT_VIDEO_MODEL,
        description="指定视频模型 ID，同 gen_creative_video。",
    )


class VideoInterpolationTool(BaseTool):
    """[图生视频·首尾帧插值] 传入起点和终点图片，由模型填补中间的演变过程。"""

    name = "video_interpolation"
    description = "传入起始和结束两张图，由模型填补中间的演变过程。创意运镜利器。"
    input_model = VideoInterpolationInput

    async def execute(self, arguments: VideoInterpolationInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"interp_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_video_model_from_context(arguments.model, context)

        try:
            f_img = load_image_as_base64(arguments.first_frame_path, "gemini")
            l_img = load_image_as_base64(arguments.last_frame_path, "gemini")
            mime = f_img["inlineData"]["mimeType"].split("/")[-1]
            f_b64 = f_img["inlineData"]["data"]
            l_b64 = l_img["inlineData"]["data"]
        except Exception as e:
            return ToolResult(output=f"加载帧图片失败: {e}", is_error=True)

        if provider == "veo":
            payload = {
                "instances": [
                    {"prompt": arguments.scene_prompt, "image": f_img, "lastFrame": l_img}
                ],
                "parameters": {"aspectRatio": arguments.aspect_ratio},
            }
        else:  # seedance
            payload = {
                "model": api_model,
                "content": [
                    {"type": "text", "text": arguments.scene_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{f_b64}"},
                        "role": "first_frame",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{l_b64}"},
                        "role": "last_frame",
                    },
                ],
                "ratio": arguments.aspect_ratio,
                "duration": arguments.duration,
                "generate_audio": True,
            }

        return await run_video_generation(
            task_id=task_id,
            prompt=arguments.scene_prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 工具 4：特征参考生视频
# ===================================================================

class VideoWithReferenceInput(BaseModel):
    reference_image_paths: List[str] = Field(
        description="[必填] 主角/物品特征参考图路径（1~4 张）。"
    )
    scene_prompt: str = Field(description="[必填] 全新剧情/环境描写。")
    duration: int = Field(default=5, description="时长（秒）。")
    aspect_ratio: str = Field(default="16:9", description="宽高比，可选：16:9, 9:16, 1:1")
    model: str = Field(
        default=DEFAULT_VIDEO_MODEL,
        description="指定视频模型 ID，同 gen_creative_video。",
    )


class VideoWithReferenceTool(BaseTool):
    """[特征参考生视频] 在保持主角外观一致的前提下，生成全新场景的视频。"""

    name = "video_with_reference"
    description = "保持主角特征一致的前提下，生成全新的视觉内容，常用于品牌或角色内容创作。"
    input_model = VideoWithReferenceInput

    async def execute(self, arguments: VideoWithReferenceInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"refvid_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_video_model_from_context(arguments.model, context)

        if provider == "veo":
            ref_list = []
            for p in arguments.reference_image_paths[:3]:
                try:
                    img = load_image_as_base64(p, "gemini")
                    ref_list.append({"image": img, "referenceType": "asset"})
                except Exception:
                    continue
            if not ref_list:
                return ToolResult(output="参考图解析完全失败。", is_error=True)
            payload = {
                "instances": [
                    {"prompt": arguments.scene_prompt, "referenceImages": ref_list}
                ],
                "parameters": {"aspectRatio": arguments.aspect_ratio},
            }
        else:  # seedance
            content: list = [{"type": "text", "text": arguments.scene_prompt}]
            for p in arguments.reference_image_paths[:4]:
                try:
                    img = load_image_as_base64(p, "gemini")
                    mime = img["inlineData"]["mimeType"].split("/")[-1]
                    b64 = img["inlineData"]["data"]
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{mime};base64,{b64}"},
                        "role": "reference_image",
                    })
                except Exception:
                    continue
            payload = {
                "model": api_model,
                "content": content,
                "ratio": arguments.aspect_ratio,
                "duration": arguments.duration,
            }

        return await run_video_generation(
            task_id=task_id,
            prompt=arguments.scene_prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )
