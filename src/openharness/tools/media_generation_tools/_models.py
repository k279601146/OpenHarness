"""
模型路由表 (Model Registry)
===========================
定义前端 model_id 到实际 API 调用参数的映射。
新增或修改模型，只需修改此文件，其余工具代码零改动。

provider 枚举值：
- "gemini"   : PackyAPI / Google Gemini 图片生成接口
- "doubao"   : 字节 PackyAPI Doubao 图片生成接口 (SSE 流式)
- "veo"      : PackyAPI / Google Veo 视频生成接口 (长任务轮询)
- "seedance" : 字节 PackyAPI Seedance 视频生成接口 (任务轮询)
"""

from typing import TypedDict, Literal

ProviderType = Literal["gemini", "doubao", "veo", "seedance"]


class ModelConfig(TypedDict):
    provider: ProviderType
    api_model: str          # 实际调用 API 时使用的模型名称


# ===================================================================
# 图片模型注册表
# ===================================================================
IMAGE_MODEL_REGISTRY: dict[str, ModelConfig] = {
    # --- Nano Banana 系列 (Google Gemini via PackyAPI) ---
    # 前端展示名: Nano Banana 2
    "nano-banana-2": {
        "provider": "gemini",
        "api_model": "gemini-3.1-flash-image-preview",
    },
    # 前端展示名: Nano Banana Pro
    "nano-banana-pro": {
        "provider": "gemini",
        "api_model": "gemini-3.0-pro-image-preview",
    },
    # 前端展示名: Nano Banana (基础版)
    "nano-banana": {
        "provider": "gemini",
        "api_model": "gemini-2.5-flash-image",
    },

    # --- 字节 Doubao Seedream 系列 ---
    "doubao-seedream-5-0-260128": {
        "provider": "doubao",
        "api_model": "doubao-seedream-5-0-260128",
    },
    "doubao-seedream-5-0-lite-260128": {
        "provider": "doubao",
        "api_model": "doubao-seedream-5-0-lite-260128",
    },
    "doubao-seedream-4-5-251128": {
        "provider": "doubao",
        "api_model": "doubao-seedream-4-5-251128",
    },
    "doubao-seedream-4-0-250828": {
        "provider": "doubao",
        "api_model": "doubao-seedream-4-0-250828",
    },
}

# ===================================================================
# 视频模型注册表
# ===================================================================
VIDEO_MODEL_REGISTRY: dict[str, ModelConfig] = {
    # --- Google Veo 系列 ---
    # 前端展示名: Veo 3.1
    "veo-3.1": {
        "provider": "veo",
        "api_model": "veo-3.1-generate-preview",
    },
    # 前端展示名: Veo 3.1 Lite
    "veo-3.1-lite": {
        "provider": "veo",
        "api_model": "veo-3.1-lite-generate-preview",
    },

    # --- 字节 Doubao Seedance 系列 ---
    "doubao-seedance-2-0-260128": {
        "provider": "seedance",
        "api_model": "doubao-seedance-2-0-260128",
    },
    "doubao-seedance-2-0-fast-260128": {
        "provider": "seedance",
        "api_model": "doubao-seedance-2-0-fast-260128",
    },
    "doubao-seedance-1-5-pro-251215": {
        "provider": "seedance",
        "api_model": "doubao-seedance-1-5-pro-251215",
    },
}

# ===================================================================
# 默认模型（Auto 模式或前端未传值时使用）
# ===================================================================
DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-lite-260128"
DEFAULT_VIDEO_MODEL = "doubao-seedance-1-5-pro-251215"


def resolve_image_model(model_id: str) -> ModelConfig:
    """将前端传入的 model_id 解析为实际 API 配置，找不到时使用默认模型。"""
    key = model_id.lower().strip()
    if key in IMAGE_MODEL_REGISTRY:
        return IMAGE_MODEL_REGISTRY[key]
    # 兼容旧版 model_id 字符串（历史原因）
    if "seedream" in key or "doubao" in key:
        return IMAGE_MODEL_REGISTRY[DEFAULT_IMAGE_MODEL]
    # 默认走 Gemini 快速通道
    return IMAGE_MODEL_REGISTRY["nano-banana"]


def resolve_video_model(model_id: str) -> ModelConfig:
    """将前端传入的 model_id 解析为实际 API 配置，找不到时使用默认模型。"""
    key = model_id.lower().strip()
    if key in VIDEO_MODEL_REGISTRY:
        return VIDEO_MODEL_REGISTRY[key]
    if "veo" in key:
        return VIDEO_MODEL_REGISTRY["veo-3.1"]
    return VIDEO_MODEL_REGISTRY[DEFAULT_VIDEO_MODEL]
