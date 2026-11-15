"""Prefix-cache-friendly Pre-Execute AutoReview Risk Guard (`dsh-auto-review` inspired)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Literal

from openharness.api.client import ApiMessageCompleteEvent, ApiMessageRequest, SupportsStreamingMessages
from openharness.engine.messages import ConversationMessage
from openharness.hooks.types import HookResult

RiskLevel = Literal["low", "medium", "high"]
ReviewDecision = Literal["allow", "deny"]

DEFAULT_SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {"bash", "write_file", "edit_file", "apply_patch"}
)

_HIGH_RISK_COMMAND_PATTERNS = (
    re.compile(r"\brm\s+-[rRfF]+\s+/(?:\s|$)"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=.*of=/dev/"),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;"),
    re.compile(r"\b(?:curl|wget)\b.*\|\s*(?:sh|bash)\b"),
)


@dataclass(frozen=True)
class AutoReviewOutcome:
    """Risk classification and allow/deny decision for a tool call."""

    risk: RiskLevel
    decision: ReviewDecision
    reason: str = ""
    code: str = ""


class AutoReviewGuard:
    """Pre-execute risk reviewer that reuses the conversation prefix for KV-cache efficiency."""

    def __init__(
        self,
        *,
        api_client: SupportsStreamingMessages | None = None,
        model: str | None = None,
        system_prompt: str = "",
        history_provider: Callable[[], list[ConversationMessage]] | None = None,
        sensitive_tools: set[str] | frozenset[str] = DEFAULT_SENSITIVE_TOOLS,
        block_medium_risk: bool = False,
    ) -> None:
        self._api_client = api_client
        self._model = model
        self._system_prompt = system_prompt
        self._history_provider = history_provider
        self._sensitive_tools = {t.strip().lower() for t in sensitive_tools}
        self._block_medium_risk = block_medium_risk

    def is_sensitive(self, tool_name: str) -> bool:
        normalized = (tool_name or "").strip().lower()
        return normalized in self._sensitive_tools or normalized.startswith("connector__")

    async def evaluate_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> AutoReviewOutcome:
        """Evaluate a tool call using deterministic high-risk rules first, then optional prefix-cached LLM review."""
        if not self.is_sensitive(tool_name):
            return AutoReviewOutcome(risk="low", decision="allow", reason="non-sensitive tool")

        cmd = str(tool_input.get("command") or "")
        for pat in _HIGH_RISK_COMMAND_PATTERNS:
            if pat.search(cmd):
                return AutoReviewOutcome(
                    risk="high",
                    decision="deny",
                    reason=f"High-risk destructive or remote-pipe shell command blocked: {cmd[:120]}",
                    code="AUTO_REVIEW_DENIED",
                )

        if self._api_client is not None and self._model:
            prefix_messages = list(self._history_provider()) if callable(self._history_provider) else []
            review_prompt = (
                "[AutoReview Security Check]\n"
                f"Tool: {tool_name}\n"
                f"Arguments: {json.dumps(tool_input, ensure_ascii=False, default=str)[:2000]}\n"
                "Classify risk as `low`, `medium`, or `high` and decision as `allow` or `deny`. "
                "Respond with strict JSON: {\"risk\": \"low|medium|high\", \"decision\": \"allow|deny\", \"reason\": \"...\"}"
            )
            request = ApiMessageRequest(
                model=self._model,
                messages=[*prefix_messages, ConversationMessage.from_user_text(review_prompt)],
                system_prompt=self._system_prompt,
                max_tokens=256,
            )
            chunks: list[str] = []
            final_evt: ApiMessageCompleteEvent | None = None
            async for evt in self._api_client.stream_message(request):
                if isinstance(evt, ApiMessageCompleteEvent):
                    final_evt = evt
                elif hasattr(evt, "text"):
                    chunks.append(evt.text)
            text = (final_evt.message.text if final_evt and final_evt.message.text else "".join(chunks)).strip()
            outcome = _parse_review_json(text, block_medium_risk=self._block_medium_risk)
            if outcome is not None:
                return outcome

        return AutoReviewOutcome(risk="low", decision="allow", reason="passed auto-review")

    async def __call__(self, payload: dict[str, Any]) -> HookResult | None:
        """HookExecutor guard entry point for `HookEvent.PRE_TOOL_USE`."""
        tool_name = str(payload.get("tool_name") or "")
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        outcome = await self.evaluate_tool_call(tool_name, tool_input)
        if outcome.decision == "deny":
            return HookResult(
                hook_type="auto_review",
                success=False,
                blocked=True,
                reason=f"[{outcome.code or 'AUTO_REVIEW_DENIED'}] ({outcome.risk} risk) {outcome.reason}",
                metadata={"risk": outcome.risk, "decision": outcome.decision, "code": outcome.code or "AUTO_REVIEW_DENIED"},
            )
        return HookResult(
            hook_type="auto_review",
            success=True,
            blocked=False,
            metadata={"risk": outcome.risk, "decision": outcome.decision},
        )


def _parse_review_json(text: str, *, block_medium_risk: bool = False) -> AutoReviewOutcome | None:
    raw = (text or "").strip()
    first = raw.find("{")
    last = raw.rfind("}")
    if 0 <= first < last:
        raw = raw[first : last + 1]
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    risk_raw = str(data.get("risk") or "low").lower()
    risk: RiskLevel = risk_raw if risk_raw in {"low", "medium", "high"} else "low"  # type: ignore[assignment]
    dec_raw = str(data.get("decision") or ("deny" if risk == "high" else "allow")).lower()
    decision: ReviewDecision = "deny" if (risk == "high" or dec_raw == "deny" or (risk == "medium" and block_medium_risk)) else "allow"
    reason = str(data.get("reason") or "")
    return AutoReviewOutcome(
        risk=risk,
        decision=decision,
        reason=reason,
        code="AUTO_REVIEW_DENIED" if decision == "deny" else "",
    )
