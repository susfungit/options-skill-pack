#!/usr/bin/env python3
"""
Fetch options chain data for a covered call via yfinance.

Usage:
  python3 fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]

  TARGET_DELTA  : absolute delta for the short call, e.g. 0.30  (default: 0.30)
  DTE_MIN       : minimum DTE, e.g. 30                           (default: 30)
  DTE_MAX       : maximum DTE, e.g. 45                           (default: 45)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, error_exit, get_stock_price, parse_expiry_flag,
    resolve_selector_expiry, select_strike_by_delta, classify_price_source,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        error_exit("Usage: fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]")

    argv, explicit_expiry = parse_expiry_flag(sys.argv)

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.30
    dte_min = int(argv[3]) if len(argv) > 3 else 30
    dte_max = int(argv[4]) if len(argv) > 4 else 45

    tk = yf.Ticker(ticker_sym)
    price = get_stock_price(tk, ticker_sym)

    expirations = tk.options
    expiry_result = resolve_selector_expiry(tk, expirations, dte_min, dte_max, explicit_expiry, ticker_sym)
    expiry_str, dte = expiry_result
    T = dte / 365.0

    # Option chain — calls only
    chain = tk.option_chain(expiry_str)
    short_call_row, _, _ = select_strike_by_delta(chain.calls, price, T, target_delta, "call")
    if short_call_row is None:
        error_exit("No usable OTM call strikes — try during market hours")

    strike = float(short_call_row["strike"])
    mid = float(short_call_row["mid_price"])
    delta = round(float(short_call_row["calc_delta"]), 3)
    iv = round(float(short_call_row["calc_iv"]), 4)
    bid = round(float(short_call_row.get("bid", 0) or 0), 2)
    ask = round(float(short_call_row.get("ask", 0) or 0), 2)

    # Covered call metrics
    premium_per_contract = round(mid * 100, 2)
    static_return = round(mid / price * 100, 2)
    annualized_return = round(static_return * (365 / dte), 1)
    downside_protection = round(mid / price * 100, 2)
    called_away_return = round((strike - price + mid) / price * 100, 2)
    breakeven = round(price - mid, 2)
    prob_called = round(delta * 100, 1)

    price_source = classify_price_source(bid, ask)

    result = {
        "ticker": ticker_sym,
        "stock_price": price,
        "expiry": expiry_str,
        "dte": dte,
        "short_call": {
            "strike": strike,
            "mid": mid,
            "delta": delta,
            "iv_pct": round(iv * 100, 1),
            "bid": bid,
            "ask": ask,
            "oi": _safe_int(short_call_row.get("openInterest")),
            "volume": _safe_int(short_call_row.get("volume")),
        },
        "premium_per_share": mid,
        "natural_premium": bid if bid > 0 else None,
        "premium_per_contract": premium_per_contract,
        "static_return_pct": static_return,
        "annualized_return_pct": annualized_return,
        "downside_protection_pct": downside_protection,
        "called_away_return_pct": called_away_return,
        "breakeven": breakeven,
        "prob_called_pct": prob_called,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
