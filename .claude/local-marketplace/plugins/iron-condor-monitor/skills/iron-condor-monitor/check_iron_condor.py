#!/usr/bin/env python3
"""
Check the current status of an existing iron condor position.

Usage:
  python3 check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY

  TICKER      : e.g. AAPL
  SHORT_PUT   : sold put strike, e.g. 220
  LONG_PUT    : bought put strike, e.g. 200
  SHORT_CALL  : sold call strike, e.g. 275
  LONG_CALL   : bought call strike, e.g. 300
  NET_CREDIT  : total credit received per share (both sides combined), e.g. 2.86
  EXPIRY      : expiry date as YYYY-MM-DD, e.g. 2026-05-01

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
    compute_spread_pnl, find_strike_data, fetch_chain_with_retry,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 8:
        error_exit("Usage: check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY")

    ticker_sym   = sys.argv[1].upper()
    short_put    = float(sys.argv[2])
    long_put     = float(sys.argv[3])
    short_call   = float(sys.argv[4])
    long_call    = float(sys.argv[5])
    net_credit   = float(sys.argv[6])
    expiry_str   = sys.argv[7]

    tk = yf.Ticker(ticker_sym)
    stock_price = get_stock_price(tk, ticker_sym)

    use_expiry, expiry_date, dte = resolve_monitor_expiry(tk, expiry_str, ticker_sym)

    puts = fetch_chain_with_retry(tk, use_expiry, side="puts")
    calls = fetch_chain_with_retry(tk, use_expiry, side="calls")

    if puts.empty or calls.empty:
        error_exit(f"No options data for {ticker_sym} {use_expiry}")

    # Look up all 4 legs
    sp = find_strike_data(puts, short_put)
    lp = find_strike_data(puts, long_put)
    sc = find_strike_data(calls, short_call)
    lc = find_strike_data(calls, long_call)

    # Price source: "live" only if all 4 legs have live bid/ask
    all_live = all(leg["src"] == "live" for leg in [sp, lp, sc, lc])
    price_source = "live" if all_live else "delayed"

    sp_mid, sp_bid, sp_ask = sp["mid"], sp["bid"], sp["ask"]
    lp_mid, lp_bid, lp_ask = lp["mid"], lp["bid"], lp["ask"]
    sc_mid, sc_bid, sc_ask = sc["mid"], sc["bid"], sc["ask"]
    lc_mid, lc_bid, lc_ask = lc["mid"], lc["bid"], lc["ask"]

    T = max(dte / 365.0, 0.001)

    # IV and delta for short put
    sp_iv_raw, sp_delta_raw = compute_iv_delta(stock_price, short_put, T, sp_mid, "put")
    sp_iv = round(sp_iv_raw * 100, 1) if sp_iv_raw else None
    sp_delta = round(sp_delta_raw, 3) if sp_delta_raw else None

    # IV and delta for short call
    sc_iv_raw, sc_delta_raw = compute_iv_delta(stock_price, short_call, T, sc_mid, "call")
    sc_iv = round(sc_iv_raw * 100, 1) if sc_iv_raw else None
    sc_delta = round(sc_delta_raw, 3) if sc_delta_raw else None

    # Cost to close each side and total
    put_cost_to_close = round((sp_ask - lp_bid) * 100, 2) if sp_ask > 0 else None
    call_cost_to_close = round((sc_ask - lc_bid) * 100, 2) if sc_ask > 0 else None
    cost_to_close = None
    if put_cost_to_close is not None and call_cost_to_close is not None:
        cost_to_close = round(put_cost_to_close + call_cost_to_close, 2)
    put_cost_mid = round((sp_mid - lp_mid) * 100, 2) if sp_mid and lp_mid else None
    call_cost_mid = round((sc_mid - lc_mid) * 100, 2) if sc_mid and lc_mid else None
    cost_to_close_mid = None
    if put_cost_mid is not None and call_cost_mid is not None:
        cost_to_close_mid = round(put_cost_mid + call_cost_mid, 2)

    # Current spread values
    put_spread_value  = round(sp_mid - lp_mid, 2) if sp_mid and lp_mid else None
    call_spread_value = round(sc_mid - lc_mid, 2) if sc_mid and lc_mid else None

    put_width   = round(short_put - long_put, 2)
    call_width  = round(long_call - short_call, 2)
    wider_width = max(put_width, call_width)

    # Combined short_mid/long_mid for the whole condor
    combo_short = round(sp_mid + sc_mid, 2) if sp_mid and sc_mid else None
    combo_long = round(lp_mid + lc_mid, 2) if lp_mid and lc_mid else None
    pnl = compute_spread_pnl(combo_short, combo_long, net_credit, wider_width)

    # Distance metrics — two-sided
    buffer_pct_put  = round((stock_price - short_put) / stock_price * 100, 2)
    buffer_pct_call = round((short_call - stock_price) / stock_price * 100, 2)
    worst_buffer_pct = min(buffer_pct_put, buffer_pct_call)
    worst_side = "put" if buffer_pct_put <= buffer_pct_call else "call"

    breakeven_low  = round(short_put - net_credit, 2)
    breakeven_high = round(short_call + net_credit, 2)

    result = {
        "ticker":               ticker_sym,
        "stock_price":          stock_price,
        "expiry":               use_expiry,
        "dte":                  dte,
        "short_put": {
            "strike":      short_put,
            "current_mid": sp_mid,
            "bid":         sp_bid,
            "ask":         sp_ask,
            "volume":      sp["volume"],
            "open_interest": sp["open_interest"],
            "current_iv_pct": sp_iv,
            "current_delta": sp_delta,
        },
        "long_put": {
            "strike":      long_put,
            "current_mid": lp_mid,
            "bid":         lp_bid,
            "ask":         lp_ask,
            "volume":      lp["volume"],
            "open_interest": lp["open_interest"],
        },
        "short_call": {
            "strike":      short_call,
            "current_mid": sc_mid,
            "bid":         sc_bid,
            "ask":         sc_ask,
            "volume":      sc["volume"],
            "open_interest": sc["open_interest"],
            "current_iv_pct": sc_iv,
            "current_delta": sc_delta,
        },
        "long_call": {
            "strike":      long_call,
            "current_mid": lc_mid,
            "bid":         lc_bid,
            "ask":         lc_ask,
            "volume":      lc["volume"],
            "open_interest": lc["open_interest"],
        },
        "original_credit":       net_credit,
        "put_spread_value":      put_spread_value,
        "call_spread_value":     call_spread_value,
        "current_spread_value":  pnl["current_spread_value"],
        "pnl_per_share":         pnl["pnl_per_share"],
        "pnl_per_contract":      pnl["pnl_per_contract"],
        "max_profit":            pnl["max_profit"],
        "max_loss":              pnl["max_loss"],
        "breakeven_low":         breakeven_low,
        "breakeven_high":        breakeven_high,
        "buffer_pct_put":        buffer_pct_put,
        "buffer_pct_call":       buffer_pct_call,
        "worst_buffer_pct":      worst_buffer_pct,
        "worst_side":            worst_side,
        "loss_pct_of_max":       pnl["loss_pct_of_max"],
        "cost_to_close":         cost_to_close,
        "cost_to_close_mid":     cost_to_close_mid,
        "put_cost_to_close":     put_cost_to_close,
        "call_cost_to_close":    call_cost_to_close,
        "price_source":          price_source,
        "data_source":           "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
