"""E2B-based sandbox backend for isolated tool execution."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openharness.config import Settings
from openharness.sandbox.adapter import SandboxAvailability, SandboxUnavailableError

logger = logging.getLogger(__name__)


def _normalize_e2b_cwd(cwd: str | Path | None) -> str:
    if cwd is None or not str(cwd).strip():
        return "/home/user"

    value = str(cwd).strip().replace("\\", "/")
    if value in {".", "~"}:
        return "/home/user"
    if len(value) >= 2 and value[1] == ":":
        return "/home/user"
    if value.startswith("/"):
        return value.rstrip("/") or "/home/user"
    return f"/home/user/{value.strip('/')}"


def get_e2b_availability(settings: Settings) -> SandboxAvailability:
    """Check whether E2B can be used as a sandbox backend."""
    # Temporarily we might just pretend we use E2B if backend is 'e2b' or if we force it.
    if not settings.sandbox.enabled:
        return SandboxAvailability(
            enabled=False, available=False, reason="Sandbox is not enabled"
        )
        
    if not os.environ.get("E2B_API_KEY"):
        return SandboxAvailability(
            enabled=True, available=False, reason="E2B_API_KEY is not set in environment"
        )
        
    return SandboxAvailability(enabled=True, available=True)


@dataclass
class E2BSandboxSession:
    """管理 E2B Sandbox 会话。
    
    使用 e2b Python SDK 完全替代 Docker run/exec/bind mount。
    不再依赖宿主机路径，所有文件操作使用 e2b files API。
    """

    settings: Settings
    template_id: str = "" # 由 Settings 或 ENV 注入, 不再硬编码默认值
    sandbox_id: str | None = None
    _sandbox: Any = field(init=False, default=None)

    @property
    def is_running(self) -> bool:
        return self._sandbox is not None

    async def start(self) -> None:
        """通过 E2B Sandbox.create() 启动远程沙箱"""
        from e2b_code_interpreter import Sandbox
        logger.info(f"Starting E2B sandbox with template: {self.template_id}")
        
        # 增加重试机制，应对 E2B API 偶发性的连接超时或协议错误
        max_retries = 3
        last_error = None
        
        loop = asyncio.get_event_loop()
        for attempt in range(max_retries):
            try:
                # E2B SDK 的创键操作是阻塞的，使用 executor 避免阻塞事件循环
                self._sandbox = await loop.run_in_executor(
                    None, 
                    lambda: Sandbox.create(
                        self.template_id, 
                        timeout=self.settings.sandbox.idle_timeout_seconds,
                        lifecycle={
                            "on_timeout": "pause",
                            "auto_resume": self.settings.sandbox.auto_resume,
                        }
                    )
                )
                self.sandbox_id = self._sandbox.sandbox_id
                logger.info(f"E2B sandbox started: {self.sandbox_id}")
                return
            except Exception as e:
                last_error = e
                logger.warning(f"E2B sandbox start attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1)) # 指数退避
        
        raise SandboxUnavailableError(f"Failed to start E2B sandbox after {max_retries} attempts: {last_error}")

    async def suspend(self) -> None:
        """对于 E2B 来说挂起可以只是记录 sandbox_id。"""
        if not self._sandbox:
            return
        self.sandbox_id = self._sandbox.sandbox_id
        self._sandbox = None
        logger.info(f"E2B sandbox suspended. sandbox_id: {self.sandbox_id}")

    async def resume(self) -> None:
        """从已有的 sandbox_id 恢复。"""
        from e2b_code_interpreter import Sandbox
        if not self.sandbox_id:
            raise SandboxUnavailableError("No sandbox_id to resume from E2B")
        
        max_retries = 2
        last_error = None
        loop = asyncio.get_event_loop()
        
        for attempt in range(max_retries):
            try:
                self._sandbox = await loop.run_in_executor(
                    None,
                    lambda: Sandbox.connect(self.sandbox_id)
                )
                logger.info(f"E2B sandbox resumed: {self.sandbox_id}")
                return
            except Exception as e:
                last_error = e
                logger.warning(f"E2B sandbox resume attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    
        raise SandboxUnavailableError(f"Failed to resume E2B sandbox: {last_error}")

    async def destroy(self) -> None:
        """彻底终止沙箱"""
        if self._sandbox:
            self._sandbox.kill()
            self._sandbox = None
        elif self.sandbox_id:
            from e2b_code_interpreter import Sandbox
            try:
                sbx = Sandbox.connect(self.sandbox_id)
                sbx.kill()
            except Exception:
                pass
        self.sandbox_id = None
        logger.info("E2B sandbox destroyed")

    def destroy_sync(self) -> None:
        """同步终止"""
        if self._sandbox:
            try:
                self._sandbox.kill()
            except Exception:
                pass
            self._sandbox = None

    async def exec_command(
        self,
        command: str | list[str],
        *,
        cwd: str | Path = "/home/user",
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
        env: dict[str, str] | None = None,
    ) -> Any:
        """在 沙箱容器内执行命令。
        通过包装返回一个类似 Process 的对象，使其能在现有使用 await process.communicate() 的逻辑中运行。
        """
        if not self._sandbox:
            raise SandboxUnavailableError("E2B sandbox session is not running")

        import asyncio

        class MockProcess:
            def __init__(self, e2b_result):
                self.returncode = e2b_result.exit_code
                self._stdout_bytes = e2b_result.stdout.encode('utf-8') if isinstance(e2b_result.stdout, str) else e2b_result.stdout
                self._stderr_bytes = e2b_result.stderr.encode('utf-8') if isinstance(e2b_result.stderr, str) else e2b_result.stderr
                
                # 为了兼容 legacy 逻辑 (communicate)
                self.stdout_str = e2b_result.stdout if isinstance(e2b_result.stdout, str) else e2b_result.stdout.decode('utf-8', errors='ignore')
                self.stderr_str = e2b_result.stderr if isinstance(e2b_result.stderr, str) else e2b_result.stderr.decode('utf-8', errors='ignore')

                # Mock stdout.readline 用的流
                self.stdout = asyncio.StreamReader()
                self.stdout.feed_data(self._stdout_bytes)
                self.stdout.feed_eof()
                
            async def communicate(self):
                return self._stdout_bytes, self._stderr_bytes
                
            async def wait(self):
                return self.returncode
            
            @property
            def stdout_data(self):
                return self.stdout_str

            def terminate(self):
                pass
                
            def kill(self):
                pass

        # 如果是列表则拼接，如果是字符串则直接使用（防止 bash -lc 包装错误）
        if isinstance(command, list):
            cmd_str = " ".join(command)
        else:
            cmd_str = command
        
        # 从 2.0 开始，我们抛弃了 .npm-global 等生硬的 prefix 补丁，
        # 我们在 bootstrap 中直接将 /usr/local 等原生 Node 安装目录授权给 user 用户。
        # 因此，此处无需再向 PATH 中生硬注入任何路径，保持 E2B 原生环境变量的最佳状态即可。
        envs = env.copy() if env else {}
        # envs["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

        sandbox_cwd = _normalize_e2b_cwd(cwd)

        # 兼容老框架中的 async. e2b python 可能是 sync 或者是 e2b-code-interpreter.
        # e2b 提供 AsyncSandbox 吗？如果是 sync 必须用 run_in_executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._sandbox.commands.run(
                    cmd_str,
                    cwd=sandbox_cwd,
                    envs=envs
                )
            )
            return MockProcess(result)
        except Exception as e:
            # 检查是否是 E2B 的命令退出异常 (exit_code != 0)
            # 这种异常不应该抛给上层杀死进程，而应该作为 ToolResult 返回给 Agent 反思
            if hasattr(e, "result"):
                logger.warning(f"E2B command failed (exit code {e.result.exit_code}), letting agent self-heal")
                return MockProcess(e.result)
            
            logger.error(f"E2B system level error: {e}")
            raise SandboxUnavailableError(f"E2B integration error: {e}")

    async def read_file(self, container_path: str) -> str:
        """读取文件为文本字符串"""
        content = await self.read_file_binary(container_path)
        if isinstance(content, bytes):
            return content.decode('utf-8', errors='replace')
        return content

    async def read_file_binary(self, container_path: str) -> bytes:
        """读取文件为原始二进制字节流"""
        if not self._sandbox:
            raise SandboxUnavailableError()
        loop = asyncio.get_event_loop()
        try:
            # E2B sandbox.files.read() 返回的可能是字节或字符串
            content = await loop.run_in_executor(
                None,
                lambda: self._sandbox.files.read(container_path, format="bytes")
            )
            # format="bytes" 保证返回 bytearray，直接返回即可
            return bytes(content) if isinstance(content, (bytearray, memoryview)) else content
        except Exception as e:
            logger.error(f"Failed to read file {container_path} from E2B: {e}")
            raise SandboxUnavailableError(f"Failed to read file: {e}")
        
    async def write_file(self, container_path: str, content: str) -> None:
        if not self._sandbox:
            raise SandboxUnavailableError()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sandbox.files.write(container_path, content))

    async def write_file_binary(self, container_path: str, content: bytes) -> None:
        if not self._sandbox:
            raise SandboxUnavailableError()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sandbox.files.write(container_path, content))
        
    async def list_dir(self, container_path: str):
        if not self._sandbox:
            raise SandboxUnavailableError()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._sandbox.files.list(container_path))
