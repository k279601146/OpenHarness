"""API error types for OpenHarness."""

from __future__ import annotations

from typing import Any


class OpenHarnessApiError(RuntimeError):
    """Base class for upstream API failures."""


class AuthenticationFailure(OpenHarnessApiError):
    """Raised when the upstream service rejects the provided credentials."""


class RateLimitFailure(OpenHarnessApiError):
    """Raised when the upstream service rejects the request due to rate limits."""


class RequestFailure(OpenHarnessApiError):
    """Raised for generic request or transport failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FallbackTriggeredError(OpenHarnessApiError):
    """Raised when consecutive errors trigger a model fallback."""

    def __init__(self, original_model: str, fallback_model: str, reason: str) -> None:
        super().__init__(f"Falling back from {original_model} to {fallback_model} due to: {reason}")
        self.original_model = original_model
        self.fallback_model = fallback_model
        self.reason = reason
