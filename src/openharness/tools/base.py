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
    from openharness.engine.messages import ImageBlock
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
    images: list[ImageBlock] = field(default_factory=list)
    additional_contexts: list[str] = field(default_factory=list)
    structured_output: Any = None


ToolMiddlewareFn = Callable[
    ["BaseTool", BaseModel, ToolExecutionContext, Callable[[BaseModel, ToolExecutionContext], Awaitable[ToolResult]]],
    Awaitable[ToolResult],
]


class BaseTool(ABC):
    """Base class for all OpenHarness tools."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None = None
    display_name: str | None = None
    default_start_message: str | None = None
    parallel_safe: bool = True
    execution_group: str | None = None
    timeout_ms: int | None = None
    
    # [Optimize] 显式标记工具是否必须在沙箱中运行
    # False: 默认在宿主机执行（节省资源）
    # True: 必须启动/使用 E2B 沙箱（安全、隔离、环境依赖）
    requires_sandbox: bool = False

    @abstractmethod
    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """Execute the tool."""

    def when(self, selection_context: Any) -> bool | None:
        """Optional step-level admission predicate (`ResolvedToolSet` contract).

        Return `True` or `False` to explicitly admit or exclude this tool for the
        current step, or `None` to defer to the default context rules.
        """
        del selection_context
        return None

    def project_content(self, result: ToolResult, context: ToolExecutionContext) -> ToolResult:
        """First-stage output projection before post-execute hooks and spill pruning."""
        del context
        return result

    def finalize_content(self, result: ToolResult, context: ToolExecutionContext) -> ToolResult:
        """Second-stage output finalization after post-execute hooks and spill policy."""
        del context
        if self.output_model is not None and not result.is_error and result.structured_output is not None:
            if isinstance(result.structured_output, BaseModel):
                validated = result.structured_output.model_dump(mode="json")
            else:
                validated = self.output_model.model_validate(result.structured_output).model_dump(mode="json")
            meta = dict(result.metadata or {})
            meta.setdefault("structured_output", validated)
            return ToolResult(
                output=result.output,
                is_error=result.is_error,
                metadata=meta,
                images=list(result.images),
                additional_contexts=list(result.additional_contexts),
                structured_output=validated,
            )
        return result

    def output_schema(self) -> dict[str, Any] | None:
        """Return sanitized JSON schema for the tool's structured output, if declared."""
        if self.output_model is None:
            return None
        schema = _inline_local_json_schema_refs(self.output_model.model_json_schema())
        return sanitize_tool_json_schema(schema)

    def is_read_only(self, arguments: BaseModel) -> bool:
        """Return whether the invocation is read-only."""
        del arguments
        return False

    def is_concurrency_safe(self, arguments: BaseModel) -> bool:
        """Return whether this invocation may execute concurrently in a batch.

        Tools with ``parallel_safe = False`` or an explicit ``execution_group``
        run sequentially relative to exclusive barriers unless overridden.
        """
        del arguments
        return bool(self.parallel_safe and self.execution_group is None)

    def display_label(self) -> str:
        """Return a user-facing tool label without changing the input schema."""
        return self.display_name or self.name.replace("_", " ")

    def start_message(self) -> str:
        """Return a user-facing start message without changing the input schema."""
        return self.default_start_message or f"正在执行工具 {self.name}..."

    def to_api_schema(self) -> dict[str, Any]:
        """Return the tool schema expected by the Messages API."""
        schema = _inline_local_json_schema_refs(self.input_model.model_json_schema())
        schema = sanitize_tool_json_schema(schema)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }


def sanitize_tool_json_schema(schema: Any) -> Any:
    """Sanitize JSON Schema for Gemini / OpenAI / Anthropic function declaration compatibility.

    Ensures that:
    1. Every ``type: "array"`` contains a valid ``items`` schema (Gemini throws 400 if missing).
    2. Any Draft 2020-12 ``prefixItems`` (e.g. from Pydantic ``tuple[...]``) is normalized to ``items``.
    3. Nested properties, items, anyOf/oneOf/allOf, and additionalProperties are recursively sanitized.
    """
    if not isinstance(schema, dict):
        if isinstance(schema, list):
            return [sanitize_tool_json_schema(item) for item in schema]
        return schema

    sanitized = deepcopy(schema)

    # Clean array schemas
    if sanitized.get("type") == "array":
        items = sanitized.get("items")
        prefix_items = sanitized.pop("prefixItems", None)
        if items is None or items == {}:
            if isinstance(prefix_items, list) and prefix_items:
                sanitized["items"] = sanitize_tool_json_schema(prefix_items[0])
            else:
                sanitized["items"] = {"type": "string"}
        else:
            sanitized["items"] = sanitize_tool_json_schema(items)

    if isinstance(sanitized.get("properties"), dict):
        sanitized["properties"] = {
            k: sanitize_tool_json_schema(v)
            for k, v in sanitized["properties"].items()
        }

    if isinstance(sanitized.get("additionalProperties"), dict):
        sanitized["additionalProperties"] = sanitize_tool_json_schema(sanitized["additionalProperties"])

    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(sanitized.get(key), list):
            sanitized[key] = [sanitize_tool_json_schema(item) for item in sanitized[key]]

    return sanitized


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
    """Map tool names to implementations and execution middlewares."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._middlewares: list[ToolMiddlewareFn] = []

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def add_middleware(self, middleware: ToolMiddlewareFn) -> None:
        """Register an around-execute tool middleware."""
        if middleware not in self._middlewares:
            self._middlewares.append(middleware)

    @property
    def middlewares(self) -> tuple[ToolMiddlewareFn, ...]:
        """Return registered tool middlewares in execution order."""
        return tuple(self._middlewares)

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
