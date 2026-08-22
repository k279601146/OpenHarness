from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


AskUserPrompt = Callable[[str | dict[str, Any]], Awaitable[str]]
AskUserFormFieldType = Literal[
    "text",
    "textarea",
    "select",
    "multi_select",
    "number",
    "boolean",
    "duration",
    "aspect_ratio",
    "file_upload",
    "image_reference",
]


class AskUserFormOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Human-readable option label")
    value: str | int | float | bool | None = Field(default=None, description="Machine-readable option value")
    description: str | None = Field(default=None, description="Optional helper text")
    recommended: bool = Field(default=False, description="Whether this option should be highlighted as the default")

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("label must not be empty")
        return text


class AskUserFormFileConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_files: int = Field(default=1, ge=1, le=20)
    max_bytes: int | None = Field(default=None, ge=1)
    allowed_mime_types: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(default_factory=list)


class AskUserFormField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable field identifier")
    label: str = Field(description="User-facing field label")
    type: AskUserFormFieldType = Field(description="Field type")
    description: str | None = Field(default=None, description="Optional long description")
    help_text: str | None = Field(default=None, description="Short helper text")
    placeholder: str | None = Field(default=None, description="Placeholder shown in text inputs")
    required: bool = Field(default=False, description="Whether the field must be filled")
    default_value: Any = Field(default=None, description="Default value used when the form opens")
    options: list[AskUserFormOption] = Field(default_factory=list, description="Select options")
    allow_custom: bool = Field(default=False, description="Whether select or multi_select fields accept direct custom input")
    custom_placeholder: str | None = Field(default=None, description="Placeholder for direct custom input")
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = Field(default=None, gt=0)
    rows: int | None = Field(default=None, ge=1, le=24)
    file_constraints: AskUserFormFileConstraints | None = None
    accept: list[str] = Field(default_factory=list, description="Accepted file extensions or mime types")

    @field_validator("id", "label")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("accept")
    @classmethod
    def _normalize_accept(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _validate_field(self) -> "AskUserFormField":
        if self.type in {"select", "multi_select"} and not self.options:
            raise ValueError(f"{self.id} requires at least one option")
        if self.allow_custom and self.type not in {"select", "multi_select", "aspect_ratio"}:
            raise ValueError(f"{self.id} allow_custom only applies to select, multi_select, or aspect_ratio fields")
        if self.type == "select" and sum(1 for option in self.options if option.recommended) > 1:
            raise ValueError(f"{self.id} select fields may only mark one recommended option")
        if self.type in {"text", "textarea"}:
            if self.rows is not None and self.type != "textarea":
                raise ValueError(f"{self.id} rows only apply to textarea fields")
        if self.type == "aspect_ratio" and not self.options:
            self.options = [
                AskUserFormOption(label=value, value=value)
                for value in ("1:1", "4:5", "9:16", "16:9", "21:9")
            ]
        elif self.type == "aspect_ratio" and any(option.value is None for option in self.options):
            for option in self.options:
                if option.value is None:
                    option.value = option.label
        if self.file_constraints is None and self.type in {"file_upload", "image_reference"}:
            self.file_constraints = AskUserFormFileConstraints(
                allowed_mime_types=["image/*"] if self.type == "image_reference" else [],
                allowed_extensions=[".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"] if self.type == "image_reference" else [],
            )
        if self.accept:
            self.accept = list(dict.fromkeys(self.accept))
        elif self.file_constraints is not None:
            derived_accept = list(self.file_constraints.allowed_mime_types) + list(self.file_constraints.allowed_extensions)
            self.accept = list(dict.fromkeys(str(item).strip() for item in derived_accept if str(item).strip()))
        if self.type == "select" and self.default_value is not None:
            allowed_values = {option.value if option.value is not None else option.label for option in self.options}
            if (
                not self.allow_custom
                and self.default_value not in allowed_values
                and str(self.default_value) not in {str(value) for value in allowed_values}
            ):
                raise ValueError(f"{self.id} default_value must match one of the select options")
        if self.type == "multi_select" and self.default_value is not None and not isinstance(self.default_value, list):
            raise ValueError(f"{self.id} default_value must be a list")
        return self


class AskUserFormSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable section identifier")
    title: str = Field(description="Section title")
    description: str | None = Field(default=None, description="Optional section description")
    fields: list[AskUserFormField] = Field(default_factory=list, description="Fields in this section")

    @field_validator("id", "title")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text


class AskUserFormToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Form title shown to the user")
    purpose: str | None = Field(default=None, description="Why the form is needed")
    interaction_kind: Literal["form"] = Field(default="form", description="Interaction marker")
    allow_skip: bool = Field(default=True, description="Whether the user can skip this form")
    submit_label: str = Field(default="提交", description="Submit button label")
    cancel_label: str = Field(default="跳过", description="Cancel button label")
    sections: list[AskUserFormSection] = Field(default_factory=list, description="Form sections")

    @field_validator("title", "submit_label", "cancel_label")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("purpose")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def _validate_sections(self) -> "AskUserFormToolInput":
        if not self.sections:
            raise ValueError("sections must not be empty")
        seen_ids: set[str] = set()
        seen_field_ids: set[str] = set()
        for section in self.sections:
            if section.id in seen_ids:
                raise ValueError(f"duplicate section id: {section.id}")
            seen_ids.add(section.id)
            if not section.fields:
                raise ValueError(f"section {section.id} must contain at least one field")
            for field in section.fields:
                if field.id in seen_field_ids:
                    raise ValueError(f"duplicate field id: {field.id}")
                seen_field_ids.add(field.id)
        return self


class AskUserFormTool(BaseTool):
    """Ask the interactive user to fill a structured form."""

    name = "ask_user_form"
    description = (
        "Ask the interactive user to fill a structured form and return a canonical submission. "
        "Use this tool for multi-field intake, ad briefs, production briefs, or any workflow that needs sectioned input, uploads, defaults, and review before continuing."
    )
    input_model = AskUserFormToolInput
    default_start_message = "正在打开结构化表单..."
    display_name = "结构化表单"

    def is_read_only(self, arguments: AskUserFormToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: AskUserFormToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        prompt = context.metadata.get("ask_user_prompt")
        if not callable(prompt):
            return ToolResult(
                output="ask_user_form is unavailable in this session",
                is_error=True,
            )
        if not context.metadata.get("ask_user_prompt_accepts_structured"):
            return ToolResult(
                output="ask_user_form requires a structured interactive host",
                is_error=True,
            )

        payload: dict[str, Any] = arguments.model_dump(exclude_none=True)
        payload["tool_name"] = self.name
        payload["tool_use_id"] = str(context.metadata.get("tool_use_id") or "").strip()
        payload["interaction_kind"] = "form"
        answer = await prompt(payload)
        if isinstance(answer, str):
            answer = answer.strip()
        if not answer:
            return ToolResult(output="(no response)")
        return ToolResult(output=str(answer))
