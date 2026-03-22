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
from datetime import date, datetime

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Black-Scholes helpers ─────────────────────────────────────────────────────

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_put_price(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return max(K - S, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_call_price(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_put_delta_abs(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return abs(_norm_cdf(d1) - 1)


def bs_call_delta(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1)


def implied_vol(S, K, T, market_price, option_type="put", r=0.045, tol=1e-5, max_iter=100):
    if market_price <= 0 or T <= 0:
        return None
    price_fn = bs_put_price if option_type == "put" else bs_call_price
    intrinsic = max(K * math.exp(-r * T) - S, 0) if option_type == "put" else max(S - K * math.exp(-r * T), 0)
    if market_price <= intrinsic:
        return None
    lo, hi = 0.001, 20.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        price = price_fn(S, K, T, mid, r)
        if abs(price - market_price) < tol:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def option_mid(row):
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_chain(ticker_str, expiry_str, side="both"):
    tk = yf.Ticker(ticker_str)
    price = tk.fast_info.get("lastPrice") or tk.fast_info.get("regularMarketPrice")
    if not price:
        hist = tk.history(period="5d")
        if hist.empty:
            return {"error": f"Cannot fetch price for {ticker_str}"}
        price = float(hist["Close"].iloc[-1])
    price = float(price)

    chain = tk.option_chain(expiry_str)
    today = date.today()
    exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    dte = (exp_date - today).days
    T = max(dte / 365.0, 1 / 365.0)

    result = {
        "ticker": ticker_str,
        "price": round(price, 2),
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
                "volume": int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
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
