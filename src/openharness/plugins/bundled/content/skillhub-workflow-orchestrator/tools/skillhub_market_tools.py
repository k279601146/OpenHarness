"""SkillHub marketplace tools for SaaS workflow orchestration."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


InstallMode = Literal["auto", "skill", "plugin"]


class SkillHubSearchInput(BaseModel):
    query: str = Field(description="Capability or task keywords to search on SkillHub")
    category: str | None = Field(default=None, description="Optional SkillHub category key")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum number of candidates")


class SkillHubPrepareInstallInput(BaseModel):
    slug: str = Field(description="SkillHub skill slug selected for installation")
    install_as: InstallMode = Field(default="auto", description="Install mode")


class SkillHubInstallConfirmedInput(BaseModel):
    confirmation_id: str = Field(description="Confirmation id returned by skillhub_prepare_install")
    slug: str = Field(description="SkillHub skill slug selected for installation")
    install_as: InstallMode = Field(default="auto", description="Install mode")


def _ensure_api_path(context: ToolExecutionContext) -> None:
    api_dir = context.metadata.get("saas_api_dir")
    if isinstance(api_dir, str) and api_dir:
        resolved = str(Path(api_dir).expanduser().resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


def _skill_market_module(context: ToolExecutionContext):
    _ensure_api_path(context)
    import skill_market

    return skill_market


def _current_user(context: ToolExecutionContext):
    _ensure_api_path(context)
    from models import User

    db = context.metadata.get("db_session")
    user_id = context.metadata.get("user_id")
    if db is None or user_id is None:
        raise RuntimeError("SaaS user context is unavailable.")
    user = db.get(User, int(user_id))
    if user is None:
        raise RuntimeError("Current user was not found.")
    return user


def _json_output(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _catalog_items(skill_market, db, user, query: str, category: str | None, limit: int) -> list[dict]:
    categories = skill_market._categories()
    categories_by_key = {item["key"]: item["name"] for item in categories}
    params = {
        "page": "1",
        "pageSize": str(max(1, min(limit * 2, 20))),
        "sortBy": "score" if query.strip() else "downloads",
        "order": "desc",
    }
    if query.strip():
        normalized_query = query.strip()
        params.update(
            {
                "query": normalized_query,
                "q": normalized_query,
                "search": normalized_query,
                "keyword": normalized_query,
            }
        )
    if category and category.strip() and category != "all":
        params["category"] = category.strip()

    payload = skill_market._skillhub_get_json("/api/skills", params)
    data = skill_market._as_dict(payload.get("data"))
    raw_items = (
        skill_market._as_list(payload.get("items"))
        or skill_market._as_list(data.get("items"))
        or skill_market._as_list(data.get("skills"))
        or skill_market._as_list(payload.get("skills"))
    )
    installed = skill_market._installed_ids(db, user)
    items = skill_market._normalize_skillhub_items(raw_items, categories_by_key, installed)
    filtered = [item for item in items if skill_market._matches_catalog_query(item, query)]
    sorted_items = filtered if query.strip() else skill_market._sort_market_items(filtered, "downloads", "desc")
    return sorted_items[:limit]


def _summarize_item(item: dict) -> dict:
    return {
        "slug": item.get("slug"),
        "name": item.get("display_name") or item.get("name"),
        "description": item.get("description") or item.get("short_description"),
        "category": item.get("category_name") or item.get("category_key"),
        "downloads": item.get("downloads"),
        "installs": item.get("installs"),
        "requires_api_key": bool(item.get("requires_api_key")),
        "capability_hint": item.get("capability_hint") or "skill",
        "installed": bool(item.get("installed")),
        "installed_as": item.get("installed_as"),
        "homepage": f"https://skillhub.cn/skills/{item.get('slug')}",
    }


class SkillHubSearchCapabilitiesTool(BaseTool):
    name = "skillhub_search_capabilities"
    description = (
        "Search SkillHub marketplace capabilities for a workflow step. "
        "Use this only when bundled and already-installed skills cannot satisfy a task."
    )
    input_model = SkillHubSearchInput

    def is_read_only(self, arguments: SkillHubSearchInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillHubSearchInput, context: ToolExecutionContext) -> ToolResult:
        try:
            skill_market = _skill_market_module(context)
            db = context.metadata.get("db_session")
            user = _current_user(context)
            candidates = [
                _summarize_item(item)
                for item in _catalog_items(skill_market, db, user, arguments.query, arguments.category, arguments.limit)
            ]
            return ToolResult(
                output=_json_output(
                    {
                        "query": arguments.query,
                        "category": arguments.category,
                        "candidates": candidates,
                    }
                ),
                metadata={"candidate_count": len(candidates)},
            )
        except Exception as exc:
            return ToolResult(output=f"SkillHub search failed: {exc}", is_error=True)


class SkillHubPrepareInstallTool(BaseTool):
    name = "skillhub_prepare_install"
    description = (
        "Prepare a SkillHub marketplace install and return a confirmation id. "
        "After this, ask the user for confirmation before calling skillhub_install_confirmed."
    )
    input_model = SkillHubPrepareInstallInput

    def is_read_only(self, arguments: SkillHubPrepareInstallInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillHubPrepareInstallInput, context: ToolExecutionContext) -> ToolResult:
        try:
            skill_market = _skill_market_module(context)
            db = context.metadata.get("db_session")
            user = _current_user(context)
            slug = skill_market._normalize_slug(arguments.slug)
            categories = skill_market._categories()
            categories_by_key = {item["key"]: item["name"] for item in categories}
            item = skill_market._detail_market_item(slug, categories_by_key, skill_market._installed_ids(db, user))
            files, has_manifest = skill_market._read_files_manifest(slug)
            capability_hint = "plugin_candidate" if any(path.endswith("plugin.json") for path in files.keys()) else "skill"
            confirmation_id = uuid.uuid4().hex
            pending = context.metadata.setdefault("pending_skillhub_installs", {})
            pending[confirmation_id] = {
                "slug": slug,
                "install_as": arguments.install_as,
                "capability_hint": capability_hint,
                "name": item.get("display_name") or item.get("name") or slug,
            }
            risks: list[str] = []
            if capability_hint == "plugin_candidate" or arguments.install_as == "plugin":
                risks.append("该能力可能作为插件型扩展安装，可能注册工具、MCP、hooks 或插件技能。")
            if item.get("requires_api_key"):
                risks.append("该能力声明可能需要 API key，使用前可能还需要额外授权或配置。")
            if not has_manifest:
                risks.append("SkillHub 未返回完整文件清单，安装时安全状态将标记为 unknown。")
            return ToolResult(
                output=_json_output(
                    {
                        "confirmation_id": confirmation_id,
                        "slug": slug,
                        "name": item.get("display_name") or item.get("name") or slug,
                        "install_as": arguments.install_as,
                        "capability_hint": capability_hint,
                        "requires_api_key": bool(item.get("requires_api_key")),
                        "security_status": "verified" if files else ("unknown" if not has_manifest else "verified"),
                        "risks": risks,
                        "instruction": "Ask the user to confirm installation before calling skillhub_install_confirmed.",
                    }
                ),
                metadata={"confirmation_id": confirmation_id, "slug": slug},
            )
        except Exception as exc:
            return ToolResult(output=f"SkillHub install preparation failed: {exc}", is_error=True)


class SkillHubInstallConfirmedTool(BaseTool):
    name = "skillhub_install_confirmed"
    description = (
        "Install a SkillHub marketplace capability after the user has confirmed. "
        "Do not call this without a matching confirmation id from skillhub_prepare_install."
    )
    input_model = SkillHubInstallConfirmedInput

    def is_read_only(self, arguments: SkillHubInstallConfirmedInput) -> bool:
        del arguments
        return False

    async def execute(self, arguments: SkillHubInstallConfirmedInput, context: ToolExecutionContext) -> ToolResult:
        try:
            skill_market = _skill_market_module(context)
            db = context.metadata.get("db_session")
            user = _current_user(context)
            pending = context.metadata.get("pending_skillhub_installs")
            if not isinstance(pending, dict):
                return ToolResult(output="No pending SkillHub install confirmation exists.", is_error=True)
            prepared = pending.get(arguments.confirmation_id)
            if not isinstance(prepared, dict):
                return ToolResult(output="SkillHub install confirmation id is invalid or expired.", is_error=True)
            slug = skill_market._normalize_slug(arguments.slug)
            if prepared.get("slug") != slug:
                return ToolResult(output="SkillHub install confirmation does not match the requested slug.", is_error=True)
            if prepared.get("install_as") != arguments.install_as:
                return ToolResult(output="SkillHub install confirmation does not match the requested install mode.", is_error=True)

            request = skill_market.SkillMarketInstallRequest(
                slug=slug,
                install_as=arguments.install_as,
                acknowledge_plugin_permissions=True,
            )
            result = skill_market.install(request, db=db, current_user=user)
            pending.pop(arguments.confirmation_id, None)
            return ToolResult(
                output=_json_output(
                    {
                        "status": "installed",
                        "slug": slug,
                        "installed_as": result.get("installed_as"),
                        "security_status": result.get("security_status"),
                        "message": "SkillHub capability installed into the current user's private SaaS directory.",
                    }
                ),
                metadata={"slug": slug, "installed_as": result.get("installed_as")},
            )
        except Exception as exc:
            return ToolResult(output=f"SkillHub install failed: {exc}", is_error=True)
