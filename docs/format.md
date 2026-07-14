# The emberlog file format (v1)

An emberlog file is ordinary Markdown that renders cleanly on any forge.
All machine state hides in HTML comments, so GitHub shows a normal
document while emberlog sees a database.

```markdown
# Decision Log

<!-- emberlog v1 -->

Optional preamble prose — preserved verbatim.

## Use SQLite for the job queue
<!-- ember id=6e28c8 added=2026-07-13 ttl=90d expires=2026-10-11 source=agent:claude-code confidence=observed tags=architecture,storage -->

Free-form Markdown body: the rationale, links, anything.
```

## Structure

| Part | Rule |
|---|---|
| H1 title | First `# ` heading before the marker; defaults to `Decision Log` |
| Marker | `<!-- emberlog v1 -->` — required; without it the file is not an emberlog file |
| Preamble | Prose between the marker and the first `## ` heading; round-trips verbatim |
| Entry | One `## ` heading + one `<!-- ember ... -->` comment + optional Markdown body |

The ember comment must be the first non-blank content after the heading
and may wrap across lines. Values containing spaces are double-quoted
with `\"` and `\\` escapes (e.g. `reason="superseded by ADR-7"`).

Known v1 limitation: any line starting with `## ` begins a new entry,
including inside a fenced code block in a body — indent such lines or
keep headings out of bodies.

## Entry fields

| Key | Format | Meaning |
|---|---|---|
| `id` | 6 lowercase hex chars | Stable handle; derived from title + added date |
| `added` | `YYYY-MM-DD` | When the claim entered the log |
| `ttl` | `45d` `8w` `6m` `1y` `never` | How long the claim stays trustworthy |
| `expires` | `YYYY-MM-DD` | **Derived**: `(renewed or added) + ttl`, kept for human readers |
| `renewed` | `YYYY-MM-DD` | Last re-anchoring of the TTL (`emberlog renew`) |
| `checked` | `YYYY-MM-DD` | Last re-verification (`emberlog verify`) |
| `source` | `kind:name` | Provenance; kinds: `human` `agent` `doc` `tool` `chat` |
| `confidence` | `guess` `inferred` `observed` `verified` | Author's stake in the claim |
| `tags` | `a,b,c` | Lowercased, deduplicated |
| `status` | `active` `expired` `retired` | Omitted when `active`; the others live in archives |
| `swept` | `YYYY-MM-DD` | When the entry left the working file |
| `reason` | quoted text | Why a retired entry no longer holds |

Unknown keys are preserved verbatim and re-emitted in sorted order —
hand additions and future emberlog versions round-trip losslessly.

## Semantics worth knowing

- **Expiry is computed, not stored.** `expires=` is a redundant courtesy
  for humans reading the raw file; every save recomputes it, and the
  linter flags hand-edited drift as `E105`.
- **An entry expires strictly *after* its expiry date.** On the day
  itself it warns (`W201`); the day after, it errors (`E101`).
- **Month arithmetic clamps.** `2026-01-31 + 1m` is `2026-02-28`,
  never a rollover into March.
- **Parsing is lossless.** A block emberlog cannot understand becomes a
  raw block: reported by the linter (`E102`), rewritten byte-identical,
  never deleted. Invalid field values (`ttl=fortnight`) keep the entry
  and re-emit the typo verbatim (`E104`).
- **The clock is injectable.** `EMBERLOG_TODAY=2026-08-01` pins every
  date computation — that is how the tests, examples, and smoke script
  stay deterministic.

## Archives

`sweep` and `retire` move entries to a sibling file
(`DECISIONS.md` → `DECISIONS.archive.md`), stamped with
`status=` and `swept=`. Archive files are themselves emberlog files:
`list`, `show`, and `lint` work on them, but archived entries are exempt
from freshness rules — they are history, not live knowledge.
