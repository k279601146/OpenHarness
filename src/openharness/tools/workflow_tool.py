"""Deterministic multi-agent Workflow orchestration tool (`dsh-workflow` inspired)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from openharness.coordinator.agent_preset import extract_and_validate_structured_output
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class WorkflowStepSpec(BaseModel):
    """Specification for a single step or composite block inside a workflow."""

    kind: Literal["agent", "parallel", "pipeline", "phase"] = Field(
        default="agent",
        description="Step type: 'agent' (isolated subagent call), 'parallel' (fan-out), 'pipeline' (sequential), or 'phase' (named stage).",
    )
    name: str = Field(default="step", description="Step or phase identifier")
    prompt: str | None = Field(
        default=None,
        description="Prompt for kind='agent' (supports `{prev}` placeholder for pipeline handoff).",
    )
    preset: str | None = Field(default=None, description="Optional AgentPreset for kind='agent'")
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON Schema contract for kind='agent' output validation",
    )
    fatal: bool = Field(
        default=True,
        description="Whether failure of this step aborts the workflow immediately.",
    )
    steps: list["WorkflowStepSpec"] = Field(
        default_factory=list,
        description="Child steps when kind is 'parallel', 'pipeline', or 'phase'.",
    )


WorkflowStepSpec.model_rebuild()


class WorkflowToolInput(BaseModel):
    """Input schema for running a structured multi-stage workflow."""

    name: str = Field(default="workflow", description="Workflow title for progress telemetry")
    steps: list[WorkflowStepSpec] = Field(
        ...,
        min_length=1,
        description="Top-level workflow steps executed as a pipeline.",
    )
    timeout_seconds: float = Field(
        default=300.0,
        ge=5.0,
        le=1800.0,
        description="Overall timeout in seconds for the workflow run.",
    )


class WorkflowOutputModel(BaseModel):
    """Structured output contract for `WorkflowTool`."""

    workflow: str
    stop_reason: Literal["completed", "cancelled", "error"]
    duration_ms: int
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class WorkflowTool(BaseTool):
    """Orchestrate fan-out (`parallel`), staged (`pipeline` / `phase`), and schema-validated `agent` steps.

    Intermediate subagent transcripts stay out of the parent context window; only
    distilled structured outputs are returned.
    """

    name = "workflow"
    display_name = "Workflow Orchestrator"
    description = (
        "Use this tool ONLY when the user explicitly asks for a workflow or for large multi-stage orchestration. "
        "For normal parallel delegations (such as 2-6 independent research or review subtasks), call `agent` directly instead. "
        "Runs a structured workflow combining `parallel`, `pipeline`, `phase`, and isolated `agent` steps, "
        "returning only aggregated structured outputs."
    )
    input_model = WorkflowToolInput
    output_model = WorkflowOutputModel
    parallel_safe = False
    execution_group = "workflow"

    def when(self, selection_context: Any) -> bool | None:
        meta = getattr(selection_context, "tool_metadata", None)
        if isinstance(meta, dict) and (
            meta.get("enable_workflow")
            or meta.get("workflow_agent_runner") is not None
        ):
            return True
        return None

    async def execute(self, arguments: WorkflowToolInput, context: ToolExecutionContext) -> ToolResult:
        started = time.monotonic()
        runtime = context.metadata.get("subagent_runtime")
        agent_runner = context.metadata.get("workflow_agent_runner")

        async def _emit(phase_name: str, status: str, message: str, detail: dict[str, Any] | None = None) -> None:
            if context.progress_callback is not None:
                await context.progress_callback(
                    {
                        "phase": phase_name,
                        "status": status,
                        "message": message,
                        "metadata": {"workflow": arguments.name, **(detail or {})},
                    }
                )

        async def _run_agent_leaf(step: WorkflowStepSpec, prev_output: Any) -> dict[str, Any]:
            raw_prompt = (step.prompt or "").strip()
            if "{prev}" in raw_prompt:
                prev_str = (
                    json.dumps(prev_output, ensure_ascii=False)
                    if isinstance(prev_output, (dict, list))
                    else str(prev_output or "")
                )
                raw_prompt = raw_prompt.replace("{prev}", prev_str)
            await _emit("workflow/step_start", "running", f"[Workflow {arguments.name}] Running agent step '{step.name}'")

            output_text = ""
            structured: Any = None
            is_err = False
            err_msg: str | None = None

            if callable(agent_runner):
                res = await agent_runner(step, raw_prompt)
                if isinstance(res, dict):
                    output_text = str(res.get("output") or "")
                    structured = res.get("structured_output")
                    is_err = bool(res.get("is_error"))
                    err_msg = res.get("error")
                else:
                    output_text = str(res)
            elif runtime is not None and hasattr(runtime, "spawn"):
                rec = await runtime.spawn(
                    description=f"workflow:{arguments.name}:{step.name}",
                    prompt=raw_prompt,
                    name=step.name,
                    preset=step.preset,
                    output_schema=step.output_schema,
                    parent_id=str(context.metadata.get("subagent_id") or "lead"),
                    parent_depth=int(context.metadata.get("subagent_depth") or 0),
                    parent_cancellation_token=context.cancellation_token,
                    inherit_context=False,
                )
                wait_res = await runtime.wait_for_agents(
                    agent_ids=[rec.agent_id],
                    timeout_seconds=arguments.timeout_seconds,
                    cancellation_token=context.cancellation_token,
                )
                completed = wait_res.get("completed") or []
                if completed:
                    item = completed[0]
                    output_text = str(item.get("output") or "")
                    structured = item.get("structured_output")
                    is_err = item.get("status") != "completed"
                    err_msg = item.get("error")
                else:
                    is_err = True
                    err_msg = f"Workflow step '{step.name}' timed out or did not complete"
            else:
                return {
                    "name": step.name,
                    "kind": "agent",
                    "status": "error",
                    "error": "No subagent_runtime or workflow_agent_runner configured",
                    "fatal": step.fatal,
                }

            if not is_err and step.output_schema and structured is None:
                parsed, schema_err = extract_and_validate_structured_output(output_text, step.output_schema)
                if schema_err is None:
                    structured = parsed
                else:
                    is_err = True
                    err_msg = f"Output schema validation failed for '{step.name}': {schema_err}"

            status_str = "error" if is_err else "completed"
            await _emit(
                "workflow/step_end",
                "error" if is_err else "success",
                f"[Workflow {arguments.name}] Step '{step.name}' {status_str}",
                {"step": step.name, "status": status_str},
            )
            return {
                "name": step.name,
                "kind": "agent",
                "status": status_str,
                "output": structured if structured is not None else output_text,
                "structured_output": structured,
                "error": err_msg,
                "fatal": step.fatal,
            }

        async def _eval_step(step: WorkflowStepSpec, prev_output: Any = None) -> dict[str, Any]:
            if context.cancellation_token is not None and context.cancellation_token.is_cancelled():
                raise asyncio.CancelledError("Workflow cancelled")
            if step.kind == "agent":
                return await _run_agent_leaf(step, prev_output)
            if step.kind == "parallel":
                await _emit("workflow/parallel_start", "running", f"[Workflow {arguments.name}] Parallel block '{step.name}' ({len(step.steps)} branches)")
                branch_results = await asyncio.gather(*(_eval_step(child, prev_output) for child in step.steps))
                failed_fatal = next((b for b in branch_results if b.get("status") == "error" and b.get("fatal", True)), None)
                return {
                    "name": step.name,
                    "kind": "parallel",
                    "status": "error" if failed_fatal else "completed",
                    "output": [b.get("output") for b in branch_results],
                    "branches": list(branch_results),
                    "error": failed_fatal.get("error") if failed_fatal else None,
                    "fatal": step.fatal,
                }
            # 'pipeline' or 'phase'
            await _emit("workflow/phase_start", "running", f"[Workflow {arguments.name}] Entering {step.kind} '{step.name}'")
            stage_results: list[dict[str, Any]] = []
            carry = prev_output
            for child in step.steps:
                res = await _eval_step(child, carry)
                stage_results.append(res)
                carry = res.get("output")
                if res.get("status") == "error" and res.get("fatal", True):
                    return {
                        "name": step.name,
                        "kind": step.kind,
                        "status": "error",
                        "output": carry,
                        "steps": stage_results,
                        "error": res.get("error"),
                        "fatal": step.fatal,
                    }
            return {
                "name": step.name,
                "kind": step.kind,
                "status": "completed",
                "output": carry,
                "steps": stage_results,
                "error": None,
                "fatal": step.fatal,
            }

        await _emit("workflow/start", "running", f"Starting workflow '{arguments.name}'")
        results: list[dict[str, Any]] = []
        stop_reason: Literal["completed", "cancelled", "error"] = "completed"
        workflow_err: str | None = None
        carry_val: Any = None

        try:
            async with asyncio.timeout(arguments.timeout_seconds):
                for top_step in arguments.steps:
                    step_res = await _eval_step(top_step, carry_val)
                    results.append(step_res)
                    carry_val = step_res.get("output")
                    if step_res.get("status") == "error" and step_res.get("fatal", True):
                        stop_reason = "error"
                        workflow_err = str(step_res.get("error") or f"Step '{top_step.name}' failed")
                        break
        except asyncio.CancelledError:
            stop_reason = "cancelled"
            workflow_err = "Workflow cancelled"
        except TimeoutError:
            stop_reason = "error"
            workflow_err = f"Workflow timed out after {arguments.timeout_seconds}s"

        duration_ms = int((time.monotonic() - started) * 1000)
        payload = {
            "workflow": arguments.name,
            "stop_reason": stop_reason,
            "duration_ms": duration_ms,
            "results": results,
            "error": workflow_err,
        }
        await _emit(
            "workflow/end",
            "success" if stop_reason == "completed" else "error",
            f"Workflow '{arguments.name}' finished ({stop_reason}) in {duration_ms}ms",
        )
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False, indent=2),
            is_error=stop_reason == "error",
            structured_output=payload,
            metadata={"workflow": arguments.name, "stop_reason": stop_reason, "duration_ms": duration_ms},
        )
