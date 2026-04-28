"""Bootstrap helper for evening-brief-reviewer.

Loads the morning brief for a given date and returns the positions to
score. Returns:
  • today's date (US/Eastern), market_status (matters for partial-review flagging)
  • path to morning brief JSON (errors if it doesn't exist)
  • the morning brief's recommendations array (today's NEW trades to score)
  • the morning brief's carry_forward_reviewed array (positions reviewed earlier today)
  • all OPEN positions in recommendations.json (full open-book — gets a fresh
    EOD price + status check, not just today's new ones)
  • the prior 14 days of prompt_change_proposals.json entries (so the LLM
    can see how often each proposal has recurred — drives the 3+ threshold rule)

Usage:
    python3 load_morning.py [--date YYYY-MM-DD] [--output-dir morning-briefs]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz

ET = pytz.timezone("US/Eastern")


def _today_et(override: str | None) -> datetime:
    if override:
        d = datetime.strptime(override, "%Y-%m-%d")
        return ET.localize(datetime.combine(d.date(), datetime.now(ET).time()))
    return datetime.now(ET)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _open_positions(recs: list[dict], today_iso: str) -> list[dict]:
    out = []
    for r in recs:
        if r.get("status") != "open":
            continue
        exp = r.get("expiry_date")
        if not exp or exp < today_iso:
            continue
        out.append(r)
    return out


def _recent_proposals(proposals: list[dict], today_iso: str, days: int = 14) -> list[dict]:
    cutoff = (datetime.fromisoformat(today_iso) - timedelta(days=days)).date().isoformat()
    return [p for p in proposals if p.get("date", "") >= cutoff]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Override date (YYYY-MM-DD).")
    p.add_argument("--output-dir", default="morning-briefs")
    args = p.parse_args()

    out_dir = Path(args.output_dir).resolve()
    if not out_dir.exists():
        sys.stderr.write(f"output dir {out_dir} does not exist — run morning-brief-generator first\n")
        return 2

    now_et = _today_et(args.date)
    today_iso = now_et.date().isoformat()

    morning_path = out_dir / f"{today_iso}.json"
    if not morning_path.exists():
        sys.stderr.write(
            f"morning brief for {today_iso} not found at {morning_path}\n"
            f"run morning-brief-generator first, or pass --date for a date that has one\n"
        )
        return 3

    morning = json.loads(morning_path.read_text())
    recs_index = _load_json(out_dir / "recommendations.json", {"recommendations": []})
    proposals_index = _load_json(
        out_dir / "prompt_change_proposals.json", {"proposals": []}
    )

    open_positions = _open_positions(recs_index.get("recommendations", []), today_iso)
    recent_proposals = _recent_proposals(proposals_index.get("proposals", []), today_iso)

    payload = {
        "today_date": today_iso,
        "today_long": now_et.strftime("%A, %B %-d %Y"),
        "current_time_et": now_et.strftime("%H:%M ET"),
        "market_status": morning.get("market_status", "unknown"),
        "market_status_detail": morning.get("market_status_detail"),
        "morning_brief_path": str(morning_path),
        "morning_brief_volume": morning.get("brief_volume"),
        "evening_output_dir": str(out_dir),
        "evening_brief_path": str(out_dir / f"{today_iso}-evening.json"),
        "evening_html_path": str(out_dir / f"{today_iso}-evening.html"),
        "recommendations_path": str(out_dir / "recommendations.json"),
        "proposals_path": str(out_dir / "prompt_change_proposals.json"),
        "morning_recommendations_today": morning.get("recommendations", []),
        "morning_carry_forward_reviewed": morning.get("carry_forward_reviewed", []),
        "morning_quote_table": morning.get("quote_table", []),
        "morning_implied_move_watch": morning.get("implied_move_watch", []),
        "morning_meta_signal": morning.get("meta_signal"),
        "open_positions_full_book": open_positions,
        "open_positions_count": len(open_positions),
        "recent_prompt_proposals": recent_proposals,
        "recent_proposals_count": len(recent_proposals),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
