"""Bulk EOD price fetcher for the evening-brief-reviewer skill.

Fetches end-of-day closes for a list of tickers via yfinance. Returns a
single JSON object with `quotes[]` and `failed[]` — never aborts on a per-
ticker error so the caller can fall back to WebSearch for just the missing
ones (preserving the v3.4 anti-fabrication discipline of one canonical
source + a documented fallback).

Usage:
    python3 fetch_eod_prices.py --tickers SPY,NVDA,AMD,...

When the script itself errors (e.g. no network in a sandboxed cloud
environment), the SKILL.md falls back to the legacy WebSearch flow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytz

# Make the _shared/options_lib helpers importable (they're not on path).
_PLUGINS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PLUGINS))

import yfinance as yf  # noqa: E402  (after sys.path tweak)

ET = pytz.timezone("US/Eastern")
TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _fetch_one(sym: str) -> dict:
    """Fetch EOD close for a single ticker. Returns either a quote dict
    or raises ValueError with a short reason. Never calls sys.exit."""
    tk = yf.Ticker(sym)
    hist = tk.history(period="2d")
    if hist.empty:
        raise ValueError("no price data")
    price = round(float(hist["Close"].iloc[-1]), 2)
    bar_ts = hist.index[-1]
    if len(hist) >= 2:
        prev_close = round(float(hist["Close"].iloc[-2]), 2)
        change_pct = (
            round((price / prev_close - 1) * 100, 2) if prev_close else 0.0
        )
    else:
        prev_close = price
        change_pct = 0.0
    return {
        "ticker": sym,
        "eod_price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "timestamp": bar_ts.strftime("%Y-%m-%d 16:00 ET"),
        "source": "yfinance",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated list of tickers (e.g. SPY,NVDA,AMD).",
    )
    args = p.parse_args()

    raw = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    quotes: list[dict] = []
    failed: list[dict] = []

    for sym in raw:
        if not TICKER_RE.match(sym):
            failed.append({"ticker": sym, "reason": "invalid ticker format"})
            continue
        try:
            quotes.append(_fetch_one(sym))
        except Exception as e:  # noqa: BLE001 (intentionally broad)
            failed.append({"ticker": sym, "reason": str(e) or type(e).__name__})

    payload = {
        "ok": True,
        "fetched_at": datetime.now(ET).strftime("%Y-%m-%d %H:%M ET"),
        "quotes": quotes,
        "failed": failed,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
