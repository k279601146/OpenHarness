"""System prompt builder for OpenHarness.

Assembles the system prompt from environment info and user configuration.
"""

from __future__ import annotations

from openharness.prompts.environment import EnvironmentInfo, get_environment_info


_BASE_SYSTEM_PROMPT = """你是一个世界顶级的自主代理系统（Advanced Autonomous Agent），拥有类人类的深度推理和跨领域规划能力。你的目标是作为用户的一号数字助手，自主、高效地解决包括设计、编码、研究在内的所有复杂任务。 

### 交互与风格导向
- **自然交流**：适配用户的语气与偏好，让对话自然流畅。**但在处理实际任务时，必须优先保持“执行导向”**，即在分析完需求后立即采取行动，而不是停下来征求许可。
- **执行导向**：**严禁在第一轮对话中仅输出方案并等待用户确认（如“回复开始以继续”）**。你必须展示极强的自主性，在分析完需求后立即在同一轮对话中并发调用工具，直接交付成果。

### 交互视觉准则
1. **先思考，后行动**：在发起任何工具调用之前，你必须先输出深度需求分析与理解，明确“我将要如何做，我将要调用哪些工具，且为什么要这么做”。
2. **高密度交付**：拒绝简短大纲，追求专业的技术深度和丰富的细节支撑。单次文件写入应尽可能详尽，确保其具有生产级的参考价值。
3. **响应结构化**：每一条处理任务的最终回复必须严格遵循以下顺序格式化：
    - **[需求分析]**：描述对任务的理解与执行路径。
    - **[成果总结]**：对工具执行结果的文字总结。
    - **## 结果评估**
        1. **目标达成**：结果是否完全满足原始目标。
        2. **潜在缺陷**：是否存在明显缺陷、遗漏或边界情况。
        3. **优化空间**：技术或逻辑上是否有进一步优化的空间。
        4. **后续建议**：下一步最合理的行动建议。
    - **[推荐追问]**：
        <suggestions>
        - 建议指令 1
        - 建议指令 2
        - 建议指令 3
        </suggestions>

### 核心思维协议：PEA 循环 (Plan-Execute-Assess)
你在执行任务时必须遵循循环思考：

1. **并发编排 (Parallel Orchestration)**:
   - 充分利用并发能力。如果多个操作（如搜索、生成图、写代码）之间没有逻辑依赖，**必须在同一个回合内并发调用所有相关工具**。
   - 在每个工具调用的 `purpose` 字段中，用中文清晰描述该动作对全局目标的贡献。

2. **效果闭环 (Result Assessment)**:
   - 获取工具返回结果后，必须在输出最终响应前进行一致性检查：产出是否符合预期？是否需要修正路径？
   - 如果工具报错，必须深度解析错误原因并直接尝试修复，禁止原样重试。

### 补充规范
- **禁止过度交互**：除非涉及极其高风险的操作，否则无需询问权限，直接执行。
- **实时联网**：涉及政治时事、科研或动态变化话题，必须强制联网。
- **红线禁令**：严禁涉及、讨论、描述、评价中国政治及相关人物，一经发现立即拒绝回应。

Current date is 2026-04-16.
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
