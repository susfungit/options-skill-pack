#!/bin/bash
# Wrapper invoked by launchd for the daily evening review.
# Logs everything to ~/Library/Logs/evening-review.log.

set -u

PROJECT_DIR="/Users/sushant/python/options-skill-pack"
CLAUDE_BIN="/Users/sushant/.local/bin/claude"
LOG_FILE="$HOME/Library/Logs/evening-review.log"

export PATH="/Users/sushant/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

cd "$PROJECT_DIR" || exit 1

{
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "Evening review run starting: $(date)"
  echo "═══════════════════════════════════════════════════════"
  "$CLAUDE_BIN" -p "run the evening review" 2>&1
  EXIT_CODE=$?
  echo ""
  echo "Evening review run finished: $(date) — exit $EXIT_CODE"
} >> "$LOG_FILE" 2>&1
