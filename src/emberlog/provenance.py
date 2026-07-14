"""Provenance tags: who or what put a claim into the log.

A source is spelled ``kind:name`` — ``agent:claude-code``,
``human:alice``, ``doc:docs/adr-0007.md``, ``tool:profiler``,
``chat:2026-07-02-standup``. The kind is the load-bearing part: a future
session weighs "a human decided this" very differently from "an agent
inferred this at 2 a.m.". Bare names parse (kind ``None``) so hand-edited
files never break, but the linter flags them as untyped (W204).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ProvenanceError

__all__ = ["Source", "KINDS"]

# The closed set of provenance kinds. Deliberately small: every kind maps to
# a distinct trust posture when a later session re-reads the log.
KINDS = ("human", "agent", "doc", "tool", "chat")

_NAME_RE = re.compile(r"^[^\s]+$")


@dataclass(frozen=True)
class Source:
    """A provenance tag. ``kind`` is None for bare (untyped) sources."""

    kind: "str | None"
    name: str

    @classmethod
    def parse(cls, text: str) -> "Source":
        """Parse ``kind:name`` or a bare ``name``.

        Unknown kinds are preserved verbatim (they round-trip through the
        file) but reported by the linter — parsing must never lose data
        someone typed on purpose.
        """
        text = text.strip()
        if not text:
            raise ProvenanceError("source must not be empty")
        if not _NAME_RE.match(text):
            raise ProvenanceError(f"invalid source {text!r}: must not contain spaces")
        kind, sep, name = text.partition(":")
        if not sep:
            return cls(None, text)
        if not kind or not name:
            raise ProvenanceError(
                f"invalid source {text!r}: expected kind:name (e.g. agent:claude-code)"
            )
        return cls(kind, name)

    @property
    def is_typed(self) -> bool:
        """True when the kind is one of the known KINDS."""
        return self.kind in KINDS

    def __str__(self) -> str:
        if self.kind is None:
            return self.name
        return f"{self.kind}:{self.name}"
