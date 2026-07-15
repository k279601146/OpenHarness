"""Canvas operation tools for the SaaS workspace canvas.

These tools mirror the infinite-canvas canvas-agent tool surface while keeping
all model calls, billing, uploads, and task state inside Bahew.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


NodeType = Literal["text", "image", "video", "audio", "config"]
GenerationMode = Literal["text", "image", "video", "audio"]


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
    ids: list[str] | None = None
    nodeType: NodeType | None = None
    title: str | None = None
    x: float | None = None
    y: float | None = None
    position: Position | None = None
    width: float | None = None
    height: float | None = None
    metadata: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None
    all: bool | None = None
    fromNodeId: str | None = None
    toNodeId: str | None = None
    viewport: Viewport | None = None
    nodeId: str | None = None
    mode: GenerationMode | None = None
    prompt: str | None = None


class EmptyInput(_CanvasModel):
    pass


class CanvasGetRequestReferencesInput(_CanvasModel):
    include_state_fallback: bool | None = Field(default=True)


class CanvasApplyOpsInput(_CanvasModel):
    ops: list[CanvasOp] = Field(description="Structured canvas operations to apply in the browser.")


class CanvasCreateNodeInput(_CanvasModel):
    nodeType: NodeType
    title: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    metadata: dict[str, Any] | None = None


class CanvasCreateTextNodeInput(_CanvasModel):
    text: str = ""
    title: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class TextNodeItem(_CanvasModel):
    text: str
    title: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class CanvasCreateTextNodesInput(_CanvasModel):
    items: list[TextNodeItem] = Field(min_length=1)
    x: float | None = None
    y: float | None = None
    gap: float | None = None
    direction: Literal["row", "column"] | None = None


class GenerationOptions(_CanvasModel):
    model: str | None = None
    size: str | None = None
    quality: str | None = None
    count: int | None = None
    seconds: str | None = None
    vquality: str | None = None
    generateAudio: str | None = None
    watermark: str | None = None
    audioVoice: str | None = None
    audioFormat: str | None = None
    audioSpeed: str | None = None
    audioInstructions: str | None = None


class CanvasCreateConfigNodeInput(GenerationOptions):
    prompt: str | None = None
    mode: GenerationMode | None = None
    title: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    autoRun: bool | None = None


class GenerationFlowInput(GenerationOptions):
    prompt: str
    title: str | None = None
    x: float | None = None
    y: float | None = None
    referenceNodeIds: list[str] | None = None
    reference_node_ids: list[str] | None = None
    mode: GenerationMode | None = None
    autoRun: bool | None = None


class CanvasUpdateNodeInput(_CanvasModel):
    id: str
    patch: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class CanvasUpdateNodeTextInput(_CanvasModel):
    id: str
    text: str
    title: str | None = None


class MoveNodeItem(_CanvasModel):
    id: str
    x: float | None = None
    y: float | None = None
    dx: float | None = None
    dy: float | None = None


class CanvasMoveNodesInput(_CanvasModel):
    items: list[MoveNodeItem] = Field(min_length=1)


class CanvasResizeNodeInput(_CanvasModel):
    id: str
    width: float
    height: float
    freeResize: bool | None = None


class CanvasDeleteNodesInput(_CanvasModel):
    ids: list[str] = Field(min_length=1)


class ConnectionInput(_CanvasModel):
    fromNodeId: str
    toNodeId: str


class CanvasConnectNodesInput(_CanvasModel):
    connections: list[ConnectionInput] | None = None
    from_node_id: str | None = None
    to_node_id: str | None = None


class CanvasSelectNodesInput(_CanvasModel):
    ids: list[str]


class CanvasSetViewportInput(_CanvasModel):
    viewport: Viewport


class CanvasRunGenerationInput(_CanvasModel):
    nodeId: str
    mode: GenerationMode | None = None
    prompt: str | None = None


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


def _find_node(state: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return next((node for node in _nodes(state) if isinstance(node, dict) and node.get("id") == node_id), None)


def _canvas_request(context: ToolExecutionContext) -> dict[str, Any]:
    request = context.metadata.get("canvas_request")
    return request if isinstance(request, dict) else {}


def _active_media_canvas_request(context: ToolExecutionContext) -> str | None:
    kind = str(_canvas_request(context).get("kind") or "")
    return kind if kind in {"image_generation", "video_generation"} else None


def _media_request_guidance(kind: str, mode: str) -> str:
    tool_name = "videogen_cli" if kind == "video_generation" else "generate_image"
    return (
        f"当前正在处理真实 canvas_request 媒体生成任务（{kind}）。"
        f"不要递归调用 canvas_generate_{mode} 或 canvas_run_generation；"
        f"请直接使用 {tool_name}，并在完成后返回 agent_artifact。"
    )


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
                if not isinstance(node, dict) or node.get("id") != node_id:
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
            nodes = [node for node in nodes if not isinstance(node, dict) or node.get("id") not in ids]
            connections = [
                conn
                for conn in connections
                if not isinstance(conn, dict) or (conn.get("fromNodeId") not in ids and conn.get("toNodeId") not in ids)
            ]
            selected_ids = [node_id for node_id in selected_ids if node_id not in ids]
        elif op_type == "delete_connections":
            if op.get("all"):
                connections = []
            else:
                ids = set(op.get("ids") or ([op["id"]] if op.get("id") else []))
                connections = [conn for conn in connections if not isinstance(conn, dict) or conn.get("id") not in ids]
        elif op_type == "connect_nodes":
            from_id = op.get("fromNodeId")
            to_id = op.get("toNodeId")
            if not from_id or not to_id or from_id == to_id:
                continue
            has_nodes = any(isinstance(node, dict) and node.get("id") == from_id for node in nodes) and any(
                isinstance(node, dict) and node.get("id") == to_id for node in nodes
            )
            exists = any(isinstance(conn, dict) and conn.get("fromNodeId") == from_id and conn.get("toNodeId") == to_id for conn in connections)
            if has_nodes and not exists:
                connections.append({"id": op.get("id") or _uid("conn"), "fromNodeId": from_id, "toNodeId": to_id})
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


def _generation_mode(value: Any) -> GenerationMode:
    return value if value in {"text", "video", "audio"} else "image"


def _generation_title(mode: str) -> str:
    if mode == "text":
        return "文本生成"
    if mode == "video":
        return "视频生成"
    if mode == "audio":
        return "音频生成"
    return "图片生成"


def _text_node_op(item: dict[str, Any], x: float, y: float) -> dict[str, Any]:
    return {
        "type": "add_node",
        "id": item.get("id"),
        "nodeType": "text",
        "title": item.get("title"),
        "position": {"x": x, "y": y},
        "width": item.get("width"),
        "height": item.get("height"),
        "metadata": {"content": item.get("text") or "", "status": "success", "fontSize": 14},
    }


def _config_node_op(node_id: str, data: dict[str, Any], x: float, y: float) -> dict[str, Any]:
    mode = _generation_mode(data.get("mode"))
    prompt = str(data.get("prompt") or "")
    return {
        "type": "add_node",
        "id": node_id,
        "nodeType": "config",
        "title": data.get("title") or _generation_title(mode),
        "position": {"x": x, "y": y},
        "width": data.get("width"),
        "height": data.get("height"),
        "metadata": _clean_record(
            {
                "generationMode": mode,
                "composerContent": prompt,
                "prompt": prompt,
                "status": "idle",
                "model": data.get("model"),
                "size": data.get("size"),
                "quality": data.get("quality"),
                "count": data.get("count"),
                "seconds": data.get("seconds"),
                "vquality": data.get("vquality"),
                "generateAudio": data.get("generateAudio"),
                "watermark": data.get("watermark"),
                "audioVoice": data.get("audioVoice"),
                "audioFormat": data.get("audioFormat"),
                "audioSpeed": data.get("audioSpeed"),
                "audioInstructions": data.get("audioInstructions"),
            }
        ),
    }


def _run_generation_op(node_id: str, mode: str, prompt: str | None = None) -> dict[str, Any]:
    return {"type": "run_generation", "nodeId": node_id, "mode": mode, "prompt": prompt}


def _flow_reference_ids(data: dict[str, Any]) -> list[str]:
    raw = data.get("referenceNodeIds")
    if raw is None:
        raw = data.get("reference_node_ids")
    return [item for item in raw or [] if isinstance(item, str)]


def _generation_flow_ops(data: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    mode = _generation_mode(data.get("mode"))
    prompt = str(data.get("prompt") or "")
    x = float(data.get("x") if data.get("x") is not None else _next_canvas_x(state))
    y = float(data.get("y") if data.get("y") is not None else 0)
    text_id = _uid("text")
    config_id = _uid("config")
    reference_ids = _flow_reference_ids(data)
    tokens = [f"@[node:{text_id}]", *[f"@[node:{node_id}]" for node_id in reference_ids]]
    config_data = {**data, "prompt": "\n".join(tokens)}
    ops = [
        _text_node_op({"id": text_id, "text": prompt, "title": data.get("title") or "提示词"}, x, y),
        _config_node_op(config_id, config_data, x + NODE_DEFAULTS["text"]["width"] + 80, y),
        {"type": "connect_nodes", "fromNodeId": text_id, "toNodeId": config_id},
        *[{"type": "connect_nodes", "fromNodeId": node_id, "toNodeId": config_id} for node_id in reference_ids],
        {"type": "select_nodes", "ids": [config_id]},
    ]
    if data.get("autoRun"):
        ops.append(_run_generation_op(config_id, mode, "\n".join(tokens)))
    return ops


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

        return ToolResult(
            output=_summarize_ops(ops) or f"已发送 {len(ops)} 个画布操作。",
            metadata={"canvas_ops": ops, "canvas_state": _compact_state(state)},
        )


class CanvasGetStateTool(BaseTool):
    name = "canvas_get_state"
    description = "读取当前 Bahew Canvas v2 的节点、连线、选区和视口。"
    input_model = EmptyInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: EmptyInput, context: ToolExecutionContext) -> ToolResult:
        return ToolResult(output=json.dumps(_compact_state(_state_from_context(context)), ensure_ascii=False))


class CanvasGetSelectionTool(BaseTool):
    name = "canvas_get_selection"
    description = "读取当前 Bahew Canvas v2 选中的节点。"
    input_model = EmptyInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: EmptyInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        ids = set(state.get("selectedNodeIds") or [])
        nodes = [_compact_node(node) for node in _nodes(state) if isinstance(node, dict) and node.get("id") in ids]
        return ToolResult(output=json.dumps({"nodes": nodes}, ensure_ascii=False))


class CanvasGetRequestReferencesTool(BaseTool):
    name = "canvas_get_request_references"
    description = "读取本轮 canvas_request 的精确节点引用包，包括当前源节点、上游节点、连线、附件和用户提示。"
    input_model = CanvasGetRequestReferencesInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: CanvasGetRequestReferencesInput, context: ToolExecutionContext) -> ToolResult:
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
        if arguments.include_state_fallback and not references["referenceNodes"]:
            fallback = _request_references_from_state(_state_from_context(context))
            references["referenceNodes"] = fallback["referenceNodes"]
            references["referenceConnections"] = fallback["referenceConnections"]
        return ToolResult(
            output=json.dumps(references, ensure_ascii=False),
            metadata={"canvas_request_references": references},
        )


class CanvasExportSnapshotTool(CanvasGetStateTool):
    name = "canvas_export_snapshot"
    description = "导出当前画布快照，用于理解布局和节点关系。"


class CanvasApplyOpsTool(BaseTool):
    name = "canvas_apply_ops"
    description = "批量操作当前画布。支持新增/更新/删除节点、连线、选择节点、调整视口和触发生成。"
    input_model = CanvasApplyOpsInput

    async def execute(self, arguments: CanvasApplyOpsInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [op.model_dump(exclude_none=True) for op in arguments.ops])


class CanvasCreateNodeTool(BaseTool):
    name = "canvas_create_node"
    description = "创建任意类型节点：text、image、config、video、audio。"
    input_model = CanvasCreateNodeInput

    async def execute(self, arguments: CanvasCreateNodeInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        x = arguments.x if arguments.x is not None else _next_canvas_x(state)
        y = arguments.y if arguments.y is not None else 0
        data = arguments.model_dump(exclude_none=True)
        if arguments.nodeType == "config":
            op = _config_node_op(_uid("config"), {**dict(arguments.metadata or {}), **data, "mode": data.get("mode") or data.get("generationMode")}, x, y)
        else:
            op = {
                "type": "add_node",
                "nodeType": arguments.nodeType,
                "title": arguments.title,
                "position": {"x": x, "y": y},
                "width": arguments.width,
                "height": arguments.height,
                "metadata": arguments.metadata,
            }
        return await _CanvasEmitter.emit(context, [_clean_record(op)])


class CanvasCreateTextNodeTool(BaseTool):
    name = "canvas_create_text_node"
    description = "在当前画布创建单个文本节点。"
    input_model = CanvasCreateTextNodeInput

    async def execute(self, arguments: CanvasCreateTextNodeInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        x = arguments.x if arguments.x is not None else _next_canvas_x(state)
        y = arguments.y if arguments.y is not None else 0
        return await _CanvasEmitter.emit(context, [_text_node_op(arguments.model_dump(exclude_none=True), x, y)])


class CanvasCreateTextNodesTool(BaseTool):
    name = "canvas_create_text_nodes"
    description = "批量创建文本节点，适合生成标题、段落、脚本、说明等内容块。"
    input_model = CanvasCreateTextNodesInput

    async def execute(self, arguments: CanvasCreateTextNodesInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        x = arguments.x if arguments.x is not None else _next_canvas_x(state)
        y = arguments.y if arguments.y is not None else 0
        gap = arguments.gap if arguments.gap is not None else 40
        direction = arguments.direction or "column"
        ops: list[dict[str, Any]] = []
        for index, item in enumerate(arguments.items):
            item_data = item.model_dump(exclude_none=True)
            item_x = item.x if item.x is not None else (x + index * (NODE_DEFAULTS["text"]["width"] + gap) if direction == "row" else x)
            item_y = item.y if item.y is not None else (y if direction == "row" else y + index * (NODE_DEFAULTS["text"]["height"] + gap))
            ops.append(_text_node_op(item_data, item_x, item_y))
        return await _CanvasEmitter.emit(context, ops)


class CanvasCreateConfigNodeTool(BaseTool):
    name = "canvas_create_config_node"
    description = "创建生成配置节点，可指定 text/image/video/audio 模式和生成参数，可选择立即触发生成。"
    input_model = CanvasCreateConfigNodeInput

    async def execute(self, arguments: CanvasCreateConfigNodeInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        data = arguments.model_dump(exclude_none=True)
        x = arguments.x if arguments.x is not None else _next_canvas_x(state)
        y = arguments.y if arguments.y is not None else 0
        config_id = _uid("config")
        mode = _generation_mode(arguments.mode)
        ops = [_config_node_op(config_id, data, x, y)]
        if arguments.autoRun:
            ops.append(_run_generation_op(config_id, mode, arguments.prompt))
        return await _CanvasEmitter.emit(context, ops)


class CanvasCreateGenerationFlowTool(BaseTool):
    name = "canvas_create_generation_flow"
    description = "创建通用生成流程：提示词文本节点、生成配置节点、参考节点连线，可用于文案、生图、视频或音频。"
    input_model = GenerationFlowInput

    async def execute(self, arguments: GenerationFlowInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        return await _CanvasEmitter.emit(context, _generation_flow_ops(arguments.model_dump(exclude_none=True), state))


class _CanvasGenerateFlowTool(CanvasCreateGenerationFlowTool):
    generation_mode: GenerationMode = "image"

    async def execute(self, arguments: GenerationFlowInput, context: ToolExecutionContext) -> ToolResult:
        active_kind = _active_media_canvas_request(context)
        if active_kind and self.generation_mode in {"image", "video"}:
            return ToolResult(output=_media_request_guidance(active_kind, self.generation_mode))
        state = _state_from_context(context)
        return await _CanvasEmitter.emit(
            context,
            _generation_flow_ops({**arguments.model_dump(exclude_none=True), "mode": self.generation_mode, "autoRun": True}, state),
        )


class CanvasGenerateTextTool(_CanvasGenerateFlowTool):
    name = "canvas_generate_text"
    description = "使用 Agent 当前已生成的文本内容创建文本节点，不调用外部模型。"
    generation_mode = "text"

    async def execute(self, arguments: GenerationFlowInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        data = arguments.model_dump(exclude_none=True)
        x = arguments.x if arguments.x is not None else _next_canvas_x(state)
        y = arguments.y if arguments.y is not None else 0
        op = _text_node_op(
            {
                "text": arguments.prompt,
                "title": arguments.title or "生成文本",
                "width": data.get("width"),
                "height": data.get("height"),
            },
            x,
            y,
        )
        return await _CanvasEmitter.emit(context, [op])


class CanvasGenerateImageTool(_CanvasGenerateFlowTool):
    name = "canvas_generate_image"
    description = "创建图片生成流程并立即触发 Bahew 图片生成请求。"
    generation_mode = "image"


class CanvasGenerateVideoTool(_CanvasGenerateFlowTool):
    name = "canvas_generate_video"
    description = "创建视频生成流程并立即触发 Bahew 视频生成请求。"
    generation_mode = "video"


class CanvasGenerateAudioTool(CanvasCreateGenerationFlowTool):
    name = "canvas_generate_audio"
    description = "创建音频生成占位流程；当前 Bahew 不启用真实音频生成。"

    async def execute(self, arguments: GenerationFlowInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        ops = _generation_flow_ops({**arguments.model_dump(exclude_none=True), "mode": "audio", "autoRun": False}, state)
        result = await _CanvasEmitter.emit(context, ops)
        if not result.is_error:
            return ToolResult(
                output=f"{result.output}。音频真实生成暂未启用，已创建画布占位流程。",
                metadata=result.metadata,
            )
        return result


class CanvasUpdateNodeTool(BaseTool):
    name = "canvas_update_node"
    description = "更新节点基础字段或 metadata。"
    input_model = CanvasUpdateNodeInput

    async def execute(self, arguments: CanvasUpdateNodeInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [{"type": "update_node", **arguments.model_dump(exclude_none=True)}])


class CanvasUpdateNodeTextTool(BaseTool):
    name = "canvas_update_node_text"
    description = "更新文本节点内容和标题。"
    input_model = CanvasUpdateNodeTextInput

    async def execute(self, arguments: CanvasUpdateNodeTextInput, context: ToolExecutionContext) -> ToolResult:
        op = {
            "type": "update_node",
            "id": arguments.id,
            "patch": {"title": arguments.title} if arguments.title else None,
            "metadata": {"content": arguments.text, "status": "success"},
        }
        return await _CanvasEmitter.emit(context, [_clean_record(op)])


class CanvasMoveNodesTool(BaseTool):
    name = "canvas_move_nodes"
    description = "移动一个或多个节点，支持绝对坐标或 dx/dy 偏移。"
    input_model = CanvasMoveNodesInput

    async def execute(self, arguments: CanvasMoveNodesInput, context: ToolExecutionContext) -> ToolResult:
        state = _state_from_context(context)
        ops: list[dict[str, Any]] = []
        for item in arguments.items:
            current = _find_node(state, item.id) or {}
            current_position = current.get("position") if isinstance(current.get("position"), dict) else {}
            x = item.x if item.x is not None else float(current_position.get("x", 0)) + float(item.dx or 0)
            y = item.y if item.y is not None else float(current_position.get("y", 0)) + float(item.dy or 0)
            ops.append({"type": "update_node", "id": item.id, "patch": {"position": {"x": x, "y": y}}})
        return await _CanvasEmitter.emit(context, ops)


class CanvasResizeNodeTool(BaseTool):
    name = "canvas_resize_node"
    description = "调整节点尺寸。"
    input_model = CanvasResizeNodeInput

    async def execute(self, arguments: CanvasResizeNodeInput, context: ToolExecutionContext) -> ToolResult:
        op = {
            "type": "update_node",
            "id": arguments.id,
            "patch": {"width": arguments.width, "height": arguments.height},
            "metadata": {"freeResize": arguments.freeResize} if arguments.freeResize is not None else None,
        }
        return await _CanvasEmitter.emit(context, [_clean_record(op)])


class CanvasDeleteNodesTool(BaseTool):
    name = "canvas_delete_nodes"
    description = "删除指定节点及相关连线。"
    input_model = CanvasDeleteNodesInput

    async def execute(self, arguments: CanvasDeleteNodesInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [{"type": "delete_node", "ids": arguments.ids}])


class CanvasConnectNodesTool(BaseTool):
    name = "canvas_connect_nodes"
    description = "批量连接节点。"
    input_model = CanvasConnectNodesInput

    async def execute(self, arguments: CanvasConnectNodesInput, context: ToolExecutionContext) -> ToolResult:
        if arguments.connections:
            connections = arguments.connections
        elif arguments.from_node_id and arguments.to_node_id:
            connections = [ConnectionInput(fromNodeId=arguments.from_node_id, toNodeId=arguments.to_node_id)]
        else:
            return ToolResult(output="缺少 connections 或 from_node_id/to_node_id。", is_error=True)
        ops = [{"type": "connect_nodes", "fromNodeId": item.fromNodeId, "toNodeId": item.toNodeId} for item in connections]
        return await _CanvasEmitter.emit(context, ops)


class CanvasSelectNodesTool(BaseTool):
    name = "canvas_select_nodes"
    description = "设置当前选中节点。"
    input_model = CanvasSelectNodesInput

    async def execute(self, arguments: CanvasSelectNodesInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [{"type": "select_nodes", "ids": arguments.ids}])


class CanvasSetViewportTool(BaseTool):
    name = "canvas_set_viewport"
    description = "调整当前画布视口。"
    input_model = CanvasSetViewportInput

    async def execute(self, arguments: CanvasSetViewportInput, context: ToolExecutionContext) -> ToolResult:
        return await _CanvasEmitter.emit(context, [{"type": "set_viewport", "viewport": arguments.viewport.model_dump()}])


class CanvasRunGenerationTool(BaseTool):
    name = "canvas_run_generation"
    description = "触发指定节点生成，通常用于配置节点或媒体占位节点。"
    input_model = CanvasRunGenerationInput

    async def execute(self, arguments: CanvasRunGenerationInput, context: ToolExecutionContext) -> ToolResult:
        mode = _generation_mode(arguments.mode)
        active_kind = _active_media_canvas_request(context)
        if active_kind and mode in {"image", "video"}:
            return ToolResult(output=_media_request_guidance(active_kind, mode))
        if mode == "audio":
            return ToolResult(output="音频真实生成暂未启用，请只创建音频占位节点。", is_error=True)
        return await _CanvasEmitter.emit(context, [_run_generation_op(arguments.nodeId, mode, arguments.prompt)])

