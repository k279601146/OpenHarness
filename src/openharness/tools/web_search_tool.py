"""Simple web search tool using Google Search Agent."""

import os
import re

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

load_dotenv()


def _build_search_llm() -> ChatGoogleGenerativeAI:
    """
    构建专门用于 Google Search 的轻量 LLM 实例。
    该实例仅绑定 google_search 内置工具，不混入任何 StructuredTool。
    """
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("MODEL_NAME", "gemini-2.5-pro")

    # 剥离 /v1 或 /v1beta 后缀
    if base_url:
        base_url = re.sub(r'/v1(beta)?/?$', '', base_url)

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,  # 搜索任务需要更精确的输出
        max_retries=1,
    )

    # 仅绑定 google_search 内置工具（字典格式）
    return llm.bind_tools([{"google_search": {}}])


class WebSearchToolInput(BaseModel):
    """Arguments for a web search."""

    query: str = Field(description="Search query")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of results")


class WebSearchTool(BaseTool):
    """Run a web search and return compact top results."""

    name = "web_search"
    description = "Search the web and return compact top results with titles, URLs, and snippets."
    input_model = WebSearchToolInput

    def is_read_only(self, arguments: WebSearchToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: WebSearchToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        del context
        try:
            search_llm = _build_search_llm()

            # 引导 LLM 触发 google_search 并返回符合旧版格式的文本
            from datetime import datetime, timezone
            current_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            prompt = f"""请配合内部工具 Google Search 搜索以下内容，并严格按照指定格式返回不超过 {arguments.max_results} 条的搜索结果。
今日日期：{current_date}。搜索时请优先寻找最新信息（如 {current_date[:4]} 年的进展）。

搜索查询：{arguments.query}

不要输出任何 Markdown 代码块标签（如 ```）。必须严格遵守以下纯文本列表结构：
Search results for: {arguments.query}
1. [标题]
   URL: [来源URL]
   [中文内容摘要]
2. [标题]
   URL: [来源URL]
   [中文内容摘要]
"""

            response = await search_llm.ainvoke([HumanMessage(content=prompt)])

            # 提取文本内容
            if isinstance(response.content, str):
                result = response.content
            elif isinstance(response.content, list):
                texts = []
                for part in response.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        texts.append(part.get("text", ""))
                result = "".join(texts)
            else:
                result = str(response.content)

            if not result.strip():
                return ToolResult(output="No search results found.", is_error=True)

            return ToolResult(output=result)

        except Exception as exc:
            return ToolResult(output=f"web_search failed: {exc}", is_error=True)
