"""File-level operations: the :class:`LogFile` façade.

Everything the CLI does goes through here, and the module is equally
usable as a library (``from emberlog import LogFile``). A LogFile wraps
one parsed document plus its path; mutating operations edit the in-memory
document and only touch disk on :meth:`save`, so a failing operation never
leaves a half-modified file.

Retired and swept entries move to a sibling archive file
(``DECISIONS.md`` → ``DECISIONS.archive.md``) — decay means the *working*
file stays small, not that history is deleted.
"""

from __future__ import annotations

import datetime as _dt
import os
from collections import Counter
from dataclasses import dataclass, field

from . import clock
from .errors import (
    AmbiguousIdError,
    DuplicateIdError,
    EntryNotFoundError,
    FieldError,
)
from .ids import new_id
from .model import ACTIVE, CONFIDENCE_LEVELS, EXPIRED, RETIRED, Entry
from .parser import Document, parse_document
from .provenance import Source
from .ttl import Ttl
from .writer import write_document

__all__ = ["LogFile", "Stats", "default_archive_path", "DEFAULT_FILE"]

DEFAULT_FILE = "DECISIONS.md"


def default_archive_path(path: str) -> str:
    """``DECISIONS.md`` → ``DECISIONS.archive.md`` (kept beside the log)."""
    root, extension = os.path.splitext(path)
    return f"{root}.archive{extension or '.md'}"


@dataclass
class Stats:
    """Aggregate health of a log, as computed by :meth:`LogFile.stats`."""

    total: int = 0
    expired: int = 0
    expiring: int = 0  # within the horizon, not yet expired
    no_ttl: int = 0
    never: int = 0
    by_confidence: "Counter[str]" = field(default_factory=Counter)
    by_source_kind: "Counter[str]" = field(default_factory=Counter)
    oldest: "Entry | None" = None
    next_expiry: "Entry | None" = None


class LogFile:
    """One decision-log file, loaded into memory."""

    def __init__(self, path: str, doc: Document) -> None:
        self.path = path
        self.doc = doc

    # -- construction ----------------------------------------------------

    @classmethod
    def load(cls, path: str) -> "LogFile":
        """Load and parse an existing log file."""
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        return cls(path, parse_document(text, path=path))

    @classmethod
    def create(cls, path: str, title: str = "Decision Log") -> "LogFile":
        """Create a fresh, empty log file on disk. Refuses to overwrite."""
        if os.path.exists(path):
            raise FieldError(f"{path} already exists — refusing to overwrite")
        log = cls(path, Document(title=title))
        log.save()
        return log

    @classmethod
    def open_or_create(cls, path: str) -> "LogFile":
        if os.path.exists(path):
            return cls.load(path)
        return cls.create(path)

    def save(self) -> None:
        write_document(self.path, self.doc)

    # -- lookups ---------------------------------------------------------

    @property
    def entries(self) -> "list[Entry]":
        return self.doc.entries

    def active_entries(self) -> "list[Entry]":
        return [entry for entry in self.entries if entry.status == ACTIVE]

    def find(self, id_or_prefix: str) -> Entry:
        """Find an entry by full id or unambiguous prefix."""
        prefix = id_or_prefix.strip().lower()
        if not prefix:
            raise EntryNotFoundError(id_or_prefix)
        matches = [entry for entry in self.entries if entry.id.startswith(prefix)]
        if not matches:
            raise EntryNotFoundError(id_or_prefix)
        if len(matches) > 1:
            raise AmbiguousIdError(prefix, matches)
        return matches[0]

    # -- mutations -------------------------------------------------------

    def add(
        self,
        title: str,
        *,
        ttl: "Ttl | str | None" = None,
        source: "Source | str | None" = None,
        confidence: "str | None" = None,
        tags: "tuple[str, ...] | list[str]" = (),
        body: str = "",
        entry_id: "str | None" = None,
        today: "_dt.date | None" = None,
    ) -> Entry:
        """Append a new entry and return it (call :meth:`save` to persist)."""
        title = " ".join(title.split())
        if not title:
            raise FieldError("entry title must not be empty")
        if isinstance(ttl, str):
            ttl = Ttl.parse(ttl)
        if isinstance(source, str):
            source = Source.parse(source)
        if confidence is not None and confidence not in CONFIDENCE_LEVELS:
            levels = "|".join(CONFIDENCE_LEVELS)
            raise FieldError(f"unknown confidence {confidence!r} (want {levels})")
        added = today or clock.today()
        taken = self.doc.ids()
        if entry_id is None:
            entry_id = new_id(title, added, taken)
        elif entry_id in taken:
            raise DuplicateIdError(entry_id)
        entry = Entry(
            title=title,
            id=entry_id,
            added=added,
            ttl=ttl,
            source=source,
            confidence=confidence,
            tags=tuple(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip())),
            body=body.strip("\n"),
        )
        self.doc.nodes.append(entry)
        return entry

    def renew(
        self,
        id_or_prefix: str,
        *,
        ttl: "Ttl | str | None" = None,
        today: "_dt.date | None" = None,
    ) -> Entry:
        """Re-anchor an entry's TTL at today, optionally changing the TTL."""
        entry = self.find(id_or_prefix)
        if isinstance(ttl, str):
            ttl = Ttl.parse(ttl)
        if ttl is not None:
            entry.ttl = ttl
        if entry.ttl is None:
            raise FieldError(
                f"entry {entry.id} has no ttl — pass one to renew (e.g. --ttl 90d)"
            )
        entry.renewed = today or clock.today()
        return entry

    def verify(self, id_or_prefix: str, *, today: "_dt.date | None" = None) -> Entry:
        """Mark an entry re-checked: confidence becomes verified, dated today.

        Verification does not extend the TTL — knowing a claim is true today
        says nothing about how long it stays true. Renew for that.
        """
        entry = self.find(id_or_prefix)
        entry.confidence = "verified"
        entry.checked = today or clock.today()
        return entry

    def retire(
        self,
        id_or_prefix: str,
        *,
        reason: "str | None" = None,
        archive_path: "str | None" = None,
        today: "_dt.date | None" = None,
    ) -> Entry:
        """Withdraw an entry: move it to the archive with status=retired."""
        entry = self.find(id_or_prefix)
        entry.status = RETIRED
        entry.swept = today or clock.today()
        entry.reason = reason
        self._move_to_archive([entry], archive_path)
        return entry

    def sweep(
        self,
        *,
        archive_path: "str | None" = None,
        today: "_dt.date | None" = None,
        dry_run: bool = False,
    ) -> "list[Entry]":
        """Move every expired active entry to the archive.

        With ``dry_run`` the expired entries are returned but nothing moves
        and nothing is written — safe to call from a status hook. A sweep
        that finds nothing expired writes nothing either.
        """
        current = today or clock.today()
        expired = [
            entry for entry in self.active_entries() if entry.is_expired(current)
        ]
        if dry_run or not expired:
            return expired
        for entry in expired:
            entry.status = EXPIRED
            entry.swept = current
        self._move_to_archive(expired, archive_path)
        return expired

    def _move_to_archive(
        self, entries: "list[Entry]", archive_path: "str | None"
    ) -> None:
        """Detach *entries* from this doc and append them to the archive.

        Persists both files (archive first, so an interruption can duplicate
        an entry into the archive but never silently drop one).
        """
        archive_path = archive_path or default_archive_path(self.path)
        if os.path.exists(archive_path):
            archive = LogFile.load(archive_path)
        else:
            archive = LogFile(
                archive_path, Document(title=f"{self.doc.title} — Archive")
            )
        moving = {id(entry) for entry in entries}
        self.doc.nodes = [
            node for node in self.doc.nodes if id(node) not in moving
        ]
        archive.doc.nodes.extend(entries)
        archive.save()
        self.save()

    # -- reporting -------------------------------------------------------

    def stats(
        self, *, today: "_dt.date | None" = None, horizon_days: int = 14
    ) -> Stats:
        """Aggregate counts used by ``emberlog stats``."""
        current = today or clock.today()
        stats = Stats()
        for entry in self.active_entries():
            stats.total += 1
            if entry.is_expired(current):
                stats.expired += 1
            elif entry.expires is not None:
                if (entry.expires - current).days <= horizon_days:
                    stats.expiring += 1
                best = stats.next_expiry
                if best is None or (
                    best.expires is not None and entry.expires < best.expires
                ):
                    stats.next_expiry = entry
            if entry.ttl is None:
                stats.no_ttl += 1
            elif entry.ttl.is_never:
                stats.never += 1
            stats.by_confidence[entry.confidence or "unset"] += 1
            if entry.source is None:
                stats.by_source_kind["none"] += 1
            else:
                stats.by_source_kind[entry.source.kind or "untyped"] += 1
            if stats.oldest is None or entry.added < stats.oldest.added:
                stats.oldest = entry
        return stats
