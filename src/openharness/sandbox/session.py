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
import shlex
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openharness.config import Settings
    from openharness.sandbox.e2b_backend import E2BSandboxSession

logger = logging.getLogger(__name__)

# ═══ 进程级沙箱注册表 ═══
# key = "user_id:thread_id", value = E2BSandboxSession
_sandbox_registry: dict[str, E2BSandboxSession] = {}
_registry_lock = asyncio.Lock()


def _registry_key(user_id: int, thread_id: str) -> str:
    return f"{user_id}:{thread_id}"


def get_active_sandbox(user_id: int, thread_id: str) -> E2BSandboxSession | None:
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


def get_sandbox_session() -> E2BSandboxSession | None:
    """自动获取当前上下文的活跃沙箱(兼任原有的 get_docker_sandbox)。"""
    try:
        # 尝试从 Engine 上下文中自动获取 UID/TID
        # 这种设计允许工具层无需显式传递上下文也能透明路由到沙箱
        from openharness.contextvars import active_user_id, active_thread_id
        uid = active_user_id.get()
        tid = active_thread_id.get()
        if uid and tid:
            return get_active_sandbox(uid, tid)
    except (ImportError, Exception):
        pass
    return None


# Alias for backward compatibility during refactoring
get_docker_sandbox = get_sandbox_session


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
    """创建三层持久化目录，返回 (workspace_path, home_path, bin_path)。
    
    重构：workspace 与 thread 绑定，home 与 bin 与 user 绑定以实现跨任务持久性。
    """
    user_base = data_root / str(user_id)
    thread_base = user_base / space_id
    
    workspace = thread_base / "workspace"
    # 变更为用户全局共享资源区，实现跨 thread 可用
    home = user_base / "shared_assets" / "user-home"
    local_bin = user_base / "shared_assets" / "local-bin"

    for d in (workspace, home, local_bin):
        d.mkdir(parents=True, exist_ok=True)

    return str(workspace), str(home), str(local_bin)


async def _ensure_imagegen_skill_in_sandbox(session: E2BSandboxSession) -> None:
    """Sync the bundled imagegen skill package into the sandbox user skills dir."""
    source_dir = Path(__file__).resolve().parents[1] / "skills" / "bundled" / "content" / "imagegen"
    if not source_dir.is_dir():
        logger.warning("Bundled imagegen skill package not found: %s", source_dir)
        return

    target_root = "/home/user/.agents/skills/imagegen"
    try:
        await session.exec_command(f"mkdir -p {shlex.quote(target_root)}")
        for root, dirs, files in os.walk(source_dir):
            root_path = Path(root)
            rel_dir = root_path.relative_to(source_dir).as_posix()
            sandbox_dir = target_root if rel_dir == "." else f"{target_root}/{rel_dir}"
            await session.exec_command(f"mkdir -p {shlex.quote(sandbox_dir)}")

            for dirname in dirs:
                await session.exec_command(f"mkdir -p {shlex.quote(f'{sandbox_dir}/{dirname}')}")

            for filename in files:
                local_path = root_path / filename
                sandbox_path = f"{sandbox_dir}/{filename}"
                content = local_path.read_bytes()
                if hasattr(session, "write_file_binary"):
                    await session.write_file_binary(sandbox_path, content)
                else:
                    await session.write_file(sandbox_path, content.decode("utf-8", errors="replace"))
        await session.exec_command(f"chmod +x {shlex.quote(target_root + '/scripts/image_gen.py')} || true")
        logger.info("Synced bundled imagegen skill to sandbox: %s", target_root)
    except Exception as exc:
        logger.warning("Failed to sync bundled imagegen skill to sandbox: %s", exc)



async def get_or_start_sandbox(
    settings: Settings,
    user_id: int,
    thread_id: str,
    db_session=None,
) -> E2BSandboxSession | None:
    """获取或启动沙箱。核心复用逻辑：

    1. 内存注册表命中 → 直接复用
    2. DB 中有 suspended 记录 → 尝试重连会话
    3. 无记录 → 新建沙箱空间 + 启动 E2B 实例
    """
    from openharness.sandbox.e2b_backend import (
        E2BSandboxSession,
        get_e2b_availability,
    )

    # 前置检查：E2B 是否可用
    availability = get_e2b_availability(settings)
    if not availability.available:
        if settings.sandbox.fail_if_unavailable:
            from openharness.sandbox.adapter import SandboxUnavailableError
            raise SandboxUnavailableError(
                availability.reason or "E2B sandbox is unavailable"
            )
        logger.warning("E2B sandbox unavailable: %s", availability.reason)
        return None

    key = _registry_key(user_id, thread_id)

    async with _registry_lock:
        # ── 路径 1: 内存命中 ──
        existing = _sandbox_registry.get(key)
        if existing is not None and existing.is_running:
            logger.info("Sandbox reused from registry: %s", existing.sandbox_id)
            _touch_last_active(db_session, thread_id)
            await _ensure_imagegen_skill_in_sandbox(existing)
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
        from openharness.skills.loader import get_community_skills_dir
        community_skills = str(get_community_skills_dir())

        if space is not None:
            # 有历史记录
            # 将 container_name 重构为考虑复用 e2b session 逻辑
            
            if space.status == "suspended":
                # 尝试恢复挂起的容器
                session = E2BSandboxSession(
                    settings=settings,
                    template_id=settings.sandbox.template_id,
                    sandbox_id=space.container_name, # E2B 把 container_name 用作 sandbox_id 存储
                )
                try:
                    await session.resume()
                    _sandbox_registry[key] = session
                    space.status = "running"
                    space.last_active_at = datetime.datetime.utcnow()
                    if db_session:
                        db_session.commit()
                    logger.info("Sandbox resumed: %s", space.container_name)
                    await _ensure_imagegen_skill_in_sandbox(session)
                    return session
                except Exception as e:
                    logger.warning("Resume failed, will recreate: %s", e)
                    # 恢复失败，新建
                    session = E2BSandboxSession(
                        settings=settings,
                        template_id=settings.sandbox.template_id
                    )
                    await session.start()
                    space.container_name = session.sandbox_id
                    space.status = "running"
                    space.last_active_at = datetime.datetime.utcnow()
                    _sandbox_registry[key] = session
                    if db_session:
                        db_session.commit()
                    await _ensure_imagegen_skill_in_sandbox(session)
                    return session

            elif space.status == "running":
                session = E2BSandboxSession(
                    settings=settings,
                    template_id=settings.sandbox.template_id,
                    sandbox_id=space.container_name,
                )
                try:
                    await session.resume() # E2B 支持用 reconnect
                    _sandbox_registry[key] = session
                    _touch_last_active(db_session, thread_id)
                    logger.info("Sandbox reconnected: %s", space.container_name)
                    await _ensure_imagegen_skill_in_sandbox(session)
                    return session
                except Exception:
                    # 重建
                    session = E2BSandboxSession(
                        settings=settings,
                        template_id=settings.sandbox.template_id
                    )
                    await session.start()
                    space.container_name = session.sandbox_id
                    space.status = "running"
                    space.last_active_at = datetime.datetime.utcnow()
                    _sandbox_registry[key] = session
                    if db_session:
                        db_session.commit()
                    await _ensure_imagegen_skill_in_sandbox(session)
                    return session

            space_id = space.id
        else:
            # 全新空间
            space_id = uuid.uuid4().hex[:16]
            session = E2BSandboxSession(
                settings=settings,
                template_id=settings.sandbox.template_id
            )
            await session.start()
            
            # [Optimization] Late Startup Sync: 将本地工作区的文件同步到新启动的沙箱中
            try:
                # 尝试定位本地工作区
                current = Path(__file__).resolve()
                project_root = None
                for parent in current.parents:
                    if (parent / "apps").is_dir():
                        project_root = parent
                        break
                
                if project_root:
                    local_ws = project_root / "temp_workspaces" / thread_id
                    if local_ws.exists() and local_ws.is_dir():
                        logger.info("Syncing local workspace %s to new sandbox...", local_ws)
                        # 遍历本地工作区并上传文件
                        for root, _, files in os.walk(local_ws):
                            for file in files:
                                local_file_path = Path(root) / file
                                # 计算相对于本地工作区的相对路径
                                rel_path = local_file_path.relative_to(local_ws)
                                sandbox_path = f"/home/user/{rel_path.as_posix()}"
                                
                                try:
                                    content = local_file_path.read_bytes()
                                    if hasattr(session, "write_file_binary"):
                                        await session.write_file_binary(sandbox_path, content)
                                    elif hasattr(session, "upload"):
                                        await session.upload(sandbox_path, content)
                                except Exception as fe:
                                    logger.warning("Failed to sync file %s: %s", file, fe)
            except Exception as se:
                logger.warning("Late Startup Sync failed: %s", se)

            # 解析持久化映射路径 (即使是 E2B 也维持本地镜像目录，用于加速读取和 API 导出)
            data_root = _resolve_sandbox_data_root(settings)
            ws_path, hm_path, bin_path = _ensure_persistent_dirs(data_root, user_id, space_id)

            # 创建或更新 DB 记录
            if db_session is not None:
                try:
                    from models import SandboxSpace
                    space = SandboxSpace(
                        id=space_id,
                        user_id=user_id,
                        thread_id=thread_id,
                        container_name=session.sandbox_id,
                        status="running",
                        host_workspace_path=ws_path,
                        host_home_path=hm_path,
                        host_bin_path=bin_path,
                    )
                    db_session.add(space)
                    db_session.commit()
                except Exception as e:
                    logger.warning("Failed to persist SandboxSpace: %s", e)
                    db_session.rollback()
                    
            _sandbox_registry[key] = session
            logger.info("Sandbox created: %s (space=%s)", session.sandbox_id, space_id)
            await _ensure_imagegen_skill_in_sandbox(session)
            return session
            
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


async def stop_docker_sandbox() -> None:
    """Legacy no-op function."""
    pass


def _touch_last_active(db_session, thread_id: str) -> None:
    """Update last_active_at timestamp for the sandbox space."""
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
