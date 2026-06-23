"""Tool for asking the interactive user a follow-up question."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


AskUserPrompt = Callable[[str | dict[str, Any]], Awaitable[str]]


class AskUserQuestionPaused(RuntimeError):
    """Raised when an interactive host pauses the agent for a user answer."""


class AskUserQuestionOption(BaseModel):
    """One selectable answer option for an interactive question."""

    label: str = Field(description="Non-empty option label shown to the user")
    recommended: bool = Field(default=False, description="Whether this option is recommended")
    value: str | None = Field(default=None, description="Optional machine-readable option value")


class AskUserQuestionItem(BaseModel):
    """One structured question shown by the interactive host."""

    id: str | None = Field(default=None, description="Stable question identifier")
    question: str = Field(description="Question text shown to the user")
    options: list[AskUserQuestionOption] = Field(
        default_factory=list,
        description="Selectable answer options. Provide at least two options, and mark exactly one best default with recommended=true.",
    )
    allow_custom: bool = Field(default=True, description="Whether the user can provide a custom answer")


class AskUserQuestionToolInput(BaseModel):
    """Arguments for asking the user a question."""

    question: str | None = Field(default=None, description="The exact question to ask the user")
    purpose: str | None = Field(default=None, description="Why the answer is needed")
    questions: list[AskUserQuestionItem] = Field(default_factory=list, description="Structured questions to ask")


class AskUserQuestionTool(BaseTool):
    """Ask the interactive user a question and return the answer."""

    name = "ask_user_question"
    description = (
        "Ask the interactive user for clarification and return the answer. "
        "Use this tool whenever the user's requirement is ambiguous, missing a decision, or needs confirmation before proceeding; "
        "do not ask those questions only in plain assistant text. "
        "For each question, provide non-empty selectable options and mark one recommended option to help the user decide."
    )
    input_model = AskUserQuestionToolInput

    def is_read_only(self, arguments: AskUserQuestionToolInput) -> bool:
        del arguments
        return True

    async def execute(
        self,
        arguments: AskUserQuestionToolInput,
        context: ToolExecutionContext,
    ) -> ToolResult:
        prompt = context.metadata.get("ask_user_prompt")
        if not callable(prompt):
            return ToolResult(
                output="ask_user_question is unavailable in this session",
                is_error=True,
            )
        payload: dict[str, Any] = arguments.model_dump(exclude_none=True)
        if not payload.get("questions") and arguments.question:
            payload["questions"] = [{"id": "question_1", "question": arguments.question, "options": [], "allow_custom": True}]
        prompt_input: str | dict[str, Any] = payload if context.metadata.get("ask_user_prompt_accepts_structured") else (arguments.question or payload["questions"][0]["question"])
        answer = str(await prompt(prompt_input)).strip()
        if not answer:
            return ToolResult(output="(no response)")
        return ToolResult(output=answer)
