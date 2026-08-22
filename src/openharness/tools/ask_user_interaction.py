from __future__ import annotations


class AskUserInteractionPaused(RuntimeError):
    """Raised when an interactive host pauses a tool for user input."""


class AskUserQuestionPaused(AskUserInteractionPaused):
    """Raised when an interactive host pauses the agent for a user answer."""


class AskUserFormPaused(AskUserInteractionPaused):
    """Raised when an interactive host pauses the agent for a user form."""
