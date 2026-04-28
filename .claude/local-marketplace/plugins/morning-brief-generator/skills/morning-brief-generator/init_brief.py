"""Bootstrap helper for morning-brief-generator.

Returns the deterministic context the brief needs before any analysis:
  • today's date (US/Eastern), day-of-week, minutes until 9:30 AM ET market open
  • brief sequence number (volume) — count of prior briefs in the directory + 1
  • path to the rolling recommendations.json (and its current contents)
  • carry-forward set: any recommendation in recommendations.json with
    status == "open" AND expiry_date >= today

The skill calls this FIRST. The returned JSON is the base context for the
v3.4 prompt — no need for the LLM to compute these values itself.

Usage:
    python3 init_brief.py [--date YYYY-MM-DD] [--output-dir PATH]

Output: single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path

import pytz

ET = pytz.timezone("US/Eastern")
MARKET_OPEN = dt_time(9, 30)

US_MARKET_HOLIDAYS = {
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Presidents' Day",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving",
    "2026-12-25": "Christmas",
    "2027-01-01": "New Year's Day",
    "2027-01-18": "Martin Luther King Jr. Day",
    "2027-02-15": "Presidents' Day",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observed)",
    "2027-07-05": "Independence Day (observed)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving",
    "2027-12-24": "Christmas (observed)",
}

US_MARKET_EARLY_CLOSE = {
    "2026-07-02": "Independence Day eve (1:00 PM ET close)",
    "2026-11-27": "Day after Thanksgiving (1:00 PM ET close)",
    "2026-12-24": "Christmas Eve (1:00 PM ET close)",
    "2027-07-02": "Independence Day eve (1:00 PM ET close)",
    "2027-11-26": "Day after Thanksgiving (1:00 PM ET close)",
    "2027-12-23": "Christmas Eve (1:00 PM ET close)",
}


def _classify_market_status(d: datetime) -> tuple[str, str | None]:
    iso = d.date().isoformat()
    weekday = d.weekday()  # 0 = Mon, 6 = Sun
    if weekday >= 5:
        return ("closed_weekend", d.strftime("%A"))
    if iso in US_MARKET_HOLIDAYS:
        return ("closed_holiday", US_MARKET_HOLIDAYS[iso])
    if iso in US_MARKET_EARLY_CLOSE:
        return ("early_close", US_MARKET_EARLY_CLOSE[iso])
    return ("open", None)


def _last_trading_day(d: datetime) -> str:
    cur = d.date() - timedelta(days=1)
    for _ in range(10):
        iso = cur.isoformat()
        weekday = cur.weekday()
        if weekday < 5 and iso not in US_MARKET_HOLIDAYS:
            return iso
        cur -= timedelta(days=1)
    return (d.date() - timedelta(days=1)).isoformat()


def _today_et(override: str | None) -> datetime:
    if override:
        d = datetime.strptime(override, "%Y-%m-%d")
        return ET.localize(datetime.combine(d.date(), datetime.now(ET).time()))
    return datetime.now(ET)


def _minutes_until_open(now_et: datetime) -> int:
    open_today = ET.localize(datetime.combine(now_et.date(), MARKET_OPEN))
    delta = (open_today - now_et).total_seconds() / 60
    return int(delta)


def _load_recommendations(path: Path) -> dict:
    if not path.exists():
        return {"recommendations": []}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"recommendations": []}


def _carry_forward(recs: list[dict], today_iso: str) -> list[dict]:
    out = []
    for r in recs:
        if r.get("status") != "open":
            continue
        exp = r.get("expiry_date")
        if not exp or exp < today_iso:
            continue
        out.append(r)
    return out


def _next_volume(output_dir: Path) -> int:
    return len(list(output_dir.glob("*.json"))) + 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Override today's date (YYYY-MM-DD) for backfill/testing.")
    p.add_argument(
        "--output-dir",
        default="morning-briefs",
        help="Directory holding daily briefs and recommendations.json. Resolved relative to CWD.",
    )
    args = p.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    now_et = _today_et(args.date)
    today_iso = now_et.date().isoformat()
    recs_path = output_dir / "recommendations.json"
    recs = _load_recommendations(recs_path)

    market_status, status_detail = _classify_market_status(now_et)
    last_td = _last_trading_day(now_et)

    if market_status == "open":
        quote_freshness_guidance = (
            "Live pre-market quotes required (timestamp ≤ 30 min). "
            "Treat this as a normal trading day."
        )
    elif market_status == "closed_weekend":
        quote_freshness_guidance = (
            f"MARKETS CLOSED ({status_detail}). No live pre-market exists. "
            f"Use {last_td} 4:00 PM ET closing prices for the quote table; "
            f"label every timestamp explicitly as '{last_td} close'. "
            "Render a banner in the HTML masthead: "
            "'MARKETS CLOSED — Quotes from prior session close. Brief is for planning only.' "
            "Skip live futures (futures markets closed Sat/Sun until 6:00 PM ET Sunday). "
            "Do NOT mark Step 6 #12 as failed for using closing prices on a non-trading day — "
            "the gate is against fabrication, not against the absence of a live pre-market."
        )
    elif market_status == "closed_holiday":
        quote_freshness_guidance = (
            f"MARKETS CLOSED — {status_detail}. No live pre-market exists. "
            f"Use {last_td} closing prices. Label timestamps as '{last_td} close'. "
            "Render holiday banner in the HTML masthead. "
            "Brief is forward-looking for the next trading session."
        )
    elif market_status == "early_close":
        quote_freshness_guidance = (
            f"EARLY CLOSE TODAY — {status_detail}. Live pre-market quotes still required, "
            "but management timelines should account for the 1:00 PM ET close. "
            "Add an early-close note to any same-day trade card."
        )
    else:
        quote_freshness_guidance = "Treat as normal trading day."

    payload = {
        "today_date": today_iso,
        "today_day_of_week": now_et.strftime("%A"),
        "today_long": now_et.strftime("%A, %B %-d %Y"),
        "current_time_et": now_et.strftime("%H:%M ET"),
        "minutes_until_market_open": _minutes_until_open(now_et) if market_status == "open" else None,
        "market_status": market_status,
        "market_status_detail": status_detail,
        "last_trading_day": last_td,
        "quote_freshness_guidance": quote_freshness_guidance,
        "brief_volume": _next_volume(output_dir),
        "output_dir": str(output_dir),
        "recommendations_path": str(recs_path),
        "carry_forward": _carry_forward(recs.get("recommendations", []), today_iso),
        "carry_forward_count": len(_carry_forward(recs.get("recommendations", []), today_iso)),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
