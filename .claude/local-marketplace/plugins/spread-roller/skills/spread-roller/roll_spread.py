#!/usr/bin/env python3
"""
Find roll targets for a bull put spread or iron condor side.

Usage (bull put spread — 5 positional args after ticker):
  python3 roll_spread.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY [TARGET_DELTA]

Usage (iron condor — 8 positional args after ticker):
  python3 roll_spread.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY ROLL_SIDE [TARGET_DELTA]

  ROLL_SIDE    : "put" or "call" — which side of the condor to roll
  TARGET_DELTA : delta target for aggressive diagonal (default: 0.20 put, 0.16 condor)

Outputs JSON to stdout. Errors output JSON with an "error" key.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
from datetime import date, datetime, timedelta

from _shared.options_lib import (
    error_exit, get_stock_price, select_strike_by_delta, classify_price_source,
    compute_iv_delta, option_mid, implied_vol,
    bs_put_delta_abs, bs_call_delta,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")


def find_future_expiries(expirations, current_expiry_str, offsets_days=(14, 28, 42)):
    """Find up to 3 future expiries at roughly the given day offsets past current expiry."""
    current_exp = datetime.strptime(current_expiry_str, "%Y-%m-%d").date()
    results = []
    used = set()
    for offset in offsets_days:
        target = current_exp + timedelta(days=offset)
        best, best_diff = None, float("inf")
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if exp_date <= current_exp:
                continue
            diff = abs((exp_date - target).days)
            if diff < best_diff and exp_str not in used:
                best_diff, best = diff, exp_str
        if best is not None and best_diff <= 10:
            used.add(best)
            results.append(best)
    return results


def find_defensive_strike(df, price, T, current_short_strike, side="put"):
    """Find the next strike further OTM from the current short strike."""
    df = df.copy()
    df["mid_price"] = df.apply(option_mid, axis=1)
    df = df[df["mid_price"] > 0]

    if side == "put":
        candidates = df[(df["strike"] < current_short_strike) & (df["strike"] < price)]
        if candidates.empty:
            return None
        further = candidates[candidates["strike"] < current_short_strike].sort_values("strike", ascending=False)
        if further.empty:
            return None
        row = further.iloc[0]
    else:
        candidates = df[(df["strike"] > current_short_strike) & (df["strike"] > price)]
        if candidates.empty:
            return None
        further = candidates[candidates["strike"] > current_short_strike].sort_values("strike", ascending=True)
        if further.empty:
            return None
        row = further.iloc[0]

    return row.to_dict()


# ── Core logic ────────────────────────────────────────────────────────────────

def price_close(tk, expiry_str, short_strike, long_strike, side="put"):
    """Price the cost to close the current spread (buy back short, sell long)."""
    available = tk.options
    use_expiry = expiry_str
    if expiry_str not in available:
        # Find nearest within ±3 days
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        for exp in available:
            if abs((datetime.strptime(exp, "%Y-%m-%d").date() - exp_date).days) <= 3:
                use_expiry = exp
                break
        else:
            return None

    chain = tk.option_chain(use_expiry)
    opts = chain.puts if side == "put" else chain.calls
    opts = opts.copy()
    opts["mid_price"] = opts.apply(option_mid, axis=1)

    # Short leg (we need to buy it back)
    short_rows = opts[opts["strike"] == short_strike]
    if short_rows.empty:
        opts["_sd"] = (opts["strike"] - short_strike).abs()
        short_rows = opts.nsmallest(1, "_sd")
    short_mid = float(short_rows.iloc[0]["mid_price"])
    short_bid = round(float(short_rows.iloc[0].get("bid", 0) or 0), 2)
    short_ask = round(float(short_rows.iloc[0].get("ask", 0) or 0), 2)

    # Long leg (we sell it)
    long_rows = opts[opts["strike"] == long_strike]
    if long_rows.empty:
        opts["_ld"] = (opts["strike"] - long_strike).abs()
        long_rows = opts.nsmallest(1, "_ld")
    long_mid = float(long_rows.iloc[0]["mid_price"])
    long_bid = round(float(long_rows.iloc[0].get("bid", 0) or 0), 2)
    long_ask = round(float(long_rows.iloc[0].get("ask", 0) or 0), 2)

    # Debit to close = buy back short - sell long
    net_debit = round(short_mid - long_mid, 2)

    return {
        "short_leg_mid": short_mid,
        "short_leg_bid": short_bid,
        "short_leg_ask": short_ask,
        "long_leg_mid": long_mid,
        "long_leg_bid": long_bid,
        "long_leg_ask": long_ask,
        "net_debit_to_close": net_debit,
    }


def evaluate_roll(tk, price, new_expiry, new_short_strike, spread_width, side, close_cost):
    """Evaluate a single roll candidate: new credit, net roll, breakeven, PoP, etc."""
    new_dte = (datetime.strptime(new_expiry, "%Y-%m-%d").date() - date.today()).days
    T = max(new_dte / 365.0, 0.001)

    chain = tk.option_chain(new_expiry)
    opts = chain.puts if side == "put" else chain.calls
    opts = opts.copy()
    opts["mid_price"] = opts.apply(option_mid, axis=1)

    # New short leg
    short_rows = opts[opts["strike"] == new_short_strike]
    if short_rows.empty:
        opts["_sd"] = (opts["strike"] - new_short_strike).abs()
        short_rows = opts.nsmallest(1, "_sd")
    if short_rows.iloc[0]["mid_price"] <= 0:
        return None

    new_short_mid = float(short_rows.iloc[0]["mid_price"])
    new_short_bid = round(float(short_rows.iloc[0].get("bid", 0) or 0), 2)
    new_short_ask = round(float(short_rows.iloc[0].get("ask", 0) or 0), 2)
    actual_short_strike = float(short_rows.iloc[0]["strike"])

    # Compute IV and delta for new short
    iv_raw, delta = compute_iv_delta(price, actual_short_strike, T, new_short_mid, side)
    iv_pct = round(iv_raw * 100, 1) if iv_raw else None
    delta = round(delta, 3) if delta else None

    # New long leg: maintain spread width
    if side == "put":
        new_long_strike = actual_short_strike - spread_width
    else:
        new_long_strike = actual_short_strike + spread_width

    long_rows = opts[opts["strike"] == new_long_strike]
    if long_rows.empty:
        opts["_ld"] = (opts["strike"] - new_long_strike).abs()
        long_rows = opts.nsmallest(1, "_ld")
    new_long_mid = float(long_rows.iloc[0]["mid_price"])
    actual_long_strike = float(long_rows.iloc[0]["strike"])

    # New credit from opening the new spread
    new_credit = round(new_short_mid - new_long_mid, 2)
    if new_credit <= 0:
        return None

    # Net roll = new credit - cost to close old
    net_roll = round(new_credit - close_cost, 2)

    # Actual width may differ if strike snapping occurred
    if side == "put":
        actual_width = round(actual_short_strike - actual_long_strike, 2)
    else:
        actual_width = round(actual_long_strike - actual_short_strike, 2)

    max_profit = round(new_credit * 100, 2)
    max_loss = round((actual_width - new_credit) * 100, 2) if actual_width > new_credit else 0.0

    if side == "put":
        breakeven = round(actual_short_strike - new_credit, 2)
    else:
        breakeven = round(actual_short_strike + new_credit, 2)

    ror = round(new_credit / (actual_width - new_credit) * 100, 1) if actual_width > new_credit else 0.0
    pop = round((1 - delta) * 100, 1) if delta else None

    if net_roll > 0.01:
        verdict = "credit"
    elif net_roll < -0.01:
        verdict = "debit"
    else:
        verdict = "even"

    return {
        "new_expiry": new_expiry,
        "new_dte": new_dte,
        "new_short_strike": actual_short_strike,
        "new_long_strike": actual_long_strike,
        "new_spread_width": actual_width,
        "new_short_mid": new_short_mid,
        "new_short_bid": new_short_bid,
        "new_short_ask": new_short_ask,
        "new_long_mid": new_long_mid,
        "new_credit": new_credit,
        "net_roll_credit": net_roll,
        "new_breakeven": breakeven,
        "new_max_profit": max_profit,
        "new_max_loss": max_loss,
        "new_return_on_risk_pct": ror,
        "new_prob_profit_pct": pop,
        "new_short_delta": delta,
        "new_short_iv_pct": iv_pct,
        "roll_verdict": verdict,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    argc = len(sys.argv)

    # Detect strategy from arg count
    # Bull put: TICKER SHORT LONG CREDIT EXPIRY [DELTA] -> 6-7 args
    # Iron condor: TICKER SP LP SC LC CREDIT EXPIRY SIDE [DELTA] -> 9-10 args
    if argc < 6:
        error_exit(
            "Usage:\n"
            "  Bull put:    roll_spread.py TICKER SHORT LONG NET_CREDIT EXPIRY [TARGET_DELTA]\n"
            "  Iron condor: roll_spread.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY ROLL_SIDE [TARGET_DELTA]"
        )

    if argc <= 7:
        # Bull put spread mode
        strategy = "bull-put-spread"
        ticker_sym = sys.argv[1].upper()
        short_strike = float(sys.argv[2])
        long_strike = float(sys.argv[3])
        net_credit = float(sys.argv[4])
        expiry_str = sys.argv[5]
        target_delta = float(sys.argv[6]) if argc > 6 else 0.20
        roll_side = "put"
        spread_width = round(short_strike - long_strike, 2)
    else:
        # Iron condor mode — roll one side
        strategy = "iron-condor"
        ticker_sym = sys.argv[1].upper()
        short_put = float(sys.argv[2])
        long_put = float(sys.argv[3])
        short_call = float(sys.argv[4])
        long_call = float(sys.argv[5])
        net_credit = float(sys.argv[6])
        expiry_str = sys.argv[7]
        roll_side = sys.argv[8].lower()
        target_delta = float(sys.argv[9]) if argc > 9 else 0.16

        if roll_side not in ("put", "call"):
            error_exit(f"ROLL_SIDE must be 'put' or 'call', got '{roll_side}'")

        if roll_side == "put":
            short_strike = short_put
            long_strike = long_put
            spread_width = round(short_put - long_put, 2)
        else:
            short_strike = short_call
            long_strike = long_call
            spread_width = round(long_call - short_call, 2)

    # Validate expiry
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        error_exit(f"Invalid expiry format: {expiry_str} — use YYYY-MM-DD")

    today = date.today()
    dte_remaining = (expiry_date - today).days

    # Fetch stock data
    tk = yf.Ticker(ticker_sym)
    price = get_stock_price(tk, ticker_sym)

    # Price the close of current position
    close_data = price_close(tk, expiry_str, short_strike, long_strike, roll_side)
    if close_data is None:
        error_exit(f"Cannot price current position — expiry {expiry_str} not found in chain")

    realized_loss = round(net_credit - close_data["net_debit_to_close"], 2)

    # Find future expiries
    expirations = tk.options
    if not expirations:
        error_exit(f"No options listed for {ticker_sym}")

    future_expiries = find_future_expiries(expirations, expiry_str)
    if not future_expiries:
        # Try with shorter offsets if nothing found
        future_expiries = find_future_expiries(expirations, expiry_str, offsets_days=(7, 14, 21))
    if not future_expiries:
        error_exit("No future expiries available for rolling")

    # Evaluate roll candidates
    candidates = []
    close_debit = close_data["net_debit_to_close"]

    for new_expiry in future_expiries:
        new_dte = (datetime.strptime(new_expiry, "%Y-%m-%d").date() - today).days
        T = max(new_dte / 365.0, 0.001)

        # 1. Calendar roll — same strikes
        cal = evaluate_roll(tk, price, new_expiry, short_strike, spread_width, roll_side, close_debit)
        if cal:
            cal["type"] = "calendar"
            candidates.append(cal)

        # 2. Defensive diagonal — next strike further OTM
        try:
            chain = tk.option_chain(new_expiry)
            opts = chain.puts if roll_side == "put" else chain.calls
            def_row = find_defensive_strike(opts, price, T, short_strike, roll_side)
            if def_row:
                def_strike = float(def_row["strike"])
                if def_strike != short_strike:
                    diag = evaluate_roll(tk, price, new_expiry, def_strike, spread_width, roll_side, close_debit)
                    if diag:
                        diag["type"] = "defensive_diagonal"
                        candidates.append(diag)
        except Exception:
            pass

        # 3. Aggressive diagonal — reset to target delta
        try:
            chain = tk.option_chain(new_expiry)
            opts = chain.puts if roll_side == "put" else chain.calls
            delta_row, _, _ = select_strike_by_delta(opts, price, T, target_delta, roll_side)
            if delta_row:
                agg_strike = float(delta_row["strike"])
                if agg_strike != short_strike:
                    agg = evaluate_roll(tk, price, new_expiry, agg_strike, spread_width, roll_side, close_debit)
                    if agg:
                        agg["type"] = "aggressive_diagonal"
                        candidates.append(agg)
        except Exception:
            pass

    if not candidates:
        error_exit("No viable roll candidates found — all returned zero or negative credit")

    # Rank by net roll credit (best first)
    candidates.sort(key=lambda c: c["net_roll_credit"], reverse=True)
    for i, c in enumerate(candidates):
        c["rank"] = i + 1

    price_source = classify_price_source(close_data["short_leg_bid"], close_data["short_leg_ask"])

    # Build current position summary
    current_position = {
        "strategy": strategy,
        "side": roll_side,
        "short_strike": short_strike,
        "long_strike": long_strike,
        "spread_width": spread_width,
        "original_credit": net_credit,
        "expiry": expiry_str,
        "dte_remaining": dte_remaining,
    }

    close_cost = {
        "short_leg_mid": close_data["short_leg_mid"],
        "long_leg_mid": close_data["long_leg_mid"],
        "net_debit_to_close": close_data["net_debit_to_close"],
        "realized_pnl": realized_loss,
    }

    result = {
        "ticker": ticker_sym,
        "stock_price": price,
        "current_position": current_position,
        "close_cost": close_cost,
        "roll_candidates": candidates,
        "ranking_method": "net_roll_credit_descending",
        "price_source": price_source,
        "data_source": "yfinance",
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
