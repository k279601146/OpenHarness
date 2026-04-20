"""
媒体生成工具包对外接口
=====================
统一导出所有图片和视频工具类，保持与原 media_generation_tools.py 完全一致的导出名称，
使 tools/__init__.py 无需修改任何导入语句。
"""

from openharness.tools.media_generation_tools.image_tools import (
    CreativeImageTool,
    EditImageTool,
    ImageFromReferenceTool,
)
from openharness.tools.media_generation_tools.video_tools import (
    AnimateFirstFrameTool,
    CreativeVideoTool,
    VideoInterpolationTool,
    VideoWithReferenceTool,
)

__all__ = [
    # 图片工具
    "CreativeImageTool",
    "EditImageTool",
    "ImageFromReferenceTool",
    # 视频工具
    "CreativeVideoTool",
    "AnimateFirstFrameTool",
    "VideoInterpolationTool",
    "VideoWithReferenceTool",
]
