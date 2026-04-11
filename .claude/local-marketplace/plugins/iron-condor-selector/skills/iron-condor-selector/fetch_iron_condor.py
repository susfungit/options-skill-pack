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

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int, error_exit, get_stock_price, parse_expiry_flag,
    resolve_selector_expiry, select_strike_by_delta, classify_price_source,
    build_spread_metrics, option_mid,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


def select_wing(valid_df, otm_df, short_strike, short_mid, side="put"):
    """Select long (wing) strike further OTM than short strike, ~$5 wide."""
    if side == "put":
        candidates = valid_df[valid_df["strike"] < short_strike].copy()
        wing_target = short_strike - 5
    else:
        candidates = valid_df[valid_df["strike"] > short_strike].copy()
        wing_target = short_strike + 5

    if candidates.empty:
        # Fallback: use full OTM chain (includes strikes without computable delta)
        if side == "put":
            candidates = otm_df[otm_df["strike"] < short_strike].copy()
        else:
            candidates = otm_df[otm_df["strike"] > short_strike].copy()
        if candidates.empty:
            return None

    # Filter to wings that cost less than the short (ensures positive leg credit)
    affordable = candidates[candidates["mid_price"] < short_mid]
    if not affordable.empty:
        candidates = affordable

    candidates["wing_diff"] = (candidates["strike"] - wing_target).abs()
    wing_row = candidates.loc[candidates["wing_diff"].idxmin()]
    return wing_row.to_dict()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        error_exit("Usage: fetch_iron_condor.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]")

    argv, explicit_expiry = parse_expiry_flag(sys.argv)

    ticker_sym = argv[1].upper()
    target_delta = float(argv[2]) if len(argv) > 2 else 0.16
    dte_min = int(argv[3]) if len(argv) > 3 else 35
    dte_max = int(argv[4]) if len(argv) > 4 else 45

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

    expiry_str, dte, chain = None, None, None
    for exp_str, exp_dte in sorted_expiries[start_idx:]:
        ch = tk.option_chain(exp_str)
        puts_otm = ch.puts[ch.puts["strike"] < price]
        calls_otm = ch.calls[ch.calls["strike"] > price]
        if len(puts_otm) >= 4 and len(calls_otm) >= 4:
            expiry_str, dte, chain = exp_str, exp_dte, ch
            break

    if chain is None:
        error_exit("No expiry with enough OTM strikes — chain too thin")

    T = dte / 365.0

    # ── Put side ──────────────────────────────────────────────────────────────
    short_put_row, put_valid, put_otm = select_strike_by_delta(chain.puts, price, T, target_delta, "put")
    if short_put_row is None:
        error_exit("No usable OTM put strikes — try during market hours")

    short_put_strike = float(short_put_row["strike"])
    short_put_delta = round(float(short_put_row["calc_delta"]), 3)
    short_put_iv = round(float(short_put_row["calc_iv"]), 4)
    short_put_mid = float(short_put_row["mid_price"])
    short_put_bid = round(float(short_put_row.get("bid", 0) or 0), 2)
    short_put_ask = round(float(short_put_row.get("ask", 0) or 0), 2)

    long_put_row = select_wing(put_valid, put_otm, short_put_strike, short_put_mid, "put")
    if long_put_row is None:
        error_exit("No valid put wing strike found")
    long_put_strike = float(long_put_row["strike"])
    long_put_mid = float(long_put_row["mid_price"])
    long_put_bid = round(float(long_put_row.get("bid", 0) or 0), 2)
    long_put_ask = round(float(long_put_row.get("ask", 0) or 0), 2)

    pm = build_spread_metrics(short_put_mid, long_put_mid, short_put_strike, long_put_strike, short_put_delta, "put")
    put_credit = pm["net_credit"]
    put_natural = round(short_put_bid - long_put_ask, 2) if short_put_bid > 0 and long_put_ask > 0 else None
    put_width = pm["spread_width"]

    # ── Call side ─────────────────────────────────────────────────────────────
    short_call_row, call_valid, call_otm = select_strike_by_delta(chain.calls, price, T, target_delta, "call")
    if short_call_row is None:
        error_exit("No usable OTM call strikes — try during market hours")

    short_call_strike = float(short_call_row["strike"])
    short_call_delta = round(float(short_call_row["calc_delta"]), 3)
    short_call_iv = round(float(short_call_row["calc_iv"]), 4)
    short_call_mid = float(short_call_row["mid_price"])
    short_call_bid = round(float(short_call_row.get("bid", 0) or 0), 2)
    short_call_ask = round(float(short_call_row.get("ask", 0) or 0), 2)

    long_call_row = select_wing(call_valid, call_otm, short_call_strike, short_call_mid, "call")
    if long_call_row is None:
        error_exit("No valid call wing strike found")
    long_call_strike = float(long_call_row["strike"])
    long_call_mid = float(long_call_row["mid_price"])
    long_call_bid = round(float(long_call_row.get("bid", 0) or 0), 2)
    long_call_ask = round(float(long_call_row.get("ask", 0) or 0), 2)

    cm = build_spread_metrics(short_call_mid, long_call_mid, short_call_strike, long_call_strike, short_call_delta, "call")
    call_credit = cm["net_credit"]
    call_natural = round(short_call_bid - long_call_ask, 2) if short_call_bid > 0 and long_call_ask > 0 else None
    call_width = cm["spread_width"]

    # ── Combined metrics ──────────────────────────────────────────────────────
    total_credit = round(put_credit + call_credit, 2)
    total_natural_credit = round(put_natural + call_natural, 2) if put_natural is not None and call_natural is not None else None
    wider_width = max(put_width, call_width)

    if wider_width <= 0 or total_credit <= 0:
        error_exit(f"Degenerate iron condor: credit={total_credit}, widths=({put_width}, {call_width})")

    max_profit = round(total_credit * 100, 2)
    max_loss = round((wider_width - total_credit) * 100, 2)
    breakeven_low = round(short_put_strike - total_credit, 2)
    breakeven_high = round(short_call_strike + total_credit, 2)
    ror = round(total_credit / (wider_width - total_credit) * 100, 1)
    pop = round((1 - short_put_delta - short_call_delta) * 100, 1)

    price_source = classify_price_source(short_put_bid, short_put_ask)

    result = {
        "ticker": ticker_sym,
        "price": round(price, 2),
        "prev_close": prev_close,
        "change_pct": change_pct,
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
                "oi": _safe_int(short_put_row.get("openInterest")),
                "volume": _safe_int(short_put_row.get("volume")),
            },
            "long_put": {
                "strike": long_put_strike,
                "mid": long_put_mid,
                "bid": long_put_bid,
                "ask": long_put_ask,
                "oi": _safe_int(long_put_row.get("openInterest")),
                "volume": _safe_int(long_put_row.get("volume")),
            },
            "credit": put_credit,
            "natural_credit": put_natural,
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
                "oi": _safe_int(short_call_row.get("openInterest")),
                "volume": _safe_int(short_call_row.get("volume")),
            },
            "long_call": {
                "strike": long_call_strike,
                "mid": long_call_mid,
                "bid": long_call_bid,
                "ask": long_call_ask,
                "oi": _safe_int(long_call_row.get("openInterest")),
                "volume": _safe_int(long_call_row.get("volume")),
            },
            "credit": call_credit,
            "natural_credit": call_natural,
            "width": call_width,
        },
        "total_credit": total_credit,
        "total_natural_credit": total_natural_credit,
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
