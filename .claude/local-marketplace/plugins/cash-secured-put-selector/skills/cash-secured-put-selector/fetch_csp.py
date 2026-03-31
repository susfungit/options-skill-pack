#!/usr/bin/env python3
"""
Fetch options chain data for a cash-secured put via yfinance.

Usage:
  python3 fetch_csp.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]

  TARGET_DELTA  : absolute delta for the short put, e.g. 0.25  (default: 0.25)
  DTE_MIN       : minimum DTE, e.g. 30                          (default: 30)
  DTE_MAX       : maximum DTE, e.g. 45                          (default: 45)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import math
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, bs_put_delta_abs, implied_vol,
    option_mid, is_market_open, find_best_expiry,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


def select_short_put(df, price, T, target_delta):
    """Select the OTM put strike closest to target_delta."""
    otm = df[df["strike"] < price].copy()
    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()

    if otm.empty:
        return None

    otm["calc_iv"] = otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"], "put") or 0, axis=1
    )
    otm["calc_delta"] = otm.apply(
        lambda r: bs_put_delta_abs(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
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
        print(json.dumps({"error": "Usage: fetch_csp.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
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
    target_delta = float(argv[2]) if len(argv) > 2 else 0.25
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

    # Option chain — puts only
    chain = tk.option_chain(expiry_str)
    short_put = select_short_put(chain.puts, price, T, target_delta)
    if short_put is None:
        print(json.dumps({"error": "No usable OTM put strikes — try during market hours"}))
        sys.exit(1)

    strike = float(short_put["strike"])
    mid = float(short_put["mid_price"])
    delta = round(float(short_put["calc_delta"]), 3)
    iv = round(float(short_put["calc_iv"]), 4)
    bid = round(float(short_put.get("bid", 0) or 0), 2)
    ask = round(float(short_put.get("ask", 0) or 0), 2)

    # CSP metrics
    premium_per_contract = round(mid * 100, 2)
    cash_required = round(strike * 100, 2)
    return_on_capital = round(mid / strike * 100, 2)
    annualized_return = round(return_on_capital * (365 / dte), 1)
    effective_buy_price = round(strike - mid, 2)
    discount_pct = round((price - effective_buy_price) / price * 100, 2)
    breakeven = effective_buy_price
    prob_assigned = round(delta * 100, 1)
    prob_profit = round((1 - delta) * 100, 1)

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
        "short_put": {
            "strike": strike,
            "mid": mid,
            "delta": delta,
            "iv_pct": round(iv * 100, 1),
            "bid": bid,
            "ask": ask,
            "oi": _safe_int(short_put.get("openInterest")),
            "volume": _safe_int(short_put.get("volume")),
        },
        "premium_per_share": mid,
        "premium_per_contract": premium_per_contract,
        "cash_required": cash_required,
        "return_on_capital_pct": return_on_capital,
        "annualized_return_pct": annualized_return,
        "effective_buy_price": effective_buy_price,
        "discount_pct": discount_pct,
        "breakeven": breakeven,
        "prob_assigned_pct": prob_assigned,
        "prob_profit_pct": prob_profit,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
