#!/usr/bin/env python3
"""
Fetch full option chain for a given ticker + expiry.

Usage:
  python3 fetch_chain_view.py TICKER EXPIRY [puts|calls|both]

  TICKER : stock symbol, e.g. AAPL
  EXPIRY : expiry date string matching yfinance, e.g. 2026-04-17
  SIDE   : puts, calls, or both (default: both)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import sys
import json
import math
import os
from datetime import date, datetime

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "local-marketplace", "plugins", "_shared"))
from options_lib import (
    bs_put_delta_abs, bs_call_delta, implied_vol, option_mid, get_stock_price,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_chain(ticker_str, expiry_str, side="both"):
    tk = yf.Ticker(ticker_str)
    price, prev_close, change_pct = get_stock_price(tk, ticker_str)
    price = float(price)

    chain = tk.option_chain(expiry_str)
    today = date.today()
    exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    dte = (exp_date - today).days
    T = max(dte / 365.0, 1 / 365.0)

    result = {
        "ticker": ticker_str,
        "price": round(price, 2),
        "prev_close": prev_close,
        "change_pct": change_pct,
        "expiry": expiry_str,
        "dte": dte,
    }

    def process_side(df, opt_type):
        rows = []
        for _, row in df.iterrows():
            strike = float(row["strike"])
            # Filter: OTM + near-ATM within 2%
            if opt_type == "put" and strike > price * 1.02:
                continue
            if opt_type == "call" and strike < price * 0.98:
                continue

            mid = option_mid(row)
            if mid <= 0:
                continue

            iv = implied_vol(price, strike, T, mid, option_type=opt_type)
            if iv is None:
                continue

            if opt_type == "put":
                delta = round(bs_put_delta_abs(price, strike, T, iv), 3)
            else:
                delta = round(bs_call_delta(price, strike, T, iv), 3)

            rows.append({
                "strike": strike,
                "bid": round(float(row.get("bid", 0) or 0), 2),
                "ask": round(float(row.get("ask", 0) or 0), 2),
                "mid": mid,
                "volume": int(row.get("volume", 0) or 0) if not math.isnan(row.get("volume", 0) or 0) else 0,
                "open_interest": int(row.get("openInterest", 0) or 0) if not math.isnan(row.get("openInterest", 0) or 0) else 0,
                "iv_pct": round(iv * 100, 1),
                "delta": delta,
            })
        return rows

    if side in ("puts", "both"):
        result["puts"] = process_side(chain.puts, "put")
    if side in ("calls", "both"):
        result["calls"] = process_side(chain.calls, "call")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: fetch_chain_view.py TICKER EXPIRY [puts|calls|both]"}))
        sys.exit(1)

    ticker = sys.argv[1].upper()
    expiry = sys.argv[2]
    side = sys.argv[3] if len(sys.argv) > 3 else "both"

    if side not in ("puts", "calls", "both"):
        print(json.dumps({"error": f"Invalid side: {side}. Use puts, calls, or both"}))
        sys.exit(1)

    try:
        out = fetch_chain(ticker, expiry, side)
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
