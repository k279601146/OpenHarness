"""Declarative Agent Preset (`dsh-agent-preset` inspired) and structured output validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

import yaml


@dataclass(frozen=True)
class AgentPreset:
    """Declarative capability bundle isolating model, prompt sections, tools, and skills per scenario."""

    name: str
    description: str = ""
    model: str | None = None
    system_prompt_sections: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    allowed_skills: tuple[str, ...] = ()
    max_turns: int | None = None
    read_only: bool = False
    external_cli: str | None = None

    def apply_to_metadata(self, base_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a copy of *base_metadata* with this preset's isolation constraints applied."""
        meta = dict(base_metadata or {})
        meta["active_agent_preset"] = self.name
        if self.allowed_tools:
            meta["preset_allowed_tools"] = list(self.allowed_tools)
        if self.disallowed_tools:
            meta["preset_disallowed_tools"] = list(self.disallowed_tools)
        if self.allowed_skills:
            meta["allowed_user_skill_ids"] = list(self.allowed_skills)
        if self.read_only:
            meta["preset_read_only"] = True
        if self.external_cli:
            meta["external_cli"] = self.external_cli
        return meta

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentPreset":
        return cls(
            name=str(data["name"]).strip(),
            description=str(data.get("description") or "").strip(),
            model=str(data["model"]).strip() if data.get("model") else None,
            system_prompt_sections=tuple(str(x) for x in (data.get("system_prompt_sections") or ())),
            allowed_tools=tuple(str(x).strip() for x in (data.get("allowed_tools") or ()) if str(x).strip()),
            disallowed_tools=tuple(str(x).strip() for x in (data.get("disallowed_tools") or ()) if str(x).strip()),
            allowed_skills=tuple(str(x).strip() for x in (data.get("allowed_skills") or ()) if str(x).strip()),
            max_turns=int(data["max_turns"]) if data.get("max_turns") is not None else None,
            read_only=bool(data.get("read_only", False)),
            external_cli=str(data["external_cli"]).strip() if data.get("external_cli") else None,
        )


BUILTIN_AGENT_PRESETS: dict[str, AgentPreset] = {
    "general": AgentPreset(
        name="general",
        description="General-purpose autonomous agent with full standard workspace toolset.",
    ),
    "researcher": AgentPreset(
        name="researcher",
        description="Read-only codebase and web researcher.",
        allowed_tools=("read_file", "glob", "grep", "web_search", "web_fetch", "run_code", "skill", "tool_search"),
        disallowed_tools=("write_file", "edit_file", "apply_patch", "bash"),
        read_only=True,
        system_prompt_sections=(
            "You are running under the `researcher` preset. Inspect files and gather evidence without mutating the workspace.",
        ),
    ),
    "coder": AgentPreset(
        name="coder",
        description="Focused software engineering preset with code editing, execution, and verification tools.",
        allowed_tools=(
            "read_file",
            "write_file",
            "edit_file",
            "apply_patch",
            "glob",
            "grep",
            "bash",
            "run_code",
            "skill",
            "todo_write",
            "task_board",
        ),
        system_prompt_sections=(
            "You are running under the `coder` preset. Make minimal, verified code changes and run lightweight checks.",
        ),
    ),
    "short_drama": AgentPreset(
        name="short_drama",
        description="Short-drama script, storyboard, and visual asset generation preset.",
        allowed_tools=(
            "read_file",
            "write_file",
            "edit_file",
            "generate_image",
            "generate_video",
            "skill",
            "run_code",
            "deliver_artifact",
        ),
    ),
    "voice": AgentPreset(
        name="voice",
        description="Audio/TTS synthesis, voice design, and voice cloning preset.",
        allowed_tools=(
            "read_file",
            "write_file",
            "generate_audio",
            "skill",
            "deliver_artifact",
        ),
    ),
    "connector_ops": AgentPreset(
        name="connector_ops",
        description="External workspace connector operations preset.",
        disallowed_tools=("generate_image", "generate_video", "generate_audio"),
    ),
}


class AgentPresetRegistry:
    """Registry of named `AgentPreset` definitions."""

    def __init__(self, *, include_builtins: bool = True) -> None:
        self._presets: dict[str, AgentPreset] = {}
        if include_builtins:
            for k, preset in BUILTIN_AGENT_PRESETS.items():
                self._presets[k] = preset

    def register(self, preset: AgentPreset) -> None:
        self._presets[preset.name.strip().lower()] = preset

    def get(self, name: str | None) -> AgentPreset | None:
        if not name:
            return None
        return self._presets.get(name.strip().lower())

    def list_presets(self) -> list[AgentPreset]:
        return list(self._presets.values())

    def load_yaml(self, yaml_text: str) -> list[AgentPreset]:
        loaded = yaml.safe_load(yaml_text)
        items = loaded.get("presets", loaded) if isinstance(loaded, dict) else loaded
        if isinstance(items, dict):
            items = [{"name": k, **v} for k, v in items.items() if isinstance(v, dict)]
        out: list[AgentPreset] = []
        if isinstance(items, list):
            for raw in items:
                if isinstance(raw, dict) and raw.get("name"):
                    preset = AgentPreset.from_dict(raw)
                    self.register(preset)
                    out.append(preset)
        return out


DEFAULT_PRESET_REGISTRY = AgentPresetRegistry()


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def extract_and_validate_structured_output(
    text: str,
    schema: dict[str, Any],
) -> tuple[Any | None, str | None]:
    """Extract JSON from *text* and validate it against a JSON Schema subset.

    Returns `(parsed_value, error_message)`. When valid, `error_message` is `None`.
    """
    raw = (text or "").strip()
    if not raw:
        return None, "Empty output; expected JSON matching output_schema"

    candidates: list[str] = [raw]
    for match in _JSON_FENCE_RE.finditer(raw):
        candidates.insert(0, match.group(1).strip())

    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if 0 <= first_brace < last_brace:
        candidates.append(raw[first_brace : last_brace + 1])

    parsed: Any = None
    parse_err = "Could not parse JSON from output"
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            parse_err = ""
            break
        except Exception as exc:
            parse_err = f"Invalid JSON: {exc}"

    if parse_err:
        return None, parse_err

    err = _validate_json_schema_subset(parsed, schema, path="$")
    if err:
        return None, err
    return parsed, None


def _validate_json_schema_subset(value: Any, schema: dict[str, Any], *, path: str = "$") -> str | None:
    if not isinstance(schema, dict):
        return None
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return f"{path}: expected object, got {type(value).__name__}"
        required = schema.get("required") or ()
        for req_key in required:
            if req_key not in value:
                return f"{path}: missing required property '{req_key}'"
        props = schema.get("properties")
        if isinstance(props, dict):
            for prop_name, prop_schema in props.items():
                if prop_name in value and isinstance(prop_schema, dict):
                    sub_err = _validate_json_schema_subset(
                        value[prop_name],
                        prop_schema,
                        path=f"{path}.{prop_name}",
                    )
                    if sub_err:
                        return sub_err
    elif expected_type == "array":
        if not isinstance(value, list):
            return f"{path}: expected array, got {type(value).__name__}"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                sub_err = _validate_json_schema_subset(item, item_schema, path=f"{path}[{idx}]")
                if sub_err:
                    return sub_err
    elif expected_type == "string":
        if not isinstance(value, str):
            return f"{path}: expected string, got {type(value).__name__}"
        if "enum" in schema and value not in schema["enum"]:
            return f"{path}: value {value!r} not in enum {schema['enum']}"
    elif expected_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{path}: expected integer, got {type(value).__name__}"
    elif expected_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{path}: expected number, got {type(value).__name__}"
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            return f"{path}: expected boolean, got {type(value).__name__}"
    return None
