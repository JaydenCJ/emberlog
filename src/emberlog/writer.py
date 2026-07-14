"""Serializer for the emberlog Markdown format.

Rendering is canonical: fixed key order, one metadata comment per entry,
computed ``expires=`` always refreshed, tags lowercase and deduplicated.
Canonical output makes git diffs minimal — editing one entry touches one
block — and makes save→load→save a fixed point (property-tested).

Writes are atomic: the new content lands in a same-directory temp file
that is fsynced and ``os.replace``d over the target, so a crash mid-save
can never leave a half-written log.
"""

from __future__ import annotations

import os
import tempfile

from .clock import format_date
from .model import ACTIVE, Entry
from .parser import MARKER, Document, RawBlock

__all__ = ["render_entry", "render_document", "write_document"]

_NEEDS_QUOTING = (" ", "\t", '"')


def _format_value(value: str) -> str:
    """Quote a metadata value when it holds whitespace or quotes."""
    if value == "" or any(ch in value for ch in _NEEDS_QUOTING):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _entry_pairs(entry: Entry) -> "list[tuple[str, str]]":
    """The metadata pairs for an entry, in canonical order."""
    pairs: "list[tuple[str, str]]" = [
        ("id", entry.id),
        ("added", format_date(entry.added)),
    ]
    if entry.ttl is not None:
        pairs.append(("ttl", str(entry.ttl)))
        expires = entry.expires
        if expires is not None:
            pairs.append(("expires", format_date(expires)))
    if entry.renewed is not None:
        pairs.append(("renewed", format_date(entry.renewed)))
    if entry.checked is not None:
        pairs.append(("checked", format_date(entry.checked)))
    if entry.source is not None:
        pairs.append(("source", str(entry.source)))
    if entry.confidence is not None:
        pairs.append(("confidence", entry.confidence))
    if entry.tags:
        pairs.append(("tags", ",".join(entry.tags)))
    if entry.status != ACTIVE:
        pairs.append(("status", entry.status))
    if entry.swept is not None:
        pairs.append(("swept", format_date(entry.swept)))
    if entry.reason is not None:
        pairs.append(("reason", entry.reason))
    # Unparseable known fields round-trip verbatim (the value someone
    # typed is preserved even though we could not interpret it) …
    written = {key for key, _ in pairs}
    for key, value in entry.invalid.items():
        if key not in written:
            pairs.append((key, value))
    # … and unknown keys survive in sorted order for stable diffs.
    for key in sorted(entry.extras):
        if key not in written:
            pairs.append((key, entry.extras[key]))
    return pairs


def render_entry(entry: Entry) -> str:
    """Render one entry as a ``##`` block (no trailing newline)."""
    attrs = " ".join(f"{key}={_format_value(value)}" for key, value in _entry_pairs(entry))
    lines = [f"## {entry.title}", f"<!-- ember {attrs} -->"]
    if entry.body:
        lines.append("")
        lines.append(entry.body)
    return "\n".join(lines)


def render_document(doc: Document) -> str:
    """Render a whole document in canonical form (trailing newline included)."""
    parts = [f"# {doc.title}", "", MARKER]
    if doc.preamble:
        parts.extend(["", doc.preamble])
    for node in doc.nodes:
        block = node.text if isinstance(node, RawBlock) else render_entry(node)
        parts.extend(["", block.rstrip("\n")])
    return "\n".join(parts) + "\n"


def write_document(path: str, doc: Document) -> None:
    """Atomically write *doc* to *path* (temp file + fsync + rename)."""
    content = render_document(doc)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    descriptor, temp_path = tempfile.mkstemp(
        prefix=".emberlog-", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:  # pragma: no cover - best-effort cleanup
            pass
        raise
