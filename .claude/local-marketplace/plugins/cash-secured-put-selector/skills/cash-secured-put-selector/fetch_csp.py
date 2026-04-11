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
        error_exit("Usage: fetch_csp.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]")

    argv, explicit_expiry = parse_expiry_flag(sys.argv)

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.25
    dte_min = int(argv[3]) if len(argv) > 3 else 30
    dte_max = int(argv[4]) if len(argv) > 4 else 45

    tk = yf.Ticker(ticker_sym)
    price, prev_close, change_pct = get_stock_price(tk, ticker_sym)

    expirations = tk.options
    expiry_result = resolve_selector_expiry(tk, expirations, dte_min, dte_max, explicit_expiry, ticker_sym)
    expiry_str, dte = expiry_result
    T = dte / 365.0

    # Option chain — puts only
    chain = tk.option_chain(expiry_str)
    short_put_row, _, _ = select_strike_by_delta(chain.puts, price, T, target_delta, "put")
    if short_put_row is None:
        error_exit("No usable OTM put strikes — try during market hours")

    strike = float(short_put_row["strike"])
    mid = float(short_put_row["mid_price"])
    delta = round(float(short_put_row["calc_delta"]), 3)
    iv = round(float(short_put_row["calc_iv"]), 4)
    bid = round(float(short_put_row.get("bid", 0) or 0), 2)
    ask = round(float(short_put_row.get("ask", 0) or 0), 2)

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

    price_source = classify_price_source(bid, ask)

    result = {
        "ticker": ticker_sym,
        "stock_price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "expiry": expiry_str,
        "dte": dte,
        "short_put": {
            "strike": strike,
            "mid": mid,
            "delta": delta,
            "iv_pct": round(iv * 100, 1),
            "bid": bid,
            "ask": ask,
            "oi": _safe_int(short_put_row.get("openInterest")),
            "volume": _safe_int(short_put_row.get("volume")),
        },
        "premium_per_share": mid,
        "natural_premium": bid if bid > 0 else None,
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
