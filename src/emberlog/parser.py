"""Parser for the emberlog Markdown format.

The format is plain Markdown that renders cleanly on any forge:

.. code-block:: markdown

    # Decision Log

    <!-- emberlog v1 -->

    ## Use SQLite for the job queue
    <!-- ember id=3f9c21 added=2026-07-13 ttl=90d expires=2026-10-11
         source=agent:claude-code confidence=observed tags=storage -->

    Postgres was overkill for a single-writer queue.

Parsing is tolerant by design: a block the parser cannot fully understand
becomes a :class:`RawBlock` that round-trips verbatim (nothing a human
typed is ever lost), and every problem is collected as a
:class:`Diagnostic` instead of an exception. Only a missing file marker is
fatal — that means the target is not an emberlog file at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .clock import parse_date
from .errors import ClockError, NotEmberlogFileError, ProvenanceError, TtlError
from .ids import is_valid_id
from .model import ACTIVE, CONFIDENCE_LEVELS, STATUSES, Entry
from .provenance import Source
from .ttl import Ttl

__all__ = [
    "MARKER",
    "Diagnostic",
    "RawBlock",
    "Document",
    "parse_document",
    "parse_attrs",
]

MARKER = "<!-- emberlog v1 -->"

_MARKER_RE = re.compile(r"^\s*<!--\s*emberlog\s+v1\s*-->\s*$")
_H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_EMBER_RE = re.compile(r"^\s*<!--\s*ember\b(?P<attrs>.*?)-->\s*$", re.DOTALL)
_ATTR_RE = re.compile(r'([A-Za-z_][\w.-]*)=("(?:[^"\\]|\\.)*"|[^\s"]+)')

# Metadata keys the parser interprets. Anything else lands in ``extras``.
KNOWN_KEYS = (
    "id",
    "added",
    "ttl",
    "expires",
    "renewed",
    "checked",
    "source",
    "confidence",
    "tags",
    "status",
    "swept",
    "reason",
)


@dataclass(frozen=True)
class Diagnostic:
    """A parse problem tied to a line. ``code`` feeds the linter."""

    line: int
    code: str  # "malformed" | "bad-field" | "duplicate-id"
    message: str


@dataclass
class RawBlock:
    """A ``##`` block the parser could not interpret; preserved verbatim."""

    text: str
    line: int
    title: str


@dataclass
class Document:
    """A parsed log file: heading, preamble prose, and entry blocks."""

    title: str = "Decision Log"
    preamble: str = ""
    nodes: "list[Entry | RawBlock]" = field(default_factory=list)
    diagnostics: "list[Diagnostic]" = field(default_factory=list)

    @property
    def entries(self) -> "list[Entry]":
        return [node for node in self.nodes if isinstance(node, Entry)]

    def ids(self) -> "set[str]":
        return {entry.id for entry in self.entries}


def parse_attrs(text: str) -> "tuple[dict[str, str], bool]":
    """Tokenize ``key=value`` pairs; values may be double-quoted.

    Returns ``(attrs, clean)`` where *clean* is False when the text held
    anything besides well-formed pairs and whitespace.
    """
    attrs: "dict[str, str]" = {}
    clean = True
    for match in _ATTR_RE.finditer(text):
        key, value = match.group(1), match.group(2)
        if value.startswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if key in attrs:
            clean = False  # repeated key: keep the first, flag the block
        else:
            attrs[key] = value
    stripped = _ATTR_RE.sub("", text)
    if stripped.strip():
        clean = False
    return attrs, clean


def _split_tags(raw: str) -> "tuple[str, ...]":
    seen: "list[str]" = []
    for part in raw.split(","):
        tag = part.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return tuple(seen)


def _parse_entry(
    title: str,
    heading_line: int,
    block_text: str,
    attrs: "dict[str, str]",
    body: str,
    diagnostics: "list[Diagnostic]",
) -> "Entry | RawBlock":
    """Build an Entry from tokenized attrs, or fall back to a RawBlock."""

    def bad(message: str) -> RawBlock:
        diagnostics.append(Diagnostic(heading_line, "malformed", message))
        return RawBlock(block_text, heading_line, title)

    entry_id = attrs.pop("id", None)
    if entry_id is None:
        return bad(f'entry "{title}" has no id= field')
    if not is_valid_id(entry_id):
        return bad(f'entry "{title}" has invalid id {entry_id!r} (want 6 hex chars)')

    added_raw = attrs.pop("added", None)
    if added_raw is None:
        return bad(f'entry "{title}" has no added= date')
    try:
        added = parse_date(added_raw)
    except ClockError as exc:
        return bad(f'entry "{title}": {exc}')

    entry = Entry(title=title, id=entry_id, added=added, body=body, line=heading_line)

    def field_error(key: str, raw: str, message: str) -> None:
        entry.invalid[key] = raw
        diagnostics.append(
            Diagnostic(heading_line, "bad-field", f'entry "{title}": {message}')
        )

    for key in ("renewed", "checked", "swept", "expires"):
        raw = attrs.pop(key, None)
        if raw is None:
            continue
        try:
            value = parse_date(raw)
        except ClockError as exc:
            field_error(key, raw, str(exc))
            continue
        if key == "expires":
            entry.stored_expires = value
        else:
            setattr(entry, key, value)

    raw = attrs.pop("ttl", None)
    if raw is not None:
        try:
            entry.ttl = Ttl.parse(raw)
        except TtlError as exc:
            field_error("ttl", raw, str(exc))

    raw = attrs.pop("source", None)
    if raw is not None:
        try:
            entry.source = Source.parse(raw)
        except ProvenanceError as exc:
            field_error("source", raw, str(exc))

    raw = attrs.pop("confidence", None)
    if raw is not None:
        if raw in CONFIDENCE_LEVELS:
            entry.confidence = raw
        else:
            levels = "|".join(CONFIDENCE_LEVELS)
            field_error("confidence", raw, f"unknown confidence {raw!r} (want {levels})")

    raw = attrs.pop("status", None)
    if raw is not None:
        if raw in STATUSES:
            entry.status = raw
        else:
            field_error("status", raw, f"unknown status {raw!r}")
    else:
        entry.status = ACTIVE

    raw = attrs.pop("tags", None)
    if raw is not None:
        entry.tags = _split_tags(raw)

    entry.reason = attrs.pop("reason", None)
    entry.extras = dict(attrs)  # whatever is left is a future/unknown key
    return entry


def parse_document(text: str, path: str = "<memory>") -> Document:
    """Parse a whole log file. Raises only :class:`NotEmberlogFileError`."""
    lines = text.replace("\r\n", "\n").split("\n")

    marker_index = next(
        (i for i, line in enumerate(lines) if _MARKER_RE.match(line)), None
    )
    if marker_index is None:
        raise NotEmberlogFileError(path)

    doc = Document()
    for line in lines[:marker_index]:
        h1 = _H1_RE.match(line)
        if h1 and not line.startswith("##"):
            doc.title = h1.group("title")
            break

    # Everything between the marker and the first ## heading is preamble
    # prose; it round-trips verbatim (minus outer blank lines).
    first_entry = next(
        (
            i
            for i in range(marker_index + 1, len(lines))
            if _H2_RE.match(lines[i])
        ),
        len(lines),
    )
    doc.preamble = "\n".join(lines[marker_index + 1 : first_entry]).strip("\n")

    # Split the remainder into ## blocks.
    index = first_entry
    while index < len(lines):
        heading = _H2_RE.match(lines[index])
        assert heading is not None
        start = index
        index += 1
        while index < len(lines) and not _H2_RE.match(lines[index]):
            index += 1
        block_lines = lines[start:index]
        doc.nodes.append(
            _parse_block(heading.group("title"), start + 1, block_lines, doc.diagnostics)
        )

    _flag_duplicate_ids(doc)
    return doc


def _parse_block(
    title: str,
    heading_line: int,
    block_lines: "list[str]",
    diagnostics: "list[Diagnostic]",
) -> "Entry | RawBlock":
    block_text = "\n".join(block_lines).rstrip("\n")

    # Locate the ember comment: it may wrap across lines, so scan forward
    # from each candidate opener until the closing ``-->``.
    comment_start = comment_end = None
    for i in range(1, len(block_lines)):
        if block_lines[i].lstrip().startswith("<!-- ember"):
            for j in range(i, len(block_lines)):
                if "-->" in block_lines[j]:
                    comment_start, comment_end = i, j
                    break
            break
        if block_lines[i].strip():
            break  # first non-blank line is not the metadata comment

    if comment_start is None or comment_end is None:
        diagnostics.append(
            Diagnostic(
                heading_line,
                "malformed",
                f'entry "{title}" has no <!-- ember ... --> metadata comment',
            )
        )
        return RawBlock(block_text, heading_line, title)

    comment_text = "\n".join(block_lines[comment_start : comment_end + 1])
    match = _EMBER_RE.match(comment_text)
    if match is None:
        diagnostics.append(
            Diagnostic(heading_line, "malformed", f'entry "{title}": unreadable ember comment')
        )
        return RawBlock(block_text, heading_line, title)

    attrs, clean = parse_attrs(match.group("attrs"))
    if not clean:
        diagnostics.append(
            Diagnostic(
                heading_line,
                "malformed",
                f'entry "{title}": ember comment holds stray or repeated tokens',
            )
        )
        return RawBlock(block_text, heading_line, title)

    body = "\n".join(block_lines[comment_end + 1 :]).strip("\n")
    return _parse_entry(title, heading_line, block_text, attrs, body, diagnostics)


def _flag_duplicate_ids(doc: Document) -> None:
    seen: "dict[str, int]" = {}
    for entry in doc.entries:
        if entry.id in seen:
            doc.diagnostics.append(
                Diagnostic(
                    entry.line,
                    "duplicate-id",
                    f'entry "{entry.title}" reuses id {entry.id} '
                    f"(first used at line {seen[entry.id]})",
                )
            )
        else:
            seen[entry.id] = entry.line
