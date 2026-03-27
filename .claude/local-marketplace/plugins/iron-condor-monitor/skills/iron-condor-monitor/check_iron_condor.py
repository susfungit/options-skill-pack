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


def option_mid(row):
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


def find_strike_data(chain_df, target_strike):
    """Find the row for a given strike, or the nearest available. Return full data."""
    exact = chain_df[chain_df["strike"] == target_strike]
    if not exact.empty:
        row = exact.iloc[0].to_dict()
    else:
        df = chain_df.copy()
        df["_diff"] = (df["strike"] - target_strike).abs()
        row = df.nsmallest(1, "_diff").iloc[0].to_dict()
    mid = option_mid(row)
    return {
        "mid": mid,
        "bid": round(float(row.get("bid", 0) or 0), 2),
        "ask": round(float(row.get("ask", 0) or 0), 2),
        "volume": int(float(row.get("volume", 0) or 0)),
        "open_interest": int(float(row.get("openInterest", 0) or 0)),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 8:
        print(json.dumps({
            "error": "Usage: check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY"
        }))
        sys.exit(1)

    ticker_sym   = sys.argv[1].upper()
    short_put    = float(sys.argv[2])
    long_put     = float(sys.argv[3])
    short_call   = float(sys.argv[4])
    long_call    = float(sys.argv[5])
    net_credit   = float(sys.argv[6])
    expiry_str   = sys.argv[7]

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
    target_expiry = expiry_str
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
        target_expiry = nearest

    chain = tk.option_chain(target_expiry)
    puts = chain.puts.copy()
    calls = chain.calls.copy()

    if puts.empty or calls.empty:
        print(json.dumps({"error": f"No options data for {ticker_sym} {target_expiry}"}))
        sys.exit(1)

    # Look up all 4 legs
    sp = find_strike_data(puts, short_put)
    lp = find_strike_data(puts, long_put)
    sc = find_strike_data(calls, short_call)
    lc = find_strike_data(calls, long_call)

    sp_mid, sp_bid, sp_ask = sp["mid"], sp["bid"], sp["ask"]
    lp_mid, lp_bid, lp_ask = lp["mid"], lp["bid"], lp["ask"]
    sc_mid, sc_bid, sc_ask = sc["mid"], sc["bid"], sc["ask"]
    lc_mid, lc_bid, lc_ask = lc["mid"], lc["bid"], lc["ask"]

    T = max(dte / 365.0, 0.001)

    # IV and delta for short put
    sp_iv, sp_delta = None, None
    if sp_mid and sp_mid > 0:
        iv = implied_vol(stock_price, short_put, T, sp_mid, option_type="put")
        if iv and iv > 0:
            sp_delta = round(bs_put_delta_abs(stock_price, short_put, T, iv), 3)
            sp_iv = round(iv * 100, 1)

    # IV and delta for short call
    sc_iv, sc_delta = None, None
    if sc_mid and sc_mid > 0:
        iv = implied_vol(stock_price, short_call, T, sc_mid, option_type="call")
        if iv and iv > 0:
            sc_delta = round(bs_call_delta(stock_price, short_call, T, iv), 3)
            sc_iv = round(iv * 100, 1)

    # Cost to close each side and total
    put_cost_to_close = round((sp_ask - lp_bid) * 100, 2) if sp_ask > 0 else None
    call_cost_to_close = round((sc_ask - lc_bid) * 100, 2) if sc_ask > 0 else None
    cost_to_close = None
    if put_cost_to_close is not None and call_cost_to_close is not None:
        cost_to_close = round(put_cost_to_close + call_cost_to_close, 2)

    # Current spread values
    put_spread_value  = round(sp_mid - lp_mid, 2) if sp_mid and lp_mid else None
    call_spread_value = round(sc_mid - lc_mid, 2) if sc_mid and lc_mid else None

    if put_spread_value is not None and call_spread_value is not None:
        current_spread_value = round(put_spread_value + call_spread_value, 2)
        pnl_per_share        = round(net_credit - current_spread_value, 2)

        put_width   = round(short_put - long_put, 2)
        call_width  = round(long_call - short_call, 2)
        wider_width = max(put_width, call_width)

        max_profit  = round(net_credit * 100, 2)
        max_loss    = round((wider_width - net_credit) * 100, 2)

        if max_loss > 0:
            loss_pct_of_max = round(max(0, -pnl_per_share * 100) / max_loss * 100, 1)
        else:
            loss_pct_of_max = 0.0

        pnl_total = round(pnl_per_share * 100, 2)
    else:
        current_spread_value = None
        pnl_per_share        = None
        pnl_total            = None
        loss_pct_of_max      = None
        put_width   = round(short_put - long_put, 2)
        call_width  = round(long_call - short_call, 2)
        wider_width = max(put_width, call_width)
        max_profit  = round(net_credit * 100, 2)
        max_loss    = round((wider_width - net_credit) * 100, 2)

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
        "expiry":               target_expiry,
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
        "current_spread_value":  current_spread_value,
        "pnl_per_share":         pnl_per_share,
        "pnl_per_contract":      pnl_total,
        "max_profit":            max_profit,
        "max_loss":              max_loss,
        "breakeven_low":         breakeven_low,
        "breakeven_high":        breakeven_high,
        "buffer_pct_put":        buffer_pct_put,
        "buffer_pct_call":       buffer_pct_call,
        "worst_buffer_pct":      worst_buffer_pct,
        "worst_side":            worst_side,
        "loss_pct_of_max":       loss_pct_of_max,
        "cost_to_close":         cost_to_close,
        "put_cost_to_close":     put_cost_to_close,
        "call_cost_to_close":    call_cost_to_close,
        "data_source":           "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
