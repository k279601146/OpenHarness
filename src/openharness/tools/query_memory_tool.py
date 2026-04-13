import os
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
            result_text = await viking.retrieve_long_term_memory(query, limit=limit)
            if result_text:
                return ToolResult(output=f"Retrieved from Memories:\n{result_text}")
            
            # 2. 如果记忆库落空，尝试直接在资源库 (Resources) 中进行发现
            print(f"DEBUG: Memory base empty. Diverting to Resource discovery for '{query}'...")
            
            client = await viking.ensure_client()
            if client:
                resource_results = await client.find(
                    query=query,
                    target_uri=viking.get_resource_base(),
                    limit=limit,
                    score_threshold=0.3
                )
                
                if resource_results and resource_results.total > 0:
                    entries = []
                    for item in resource_results:
                        content = item.overview or item.abstract or item.id
                        entries.append(f"[Resource({item.score:.2f})]: {content}")
                    return ToolResult(output="Retrieved from Resources:\n" + "\n".join(entries))

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
                # 语义检索退化为关键词检索
                sql = text("""
                    SELECT t.title, e.type, e.payload, e.created_at
                    FROM agent_events e
                    JOIN agent_threads t ON e.thread_id = t.id
                    WHERE t.owner_id = :user_id
                    AND (e.payload->>'content' ILIKE :q)
                    ORDER BY e.created_at DESC
                    LIMIT :limit
                """)
                
                db_results = db.execute(sql, {"user_id": int(user_id), "q": f"%{query}%", "limit": limit}).fetchall()
                
                if not db_results:
                    return ToolResult(output=f"No relevant sessions found for '{query}' in either memory engine or primary database.")
                
                db_entries = []
                for title, e_type, payload, dt in db_results:
                    role = "User" if e_type == "user_message" else "Assistant"
                    content = payload.get("content", "")
                    db_entries.append(f"[{dt.date()}] Thread: {title}\n  {role}: {content[:200]}")
                
                return ToolResult(output="Retrieved from Primary Database (Fallback Mode):\n" + "\n".join(db_entries))
            finally:
                db.close()
            
        except Exception as e:
            return ToolResult(output=f"Deep Search Failed: {str(e)}", is_error=True)
