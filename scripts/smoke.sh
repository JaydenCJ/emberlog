#!/usr/bin/env bash
# Smoke test for emberlog: drive the real CLI end-to-end through the whole
# entry lifecycle — init, add, lint, time-jump, sweep, renew, verify,
# retire, stats — asserting on real output at every step.
# Self-contained: pure stdlib, no network, idempotent (works from a clean
# tree). The clock is pinned via EMBERLOG_TODAY, so output never drifts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies: running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
EMBERLOG=("$PYTHON" -m emberlog)

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/emberlog-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. init + three adds under a pinned clock.
export EMBERLOG_TODAY=2026-07-13
"${EMBERLOG[@]}" init --title "Smoke Log" | grep -q "initialized DECISIONS.md" \
  || fail "init did not report the new file"
add_out="$("${EMBERLOG[@]}" add "Use SQLite for the job queue" \
  --ttl 90d --source agent:claude-code --confidence observed --tags storage \
  --body "Single-writer queue; WAL mode is plenty.")"
echo "$add_out" | grep -q "expires 2026-10-11, in 90d" || fail "add printed wrong expiry"
SQLITE_ID="$(echo "$add_out" | awk '{print $2}')"
"${EMBERLOG[@]}" add "Deploys happen from main only" \
  --ttl never --source human:alice --confidence verified >/dev/null
"${EMBERLOG[@]}" add "Cache is behind the flaky checkout test" \
  --ttl 14d --source agent:claude-code --confidence guess >/dev/null

# 2. list shows all three; lint passes (warnings only, no errors).
list_out="$("${EMBERLOG[@]}" list)"
echo "$list_out" | sed 's/^/[list] /'
[ "$(echo "$list_out" | wc -l)" -eq 4 ] || fail "list should show header + 3 rows"
echo "$list_out" | grep -q "never" || fail "list missing the never-TTL entry"
lint_out="$("${EMBERLOG[@]}" lint)" || fail "lint should exit 0 on a fresh log"
echo "$lint_out" | grep -q "W201 expiring-soon" || fail "14d entry should warn W201"
"${EMBERLOG[@]}" lint --strict >/dev/null && fail "--strict should fail on warnings"

# 3. Time-jump: the 14d guess expires; lint must turn red.
export EMBERLOG_TODAY=2026-09-01
set +e
lint_out="$("${EMBERLOG[@]}" lint)"
lint_rc=$?
set -e
echo "$lint_out" | sed 's/^/[lint] /'
[ "$lint_rc" -eq 1 ] || fail "lint on an expired log should exit 1, got $lint_rc"
echo "$lint_out" | grep -q 'E101 expired: "Cache is behind the flaky checkout test"' \
  || fail "lint did not flag the expired entry"

# 4. Dry-run sweep changes nothing; real sweep archives the expired entry.
before="$(cat DECISIONS.md)"
"${EMBERLOG[@]}" sweep --dry-run | grep -q "would sweep 1 expired entry" \
  || fail "dry-run sweep miscounted"
[ "$before" = "$(cat DECISIONS.md)" ] || fail "dry-run sweep modified the file"
"${EMBERLOG[@]}" sweep | grep -q "swept 1 expired entry -> DECISIONS.archive.md" \
  || fail "sweep did not report the move"
grep -q "status=expired swept=2026-09-01" DECISIONS.archive.md \
  || fail "archive missing status/swept stamps"
grep -q "Cache is behind" DECISIONS.md && fail "swept entry still in working file"
"${EMBERLOG[@]}" lint >/dev/null || fail "lint should be green after the sweep"

# 5. renew re-anchors, verify re-dates confidence — both by id prefix.
"${EMBERLOG[@]}" renew "${SQLITE_ID:0:3}" --ttl 30d \
  | grep -q "now expires 2026-10-01" || fail "renew computed wrong expiry"
grep -q "renewed=2026-09-01" DECISIONS.md || fail "renewed= not persisted"
"${EMBERLOG[@]}" verify "$SQLITE_ID" | grep -q "confidence=verified" \
  || fail "verify did not report"
grep -q "checked=2026-09-01" DECISIONS.md || fail "checked= not persisted"
show_out="$("${EMBERLOG[@]}" show "${SQLITE_ID:0:3}")"
echo "$show_out" | grep -q "source:      agent:claude-code" || fail "show missing source"

# 6. retire with a reason; stats and JSON agree on what is left.
"${EMBERLOG[@]}" retire "$SQLITE_ID" --reason "moved to a hosted queue" >/dev/null
grep -q 'reason="moved to a hosted queue"' DECISIONS.archive.md \
  || fail "retire reason not archived"
"${EMBERLOG[@]}" stats | sed 's/^/[stats] /'
"${EMBERLOG[@]}" stats | grep -q "active:        1" || fail "stats miscounted actives"
"${EMBERLOG[@]}" list --json | "$PYTHON" -c '
import json, sys
entries = json.load(sys.stdin)
assert len(entries) == 1, entries
assert entries[0]["title"] == "Deploys happen from main only", entries
assert entries[0]["expires"] is None, entries
' || fail "list --json shape wrong"

# 7. Refusals: a plain Markdown file is rejected, exit code 2.
printf '# Notes\n\nprose only\n' > NOTES.md
set +e
"${EMBERLOG[@]}" lint -f NOTES.md 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "non-emberlog file should exit 2, got $rc"

# 8. --version agrees with the package.
version_out="$("${EMBERLOG[@]}" --version)"
pkg_version="$("$PYTHON" -c 'import emberlog; print(emberlog.__version__)')"
[ "$version_out" = "emberlog $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
