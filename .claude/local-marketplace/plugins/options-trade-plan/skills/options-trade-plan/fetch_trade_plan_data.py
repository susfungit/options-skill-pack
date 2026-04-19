#!/usr/bin/env python3
"""
Fetch all data required to produce an options trade plan for a ticker
and timeframe. Outputs a single JSON object to stdout with:

  - spot, OHLC, change, 50/200 SMA
  - resolved expiry + DTE + how it was resolved
  - ATM IV (30d proxy) + 30d realized HV + IV/HV ratio + verdict
  - IV rank / percentile proxy (best-effort, may be null)
  - expected move for the expiry window (1-SD)
  - classical pivot levels (P, R1, R2, S1, S2) from last completed session
  - earnings date + timing + whether it falls inside the expiry window
  - strike guidance bucket (target delta, suggested width, LEAPS warning)
  - three trade structures: bull_put, bear_call, iron_condor
    each with strikes, premiums, credit, max P/L, breakeven, delta, POP
  - chain-level stats: max pain, OI walls, put/call OI ratio
  - warnings (earnings-in-window, low IV, thin chain, etc.)

Usage:
  python3 fetch_trade_plan_data.py TICKER
    [--expiry YYYY-MM-DD] [--dte N] [--timeframe weekly|monthly|eom]

Timeframe resolution rules:
  --expiry takes priority
  --dte N             → nearest listed expiry at or beyond N DTE
  --timeframe weekly  → nearest Friday ≥ tomorrow
  --timeframe monthly → 3rd Friday of nearest upcoming month
  --timeframe eom     → last listed expiry on/before last trading day of month
  default             → nearest weekly Friday, flagged in `expiry_resolution`

All option premiums are labeled "bs_from_mid" in `delta_source`. The caller
must present them as model estimates, not live quotes.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import json
import math
import calendar as _cal
from datetime import date, datetime, timedelta

from _shared.options_lib import (
    _safe_int, error_exit, get_stock_price,
    bs_put_price, bs_call_price, bs_put_delta_abs, bs_call_delta,
    implied_vol, option_mid,
)

import logging
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")

try:
    import pandas as pd
except ImportError:
    error_exit("pandas not installed — run: pip3 install pandas")


# ── Expiry resolution ────────────────────────────────────────────────────────

def _third_friday(year, month):
    c = _cal.Calendar()
    fridays = [d for d in c.itermonthdates(year, month)
               if d.month == month and d.weekday() == 4]
    return fridays[2]


def _next_friday(today):
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _last_trading_day_of_month(today):
    last_day = _cal.monthrange(today.year, today.month)[1]
    d = date(today.year, today.month, last_day)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _nearest_listed(expirations, target, direction="ge"):
    """Pick closest listed expiry to target. direction='ge' prefers >= target."""
    today = date.today()
    parsed = [(e, datetime.strptime(e, "%Y-%m-%d").date()) for e in expirations]
    parsed = [(e, d) for e, d in parsed if d >= today]
    if not parsed:
        return None
    if direction == "ge":
        forward = [(e, d) for e, d in parsed if d >= target]
        if forward:
            return min(forward, key=lambda x: (x[1] - target).days)[0]
    return min(parsed, key=lambda x: abs((x[1] - target).days))[0]


def resolve_expiry(expirations, explicit_expiry, target_dte, timeframe):
    """Return (expiry_str, dte, how_resolved_text)."""
    if not expirations:
        return None, None, "no listed options"

    today = date.today()

    if explicit_expiry:
        if explicit_expiry in expirations:
            d = datetime.strptime(explicit_expiry, "%Y-%m-%d").date()
            return explicit_expiry, (d - today).days, f"explicit expiry {explicit_expiry}"
        nearest = _nearest_listed(expirations,
                                  datetime.strptime(explicit_expiry, "%Y-%m-%d").date(),
                                  direction="ge")
        if nearest:
            d = datetime.strptime(nearest, "%Y-%m-%d").date()
            return nearest, (d - today).days, (
                f"requested {explicit_expiry} not listed — using nearest {nearest}"
            )
        return None, None, f"no expiry near {explicit_expiry}"

    if target_dte is not None:
        target = today + timedelta(days=int(target_dte))
        chosen = _nearest_listed(expirations, target, direction="ge")
        if chosen:
            d = datetime.strptime(chosen, "%Y-%m-%d").date()
            return chosen, (d - today).days, (
                f"user requested {target_dte} DTE — chose nearest listed expiry {chosen} "
                f"({(d - today).days} DTE)"
            )

    tf = (timeframe or "").lower()
    if tf in ("weekly", "week", "weeklies"):
        target = _next_friday(today)
        chosen = _nearest_listed(expirations, target, direction="ge")
        if chosen:
            d = datetime.strptime(chosen, "%Y-%m-%d").date()
            return chosen, (d - today).days, (
                f"weekly → nearest Friday {target} → listed expiry {chosen}"
            )

    if tf in ("monthly", "month", "monthlies"):
        tf_m = _third_friday(today.year, today.month)
        if tf_m <= today:
            nm = today.month + 1
            ny = today.year + (1 if nm > 12 else 0)
            nm = 1 if nm > 12 else nm
            tf_m = _third_friday(ny, nm)
        chosen = _nearest_listed(expirations, tf_m, direction="ge")
        if chosen:
            d = datetime.strptime(chosen, "%Y-%m-%d").date()
            return chosen, (d - today).days, (
                f"monthly → 3rd Friday {tf_m} → listed expiry {chosen}"
            )

    if tf in ("eom", "end-of-month", "end_of_month"):
        tf_m = _last_trading_day_of_month(today)
        chosen = _nearest_listed(expirations, tf_m, direction="ge")
        if chosen:
            d = datetime.strptime(chosen, "%Y-%m-%d").date()
            return chosen, (d - today).days, (
                f"end-of-month → last trading day {tf_m} → listed expiry {chosen}"
            )

    # Default: nearest weekly Friday
    target = _next_friday(today)
    chosen = _nearest_listed(expirations, target, direction="ge")
    if chosen:
        d = datetime.strptime(chosen, "%Y-%m-%d").date()
        return chosen, (d - today).days, (
            f"no timeframe specified — defaulted to nearest weekly Friday {chosen}"
        )
    return None, None, "no usable expiry"


# ── Strike guidance by DTE ──────────────────────────────────────────────────

def strike_guidance(dte):
    """Return (bucket_label, target_delta, width, eligible_strategies, leaps_warning)."""
    if dte <= 7:
        return {
            "dte_bucket": "weekly (0-7 DTE)",
            "target_short_delta": 0.15,
            "recommended_width": 5,
            "eligible_strategies": [
                "bull put spread", "bear call spread", "iron condor"
            ],
            "naked_strangle_eligible": False,
            "leaps_warning": False,
            "gamma_warning": "gamma risk is highest at this DTE — defined-risk only",
        }
    if dte <= 21:
        return {
            "dte_bucket": "bi-weekly (8-21 DTE)",
            "target_short_delta": 0.18,
            "recommended_width": 7,
            "eligible_strategies": [
                "bull put spread", "bear call spread", "iron condor"
            ],
            "naked_strangle_eligible": False,
            "leaps_warning": False,
            "gamma_warning": "gamma still elevated — defined-risk only",
        }
    if dte <= 45:
        return {
            "dte_bucket": "monthly (22-45 DTE)",
            "target_short_delta": 0.22,
            "recommended_width": 10,
            "eligible_strategies": [
                "bull put spread", "bear call spread", "iron condor",
                "naked strangle (if IV rank > 50 and account approved)",
            ],
            "naked_strangle_eligible": True,
            "leaps_warning": False,
            "gamma_warning": None,
        }
    if dte <= 90:
        return {
            "dte_bucket": "extended (46-90 DTE)",
            "target_short_delta": 0.27,
            "recommended_width": 12,
            "eligible_strategies": [
                "bull put spread", "bear call spread", "iron condor",
                "diagonal", "calendar",
            ],
            "naked_strangle_eligible": True,
            "leaps_warning": False,
            "gamma_warning": None,
        }
    return {
        "dte_bucket": "LEAPS zone (>90 DTE)",
        "target_short_delta": 0.30,
        "recommended_width": 15,
        "eligible_strategies": [
            "diagonal (preferred)", "calendar (preferred)",
            "bull put spread", "bear call spread",
        ],
        "naked_strangle_eligible": False,
        "leaps_warning": (
            "Standard premium-selling weeklies/monthlies are suboptimal at >90 DTE. "
            "Theta decay is too slow. Recommend a diagonal or calendar instead."
        ),
        "gamma_warning": None,
    }


# ── Volatility helpers ──────────────────────────────────────────────────────

def realized_vol_annualized(close_series, window=30):
    """Annualized stdev of daily log returns over last `window` days."""
    if len(close_series) < window + 1:
        window = len(close_series) - 1
    if window < 2:
        return None
    log_ret = (close_series / close_series.shift(1)).apply(
        lambda x: math.log(x) if x and x > 0 else 0
    ).dropna()
    recent = log_ret.tail(window)
    if len(recent) < 2:
        return None
    sigma_daily = recent.std()
    return float(sigma_daily * math.sqrt(252))


def atm_iv_for_expiry(chain_puts, chain_calls, price, T):
    """Estimate ATM implied vol by averaging IV of nearest-to-ATM put and call."""
    ivs = []
    for df, opt_type in [(chain_calls, "call"), (chain_puts, "put")]:
        if df is None or df.empty:
            continue
        d = df.copy()
        d["_mid"] = d.apply(option_mid, axis=1)
        d = d[d["_mid"] > 0]
        if d.empty:
            continue
        d["_dist"] = (d["strike"] - price).abs()
        row = d.nsmallest(1, "_dist").iloc[0]
        iv = implied_vol(price, float(row["strike"]), T, float(row["_mid"]), opt_type)
        if iv and 0 < iv < 5:
            ivs.append(iv)
    if not ivs:
        return None
    return sum(ivs) / len(ivs)


# ── Strike selection ────────────────────────────────────────────────────────

def find_strike_near_delta(chain_df, price, T, target_delta, side, max_scan=60):
    """Search OTM strikes and return the row (as dict) whose BS delta is closest to target."""
    if side == "put":
        otm = chain_df[chain_df["strike"] < price].copy()
    else:
        otm = chain_df[chain_df["strike"] > price].copy()
    if otm.empty:
        return None
    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()
    if otm.empty:
        return None
    otm = otm.head(max_scan) if side == "call" else otm.tail(max_scan)

    results = []
    for _, r in otm.iterrows():
        iv = implied_vol(price, float(r["strike"]), T, float(r["mid_price"]), side)
        if not iv or iv <= 0:
            continue
        if side == "put":
            d = bs_put_delta_abs(price, float(r["strike"]), T, iv)
        else:
            d = bs_call_delta(price, float(r["strike"]), T, iv)
        results.append((r, iv, d))
    if not results:
        return None
    r, iv, d = min(results, key=lambda x: abs(x[2] - target_delta))
    out = r.to_dict()
    out["calc_iv"] = iv
    out["calc_delta"] = d
    return out


def find_wing(chain_df, short_strike, side, target_width):
    """Pick long-wing strike ~target_width away from short, same side."""
    if side == "put":
        candidates = chain_df[chain_df["strike"] < short_strike].copy()
        wing_target = short_strike - target_width
    else:
        candidates = chain_df[chain_df["strike"] > short_strike].copy()
        wing_target = short_strike + target_width
    if candidates.empty:
        return None
    candidates["mid_price"] = candidates.apply(option_mid, axis=1)
    candidates = candidates[candidates["mid_price"] > 0]
    if candidates.empty:
        return None
    candidates["_diff"] = (candidates["strike"] - wing_target).abs()
    return candidates.loc[candidates["_diff"].idxmin()].to_dict()


def build_spread_leg(short_row, long_row, side, T, price):
    """Package a vertical credit spread into a serialisable dict."""
    short_strike = float(short_row["strike"])
    long_strike = float(long_row["strike"])
    short_mid = float(short_row.get("mid_price") or option_mid(short_row))
    long_mid = float(long_row.get("mid_price") or option_mid(long_row))
    short_delta = float(short_row.get("calc_delta") or 0)
    short_iv = float(short_row.get("calc_iv") or 0)
    width = abs(short_strike - long_strike)
    net_credit = round(short_mid - long_mid, 2)
    max_profit = round(net_credit * 100, 2)
    max_loss = round((width - net_credit) * 100, 2) if width > 0 else 0.0
    breakeven = (short_strike - net_credit) if side == "put" else (short_strike + net_credit)
    pop = round((1 - short_delta) * 100, 1)
    return {
        "side": side,
        "short_strike": short_strike,
        "short_mid": round(short_mid, 2),
        "short_delta": round(short_delta, 3),
        "short_iv_pct": round(short_iv * 100, 1) if short_iv else None,
        "short_bid": round(float(short_row.get("bid", 0) or 0), 2),
        "short_ask": round(float(short_row.get("ask", 0) or 0), 2),
        "short_oi": _safe_int(short_row.get("openInterest")),
        "long_strike": long_strike,
        "long_mid": round(long_mid, 2),
        "long_bid": round(float(long_row.get("bid", 0) or 0), 2),
        "long_ask": round(float(long_row.get("ask", 0) or 0), 2),
        "long_oi": _safe_int(long_row.get("openInterest")),
        "width": round(width, 2),
        "net_credit": net_credit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": round(breakeven, 2),
        "prob_profit_pct": pop,
    }


# ── Chain-level stats ───────────────────────────────────────────────────────

def max_pain_calc(puts, calls):
    """Strike that minimises total intrinsic value of open interest."""
    strikes = sorted(set(puts["strike"]).union(set(calls["strike"])))
    best_strike, best_val = None, float("inf")
    for k in strikes:
        put_pain = ((k - puts["strike"]).clip(lower=0) * puts["openInterest"].fillna(0)).sum()
        call_pain = ((calls["strike"] - k).clip(lower=0) * calls["openInterest"].fillna(0)).sum()
        total = put_pain + call_pain
        if total < best_val:
            best_val, best_strike = total, k
    return float(best_strike) if best_strike is not None else None


def oi_wall(df):
    d = df.dropna(subset=["openInterest"])
    if d.empty:
        return None
    row = d.loc[d["openInterest"].idxmax()]
    return {"strike": float(row["strike"]), "oi": int(row["openInterest"])}


# ── Earnings ────────────────────────────────────────────────────────────────

def fetch_earnings(tk):
    """Best-effort earnings date fetch. Returns dict or None."""
    try:
        df = tk.get_earnings_dates(limit=8)
        if df is not None and not df.empty:
            today = pd.Timestamp(date.today()).tz_localize(None)
            future = df[df.index.tz_localize(None) >= today] if df.index.tz is not None else df[df.index >= today]
            if not future.empty:
                ts = future.index[-1] if future.index[-1] < future.index[0] else future.index[0]
                # The frame is usually sorted descending; pick the nearest future
                ts = min(
                    future.index.tz_localize(None) if future.index.tz is not None else future.index
                )
                ed = ts.date() if hasattr(ts, "date") else ts
                hour = ts.hour if hasattr(ts, "hour") else 0
                timing = "BMO" if hour < 12 else "AMC"
                return {"date": ed.isoformat(), "timing": timing, "source": "get_earnings_dates"}
    except Exception:
        pass
    try:
        cal = tk.calendar
        if cal is not None:
            ed = None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    ed = ed[0]
            elif hasattr(cal, "loc"):
                ed = cal.loc["Earnings Date"].iloc[0] if "Earnings Date" in cal.index else None
            if ed is not None:
                if hasattr(ed, "date"):
                    ed = ed.date()
                if isinstance(ed, date):
                    return {"date": ed.isoformat(), "timing": None, "source": "calendar"}
    except Exception:
        pass
    return None


# ── Main ────────────────────────────────────────────────────────────────────

def parse_flags(argv):
    argv = list(argv)
    out = {"expiry": None, "dte": None, "timeframe": None}
    for flag in ("--expiry", "--dte", "--timeframe"):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv):
                out[flag.lstrip("-")] = argv[idx + 1]
            argv = argv[:idx] + argv[idx + 2:]
    if out["dte"] is not None:
        try:
            out["dte"] = int(out["dte"])
        except ValueError:
            out["dte"] = None
    return argv, out


def main():
    if len(sys.argv) < 2:
        error_exit("Usage: fetch_trade_plan_data.py TICKER [--expiry YYYY-MM-DD] "
                   "[--dte N] [--timeframe weekly|monthly|eom]")

    argv, flags = parse_flags(sys.argv)
    ticker_sym = argv[1].upper()

    tk = yf.Ticker(ticker_sym)
    price, prev_close, change_pct = get_stock_price(tk, ticker_sym)

    # History for HV, SMAs, OHLC of last completed session
    hist = tk.history(period="1y")
    if hist.empty or len(hist) < 5:
        error_exit(f"Not enough price history for {ticker_sym}")
    closes = hist["Close"]
    sma_50 = round(float(closes.tail(50).mean()), 2) if len(closes) >= 50 else None
    sma_200 = round(float(closes.tail(200).mean()), 2) if len(closes) >= 200 else None
    hv_30 = realized_vol_annualized(closes, window=30)
    hv_252 = realized_vol_annualized(closes, window=min(252, len(closes) - 1))

    # Last completed session OHLC for pivot calculation
    last = hist.iloc[-1]
    ohlc_last = {
        "date": str(hist.index[-1].date()),
        "open": round(float(last["Open"]), 2),
        "high": round(float(last["High"]), 2),
        "low": round(float(last["Low"]), 2),
        "close": round(float(last["Close"]), 2),
        "volume": int(last["Volume"]) if not pd.isna(last["Volume"]) else None,
    }
    if len(hist) >= 2:
        prev = hist.iloc[-2]
        ohlc_prev = {
            "date": str(hist.index[-2].date()),
            "open": round(float(prev["Open"]), 2),
            "high": round(float(prev["High"]), 2),
            "low": round(float(prev["Low"]), 2),
            "close": round(float(prev["Close"]), 2),
            "volume": int(prev["Volume"]) if not pd.isna(prev["Volume"]) else None,
        }
    else:
        ohlc_prev = ohlc_last

    # Pivot from the last COMPLETED session (i.e. ohlc_prev)
    piv = ohlc_prev
    P = (piv["high"] + piv["low"] + piv["close"]) / 3
    R1 = 2 * P - piv["low"]
    R2 = P + (piv["high"] - piv["low"])
    S1 = 2 * P - piv["high"]
    S2 = P - (piv["high"] - piv["low"])
    pivot = {
        "source_session": piv["date"],
        "P": round(P, 2),
        "R1": round(R1, 2),
        "R2": round(R2, 2),
        "S1": round(S1, 2),
        "S2": round(S2, 2),
    }

    # Resolve expiry
    expirations = list(tk.options or [])
    if not expirations:
        error_exit(f"No options listed for {ticker_sym}")
    expiry_str, dte, how = resolve_expiry(
        expirations, flags["expiry"], flags["dte"], flags["timeframe"]
    )
    if expiry_str is None:
        error_exit(f"Could not resolve expiry for {ticker_sym}")

    # Option chain at resolved expiry
    chain = tk.option_chain(expiry_str)
    puts, calls = chain.puts.copy(), chain.calls.copy()

    T = max(dte, 0) / 365.0 if dte > 0 else 1 / 365.0
    T_safe = max(T, 1 / 365.0)

    # ATM IV
    atm_iv = atm_iv_for_expiry(puts, calls, price, T_safe)
    iv_hv_ratio = None
    iv_hv_verdict = None
    if atm_iv and hv_30:
        iv_hv_ratio = round(atm_iv / hv_30, 2)
        if iv_hv_ratio > 1.20:
            iv_hv_verdict = "IV is rich relative to realized — favors selling premium"
        elif iv_hv_ratio >= 0.85:
            iv_hv_verdict = "IV and realized are roughly fair — neutral stance"
        else:
            iv_hv_verdict = "IV is below realized — premium is thin, avoid selling vol"

    # Proxy IV rank/percentile using HV-history bucket
    iv_rank_pct = None
    iv_percentile_pct = None
    if atm_iv and len(closes) > 60:
        window_hvs = []
        log_ret = (closes / closes.shift(1)).apply(
            lambda x: math.log(x) if x and x > 0 else 0
        ).dropna()
        for i in range(30, len(log_ret)):
            sigma = log_ret.iloc[i - 30:i].std() * math.sqrt(252)
            if sigma and not math.isnan(sigma):
                window_hvs.append(float(sigma))
        if window_hvs:
            hv_min = min(window_hvs)
            hv_max = max(window_hvs)
            if hv_max > hv_min:
                iv_rank_pct = round((atm_iv - hv_min) / (hv_max - hv_min) * 100, 1)
                iv_rank_pct = max(0.0, min(100.0, iv_rank_pct))
            below = sum(1 for h in window_hvs if h < atm_iv)
            iv_percentile_pct = round(below / len(window_hvs) * 100, 1)

    # Expected move (1-SD)
    if atm_iv and dte > 0:
        em_dollar = round(price * atm_iv * math.sqrt(dte / 365.0), 2)
        em_pct = round(em_dollar / price * 100, 2)
        em_low = round(price - em_dollar, 2)
        em_high = round(price + em_dollar, 2)
    else:
        em_dollar = em_pct = em_low = em_high = None

    # Strike guidance
    guidance = strike_guidance(dte)
    target_delta = guidance["target_short_delta"]
    width = guidance["recommended_width"]

    # Three trade structures
    short_put = find_strike_near_delta(puts, price, T_safe, target_delta, "put")
    short_call = find_strike_near_delta(calls, price, T_safe, target_delta, "call")
    trades = {}
    warnings_out = []

    if short_put:
        long_put = find_wing(puts, float(short_put["strike"]), "put", width)
        if long_put:
            trades["bull_put"] = build_spread_leg(short_put, long_put, "put", T_safe, price)
        else:
            warnings_out.append("could not find a usable long-put wing")
    else:
        warnings_out.append("could not find a short put near target delta")

    if short_call:
        long_call = find_wing(calls, float(short_call["strike"]), "call", width)
        if long_call:
            trades["bear_call"] = build_spread_leg(short_call, long_call, "call", T_safe, price)
        else:
            warnings_out.append("could not find a usable long-call wing")
    else:
        warnings_out.append("could not find a short call near target delta")

    if "bull_put" in trades and "bear_call" in trades:
        bp, bc = trades["bull_put"], trades["bear_call"]
        total_credit = round(bp["net_credit"] + bc["net_credit"], 2)
        wider = max(bp["width"], bc["width"])
        max_profit_ic = round(total_credit * 100, 2)
        max_loss_ic = round((wider - total_credit) * 100, 2) if wider > 0 else 0.0
        pop_ic = round((1 - bp["short_delta"] - bc["short_delta"]) * 100, 1)
        trades["iron_condor"] = {
            "put_side": bp,
            "call_side": bc,
            "total_credit": total_credit,
            "max_profit": max_profit_ic,
            "max_loss": max_loss_ic,
            "breakeven_low": round(bp["short_strike"] - total_credit, 2),
            "breakeven_high": round(bc["short_strike"] + total_credit, 2),
            "profit_zone": f"${round(bp['short_strike'] - total_credit, 2)} – ${round(bc['short_strike'] + total_credit, 2)}",
            "prob_profit_pct": pop_ic,
            "width": round(wider, 2),
        }

    # Chain-level stats
    chain_summary = {
        "max_pain": max_pain_calc(puts, calls),
        "put_oi_wall": oi_wall(puts),
        "call_oi_wall": oi_wall(calls),
        "total_put_oi": int(puts["openInterest"].fillna(0).sum()),
        "total_call_oi": int(calls["openInterest"].fillna(0).sum()),
    }
    if chain_summary["total_call_oi"]:
        chain_summary["put_call_oi_ratio"] = round(
            chain_summary["total_put_oi"] / chain_summary["total_call_oi"], 2
        )
    else:
        chain_summary["put_call_oi_ratio"] = None

    # Earnings
    earnings = fetch_earnings(tk)
    earnings_info = None
    if earnings and earnings.get("date"):
        ed = datetime.strptime(earnings["date"], "%Y-%m-%d").date()
        today = date.today()
        exp_d = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        days_to_earn = (ed - today).days
        within_window = today <= ed <= exp_d
        days_from_expiry = (ed - exp_d).days
        earnings_info = {
            "date": earnings["date"],
            "timing": earnings.get("timing"),
            "days_to_earnings": days_to_earn,
            "within_expiry_window": within_window,
            "days_from_expiry": days_from_expiry,
            "source": earnings.get("source"),
        }
        if within_window:
            warnings_out.append(
                f"EARNINGS within expiry window (on {earnings['date']}, {days_to_earn} days out) — "
                f"consider widening shorts by 1.5× earnings EM or avoiding premium selling outright"
            )
        elif -7 <= days_from_expiry <= 14:
            warnings_out.append(
                f"earnings on {earnings['date']} ({'after' if days_from_expiry > 0 else 'before'} "
                f"expiry by {abs(days_from_expiry)} days) — pre-earnings IV may be inflating premium"
            )

    if iv_rank_pct is not None and iv_rank_pct < 25:
        warnings_out.append(f"IV rank is low ({iv_rank_pct:.0f}) — premium is thin for selling vol")
    if guidance.get("leaps_warning"):
        warnings_out.append(guidance["leaps_warning"])

    result = {
        "ticker": ticker_sym,
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "price": price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "ohlc_last_session": ohlc_last,
        "ohlc_prev_session": ohlc_prev,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "hv_30d_pct": round(hv_30 * 100, 1) if hv_30 else None,
        "hv_252d_pct": round(hv_252 * 100, 1) if hv_252 else None,
        "atm_iv_pct": round(atm_iv * 100, 1) if atm_iv else None,
        "iv_hv_ratio": iv_hv_ratio,
        "iv_hv_verdict": iv_hv_verdict,
        "iv_rank_pct_proxy": iv_rank_pct,
        "iv_percentile_pct_proxy": iv_percentile_pct,
        "expected_move": {
            "dollar": em_dollar,
            "pct": em_pct,
            "low": em_low,
            "high": em_high,
            "formula": "price × ATM IV × sqrt(DTE / 365)",
        },
        "pivot": pivot,
        "expiry": expiry_str,
        "dte": dte,
        "expiry_resolution": how,
        "earnings": earnings_info,
        "strike_guidance": guidance,
        "trades": trades,
        "chain_summary": chain_summary,
        "warnings": warnings_out,
        "data_source": "yfinance",
        "delta_source": "bs_from_mid (model estimate)",
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
