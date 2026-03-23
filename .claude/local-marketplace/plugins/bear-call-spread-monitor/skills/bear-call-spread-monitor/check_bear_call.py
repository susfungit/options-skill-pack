#!/usr/bin/env python3
"""
Check the current status of an existing bear call spread position.

Usage:
  python3 check_bear_call.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY

  TICKER       : e.g. AAPL
  SHORT_STRIKE : sold call strike, e.g. 260
  LONG_STRIKE  : bought call strike, e.g. 270
  NET_CREDIT   : original credit received per share, e.g. 1.50
  EXPIRY       : expiry date as YYYY-MM-DD, e.g. 2026-05-01

Outputs JSON to stdout with current position metrics.
Errors output JSON with an "error" key.
"""

import sys
import json
import math
from datetime import date, datetime

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Black-Scholes helpers ─────────────────────────────────────────────────────

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_call_price(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def implied_vol(S, K, T, market_price, r=0.045, tol=1e-5, max_iter=100):
    if market_price <= 0 or T <= 0:
        return None
    intrinsic = max(S - K * math.exp(-r * T), 0)
    if market_price <= intrinsic:
        return None
    lo, hi = 0.001, 20.0
    for _ in range(max_iter):
        mid_v = (lo + hi) / 2
        price = bs_call_price(S, K, T, mid_v, r)
        if abs(price - market_price) < tol:
            return mid_v
        if price < market_price:
            lo = mid_v
        else:
            hi = mid_v
    return (lo + hi) / 2


def option_mid(row):
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 6:
        print(json.dumps({"error": "Usage: check_bear_call.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY"}))
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
    calls = chain.calls.copy()
    if calls.empty:
        print(json.dumps({"error": f"No calls available for {ticker_sym} {expiry_str}"}))
        sys.exit(1)

    calls["mid_price"] = calls.apply(option_mid, axis=1)
    T = max(dte / 365.0, 0.001)

    # Look up short call
    short_rows = calls[calls["strike"] == short_strike]
    if short_rows.empty:
        calls["strike_diff"] = (calls["strike"] - short_strike).abs()
        short_rows = calls.nsmallest(1, "strike_diff")
    short_row = short_rows.iloc[0].to_dict()
    short_mid = float(short_row["mid_price"]) if short_row["mid_price"] > 0 else None
    short_bid = round(float(short_row.get("bid", 0) or 0), 2)
    short_ask = round(float(short_row.get("ask", 0) or 0), 2)

    # Look up long call
    long_rows = calls[calls["strike"] == long_strike]
    if long_rows.empty:
        calls["strike_diff"] = (calls["strike"] - long_strike).abs()
        long_rows = calls.nsmallest(1, "strike_diff")
    long_row = long_rows.iloc[0].to_dict()
    long_mid = float(long_row["mid_price"]) if long_row["mid_price"] > 0 else None
    long_bid = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask = round(float(long_row.get("ask", 0) or 0), 2)

    # Current spread value and P&L
    spread_width = round(long_strike - short_strike, 2)
    max_loss = round((spread_width - net_credit) * 100, 2)
    max_profit = round(net_credit * 100, 2)

    if short_mid is not None and long_mid is not None:
        current_spread_value = round(short_mid - long_mid, 2)
        pnl_per_share = round(net_credit - current_spread_value, 2)

        if max_loss > 0:
            loss_pct_of_max = round(max(0, -pnl_per_share * 100) / max_loss * 100, 1)
        else:
            loss_pct_of_max = 0.0

        pnl_total = round(pnl_per_share * 100, 2)
    else:
        current_spread_value = None
        pnl_per_share = None
        pnl_total = None
        loss_pct_of_max = None

    # Distance metrics — buffer is how far stock is BELOW the short call
    buffer_pct = round((short_strike - stock_price) / stock_price * 100, 2)
    breakeven = round(short_strike + net_credit, 2)
    be_buffer_pct = round((breakeven - stock_price) / stock_price * 100, 2)

    result = {
        "ticker":               ticker_sym,
        "stock_price":          stock_price,
        "expiry":               expiry_str,
        "dte":                  dte,
        "short_call": {
            "strike":      short_strike,
            "current_mid": short_mid,
            "bid":         short_bid,
            "ask":         short_ask,
        },
        "long_call": {
            "strike":      long_strike,
            "current_mid": long_mid,
            "bid":         long_bid,
            "ask":         long_ask,
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
        "data_source":           "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
