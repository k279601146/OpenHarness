"""Iterative fresh-context subagent loop tool (`tool-ralph` inspired)."""

from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.coordinator.agent_preset import extract_and_validate_structured_output
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

MAX_RALPH_HANDOFF_CHARS = 16_384
MAX_RALPH_ROUNDS = 256

RALPH_HANDOFF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["done", "summary", "next_handoff"],
    "properties": {
        "done": {"type": "boolean"},
        "summary": {"type": "string"},
        "next_handoff": {"type": "object"},
    },
}


class RalphToolInput(BaseModel):
    """Input schema for the `ralph` iterative fresh-agent loop tool."""

    objective: str = Field(
        ...,
        min_length=1,
        description="Overall objective to iteratively achieve across fresh-context subagent rounds.",
    )
    initial_handoff: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial structured handoff state passed into round 1.",
    )
    max_rounds: int = Field(
        default=5,
        ge=1,
        le=MAX_RALPH_ROUNDS,
        description="Maximum fresh-context subagent rounds to run.",
    )
    max_handoff_chars: int = Field(
        default=MAX_RALPH_HANDOFF_CHARS,
        ge=512,
        le=MAX_RALPH_HANDOFF_CHARS,
        description="Maximum serialized JSON characters allowed for inter-round handoff.",
    )
    preset: str | None = Field(
        default=None,
        description="Optional AgentPreset for each round's fresh worker.",
    )


class RalphOutputModel(BaseModel):
    """Structured output contract for `RalphTool`."""

    done: bool
    rounds_executed: int
    stop_reason: Literal["completed", "max_rounds_reached", "error"]
    final_summary: str
    final_handoff: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class RalphTool(BaseTool):
    """Run an iterative loop where each round spawns a fresh-context subagent.

    Prevents context rot on long-horizon tasks by passing only workspace state
    plus a bounded JSON handoff (`<= 16384` chars) from round N to round N+1.
    """

    name = "ralph"
    display_name = "Fresh-Context Iterative Loop"
    description = (
        "Execute a multi-round iterative loop where every round runs in a brand-new subagent context window "
        "and hands off a bounded JSON state (`<= 16KB`) to the next round until `done: true` or `max_rounds`."
    )
    input_model = RalphToolInput
    output_model = RalphOutputModel
    parallel_safe = False
    execution_group = "workflow"

    def when(self, selection_context: Any) -> bool | None:
        meta = getattr(selection_context, "tool_metadata", None)
        if isinstance(meta, dict) and (
            meta.get("enable_ralph")
            or meta.get("ralph_round_runner") is not None
        ):
            return True
        return None

    async def execute(self, arguments: RalphToolInput, context: ToolExecutionContext) -> ToolResult:
        runtime = context.metadata.get("subagent_runtime")
        round_runner = context.metadata.get("ralph_round_runner")
        if runtime is None and not callable(round_runner):
            return ToolResult(
                output="ralph requires `subagent_runtime` or `ralph_round_runner` in context.metadata",
                is_error=True,
            )

        handoff: dict[str, Any] = dict(arguments.initial_handoff or {})
        round_history: list[dict[str, Any]] = []
        done = False
        final_summary = ""
        stop_reason: Literal["completed", "max_rounds_reached", "error"] = "max_rounds_reached"
        started = time.monotonic()

        for round_idx in range(1, arguments.max_rounds + 1):
            handoff_json = json.dumps(handoff, ensure_ascii=False)
            if len(handoff_json) > arguments.max_handoff_chars:
                handoff_json = handoff_json[: arguments.max_handoff_chars - 32] + '..."_truncated":true}'

            round_prompt = (
                f"# Ralph Iterative Objective (Round {round_idx}/{arguments.max_rounds})\n"
                f"{arguments.objective}\n\n"
                f"## Handoff State From Previous Round\n"
                f"```json\n{handoff_json}\n```\n\n"
                "## Instructions\n"
                " make measurable progress in the workspace during this round, verify your changes, "
                "and finish with a JSON block matching `{ \"done\": bool, \"summary\": str, \"next_handoff\": object }`."
            )

            if callable(round_runner):
                raw_out = await round_runner(round_idx, round_prompt, handoff)
                output_text = raw_out if isinstance(raw_out, str) else json.dumps(raw_out, ensure_ascii=False)
                parsed, err = extract_and_validate_structured_output(output_text, RALPH_HANDOFF_SCHEMA)
            else:
                rec = await runtime.spawn(
                    description=f"ralph-round-{round_idx}",
                    prompt=round_prompt,
                    name=f"ralph-r{round_idx}",
                    preset=arguments.preset,
                    output_schema=RALPH_HANDOFF_SCHEMA,
                    parent_id=str(context.metadata.get("subagent_id") or "lead"),
                    parent_depth=int(context.metadata.get("subagent_depth") or 0),
                    parent_cancellation_token=context.cancellation_token,
                    inherit_context=False,
                )
                wait_res = await runtime.wait_for_agents(
                    agent_ids=[rec.agent_id],
                    timeout_seconds=180.0,
                    cancellation_token=context.cancellation_token,
                )
                completed = wait_res.get("completed") or []
                if not completed or completed[0].get("status") != "completed":
                    stop_reason = "error"
                    final_summary = (
                        completed[0].get("error")
                        if completed
                        else f"Ralph round {round_idx} failed or timed out"
                    ) or "Round failed"
                    break
                output_text = str(completed[0].get("output") or "")
                structured = completed[0].get("structured_output")
                if isinstance(structured, dict):
                    parsed, err = structured, None
                else:
                    parsed, err = extract_and_validate_structured_output(output_text, RALPH_HANDOFF_SCHEMA)

            if err is not None or not isinstance(parsed, dict):
                stop_reason = "error"
                final_summary = f"Round {round_idx} did not return valid handoff JSON: {err}"
                round_history.append({"round": round_idx, "error": final_summary, "raw_output": output_text[:1000]})
                break

            done = bool(parsed.get("done"))
            final_summary = str(parsed.get("summary") or "")
            next_handoff = parsed.get("next_handoff")
            handoff = dict(next_handoff) if isinstance(next_handoff, dict) else {"value": next_handoff}
            round_history.append(
                {
                    "round": round_idx,
                    "done": done,
                    "summary": final_summary,
                }
            )
            if done:
                stop_reason = "completed"
                break

        payload = {
            "done": done,
            "rounds_executed": len(round_history),
            "stop_reason": stop_reason,
            "final_summary": final_summary,
            "final_handoff": handoff,
            "history": round_history,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False, indent=2),
            is_error=stop_reason == "error",
            structured_output=payload,
            metadata={"rounds_executed": len(round_history), "stop_reason": stop_reason},
        )
