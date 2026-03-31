#!/usr/bin/env python3
"""
Notification sender for the options portfolio monitor.

Reads monitor_config.json internally so credentials never leave this process.
Called by claude -p after position checks are complete.

Usage:
  python3 notify.py --mode alert   --results '[{"label":"NVDA","zone":"SAFE",...}]'
  python3 notify.py --mode summary --results '[...]'
"""

import argparse
import json
import platform
import smtplib
import subprocess
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
CONFIG_FILE = PROJECT_ROOT / "monitor_config.json"
LOG_FILE = PROJECT_ROOT / "monitor.log"

ZONE_EMOJI = {
    "SAFE": "🟢", "WATCH": "🟡", "WARNING": "🟠",
    "DANGER": "🔴", "ACT NOW": "🚨",
}

ALERT_ZONES = {"WATCH", "WARNING", "DANGER", "ACT NOW"}


def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE} not found. Run: bash setup_monitor.sh")
        sys.exit(1)
    return json.loads(CONFIG_FILE.read_text())


def _applescript_escape(s: str) -> str:
    """Escape a string for safe interpolation into AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send_macos(positions):
    if platform.system() != "Darwin":
        return 0
    sent = 0
    for p in positions:
        emoji = ZONE_EMOJI.get(p["zone"], "❓")
        title = _applescript_escape(f"Options Monitor — {p.get('label', p.get('ticker', ''))}")
        msg = _applescript_escape(
            f"{emoji} {p['zone']}  |  buffer {p.get('buffer_pct', 0):.1f}%  |  P&L ${p.get('pnl_per_contract', 0):.0f}"
        )
        script = f'display notification "{msg}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
        sent += 1
    return sent


def send_email(positions, cfg):
    rows = ""
    for p in positions:
        emoji = ZONE_EMOJI.get(p["zone"], "")
        rows += (
            f"<tr><td>{p.get('label', p.get('ticker', ''))}</td>"
            f"<td>{emoji} {p['zone']}</td>"
            f"<td>${p.get('stock_price', 0):.2f}</td>"
            f"<td>{p.get('buffer_pct', 0):.1f}%</td>"
            f"<td>${p.get('pnl_per_contract', 0):.0f}</td>"
            f"<td>{p.get('dte', 0)}</td>"
            f"<td>${p.get('cost_to_close', 0):.2f}</td></tr>\n"
        )

    html = f"""<html><body>
<h3>Options Portfolio Monitor</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr style="background:#f0f0f0;">
  <th>Position</th><th>Zone</th><th>Stock</th><th>Buffer</th>
  <th>P&amp;L/contract</th><th>DTE</th><th>Close Cost</th>
</tr>
{rows}
</table>
<p style="color:#888;font-size:12px;">Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Options Monitor — {len(positions)} position(s)"
    msg["From"] = cfg["username"]
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
        server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["username"], cfg["to"], msg.as_string())
    return 1


def send_pushover(positions, cfg):
    try:
        import requests
    except ImportError:
        print("WARNING: requests not installed — skipping Pushover. pip install requests")
        return 0

    sent = 0
    for p in positions:
        emoji = ZONE_EMOJI.get(p["zone"], "")
        title = f"{p.get('label', p.get('ticker', ''))} — {emoji} {p['zone']}"
        msg = (
            f"Stock: ${p.get('stock_price', 0):.2f}  Buffer: {p.get('buffer_pct', 0):.1f}%\n"
            f"P&L: ${p.get('pnl_per_contract', 0):.0f}  DTE: {p.get('dte', 0)}\n"
            f"Close cost: ${p.get('cost_to_close', 0):.2f}"
        )
        resp = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": cfg["api_token"],
                "user": cfg["user_key"],
                "title": title,
                "message": msg,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            sent += 1
        else:
            print(f"WARNING: Pushover failed for {p.get('label', '')}: {resp.status_code}")
    return sent


def append_log(results, mode):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "results": results,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Send options monitor notifications")
    parser.add_argument("--mode", choices=["alert", "summary"], default="alert")
    parser.add_argument("--results", required=True, help="JSON array of position results")
    args = parser.parse_args()

    results = json.loads(args.results)
    config = load_config()
    notif = config.get("notifications", {})

    # Filter based on mode
    if args.mode == "alert":
        positions = [r for r in results if r.get("zone") in ALERT_ZONES]
    else:
        positions = results

    # Track what was sent
    sent = {"macos": 0, "email": 0, "pushover": 0}

    if not positions and args.mode == "alert":
        # All safe — quiet macOS-only notification
        if notif.get("macos", {}).get("enabled") and platform.system() == "Darwin":
            subprocess.run([
                "osascript", "-e",
                'display notification "All positions SAFE" with title "Options Monitor"'
            ], capture_output=True)
            sent["macos"] = 1
        print(f"All {len(results)} position(s) SAFE — no alerts sent.")
    else:
        if notif.get("macos", {}).get("enabled"):
            sent["macos"] = send_macos(positions)

        if notif.get("email", {}).get("enabled"):
            try:
                sent["email"] = send_email(positions, notif["email"])
            except Exception as e:
                print(f"ERROR: Email failed — {e}")

        if notif.get("pushover", {}).get("enabled"):
            try:
                sent["pushover"] = send_pushover(positions, notif["pushover"])
            except Exception as e:
                print(f"ERROR: Pushover failed — {e}")

    # Log all results (not just filtered)
    append_log(results, args.mode)

    # Summary
    total = sum(sent.values())
    zones = {}
    for r in results:
        z = r.get("zone", "UNKNOWN")
        zones[z] = zones.get(z, 0) + 1
    zone_str = ", ".join(f"{v} {k}" for k, v in sorted(zones.items()))
    print(f"Checked {len(results)} position(s): {zone_str}")
    print(f"Notifications sent: {total} ({', '.join(f'{k}:{v}' for k, v in sent.items() if v > 0) or 'none'})")


if __name__ == "__main__":
    main()
