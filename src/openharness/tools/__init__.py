"""Built-in tool registration."""

from openharness.tools.ask_user_question_tool import AskUserQuestionTool
from openharness.tools.ask_user_form_tool import AskUserFormTool
from openharness.tools.agent_tool import AgentTool
from openharness.tools.bash_tool import BashTool
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolRegistry, ToolResult
from openharness.tools.brief_tool import BriefTool
from openharness.tools.canvas_ops_tool import (
    CanvasApplyOpsTool,
    CanvasConnectNodesTool,
    CanvasCreateGenerationFlowTool,
    CanvasCreateNodeTool,
    CanvasCreateTextNodeTool,
    CanvasCreateTextNodesTool,
    CanvasDeleteNodesTool,
    CanvasExportSnapshotTool,
    CanvasGenerateAudioTool,
    CanvasGenerateImageTool,
    CanvasGenerateTextTool,
    CanvasGenerateVideoTool,
    CanvasGetRequestReferencesTool,
    CanvasGetSelectionTool,
    CanvasGetStateTool,
    CanvasMoveNodesTool,
    CanvasResizeNodeTool,
    CanvasRunGenerationTool,
    CanvasSelectNodesTool,
    CanvasSetViewportTool,
    CanvasUpdateNodeTextTool,
    CanvasUpdateNodeTool,
)
from openharness.tools.create_folder_tool import CreateFolderTool
from openharness.tools.create_handdraw_story_video_tool import CreateHanddrawStoryVideoTool
from openharness.tools.cron_create_tool import CronCreateTool
from openharness.tools.cron_delete_tool import CronDeleteTool
from openharness.tools.cron_list_tool import CronListTool
from openharness.tools.cron_toggle_tool import CronToggleTool
from openharness.tools.deliver_artifact_tool import DeliverArtifactTool
from openharness.tools.enter_plan_mode_tool import EnterPlanModeTool
from openharness.tools.exit_plan_mode_tool import ExitPlanModeTool
from openharness.tools.file_edit_tool import FileEditTool
from openharness.tools.file_read_tool import FileReadTool
from openharness.tools.file_write_tool import FileWriteTool
from openharness.tools.glob_tool import GlobTool
from openharness.tools.grep_tool import GrepTool
from openharness.tools.generate_image_tool import GenerateImageTool
from openharness.tools.generate_video_tool import GenerateVideoTool
from openharness.tools.merge_video_tool import MergeVideoTool
from openharness.tools.list_mcp_resources_tool import ListMcpResourcesTool
from openharness.tools.mcp_auth_tool import McpAuthTool
from openharness.tools.mcp_tool import McpToolAdapter
from openharness.tools.prepare_web_image_reference_tool import PrepareWebImageReferenceTool
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


def create_default_tool_registry(mcp_manager=None) -> ToolRegistry:
    """Return the default built-in tool registry."""
    registry = ToolRegistry()
    for tool in (
        BashTool(),
        AskUserQuestionTool(),
        AskUserFormTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        McpAuthTool(),
        GlobTool(),
        GrepTool(),
        GenerateImageTool(),
        GenerateVideoTool(),
        MergeVideoTool(),
        CreateHanddrawStoryVideoTool(),
        SkillTool(),
        ToolSearchTool(),
        WebFetchTool(),
        WebSearchTool(),
        PrepareWebImageReferenceTool(),
        CreateFolderTool(),
        BriefTool(),
        CanvasGetStateTool(),
        CanvasGetSelectionTool(),
        CanvasGetRequestReferencesTool(),
        CanvasExportSnapshotTool(),
        CanvasApplyOpsTool(),
        CanvasCreateNodeTool(),
        CanvasCreateTextNodeTool(),
        CanvasCreateTextNodesTool(),
        CanvasCreateGenerationFlowTool(),
        CanvasGenerateTextTool(),
        CanvasGenerateImageTool(),
        CanvasGenerateVideoTool(),
        CanvasGenerateAudioTool(),
        CanvasUpdateNodeTool(),
        CanvasUpdateNodeTextTool(),
        CanvasMoveNodesTool(),
        CanvasResizeNodeTool(),
        CanvasDeleteNodesTool(),
        CanvasConnectNodesTool(),
        CanvasSelectNodesTool(),
        CanvasSetViewportTool(),
        CanvasRunGenerationTool(),
        SleepTool(),
        TodoWriteTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        CronCreateTool(),
        CronListTool(),
        CronDeleteTool(),
        CronToggleTool(),
        DeliverArtifactTool(),
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
        QueryMemoryTool(),
    ):
        registry.register(tool)
    if mcp_manager is not None:
        registry.register(ListMcpResourcesTool(mcp_manager))
        registry.register(ReadMcpResourceTool(mcp_manager))
        for tool_info in mcp_manager.list_tools():
            registry.register(McpToolAdapter(mcp_manager, tool_info))
    return registry


__all__ = [
    "BaseTool",
    "ToolExecutionContext",
    "ToolRegistry",
    "ToolResult",
    "create_default_tool_registry",
]
