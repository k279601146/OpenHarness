import os
import json
import re
from typing import Any, Optional
from pydantic import BaseModel, Field
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

class QueryMemoryInput(BaseModel):
    """Input for QueryMemoryTool."""
    query: str = Field(..., description="The search query (e.g., 'yesterday's generated cat image' or 'code for the react project')")
    limit: int = Field(5, description="Maximum number of memory entries to retrieve")
    purpose: Optional[str] = Field(None, description="The reasoning behind why you are querying memory")

class QueryMemoryTool(BaseTool):
    """Tool for performing semantic search across long-term memory via OpenViking."""
    
    name: str = "query_memory"
    description: str = (
        "Search your long-term memory for past interactions, images, code, or context. "
        "Use this when the user asks about something from a previous session or 'yesterday'. "
        "The search is semantic, so use descriptive natural language queries."
    )
    input_model: type[BaseModel] = QueryMemoryInput

    async def execute(self, arguments: QueryMemoryInput, context: ToolExecutionContext) -> ToolResult:
        query = arguments.query
        limit = arguments.limit
        
        # 从上下文元数据中提取注入的 viking 适配器 (注入逻辑在 engine_adapter.py:437)
        viking = context.metadata.get("viking")
        if not viking:
            return ToolResult(output="Error: OpenViking memory service is not available in current context.")
        
        try:
            # 1. 首先尝试搜索语义记忆 (Memories)
            result_text, _hit_uris = await viking.retrieve_long_term_memory(query, limit=limit, reliable=True)
            if result_text:
                return ToolResult(output=f"Retrieved from OpenViking Memories:\n{result_text}")
            
            # 2. 如果记忆库落空，尝试直接在资源库 (Resources) 中进行发现
            print(f"DEBUG: Memory base empty. Diverting to Resource discovery for '{query}'...")
            
            try:
                client = await viking.ensure_client()
                if client:
                    resource_results = await client.find(
                        query=query,
                        target_uri=viking.get_resource_base(),
                        limit=limit,
                        score_threshold=0.3
                    )

                    if resource_results and getattr(resource_results, "total", 0) > 0:
                        entries = []
                        candidates = (
                            (getattr(resource_results, "memories", []) or []) +
                            (getattr(resource_results, "resources", []) or [])
                        )
                        for item in candidates:
                            content = (
                                getattr(item, "overview", None)
                                or getattr(item, "abstract", None)
                                or getattr(item, "id", "")
                            )
                            score = getattr(item, "score", 0.0)
                            entries.append(f"[Resource({score:.2f})]: {content}")
                        if entries:
                            return ToolResult(output="Retrieved from OpenViking Resources:\n" + "\n".join(entries))
            except Exception as e:
                print(f"DEBUG: Viking resource discovery skipped: {e}")

            # 3. 终极原子兜底：直接从数据库检索历史消息 (Atomic Fallback)
            # 即使 Viking 索引挂了，主数据库里的历史永远是真实的
            print(f"DEBUG: Viking failed. Initiating Atomic DB Fallback for query: '{query}'")
            
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            
            # TODO: 生产环境应从配置中心读取
            DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:a4875784@localhost:5432/openharness_saas")
            engine = create_engine(DB_URL)
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()
            
            try:
                user_id = viking.user_id
                db_entries = []
                count = 0
                query_lower = arguments.query.lower()

                sql = text("""
                    SELECT t.id as thread_id, t.title, e.type, e.payload, e.created_at
                    FROM agent_events e
                    JOIN agent_threads t ON e.thread_id = t.id
                    WHERE t.owner_id = :user_id
                    ORDER BY e.created_at DESC
                    LIMIT 600
                """)
                db_results = db.execute(sql, {"user_id": int(user_id)}).fetchall()

                query_terms = _memory_query_terms(arguments.query)
                scored_entries = []
                for tid, title, e_type, payload, dt in db_results:
                    content = _payload_to_search_text(payload)
                    haystack = f"{title or ''} {e_type or ''} {content}".lower()
                    score = _memory_match_score(query_lower, query_terms, haystack)
                    if score <= 0:
                        continue
                    scored_entries.append((score, dt, tid, title, e_type, content))

                seen_threads = set()
                for _score, dt, tid, title, e_type, content in sorted(
                    scored_entries,
                    key=lambda item: (item[0], item[1]),
                    reverse=True,
                ):
                    if count >= limit:
                        break
                    if tid in seen_threads:
                        continue
                    seen_threads.add(tid)
                    role = _event_role_label(e_type)
                    db_entries.append(f"[History {dt.date()}] Thread: {title}\n  {role}: {content[:240]}")
                    count += 1
                
                if not db_entries:
                    return ToolResult(output=f"No relevant items found in memory or database for '{arguments.query}'.")
                    
                return ToolResult(output="Retrieved from Database Fallback:\n" + "\n".join(db_entries))
            finally:
                db.close()
            
        except Exception as e:
            return ToolResult(output=f"Deep Search Failed: {str(e)}", is_error=True)


def _payload_to_search_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)

    parts: list[str] = []
    for key in (
        "content",
        "reason",
        "tool_name",
        "input",
        "output",
        "file_path",
        "url",
        "type",
    ):
        value = payload.get(key)
        if value:
            parts.append(_stringify_payload_value(value))

    data = payload.get("data")
    if isinstance(data, dict):
        parts.append(_payload_to_search_text(data))

    item = payload.get("item")
    if isinstance(item, dict):
        for key in ("result", "revisedPrompt", "savedPath", "type", "status"):
            value = item.get(key)
            if value:
                parts.append(_stringify_payload_value(value))

    return " ".join(part for part in parts if part)


def _stringify_payload_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _memory_query_terms(query: str) -> set[str]:
    keep_single_char_terms = {"画", "图"}
    terms = {
        term.lower()
        for term in re.findall(r"[\w\u4e00-\u9fff]+", query or "")
        if len(term.strip()) >= 2 or term in keep_single_char_terms
    }
    expansions = {
        "画": {"画", "图", "图片", "图像", "生成", "image", "generation", "generated"},
        "图": {"图", "图片", "图像", "image", "photo", "portrait", "png", "jpg"},
        "图片": {"图片", "图像", "image", "photo", "portrait", "png", "jpg"},
        "图像": {"图片", "图像", "image", "photo", "portrait", "png", "jpg"},
        "生成图像": {"图片", "图像", "image", "generation", "generated", "revisedprompt"},
    }
    expanded = set(terms)
    for term in terms:
        expanded.update(expansions.get(term, set()))
    return expanded


def _memory_match_score(query_lower: str, query_terms: set[str], haystack: str) -> int:
    if not haystack:
        return 0
    if query_lower and query_lower in haystack:
        return 100
    return sum(1 for term in query_terms if term and term in haystack)


def _event_role_label(event_type: str) -> str:
    if event_type == "user_message":
        return "User"
    if event_type in {"agent_message", "agent_artifact"}:
        return "Assistant"
    if event_type in {"agent_action", "agent_action_result"}:
        return "Tool"
    return event_type or "Event"
