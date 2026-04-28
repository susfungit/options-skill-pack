#!/bin/bash
# Wrapper invoked by launchd for the daily morning brief.
# Logs everything to ~/Library/Logs/morning-brief.log.

set -u

PROJECT_DIR="/Users/sushant/python/options-skill-pack"
CLAUDE_BIN="/Users/sushant/.local/bin/claude"
LOG_FILE="$HOME/Library/Logs/morning-brief.log"

export PATH="/Users/sushant/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

cd "$PROJECT_DIR" || exit 1

{
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "Morning brief run starting: $(date)"
  echo "═══════════════════════════════════════════════════════"
  "$CLAUDE_BIN" -p "run the morning brief" 2>&1
  EXIT_CODE=$?
  echo ""
  echo "Morning brief run finished: $(date) — exit $EXIT_CODE"
} >> "$LOG_FILE" 2>&1
