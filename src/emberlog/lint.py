"""Expiry and hygiene linting for a decision log.

The linter is the reason emberlog exists: a notes file only stays
trustworthy if something *fails loudly* when its contents rot. Errors
(``E1xx``) mean the log is lying to its next reader — expired claims,
unreadable blocks, drifted dates. Warnings (``W2xx``) mean it is about to:
entries expiring soon, missing TTLs, anonymous or decaying claims.

Run it at session start (agents) or in CI (humans): exit 1 on errors,
and on warnings too with ``--strict``.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from .clock import format_date, humanize_delta
from .model import ACTIVE, Entry
from .parser import Diagnostic, Document

__all__ = ["Finding", "LintOptions", "RULES", "lint_document", "summarize"]

ERROR = "error"
WARNING = "warning"

# code -> (name, severity, one-line description). This table is the single
# source of truth; docs/rules.md and the README table mirror it.
RULES: "dict[str, tuple[str, str, str]]" = {
    "E101": ("expired", ERROR, "entry is past its computed expiry date"),
    "E102": ("malformed-entry", ERROR, "block could not be parsed as an entry"),
    "E103": ("duplicate-id", ERROR, "two entries share the same id"),
    "E104": ("bad-field", ERROR, "a metadata field value is invalid"),
    "E105": ("expires-drift", ERROR, "stored expires= disagrees with added/renewed + ttl"),
    "W201": ("expiring-soon", WARNING, "entry expires within the horizon (default 14d)"),
    "W202": ("no-ttl", WARNING, "entry has no ttl= and will never be revisited"),
    "W203": ("no-provenance", WARNING, "entry has no source= tag"),
    "W204": ("untyped-provenance", WARNING, "source has no known kind: prefix"),
    "W205": ("stale-unverified", WARNING, "low-confidence entry untouched past the decay age"),
}

_DIAGNOSTIC_CODES = {"malformed": "E102", "duplicate-id": "E103", "bad-field": "E104"}


@dataclass(frozen=True)
class LintOptions:
    """Tunable thresholds. Defaults are deliberately opinionated."""

    horizon_days: int = 14  # W201: how far ahead "expiring soon" looks
    decay_days: int = 45  # W205: max age for a guess/inferred entry
    strict: bool = False  # treat warnings as failures (CLI exit code)


@dataclass(frozen=True)
class Finding:
    """One lint result, printable as ``FILE:LINE: CODE name: message``."""

    code: str
    line: int
    message: str
    entry_id: "str | None" = None

    @property
    def name(self) -> str:
        return RULES[self.code][0]

    @property
    def severity(self) -> str:
        return RULES[self.code][1]

    def render(self, path: str) -> str:
        return f"{path}:{self.line}: {self.code} {self.name}: {self.message}"


def lint_document(
    doc: Document,
    today: _dt.date,
    options: "LintOptions | None" = None,
) -> "list[Finding]":
    """Lint a parsed document; findings come back sorted by line then code."""
    options = options or LintOptions()
    findings: "list[Finding]" = []
    for diagnostic in doc.diagnostics:
        findings.append(_from_diagnostic(diagnostic))
    for entry in doc.entries:
        findings.extend(_lint_entry(entry, today, options))
    findings.sort(key=lambda f: (f.line, f.code))
    return findings


def _from_diagnostic(diagnostic: Diagnostic) -> Finding:
    return Finding(
        code=_DIAGNOSTIC_CODES[diagnostic.code],
        line=diagnostic.line,
        message=diagnostic.message,
    )


def _lint_entry(entry: Entry, today: _dt.date, options: LintOptions) -> "list[Finding]":
    findings: "list[Finding]" = []

    def add(code: str, message: str) -> None:
        findings.append(Finding(code, entry.line, message, entry_id=entry.id))

    quoted = f'"{entry.title}"'

    # E105 applies to every status: a wrong date is wrong even in the
    # archive. All other rules only judge live knowledge.
    if entry.stored_expires is not None and "ttl" not in entry.invalid:
        computed = entry.expires
        if computed is None:
            add(
                "E105",
                f"{quoted} stores expires={format_date(entry.stored_expires)} "
                "but has no finite ttl — remove one or the other",
            )
        elif computed != entry.stored_expires:
            add(
                "E105",
                f"{quoted} stores expires={format_date(entry.stored_expires)} but "
                f"{format_date(entry.anchor)} + {entry.ttl} gives {format_date(computed)} "
                "— any emberlog write rewrites the correct value",
            )

    if entry.status != ACTIVE:
        return findings

    expires = entry.expires
    if entry.is_expired(today):
        assert expires is not None
        add(
            "E101",
            f"{quoted} expired {format_date(expires)} ({humanize_delta(expires, today)}) "
            "— renew it, retire it, or run 'emberlog sweep'",
        )
    elif expires is not None and (expires - today).days <= options.horizon_days:
        add(
            "W201",
            f"{quoted} expires {format_date(expires)} ({humanize_delta(expires, today)})",
        )

    if entry.ttl is None and "ttl" not in entry.invalid:
        add("W202", f"{quoted} has no ttl= — give it one, or an explicit ttl=never")

    if entry.source is None and "source" not in entry.invalid:
        add("W203", f"{quoted} has no source= — future readers cannot weigh it")
    elif entry.source is not None and not entry.source.is_typed:
        if entry.source.kind is None:
            detail = f"source={entry.source} has no kind: prefix"
        else:
            detail = f"source={entry.source} uses unknown kind {entry.source.kind!r}"
        add("W204", f"{quoted}: {detail} (want human|agent|doc|tool|chat)")

    if entry.confidence in ("guess", "inferred"):
        idle = (today - entry.last_touch).days
        if idle > options.decay_days:
            add(
                "W205",
                f"{quoted} is still confidence={entry.confidence} after {idle}d "
                "— verify it or retire it",
            )

    return findings


def summarize(findings: "list[Finding]") -> "tuple[int, int]":
    """Return ``(error_count, warning_count)``."""
    errors = sum(1 for f in findings if f.severity == ERROR)
    return errors, len(findings) - errors
