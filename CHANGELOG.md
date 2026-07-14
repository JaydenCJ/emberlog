# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Markdown decision-log format v1: entries as `##` blocks with metadata in
  `<!-- ember ... -->` HTML comments, so files render cleanly on any forge.
  Specified in `docs/format.md`.
- Tolerant, lossless parser: unreadable blocks are preserved verbatim as raw
  blocks, invalid field values re-emit byte-for-byte, unknown keys round-trip
  in sorted order, and every problem becomes a lint finding instead of a
  crash.
- TTL engine: `45d`/`8w`/`6m`/`1y`/`never`, calendar-aware month arithmetic
  with end-of-month clamping, expiry computed from the last renewal, and the
  stored `expires=` healed on every save.
- Provenance tags (`human:` / `agent:` / `doc:` / `tool:` / `chat:`) and a
  four-step confidence ladder (`guess`, `inferred`, `observed`, `verified`).
- Expiry linter with 10 rules — E101 expired, E102 malformed-entry, E103
  duplicate-id, E104 bad-field, E105 expires-drift, W201 expiring-soon, W202
  no-ttl, W203 no-provenance, W204 untyped-provenance, W205 stale-unverified —
  with `--strict`, `--horizon`, `--decay`, `--json`, and stable exit codes
  (0 clean / 1 findings / 2 usage).
- Lifecycle commands: `init`, `add`, `list` (filters + JSON), `show`, `stats`,
  `renew`, `verify`, `retire --reason`, and non-destructive `sweep
  [--dry-run]` into a sibling `*.archive.md` file.
- Deterministic behavior end to end: content-derived 6-hex ids, the
  `EMBERLOG_TODAY` clock override, atomic writes, zero runtime dependencies.
- Runnable example log with every kind of rot (`examples/`), a session-start
  hook script, and a worked cleanup walkthrough.
- 92 deterministic pytest tests (including a verbatim README-quickstart
  reproduction) and `scripts/smoke.sh` driving the full CLI lifecycle.

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/emberlog/releases/tag/v0.1.0
