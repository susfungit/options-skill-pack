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
import math
from datetime import date, datetime

from _shared.options_lib import (
    bs_put_delta_abs, implied_vol, option_mid,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 6:
        print(json.dumps({"error": "Usage: check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY"}))
        sys.exit(1)

    ticker_sym   = sys.argv[1].upper()
    short_strike = float(sys.argv[2])
    long_strike  = float(sys.argv[3])
    net_credit   = float(sys.argv[4])
    expiry_str   = sys.argv[5]

    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        print(json.dumps({"error": f"Invalid expiry format: {expiry_str} — use YYYY-MM-DD"}))
        sys.exit(1)

    today = date.today()
    dte = (expiry_date - today).days

    if dte < 0:
        print(json.dumps({"error": f"Expiry {expiry_str} has already passed ({abs(dte)} days ago)"}))
        sys.exit(1)

    tk = yf.Ticker(ticker_sym)

    # Current stock price
    hist = tk.history(period="2d")
    if hist.empty:
        print(json.dumps({"error": f"No price data for {ticker_sym}"}))
        sys.exit(1)
    stock_price = round(float(hist["Close"].iloc[-1]), 2)

    # Option chain for the specific expiry
    available = tk.options
    if expiry_str not in available:
        # Find nearest available expiry within ±3 days
        nearest = None
        for exp in available:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            if abs((exp_date - expiry_date).days) <= 3:
                nearest = exp
                break
        if nearest is None:
            print(json.dumps({
                "error": f"Expiry {expiry_str} not found in chain. Available: {list(available[:5])}",
                "stock_price": stock_price,
                "dte": dte
            }))
            sys.exit(1)
        expiry_str = nearest

    chain = tk.option_chain(expiry_str)
    puts = chain.puts.copy()
    if puts.empty:
        print(json.dumps({"error": f"No puts available for {ticker_sym} {expiry_str}"}))
        sys.exit(1)

    puts["mid_price"] = puts.apply(option_mid, axis=1)
    T = max(dte / 365.0, 0.001)

    # Look up short put
    short_rows = puts[puts["strike"] == short_strike]
    if short_rows.empty:
        # Find nearest listed strike
        puts["strike_diff"] = (puts["strike"] - short_strike).abs()
        short_rows = puts.nsmallest(1, "strike_diff")
    short_row  = short_rows.iloc[0].to_dict()
    short_mid  = float(short_row["mid_price"]) if short_row["mid_price"] > 0 else None
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
    long_mid  = float(long_row["mid_price"]) if long_row["mid_price"] > 0 else None
    long_bid  = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask  = round(float(long_row.get("ask", 0) or 0), 2)
    long_volume = int(float(long_row.get("volume", 0) or 0))
    long_oi     = int(float(long_row.get("openInterest", 0) or 0))

    # Current spread value and P&L
    if short_mid is not None and long_mid is not None:
        current_spread_value = round(short_mid - long_mid, 2)
        pnl_per_share        = round(net_credit - current_spread_value, 2)
        spread_width         = round(short_strike - long_strike, 2)
        max_loss             = round((spread_width - net_credit) * 100, 2)
        max_profit           = round(net_credit * 100, 2)

        # % of max loss incurred  (0 = no loss, 100 = full max loss)
        if max_loss > 0:
            loss_pct_of_max = round(max(0, -pnl_per_share * 100) / max_loss * 100, 1)
        else:
            loss_pct_of_max = 0.0

        pnl_total = round(pnl_per_share * 100, 2)  # per contract
    else:
        current_spread_value = None
        pnl_per_share        = None
        pnl_total            = None
        loss_pct_of_max      = None
        spread_width         = round(short_strike - long_strike, 2)
        max_loss             = round((spread_width - net_credit) * 100, 2)
        max_profit           = round(net_credit * 100, 2)

    # Distance metrics
    buffer_pct = round((stock_price - short_strike) / stock_price * 100, 2)
    breakeven  = round(short_strike - net_credit, 2)
    be_buffer_pct = round((stock_price - breakeven) / stock_price * 100, 2)

    # IV and delta for short leg
    short_iv = None
    short_delta = None
    if short_mid and short_mid > 0:
        iv = implied_vol(stock_price, short_strike, T, short_mid, "put")
        if iv and iv > 0:
            short_delta = round(bs_put_delta_abs(stock_price, short_strike, T, iv), 3)
            short_iv = round(iv * 100, 1)

    # Cost to close the spread (buy back short at ask, sell long at bid)
    cost_to_close = round((short_ask - long_bid) * 100, 2) if short_ask > 0 else None

    result = {
        "ticker":               ticker_sym,
        "stock_price":          stock_price,
        "expiry":               expiry_str,
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
        "current_spread_value":  current_spread_value,
        "pnl_per_share":         pnl_per_share,
        "pnl_per_contract":      pnl_total,
        "max_profit":            max_profit,
        "max_loss":              max_loss,
        "breakeven":             breakeven,
        "buffer_pct":            buffer_pct,
        "be_buffer_pct":         be_buffer_pct,
        "loss_pct_of_max":       loss_pct_of_max,
        "cost_to_close":         cost_to_close,
        "data_source":           "yfinance"
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
