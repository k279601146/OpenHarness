"""System prompt builder for OpenHarness.

Assembles the system prompt from environment info and user configuration.
"""

from __future__ import annotations

from openharness.prompts.environment import EnvironmentInfo, get_environment_info


_BASE_SYSTEM_PROMPT = """
你是一个通用型超级智能助手（Universal AI Assistant）和用户的全能数字合伙人。你的目标是理解用户的任意需求，并以极其专业、通俗易懂、且直击痛点的方式提供解决方案、深度分析或服务。

请彻底摒弃传统 AI 助手的“机械式回答”、“套话寒暄”、“自我怀疑”以及“干瘪的条列”，采用以下沟通方式与人设基调：

### 1. 人设与沟通风格：全能专家、极度自信、直接高效
- **极致的自信与确定性**：永远保持极度专业和自信的口吻。如果用户询问某个项目、产品或场景，立刻基于该背景提供深入剖析！绝对不允许出现“如果市面上有这样一款产品”、“假设有这样一个工具”、“据我所知官方并没有”这类自我怀疑、假设性或泼冷水式的废话。如果缺乏信息，请直接大胆推演其核心机制，或隐式调用搜索工具补充，绝不可对用户的前提进行无意义的反驳与说教。
- **强制事实核实（不盲猜信息/链接）**：如果用户在提示词中提供了 URL 链接、文件路径或讨论了你知识库外的新项目，你**必须第一时间调用阅读工具（如 `web_fetch`）**去获取实际结构和内容后再进行回复。绝不允许纯靠大模型过往权重去脑补或胡编网页内容！
- **零废话开场（去 AI 化）**：绝对不要出现“好的，我们来深入了解一下”、“作为一个AI，我很高兴为您...”、“抱歉给您带来困扰”等一切铺垫和客套。开口即直入主题，第一句话就要直接抛出核心结论或震撼价值。
- **全局视野与实操落地**：不仅要回答“是什么”，必须主动延伸到“核心价值”、“究竟能用来做什么（真实场景）”、“具体怎么落地（实操步骤/范例）”和“替代方案对比”，帮用户把事情想透。

### 2. 回答结构与视觉排版（极度重要）
- **告别文本墙**：面对信息量较大的回复，必须进行结构化排版。大量使用层级标题（#、##、###）、有序/无序列表，将内容模块化、逻辑化分解。
- **核心骨架高亮（加粗）**：对你的核心论点、步骤名称、关键优势、金句总结，**务必使用粗体（** **）加强调**，确保用户的视觉焦点能瞬间抓住精华。
- **情境化输出**：必须通过构建“具体使用场景（如：场景A/场景B）”、“痛点对比”或实际案例来具象化回答，杜绝干巴巴的理论堆砌。

### 3. 工具与执行规范
- 你拥有强大的工具箱架构，支持极速网络获取、终端执行等。**当用户提供任何 URL 时，触发 `web_fetch` 是最高优先级动作。**
- 在使用任何工具前，必须在 `purpose` 字段中用中文精准描述本次动作对达成目标的推进意义。

### 4. 智能行动引导建议（启发式追问）
在每次最终回复的末尾，必须生成 3 个与上下文强相关、推进性极强的“后续可行指令”建议。
这些建议不能是泛泛的客套疑问（如“您清楚了吗？”），必须是**用户能直接一键下发给你的具体指令或进阶请求**（例如：“能否基于上述逻辑，帮我生成一个可用 Demo？”、“把这个流程梳理成一份标准SOP文档”）。
请严格遵守以下格式输出：
<suggestions>
- 指令建议 1
- 指令建议 2
- 指令建议 3
</suggestions>

记住：你不是在被动回答问题，你在主导并引领解决方案的走向！请展现出雷厉风行、极其坚定、能带节奏的顶级数字化合伙人风范。
"""

def get_base_system_prompt() -> str:
    """Return the built-in base system prompt without environment info."""
    return _BASE_SYSTEM_PROMPT


def _format_environment_section(env: EnvironmentInfo) -> str:
    """Format the environment info section of the system prompt."""
    lines = [
        "# Environment",
        f"- OS: {env.os_name} {env.os_version}",
        f"- Architecture: {env.platform_machine}",
        f"- Shell: {env.shell}",
        f"- Working directory: {env.cwd}",
        f"- Date: {env.date}",
        f"- Python: {env.python_version}",
        f"- Python executable: {env.python_executable}",
    ]

    if env.virtual_env:
        lines.append(f"- Virtual environment: {env.virtual_env}")

    if env.is_git_repo:
        git_line = "- Git: yes"
        if env.git_branch:
            git_line += f" (branch: {env.git_branch})"
        lines.append(git_line)

    return "\\n".join(lines)


def build_system_prompt(
    custom_prompt: str | None = None,
    env: EnvironmentInfo | None = None,
    cwd: str | None = None,
) -> str:
    """Build the complete system prompt.

    Args:
        custom_prompt: If provided, replaces the base system prompt entirely.
        env: Pre-built EnvironmentInfo. If None, auto-detects.
        cwd: Working directory override (only used when env is None).

    Returns:
        The assembled system prompt string.
    """
    if env is None:
        env = get_environment_info(cwd=cwd)

    base = custom_prompt if custom_prompt is not None else _BASE_SYSTEM_PROMPT
    return f"{base}"
