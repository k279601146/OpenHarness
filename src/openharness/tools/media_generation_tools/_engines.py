"""
底层媒体生成引擎 (Private Engines)
=====================================
本模块只负责"如何调用 API"以及"如何将结果推送给前端"。
不包含任何业务逻辑或模型路由；由上层工具调用。
"""

import asyncio
import base64
import json
import logging
import os
import random
import uuid
from pathlib import Path
from typing import Union

import httpx

from openharness.tools.base import ToolExecutionContext, ToolResult

log = logging.getLogger(__name__)

# --- Mock 数据（仅用于测试环境）---
_MOCK_IMAGE_URLS = [
    "https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?w=1024",
    "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?w=1024",
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1024",
    "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?w=1024",
    "https://images.unsplash.com/photo-1579546929518-9e396f3cc809?w=1024",
]

_MOCK_VIDEO_URLS = [
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
]


def _public_media_output(kind: str, paths: list[Path]) -> str:
    names = ", ".join(path.name for path in paths)
    count = len(paths)
    plural = "" if count == 1 else "s"
    return (
        f"SUCCESS: Generated {count} {kind}{plural}: {names}. "
        "The media has been published to the artifact preview. "
        "Do not expose host filesystem paths to the user."
    )


def _is_mock_mode(api_key: str) -> bool:
    """判断是否应使用 Mock 模式。必须显式设置 MOCK_MEDIA=true 才会启用。"""
    is_mock = os.getenv("MOCK_MEDIA", "false").lower() == "true"
    if is_mock:
        log.warning("⚠️ 检测到 MOCK_MEDIA=true，正在使用模拟数据模式生成媒体产物。")
    elif not api_key:
        log.error("❌ 媒体 API Key 未设置，生成任务将失败。")
    return is_mock


def load_image_as_base64(file_path: Union[str, Path], api_format: str) -> Union[str, dict]:
    """
    读取本地图片并转为 Base64。

    api_format:
        "doubao" -> 返回 data URI 字符串 "data:image/png;base64,..."
        "gemini" -> 返回 inlineData dict {"inlineData": {"mimeType": ..., "data": ...}}
    """
    str_path = str(file_path).lstrip("/")
    path = Path(str_path)

    if not path.exists():
        alt = Path(os.getcwd()) / str_path
        if alt.exists():
            path = alt
        else:
            raise FileNotFoundError(f"图片未找到: {file_path}")

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}
    mime = mime_map.get(path.suffix.lower().lstrip("."), "png")

    if api_format == "doubao":
        return f"data:image/{mime};base64,{encoded}"
    else:
        return {"inlineData": {"mimeType": f"image/{mime}", "data": encoded}}


async def notify_artifact(
    context: ToolExecutionContext,
    file_path: Path,
    prompt: str,
    artifact_type: str,  # "image" | "video"
) -> None:
    """通知前端产物已生成，实现 UI 实时预览。"""
    hook = context.metadata.get("hook")
    if not hook:
        return
    
    # 获取任务 ID
    task_id = context.metadata.get("thread_id")
    
    # 构建基础预览 URL (兜底方案)
    # 注意：SaaS 层的 hook.on_artifact 会拦截并重写为更简洁的 /artifacts/ 路径
    filename = os.path.basename(str(file_path))
    preview_url = f"/api/v1/tasks/files?path={filename}"
    if task_id:
        preview_url += f"&task_id={task_id}"
        
    prefix = "Generated image: " if artifact_type == "image" else "Generated video: "
    await hook.on_artifact(
        file_path=str(file_path),
        url=preview_url,
        reason=f"{prefix}{prompt[:50]}",
    )


# ===================================================================
# 图片生成引擎
# ===================================================================

async def _write_binary(dest, content_bytes: bytes):
    # 0. 确保 dest 是一个具体的 Path 对象，而不是 PurePath
    local_dest = Path(str(dest))

    # 1. 尝试本地写入 (宿主机)
    try:
        # 确保父目录存在
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        local_dest.write_bytes(content_bytes)
        log.info(f"Written binary locally: {local_dest}")
    except Exception as e:
        log.debug(f"Local write skipped or failed (might be remote path): {e}")

    # 2. 尝试同步到沙箱 (E2B)
    try:
        from openharness.sandbox.session import get_sandbox_session
        session = get_sandbox_session()
        if session and session.is_running:
            # 获取纯文件名，确保写入沙箱的 /home/user 根目录
            filename = os.path.basename(str(dest))
            sandbox_path = f"/home/user/{filename}"
            if hasattr(session, "write_file_binary"):
                await session.write_file_binary(sandbox_path, content_bytes)
                log.info(f"Synced binary to Sandbox: {sandbox_path}")
            elif hasattr(session, "upload"):
                await session.upload(sandbox_path, content_bytes)
        elif not os.path.exists(local_dest):
            # 如果本地没写成功且没沙箱，才报错
            raise RuntimeError(f"Cannot write to {dest}: not a local path and no sandbox session available.")
    except Exception as e:
        log.warning(f"Failed to sync binary to sandbox: {e}")


async def run_image_generation(
    *,
    task_id: str,
    prompt: str,
    provider: str,           # "gemini" | "doubao"
    api_model: str,          # 实际调用的模型名称
    payload: dict,           # 根据 provider 构建的请求 body
    api_key: str,
    base_url: str,
    context: ToolExecutionContext,
) -> ToolResult:
    """统一图片生成入口，根据 provider 分发到对应的执行逻辑。"""
    if _is_mock_mode(api_key):
        # 从 payload 中尝试提取 num_images
        count = 1
        if provider == "doubao":
            count = payload.get("sequential_image_generation_options", {}).get("max_images", 1)
        elif provider == "gemini":
            # Gemini 目前 payload 中没有多图配置，默认为 1
            count = 1
        elif provider == "openai":
            count = payload.get("n", 1)
        return await _mock_image(task_id, prompt, context, count=count)

    if provider == "gemini":
        return await _run_gemini_image(task_id, prompt, api_model, payload, api_key, base_url, context)
    elif provider == "doubao":
        return await _run_doubao_image(task_id, prompt, payload, api_key, base_url, context)
    elif provider == "openai":
        return await _run_openai_image(task_id, prompt, payload, api_key, base_url, context)
    else:
        return ToolResult(output=f"不支持的图片 provider: {provider}", is_error=True)


async def _mock_image(task_id: str, prompt: str, context: ToolExecutionContext, count: int = 1) -> ToolResult:
    log.info("[MockImageEngine] 使用模拟模式")
    saved = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(count):
            url = random.choice(_MOCK_IMAGE_URLS)
            fname = f"{task_id}_{i}.png" if count > 1 else f"{task_id}.png"
            dest = context.cwd / fname
            try:
                res = await client.get(url)
                res.raise_for_status()
                await _write_binary(dest, res.content)
                saved.append(dest)
                await notify_artifact(context, dest, prompt, "image")
            except Exception as e:
                log.warning(f"Mock 图片下载失败: {e}")
    if not saved:
        return ToolResult(output="Mock 图片下载失败，请检查网络。", is_error=True)
    return ToolResult(output=f"SUCCESS: (MOCK) 已模拟生成 {len(saved)} 张图片。保存文件: {[p.name for p in saved]}")


async def _run_gemini_image(
    task_id: str, prompt: str, api_model: str, payload: dict,
    api_key: str, base_url: str, context: ToolExecutionContext,
) -> ToolResult:
    log.info(f"[GeminiImageEngine] 提交任务 model={api_model}")
    # 确保 Gemini 使用 v1beta 路径
    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:  # 如果没有版本号，补上 v1beta
        clean_url = f"{clean_url}/v1beta"
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(
                f"{clean_url}/models/{api_model}:generateContent",
                json=payload,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            )
            res.raise_for_status()
            parts = res.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            b64 = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
            if not b64:
                return ToolResult(output="Gemini API 未返回图像数据。", is_error=True)
            dest = context.cwd / f"{task_id}.png"
            await _write_binary(dest, base64.b64decode(b64))
            await notify_artifact(context, dest, prompt, "image")
            return ToolResult(output=f"SUCCESS: 图像生成完毕，任务 ID: {task_id}。保存文件: {dest.name}")
    except Exception as e:
        log.exception("GeminiImageEngine 异常")
        return ToolResult(output=f"Gemini 图片生成失败: {e}", is_error=True)


async def _run_doubao_image(
    task_id: str, prompt: str, payload: dict,
    api_key: str, base_url: str, context: ToolExecutionContext,
) -> ToolResult:
    # 智能识别主体域名
    if "/v1" in base_url:
        base_domain = base_url.split("/v1")[0]
    elif "/v1beta" in base_url:
        base_domain = base_url.split("/v1beta")[0]
    else:
        base_domain = base_url.rstrip("/")
        
    log.info(f"[DoubaoImageEngine] 提交 SSE 流式任务")
    saved = []
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", f"{base_domain}/v1/images/generations", json=payload, headers=headers) as res:
                res.raise_for_status()
                async for line in res.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str in ("[DONE]", ""):
                        continue
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "image_generation.partial_succeeded":
                            b64 = event.get("b64_json", "")
                            idx = event.get("image_index", len(saved))
                            if b64:
                                dest = context.cwd / f"{task_id}_{idx}.png"
                                await _write_binary(dest, base64.b64decode(b64))
                                saved.append(dest)
                                await notify_artifact(context, dest, prompt, "image")
                    except Exception:
                        continue
        if not saved:
            return ToolResult(output="Doubao 未生成图像，请检查提示词合规性或 API 额度。", is_error=True)
        return ToolResult(output=_public_media_output("image", saved))
    except Exception as e:
        log.exception("DoubaoImageEngine 异常")
        return ToolResult(output=f"Doubao 图片生成失败: {e}", is_error=True)


async def _run_openai_image(
    task_id: str, prompt: str, payload: dict,
    api_key: str, base_url: str, context: ToolExecutionContext,
) -> ToolResult:
    """运行 OpenAI 兼容的图片生成接口。"""
    log.info(f"[OpenAIImageEngine] 提交任务 model={payload.get('model')}")
    # 确保 OpenAI 使用 v1 路径
    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:
        clean_url = f"{clean_url}/v1"
        
    saved = []
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(f"{clean_url}/images/generations", json=payload, headers=headers)
            res.raise_for_status()
            data_list = res.json().get("data", [])
            for idx, item in enumerate(data_list):
                b64 = item.get("b64_json")
                url = item.get("url")
                dest = context.cwd / (f"{task_id}_{idx}.png" if len(data_list) > 1 else f"{task_id}.png")

                if b64:
                    await _write_binary(dest, base64.b64decode(b64))
                elif url:
                    img_res = await client.get(url)
                    img_res.raise_for_status()
                    await _write_binary(dest, img_res.content)
                else:
                    continue

                saved.append(dest)
                await notify_artifact(context, dest, prompt, "image")

        if not saved:
            return ToolResult(output="OpenAI API 未返回有效的预览图像。", is_error=True)
        return ToolResult(output=_public_media_output("image", saved))
    except Exception as e:
        log.exception("OpenAIImageEngine 异常")
        return ToolResult(output=f"OpenAI 图片生成失败: {e}", is_error=True)


# ===================================================================
# 视频生成引擎
# ===================================================================

async def run_video_generation(
    *,
    task_id: str,
    prompt: str,
    provider: str,      # "veo" | "seedance"
    api_model: str,
    payload: dict,
    api_key: str,
    base_url: str,
    context: ToolExecutionContext,
) -> ToolResult:
    """统一视频生成入口，根据 provider 分发到对应执行逻辑。"""
    if _is_mock_mode(api_key):
        return await _mock_video(task_id, prompt, context)

    if provider == "veo":
        return await _run_veo_video(task_id, prompt, api_model, payload, api_key, base_url, context)
    elif provider == "seedance":
        return await _run_seedance_video(task_id, prompt, api_model, payload, api_key, base_url, context)
    else:
        return ToolResult(output=f"不支持的视频 provider: {provider}", is_error=True)


async def _mock_video(task_id: str, prompt: str, context: ToolExecutionContext) -> ToolResult:
    log.info("[MockVideoEngine] 使用模拟模式")
    url = random.choice(_MOCK_VIDEO_URLS)
    dest = context.cwd / f"{task_id}.mp4"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.get(url)
            res.raise_for_status()
            await _write_binary(dest, res.content)
        await notify_artifact(context, dest, prompt, "video")
        return ToolResult(output=f"SUCCESS: (MOCK) 视频模拟创作完成，任务 ID: {task_id}。保存文件: {dest.name}")
    except Exception as e:
        return ToolResult(output=f"Mock 视频下载失败: {e}", is_error=True)


async def _run_veo_video(
    task_id: str, prompt: str, api_model: str, payload: dict,
    api_key: str, base_url: str, context: ToolExecutionContext,
) -> ToolResult:
    log.info(f"[VeoEngine] 提交长任务 model={api_model}")
    clean_url = base_url.rstrip("/")
    if "/v1" not in clean_url:
        clean_url = f"{clean_url}/v1beta"
        
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{clean_url}/models/{api_model}:predictLongRunning",
                json=payload,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            )
            res.raise_for_status()
            operation_name = res.json().get("name")
            if not operation_name:
                return ToolResult(output="Veo API 未返回 operation_name", is_error=True)

            for _ in range(90):
                await asyncio.sleep(10)
                poll = await client.get(f"{base_url}/{operation_name}", headers={"x-goog-api-key": api_key})
                data = poll.json()
                if data.get("done"):
                    if "error" in data:
                        return ToolResult(output=f"Veo 制作失败: {data['error']}", is_error=True)
                    video_url = data["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
                    return await _download_video(task_id, prompt, video_url, context)

        return ToolResult(output="Veo 渲染等待超时。", is_error=True)
    except Exception as e:
        log.exception("VeoEngine 异常")
        return ToolResult(output=f"Veo 视频生成失败: {e}", is_error=True)


async def _run_seedance_video(
    task_id: str, prompt: str, api_model: str, payload: dict,
    api_key: str, base_url: str, context: ToolExecutionContext,
) -> ToolResult:
    # 识别域名
    if "/v1" in base_url:
        base_domain = base_url.split("/v1")[0]
    elif "/v1beta" in base_url:
        base_domain = base_url.split("/v1beta")[0]
    else:
        base_domain = base_url.rstrip("/")
        
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    log.info(f"[SeedanceEngine] 提交任务 model={api_model}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 提交任务
            endpoint = f"{base_domain}/v1/contents/generations/tasks"
            res = await client.post(endpoint, json=payload, headers=headers)
            if res.status_code == 404:
                endpoint = f"{base_domain}/api/v3/contents/generations/tasks"
                res = await client.post(endpoint, json=payload, headers=headers)
            res.raise_for_status()
            server_task_id = res.json().get("id")

            # 轮询状态
            for _ in range(120):
                await asyncio.sleep(10)
                poll_url = f"{base_domain}/v1/contents/generations/tasks/{server_task_id}"
                poll = await client.get(poll_url, headers=headers)
                if poll.status_code == 404:
                    poll_url = f"{base_domain}/api/v3/contents/generations/tasks/{server_task_id}"
                    poll = await client.get(poll_url, headers=headers)
                data = poll.json()
                status = data.get("status")
                if status == "succeeded":
                    video_url = data.get("content", {}).get("video_url")
                    return await _download_video(task_id, prompt, video_url, context)
                elif status in ("failed", "cancelled", "expired"):
                    return ToolResult(output=f"Seedance 异常终止: {status} | {data.get('error')}", is_error=True)

        return ToolResult(output="Seedance 渲染等待超时。", is_error=True)
    except Exception as e:
        log.exception("SeedanceEngine 异常")
        return ToolResult(output=f"Seedance 视频生成失败: {e}", is_error=True)


async def _download_video(task_id: str, prompt: str, video_url: str, context: ToolExecutionContext) -> ToolResult:
    """通用视频下载函数。"""
    if not video_url or "http" not in video_url:
        return ToolResult(output="未获取到有效的视频 URL。", is_error=True)
    dest = context.cwd / f"{task_id}.mp4"
    log.info(f"正在下载视频到: {dest}")
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("GET", video_url) as res:
                res.raise_for_status()
                content_bytes = await res.aread()
                await _write_binary(dest, content_bytes)
        await notify_artifact(context, dest, prompt, "video")
        return ToolResult(output=f"SUCCESS: 视频创作完成，任务 ID: {task_id}。保存文件: {dest.name}")
    except Exception as e:
        return ToolResult(output=f"视频下载失败: {e}", is_error=True)
