#!/usr/bin/env python3
"""
Check the current status of an existing bull put spread position.

Usage:
  python3 check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY

  TICKER       : e.g. AAPL
  SHORT_STRIKE : sold put strike, e.g. 155
  LONG_STRIKE  : bought put strike, e.g. 140
  NET_CREDIT   : original credit received per share, e.g. 1.98
  EXPIRY       : expiry date as YYYY-MM-DD, e.g. 2026-05-01

Outputs JSON to stdout with current position metrics.
Errors output JSON with an "error" key.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
from datetime import date, datetime

from _shared.options_lib import (
    error_exit, get_stock_price, resolve_monitor_expiry, compute_iv_delta,
    compute_spread_pnl, option_mid, option_mid_ex, fetch_chain_with_retry,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 6:
        error_exit("Usage: check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY")

    ticker_sym   = sys.argv[1].upper()
    short_strike = float(sys.argv[2])
    long_strike  = float(sys.argv[3])
    net_credit   = float(sys.argv[4])
    expiry_str   = sys.argv[5]

    tk = yf.Ticker(ticker_sym)
    stock_price = get_stock_price(tk, ticker_sym)

    use_expiry, expiry_date, dte = resolve_monitor_expiry(tk, expiry_str, ticker_sym)

    puts = fetch_chain_with_retry(tk, use_expiry, side="puts")
    if puts.empty:
        error_exit(f"No puts available for {ticker_sym} {use_expiry}")

    puts["mid_price"] = puts.apply(option_mid, axis=1)
    T = max(dte / 365.0, 0.001)

    # Look up short put
    short_rows = puts[puts["strike"] == short_strike]
    if short_rows.empty:
        puts["strike_diff"] = (puts["strike"] - short_strike).abs()
        short_rows = puts.nsmallest(1, "strike_diff")
    short_row  = short_rows.iloc[0].to_dict()
    short_mid, short_src = option_mid_ex(short_row)
    short_mid  = short_mid if short_mid > 0 else None
    short_bid  = round(float(short_row.get("bid", 0) or 0), 2)
    short_ask  = round(float(short_row.get("ask", 0) or 0), 2)
    short_volume = int(float(short_row.get("volume", 0) or 0))
    short_oi     = int(float(short_row.get("openInterest", 0) or 0))

    # Look up long put
    long_rows = puts[puts["strike"] == long_strike]
    if long_rows.empty:
        puts["strike_diff"] = (puts["strike"] - long_strike).abs()
        long_rows = puts.nsmallest(1, "strike_diff")
    long_row  = long_rows.iloc[0].to_dict()
    long_mid, long_src = option_mid_ex(long_row)
    long_mid  = long_mid if long_mid > 0 else None
    long_bid  = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask  = round(float(long_row.get("ask", 0) or 0), 2)
    long_volume = int(float(long_row.get("volume", 0) or 0))
    long_oi     = int(float(long_row.get("openInterest", 0) or 0))

    # Price source: "live" only if both legs have live bid/ask
    price_source = "live" if (short_src == "live" and long_src == "live") else "delayed"

    # Current spread value and P&L
    spread_width = round(short_strike - long_strike, 2)
    pnl = compute_spread_pnl(short_mid, long_mid, net_credit, spread_width)

    # Distance metrics
    buffer_pct = round((stock_price - short_strike) / stock_price * 100, 2)
    breakeven  = round(short_strike - net_credit, 2)
    be_buffer_pct = round((stock_price - breakeven) / stock_price * 100, 2)

    # IV and delta for short leg
    short_iv_raw, short_delta_raw = compute_iv_delta(stock_price, short_strike, T, short_mid, "put")
    short_iv = round(short_iv_raw * 100, 1) if short_iv_raw else None
    short_delta = round(short_delta_raw, 3) if short_delta_raw else None

    # Cost to close the spread (buy back short at ask, sell long at bid)
    cost_to_close = round((short_ask - long_bid) * 100, 2) if short_ask > 0 else None

    result = {
        "ticker":               ticker_sym,
        "stock_price":          stock_price,
        "expiry":               use_expiry,
        "dte":                  dte,
        "short_put": {
            "strike":  short_strike,
            "current_mid": short_mid,
            "bid":     short_bid,
            "ask":     short_ask,
            "volume":  short_volume,
            "open_interest": short_oi,
            "current_iv_pct": short_iv,
            "current_delta": short_delta,
        },
        "long_put": {
            "strike":  long_strike,
            "current_mid": long_mid,
            "bid":     long_bid,
            "ask":     long_ask,
            "volume":  long_volume,
            "open_interest": long_oi,
        },
        "original_credit":       net_credit,
        "current_spread_value":  pnl["current_spread_value"],
        "pnl_per_share":         pnl["pnl_per_share"],
        "pnl_per_contract":      pnl["pnl_per_contract"],
        "max_profit":            pnl["max_profit"],
        "max_loss":              pnl["max_loss"],
        "breakeven":             breakeven,
        "buffer_pct":            buffer_pct,
        "be_buffer_pct":         be_buffer_pct,
        "loss_pct_of_max":       pnl["loss_pct_of_max"],
        "cost_to_close":         cost_to_close,
        "price_source":          price_source,
        "data_source":           "yfinance"
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
