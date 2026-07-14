"""emberlog — keep an agent decision-log file honest.

A decision log is the memory a project hands its next session: choices
made, constraints discovered, dead ends already explored. Those files rot.
emberlog stamps every entry with a TTL and a provenance tag, lints the
file for expired or decaying knowledge, and sweeps dead entries into an
archive — all in one plain, git-friendly Markdown file.

Library use mirrors the CLI::

    from emberlog import LogFile, lint_document
    from emberlog.clock import today

    log = LogFile.load("DECISIONS.md")
    log.add("Use SQLite for the job queue", ttl="90d",
            source="agent:claude-code", confidence="observed")
    log.save()
    findings = lint_document(log.doc, today())
"""

from .clock import today
from .errors import (
    AmbiguousIdError,
    ClockError,
    DuplicateIdError,
    EmberlogError,
    EntryNotFoundError,
    FieldError,
    NotEmberlogFileError,
    ProvenanceError,
    TtlError,
)
from .lint import Finding, LintOptions, RULES, lint_document, summarize
from .model import CONFIDENCE_LEVELS, Entry
from .parser import Diagnostic, Document, RawBlock, parse_document
from .provenance import KINDS, Source
from .store import DEFAULT_FILE, LogFile, Stats, default_archive_path
from .ttl import Ttl
from .writer import render_document, render_entry, write_document

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # model
    "Entry",
    "Ttl",
    "Source",
    "CONFIDENCE_LEVELS",
    "KINDS",
    # files
    "LogFile",
    "Stats",
    "DEFAULT_FILE",
    "default_archive_path",
    "Document",
    "RawBlock",
    "Diagnostic",
    "parse_document",
    "render_document",
    "render_entry",
    "write_document",
    # lint
    "Finding",
    "LintOptions",
    "RULES",
    "lint_document",
    "summarize",
    # clock
    "today",
    # errors
    "EmberlogError",
    "ClockError",
    "TtlError",
    "ProvenanceError",
    "NotEmberlogFileError",
    "EntryNotFoundError",
    "AmbiguousIdError",
    "DuplicateIdError",
    "FieldError",
]
