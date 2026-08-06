"""Tool abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from copy import deepcopy
from typing import Any, Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from openharness.hooks.executor import HookExecutor


class CancellationToken:
    """Shared cancellation signal for a running query/tool turn."""

    def __init__(self) -> None:
        import asyncio

        self._event = asyncio.Event()
        self._reason: str | None = None

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        self._reason = reason or self._reason or "cancelled"
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


@dataclass
class ToolExecutionContext:
    """Shared execution context for tool invocations."""

    cwd: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    hook_executor: HookExecutor | None = None
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    cancellation_token: CancellationToken | None = None


@dataclass(frozen=True)
class ToolResult:
    """Normalized tool execution result."""

    output: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Base class for all OpenHarness tools."""

    name: str
    description: str
    input_model: type[BaseModel]
    display_name: str | None = None
    default_start_message: str | None = None
    parallel_safe: bool = True
    execution_group: str | None = None
    
    # [Optimize] 显式标记工具是否必须在沙箱中运行
    # False: 默认在宿主机执行（节省资源）
    # True: 必须启动/使用 E2B 沙箱（安全、隔离、环境依赖）
    requires_sandbox: bool = False

    @abstractmethod
    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """Execute the tool."""

    def is_read_only(self, arguments: BaseModel) -> bool:
        """Return whether the invocation is read-only."""
        del arguments
        return False

    def display_label(self) -> str:
        """Return a user-facing tool label without changing the input schema."""
        return self.display_name or self.name.replace("_", " ")

    def start_message(self) -> str:
        """Return a user-facing start message without changing the input schema."""
        return self.default_start_message or f"正在执行工具 {self.name}..."

    def to_api_schema(self) -> dict[str, Any]:
        """Return the tool schema expected by the Messages API."""
        schema = _inline_local_json_schema_refs(self.input_model.model_json_schema())
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }


def _inline_local_json_schema_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline local $defs refs for model/tool APIs with weak $ref support."""
    definitions = schema.get("$defs") if isinstance(schema.get("$defs"), dict) else {}
    if not definitions:
        return schema

    def resolve(value: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(value, list):
            return [resolve(item, stack) for item in value]
        if not isinstance(value, dict):
            return value
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.rsplit("/", 1)[-1]
            if name in definitions and name not in stack:
                resolved = resolve(deepcopy(definitions[name]), (*stack, name))
                siblings = {key: item for key, item in value.items() if key != "$ref"}
                if siblings and isinstance(resolved, dict):
                    resolved.update(resolve(siblings, stack))
                return resolved
        return {key: resolve(item, stack) for key, item in value.items() if key != "$defs"}

    return resolve(schema)


class ToolRegistry:
    """Map tool names to implementations."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Return a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def to_api_schema(self, *, cache_last: bool = False) -> list[dict[str, Any]]:
        """Return all tool schemas in API format."""
        schemas = [tool.to_api_schema() for tool in self._tools.values()]
        if cache_last and schemas:
            # [Claude Code Pattern 13.2] 为最后一个工具注入缓存标记
            schemas[-1]["cache_control"] = {"type": "ephemeral"}
        return schemas
