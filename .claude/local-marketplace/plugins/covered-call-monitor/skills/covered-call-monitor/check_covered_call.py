#!/usr/bin/env python3
"""
Check the current status of an existing covered call position.

Usage:
  python3 check_covered_call.py TICKER SHORT_CALL_STRIKE NET_CREDIT EXPIRY [COST_BASIS]

  TICKER            : e.g. AAPL
  SHORT_CALL_STRIKE : sold call strike, e.g. 260
  NET_CREDIT        : premium received per share, e.g. 3.33
  EXPIRY            : expiry date as YYYY-MM-DD, e.g. 2026-04-24
  COST_BASIS        : (optional) stock purchase price per share, e.g. 245

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
    bs_call_delta, implied_vol, option_mid, option_mid_ex,
    fetch_chain_with_retry,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: check_covered_call.py TICKER SHORT_CALL_STRIKE NET_CREDIT EXPIRY [COST_BASIS]"}))
        sys.exit(1)

    ticker_sym = sys.argv[1].upper()
    short_strike = float(sys.argv[2])
    net_credit = float(sys.argv[3])
    expiry_str = sys.argv[4]
    cost_basis = float(sys.argv[5]) if len(sys.argv) > 5 else None

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

    calls = fetch_chain_with_retry(tk, use_expiry, side="calls")
    if calls.empty:
        print(json.dumps({"error": f"No calls available for {ticker_sym} {use_expiry}"}))
        sys.exit(1)

    calls["mid_price"] = calls.apply(option_mid, axis=1)
    T = max(dte / 365.0, 0.001)

    # Look up short call
    call_rows = calls[calls["strike"] == short_strike]
    if call_rows.empty:
        calls["strike_diff"] = (calls["strike"] - short_strike).abs()
        call_rows = calls.nsmallest(1, "strike_diff")
    call_row = call_rows.iloc[0].to_dict()
    call_mid, call_src = option_mid_ex(call_row)
    call_mid = call_mid if call_mid > 0 else None
    call_bid = round(float(call_row.get("bid", 0) or 0), 2)
    call_ask = round(float(call_row.get("ask", 0) or 0), 2)
    call_volume = int(float(call_row.get("volume", 0) or 0))
    call_oi     = int(float(call_row.get("openInterest", 0) or 0))

    price_source = "live" if call_src == "live" else "delayed"

    # Compute delta and IV
    current_delta = None
    current_iv = None
    if call_mid and call_mid > 0:
        iv = implied_vol(stock_price, short_strike, T, call_mid, "call")
        if iv and iv > 0:
            current_delta = round(bs_call_delta(stock_price, short_strike, T, iv), 3)
            current_iv = round(iv * 100, 1)

    # P&L
    if call_mid is not None:
        pnl_per_share = round(net_credit - call_mid, 2)
        pnl_per_contract = round(pnl_per_share * 100, 2)
    else:
        pnl_per_share = None
        pnl_per_contract = None

    # Buffer: how far stock is below the short call strike
    # Positive = OTM (safe), negative = ITM (threatened)
    buffer_pct = round((short_strike - stock_price) / stock_price * 100, 2)

    # Intrinsic and time value
    intrinsic = round(max(stock_price - short_strike, 0), 2)
    time_value = round(call_mid - intrinsic, 2) if call_mid else None

    # Max profit on the call = premium received (if stock stays below strike)
    max_profit = round(net_credit * 100, 2)

    # Build result
    result = {
        "ticker": ticker_sym,
        "stock_price": stock_price,
        "expiry": use_expiry,
        "dte": dte,
        "short_call": {
            "strike": short_strike,
            "current_mid": call_mid,
            "bid": call_bid,
            "ask": call_ask,
            "volume": call_volume,
            "open_interest": call_oi,
            "current_delta": current_delta,
            "current_iv_pct": current_iv,
        },
        "original_credit": net_credit,
        "current_call_value": call_mid,
        "pnl_per_share": pnl_per_share,
        "pnl_per_contract": pnl_per_contract,
        "max_profit": max_profit,
        "buffer_pct": buffer_pct,
        "intrinsic_value": intrinsic,
        "time_value": time_value,
        "cost_to_close": round(call_ask * 100, 2) if call_ask > 0 else None,
        "price_source": price_source,
        "data_source": "yfinance",
    }

    # Cost basis metrics (optional)
    if cost_basis is not None:
        effective_cost_basis = round(cost_basis - net_credit, 2)
        called_away_pnl = round(short_strike - cost_basis + net_credit, 2)
        called_away_return_pct = round(called_away_pnl / cost_basis * 100, 2)
        result["cost_basis"] = cost_basis
        result["effective_cost_basis"] = effective_cost_basis
        result["called_away_pnl"] = called_away_pnl
        result["called_away_return_pct"] = called_away_return_pct

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
