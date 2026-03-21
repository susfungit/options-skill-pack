#!/usr/bin/env python3
"""
Fetch options chain data for a covered call via yfinance.

Usage:
  python3 fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]

  TARGET_DELTA  : absolute delta for the short call, e.g. 0.30  (default: 0.30)
  DTE_MIN       : minimum DTE, e.g. 30                           (default: 30)
  DTE_MAX       : maximum DTE, e.g. 45                           (default: 45)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import sys
import json
import math
from datetime import date, datetime
import pytz

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


def bs_call_delta(S, K, T, sigma, r=0.045):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1)


def implied_vol(S, K, T, market_price, r=0.045, tol=1e-5, max_iter=100):
    if market_price <= 0 or T <= 0:
        return None
    intrinsic = max(S - K * math.exp(-r * T), 0)
    if market_price <= intrinsic:
        return None
    lo, hi = 0.001, 20.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        price = bs_call_price(S, K, T, mid, r)
        if abs(price - market_price) < tol:
            return mid
        if price < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ── Helpers ───────────────────────────────────────────────────────────────────

def option_mid(row):
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


def is_market_open():
    try:
        et = pytz.timezone("America/New_York")
        now = datetime.now(et)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_open <= now <= market_close
    except Exception:
        return False


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


def select_short_call(df, price, T, target_delta):
    """Select the OTM call strike closest to target_delta."""
    otm = df[df["strike"] > price].copy()
    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()

    if otm.empty:
        return None

    otm["calc_iv"] = otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"]) or 0, axis=1
    )
    otm["calc_delta"] = otm.apply(
        lambda r: bs_call_delta(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
        axis=1
    )

    valid = otm[otm["calc_delta"] > 0].copy()
    if valid.empty:
        return None

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()]
    return short_row.to_dict()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
        sys.exit(1)

    ticker_sym = sys.argv[1].upper()
    target_delta = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
    dte_min = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    dte_max = int(sys.argv[4]) if len(sys.argv) > 4 else 45

    tk = yf.Ticker(ticker_sym)

    # Stock price
    hist = tk.history(period="2d")
    if hist.empty:
        print(json.dumps({"error": f"No price data for {ticker_sym}"}))
        sys.exit(1)
    price = round(float(hist["Close"].iloc[-1]), 2)

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

    # Option chain — calls only
    chain = tk.option_chain(expiry_str)
    short_call = select_short_call(chain.calls, price, T, target_delta)
    if short_call is None:
        print(json.dumps({"error": "No usable OTM call strikes — try during market hours"}))
        sys.exit(1)

    strike = float(short_call["strike"])
    mid = float(short_call["mid_price"])
    delta = round(float(short_call["calc_delta"]), 3)
    iv = round(float(short_call["calc_iv"]), 4)
    bid = round(float(short_call.get("bid", 0) or 0), 2)
    ask = round(float(short_call.get("ask", 0) or 0), 2)

    # Covered call metrics
    premium_per_contract = round(mid * 100, 2)
    static_return = round(mid / price * 100, 2)
    annualized_return = round(static_return * (365 / dte), 1)
    downside_protection = round(mid / price * 100, 2)
    called_away_return = round((strike - price + mid) / price * 100, 2)
    breakeven = round(price - mid, 2)
    prob_called = round(delta * 100, 1)

    # Price source
    live = is_market_open()
    has_bid_ask = bid > 0 and ask > 0
    if live and has_bid_ask:
        price_source = "live_bid_ask_mid"
    elif has_bid_ask:
        price_source = "prev_close_bid_ask_mid"
    else:
        price_source = "last_trade_price"

    result = {
        "ticker": ticker_sym,
        "stock_price": price,
        "expiry": expiry_str,
        "dte": dte,
        "short_call": {
            "strike": strike,
            "mid": mid,
            "delta": delta,
            "iv_pct": round(iv * 100, 1),
            "bid": bid,
            "ask": ask,
        },
        "premium_per_share": mid,
        "premium_per_contract": premium_per_contract,
        "static_return_pct": static_return,
        "annualized_return_pct": annualized_return,
        "downside_protection_pct": downside_protection,
        "called_away_return_pct": called_away_return,
        "breakeven": breakeven,
        "prob_called_pct": prob_called,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
