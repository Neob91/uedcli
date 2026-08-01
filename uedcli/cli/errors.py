"""Command-facing error types raised by the CLI layer.

`CommandError` is the base for a clean exit-2 failure the central `dispatch()` guard prints to stderr
(never a traceback). It carries `.message` (== `str(self)`) so a handler that catches it can re-wrap
the text. `ProjectError` specializes it for "no uedcli project could be resolved".

A generic `except CommandError` catch now also catches `ProjectError` (its subclass). Where a catch
re-wraps the message, it must `except ProjectError: raise` first, so a missing-project failure keeps
its own message instead of being relabelled (e.g. the mover-index and actor-preview paths).
"""
from __future__ import annotations


class CommandError(Exception):
    """A clean, user-facing CLI failure (→ stderr + exit 2). Carries `.message`."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProjectError(CommandError):
    """No uedcli project could be resolved — user-facing (→ stderr + exit 2)."""


class LevelSelectionError(CommandError):
    """No level could be resolved / an invalid level was named — user-facing (→ stderr + exit 2)."""
