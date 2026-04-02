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

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import math
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, bs_put_price, bs_put_delta_abs, implied_vol,
    option_mid, is_market_open, find_best_expiry,
)

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed — run: pip3 install yfinance"}))
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_chain.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]"}))
        sys.exit(1)

    # Extract --expiry flag before positional parsing
    explicit_expiry = None
    argv = list(sys.argv)
    if "--expiry" in argv:
        idx = argv.index("--expiry")
        if idx + 1 < len(argv):
            explicit_expiry = argv[idx + 1]
        argv = argv[:idx] + argv[idx + 2:]

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.20
    dte_min = int(argv[3]) if len(argv) > 3 else 35
    dte_max = int(argv[4]) if len(argv) > 4 else 45
    spread_width_pct = float(argv[5]) if len(argv) > 5 else 10.0

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

    if explicit_expiry:
        if explicit_expiry not in expirations:
            print(json.dumps({"error": f"Expiry {explicit_expiry} not available for {ticker_sym}"}))
            sys.exit(1)
        expiry_result = (explicit_expiry, (datetime.strptime(explicit_expiry, "%Y-%m-%d").date() - date.today()).days)
    else:
        expiry_result = find_best_expiry(expirations, dte_min, dte_max)
        if expiry_result is None:
            print(json.dumps({"error": f"No expiry within {dte_min}–{dte_max} DTE"}))
            sys.exit(1)

    # Try preferred expiry first, then later expiries if chain is too thin
    today = date.today()
    sorted_expiries = sorted(
        [(e, (datetime.strptime(e, "%Y-%m-%d").date() - today).days) for e in expirations],
        key=lambda x: x[1]
    )
    # Start from the best expiry and try later ones
    start_idx = next((i for i, (e, _) in enumerate(sorted_expiries) if e == expiry_result[0]), 0)

    expiry_str, dte, puts_otm = None, None, None
    for exp_str, exp_dte in sorted_expiries[start_idx:]:
        chain = tk.option_chain(exp_str)
        puts = chain.puts.copy()
        if puts.empty:
            continue
        otm = puts[puts["strike"] < price].copy()
        otm["mid_price"] = otm.apply(option_mid, axis=1)
        otm = otm[otm["mid_price"] > 0].copy()
        if len(otm) >= 4:
            expiry_str, dte, puts_otm = exp_str, exp_dte, otm
            break

    if puts_otm is None or puts_otm.empty:
        print(json.dumps({"error": "No expiry with enough OTM put strikes — chain too thin"}))
        sys.exit(1)

    T = dte / 365.0

    # Compute IV and delta from actual option prices
    puts_otm["calc_iv"] = puts_otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"], "put") or 0, axis=1
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
    long_candidates = puts_otm[puts_otm["strike"] < short_strike].copy()
    if long_candidates.empty:
        print(json.dumps({"error": f"No strikes available below short strike {short_strike}"}))
        sys.exit(1)
    long_candidates["long_diff"] = (long_candidates["strike"] - long_target).abs()
    long_row = long_candidates.loc[long_candidates["long_diff"].idxmin()].to_dict()
    long_strike = float(long_row["strike"])
    long_mid = float(long_row["mid_price"])
    long_bid = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask = round(float(long_row.get("ask", 0) or 0), 2)

    # Metrics
    net_credit = round(short_mid - long_mid, 2)
    natural_credit = round(short_bid - long_ask, 2) if short_bid > 0 and long_ask > 0 else None
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
            "oi": _safe_int(short_row.get("openInterest")),
            "volume": _safe_int(short_row.get("volume")),
        },
        "long_put": {
            "strike": long_strike,
            "mid": long_mid,
            "bid": long_bid,
            "ask": long_ask,
            "oi": _safe_int(long_row.get("openInterest")),
            "volume": _safe_int(long_row.get("volume")),
        },
        "net_credit": net_credit,
        "natural_credit": natural_credit,
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
