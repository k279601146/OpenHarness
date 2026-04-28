"""Docker-based sandbox backend for isolated tool execution.

重构版：支持三层持久化挂载、容器挂起/恢复、进程级安全加固。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openharness.config import Settings
from openharness.platforms import get_platform, get_platform_capabilities
from openharness.sandbox.adapter import SandboxAvailability, SandboxUnavailableError

logger = logging.getLogger(__name__)


def get_docker_availability(settings: Settings) -> SandboxAvailability:
    """Check whether Docker can be used as a sandbox backend."""
    if not settings.sandbox.enabled or settings.sandbox.backend != "docker":
        return SandboxAvailability(
            enabled=False, available=False, reason="Docker sandbox is not enabled"
        )

    platform_name = get_platform()
    capabilities = get_platform_capabilities(platform_name)
    if not capabilities.supports_docker_sandbox:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason=f"Docker sandbox is not supported on platform {platform_name}",
        )

    docker = shutil.which("docker")
    if not docker:
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason="Docker CLI not found; install Docker Desktop or Docker Engine",
        )

    try:
        subprocess.run(
            [docker, "info"],
            capture_output=True,
            timeout=5,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return SandboxAvailability(
            enabled=True,
            available=False,
            reason="Docker daemon is not running",
            command=docker,
        )

    return SandboxAvailability(enabled=True, available=True, command=docker)


@dataclass
class DockerSandboxSession:
    """管理一个长期运行的 Docker 容器，对应一个沙箱空间。

    重构后使用三层持久化挂载替代单一 workspace 绑定。
    """

    settings: Settings
    container_name: str
    host_workspace: str   # 宿主机 workspace 目录
    host_home: str        # 宿主机 user-home 目录
    host_bin: str         # 宿主机 local-bin 目录
    _running: bool = field(init=False, default=False)

    @property
    def is_running(self) -> bool:
        return self._running

    def map_to_host_path(self, container_path: str | Path) -> Path:
        """将容器内路径映射回宿主机路径，支持三层持久化目录。"""
        cp = str(container_path).replace("\\", "/")
        
        # 处理 ~ 号 (容器内)
        if cp.startswith("~/"):
            cp = cp.replace("~/", "/home/sandbox/", 1)
        elif cp == "~":
            cp = "/home/sandbox"

        # 映射逻辑
        if cp.startswith("/workspace"):
            rel = cp[len("/workspace"):].lstrip("/")
            return Path(self.host_workspace) / rel
        if cp.startswith("/home/sandbox"):
            rel = cp[len("/home/sandbox"):].lstrip("/")
            return Path(self.host_home) / rel
        if cp.startswith("/usr/local/sandbox-bin"):
            rel = cp[len("/usr/local/sandbox-bin"):].lstrip("/")
            return Path(self.host_bin) / rel
            
        # 如果是相对路径，默认相对于 /workspace (即 host_workspace)
        if not cp.startswith("/"):
            return Path(self.host_workspace) / cp
            
        # 其他路径保持原样
        return Path(cp)

    def _to_container_path(self, host_path: str | Path) -> str:
        """根据宿主机路径动态判断所属持久化层并转换为容器内路径。"""
        hp = Path(host_path).resolve()
        
        # 匹配 workspace 层
        try:
            rel = hp.relative_to(Path(self.host_workspace).resolve())
            return str(Path("/workspace") / rel).replace("\\", "/")
        except ValueError:
            pass
            
        # 匹配 home 层
        try:
            rel = hp.relative_to(Path(self.host_home).resolve())
            return str(Path("/home/sandbox") / rel).replace("\\", "/")
        except ValueError:
            pass
            
        # 匹配 bin 层
        try:
            rel = hp.relative_to(Path(self.host_bin).resolve())
            return str(Path("/usr/local/sandbox-bin") / rel).replace("\\", "/")
        except ValueError:
            pass
            
        return "/workspace"

    def _build_run_argv(self) -> list[str]:
        """构建 docker run 启动参数，包含三层持久化挂载和安全加固。"""
        docker = shutil.which("docker") or "docker"
        sandbox = self.settings.sandbox
        docker_cfg = sandbox.docker

        argv = [
            docker, "run", "-d",
            "--name", self.container_name,
        ]

        # 网络策略：只有在明确定义了域名过滤规则时才断网（当前 Docker 驱动暂不支持域名级细粒度过滤）
        if (sandbox.network.allowed_domains and len(sandbox.network.allowed_domains) > 0) or \
           (sandbox.network.denied_domains and len(sandbox.network.denied_domains) > 0):
            logger.warning(
                "Docker sandbox does not enforce domain-level filtering yet; "
                "falling back to network=none for security."
            )
            argv.extend(["--network", "none"])
        else:
            argv.extend(["--network", "bridge"])

        # 资源限制
        if docker_cfg.cpu_limit > 0:
            argv.extend(["--cpus", str(docker_cfg.cpu_limit)])
        if docker_cfg.memory_limit:
            argv.extend(["--memory", docker_cfg.memory_limit])

        # 安全加固：适当放松权限以支持开发工具 (如 sudo, ping, chown)
        # 仅显式禁用极高风险的系统管理权限，保留默认的开发者友好权限
        argv.extend(["--cap-drop", "SYS_ADMIN"])
        argv.extend(["--cap-drop", "NET_ADMIN"])

        # ═══ 三层持久化挂载 ═══
        argv.extend(["-v", f"{self.host_workspace}:/workspace"])
        argv.extend(["-v", f"{self.host_home}:/home/sandbox"])
        argv.extend(["-v", f"{self.host_bin}:/usr/local/sandbox-bin"])
        argv.extend(["-w", "/workspace"])

        # 额外挂载
        for mount in docker_cfg.extra_mounts:
            argv.extend(["-v", mount])

        # 固定环境变量：保证跨容器生命周期一致性
        persistence_env = self._get_base_env()
        for key, value in persistence_env.items():
            argv.extend(["-e", f"{key}={value}"])

        # UID/GID 动态映射
        uid = os.getuid() if hasattr(os, "getuid") else 0
        gid = os.getgid() if hasattr(os, "getgid") else 0

        # 以 root 启动容器，动态对齐 ohuser UID
        argv.extend(["-u", "0"])

        if uid != 0 and gid != 0:
            # Linux 生产环境：ohuser UID/GID 对齐宿主机进程
            setup_cmd = (
                f"groupmod -o -g {gid} ohuser && "
                f"usermod -o -u {uid} -d /home/sandbox ohuser && "
                f"chown -R ohuser:ohuser /home/sandbox && "
                f"exec tail -f /dev/null"
            )
        else:
            # Windows 开发环境：root 直接运行
            setup_cmd = "exec tail -f /dev/null"

        argv.extend([docker_cfg.image, "/bin/bash", "-c", setup_cmd])
        return argv

    async def start(self) -> None:
        """创建并启动沙箱容器（不使用 --rm，支持后续 suspend/resume）。"""
        from openharness.sandbox.docker_image import ensure_image_available

        docker_cfg = self.settings.sandbox.docker
        available = await ensure_image_available(
            docker_cfg.image, docker_cfg.auto_build_image
        )
        if not available:
            raise SandboxUnavailableError(
                f"Docker image {docker_cfg.image!r} is not available and "
                "auto_build_image is disabled"
            )

        argv = self._build_run_argv()
        logger.info("Starting Docker sandbox: %s", " ".join(argv))

        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            msg = stderr.decode("utf-8", errors="replace").strip()
            raise SandboxUnavailableError(f"Failed to start Docker sandbox: {msg}")

        self._running = True
        logger.info("Docker sandbox started: %s", self.container_name)

    async def suspend(self) -> None:
        """挂起（stop）容器但 不删除 它，以便后续快速恢复。"""
        if not self._running:
            return
        docker = shutil.which("docker") or "docker"
        try:
            process = await asyncio.create_subprocess_exec(
                docker, "stop", "-t", "5", self.container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=15)
        except (asyncio.TimeoutError, OSError) as exc:
            logger.warning("Error suspending Docker sandbox: %s", exc)
        finally:
            self._running = False
            logger.info("Docker sandbox suspended: %s", self.container_name)

    async def resume(self) -> None:
        """恢复一个已挂起的容器。"""
        docker = shutil.which("docker") or "docker"
        process = await asyncio.create_subprocess_exec(
            docker, "start", self.container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            msg = stderr.decode("utf-8", errors="replace").strip()
            raise SandboxUnavailableError(f"Failed to resume Docker sandbox: {msg}")
        self._running = True
        logger.info("Docker sandbox resumed: %s", self.container_name)

    async def destroy(self) -> None:
        """彻底停止并删除容器（但保留宿主机持久化目录）。"""
        docker = shutil.which("docker") or "docker"
        try:
            process = await asyncio.create_subprocess_exec(
                docker, "rm", "-f", self.container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=15)
        except (asyncio.TimeoutError, OSError) as exc:
            logger.warning("Error destroying Docker sandbox: %s", exc)
        finally:
            self._running = False
            logger.info("Docker sandbox destroyed: %s", self.container_name)

    def destroy_sync(self) -> None:
        """同步销毁，用于 atexit 清理。"""
        if not self._running:
            return
        docker = shutil.which("docker") or "docker"
        try:
            subprocess.run(
                [docker, "rm", "-f", self.container_name],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        finally:
            self._running = False

    async def exec_command(
        self,
        argv: list[str],
        *,
        cwd: str | Path,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
        env: dict[str, str] | None = None,
    ) -> asyncio.subprocess.Process:
        """在沙箱容器内执行命令。"""
        if not self._running:
            raise SandboxUnavailableError("Docker sandbox session is not running")

        docker = shutil.which("docker") or "docker"
        cmd: list[str] = [docker, "exec"]
        
        # 核心：将持久化环境变量注入 exec 会话，否则 skillhub 等路径会失效
        base_env = self._get_base_env()
        if env:
            base_env.update(env)
            
        for key, value in base_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend(["-w", self._to_container_path(Path(cwd).resolve())])

        cmd.append(self.container_name)
        cmd.extend(argv)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
        return process

    def _get_base_env(self) -> dict[str, str]:
        """获取沙箱基础环境变量。"""
        docker_cfg = self.settings.sandbox.docker
        env = {
            "HOME": "/home/sandbox",
            "PATH": "/usr/local/sandbox-bin:/home/sandbox/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "XDG_CONFIG_HOME": "/home/sandbox/.config",
            "XDG_DATA_HOME": "/home/sandbox/.local/share",
            "XDG_CACHE_HOME": "/home/sandbox/.cache",
            "PYTHONUNBUFFERED": "1",
        }
        # 混入额外配置
        env.update(docker_cfg.extra_env)
        return env

