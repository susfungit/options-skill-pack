#!/usr/bin/env python3
"""
Check the current status of an existing cash-secured put position.

Usage:
  python3 check_csp.py TICKER SHORT_PUT_STRIKE NET_CREDIT EXPIRY

  TICKER          : e.g. AAPL
  SHORT_PUT_STRIKE: sold put strike, e.g. 200
  NET_CREDIT      : premium received per share, e.g. 3.50
  EXPIRY          : expiry date as YYYY-MM-DD, e.g. 2026-05-01

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
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: check_csp.py TICKER SHORT_PUT_STRIKE NET_CREDIT EXPIRY"}))
        sys.exit(1)

    ticker_sym   = sys.argv[1].upper()
    short_strike = float(sys.argv[2])
    net_credit   = float(sys.argv[3])
    expiry_str   = sys.argv[4]

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
    use_expiry = expiry_str
    if expiry_str not in available:
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
        use_expiry = nearest

    chain = tk.option_chain(use_expiry)
    puts = chain.puts.copy()
    if puts.empty:
        print(json.dumps({"error": f"No puts available for {ticker_sym} {use_expiry}"}))
        sys.exit(1)

    puts["mid_price"] = puts.apply(option_mid, axis=1)
    T = max(dte / 365.0, 0.001)

    # Look up short put
    put_rows = puts[puts["strike"] == short_strike]
    if put_rows.empty:
        puts["strike_diff"] = (puts["strike"] - short_strike).abs()
        put_rows = puts.nsmallest(1, "strike_diff")
    put_row = put_rows.iloc[0].to_dict()
    put_mid = float(put_row["mid_price"]) if put_row["mid_price"] > 0 else None
    put_bid = round(float(put_row.get("bid", 0) or 0), 2)
    put_ask = round(float(put_row.get("ask", 0) or 0), 2)
    put_volume = int(float(put_row.get("volume", 0) or 0))
    put_oi     = int(float(put_row.get("openInterest", 0) or 0))

    # Compute delta and IV
    current_delta = None
    current_iv = None
    if put_mid and put_mid > 0:
        iv = implied_vol(stock_price, short_strike, T, put_mid, "put")
        if iv and iv > 0:
            current_delta = round(bs_put_delta_abs(stock_price, short_strike, T, iv), 3)
            current_iv = round(iv * 100, 1)

    # P&L
    if put_mid is not None:
        pnl_per_share = round(net_credit - put_mid, 2)
        pnl_per_contract = round(pnl_per_share * 100, 2)
    else:
        pnl_per_share = None
        pnl_per_contract = None

    # Buffer: how far stock is above the short put strike
    # Positive = OTM (safe), negative = ITM (threatened)
    buffer_pct = round((stock_price - short_strike) / stock_price * 100, 2)

    # Breakeven and buffer
    breakeven = round(short_strike - net_credit, 2)
    be_buffer_pct = round((stock_price - breakeven) / stock_price * 100, 2)

    # Max loss: assigned at strike, stock goes to 0, minus premium received
    cash_required = round(short_strike * 100, 2)
    max_loss = round((short_strike - net_credit) * 100, 2)
    max_profit = round(net_credit * 100, 2)

    # Loss % of max
    if put_mid is not None and max_loss > 0:
        loss_pct_of_max = round(max(0, -pnl_per_share * 100) / max_loss * 100, 1)
    else:
        loss_pct_of_max = None

    # Effective buy price if assigned
    effective_buy_price = round(short_strike - net_credit, 2)
    discount_pct = round((stock_price - effective_buy_price) / stock_price * 100, 2)

    result = {
        "ticker":               ticker_sym,
        "stock_price":          stock_price,
        "expiry":               use_expiry,
        "dte":                  dte,
        "short_put": {
            "strike":           short_strike,
            "current_mid":      put_mid,
            "bid":              put_bid,
            "ask":              put_ask,
            "volume":           put_volume,
            "open_interest":    put_oi,
            "current_delta":    current_delta,
            "current_iv_pct":   current_iv,
        },
        "original_credit":      net_credit,
        "current_put_value":    put_mid,
        "pnl_per_share":        pnl_per_share,
        "pnl_per_contract":     pnl_per_contract,
        "max_profit":           max_profit,
        "max_loss":             max_loss,
        "cash_required":        cash_required,
        "breakeven":            breakeven,
        "buffer_pct":           buffer_pct,
        "be_buffer_pct":        be_buffer_pct,
        "loss_pct_of_max":      loss_pct_of_max,
        "effective_buy_price":  effective_buy_price,
        "discount_pct":         discount_pct,
        "cost_to_close":        round(put_ask * 100, 2) if put_ask > 0 else None,
        "data_source":          "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
