"""Canvas operation tools for the SaaS workspace canvas.

These tools mirror the infinite-canvas canvas-agent tool surface while keeping
all model calls, billing, uploads, and task state inside Bahew.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


NodeType = Literal["text", "image", "video", "audio"]
GenerationMode = Literal["text", "image", "video", "audio"]
ContentRole = Literal["prompt", "reference_image", "reference_video", "reference_audio", "context"]


class _CanvasModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Position(_CanvasModel):
    x: float
    y: float


class Viewport(_CanvasModel):
    x: float
    y: float
    k: float


class CanvasOp(_CanvasModel):
    type: Literal[
        "add_node",
        "update_node",
        "delete_node",
        "delete_connections",
        "connect_nodes",
        "set_viewport",
        "select_nodes",
        "run_generation",
    ]
    id: str | None = None
    nodeType: NodeType | None = None
    title: str | None = None
    position: Position | dict[str, float] | None = None
    width: float | None = None
    height: float | None = None
    metadata: dict[str, Any] | None = None
    nodeIds: list[str] | None = None
    connectionIds: list[str] | None = None
    fromNodeId: str | None = None
    toNodeId: str | None = None
    contentRole: ContentRole | None = None
    viewport: Viewport | dict[str, float] | None = None
    targetNodeId: str | None = None
    options: dict[str, Any] | None = None


class CanvasGetStateInput(_CanvasModel):
    scope: Literal["all", "selection", "references"] | None = Field(
        default="all",
        description="检索范围：'all' 读取画布概览（节点、连线与选区），'selection' 仅读取当前选中的高亮节点，'references' 读取本轮请求关联的参考卡片与素材。",
    )


class CanvasApplyOpsInput(_CanvasModel):
    ops: list[CanvasOp] = Field(description="Structured canvas operations to apply in the browser.")


class CreateNodeItem(_CanvasModel):
    nodeType: NodeType | None = Field(default="text", description="节点类型：'text', 'image', 'video', 'audio'")
    text: str | None = Field(default="", description="文本内容（对 text 节点有效）")
    content: str | None = Field(default=None, description="别名：文本内容")
    title: str | None = Field(default=None, description="卡片标题")
    color: str | None = Field(default=None, description="卡片主题色：'blue', 'green', 'amber', 'red', 'purple', 'gray'")
    x: float | None = Field(default=None, description="绝对X坐标（通常省略，由 layout 自动排版）")
    y: float | None = Field(default=None, description="绝对Y坐标（通常省略，由 layout 自动排版）")
    width: float | None = Field(default=None, description="卡片宽度")
    height: float | None = Field(default=None, description="卡片高度")
    metadata: dict[str, Any] | None = Field(default=None, description="附加元数据")


class CanvasCreateNodesInput(_CanvasModel):
    items: list[CreateNodeItem] = Field(default_factory=list, description="待创建的节点列表（支持创建 1 个或多个节点）")
    nodes: list[CreateNodeItem] | None = Field(default=None, description="别名：待创建的节点列表（等同于 items）")
    relative_to_node_id: str | None = Field(default=None, description="排版基准父节点ID。留空时默认检测当前焦点/选区节点")
    placement: Literal["right", "bottom", "left", "top"] | None = Field(
        default="right",
        description="相对基准节点方向（单节点或无 layout 时生效）",
    )
    layout: Literal["tree_right", "tree_bottom", "grid", "row", "column"] | None = Field(
        default=None,
        description="多卡片排版布局：'tree_right'（向右树状辐射，脑图首选），'tree_bottom'（向下树状分支），'grid'（网格），'row'（横排），'column'（纵排）",
    )
    gap: float | None = Field(default=40.0, description="卡片之间的间距，默认 40")
    connect_from_parent: bool | None = Field(default=False, description="是否自动从父节点向每个新建卡片建立连线（形成脑图/树状分支）")
    auto_connect: bool | None = Field(default=False, description="别名：等同于 connect_from_parent")
    content_role: ContentRole | None = Field(default="context", description="连线语义角色：'context', 'prompt' 等")
    x: float | None = Field(default=None, description="起始绝对X坐标（可选）")
    y: float | None = Field(default=None, description="起始绝对Y坐标（可选）")

    @model_validator(mode="before")
    @classmethod
    def normalize_items(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("items") and data.get("nodes"):
                data["items"] = data["nodes"]
        return data


NODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "text": {"title": "文本", "width": 320, "height": 220, "metadata": {"status": "success"}},
    "image": {"title": "图片", "width": 320, "height": 240, "metadata": {"status": "idle"}},
    "video": {"title": "视频", "width": 360, "height": 260, "metadata": {"status": "idle"}},
    "audio": {"title": "音频", "width": 320, "height": 160, "metadata": {"status": "idle"}},
    "config": {"title": "生成配置", "width": 320, "height": 260, "metadata": {"status": "idle", "generationMode": "image"}},
}


NODE_DEFAULTS.update(
    {
        "text": {**NODE_DEFAULTS["text"], "width": 340, "height": 240},
        "image": {**NODE_DEFAULTS["image"], "width": 340, "height": 240},
        "video": {**NODE_DEFAULTS["video"], "width": 420, "height": 236},
        "audio": {**NODE_DEFAULTS["audio"], "width": 340, "height": 120},
        "config": {**NODE_DEFAULTS["config"], "width": 340, "height": 240},
    }
)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _clean_record(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None and item != ""}


def _state_from_context(context: ToolExecutionContext) -> dict[str, Any]:
    canvas_context = context.metadata.setdefault("canvas_context", {})
    if not isinstance(canvas_context, dict):
        canvas_context = {}
        context.metadata["canvas_context"] = canvas_context
    state = canvas_context.get("state")
    if not isinstance(state, dict):
        state = _empty_state()
        canvas_context["state"] = state
    state.setdefault("version", 2)
    state.setdefault("title", "")
    state.setdefault("nodes", [])
    state.setdefault("connections", [])
    state.setdefault("selectedNodeIds", [])
    state.setdefault("viewport", {"x": 0, "y": 0, "k": 1})
    state.setdefault("backgroundMode", "blank")
    state.setdefault("showMiniMap", False)
    return state


def _empty_state() -> dict[str, Any]:
    return {
        "version": 2,
        "title": "",
        "nodes": [],
        "connections": [],
        "selectedNodeIds": [],
        "viewport": {"x": 0, "y": 0, "k": 1},
        "backgroundMode": "blank",
        "showMiniMap": False,
    }


def _nodes(state: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = state.setdefault("nodes", [])
    return nodes if isinstance(nodes, list) else []


def _connections(state: dict[str, Any]) -> list[dict[str, Any]]:
    connections = state.setdefault("connections", [])
    return connections if isinstance(connections, list) else []


def _normalize_node_id(node_id: Any) -> str:
    if not node_id:
        return ""
    val = str(node_id).strip()
    if val.startswith("canvas-"):
        return val[len("canvas-"):]
    return val


def _node_ids_match(id_a: Any, id_b: Any) -> bool:
    if not id_a or not id_b:
        return False
    str_a = str(id_a).strip()
    str_b = str(id_b).strip()
    if str_a == str_b:
        return True
    norm_a = _normalize_node_id(str_a)
    norm_b = _normalize_node_id(str_b)
    return norm_a == norm_b or str_a == norm_b or norm_a == str_b


def _find_node(state: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return next((node for node in _nodes(state) if isinstance(node, dict) and _node_ids_match(node.get("id"), node_id)), None)


def _get_default_anchor_node(
    context: ToolExecutionContext,
    state: dict[str, Any],
    relative_to_node_id: str | None = None,
) -> dict[str, Any] | None:
    if relative_to_node_id:
        found = _find_node(state, relative_to_node_id)
        if found:
            return found
    # 从 canvas_request 中提取聚焦节点
    req = _canvas_request(context)
    for key in ("sourceNodeId", "source_node_id", "targetNodeId", "target_node_id"):
        val = req.get(key)
        if val:
            found = _find_node(state, str(val))
            if found:
                return found
    # 从 selectedNodeIds 提取
    selected = state.get("selectedNodeIds") or []
    if selected and isinstance(selected, list) and selected[0]:
        found = _find_node(state, str(selected[0]))
        if found:
            return found
    return None


def _resolve_placement_position(
    state: dict[str, Any],
    anchor_node: dict[str, Any] | None,
    placement: str | None = "right",
    gap: float | None = None,
    new_width: float = 340.0,
    new_height: float = 240.0,
) -> tuple[float, float]:
    effective_gap = 40.0 if gap is None else float(gap)
    if anchor_node and isinstance(anchor_node, dict):
        pos = anchor_node.get("position") if isinstance(anchor_node.get("position"), dict) else {}
        ax = float(pos.get("x", 0))
        ay = float(pos.get("y", 0))
        aw = float(anchor_node.get("width", 340))
        ah = float(anchor_node.get("height", 240))
        direction = (placement or "right").lower()
        if direction == "bottom":
            return (ax, ay + ah + effective_gap)
        elif direction == "left":
            return (ax - new_width - effective_gap, ay)
        elif direction == "top":
            return (ax, ay - new_height - effective_gap)
        else:  # "right"
            return (ax + aw + effective_gap, ay)
    # 无锚点时排在最右侧
    return (_next_canvas_x(state), 0.0)


def _canvas_request(context: ToolExecutionContext) -> dict[str, Any]:
    request = context.metadata.get("canvas_request")
    return request if isinstance(request, dict) else {}


def _active_media_canvas_request(context: ToolExecutionContext) -> str | None:
    kind = str(_canvas_request(context).get("kind") or "")
    return kind if kind in {"image_generation", "video_generation"} else None


def _canvas_request_target_ids(context: ToolExecutionContext) -> set[str]:
    request = _canvas_request(context)
    ids: set[str] = set()
    for key in ("targetNodeId", "target_node_id"):
        value = request.get(key)
        if value:
            ids.add(str(value))
    for key in ("targetNodeIds", "target_node_ids"):
        values = request.get(key)
        if isinstance(values, list):
            ids.update(str(value) for value in values if value)
    return ids


def _update_metadata(op: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    patch = op.get("patch") if isinstance(op.get("patch"), dict) else {}
    patch_metadata = patch.get("metadata") if isinstance(patch.get("metadata"), dict) else {}
    direct_metadata = op.get("metadata") if isinstance(op.get("metadata"), dict) else {}
    metadata.update(patch_metadata)
    metadata.update(direct_metadata)
    return metadata


def _has_non_metadata_patch(op: dict[str, Any]) -> bool:
    patch = op.get("patch")
    return isinstance(patch, dict) and any(key != "metadata" for key in patch)


def _is_redundant_media_success_update(context: ToolExecutionContext, op: dict[str, Any]) -> bool:
    if _active_media_canvas_request(context) not in {"image_generation", "video_generation"}:
        return False
    if op.get("type") != "update_node" or _has_non_metadata_patch(op):
        return False
    target_ids = _canvas_request_target_ids(context)
    if target_ids and str(op.get("id") or "") not in target_ids:
        return False
    metadata = _update_metadata(op)
    status = str(metadata.get("status") or "").lower()
    has_media_ref = any(metadata.get(key) for key in ("content", "path", "url", "file_path"))
    return status == "success" and has_media_ref


def _collect_upstream_node_ids(state: dict[str, Any], node_id: str) -> list[str]:
    result: list[str] = []
    visited: set[str] = set()
    queue = [str(conn.get("fromNodeId")) for conn in _connections(state) if isinstance(conn, dict) and conn.get("toNodeId") == node_id]
    while queue:
        current = queue.pop(0)
        if not current or current in visited:
            continue
        visited.add(current)
        result.append(current)
        queue.extend(
            str(conn.get("fromNodeId"))
            for conn in _connections(state)
            if isinstance(conn, dict) and conn.get("toNodeId") == current
        )
    return result


def _node_reference(node: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "nodeId": node.get("id"),
        "role": role,
        "type": node.get("type"),
        "title": node.get("title"),
        "position": node.get("position"),
        "width": node.get("width"),
        "height": node.get("height"),
        "metadata": node.get("metadata"),
    }


def _request_references_from_state(state: dict[str, Any]) -> dict[str, Any]:
    selected_ids = [item for item in state.get("selectedNodeIds") or [] if isinstance(item, str)]
    source_id = selected_ids[0] if selected_ids else ""
    source = _find_node(state, source_id) if source_id else None
    reference_nodes: list[dict[str, Any]] = []
    if source:
        reference_nodes.append(_node_reference(source, "source"))
        for upstream_id in _collect_upstream_node_ids(state, source_id):
            upstream = _find_node(state, upstream_id)
            if upstream:
                reference_nodes.append(_node_reference(upstream, "upstream"))
    node_ids = {str(node.get("nodeId")) for node in reference_nodes if node.get("nodeId")}
    reference_connections = [
        {
            "id": conn.get("id"),
            "fromNodeId": conn.get("fromNodeId"),
            "toNodeId": conn.get("toNodeId"),
        }
        for conn in _connections(state)
        if isinstance(conn, dict) and conn.get("fromNodeId") in node_ids and conn.get("toNodeId") in node_ids
    ]
    return {"referenceNodes": reference_nodes, "referenceConnections": reference_connections}


def _next_canvas_x(state: dict[str, Any]) -> float:
    nodes = _nodes(state)
    if not nodes:
        return 0
    return max(float(node.get("position", {}).get("x", 0)) + float(node.get("width", 0)) for node in nodes if isinstance(node, dict)) + 80


def _compact_node(node: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(node.get("metadata") or {})
    content = metadata.get("content")
    if isinstance(content, str) and len(content) > 240:
        metadata["content"] = f"{content[:120]}..."
    return {
        "id": node.get("id"),
        "type": node.get("type"),
        "title": node.get("title"),
        "position": node.get("position"),
        "width": node.get("width"),
        "height": node.get("height"),
        "metadata": metadata,
    }


def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "nodes": [_compact_node(node) for node in _nodes(state) if isinstance(node, dict)],
    }


def _summarize_ops(ops: list[dict[str, Any]]) -> str:
    labels = {
        "add_node": "新增节点",
        "update_node": "更新节点",
        "delete_node": "删除节点",
        "delete_connections": "删除连线",
        "connect_nodes": "连接",
        "set_viewport": "调整视图",
        "select_nodes": "选择节点",
        "run_generation": "触发生成",
    }
    counts: dict[str, int] = {}
    for op in ops:
        op_type = str(op.get("type") or "")
        counts[op_type] = counts.get(op_type, 0) + 1
    return "，".join(f"{labels.get(key, key)} {count}" for key, count in counts.items() if key)


def _create_node(
    node_type: str,
    position: dict[str, Any],
    *,
    node_id: str | None = None,
    title: str | None = None,
    width: float | None = None,
    height: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = NODE_DEFAULTS.get(node_type, NODE_DEFAULTS["text"])
    width_value = _normalize_node_dimension(width, float(spec["width"]))
    height_value = _normalize_node_dimension(height, float(spec["height"]))
    return {
        "id": node_id or _uid(node_type),
        "type": node_type,
        "title": title or spec["title"],
        "position": {
            "x": float(position.get("x", 0)),
            "y": float(position.get("y", 0)),
        },
        "width": width_value,
        "height": height_value,
        "metadata": {**dict(spec.get("metadata") or {}), **dict(metadata or {})},
    }


def _normalize_node_dimension(value: float | None, default_value: float) -> float:
    if value is None:
        return default_value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default_value
    return numeric if numeric > default_value else default_value


def _normalize_add_node_op(op: dict[str, Any]) -> dict[str, Any]:
    if op.get("type") != "add_node":
        return op
    node_type = op.get("nodeType") if op.get("nodeType") in NODE_DEFAULTS else "text"
    spec = NODE_DEFAULTS[node_type]
    return {
        **op,
        "nodeType": node_type,
        "width": _normalize_node_dimension(op.get("width"), float(spec["width"])),
        "height": _normalize_node_dimension(op.get("height"), float(spec["height"])),
    }


def _apply_ops_to_state(state: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = list(_nodes(state))
    connections = list(_connections(state))
    selected_ids = list(state.get("selectedNodeIds") or [])
    viewport = dict(state.get("viewport") or {"x": 0, "y": 0, "k": 1})

    for index, op in enumerate(ops):
        op_type = op.get("type")
        if op_type == "add_node":
            node_type = op.get("nodeType") if op.get("nodeType") in NODE_DEFAULTS else "text"
            position = op.get("position") if isinstance(op.get("position"), dict) else {"x": op.get("x", index * 40), "y": op.get("y", index * 40)}
            node = _create_node(
                node_type,
                position,
                node_id=op.get("id"),
                title=op.get("title"),
                width=op.get("width"),
                height=op.get("height"),
                metadata=op.get("metadata") if isinstance(op.get("metadata"), dict) else None,
            )
            nodes.append(node)
            selected_ids = [node["id"]]
        elif op_type == "update_node":
            node_id = op.get("id")
            patch = op.get("patch") if isinstance(op.get("patch"), dict) else {}
            metadata = op.get("metadata") if isinstance(op.get("metadata"), dict) else {}
            next_nodes = []
            for node in nodes:
                if not isinstance(node, dict) or not _node_ids_match(node.get("id"), node_id):
                    next_nodes.append(node)
                    continue
                merged = {**node, **patch}
                merged["metadata"] = {**dict(node.get("metadata") or {}), **dict(patch.get("metadata") or {}), **metadata}
                next_nodes.append(merged)
            nodes = next_nodes
        elif op_type == "delete_node":
            ids = set(op.get("ids") or ([op["id"]] if op.get("id") else []))
            node_type = op.get("nodeType")
            if node_type:
                ids.update(str(node.get("id")) for node in nodes if isinstance(node, dict) and node.get("type") == node_type)
            nodes = [node for node in nodes if not isinstance(node, dict) or not any(_node_ids_match(node.get("id"), target_id) for target_id in ids)]
            connections = [
                conn
                for conn in connections
                if not isinstance(conn, dict)
                or (not any(_node_ids_match(conn.get("fromNodeId"), tid) for tid in ids) and not any(_node_ids_match(conn.get("toNodeId"), tid) for tid in ids))
            ]
            selected_ids = [node_id for node_id in selected_ids if not any(_node_ids_match(node_id, tid) for tid in ids)]
        elif op_type == "delete_connections":
            if op.get("all"):
                connections = []
            else:
                ids = set(op.get("ids") or ([op["id"]] if op.get("id") else []))
                connections = [conn for conn in connections if not isinstance(conn, dict) or not any(_node_ids_match(conn.get("id"), tid) for tid in ids)]
        elif op_type == "connect_nodes":
            from_id = op.get("fromNodeId")
            to_id = op.get("toNodeId")
            if not from_id or not to_id or _node_ids_match(from_id, to_id):
                continue
            from_node = next((node for node in nodes if isinstance(node, dict) and _node_ids_match(node.get("id"), from_id)), None)
            to_node = next((node for node in nodes if isinstance(node, dict) and _node_ids_match(node.get("id"), to_id)), None)
            if not from_node or not to_node:
                continue
            real_from_id = str(from_node.get("id"))
            real_to_id = str(to_node.get("id"))
            exists = any(
                isinstance(conn, dict)
                and _node_ids_match(conn.get("fromNodeId"), real_from_id)
                and _node_ids_match(conn.get("toNodeId"), real_to_id)
                for conn in connections
            )
            if not exists:
                connections.append(
                    _clean_record(
                        {
                            "id": op.get("id") or _uid("conn"),
                            "fromNodeId": real_from_id,
                            "toNodeId": real_to_id,
                            "contentRole": op.get("contentRole"),
                        }
                    )
                )
        elif op_type == "set_viewport" and isinstance(op.get("viewport"), dict):
            viewport = dict(op["viewport"])
        elif op_type == "select_nodes":
            requested = [node_id for node_id in op.get("ids", []) if isinstance(node_id, str)]
            existing = {str(node.get("id")) for node in nodes if isinstance(node, dict)}
            selected_ids = [node_id for node_id in requested if node_id in existing]

    state["nodes"] = nodes
    state["connections"] = connections
    state["selectedNodeIds"] = selected_ids
    state["viewport"] = viewport
    return state


class _CanvasEmitter:
    @staticmethod
    async def emit(context: ToolExecutionContext, ops: list[dict[str, Any]]) -> ToolResult:
        ops = [_normalize_add_node_op(op) for op in ops]
        skipped_redundant = [op for op in ops if _is_redundant_media_success_update(context, op)]
        if skipped_redundant:
            skipped_ids = {id(op) for op in skipped_redundant}
            ops = [op for op in ops if id(op) not in skipped_ids]
            if not ops:
                return ToolResult(
                    output=(
                        "Skipped redundant canvas node update. Media artifacts are already applied "
                        "to target canvas nodes from agent_artifact canvas_request fields."
                    ),
                    metadata={"skipped_redundant_canvas_updates": len(skipped_redundant)},
                )

        state = _state_from_context(context)
        apply_ops = [op for op in ops if op.get("type") != "run_generation"]
        if apply_ops:
            _apply_ops_to_state(state, apply_ops)

        thread_id = str(context.metadata.get("thread_id") or "")
        if not thread_id:
            return ToolResult(output="Missing thread_id; canvas operations were not sent.", is_error=True)
        try:
            from ws_agent import manager

            canvas_request = context.metadata.get("canvas_request")
            await manager.send_event(
                thread_id,
                "canvas_ops",
                {
                    "ops": ops,
                    "request_id": canvas_request.get("id") if isinstance(canvas_request, dict) else None,
                    "message": _summarize_ops(ops) or f"已应用 {len(ops)} 个画布操作。",
                },
            )
        except Exception as exc:
            return ToolResult(output=f"Failed to send canvas operations: {exc}", is_error=True)

        summary = _summarize_ops(ops) or f"已发送 {len(ops)} 个画布操作。"
        details: list[str] = []
        added_nodes = [op for op in ops if op.get("type") == "add_node"]
        for n in added_nodes:
            nid = n.get("id")
            title = n.get("title") or n.get("nodeType") or "节点"
            pos = n.get("position") if isinstance(n.get("position"), dict) else {"x": n.get("x", 0), "y": n.get("y", 0)}
            details.append(f"- 新建节点: id=\"{nid}\", title=\"{title}\", position={pos}, width={n.get('width')}, height={n.get('height')}")
        connected_ops = [op for op in ops if op.get("type") == "connect_nodes"]
        for c in connected_ops:
            details.append(f"- 建立连线: from=\"{c.get('fromNodeId')}\" -> to=\"{c.get('toNodeId')}\" ({c.get('contentRole') or 'connect'})")

        output_text = summary
        if details:
            output_text += "\n" + "\n".join(details)

        return ToolResult(
            output=output_text,
            metadata={"canvas_ops": ops, "canvas_state": _compact_state(state)},
        )


class CanvasGetStateTool(BaseTool):
    name = "canvas_get_state"
    description = (
        "读取当前 Bahew Canvas v2 的节点、连线、选区和参考素材。"
        "支持 scope='all'（全量概览）、scope='selection'（仅选中/高亮卡片）、scope='references'（当前请求关联的素材与参考节点）。"
    )
    input_model = CanvasGetStateInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: CanvasGetStateInput, context: ToolExecutionContext) -> ToolResult:
        scope = (getattr(arguments, "scope", None) or "all").lower()
        if scope == "selection":
            state = _state_from_context(context)
            ids = set(state.get("selectedNodeIds") or [])
            nodes = [_compact_node(node) for node in _nodes(state) if isinstance(node, dict) and node.get("id") in ids]
            return ToolResult(output=json.dumps({"nodes": nodes}, ensure_ascii=False))

        if scope == "references":
            request = _canvas_request(context)
            references = {
                "requestId": request.get("id"),
                "kind": request.get("kind"),
                "sourceNodeId": request.get("sourceNodeId"),
                "targetNodeId": request.get("targetNodeId"),
                "targetNodeIds": request.get("targetNodeIds"),
                "outputCount": request.get("outputCount"),
                "userPrompt": request.get("userPrompt"),
                "attachments": request.get("attachments") or [],
                "referenceNodes": request.get("referenceNodes") or [],
                "referenceConnections": request.get("referenceConnections") or [],
            }
            fallback = _request_references_from_state(_state_from_context(context))
            if not references["referenceNodes"]:
                references["referenceNodes"] = fallback["referenceNodes"]
                references["referenceConnections"] = fallback["referenceConnections"]
            return ToolResult(
                output=json.dumps(references, ensure_ascii=False),
                metadata={"canvas_request_references": references},
            )

        return ToolResult(output=json.dumps(_compact_state(_state_from_context(context)), ensure_ascii=False))


class CanvasCreateNodesTool(BaseTool):
    name = "canvas_create_nodes"
    description = (
        "在画布批量或单个创建卡片节点（text、image、video、audio）。"
        "极其适合脑图拆解、章节大纲、分镜表、角色清单或卡片流。"
        "支持 relative_to_node_id 基准锚定与 layout='tree_right'（向右辐射脑图树）、'tree_bottom'、'grid'、'row'、'column'，"
        "并支持 auto_connect=True（或 connect_from_parent=True）自动从父节点建立连线。"
    )
    input_model = CanvasCreateNodesInput

    async def execute(self, arguments: CanvasCreateNodesInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        gap = arguments.gap if arguments.gap is not None else 40.0
        anchor_node = _get_default_anchor_node(context, state, arguments.relative_to_node_id)
        parent_id = str(anchor_node.get("id")) if anchor_node else None
        should_connect = bool(arguments.connect_from_parent or arguments.auto_connect)

        items = list(arguments.items or arguments.nodes or [])
        if not items:
            return ToolResult(output="items 列表不能为空，请至少提供一个待创建的节点。", is_error=True)
        items_count = len(items)
        first_item = items[0]
        first_type = first_item.nodeType or "text"
        default_w = NODE_DEFAULTS.get(first_type, NODE_DEFAULTS["text"])["width"]
        default_h = NODE_DEFAULTS.get(first_type, NODE_DEFAULTS["text"])["height"]

        if items_count == 1 and not arguments.layout:
            item = first_item
            node_type = item.nodeType or "text"
            spec = NODE_DEFAULTS.get(node_type, NODE_DEFAULTS["text"])
            item_w = _normalize_node_dimension(item.width, float(spec["width"]))
            item_h = _normalize_node_dimension(item.height, float(spec["height"]))

            if item.x is not None and item.y is not None:
                x, y = float(item.x), float(item.y)
            elif arguments.x is not None and arguments.y is not None:
                x, y = float(arguments.x), float(arguments.y)
            else:
                x, y = _resolve_placement_position(
                    state, anchor_node, arguments.placement or "right", gap, item_w, item_h
                )

            new_id = _uid(node_type)
            metadata = dict(item.metadata or {})
            text_val = item.text or item.content or ""
            if node_type == "text":
                metadata.setdefault("content", text_val)
                metadata.setdefault("status", "success")
                metadata.setdefault("fontSize", 14)
            if item.color:
                metadata["color"] = item.color

            op = {
                "type": "add_node",
                "id": new_id,
                "nodeType": node_type,
                "title": item.title,
                "position": {"x": x, "y": y},
                "width": item_w,
                "height": item_h,
                "metadata": metadata,
            }
            ops = [_clean_record(op)]
            if should_connect and parent_id:
                ops.append(
                    _clean_record(
                        {
                            "type": "connect_nodes",
                            "fromNodeId": parent_id,
                            "toNodeId": new_id,
                            "contentRole": arguments.content_role or "context",
                        }
                    )
                )
            return await _CanvasEmitter.emit(context, ops)

        layout_mode = arguments.layout or (
            "tree_right" if anchor_node and should_connect else "column"
        )

        if arguments.x is not None and arguments.y is not None:
            base_x, base_y = float(arguments.x), float(arguments.y)
        elif anchor_node:
            pos = anchor_node.get("position") if isinstance(anchor_node.get("position"), dict) else {}
            ax = float(pos.get("x", 0))
            ay = float(pos.get("y", 0))
            aw = float(anchor_node.get("width", default_w))
            ah = float(anchor_node.get("height", default_h))
            if layout_mode == "tree_bottom":
                base_x = ax
                base_y = ay + ah + 80.0
            else:  # tree_right or default
                base_x = ax + aw + 100.0
                total_h = items_count * default_h + (items_count - 1) * gap
                base_y = (ay + ah / 2.0) - (total_h / 2.0)
        else:
            base_x = _next_canvas_x(state)
            base_y = 0.0

        ops: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            node_type = item.nodeType or "text"
            spec = NODE_DEFAULTS.get(node_type, NODE_DEFAULTS["text"])
            item_w = _normalize_node_dimension(item.width, float(spec["width"]))
            item_h = _normalize_node_dimension(item.height, float(spec["height"]))
            new_id = _uid(node_type)

            if item.x is not None:
                item_x = float(item.x)
            elif layout_mode in {"tree_bottom", "row"}:
                item_x = base_x + index * (default_w + gap)
            elif layout_mode == "grid":
                cols = 2 if items_count <= 4 else 3
                item_x = base_x + (index % cols) * (default_w + gap)
            else:
                item_x = base_x

            if item.y is not None:
                item_y = float(item.y)
            elif layout_mode in {"tree_bottom", "row"}:
                item_y = base_y
            elif layout_mode == "grid":
                cols = 2 if items_count <= 4 else 3
                item_y = base_y + (index // cols) * (default_h + gap)
            else:
                item_y = base_y + index * (default_h + gap)

            metadata = dict(item.metadata or {})
            text_val = item.text or item.content or ""
            if node_type == "text":
                metadata.setdefault("content", text_val)
                metadata.setdefault("status", "success")
                metadata.setdefault("fontSize", 14)
            if item.color:
                metadata["color"] = item.color

            ops.append(
                _clean_record(
                    {
                        "type": "add_node",
                        "id": new_id,
                        "nodeType": node_type,
                        "title": item.title or (f"分支 {index + 1}" if items_count > 1 else None),
                        "position": {"x": item_x, "y": item_y},
                        "width": item_w,
                        "height": item_h,
                        "metadata": metadata,
                    }
                )
            )

            if should_connect and parent_id:
                ops.append(
                    _clean_record(
                        {
                            "type": "connect_nodes",
                            "fromNodeId": parent_id,
                            "toNodeId": new_id,
                            "contentRole": arguments.content_role or "context",
                        }
                    )
                )

        return await _CanvasEmitter.emit(context, ops)


class CanvasApplyOpsTool(BaseTool):
    name = "canvas_apply_ops"
    description = "批量操作当前画布。支持新增/更新/删除节点、连线、选择节点和调整视口。"
    input_model = CanvasApplyOpsInput

    async def execute(self, arguments: CanvasApplyOpsInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [op.model_dump(exclude_none=True) for op in arguments.ops])


__all__ = [
    "CanvasGetStateTool",
    "CanvasCreateNodesTool",
    "CanvasApplyOpsTool",
    "CanvasGetStateInput",
    "CanvasCreateNodesInput",
    "CanvasApplyOpsInput",
    "CreateNodeItem",
]

