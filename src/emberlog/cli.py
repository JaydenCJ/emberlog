"""The ``emberlog`` command-line interface.

Subcommands mirror the entry lifecycle: ``init`` → ``add`` → (``list`` /
``show`` / ``stats``) → ``lint`` → (``renew`` / ``verify``) → (``retire`` /
``sweep``). Exit codes are stable and script-friendly:

* ``0`` — success / clean lint
* ``1`` — lint found errors (or warnings under ``--strict``)
* ``2`` — usage, parse, or I/O problem

Machine consumers pass ``--json`` to ``list``, ``show``, ``lint``, and
``stats``; everything is emitted on stdout, diagnostics on stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, clock
from .clock import format_date, humanize_delta
from .errors import EmberlogError
from .lint import LintOptions, lint_document, summarize
from .model import CONFIDENCE_LEVELS, Entry
from .store import DEFAULT_FILE, LogFile, default_archive_path

__all__ = ["main", "build_parser"]


# -- helpers ---------------------------------------------------------------


def _entry_json(entry: Entry, today) -> "dict[str, object]":
    return {
        "id": entry.id,
        "title": entry.title,
        "status": entry.status,
        "added": format_date(entry.added),
        "ttl": str(entry.ttl) if entry.ttl else None,
        "expires": format_date(entry.expires) if entry.expires else None,
        "renewed": format_date(entry.renewed) if entry.renewed else None,
        "checked": format_date(entry.checked) if entry.checked else None,
        "source": str(entry.source) if entry.source else None,
        "confidence": entry.confidence,
        "tags": list(entry.tags),
        "age_days": entry.age_days(today),
        "expired": entry.is_expired(today),
        "body": entry.body,
    }


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _render_table(headers: "list[str]", rows: "list[list[str]]") -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = []
    for row in [headers] + rows:
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row)]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def _expiry_summary(entry: Entry, today) -> str:
    if entry.ttl is None:
        return "no ttl"
    if entry.ttl.is_never:
        return "never expires"
    expires = entry.expires
    assert expires is not None
    return f"expires {format_date(expires)}, {humanize_delta(expires, today)}"


# -- subcommand implementations ---------------------------------------------


def _cmd_init(args: argparse.Namespace) -> int:
    log = LogFile.create(args.file, title=args.title)
    print(f"initialized {log.path}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    today = clock.today()
    body = args.body or ""
    if body == "-":
        body = sys.stdin.read()
    log = LogFile.load(args.file)
    entry = log.add(
        args.title,
        ttl=args.ttl,
        source=args.source,
        confidence=args.confidence,
        tags=args.tags.split(",") if args.tags else (),
        body=body,
        entry_id=args.id,
        today=today,
    )
    log.save()
    print(f'added {entry.id} "{entry.title}" ({_expiry_summary(entry, today)})')
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    entries = log.entries
    if args.tag:
        wanted = args.tag.strip().lower()
        entries = [e for e in entries if wanted in e.tags]
    if args.kind:
        entries = [
            e
            for e in entries
            if e.source is not None and (e.source.kind or "untyped") == args.kind
        ]
    if args.expired:
        entries = [e for e in entries if e.is_expired(today)]
    if args.expiring is not None:
        entries = [
            e
            for e in entries
            if e.expires is not None
            and not e.is_expired(today)
            and (e.expires - today).days <= args.expiring
        ]
    if args.json:
        _print_json([_entry_json(entry, today) for entry in entries])
        return 0
    if not entries:
        print("no matching entries")
        return 0
    rows = [
        [
            entry.id,
            f"{entry.age_days(today)}d",
            entry.expiry_phrase(today),
            entry.confidence or "-",
            str(entry.source) if entry.source else "-",
            entry.title,
        ]
        for entry in entries
    ]
    print(_render_table(["ID", "AGE", "EXPIRES", "CONF", "SOURCE", "TITLE"], rows))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    entry = log.find(args.id)
    if args.json:
        _print_json(_entry_json(entry, today))
        return 0
    ttl_text = "-"
    if entry.ttl is not None:
        ttl_text = f"{entry.ttl} ({_expiry_summary(entry, today)})"
    pairs = [
        ("id", entry.id),
        ("title", entry.title),
        ("status", entry.status),
        ("added", f"{format_date(entry.added)} ({entry.age_days(today)}d ago)"),
        ("ttl", ttl_text),
        ("renewed", format_date(entry.renewed) if entry.renewed else "-"),
        ("checked", format_date(entry.checked) if entry.checked else "-"),
        ("source", str(entry.source) if entry.source else "-"),
        ("confidence", entry.confidence or "-"),
        ("tags", ", ".join(entry.tags) if entry.tags else "-"),
    ]
    for key, value in pairs:
        print(f"{key + ':':<12} {value}")
    if entry.body:
        print()
        print(entry.body)
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    options = LintOptions(
        horizon_days=args.horizon, decay_days=args.decay, strict=args.strict
    )
    findings = lint_document(log.doc, today, options)
    errors, warnings = summarize(findings)
    failed = errors > 0 or (args.strict and warnings > 0)
    if args.json:
        _print_json(
            {
                "path": log.path,
                "errors": errors,
                "warnings": warnings,
                "ok": not failed,
                "findings": [
                    {
                        "code": f.code,
                        "name": f.name,
                        "severity": f.severity,
                        "line": f.line,
                        "entry_id": f.entry_id,
                        "message": f.message,
                    }
                    for f in findings
                ],
            }
        )
        return 1 if failed else 0
    for finding in findings:
        print(finding.render(log.path))
    active = len(log.active_entries())
    if findings:
        noun = "finding" if len(findings) == 1 else "findings"
        e_noun = "error" if errors == 1 else "errors"
        w_noun = "warning" if warnings == 1 else "warnings"
        print(f"{log.path}: {len(findings)} {noun} ({errors} {e_noun}, {warnings} {w_noun})")
    else:
        noun = "entry" if active == 1 else "entries"
        print(f"{log.path}: clean — {active} active {noun}, nothing stale")
    return 1 if failed else 0


def _cmd_renew(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    entry = log.renew(args.id, ttl=args.ttl, today=today)
    log.save()
    print(f'renewed {entry.id} "{entry.title}" — now {_expiry_summary(entry, today)}')
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    entry = log.verify(args.id, today=today)
    log.save()
    print(
        f'verified {entry.id} "{entry.title}" '
        f"(confidence=verified, checked {format_date(today)})"
    )
    return 0


def _cmd_retire(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    entry = log.retire(
        args.id, reason=args.reason, archive_path=args.archive, today=today
    )
    archive = args.archive or default_archive_path(log.path)
    print(f'retired {entry.id} "{entry.title}" -> {archive}')
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    swept = log.sweep(archive_path=args.archive, today=today, dry_run=args.dry_run)
    if not swept:
        print("nothing to sweep — no expired entries")
        return 0
    for entry in swept:
        expires = entry.expires
        assert expires is not None
        print(
            f'  {entry.id} "{entry.title}" '
            f"(expired {format_date(expires)}, {humanize_delta(expires, today)})"
        )
    archive = args.archive or default_archive_path(log.path)
    noun = "entry" if len(swept) == 1 else "entries"
    if args.dry_run:
        print(f"would sweep {len(swept)} expired {noun} -> {archive}")
    else:
        print(f"swept {len(swept)} expired {noun} -> {archive}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    today = clock.today()
    log = LogFile.load(args.file)
    stats = log.stats(today=today, horizon_days=args.horizon)
    if args.json:
        _print_json(
            {
                "path": log.path,
                "total": stats.total,
                "expired": stats.expired,
                "expiring": stats.expiring,
                "no_ttl": stats.no_ttl,
                "never": stats.never,
                "by_confidence": dict(stats.by_confidence),
                "by_source_kind": dict(stats.by_source_kind),
                "oldest": stats.oldest.id if stats.oldest else None,
                "next_expiry": stats.next_expiry.id if stats.next_expiry else None,
            }
        )
        return 0

    def counts(counter) -> str:
        if not counter:
            return "-"
        return ", ".join(f"{count} {key}" for key, count in counter.most_common())

    print(f"{'active:':<14} {stats.total}")
    print(f"{'expired:':<14} {stats.expired}")
    print(f"{'expiring:':<14} {stats.expiring} (within {args.horizon}d)")
    print(f"{'no ttl:':<14} {stats.no_ttl}")
    print(f"{'never:':<14} {stats.never}")
    print(f"{'confidence:':<14} {counts(stats.by_confidence)}")
    print(f"{'sources:':<14} {counts(stats.by_source_kind)}")
    if stats.oldest is not None:
        print(
            f"{'oldest:':<14} {stats.oldest.id} "
            f'"{stats.oldest.title}" ({stats.oldest.age_days(today)}d)'
        )
    if stats.next_expiry is not None:
        expires = stats.next_expiry.expires
        assert expires is not None
        print(
            f"{'next expiry:':<14} {stats.next_expiry.id} "
            f'"{stats.next_expiry.title}" ({humanize_delta(expires, today)})'
        )
    return 0


# -- parser ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emberlog",
        description=(
            "Keep an agent decision-log file honest: TTL-stamped, "
            "provenance-tagged entries with expiry linting."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"emberlog {__version__}"
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-f",
        "--file",
        default=DEFAULT_FILE,
        help=f"decision-log file to operate on (default: {DEFAULT_FILE})",
    )

    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("init", parents=[common], help="create a new decision-log file")
    p.add_argument("--title", default="Decision Log", help="H1 title for the new file")
    p.set_defaults(func=_cmd_init)

    p = sub.add_parser("add", parents=[common], help="append a new entry")
    p.add_argument("title", help="one-line decision or fact")
    p.add_argument("--ttl", help="time-to-live: 45d, 8w, 6m, 1y, or never")
    p.add_argument("--source", help="provenance tag, e.g. agent:claude-code or human:alice")
    p.add_argument("--confidence", choices=CONFIDENCE_LEVELS, help="how sure the author is")
    p.add_argument("--tags", help="comma-separated tags")
    p.add_argument("--body", help="longer rationale ('-' reads stdin)")
    p.add_argument("--id", help="explicit 6-hex-char id (default: derived)")
    p.set_defaults(func=_cmd_add)

    p = sub.add_parser("list", parents=[common], help="list entries as a table")
    p.add_argument("--tag", help="only entries carrying this tag")
    p.add_argument("--kind", help="only entries whose source kind matches")
    p.add_argument("--expired", action="store_true", help="only expired entries")
    p.add_argument("--expiring", type=int, metavar="DAYS", help="only entries expiring within DAYS")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show", parents=[common], help="show one entry in full")
    p.add_argument("id", help="entry id (or unambiguous prefix)")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=_cmd_show)

    p = sub.add_parser("lint", parents=[common], help="check the log for rot (exit 1 on errors)")
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("--horizon", type=int, default=14, metavar="DAYS", help="expiring-soon window (default 14)")
    p.add_argument("--decay", type=int, default=45, metavar="DAYS", help="max age for guess/inferred entries (default 45)")
    p.add_argument("--json", action="store_true", help="emit JSON findings")
    p.set_defaults(func=_cmd_lint)

    p = sub.add_parser("renew", parents=[common], help="re-anchor an entry's TTL at today")
    p.add_argument("id", help="entry id (or unambiguous prefix)")
    p.add_argument("--ttl", help="also change the TTL (e.g. 90d)")
    p.set_defaults(func=_cmd_renew)

    p = sub.add_parser("verify", parents=[common], help="mark an entry re-checked today")
    p.add_argument("id", help="entry id (or unambiguous prefix)")
    p.set_defaults(func=_cmd_verify)

    p = sub.add_parser("retire", parents=[common], help="withdraw an entry to the archive")
    p.add_argument("id", help="entry id (or unambiguous prefix)")
    p.add_argument("--reason", help="why the entry no longer holds")
    p.add_argument("--archive", metavar="FILE", help="archive file (default: <log>.archive.md)")
    p.set_defaults(func=_cmd_retire)

    p = sub.add_parser("sweep", parents=[common], help="move expired entries to the archive")
    p.add_argument("--dry-run", action="store_true", help="report only; move nothing")
    p.add_argument("--archive", metavar="FILE", help="archive file (default: <log>.archive.md)")
    p.set_defaults(func=_cmd_sweep)

    p = sub.add_parser("stats", parents=[common], help="aggregate health of the log")
    p.add_argument("--horizon", type=int, default=14, metavar="DAYS", help="expiring-soon window (default 14)")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.set_defaults(func=_cmd_stats)

    return parser


def main(argv: "list[str] | None" = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except EmberlogError as exc:
        print(f"emberlog: error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(
            f"emberlog: error: {exc.filename or exc} not found — "
            "run 'emberlog init' first or pass -f",
            file=sys.stderr,
        )
        return 2
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. ``emberlog list | head``). Behave
        # like standard Unix tools: exit quietly instead of erroring. Point
        # stdout at /dev/null so the interpreter's final flush cannot raise
        # a second BrokenPipeError on the way out.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):  # pragma: no cover
            pass
        return 0
    except OSError as exc:  # pragma: no cover - unusual I/O failures
        print(f"emberlog: error: {exc}", file=sys.stderr)
        return 2
