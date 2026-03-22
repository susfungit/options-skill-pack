#!/usr/bin/env python3
"""
Fetch options chain data for a bull put spread via yfinance.

Usage:
  python3 fetch_chain.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX] [SPREAD_WIDTH]

  TARGET_DELTA  : absolute delta value, e.g. 0.20  (default: 0.20)
  DTE_MIN       : minimum DTE, e.g. 35             (default: 35)
  DTE_MAX       : maximum DTE, e.g. 45             (default: 45)
  SPREAD_WIDTH  : % below short strike for long put (default: 10)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import sys
import json
import math
from datetime import date, datetime, time
import pytz

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


def bs_put_delta_abs(S, K, T, sigma, r=0.045):
    """Absolute value of BS put delta."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return abs(_norm_cdf(d1) - 1)


def implied_vol(S, K, T, market_price, r=0.045, tol=1e-5, max_iter=100):
    """Bisection IV solver. Returns None if no solution found."""
    if market_price <= 0 or T <= 0:
        return None
    intrinsic = max(K * math.exp(-r * T) - S, 0)
    if market_price <= intrinsic:
        return None
    lo, hi = 0.001, 20.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        price = bs_put_price(S, K, T, mid, r)
        if abs(price - market_price) < tol:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ── Helpers ───────────────────────────────────────────────────────────────────

def option_mid(row):
    """Best price: bid/ask mid if available, else lastPrice."""
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


def is_market_open():
    """Check if US equity market is currently open (Mon–Fri 9:30–16:00 ET)."""
    try:
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now <= market_close
    except Exception:
        return False  # pytz not available, can't determine


def find_best_expiry(expirations, dte_min, dte_max):
    today = date.today()
    target_dte = (dte_min + dte_max) / 2
    best, best_diff = None, float("inf")
    for exp_str in expirations:
        dte = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
        if dte_min <= dte <= dte_max:
            diff = abs(dte - target_dte)
            if diff < best_diff:
                best_diff, best = diff, (exp_str, dte)
    if best is None:
        for exp_str in expirations:
            dte = (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days
            if dte >= dte_min:
                return exp_str, dte
    return best


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_chain.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
        sys.exit(1)

    ticker_sym = sys.argv[1].upper()
    target_delta = float(sys.argv[2]) if len(sys.argv) > 2 else 0.20
    dte_min = int(sys.argv[3]) if len(sys.argv) > 3 else 35
    dte_max = int(sys.argv[4]) if len(sys.argv) > 4 else 45
    spread_width_pct = float(sys.argv[5]) if len(sys.argv) > 5 else 10.0

    tk = yf.Ticker(ticker_sym)

    # Stock price
    hist = tk.history(period="2d")
    if hist.empty:
        print(json.dumps({"error": f"No price data for {ticker_sym}"}))
        sys.exit(1)
    price = float(hist["Close"].iloc[-1])

    # Best expiry
    expirations = tk.options
    if not expirations:
        print(json.dumps({"error": f"No options listed for {ticker_sym}"}))
        sys.exit(1)

    expiry_result = find_best_expiry(expirations, dte_min, dte_max)
    if expiry_result is None:
        print(json.dumps({"error": f"No expiry within {dte_min}–{dte_max} DTE"}))
        sys.exit(1)
    expiry_str, dte = expiry_result
    T = dte / 365.0

    # Put chain
    chain = tk.option_chain(expiry_str)
    puts = chain.puts.copy()
    if puts.empty:
        print(json.dumps({"error": f"No puts for {ticker_sym} {expiry_str}"}))
        sys.exit(1)

    # OTM puts with a usable price
    puts_otm = puts[(puts["strike"] < price)].copy()
    puts_otm["mid_price"] = puts_otm.apply(option_mid, axis=1)
    puts_otm = puts_otm[puts_otm["mid_price"] > 0].copy()

    if puts_otm.empty:
        print(json.dumps({"error": "No usable OTM put prices in chain (market may be closed)"}))
        sys.exit(1)

    # Compute IV and delta from actual option prices
    puts_otm["calc_iv"] = puts_otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"]) or 0, axis=1
    )
    puts_otm["calc_delta"] = puts_otm.apply(
        lambda r: bs_put_delta_abs(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
        axis=1
    )

    # Select short put: closest delta to target
    valid = puts_otm[puts_otm["calc_delta"] > 0].copy()
    if valid.empty:
        print(json.dumps({"error": "Could not compute delta for any strike — try during market hours"}))
        sys.exit(1)

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()].to_dict()

    short_strike = float(short_row["strike"])
    short_delta = round(float(short_row["calc_delta"]), 3)
    short_iv = round(float(short_row["calc_iv"]), 4)
    short_mid = float(short_row["mid_price"])
    short_bid = round(float(short_row.get("bid", 0) or 0), 2)
    short_ask = round(float(short_row.get("ask", 0) or 0), 2)
    live = is_market_open()
    has_bid_ask = (short_bid > 0 and short_ask > 0)
    if live and has_bid_ask:
        price_source = "live_bid_ask_mid"
    elif has_bid_ask:
        price_source = "prev_close_bid_ask_mid"
    else:
        price_source = "last_trade_price"

    # Long put: nearest listed strike at spread_width_pct below short
    long_target = short_strike * (1 - spread_width_pct / 100)
    valid["long_diff"] = (valid["strike"] - long_target).abs()
    long_row = valid.loc[valid["long_diff"].idxmin()].to_dict()
    long_strike = float(long_row["strike"])
    long_mid = float(long_row["mid_price"])
    long_bid = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask = round(float(long_row.get("ask", 0) or 0), 2)

    # Metrics
    net_credit = round(short_mid - long_mid, 2)
    spread_width = round(short_strike - long_strike, 2)
    if spread_width <= 0 or net_credit <= 0:
        print(json.dumps({"error": f"Degenerate spread: short={short_strike}, long={long_strike}, credit={net_credit}"}))
        sys.exit(1)

    max_profit = round(net_credit * 100, 2)
    max_loss = round((spread_width - net_credit) * 100, 2)
    breakeven = round(short_strike - net_credit, 2)
    ror = round(net_credit / (spread_width - net_credit) * 100, 1)
    pop = round((1 - short_delta) * 100, 1)

    result = {
        "ticker": ticker_sym,
        "price": round(price, 2),
        "expiry": expiry_str,
        "dte": dte,
        "short_put": {
            "strike": short_strike,
            "mid": short_mid,
            "delta": short_delta,
            "iv_pct": round(short_iv * 100, 1),
            "bid": short_bid,
            "ask": short_ask,
        },
        "long_put": {
            "strike": long_strike,
            "mid": long_mid,
            "bid": long_bid,
            "ask": long_ask,
        },
        "net_credit": net_credit,
        "spread_width": spread_width,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "return_on_risk_pct": ror,
        "prob_profit_pct": pop,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance"
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
