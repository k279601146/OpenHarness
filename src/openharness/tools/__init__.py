"""Built-in tool registration."""

from openharness.tools.ask_user_question_tool import AskUserQuestionTool
from openharness.tools.agent_tool import AgentTool
from openharness.tools.bash_tool import BashTool
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResult
from openharness.tools.brief_tool import BriefTool
from openharness.tools.config_tool import ConfigTool
from openharness.tools.cron_create_tool import CronCreateTool
from openharness.tools.cron_delete_tool import CronDeleteTool
from openharness.tools.cron_list_tool import CronListTool
from openharness.tools.cron_toggle_tool import CronToggleTool
from openharness.tools.enter_plan_mode_tool import EnterPlanModeTool
from openharness.tools.enter_worktree_tool import EnterWorktreeTool
from openharness.tools.exit_plan_mode_tool import ExitPlanModeTool
from openharness.tools.exit_worktree_tool import ExitWorktreeTool
from openharness.tools.file_edit_tool import FileEditTool
from openharness.tools.file_read_tool import FileReadTool
from openharness.tools.file_write_tool import FileWriteTool
from openharness.tools.glob_tool import GlobTool
from openharness.tools.grep_tool import GrepTool
from openharness.tools.list_mcp_resources_tool import ListMcpResourcesTool
from openharness.tools.lsp_tool import LspTool
from openharness.tools.mcp_auth_tool import McpAuthTool
from openharness.tools.mcp_tool import McpToolAdapter
from openharness.tools.notebook_edit_tool import NotebookEditTool
from openharness.tools.read_mcp_resource_tool import ReadMcpResourceTool
from openharness.tools.remote_trigger_tool import RemoteTriggerTool
from openharness.tools.query_memory_tool import QueryMemoryTool
from openharness.tools.send_message_tool import SendMessageTool
from openharness.tools.skill_tool import SkillTool
from openharness.tools.sleep_tool import SleepTool
from openharness.tools.task_create_tool import TaskCreateTool
from openharness.tools.task_get_tool import TaskGetTool
from openharness.tools.task_list_tool import TaskListTool
from openharness.tools.task_output_tool import TaskOutputTool
from openharness.tools.task_stop_tool import TaskStopTool
from openharness.tools.task_update_tool import TaskUpdateTool
from openharness.tools.team_create_tool import TeamCreateTool
from openharness.tools.team_delete_tool import TeamDeleteTool
from openharness.tools.todo_write_tool import TodoWriteTool
from openharness.tools.tool_search_tool import ToolSearchTool
from openharness.tools.web_fetch_tool import WebFetchTool
from openharness.tools.web_search_tool import WebSearchTool
from openharness.tools.media_generation_tools import (
    CreativeImageTool,
    EditImageTool,
    ImageFromReferenceTool,
    CreativeVideoTool,
    AnimateFirstFrameTool,
    VideoInterpolationTool,
    VideoWithReferenceTool,
)


def create_default_tool_registry(mcp_manager=None) -> ToolRegistry:
    """Return the default built-in tool registry."""
    registry = ToolRegistry()
    for tool in (
        BashTool(),
        AskUserQuestionTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        NotebookEditTool(),
        LspTool(),
        McpAuthTool(),
        GlobTool(),
        GrepTool(),
        SkillTool(),
        ToolSearchTool(),
        WebFetchTool(),
        WebSearchTool(),
        ConfigTool(),
        BriefTool(),
        SleepTool(),
        EnterWorktreeTool(),
        ExitWorktreeTool(),
        TodoWriteTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        CronCreateTool(),
        CronListTool(),
        CronDeleteTool(),
        CronToggleTool(),
        RemoteTriggerTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskStopTool(),
        TaskOutputTool(),
        TaskUpdateTool(),
        AgentTool(),
        SendMessageTool(),
        TeamCreateTool(),
        TeamDeleteTool(),
        CreativeImageTool(),
        EditImageTool(),
        ImageFromReferenceTool(),
        CreativeVideoTool(),
        AnimateFirstFrameTool(),
        VideoInterpolationTool(),
        VideoWithReferenceTool(),

        QueryMemoryTool(),
    ):
        registry.register(tool)
    if mcp_manager is not None:
        registry.register(ListMcpResourcesTool(mcp_manager))
        registry.register(ReadMcpResourceTool(mcp_manager))
        for tool_info in mcp_manager.list_tools():
            registry.register(McpToolAdapter(mcp_manager, tool_info))
    return registry


def create_mvp_safe_tool_registry(mcp_manager=None) -> ToolRegistry:
    """
    MVP 阶段安全工具注册表
    排除所有 Bash 相关工具，专注于 Manus/Loveart 核心能力
    
    5 大核心工具矩阵：
    1. 超级网联能力 (Research & Scraping)
    2. 长程记忆与检索引擎 (Memory & RAG)
    3. 多模态内容生成器 (Creative Generation)
    4. 自动化排班与多 Agent 协同 (Autonomy & Cron)
    5. 外部生态系统打通 (MCP)
    """
    registry = ToolRegistry()
    
    # === 1. 超级网联能力 ===
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    
    # === 2. 长程记忆与检索 ===
    registry.register(QueryMemoryTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(FileReadTool())
    
    # === 3. 多模态内容生成 ===
    registry.register(CreativeImageTool())
    registry.register(EditImageTool())
    registry.register(ImageFromReferenceTool())
    registry.register(CreativeVideoTool())
    registry.register(AnimateFirstFrameTool())
    registry.register(VideoInterpolationTool())
    registry.register(VideoWithReferenceTool())
    registry.register(FileWriteTool())  # 带白名单验证
    registry.register(FileEditTool())   # 带白名单验证
    registry.register(BriefTool())
    
    # === 4. 自动化排班与协同 ===
    registry.register(CronCreateTool())
    registry.register(CronListTool())
    registry.register(CronDeleteTool())
    registry.register(CronToggleTool())
    registry.register(TaskCreateTool())  # 仅支持 local_agent 类型
    registry.register(TaskGetTool())
    registry.register(TaskListTool())
    registry.register(TaskStopTool())
    registry.register(TaskOutputTool())
    registry.register(TaskUpdateTool())
    registry.register(AgentTool())
    
    # === 5. MCP 生态打通 ===
    registry.register(McpAuthTool())
    if mcp_manager is not None:
        registry.register(ListMcpResourcesTool(mcp_manager))
        registry.register(ReadMcpResourceTool(mcp_manager))
        for tool_info in mcp_manager.list_tools():
            registry.register(McpToolAdapter(mcp_manager, tool_info))
    
    # === 辅助工具 ===
    registry.register(AskUserQuestionTool())
    registry.register(SkillTool())
    registry.register(ToolSearchTool())
    registry.register(ConfigTool())
    registry.register(SleepTool())
    registry.register(SendMessageTool())
    
    return registry


__all__ = [
    "BaseTool",
    "ToolExecutionContext",
    "ToolRegistry",
    "ToolResult",
    "create_default_tool_registry",
    "create_mvp_safe_tool_registry",
]
