#!/usr/bin/env python3
"""
Fetch options chain data for an iron condor via yfinance.

Usage:
  python3 fetch_iron_condor.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]

  TARGET_DELTA  : absolute delta for both short strikes, e.g. 0.16  (default: 0.16)
  DTE_MIN       : minimum DTE, e.g. 35                              (default: 35)
  DTE_MAX       : maximum DTE, e.g. 45                              (default: 45)

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


def select_short_strike(df, price, T, target_delta, side="put"):
    """Select the OTM strike closest to target_delta."""
    if side == "put":
        otm = df[df["strike"] < price].copy()
    else:
        otm = df[df["strike"] > price].copy()

    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()

    if otm.empty:
        return None, None

    # Compute IV and delta
    opt_type = "put" if side == "put" else "call"
    otm["calc_iv"] = otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"], opt_type) or 0, axis=1
    )

    if side == "put":
        otm["calc_delta"] = otm.apply(
            lambda r: bs_put_delta_abs(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
            axis=1
        )
    else:
        otm["calc_delta"] = otm.apply(
            lambda r: bs_call_delta(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
            axis=1
        )

    valid = otm[otm["calc_delta"] > 0].copy()
    if valid.empty:
        return None, otm

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()]
    return short_row.to_dict(), valid


def select_wing(valid_df, short_strike, side="put"):
    """Select long (wing) strike ~10% away from short strike."""
    if side == "put":
        wing_target = short_strike * 0.90
    else:
        wing_target = short_strike * 1.10

    valid_df["wing_diff"] = (valid_df["strike"] - wing_target).abs()
    wing_row = valid_df.loc[valid_df["wing_diff"].idxmin()]
    return wing_row.to_dict()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_iron_condor.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
        sys.exit(1)

    ticker_sym = sys.argv[1].upper()
    target_delta = float(sys.argv[2]) if len(sys.argv) > 2 else 0.16
    dte_min = int(sys.argv[3]) if len(sys.argv) > 3 else 35
    dte_max = int(sys.argv[4]) if len(sys.argv) > 4 else 45

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

    # Option chain
    chain = tk.option_chain(expiry_str)

    # ── Put side ──────────────────────────────────────────────────────────────
    short_put_row, put_valid = select_short_strike(chain.puts, price, T, target_delta, "put")
    if short_put_row is None:
        print(json.dumps({"error": "No usable OTM put strikes — try during market hours"}))
        sys.exit(1)

    short_put_strike = float(short_put_row["strike"])
    short_put_delta = round(float(short_put_row["calc_delta"]), 3)
    short_put_iv = round(float(short_put_row["calc_iv"]), 4)
    short_put_mid = float(short_put_row["mid_price"])
    short_put_bid = round(float(short_put_row.get("bid", 0) or 0), 2)
    short_put_ask = round(float(short_put_row.get("ask", 0) or 0), 2)

    long_put_row = select_wing(put_valid, short_put_strike, "put")
    long_put_strike = float(long_put_row["strike"])
    long_put_mid = float(long_put_row["mid_price"])
    long_put_bid = round(float(long_put_row.get("bid", 0) or 0), 2)
    long_put_ask = round(float(long_put_row.get("ask", 0) or 0), 2)

    put_credit = round(short_put_mid - long_put_mid, 2)
    put_width = round(short_put_strike - long_put_strike, 2)

    # ── Call side ─────────────────────────────────────────────────────────────
    short_call_row, call_valid = select_short_strike(chain.calls, price, T, target_delta, "call")
    if short_call_row is None:
        print(json.dumps({"error": "No usable OTM call strikes — try during market hours"}))
        sys.exit(1)

    short_call_strike = float(short_call_row["strike"])
    short_call_delta = round(float(short_call_row["calc_delta"]), 3)
    short_call_iv = round(float(short_call_row["calc_iv"]), 4)
    short_call_mid = float(short_call_row["mid_price"])
    short_call_bid = round(float(short_call_row.get("bid", 0) or 0), 2)
    short_call_ask = round(float(short_call_row.get("ask", 0) or 0), 2)

    long_call_row = select_wing(call_valid, short_call_strike, "call")
    long_call_strike = float(long_call_row["strike"])
    long_call_mid = float(long_call_row["mid_price"])
    long_call_bid = round(float(long_call_row.get("bid", 0) or 0), 2)
    long_call_ask = round(float(long_call_row.get("ask", 0) or 0), 2)

    call_credit = round(short_call_mid - long_call_mid, 2)
    call_width = round(long_call_strike - short_call_strike, 2)

    # ── Combined metrics ──────────────────────────────────────────────────────
    total_credit = round(put_credit + call_credit, 2)
    wider_width = max(put_width, call_width)

    if wider_width <= 0 or total_credit <= 0:
        print(json.dumps({"error": f"Degenerate iron condor: credit={total_credit}, widths=({put_width}, {call_width})"}))
        sys.exit(1)

    max_profit = round(total_credit * 100, 2)
    max_loss = round((wider_width - total_credit) * 100, 2)
    breakeven_low = round(short_put_strike - total_credit, 2)
    breakeven_high = round(short_call_strike + total_credit, 2)
    ror = round(total_credit / (wider_width - total_credit) * 100, 1)
    pop = round((1 - short_put_delta - short_call_delta) * 100, 1)

    live = is_market_open()
    has_bid_ask = (short_put_bid > 0 and short_put_ask > 0)
    if live and has_bid_ask:
        price_source = "live_bid_ask_mid"
    elif has_bid_ask:
        price_source = "prev_close_bid_ask_mid"
    else:
        price_source = "last_trade_price"

    result = {
        "ticker": ticker_sym,
        "price": round(price, 2),
        "expiry": expiry_str,
        "dte": dte,
        "put_side": {
            "short_put": {
                "strike": short_put_strike,
                "mid": short_put_mid,
                "delta": short_put_delta,
                "iv_pct": round(short_put_iv * 100, 1),
                "bid": short_put_bid,
                "ask": short_put_ask,
            },
            "long_put": {
                "strike": long_put_strike,
                "mid": long_put_mid,
                "bid": long_put_bid,
                "ask": long_put_ask,
            },
            "credit": put_credit,
            "width": put_width,
        },
        "call_side": {
            "short_call": {
                "strike": short_call_strike,
                "mid": short_call_mid,
                "delta": short_call_delta,
                "iv_pct": round(short_call_iv * 100, 1),
                "bid": short_call_bid,
                "ask": short_call_ask,
            },
            "long_call": {
                "strike": long_call_strike,
                "mid": long_call_mid,
                "bid": long_call_bid,
                "ask": long_call_ask,
            },
            "credit": call_credit,
            "width": call_width,
        },
        "total_credit": total_credit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven_low": breakeven_low,
        "breakeven_high": breakeven_high,
        "profit_zone": f"${breakeven_low} – ${breakeven_high}",
        "return_on_risk_pct": ror,
        "prob_profit_pct": pop,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
