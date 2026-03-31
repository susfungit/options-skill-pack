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
import math
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, bs_call_delta, implied_vol,
    option_mid, is_market_open, find_best_expiry,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


def select_short_call(df, price, T, target_delta):
    """Select the OTM call strike closest to target_delta."""
    otm = df[df["strike"] > price].copy()
    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()

    if otm.empty:
        return None

    otm["calc_iv"] = otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"], "call") or 0, axis=1
    )
    otm["calc_delta"] = otm.apply(
        lambda r: bs_call_delta(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
        axis=1
    )

    valid = otm[otm["calc_delta"] > 0].copy()
    if valid.empty:
        return None

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()]
    return short_row.to_dict()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
        sys.exit(1)

    # Extract --expiry flag before positional parsing
    explicit_expiry = None
    argv = list(sys.argv)
    if "--expiry" in argv:
        idx = argv.index("--expiry")
        if idx + 1 < len(argv):
            explicit_expiry = argv[idx + 1]
        argv = argv[:idx] + argv[idx + 2:]

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.30
    dte_min = int(argv[3]) if len(argv) > 3 else 30
    dte_max = int(argv[4]) if len(argv) > 4 else 45

    tk = yf.Ticker(ticker_sym)

    # Stock price
    hist = tk.history(period="2d")
    if hist.empty:
        print(json.dumps({"error": f"No price data for {ticker_sym}"}))
        sys.exit(1)
    price = round(float(hist["Close"].iloc[-1]), 2)

    # Best expiry
    expirations = tk.options
    if not expirations:
        print(json.dumps({"error": f"No options listed for {ticker_sym}"}))
        sys.exit(1)

    if explicit_expiry:
        if explicit_expiry not in expirations:
            print(json.dumps({"error": f"Expiry {explicit_expiry} not available for {ticker_sym}"}))
            sys.exit(1)
        expiry_result = (explicit_expiry, (datetime.strptime(explicit_expiry, "%Y-%m-%d").date() - date.today()).days)
    else:
        expiry_result = find_best_expiry(expirations, dte_min, dte_max)
        if expiry_result is None:
            print(json.dumps({"error": f"No expiry within {dte_min}–{dte_max} DTE"}))
            sys.exit(1)
    expiry_str, dte = expiry_result
    T = dte / 365.0

    # Option chain — calls only
    chain = tk.option_chain(expiry_str)
    short_call = select_short_call(chain.calls, price, T, target_delta)
    if short_call is None:
        print(json.dumps({"error": "No usable OTM call strikes — try during market hours"}))
        sys.exit(1)

    strike = float(short_call["strike"])
    mid = float(short_call["mid_price"])
    delta = round(float(short_call["calc_delta"]), 3)
    iv = round(float(short_call["calc_iv"]), 4)
    bid = round(float(short_call.get("bid", 0) or 0), 2)
    ask = round(float(short_call.get("ask", 0) or 0), 2)

    # Covered call metrics
    premium_per_contract = round(mid * 100, 2)
    static_return = round(mid / price * 100, 2)
    annualized_return = round(static_return * (365 / dte), 1)
    downside_protection = round(mid / price * 100, 2)
    called_away_return = round((strike - price + mid) / price * 100, 2)
    breakeven = round(price - mid, 2)
    prob_called = round(delta * 100, 1)

    # Price source
    live = is_market_open()
    has_bid_ask = bid > 0 and ask > 0
    if live and has_bid_ask:
        price_source = "live_bid_ask_mid"
    elif has_bid_ask:
        price_source = "prev_close_bid_ask_mid"
    else:
        price_source = "last_trade_price"

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
            "oi": _safe_int(short_call.get("openInterest")),
            "volume": _safe_int(short_call.get("volume")),
        },
        "premium_per_share": mid,
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
