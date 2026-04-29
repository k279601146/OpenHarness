"""Context variables for OpenHarness."""

from __future__ import annotations
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.api.viking_adapter import VikingAdapter

# Context variables for SaaS environment tracking
active_user_id: ContextVar[str | None] = ContextVar("active_user_id", default=None)
active_thread_id: ContextVar[str | None] = ContextVar("active_thread_id", default=None)
active_viking: ContextVar[VikingAdapter | None] = ContextVar("active_viking", default=None)
