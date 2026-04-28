#!/bin/bash
# Uninstalls the morning-brief + evening-review launchd agents.

set -e

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
MORNING_PLIST="com.sushant.morning-brief.plist"
EVENING_PLIST="com.sushant.evening-review.plist"

launchctl unload "$LAUNCH_AGENTS/$MORNING_PLIST" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/$EVENING_PLIST" 2>/dev/null || true

rm -f "$LAUNCH_AGENTS/$MORNING_PLIST" "$LAUNCH_AGENTS/$EVENING_PLIST"

echo "✓ Schedule removed. Logs in ~/Library/Logs/ are preserved."
