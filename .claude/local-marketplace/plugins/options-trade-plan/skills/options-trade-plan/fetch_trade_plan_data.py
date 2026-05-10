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


# ── HTML rendering (pre-built fragments — keeps the model out of structural HTML) ──

_BULL_KICKER = "Bullish / stable tape"
_NEUTRAL_KICKER = "Neutral / range-bound tape"
_BEAR_KICKER = "Bearish / rejection tape"

_MGMT_TIMELINE = {
    "weekly (0-7 DTE)":
        "Take 50% profit by day 3. Close Thursday if the short strike is threatened. Hard stop at 2× credit.",
    "bi-weekly (8-21 DTE)":
        "Take 50% profit at 50% of time elapsed. Close at 7 DTE remaining. Hard stop at 2× credit.",
    "monthly (22-45 DTE)":
        "Take 50% profit or close at 21 DTE remaining, whichever comes first. Hard stop at 2× credit.",
    "extended (46-90 DTE)":
        "Take 50% profit. Close at 30 DTE remaining. Hard stop at 2× credit.",
    "LEAPS zone (>90 DTE)":
        "Diagonal/calendar preferred at this DTE. If holding the spread: take 50% profit, close at 30 DTE remaining. Hard stop at 2× credit.",
}

_RISK_BUDGET = {
    "bull_put": 0.0035,
    "bear_call": 0.0035,
    "iron_condor": 0.0025,
}


def _fmt_money(x, decimals=2):
    if x is None:
        return "—"
    try:
        return f"${float(x):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(x, decimals=1):
    if x is None:
        return "—"
    try:
        return f"{float(x):.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _strategy_label(dte):
    if dte is None:
        return "Credit Spread Framework"
    if dte <= 7:
        return "Weekly Credit Spread Framework"
    if dte <= 21:
        return "Bi-Weekly Credit Spread Framework"
    if dte <= 45:
        return "Monthly Credit Spread Framework"
    if dte <= 90:
        return "Extended-Dated Spread Framework"
    return "LEAPS-Zone Framework"


def _pretty_expiry(expiry_str):
    try:
        d = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return d.strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return expiry_str or "—"


def _render_levels_rows(pivot, sma_50, sma_200, ohlc_prev):
    rows = []
    src = pivot.get("source_session", "prev session")
    rows.append(f'<tr><td>R2</td><td class="num">${pivot["R2"]:.2f}</td><td>Pivot resistance 2 ({src})</td></tr>')
    rows.append(f'<tr><td>R1</td><td class="num">${pivot["R1"]:.2f}</td><td>Pivot resistance 1 ({src})</td></tr>')
    rows.append(f'<tr class="highlight"><td>Pivot</td><td class="num">${pivot["P"]:.2f}</td><td>Classical pivot from {src} OHLC</td></tr>')
    rows.append(f'<tr><td>S1</td><td class="num">${pivot["S1"]:.2f}</td><td>Pivot support 1 ({src})</td></tr>')
    rows.append(f'<tr><td>S2</td><td class="num">${pivot["S2"]:.2f}</td><td>Pivot support 2 ({src})</td></tr>')
    if sma_50 is not None:
        rows.append(f'<tr><td>SMA 50</td><td class="num">${sma_50:.2f}</td><td>50-day simple moving average</td></tr>')
    if sma_200 is not None:
        rows.append(f'<tr><td>SMA 200</td><td class="num">${sma_200:.2f}</td><td>200-day simple moving average</td></tr>')
    if ohlc_prev:
        rows.append(
            f'<tr><td>Prev close</td><td class="num">${ohlc_prev["close"]:.2f}</td>'
            f'<td>Last completed session ({ohlc_prev["date"]})</td></tr>'
        )
    return "\n".join(rows)


def _render_trade_summary_rows(trades):
    rows = []
    if "bull_put" in trades:
        bp = trades["bull_put"]
        rows.append(
            '<tr>'
            '<td class="tag tag-bull">Bullish / stable</td>'
            f'<td>Bull put {bp["short_strike"]:.0f}/{bp["long_strike"]:.0f}</td>'
            f'<td class="num">${bp["net_credit"]:.2f}</td>'
            f'<td class="num">${bp["max_profit"]:.0f}</td>'
            f'<td class="num">${bp["max_loss"]:.0f}</td>'
            f'<td class="num">{bp["prob_profit_pct"]:.0f}%</td>'
            '</tr>'
        )
    if "iron_condor" in trades:
        ic = trades["iron_condor"]
        bp = ic["put_side"]
        bc = ic["call_side"]
        rows.append(
            '<tr>'
            '<td class="tag tag-neutral">Neutral / range</td>'
            f'<td>IC {bp["long_strike"]:.0f}/{bp["short_strike"]:.0f} – {bc["short_strike"]:.0f}/{bc["long_strike"]:.0f}</td>'
            f'<td class="num">${ic["total_credit"]:.2f}</td>'
            f'<td class="num">${ic["max_profit"]:.0f}</td>'
            f'<td class="num">${ic["max_loss"]:.0f}</td>'
            f'<td class="num">{ic["prob_profit_pct"]:.0f}%</td>'
            '</tr>'
        )
    if "bear_call" in trades:
        bc = trades["bear_call"]
        rows.append(
            '<tr>'
            '<td class="tag tag-bear">Bearish / rejection</td>'
            f'<td>Bear call {bc["short_strike"]:.0f}/{bc["long_strike"]:.0f}</td>'
            f'<td class="num">${bc["net_credit"]:.2f}</td>'
            f'<td class="num">${bc["max_profit"]:.0f}</td>'
            f'<td class="num">${bc["max_loss"]:.0f}</td>'
            f'<td class="num">{bc["prob_profit_pct"]:.0f}%</td>'
            '</tr>'
        )
    return "\n".join(rows)


def _legs_table(rows):
    """rows: list of (action, strike, premium, oi, delta_or_blank)."""
    body = []
    for action, strike, premium, oi, delta_str in rows:
        cls = "sell" if action == "SELL" else "buy"
        body.append(
            f'<tr>'
            f'<td class="act {cls}">{action}</td>'
            f'<td class="num">${strike:.2f}</td>'
            f'<td class="num">${premium:.2f}</td>'
            f'<td class="num">{oi if oi is not None else "—"}</td>'
            f'<td class="num">{delta_str}</td>'
            '</tr>'
        )
    return (
        '<table class="legs">'
        '<thead><tr><th>Action</th><th class="num">Strike</th>'
        '<th class="num">Premium (mid)</th><th class="num">OI</th>'
        '<th class="num">Δ</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def _card_metrics(max_profit, max_loss, breakeven, pop):
    be_str = breakeven if isinstance(breakeven, str) else f'${breakeven:.2f}'
    return (
        '<div class="metrics">'
        f'<div><div class="lab">Max profit</div><div class="v">${max_profit:.0f}</div></div>'
        f'<div><div class="lab">Max loss</div><div class="v">${max_loss:.0f}</div></div>'
        f'<div><div class="lab">Breakeven</div><div class="v">{be_str}</div></div>'
        f'<div><div class="lab">POP</div><div class="v">{pop:.0f}%</div></div>'
        '</div>'
    )


def _model_slot(name):
    """Single-paragraph placeholder for the model to replace verbatim."""
    return f'<!-- MODEL_SLOT:{name} --><p>[{name.replace("_", " ")}]</p>'


def _disclaimer():
    return (
        '<p class="disclaimer">Premiums are model estimates from Black-Scholes against '
        'bid/ask mid; verify against your broker before trading.</p>'
    )


def _render_card_bull_put(bp, expiry_str, mgmt_text):
    sp_d = abs(bp.get("short_delta") or 0)
    legs = _legs_table([
        ("SELL", bp["short_strike"], bp["short_mid"], bp["short_oi"], f"{sp_d:.2f}"),
        ("BUY",  bp["long_strike"],  bp["long_mid"],  bp["long_oi"],  ""),
    ])
    return (
        '<article class="card bull">'
        f'<div class="card-kicker">{_BULL_KICKER}</div>'
        f'<h3>Bull put spread — short {bp["short_strike"]:.0f}P / long {bp["long_strike"]:.0f}P</h3>'
        f'<p class="credit-big">${bp["net_credit"]:.2f} <small>net credit per contract</small></p>'
        f'{_card_metrics(bp["max_profit"], bp["max_loss"], bp["breakeven"], bp["prob_profit_pct"])}'
        f'{legs}'
        f'<div class="sect"><h4>Rationale</h4>{_model_slot("bull_put_rationale")}</div>'
        f'<div class="sect"><h4>Entry trigger</h4>{_model_slot("bull_put_entry_trigger")}</div>'
        f'<div class="sect"><h4>Stop / adjustment</h4>{_model_slot("bull_put_stop_rule")}</div>'
        f'<div class="sect"><h4>Management timeline</h4><p>{mgmt_text}</p></div>'
        f'{_disclaimer()}'
        '</article>'
    )


def _render_card_iron_condor(ic, expiry_str, mgmt_text):
    bp = ic["put_side"]
    bc = ic["call_side"]
    sp_d = abs(bp.get("short_delta") or 0)
    sc_d = abs(bc.get("short_delta") or 0)
    legs = _legs_table([
        ("BUY",  bp["long_strike"],  bp["long_mid"],  bp["long_oi"],  ""),
        ("SELL", bp["short_strike"], bp["short_mid"], bp["short_oi"], f"{sp_d:.2f}"),
        ("SELL", bc["short_strike"], bc["short_mid"], bc["short_oi"], f"{sc_d:.2f}"),
        ("BUY",  bc["long_strike"],  bc["long_mid"],  bc["long_oi"],  ""),
    ])
    profit_zone = ic.get("profit_zone") or (
        f'${ic["breakeven_low"]:.2f} – ${ic["breakeven_high"]:.2f}'
    )
    return (
        '<article class="card neutral">'
        f'<div class="card-kicker">{_NEUTRAL_KICKER}</div>'
        f'<h3>Iron condor — {bp["long_strike"]:.0f}/{bp["short_strike"]:.0f} put · '
        f'{bc["short_strike"]:.0f}/{bc["long_strike"]:.0f} call</h3>'
        f'<p class="credit-big">${ic["total_credit"]:.2f} <small>net credit per contract</small></p>'
        f'{_card_metrics(ic["max_profit"], ic["max_loss"], profit_zone, ic["prob_profit_pct"])}'
        f'{legs}'
        f'<div class="sect"><h4>Rationale</h4>{_model_slot("iron_condor_rationale")}</div>'
        f'<div class="sect"><h4>Entry trigger</h4>{_model_slot("iron_condor_entry_trigger")}</div>'
        f'<div class="sect"><h4>Stop / adjustment</h4>{_model_slot("iron_condor_stop_rule")}</div>'
        f'<div class="sect"><h4>Management timeline</h4><p>{mgmt_text}</p></div>'
        f'{_disclaimer()}'
        '</article>'
    )


def _render_card_bear_call(bc, expiry_str, mgmt_text):
    sc_d = abs(bc.get("short_delta") or 0)
    legs = _legs_table([
        ("SELL", bc["short_strike"], bc["short_mid"], bc["short_oi"], f"{sc_d:.2f}"),
        ("BUY",  bc["long_strike"],  bc["long_mid"],  bc["long_oi"],  ""),
    ])
    return (
        '<article class="card bear">'
        f'<div class="card-kicker">{_BEAR_KICKER}</div>'
        f'<h3>Bear call spread — short {bc["short_strike"]:.0f}C / long {bc["long_strike"]:.0f}C</h3>'
        f'<p class="credit-big">${bc["net_credit"]:.2f} <small>net credit per contract</small></p>'
        f'{_card_metrics(bc["max_profit"], bc["max_loss"], bc["breakeven"], bc["prob_profit_pct"])}'
        f'{legs}'
        f'<div class="sect"><h4>Rationale</h4>{_model_slot("bear_call_rationale")}</div>'
        f'<div class="sect"><h4>Entry trigger</h4>{_model_slot("bear_call_entry_trigger")}</div>'
        f'<div class="sect"><h4>Stop / adjustment</h4>{_model_slot("bear_call_stop_rule")}</div>'
        f'<div class="sect"><h4>Management timeline</h4><p>{mgmt_text}</p></div>'
        f'{_disclaimer()}'
        '</article>'
    )


def _render_flowchart(pivot):
    s1 = pivot["S1"]
    r1 = pivot["R1"]
    r2 = pivot["R2"]
    return (
        '<div class="flow-node"><div class="q">Open: where is price after first 30–60 min?</div></div>'
        f'<div class="flow-node"><div class="q">Above ${s1:.2f} (S1)?</div>'
        '<div class="flow-node"><span class="yes">YES</span> '
        f'<span class="q">→ Rejection below ${r1:.2f}–${r2:.2f}?</span>'
        '<div class="flow-node"><span class="no">NO</span> '
        '<span class="outcome">→ Scenario A · bull put spread</span></div>'
        '<div class="flow-node"><span class="yes">YES</span> '
        '<span class="outcome">→ Scenario C · bear call spread</span></div>'
        '</div>'
        '<div class="flow-node"><span class="no">NO</span> '
        f'<span class="q">→ Range-bound inside ${s1:.2f}–${r1:.2f}?</span>'
        '<div class="flow-node"><span class="yes">YES</span> '
        '<span class="outcome">→ Scenario B · iron condor</span></div>'
        '<div class="flow-node"><span class="no">NO</span> '
        '<span class="outcome">→ No trade. Wait for next session.</span></div>'
        '</div></div>'
    )


def _sizing_for(max_loss, budget_pct, portfolio):
    if not max_loss or max_loss <= 0:
        return 0
    return int((portfolio * budget_pct) // max_loss)


def _render_sizing_rows(trades):
    sizes = [250_000, 500_000, 1_000_000]
    out = []

    def row(label, max_loss, budget_pct):
        cells = "".join(
            f'<td class="num">{_sizing_for(max_loss, budget_pct, s)}</td>' for s in sizes
        )
        return (
            f'<tr><td>{label}</td><td class="num">${max_loss:.0f}</td>{cells}</tr>'
        )

    if "bull_put" in trades:
        out.append(row("Bull put", trades["bull_put"]["max_loss"], _RISK_BUDGET["bull_put"]))
    if "iron_condor" in trades:
        out.append(row("Iron condor", trades["iron_condor"]["max_loss"], _RISK_BUDGET["iron_condor"]))
    if "bear_call" in trades:
        out.append(row("Bear call", trades["bear_call"]["max_loss"], _RISK_BUDGET["bear_call"]))
    return "\n".join(out)


def _render_chart_config(trades, price):
    """Build {labels, bullPut, condor, bearCall} dict ready to be JSON-encoded."""
    if not price:
        return {"labels": [], "bullPut": [], "condor": [], "bearCall": []}

    low = price * 0.85
    high = price * 1.15
    step = 0.5
    n_steps = max(1, int((high - low) / step) + 1)
    xs = [round(low + i * step, 2) for i in range(n_steps)]

    def bull_put_pnl(x):
        if "bull_put" not in trades:
            return None
        bp = trades["bull_put"]
        cr = bp["net_credit"]
        w = bp["width"]
        sp = bp["short_strike"]
        lp = bp["long_strike"]
        if x >= sp:
            v = cr
        elif x <= lp:
            v = cr - w
        else:
            v = cr - (sp - x)
        return round(v * 100, 2)

    def bear_call_pnl(x):
        if "bear_call" not in trades:
            return None
        bc = trades["bear_call"]
        cr = bc["net_credit"]
        w = bc["width"]
        sc = bc["short_strike"]
        lc = bc["long_strike"]
        if x <= sc:
            v = cr
        elif x >= lc:
            v = cr - w
        else:
            v = cr - (x - sc)
        return round(v * 100, 2)

    def condor_pnl(x):
        if "iron_condor" not in trades:
            return None
        ic = trades["iron_condor"]
        bp = ic["put_side"]
        bc = ic["call_side"]
        cr = ic["total_credit"]
        sp, lp = bp["short_strike"], bp["long_strike"]
        sc, lc = bc["short_strike"], bc["long_strike"]
        bp_w = bp["width"]
        bc_w = bc["width"]
        # Put-side loss
        if x >= sp:
            put_loss = 0.0
        elif x <= lp:
            put_loss = bp_w
        else:
            put_loss = sp - x
        # Call-side loss
        if x <= sc:
            call_loss = 0.0
        elif x >= lc:
            call_loss = bc_w
        else:
            call_loss = x - sc
        v = cr - put_loss - call_loss
        return round(v * 100, 2)

    return {
        "labels": xs,
        "bullPut": [bull_put_pnl(x) for x in xs],
        "condor": [condor_pnl(x) for x in xs],
        "bearCall": [bear_call_pnl(x) for x in xs],
    }


def _render_earnings_line(earnings_info, expiry_str):
    if not earnings_info:
        return "None scheduled before expiry"
    d = earnings_info["date"]
    timing = earnings_info.get("timing")
    days_from = earnings_info.get("days_from_expiry")
    in_window = earnings_info.get("within_expiry_window")
    timing_str = f", {timing}" if timing else ""
    if in_window:
        return f"{d}{timing_str} (INSIDE window)"
    if days_from is None:
        return f"{d}{timing_str}"
    if days_from > 0:
        return f"{d}{timing_str} ({days_from}d after expiry)"
    return f"{d}{timing_str} ({abs(days_from)}d before expiry)"


def _render_vol_bars(atm_iv_pct, hv_30_pct):
    cap = max(atm_iv_pct or 0, hv_30_pct or 0, 1.0) * 1.15
    iv_w = round((atm_iv_pct or 0) / cap * 100, 1)
    hv_w = round((hv_30_pct or 0) / cap * 100, 1)
    return (
        f'<div class="vol-bar-row"><span class="lab">IV</span>'
        f'<span class="bar"><span class="fill" style="width:{iv_w}%"></span></span>'
        f'<span class="num">{(atm_iv_pct or 0):.1f}%</span></div>'
        f'<div class="vol-bar-row"><span class="lab">HV 30d</span>'
        f'<span class="bar"><span class="fill" style="width:{hv_w}%"></span></span>'
        f'<span class="num">{(hv_30_pct or 0):.1f}%</span></div>'
    )


def _render_positioning(chain_summary):
    items = []
    mp = chain_summary.get("max_pain")
    if mp is not None:
        items.append(f'<li>Max pain: <b class="mono">${mp:.2f}</b></li>')
    pw = chain_summary.get("put_oi_wall")
    if pw:
        items.append(f'<li>Put OI wall: <b class="mono">${pw["strike"]:.2f}</b> ({pw["oi"]:,} contracts)</li>')
    cw = chain_summary.get("call_oi_wall")
    if cw:
        items.append(f'<li>Call OI wall: <b class="mono">${cw["strike"]:.2f}</b> ({cw["oi"]:,} contracts)</li>')
    pcr = chain_summary.get("put_call_oi_ratio")
    if pcr is not None:
        bias = "put-heavy" if pcr > 1.1 else ("call-heavy" if pcr < 0.9 else "balanced")
        items.append(f'<li>Put/Call OI ratio: <b class="mono">{pcr:.2f}</b> ({bias})</li>')
    return f'<ul>{"".join(items)}</ul>' if items else "<p>No positioning data available.</p>"


def render_html_fragments(result):
    """Return a dict of pre-rendered HTML fragments and pre-formatted scalars
    keyed to template.html placeholder names. The model uses these directly
    rather than reconstructing them."""
    trades = result.get("trades") or {}
    pivot = result.get("pivot") or {}
    guidance = result.get("strike_guidance") or {}
    bucket = guidance.get("dte_bucket")
    mgmt_text = _MGMT_TIMELINE.get(bucket, "Take 50% profit; close before final week. Hard stop at 2× credit.")

    expiry_str = result.get("expiry") or ""
    em = result.get("expected_move") or {}
    em_str = "—"
    if em.get("dollar") is not None and em.get("pct") is not None:
        em_str = f'±${em["dollar"]:.2f} (±{em["pct"]:.2f}%)'

    ch = result.get("change_pct")
    if ch is None:
        chg_str = "—"
    else:
        chg_str = f"{ch:+.2f}%"

    chain_summary = result.get("chain_summary") or {}

    return {
        # Scalar tokens (already-formatted strings)
        "ticker": result.get("ticker", ""),
        "strategy_label": _strategy_label(result.get("dte")),
        "expiry": _pretty_expiry(expiry_str),
        "dte": result.get("dte"),
        "pub_date": date.today().strftime("%B %d, %Y"),
        "expiry_resolution": result.get("expiry_resolution") or "",
        "spot": f'{result.get("price"):.2f}' if result.get("price") is not None else "—",
        "chg_pct": chg_str,
        "iv": _fmt_pct(result.get("atm_iv_pct")),
        "hv": _fmt_pct(result.get("hv_30d_pct")),
        "iv_hv_ratio": f'{result["iv_hv_ratio"]:.2f}' if result.get("iv_hv_ratio") is not None else "—",
        "iv_rank": f'{result["iv_rank_pct_proxy"]:.0f}' if result.get("iv_rank_pct_proxy") is not None else "—",
        "max_pain": _fmt_money(chain_summary.get("max_pain")),
        "earnings_line": _render_earnings_line(result.get("earnings"), expiry_str),
        "expected_move": em_str,
        "iv_verdict": result.get("iv_hv_verdict") or "Neutral.",
        # HTML fragments
        "levels_rows_html": _render_levels_rows(
            pivot, result.get("sma_50"), result.get("sma_200"), result.get("ohlc_prev_session")
        ),
        "trade_summary_rows_html": _render_trade_summary_rows(trades),
        "bull_put_card_html": (
            _render_card_bull_put(trades["bull_put"], expiry_str, mgmt_text)
            if "bull_put" in trades else "<p><em>Bull put spread not available for this chain.</em></p>"
        ),
        "condor_card_html": (
            _render_card_iron_condor(trades["iron_condor"], expiry_str, mgmt_text)
            if "iron_condor" in trades else "<p><em>Iron condor not available for this chain.</em></p>"
        ),
        "bear_call_card_html": (
            _render_card_bear_call(trades["bear_call"], expiry_str, mgmt_text)
            if "bear_call" in trades else "<p><em>Bear call spread not available for this chain.</em></p>"
        ),
        "flowchart_html": _render_flowchart(pivot) if pivot else "",
        "vol_bars_html": _render_vol_bars(result.get("atm_iv_pct"), result.get("hv_30d_pct")),
        "positioning_html": _render_positioning(chain_summary),
        "sizing_rows_html": _render_sizing_rows(trades),
        "chart_config_json": _render_chart_config(trades, result.get("price")),
    }


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

    result["html"] = render_html_fragments(result)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
