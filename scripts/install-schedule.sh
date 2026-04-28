#!/bin/bash
# Installs the morning-brief + evening-review launchd agents.
# Idempotent: safe to re-run after editing the plists.

set -e

PROJECT_DIR="/Users/sushant/python/options-skill-pack"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
LOGS_DIR="$HOME/Library/Logs"

MORNING_PLIST="com.sushant.morning-brief.plist"
EVENING_PLIST="com.sushant.evening-review.plist"

mkdir -p "$LAUNCH_AGENTS" "$LOGS_DIR"

chmod +x "$SCRIPTS_DIR/run-morning-brief.sh" "$SCRIPTS_DIR/run-evening-review.sh"

# Unload first if already loaded (so we pick up plist edits cleanly)
launchctl unload "$LAUNCH_AGENTS/$MORNING_PLIST" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/$EVENING_PLIST" 2>/dev/null || true

cp "$SCRIPTS_DIR/$MORNING_PLIST" "$LAUNCH_AGENTS/$MORNING_PLIST"
cp "$SCRIPTS_DIR/$EVENING_PLIST" "$LAUNCH_AGENTS/$EVENING_PLIST"

launchctl load "$LAUNCH_AGENTS/$MORNING_PLIST"
launchctl load "$LAUNCH_AGENTS/$EVENING_PLIST"

echo ""
echo "✓ Installed and loaded:"
echo "    $LAUNCH_AGENTS/$MORNING_PLIST   → fires Mon-Fri 7:00 AM local"
echo "    $LAUNCH_AGENTS/$EVENING_PLIST   → fires Mon-Fri 4:30 PM local"
echo ""
echo "Logs:"
echo "    $LOGS_DIR/morning-brief.log"
echo "    $LOGS_DIR/evening-review.log"
echo "    $LOGS_DIR/morning-brief.launchd.log    (launchd stdout/err)"
echo "    $LOGS_DIR/evening-review.launchd.log"
echo ""
echo "Useful commands:"
echo "    launchctl list | grep sushant            # see if loaded"
echo "    launchctl print gui/$(id -u)/com.sushant.morning-brief  # detailed status + next fire"
echo "    bash $SCRIPTS_DIR/run-morning-brief.sh   # trigger a manual test run"
echo "    bash $SCRIPTS_DIR/uninstall-schedule.sh  # remove the schedule"
echo ""
