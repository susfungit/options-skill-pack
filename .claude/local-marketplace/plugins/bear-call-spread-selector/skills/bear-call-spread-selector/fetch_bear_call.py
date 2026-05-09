#!/usr/bin/env python3
"""
Fetch options chain data for a bear call spread via yfinance.

Usage:
  python3 fetch_bear_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX] [SPREAD_WIDTH] [MIN_ROR]

  TARGET_DELTA  : absolute delta value, e.g. 0.20  (default: 0.20)
  DTE_MIN       : minimum DTE, e.g. 35             (default: 35)
  DTE_MAX       : maximum DTE, e.g. 45             (default: 45)
  SPREAD_WIDTH  : % above short strike for long call (default: 10)
  MIN_ROR       : minimum return-on-risk %, 0 disables (default: 20)

If the requested width can't clear MIN_ROR, the script tries progressively
wider variants (15%, 20%, 25%) before giving up. Delta is held fixed.

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, error_exit, get_stock_price, parse_expiry_flag,
    resolve_selector_expiry, classify_price_source, build_spread_metrics,
    option_mid, implied_vol, bs_call_delta,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        error_exit("Usage: fetch_bear_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX] [SPREAD_WIDTH]")

    argv, explicit_expiry = parse_expiry_flag(sys.argv)

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.20
    dte_min = int(argv[3]) if len(argv) > 3 else 35
    dte_max = int(argv[4]) if len(argv) > 4 else 45
    spread_width_pct = float(argv[5]) if len(argv) > 5 else 10.0
    min_ror = float(argv[6]) if len(argv) > 6 else 20.0

    tk = yf.Ticker(ticker_sym)
    price, prev_close, change_pct = get_stock_price(tk, ticker_sym)

    expirations = tk.options
    expiry_result = resolve_selector_expiry(tk, expirations, dte_min, dte_max, explicit_expiry, ticker_sym)

    # Try preferred expiry first, then later expiries if chain is too thin
    today = date.today()
    sorted_expiries = sorted(
        [(e, (datetime.strptime(e, "%Y-%m-%d").date() - today).days) for e in expirations],
        key=lambda x: x[1]
    )
    start_idx = next((i for i, (e, _) in enumerate(sorted_expiries) if e == expiry_result[0]), 0)

    expiry_str, dte, calls_otm = None, None, None
    for exp_str, exp_dte in sorted_expiries[start_idx:]:
        chain = tk.option_chain(exp_str)
        calls = chain.calls.copy()
        if calls.empty:
            continue
        otm = calls[calls["strike"] > price].copy()
        otm["mid_price"] = otm.apply(option_mid, axis=1)
        otm = otm[otm["mid_price"] > 0].copy()
        if len(otm) >= 4:
            expiry_str, dte, calls_otm = exp_str, exp_dte, otm
            break

    if calls_otm is None or calls_otm.empty:
        error_exit("No expiry with enough OTM call strikes — chain too thin")

    T = dte / 365.0

    # Compute IV and delta from actual option prices
    calls_otm["calc_iv"] = calls_otm.apply(
        lambda r: implied_vol(price, r["strike"], T, r["mid_price"], "call") or 0, axis=1
    )
    calls_otm["calc_delta"] = calls_otm.apply(
        lambda r: bs_call_delta(price, r["strike"], T, r["calc_iv"]) if r["calc_iv"] > 0 else 0,
        axis=1
    )

    # Select short call: closest delta to target
    valid = calls_otm[calls_otm["calc_delta"] > 0].copy()
    if valid.empty:
        error_exit("Could not compute delta for any strike — try during market hours")

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()].to_dict()

    short_strike = float(short_row["strike"])
    short_delta = round(float(short_row["calc_delta"]), 3)
    short_iv = round(float(short_row["calc_iv"]), 4)
    short_mid = float(short_row["mid_price"])
    short_bid = round(float(short_row.get("bid", 0) or 0), 2)
    short_ask = round(float(short_row.get("ask", 0) or 0), 2)
    price_source = classify_price_source(short_bid, short_ask)

    # Long call candidates pool — strikes above short strike
    long_pool = calls_otm[calls_otm["strike"] > short_strike].copy()
    if long_pool.empty:
        error_exit(f"No strikes available above short strike {short_strike}")

    # Iterate width candidates: requested first, then wider fallbacks.
    width_candidates = []
    for w in [spread_width_pct, 15.0, 20.0, 25.0]:
        if w not in width_candidates:
            width_candidates.append(w)

    widths_tried = []
    chosen = None
    for w in width_candidates:
        long_target = short_strike * (1 + w / 100)
        pool = long_pool.copy()
        pool["long_diff"] = (pool["strike"] - long_target).abs()
        candidate_row = pool.loc[pool["long_diff"].idxmin()].to_dict()
        c_long_strike = float(candidate_row["strike"])
        c_long_mid = float(candidate_row["mid_price"])
        cm = build_spread_metrics(short_mid, c_long_mid, short_strike, c_long_strike, short_delta, "call")
        widths_tried.append({
            "width_pct": w,
            "long_strike": c_long_strike,
            "net_credit": cm["net_credit"],
            "return_on_risk_pct": cm["return_on_risk_pct"],
        })
        if cm["spread_width"] <= 0 or cm["net_credit"] <= 0:
            continue
        if cm["return_on_risk_pct"] >= min_ror:
            chosen = (w, candidate_row, cm)
            break

    if chosen is None:
        error_exit(
            f"No width clears min_ror={min_ror}% at delta={short_delta} — try a higher delta or lower threshold",
            min_ror=min_ror,
            short_delta=short_delta,
            widths_tried=widths_tried,
        )

    width_used, long_row, m = chosen
    long_strike = float(long_row["strike"])
    long_mid = float(long_row["mid_price"])
    long_bid = round(float(long_row.get("bid", 0) or 0), 2)
    long_ask = round(float(long_row.get("ask", 0) or 0), 2)
    natural_credit = round(short_bid - long_ask, 2) if short_bid > 0 and long_ask > 0 else None

    result = {
        "ticker": ticker_sym,
        "price": round(price, 2),
        "prev_close": prev_close,
        "change_pct": change_pct,
        "expiry": expiry_str,
        "dte": dte,
        "short_call": {
            "strike": short_strike,
            "mid": short_mid,
            "delta": short_delta,
            "iv_pct": round(short_iv * 100, 1),
            "bid": short_bid,
            "ask": short_ask,
            "oi": _safe_int(short_row.get("openInterest")),
            "volume": _safe_int(short_row.get("volume")),
        },
        "long_call": {
            "strike": long_strike,
            "mid": long_mid,
            "bid": long_bid,
            "ask": long_ask,
            "oi": _safe_int(long_row.get("openInterest")),
            "volume": _safe_int(long_row.get("volume")),
        },
        "net_credit": m["net_credit"],
        "natural_credit": natural_credit,
        "spread_width": m["spread_width"],
        "max_profit": m["max_profit"],
        "max_loss": m["max_loss"],
        "breakeven": m["breakeven"],
        "return_on_risk_pct": m["return_on_risk_pct"],
        "prob_profit_pct": m["prob_profit_pct"],
        "min_ror_used": min_ror,
        "width_pct_requested": spread_width_pct,
        "width_pct_used": width_used,
        "widths_tried": widths_tried,
        "price_source": price_source,
        "delta_source": "bs_from_option_price",
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
