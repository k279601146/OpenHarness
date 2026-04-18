"""Image and Video generation tools using PackyAPI (OpenViking compatible)."""

import asyncio
import base64
import json
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional, Union, Any, Dict

import httpx
from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

log = logging.getLogger(__name__)

# --- Helper Functions (Core Engines) ---

def _get_image_data(file_path: Union[str, Path], api_format: str) -> Union[str, dict]:
    """读取本地已生成图片，转为 Base64 并根据对接方接口格式化。"""
    # 移除可能的开头斜杠，确保路径正确
    str_path = str(file_path).lstrip('/')
    path = Path(str_path)
    
    # 尝试多种路径可能，处理相对/绝对路径不一致问题
    if not path.exists():
        # 尝试在当前工作目录下查找
        alt_path = Path(os.getcwd()) / str_path
        if alt_path.exists():
            path = alt_path
        else:
            raise FileNotFoundError(f"本地图片未找到: {file_path} (尝试了 {path} 和 {alt_path})")
        
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    
    ext = path.suffix.lower().replace('.', '')
    mime_mapping = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}
    mime_type = mime_mapping.get(ext, "png")
    
    if api_format == "doubao":
        return f"data:image/{mime_type};base64,{encoded}"
    else: # gemini / nano-banana / veo
        return {"inlineData": {"mimeType": f"image/{mime_type}", "data": encoded}}

async def _execute_image_generation(
    task_id: str,
    prompt: str,
    model: str,
    payload_variants: dict,
    api_key: str,
    base_url: str,
    context: ToolExecutionContext
) -> ToolResult:
    """抽象出的底层图片生成引擎。支持并列处理不同供应商的参数组合。"""
    if not api_key:
        log.warning("PACKY_API_KEY is missing, returning mock image.")
        return ToolResult(output="API_KEY 缺失，无法生成真实图片。请联系管理员配置环境变量。", is_error=True)

    output_dir = context.cwd
    
    try:
        if "banana" in model.lower():
            actual_model_name = "gemini-3.1-flash-image-preview" if "nano-banana" in model else "gemini-2.5-flash-image"
            payload = payload_variants.get("gemini", {})
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                log.info(f"[图片渲染引擎] 正在向 PackyAPI(模型={actual_model_name}) 提交任务...")
                res = await client.post(
                    f"{base_url}/models/{actual_model_name}:generateContent",
                    json=payload,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}
                )
                res.raise_for_status()
                data = res.json()
                
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                base64_data = None
                for p in parts:
                    if "inlineData" in p:
                        base64_data = p["inlineData"]["data"]
                        break
                
                if base64_data:
                    filename = f"{task_id}.png"
                    physical_path = output_dir / filename
                    physical_path.write_bytes(base64.b64decode(base64_data))
                    
                    await _notify_artifact(context, physical_path, prompt, "image")
                    return ToolResult(output=f"SUCCESS: 图像已成功生成。任务ID: {task_id}。用户已在屏幕上看到结果。")
                else:
                    return ToolResult(output="API 调用成功，但未返回图像数据。", is_error=True)
                    
        else: # Doubao
            actual_model_name = "doubao-seedream-5.0-lite"
            base_domain = base_url.split("/v1")[0] if "/v1" in base_url else "https://api.packyapi.com"
            payload = payload_variants.get("doubao", {})
            
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            saved_images = []
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                log.info(f"[图片渲染引擎] 正在向 PackyAPI 提交 Doubao({actual_model_name}) 流式生成任务...")
                async with client.stream("POST", f"{base_domain}/v1/images/generations", json=payload, headers=headers) as res:
                    res.raise_for_status()
                    async for line in res.aiter_lines():
                        line = line.strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]" or not data_str: continue
                            try:
                                event_data = json.loads(data_str)
                                if event_data.get("type") == "image_generation.partial_succeeded":
                                    b64_data = event_data.get("b64_json", "")
                                    img_idx = event_data.get("image_index", len(saved_images))
                                    if b64_data:
                                        filename = f"{task_id}_{img_idx}.png"
                                        physical_path = output_dir / filename
                                        physical_path.write_bytes(base64.b64decode(b64_data))
                                        saved_images.append(physical_path)
                                        await _notify_artifact(context, physical_path, prompt, "image")
                            except: continue
            
            if not saved_images:
                return ToolResult(output="未生成图像。请检查提示词合规性或 API 资源额度。", is_error=True)
            
            return ToolResult(output=f"SUCCESS: 已生成 {len(saved_images)} 张图像并展示给用户。")

    except Exception as e:
        log.exception("Image generation engine failed")
        return ToolResult(output=f"生图引擎报错: {str(e)}", is_error=True)

async def _execute_video_task(
    task_id: str,
    scene_prompt: str,
    model: str,
    provider: str,
    payload: dict,
    api_key: str,
    base_url: str,
    context: ToolExecutionContext
) -> ToolResult:
    """内部通用视频生成轮询引擎。"""
    if not api_key:
        return ToolResult(output="API_KEY 缺失，无法调用视频模型。", is_error=True)

    output_dir = context.cwd
    final_video_url = None
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "veo":
                log.info(f"[Veo 引擎] 正在提交任务: {model}")
                res = await client.post(
                    f"{base_url}/models/{model}:predictLongRunning",
                    json=payload,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}
                )
                res.raise_for_status()
                operation_name = res.json().get("name")
                if not operation_name:
                    return ToolResult(output="Veo API 未返回 operation_name", is_error=True)
                    
                poll_count = 0
                while poll_count < 90:
                    poll_count += 1
                    await asyncio.sleep(10)
                    poll_res = await client.get(f"{base_url}/{operation_name}", headers={"x-goog-api-key": api_key})
                    status_data = poll_res.json()
                    if status_data.get("done"):
                        if "error" in status_data:
                            return ToolResult(output=f"Veo 制作失败: {status_data['error']}", is_error=True)
                        final_video_url = status_data["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
                        break
            
            elif provider == "seedance":
                base_domain = base_url.split("/v1")[0] if "/v1" in base_url else "https://api.packyapi.com"
                log.info(f"[Seedance 引擎] 正在提交任务: {model}")
                res = await client.post(
                    f"{base_domain}/v1/contents/generations/tasks",
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                )
                if res.status_code == 404:
                    res = await client.post(
                        f"{base_domain}/api/v3/contents/generations/tasks",
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    )
                res.raise_for_status()
                task_id_server = res.json().get("id")
                
                poll_count = 0
                while poll_count < 120:
                    poll_count += 1
                    await asyncio.sleep(10)
                    poll_url = f"{base_domain}/v1/contents/generations/tasks/{task_id_server}"
                    poll_res = await client.get(poll_url, headers={"Authorization": f"Bearer {api_key}"})
                    if poll_res.status_code == 404:
                         poll_url = f"{base_domain}/api/v3/contents/generations/tasks/{task_id_server}"
                         poll_res = await client.get(poll_url, headers={"Authorization": f"Bearer {api_key}"})
                    
                    status_data = poll_res.json()
                    status = status_data.get("status")
                    if status == "succeeded":
                        final_video_url = status_data.get("content", {}).get("video_url")
                        break
                    elif status in ["failed", "cancelled", "expired"]:
                        return ToolResult(output=f"Seedance 异常终止: {status} | {status_data.get('error')}", is_error=True)

        if final_video_url and "http" in final_video_url:
            filename = f"{task_id}.mp4"
            physical_path = output_dir / filename
            log.info(f"正在下载视频到: {physical_path}")
            async with httpx.AsyncClient(timeout=300.0) as dl_client:
                async with dl_client.stream("GET", final_video_url) as dl_res:
                    dl_res.raise_for_status()
                    with open(physical_path, "wb") as f:
                        async for chunk in dl_res.aiter_bytes(): f.write(chunk)
            
            await _notify_artifact(context, physical_path, scene_prompt, "video")
            return ToolResult(output=f"SUCCESS: 视频创作完成。任务ID: {task_id}。用户已可以观看。")

    except Exception as e:
        log.exception("Video generation engine failed")
        return ToolResult(output=f"视频引擎网络错误: {str(e)}", is_error=True)

    return ToolResult(output="视频渲染等待超时，上游算力压力过大或请求被取消。", is_error=True)

async def _notify_artifact(context: ToolExecutionContext, file_path: Path, prompt: str, artifact_type: str):
    """通知前端 UI 产物已生成，以便实时渲染。"""
    hook = context.metadata.get("hook")
    if not hook:
        return
        
    api_url = os.getenv("NEXT_PUBLIC_API_URL") or "http://localhost:8000"
    # 注意：这里我们无法获取用户的 JWT token，所以只传 path 和 api_url
    preview_url = f"{api_url}/api/v1/tasks/files?path={file_path}"
    
    # 构建精准的 reason 用于反查关联 ID
    prefix = "Generated image: " if artifact_type == "image" else "Generated video: "
    reason = f"{prefix}{prompt[:50]}"
    
    await hook.on_artifact(
        file_path=str(file_path),
        url=preview_url,
        reason=reason
    )

# --- 图像工具类定义 ---

class CreativeImageInput(BaseModel):
    prompt: str = Field(description="[必填] 高质量图像描述。包含主体描述、布光、构图、背景、风格等。")
    aspect_ratio: str = Field(default="1:1", description="宽高比。可选：1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3")
    model: str = Field(default="nano-banana", description="模型选择：'nano-banana' (极速), 'Doubao' (超高质量)")

class CreativeImageTool(BaseTool):
    """[纯文生图] 使用 AI 图像模型从零开始生成全新素材。"""
    name = "gen_creative_image"
    description = "使用最新多模态模型从零开始生成高质量图片。提示词需尽可能详细。"
    input_model = CreativeImageInput

    async def execute(self, arguments: CreativeImageInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"img_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("image_model")
            if pref_model == "seedream-4": target_model = "nano-banana"
            elif "seedream" in str(pref_model): target_model = "Doubao"
            
        doubao_size_mapping = {"1:1": "2048x2048", "4:3": "2304x1728", "3:4": "1728x2304", "16:9": "2848x1600", "9:16": "1600x2848"}
        gemini_payload = {
            "contents": [{"parts": [{"text": arguments.prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"], 
                "imageConfig": {"aspectRatio": arguments.aspect_ratio if arguments.aspect_ratio in ["1:1","16:9","9:16","4:3","3:4"] else "1:1", "imageSize": "2K"}
            }
        }
        doubao_payload = {
            "model": "doubao-seedream-5.0-lite",
            "prompt": arguments.prompt,
            "size": doubao_size_mapping.get(arguments.aspect_ratio, "2048x2048"),
            "stream": True,
            "response_format": "b64_json",
            "sequential_image_generation": "auto",
            "sequential_image_generation_options": {"max_images": 4}
        }
        return await _execute_image_generation(task_id, arguments.prompt, target_model, {"gemini": gemini_payload, "doubao": doubao_payload}, api_key, base_url, context)

class EditImageInput(BaseModel):
    source_image_path: str = Field(description="[必填] 原始图片路径（物理路径）")
    prompt: str = Field(description="[必填] 编辑指令。如“增加一只猫”、“背景改为赛博朋克风”")
    model: str = Field(default="nano-banana", description="模型选择")

class EditImageTool(BaseTool):
    """[图片编辑] 针对已有图片进行局部修改或风格变换。"""
    name = "edit_image"
    description = "对给定的已有图片进行局部修改、添删元素或变换整体风格。"
    input_model = EditImageInput

    async def execute(self, arguments: EditImageInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"edit_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("image_model")
            if pref_model == "seedream-4": target_model = "nano-banana"
            elif "seedream" in str(pref_model): target_model = "Doubao"

        try:
            gemini_img = _get_image_data(arguments.source_image_path, "gemini")
            doubao_img = _get_image_data(arguments.source_image_path, "doubao")
        except Exception as e: return ToolResult(output=f"加载源图失败: {e}", is_error=True)

        gemini_payload = {
            "contents": [{"parts": [{"text": arguments.prompt}, gemini_img]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"imageSize": "2K"}}
        }
        doubao_payload = {
            "model": "doubao-seedream-5.0-lite", "prompt": arguments.prompt, "image": [doubao_img],
            "stream": True, "response_format": "b64_json", "sequential_image_generation": "disabled"
        }
        return await _execute_image_generation(task_id, arguments.prompt, target_model, {"gemini": gemini_payload, "doubao": doubao_payload}, api_key, base_url, context)

class ImageFromReferenceInput(BaseModel):
    image_paths: List[str] = Field(description="[必填] 参考图路径列表（1-14张）")
    prompt: str = Field(description="[必填] 混合描述或角色描述")
    model: str = Field(default="Doubao-seedream-5.0-lite", description="模型选择")

class ImageFromReferenceTool(BaseTool):
    """[参考生图] 使用多张图片作为特征参考生成新图。"""
    name = "generate_from_reference"
    description = "使用 1~14 张已有图片作为参考（保持一致性或融合特征），生成连贯的新图。"
    input_model = ImageFromReferenceInput

    async def execute(self, arguments: ImageFromReferenceInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"ref_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        try:
            gemini_imgs = [_get_image_data(p, "gemini") for p in arguments.image_paths]
            doubao_imgs = [_get_image_data(p, "doubao") for p in arguments.image_paths]
        except Exception as e: return ToolResult(output=f"加载参考图失败: {e}", is_error=True)

        gemini_payload = {"contents": [{"parts": [{"text": arguments.prompt}] + gemini_imgs}], "generationConfig": {"responseModalities": ["IMAGE"]}}
        doubao_payload = {"model": "doubao-seedream-5.0-lite", "prompt": arguments.prompt, "image": doubao_imgs, "stream": True, "response_format": "b64_json", "sequential_image_generation": "auto"}
        return await _execute_image_generation(task_id, arguments.prompt, arguments.model, {"gemini": gemini_payload, "doubao": doubao_payload}, api_key, base_url, context)

# --- 视频工具类定义 ---

class CreativeVideoInput(BaseModel):
    scene_prompt: str = Field(description="[必填] 视频分镜描述。支持描绘细节、音效背景、台词等。")
    duration: int = Field(default=5, description="时长（秒），最大建议 10s")
    model: str = Field(default="veo", description="模型：'veo' (谷歌电影级) 或 'seedance' (字节高质量)")

class CreativeVideoTool(BaseTool):
    """[纯文生视频] 从文本生成有声视频。"""
    name = "gen_creative_video"
    description = "从零生成带音效和配音的高质量有声视频，不支持图片输入。"
    input_model = CreativeVideoInput

    async def execute(self, arguments: CreativeVideoInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"vid_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("video_model")
            if pref_model == "video-3.1-fast": target_model = "veo"
            elif "seedance" in str(pref_model): target_model = "seedance"
            elif "keling" in str(pref_model): target_model = "keling"

        if target_model.lower() == "veo":
            payload = {"instances": [{"prompt": arguments.scene_prompt}], "parameters": {"aspectRatio": "16:9", "durationSeconds": str(min(8, arguments.duration))}}
            return await _execute_video_task(task_id, arguments.scene_prompt, "veo-3.1-generate-preview", "veo", payload, api_key, base_url, context)
        elif target_model.lower() == "keling":
             # 这里可以适配 Keling 接口，目前假设通过 seedance 或相同 payload 兼容
             payload = {"model": "keling-2.6", "content": [{"type": "text", "text": arguments.scene_prompt}], "ratio": "16:9", "duration": arguments.duration}
             return await _execute_video_task(task_id, arguments.scene_prompt, "keling-2.6", "seedance", payload, api_key, base_url, context)
        else:
            payload = {"model": "doubao-seedance-1-5-pro-251215", "content": [{"type": "text", "text": arguments.scene_prompt}], "ratio": "16:9", "duration": arguments.duration, "generate_audio": True}
            return await _execute_video_task(task_id, arguments.scene_prompt, "doubao-seedance-1-5-pro-251215", "seedance", payload, api_key, base_url, context)

class AnimateFirstFrameInput(BaseModel):
    source_image_path: str = Field(description="[必填] 首帧图片物理路径")
    scene_prompt: str = Field(description="[必填] 描述后续的镜头变幻或动作")
    duration: int = Field(default=5, description="时长")
    model: str = Field(default="veo", description="模型选择")

class AnimateFirstFrameTool(BaseTool):
    """[图生视频-首帧推演] 让图片按指令动起来。"""
    name = "animate_first_frame"
    description = "使用指定图片作为起点起点，让画面动起来，支持提示词控音效。"
    input_model = AnimateFirstFrameInput

    async def execute(self, arguments: AnimateFirstFrameInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"anim_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("video_model")
            if pref_model == "video-3.1-fast": target_model = "veo"
            elif "seedance" in str(pref_model): target_model = "seedance"
            elif "keling" in str(pref_model): target_model = "keling"

        try:
            img_data = _get_image_data(arguments.source_image_path, "gemini")
            raw_b64 = img_data["inlineData"]["data"]
            mime = img_data["inlineData"]["mimeType"].split('/')[-1]
        except Exception as e: return ToolResult(output=f"载入图片失败: {e}", is_error=True)

        if target_model.lower() == "veo":
            payload = {"instances": [{"prompt": arguments.scene_prompt, "image": img_data}], "parameters": {"aspectRatio": "16:9", "durationSeconds": str(min(8, arguments.duration))}}
            return await _execute_video_task(task_id, arguments.scene_prompt, "veo-3.1-generate-preview", "veo", payload, api_key, base_url, context)
        elif target_model.lower() == "keling":
             payload = {"model": "keling-2.6", "content": [{"type": "text", "text": arguments.scene_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{raw_b64}"}, "role": "first_frame"}], "ratio": "16:9", "duration": arguments.duration}
             return await _execute_video_task(task_id, arguments.scene_prompt, "keling-2.6", "seedance", payload, api_key, base_url, context)
        else:
            payload = {"model": "doubao-seedance-1-5-pro-251215", "content": [{"type": "text", "text": arguments.scene_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{raw_b64}"}, "role": "first_frame"}], "ratio": "16:9", "duration": arguments.duration, "generate_audio": True}
            return await _execute_video_task(task_id, arguments.scene_prompt, "doubao-seedance-1-5-pro-251215", "seedance", payload, api_key, base_url, context)

class VideoInterpolationInput(BaseModel):
    first_frame_path: str = Field(description="[必填] 起始图物理路径")
    last_frame_path: str = Field(description="[必填] 结束图物理路径")
    scene_prompt: str = Field(description="[必填] 中间演变过程描写")
    duration: int = Field(default=5, description="时长")
    model: str = Field(default="veo", description="模型选择")

class VideoInterpolationTool(BaseTool):
    """[图生视频-首尾帧补齐] 实现极具张力的演变创意。"""
    name = "video_interpolation"
    description = "传入起始和终结图，由模型填补中间的演变过程。创意运镜利器。"
    input_model = VideoInterpolationInput

    async def execute(self, arguments: VideoInterpolationInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"interp_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("video_model")
            if pref_model == "video-3.1-fast": target_model = "veo"
            elif "seedance" in str(pref_model): target_model = "seedance"
            elif "keling" in str(pref_model): target_model = "keling"

        try:
           f_img = _get_image_data(arguments.first_frame_path, "gemini")
           l_img = _get_image_data(arguments.last_frame_path, "gemini")
           mime = f_img["inlineData"]["mimeType"].split('/')[-1]
        except Exception as e: return ToolResult(output=f"加载帧图片失败: {e}", is_error=True)

        if target_model.lower() == "veo":
            payload = {"instances": [{"prompt": arguments.scene_prompt, "image": f_img, "lastFrame": l_img}], "parameters": {"aspectRatio": "16:9"}}
            return await _execute_video_task(task_id, arguments.scene_prompt, "veo-3.1-generate-preview", "veo", payload, api_key, base_url, context)
        elif target_model.lower() == "keling":
             payload = {"model": "keling-2.6", "content": [{"type": "text", "text": arguments.scene_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{f_img['inlineData']['data']}"}, "role": "first_frame"}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{l_img['inlineData']['data']}"}, "role": "last_frame"}], "ratio": "16:9", "duration": arguments.duration}
             return await _execute_video_task(task_id, arguments.scene_prompt, "keling-2.6", "seedance", payload, api_key, base_url, context)
        else:
            payload = {"model": "doubao-seedance-1-5-pro-251215", "content": [{"type": "text", "text": arguments.scene_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{f_img['inlineData']['data']}"}, "role": "first_frame"}, {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{l_img['inlineData']['data']}"}, "role": "last_frame"}], "ratio": "16:9", "duration": arguments.duration, "generate_audio": True}
            return await _execute_video_task(task_id, arguments.scene_prompt, "doubao-seedance-1-5-pro-251215", "seedance", payload, api_key, base_url, context)

class VideoWithReferenceInput(BaseModel):
    reference_image_paths: List[str] = Field(description="[必填] 主角/物品特征参考图路径（1-3张）")
    scene_prompt: str = Field(description="[必填] 全新剧情/环境描写")
    duration: int = Field(default=5, description="时长")
    model: str = Field(default="veo", description="模型选择")

class VideoWithReferenceTool(BaseTool):
    """[特征生视频] 保持主角外观一致拍摄新剧本。"""
    name = "video_with_reference"
    description = "保持主角特征一致的前提下，生成全新的视觉内容。常用于品牌或角色内容创作。"
    input_model = VideoWithReferenceInput

    async def execute(self, arguments: VideoWithReferenceInput, context: ToolExecutionContext) -> ToolResult:
        task_id = f"refvid_{uuid.uuid4().hex[:8]}"
        api_key = os.getenv("PACKY_API_KEY") 
        base_url = os.getenv("PACKY_BASE_URL", "https://api.packyapi.com/v1beta")
        
        # 尊重用户偏好
        prefs = context.metadata.get("media_preferences", {})
        target_model = arguments.model
        if not prefs.get("is_auto", True):
            pref_model = prefs.get("video_model")
            if pref_model == "video-3.1-fast": target_model = "veo"
            elif "seedance" in str(pref_model): target_model = "seedance"
            elif "keling" in str(pref_model): target_model = "keling"

        if target_model.lower() == "veo":
            ref_list = []
            for p in arguments.reference_image_paths[:3]:
                try: 
                    img = _get_image_data(p, "gemini")
                    ref_list.append({"image": img, "referenceType": "asset"})
                except: continue
            if not ref_list: return ToolResult(output="参考图解析完全失败", is_error=True)
            payload = {"instances": [{"prompt": arguments.scene_prompt, "referenceImages": ref_list}], "parameters": {"aspectRatio": "16:9"}}
            return await _execute_video_task(task_id, arguments.scene_prompt, "veo-3.1-generate-preview", "veo", payload, api_key, base_url, context)
        elif target_model.lower() == "keling":
             content = [{"type": "text", "text": arguments.scene_prompt}]
             for p in arguments.reference_image_paths[:4]:
                try:
                    img = _get_image_data(p, "gemini")
                    mime = img["inlineData"]["mimeType"].split('/')[-1]
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img['inlineData']['data']}"}, "role": "reference_image"})
                except: continue
             payload = {"model": "keling-2.6", "content": content, "ratio": "16:9", "duration": arguments.duration}
             return await _execute_video_task(task_id, arguments.scene_prompt, "keling-2.6", "seedance", payload, api_key, base_url, context)
        else:
            content = [{"type": "text", "text": arguments.scene_prompt}]
            for p in arguments.reference_image_paths[:4]:
                try:
                    img = _get_image_data(p, "gemini")
                    mime = img["inlineData"]["mimeType"].split('/')[-1]
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{img['inlineData']['data']}"}, "role": "reference_image"})
                except: continue
            payload = {"model": "doubao-seedance-1-0-lite-i2v-250428", "content": content, "ratio": "16:9", "duration": arguments.duration}
            return await _execute_video_task(task_id, arguments.scene_prompt, "doubao-seedance-1-0-lite-i2v-250428", "seedance", payload, api_key, base_url, context)
