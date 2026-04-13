"""Tool abstractions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel


@dataclass
class ToolExecutionContext:
    """Shared execution context for tool invocations."""

    cwd: Path
    metadata: dict[str, Any] = field(default_factory=dict)


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

    @abstractmethod
    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """Execute the tool."""

    def is_read_only(self, arguments: BaseModel) -> bool:
        """Return whether the invocation is read-only."""
        del arguments
        return False

    def to_api_schema(self) -> dict[str, Any]:
        """Return the tool schema expected by the Messages API with global reasoning injection."""
        schema = self.input_model.model_json_schema()
        
        # ====== 全局意图注入 (Manus/Loveart 级架构) ======
        # 强制所有工具都具备 purpose 字段，让模型每次调用工具都必须向用户解释动作目的
        if "properties" in schema:
            schema["properties"]["purpose"] = {
                "type": "string",
                "description": "对该具体操作的功能及其用途进行对话式说明（默认使用中文）。此文本将直接展示给用户。"
            }
            # 强迫大模型必须输出该字段，否则不合法
            if "required" not in schema:
                schema["required"] = []
            if "purpose" not in schema["required"]:
                schema["required"].append("purpose")
                
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }


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

    def to_api_schema(self) -> list[dict[str, Any]]:
        """Return all tool schemas in API format."""
        return [tool.to_api_schema() for tool in self._tools.values()]
