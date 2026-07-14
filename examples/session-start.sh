#!/usr/bin/env bash
# Session-start hook: refuse to trust a rotten decision log.
#
# Wire this as the first step of an agent session (e.g. a Claude Code
# SessionStart hook, a Makefile target, or your shell profile for a
# project). It lints the log, shows what is still fresh, and exits
# non-zero when the log contains expired knowledge — so the session
# starts by fixing the log instead of believing it.
#
# Usage: bash examples/session-start.sh [DECISIONS.md]
set -euo pipefail

LOG_FILE="${1:-DECISIONS.md}"

echo "== decision-log health: $LOG_FILE =="
if ! emberlog lint -f "$LOG_FILE"; then
  echo
  echo "The log contains expired knowledge. Renew, retire, or sweep before"
  echo "reading it into a session:  emberlog sweep -f $LOG_FILE"
  exit 1
fi

echo
echo "== fresh knowledge =="
emberlog list -f "$LOG_FILE"

echo
echo "== expiring within 14 days =="
emberlog list -f "$LOG_FILE" --expiring 14
