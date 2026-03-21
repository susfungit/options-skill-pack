#!/bin/bash
# First-time setup for the options portfolio monitor.
# Run once after cloning: bash setup_monitor.sh

set -e

echo ""
echo "=== Options Portfolio Monitor — First-Time Setup ==="
echo ""

# ── portfolio.json ────────────────────────────────────────────────────────────

if [ -f portfolio.json ]; then
  echo "✓ portfolio.json already exists — skipping"
else
  cp portfolio.example.json portfolio.json
  echo "✓ Created portfolio.json from template"
  echo ""
  echo "  Edit portfolio.json to add your open bull put spread positions."
  echo "  Each entry needs: ticker, short_strike, long_strike, net_credit, expiry"
  echo ""
fi

# ── monitor_config.json ───────────────────────────────────────────────────────

if [ -f monitor_config.json ]; then
  echo "✓ monitor_config.json already exists — skipping"
else
  cp monitor_config.example.json monitor_config.json
  echo "✓ Created monitor_config.json from template"
  echo ""
  echo "  Configure your notification channels in monitor_config.json:"
  echo ""
  echo "  macOS desktop  → already enabled, no setup needed"
  echo "  Email          → set enabled=true, fill in smtp credentials"
  echo "                   Tip: use a Gmail App Password (not your main password)"
  echo "                   Google Account → Security → App Passwords"
  echo "  Pushover       → set enabled=true, sign up at pushover.net (\$5 one-time)"
  echo "                   for push notifications on iPhone/Android"
  echo "  SMS via email  → use email channel, set 'to' to your carrier gateway"
  echo "                   e.g. 5551234567@vtext.com (Verizon)"
  echo "                        5551234567@txt.att.net (AT&T)"
  echo "                        5551234567@tmomail.net (T-Mobile)"
  echo ""
fi

# ── summary ───────────────────────────────────────────────────────────────────

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit portfolio.json     — add your positions"
echo "  2. Edit monitor_config.json — configure notification channels"
echo "  3. Run the monitor:"
echo ""
echo "     Alert mode (WATCH or worse only):"
echo "     claude -p \"Read portfolio.json and check each bull put spread using the bull-put-spread-monitor skill. Mode: alert — only notify WATCH or worse. Send notifications per monitor_config.json. Append results to monitor.log.\" --allowedTools Bash,Read,Write"
echo ""
echo "     Summary mode (all positions — end of day):"
echo "     claude -p \"Read portfolio.json and check each bull put spread using the bull-put-spread-monitor skill. Mode: summary — notify all positions. Send notifications per monitor_config.json. Append results to monitor.log.\" --allowedTools Bash,Read,Write"
echo ""
echo "  See README.md for scheduling instructions (macOS launchd / Windows Task Scheduler)."
echo ""
