"""沙箱会话管理器 — 进程级注册表 + DB 持久化。

重构后不再使用 ContextVar 单例，改为 dict 注册表，支持：
- 同用户同会话容器复用
- 闲置挂起 → 超时自动销毁
- 跨 Worker 重启后从 DB 恢复状态
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openharness.config import Settings
    from openharness.sandbox.docker_backend import DockerSandboxSession

logger = logging.getLogger(__name__)

# ═══ 进程级沙箱注册表 ═══
# key = "user_id:thread_id", value = DockerSandboxSession
_sandbox_registry: dict[str, DockerSandboxSession] = {}
_registry_lock = asyncio.Lock()


def _registry_key(user_id: int, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def get_active_sandbox(user_id: int, thread_id: str) -> DockerSandboxSession | None:
    """从进程内存注册表获取活跃的沙箱会话。"""
    key = _registry_key(user_id, thread_id)
    session = _sandbox_registry.get(key)
    if session is not None and session.is_running:
        return session
    return None


def is_docker_sandbox_active_for(user_id: int, thread_id: str) -> bool:
    """检查指定用户+会话的沙箱是否正在运行。"""
    return get_active_sandbox(user_id, thread_id) is not None


def is_docker_sandbox_active() -> bool:
    """兼容旧接口：检查当前进程中是否有任何活跃的沙箱。"""
    return any(s.is_running for s in _sandbox_registry.values())


def get_docker_sandbox() -> DockerSandboxSession | None:
    """兼容旧接口：自动获取当前上下文的活跃沙箱。"""
    try:
        # 尝试从 Engine 上下文中自动获取 UID/TID
        # 这种设计允许工具层无需显式传递上下文也能透明路由到沙箱
        import sys
        # 检查是否在 api 路径下，如果是则可以导入 engine_adapter
        from engine_adapter import active_user_id, active_thread_id
        uid = active_user_id.get()
        tid = active_thread_id.get()
        if uid and tid:
            return get_active_sandbox(int(uid), tid)
    except (ImportError, Exception):
        pass
    return None


def _resolve_sandbox_data_root(settings: Settings) -> Path:
    """确定沙箱持久化数据根目录。

    优先级：
    1. settings.sandbox.sandbox_data_root (显式配置)
    2. /opt/manus/sandbox-data (Linux 生产环境)
    3. 项目根/sandbox-data (Windows 开发环境)
    """
    if settings.sandbox.sandbox_data_root:
        return Path(settings.sandbox.sandbox_data_root)

    if os.name == "nt":
        # Windows 开发环境：定位到项目根
        # settings 模块通常在 OpenHarness/src/openharness/config/ 下
        # 我们需要找到外层项目根
        current = Path(__file__).resolve()
        # 向上查找包含 apps/ 的目录作为项目根
        for parent in current.parents:
            if (parent / "apps").is_dir():
                return parent / "sandbox-data"
        # Fallback
        return Path.cwd() / "sandbox-data"
    else:
        return Path("/opt/manus/sandbox-data")


def _ensure_persistent_dirs(data_root: Path, user_id: int, space_id: str) -> tuple[str, str, str]:
    """创建三层持久化目录，返回 (workspace_path, home_path, bin_path)。"""
    base = data_root / str(user_id) / space_id
    workspace = base / "workspace"
    home = base / "user-home"
    local_bin = base / "local-bin"

    for d in (workspace, home, local_bin):
        d.mkdir(parents=True, exist_ok=True)

    return str(workspace), str(home), str(local_bin)


async def get_or_start_sandbox(
    settings: Settings,
    user_id: int,
    thread_id: str,
    db_session=None,
) -> DockerSandboxSession | None:
    """获取或启动沙箱。核心复用逻辑：

    1. 内存注册表命中 → 直接复用
    2. DB 中有 suspended 记录 → 尝试恢复容器
    3. 无记录 → 新建沙箱空间 + 启动容器
    """
    from openharness.sandbox.docker_backend import (
        DockerSandboxSession,
        get_docker_availability,
    )

    # 前置检查：Docker 是否可用
    availability = get_docker_availability(settings)
    if not availability.available:
        if settings.sandbox.fail_if_unavailable:
            from openharness.sandbox.adapter import SandboxUnavailableError
            raise SandboxUnavailableError(
                availability.reason or "Docker sandbox is unavailable"
            )
        logger.warning("Docker sandbox unavailable: %s", availability.reason)
        return None

    key = _registry_key(user_id, thread_id)

    async with _registry_lock:
        # ── 路径 1: 内存命中 ──
        existing = _sandbox_registry.get(key)
        if existing is not None and existing.is_running:
            logger.info("Sandbox reused from registry: %s", existing.container_name)
            _touch_last_active(db_session, thread_id)
            return existing

        # ── 路径 2: DB 查找已有空间 ──
        space = None
        if db_session is not None:
            try:
                from models import SandboxSpace
                space = db_session.query(SandboxSpace).filter_by(
                    thread_id=thread_id, user_id=user_id
                ).first()
            except Exception as e:
                logger.warning("Failed to query SandboxSpace: %s", e)

        data_root = _resolve_sandbox_data_root(settings)

        if space is not None:
            # 有历史记录
            container_name = space.container_name or f"oh-sandbox-{user_id}-{space.id}"

            if space.status == "suspended":
                # 尝试恢复挂起的容器
                session = DockerSandboxSession(
                    settings=settings,
                    container_name=container_name,
                    host_workspace=space.host_workspace_path,
                    host_home=space.host_home_path,
                    host_bin=space.host_bin_path,
                )
                try:
                    await session.resume()
                    _sandbox_registry[key] = session
                    space.status = "running"
                    space.last_active_at = datetime.datetime.utcnow()
                    if db_session:
                        db_session.commit()
                    logger.info("Sandbox resumed: %s", container_name)
                    return session
                except Exception as e:
                    logger.warning("Resume failed, will recreate: %s", e)
                    # 恢复失败，销毁旧容器后重新创建
                    await session.destroy()

            elif space.status == "running":
                # DB 说运行中但内存没有 → Worker 可能重启过，尝试连接
                session = DockerSandboxSession(
                    settings=settings,
                    container_name=container_name,
                    host_workspace=space.host_workspace_path,
                    host_home=space.host_home_path,
                    host_bin=space.host_bin_path,
                )
                # 检查容器是否真的在运行
                if await _is_container_running(container_name):
                    session._running = True
                    _sandbox_registry[key] = session
                    _touch_last_active(db_session, thread_id)
                    logger.info("Sandbox reconnected: %s", container_name)
                    return session
                else:
                    # 容器已不在，需要重建
                    await session.destroy()

            # 空间存在但容器需要重建
            workspace_path = space.host_workspace_path
            home_path = space.host_home_path
            bin_path = space.host_bin_path
            space_id = space.id
        else:
            # ── 路径 3: 全新空间 ──
            space_id = uuid.uuid4().hex[:16]
            workspace_path, home_path, bin_path = _ensure_persistent_dirs(
                data_root, user_id, space_id
            )

        container_name = f"oh-sandbox-{user_id}-{space_id}"

        # 创建或更新 DB 记录
        if db_session is not None:
            try:
                from models import SandboxSpace
                if space is None:
                    space = SandboxSpace(
                        id=space_id,
                        user_id=user_id,
                        thread_id=thread_id,
                        host_workspace_path=workspace_path,
                        host_home_path=home_path,
                        host_bin_path=bin_path,
                        container_name=container_name,
                        status="running",
                    )
                    db_session.add(space)
                else:
                    space.container_name = container_name
                    space.status = "running"
                    space.last_active_at = datetime.datetime.utcnow()
                db_session.commit()
            except Exception as e:
                logger.warning("Failed to persist SandboxSpace: %s", e)
                db_session.rollback()

        # 确保持久化目录存在
        _ensure_persistent_dirs(data_root, user_id, space_id)

        # 启动容器
        session = DockerSandboxSession(
            settings=settings,
            container_name=container_name,
            host_workspace=workspace_path,
            host_home=home_path,
            host_bin=bin_path,
        )
        await session.start()
        _sandbox_registry[key] = session
        logger.info("Sandbox created: %s (space=%s)", container_name, space_id)
        return session


async def suspend_sandbox(user_id: int, thread_id: str, db_session=None) -> None:
    """挂起沙箱容器（不销毁），更新 DB 状态为 suspended。"""
    key = _registry_key(user_id, thread_id)

    session = _sandbox_registry.pop(key, None)
    if session is None:
        return

    await session.suspend()

    if db_session is not None:
        try:
            from models import SandboxSpace
            space = db_session.query(SandboxSpace).filter_by(
                thread_id=thread_id, user_id=user_id
            ).first()
            if space:
                space.status = "suspended"
                space.last_active_at = datetime.datetime.utcnow()
                db_session.commit()
        except Exception as e:
            logger.warning("Failed to update SandboxSpace status: %s", e)
            db_session.rollback()


async def destroy_sandbox(user_id: int, thread_id: str, db_session=None) -> None:
    """彻底销毁沙箱容器，更新 DB 状态为 destroyed。持久化目录保留。"""
    key = _registry_key(user_id, thread_id)

    session = _sandbox_registry.pop(key, None)
    if session is not None:
        await session.destroy()

    if db_session is not None:
        try:
            from models import SandboxSpace
            space = db_session.query(SandboxSpace).filter_by(
                thread_id=thread_id, user_id=user_id
            ).first()
            if space:
                space.status = "destroyed"
                space.destroyed_at = datetime.datetime.utcnow()
                db_session.commit()
        except Exception as e:
            logger.warning("Failed to update SandboxSpace status: %s", e)
            db_session.rollback()


# ═══ 兼容旧接口 (供 environment.py 等模块使用) ═══

async def stop_docker_sandbox() -> None:
    """旧接口兼容：不做任何事。生命周期现在由 suspend_sandbox 管理。"""
    pass


def _touch_last_active(db_session, thread_id: str) -> None:
    """更新 SandboxSpace 的 last_active_at 时间戳。"""
    if db_session is None:
        return
    try:
        from models import SandboxSpace
        space = db_session.query(SandboxSpace).filter_by(thread_id=thread_id).first()
        if space:
            space.last_active_at = datetime.datetime.utcnow()
            db_session.commit()
    except Exception:
        pass


async def _is_container_running(container_name: str) -> bool:
    """检查 Docker 容器是否正在运行。"""
    import shutil
    docker = shutil.which("docker") or "docker"
    try:
        process = await asyncio.create_subprocess_exec(
            docker, "inspect", "-f", "{{.State.Running}}", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
        return stdout.decode().strip() == "true"
    except Exception:
        return False
