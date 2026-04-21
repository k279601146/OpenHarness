"""
图片生成工具集
=============
包含三个图片工具：
1. CreativeImageTool       - 纯文生图
2. EditImageTool           - 图片编辑
3. ImageFromReferenceTool  - 多图参考生图
"""

import os
import uuid
from typing import List

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult
from openharness.tools.media_generation_tools._engines import (
    load_image_as_base64,
    run_image_generation,
)
from openharness.tools.media_generation_tools._models import (
    DEFAULT_IMAGE_MODEL,
    resolve_image_model,
)


def _get_api_credentials() -> tuple[str, str]:
    """获取 API Key 和 Base URL。"""
    api_key = os.getenv("PACKY_API_KEY", "")
    base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
    return api_key, base_url


def _resolve_model_from_context(arguments_model: str, context: ToolExecutionContext) -> tuple[str, str]:
    """
    综合前端偏好和工具参数，确定最终使用的 provider 和 api_model。
    优先级：用户在工具调用时显式传入的 model > 前端全局偏好设置 > 默认值
    """
    prefs = context.metadata.get("media_preferences", {})
    # 仅当非 Auto 模式时，前端偏好才生效
    if not prefs.get("is_auto", True):
        model_id = prefs.get("image_model", DEFAULT_IMAGE_MODEL)
    else:
        model_id = arguments_model or DEFAULT_IMAGE_MODEL

    cfg = resolve_image_model(model_id)
    return cfg["provider"], cfg["api_model"]


# ===================================================================
# 工具 1：纯文生图
# ===================================================================

class CreativeImageInput(BaseModel):
    prompt: str = Field(description="[必填] 高质量图像描述。需包含主体、风格、构图、光影等细节。")
    aspect_ratio: str = Field(
        default="1:1",
        description="宽高比，可选：1:1, 16:9, 9:16, 4:3, 3:4",
    )
    model: str = Field(
        default=DEFAULT_IMAGE_MODEL,
        description=(
            "指定要使用的图片生成模型 ID。"
            "可选值：nano-banana, nano-banana-2, nano-banana-pro, "
            "doubao-seedream-5-0-260128, doubao-seedream-5-0-lite-260128, "
            "doubao-seedream-4-5-251128, doubao-seedream-4-0-250828"
        ),
    )
    num_images: int = Field(
        default=1,
        ge=1,
        le=8,
        description="生成的图片数量（1-8）。对于支持多图的模型有效，默认根据用户意图决定。",
    )


class CreativeImageTool(BaseTool):
    """[纯文生图] 从文本描述生成全新的高质量图像素材。"""

    name = "gen_creative_image"
    description = (
        "使用 AI 图像模型从零开始生成高质量图片。"
        "提示词需尽可能详细，可指定模型；若未指定则由系统根据用户偏好自动选择。"
    )
    input_model = CreativeImageInput

    async def execute(self, arguments: CreativeImageInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"img_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_model_from_context(arguments.model, context)

        # 构建 payload
        ar = arguments.aspect_ratio
        doubao_size_map = {
            "1:1": "2048x2048", "4:3": "2304x1728", "3:4": "1728x2304",
            "16:9": "2848x1600", "9:16": "1600x2848",
        }
        payload = _build_image_payload(
            provider, api_model, arguments.prompt, ar, doubao_size_map, arguments.num_images
        )

        return await run_image_generation(
            task_id=task_id,
            prompt=arguments.prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 工具 2：图片编辑
# ===================================================================

class EditImageInput(BaseModel):
    source_image_path: str = Field(description="[必填] 原始图片的物理路径。")
    prompt: str = Field(description='[必填] 编辑指令，如"增加一只猫"、"改为赛博朋克风"。')
    model: str = Field(
        default=DEFAULT_IMAGE_MODEL,
        description="指定图片模型 ID，同 gen_creative_image。",
    )
    num_images: int = Field(
        default=1,
        ge=1,
        le=4,
        description="生成的图片数量（1-4）。对于支持多图的模型有效。",
    )


class EditImageTool(BaseTool):
    """[图片编辑] 对已有图片进行局部修改、元素增删或整体风格变换。"""

    name = "edit_image"
    description = "对给定的已有图片进行局部修改、添删元素或变换整体风格。"
    input_model = EditImageInput

    async def execute(self, arguments: EditImageInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"edit_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_model_from_context(arguments.model, context)

        try:
            gemini_img = load_image_as_base64(arguments.source_image_path, "gemini")
            doubao_img = load_image_as_base64(arguments.source_image_path, "doubao")
        except Exception as e:
            return ToolResult(output=f"加载源图失败: {e}", is_error=True)

        if provider == "gemini":
            payload = {
                "contents": [{"parts": [{"text": arguments.prompt}, gemini_img]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"imageSize": "2K"}},
            }
        else:
            payload = {
                "model": api_model,
                "prompt": arguments.prompt,
                "image": [doubao_img],
                "stream": True,
                "response_format": "b64_json",
                "sequential_image_generation": "auto" if arguments.num_images > 1 else "disabled",
                "sequential_image_generation_options": {"max_images": arguments.num_images},
            }

        return await run_image_generation(
            task_id=task_id,
            prompt=arguments.prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 工具 3：多图参考生图
# ===================================================================

class ImageFromReferenceInput(BaseModel):
    image_paths: List[str] = Field(description="[必填] 参考图路径列表（1~14 张）。")
    prompt: str = Field(description="[必填] 描述目标图像的提示词。")
    model: str = Field(
        default=DEFAULT_IMAGE_MODEL,
        description="指定图片模型 ID，同 gen_creative_image。",
    )
    num_images: int = Field(
        default=1,
        ge=1,
        le=4,
        description="生成的图片数量（1-4）。对于支持多图的模型有效。",
    )


class ImageFromReferenceTool(BaseTool):
    """[参考生图] 以多张图片作为特征参考，生成风格或角色连贯的新图。"""

    name = "generate_from_reference"
    description = "使用 1~14 张已有图片作为参考（保持一致性或融合特征），生成连贯的新图。"
    input_model = ImageFromReferenceInput

    async def execute(self, arguments: ImageFromReferenceInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"ref_{uuid.uuid4().hex[:8]}"
        api_key, base_url = _get_api_credentials()
        provider, api_model = _resolve_model_from_context(arguments.model, context)

        try:
            gemini_imgs = [load_image_as_base64(p, "gemini") for p in arguments.image_paths]
            doubao_imgs = [load_image_as_base64(p, "doubao") for p in arguments.image_paths]
        except Exception as e:
            return ToolResult(output=f"加载参考图失败: {e}", is_error=True)

        if provider == "gemini":
            payload = {
                "contents": [{"parts": [{"text": arguments.prompt}] + gemini_imgs}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            }
        else:
            payload = {
                "model": api_model,
                "prompt": arguments.prompt,
                "image": doubao_imgs,
                "stream": True,
                "response_format": "b64_json",
                "sequential_image_generation": "auto" if arguments.num_images > 1 else "disabled",
                "sequential_image_generation_options": {"max_images": arguments.num_images},
            }

        return await run_image_generation(
            task_id=task_id,
            prompt=arguments.prompt,
            provider=provider,
            api_model=api_model,
            payload=payload,
            api_key=api_key,
            base_url=base_url,
            context=context,
        )


# ===================================================================
# 内部辅助：构建文生图 payload
# ===================================================================

def _build_image_payload(
    provider: str,
    api_model: str,
    prompt: str,
    aspect_ratio: str,
    doubao_size_map: dict,
    num_images: int = 1,
) -> dict:
    if provider == "gemini":
        valid_ar = aspect_ratio if aspect_ratio in ("1:1", "16:9", "9:16", "4:3", "3:4") else "1:1"
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": valid_ar, "imageSize": "2K"},
            },
        }
    else:  # doubao
        return {
            "model": api_model,
            "prompt": prompt,
            "size": doubao_size_map.get(aspect_ratio, "2048x2048"),
            "stream": True,
            "response_format": "b64_json",
            "sequential_image_generation": "auto" if num_images > 1 else "disabled",
            "sequential_image_generation_options": {"max_images": num_images},
        }
