#!/usr/bin/env python3
"""Weekend PMCC (Poor Man's Covered Call) LEAP scanner.

Sweeps a universe of tickers and ranks candidates for a poor man's covered call:
a deep-ITM long-dated LEAP call (the stock substitute) against which shorter-dated
calls can be sold. Outputs a single JSON object to stdout with ranked candidates
and a transparent list of skipped tickers (with reasons).

Usage:
    scan_pmcc.py [TICKER ...] [--leap-delta 0.80] [--leap-dte-min 330]
                 [--leap-dte-max 730] [--short-delta 0.30] [--short-dte-min 30]
                 [--short-dte-max 45] [--min-oi 100] [--max-extrinsic-pct 0.10]
                 [--max-spread-pct 0.15] [--top 25] [--html]

With no tickers (or --universe), scans the built-in universe.json list.
With --html, also writes pmcc-scans/YYYY-MM-DD.{json,html} under the repo root.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import contextlib
import io
import json
import re
from datetime import date, datetime

from _shared.options_lib import (
    _safe_int,
    error_exit,
    get_stock_price,
    option_mid,
    compute_iv_delta,
    select_strike_by_delta,
    fetch_chain_with_retry,
    classify_price_source,
)

try:
    import yfinance as yf
except ImportError:
    error_exit("yfinance not installed — run: pip3 install yfinance")

TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
HERE = os.path.dirname(__file__)


def _load_universe():
    """Load the built-in ticker universe from universe.json."""
    path = os.path.join(HERE, "universe.json")
    try:
        with open(path) as f:
            data = json.load(f)
        tickers = data.get("tickers", []) if isinstance(data, dict) else data
        return [t.upper() for t in tickers if TICKER_RE.match(str(t).upper())]
    except (OSError, ValueError):
        return []


def _parse_args(argv):
    """Parse positional tickers and --flag value pairs."""
    opts = {
        "leap_delta": 0.80,
        "leap_dte_min": 330,
        "leap_dte_max": 730,
        "short_delta": 0.30,
        "short_dte_min": 30,
        "short_dte_max": 45,
        "min_oi": 100,
        "max_extrinsic_pct": 0.15,
        "max_spread_pct": 0.15,
        "top": 25,
        "html": False,
        "use_universe": False,
    }
    floats = {"leap_delta", "short_delta", "max_extrinsic_pct", "max_spread_pct"}
    ints = {"leap_dte_min", "leap_dte_max", "short_dte_min", "short_dte_max", "min_oi", "top"}
    tickers = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--html":
            opts["html"] = True
        elif a == "--universe":
            opts["use_universe"] = True
        elif a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 >= len(argv):
                error_exit(f"Missing value for {a}")
            val = argv[i + 1]
            i += 1
            if key in floats:
                opts[key] = float(val)
            elif key in ints:
                opts[key] = int(val)
            else:
                error_exit(f"Unknown flag {a}")
        else:
            t = a.upper()
            if not TICKER_RE.match(t):
                error_exit(f"Invalid ticker '{a}' — must match ^[A-Z]{{1,5}}$")
            tickers.append(t)
        i += 1
    return tickers, opts


def _pick_leap_expiry(tk, expirations, today, dte_min, dte_max):
    """Pick the longest-dated expiry within [dte_min, dte_max]; fall back to the
    longest available expiry that is at least dte_min out. Returns (expiry, dte)."""
    best_in_range = None
    longest = None
    for exp in expirations:
        try:
            d = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if d < dte_min:
            continue
        if longest is None or d > longest[1]:
            longest = (exp, d)
        if d <= dte_max and (best_in_range is None or d > best_in_range[1]):
            best_in_range = (exp, d)
    return best_in_range or longest


def _select_itm_call_by_delta(calls, price, T, target_delta, delta_floor):
    """Pick the ITM call whose computed delta is closest to target_delta, requiring
    delta >= delta_floor. Returns an enriched row dict, or None."""
    itm = calls[calls["strike"] < price].copy()
    if itm.empty:
        return None
    best = None
    for _, row in itm.iterrows():
        mid = option_mid(row)
        if mid is None or mid <= 0:
            continue
        strike = float(row["strike"])
        iv, delta = compute_iv_delta(price, strike, T, mid, "call")
        if delta is None or delta < delta_floor:
            continue
        score = abs(delta - target_delta)
        if best is None or score < best["_score"]:
            d = row.to_dict()
            d["_score"] = score
            d["mid_price"] = mid
            d["calc_iv"] = iv
            d["calc_delta"] = delta
            best = d
    return best


def _spread_pct(bid, ask, mid):
    if not mid or mid <= 0 or bid <= 0 or ask <= 0:
        return None
    return round((ask - bid) / mid, 4)


def scan_ticker(ticker_sym, today, opts):
    """Evaluate one ticker. Returns (candidate_dict | None, skip_reason | None)."""
    tk = yf.Ticker(ticker_sym)
    try:
        # get_stock_price calls error_exit (prints a JSON error line + raises
        # SystemExit) on a delisted/dataless ticker. In a multi-ticker sweep that
        # must not abort the run nor corrupt the single-JSON-object output, so we
        # swallow its stray stdout and treat it as an ordinary per-ticker skip.
        with contextlib.redirect_stdout(io.StringIO()):
            price, prev_close, change_pct = get_stock_price(tk, ticker_sym)
    except (SystemExit, Exception):
        return None, "no_price"

    expirations = tk.options
    if not expirations:
        return None, "no_options_chain"

    # --- LEAP long leg ---
    leap = _pick_leap_expiry(tk, expirations, today, opts["leap_dte_min"], opts["leap_dte_max"])
    if leap is None:
        return None, f"no_leap_expiry_>={opts['leap_dte_min']}dte"
    leap_exp, leap_dte = leap
    leap_T = leap_dte / 365.0

    leap_calls = fetch_chain_with_retry(tk, leap_exp, side="calls")
    if leap_calls is None or leap_calls.empty:
        return None, "no_leap_calls"

    delta_floor = max(0.55, opts["leap_delta"] - 0.10)
    leap_row = _select_itm_call_by_delta(leap_calls, price, leap_T, opts["leap_delta"], delta_floor)
    if leap_row is None:
        return None, f"no_itm_call_delta>={delta_floor:.2f}"

    leap_strike = float(leap_row["strike"])
    leap_mid = float(leap_row["mid_price"])
    leap_delta = round(float(leap_row["calc_delta"]), 3)
    leap_iv = leap_row.get("calc_iv")
    leap_bid = round(float(leap_row.get("bid", 0) or 0), 2)
    leap_ask = round(float(leap_row.get("ask", 0) or 0), 2)
    leap_oi = _safe_int(leap_row.get("openInterest"))
    leap_vol = _safe_int(leap_row.get("volume"))

    intrinsic = max(price - leap_strike, 0)
    extrinsic = round(leap_mid - intrinsic, 2)
    if leap_strike <= 0 or extrinsic <= 0:
        return None, "leap_no_extrinsic"
    extrinsic_pct = round(extrinsic / leap_strike, 4)

    # Quality gates on the LEAP
    if leap_oi < opts["min_oi"]:
        return None, f"leap_illiquid_oi={leap_oi}<{opts['min_oi']}"
    spread_pct = _spread_pct(leap_bid, leap_ask, leap_mid)
    if spread_pct is not None and spread_pct > opts["max_spread_pct"]:
        return None, f"leap_wide_spread={spread_pct}"
    if extrinsic_pct > opts["max_extrinsic_pct"]:
        return None, f"extrinsic_too_high={extrinsic_pct}"

    # --- Short call income leg (modeled) ---
    short_exp = _pick_short_expiry(expirations, today, opts["short_dte_min"], opts["short_dte_max"])
    if short_exp is None:
        return None, "no_short_expiry"
    short_exp_str, short_dte = short_exp
    short_T = short_dte / 365.0
    short_calls = fetch_chain_with_retry(tk, short_exp_str, side="calls")
    if short_calls is None or short_calls.empty:
        return None, "no_short_calls"

    short_row, _, _ = select_strike_by_delta(short_calls, price, short_T, opts["short_delta"], "call")
    if short_row is None:
        return None, "no_short_strike"
    short_strike = float(short_row["strike"])
    short_mid = float(short_row["mid_price"])
    short_delta = round(float(short_row["calc_delta"]), 3)

    if short_strike <= leap_strike:
        return None, "short_strike_<=_leap_strike"

    # --- PMCC metrics ---
    net_debit = round(leap_mid - short_mid, 2)
    width = round(short_strike - leap_strike, 2)
    max_profit = round(width - net_debit, 2)
    breakeven = round(leap_strike + net_debit, 2)
    # Yield efficiency: how much of the extrinsic one short-call cycle recovers,
    # and annualized across the year.
    cycles_per_year = 365.0 / short_dte if short_dte else 0
    annual_income = short_mid * cycles_per_year
    recovery_ratio = round(annual_income / extrinsic, 3) if extrinsic else None
    cycle_recovery = round(short_mid / extrinsic, 3) if extrinsic else None
    capital_efficiency = round((price * 100) / (leap_mid * 100), 2) if leap_mid else None
    return_on_debit = round(max_profit / net_debit * 100, 1) if net_debit > 0 else None

    candidate = {
        "ticker": ticker_sym,
        "stock_price": round(price, 2),
        "change_pct": change_pct,
        "leap": {
            "expiry": leap_exp,
            "dte": leap_dte,
            "strike": leap_strike,
            "mid": round(leap_mid, 2),
            "delta": leap_delta,
            "iv_pct": round(leap_iv * 100, 1) if leap_iv else None,
            "intrinsic": round(intrinsic, 2),
            "extrinsic": extrinsic,
            "extrinsic_pct": extrinsic_pct,
            "bid": leap_bid,
            "ask": leap_ask,
            "oi": leap_oi,
            "volume": leap_vol,
            "spread_pct": spread_pct,
        },
        "short_call": {
            "expiry": short_exp_str,
            "dte": short_dte,
            "strike": short_strike,
            "mid": round(short_mid, 2),
            "delta": short_delta,
        },
        "net_debit": net_debit,
        "width": width,
        "max_profit": max_profit,
        "return_on_debit_pct": return_on_debit,
        "breakeven": breakeven,
        "cycle_recovery_ratio": cycle_recovery,
        "annual_recovery_ratio": recovery_ratio,
        "capital_efficiency_x": capital_efficiency,
        "price_source": classify_price_source(leap_bid, leap_ask),
    }
    return candidate, None


def _pick_short_expiry(expirations, today, dte_min, dte_max):
    """Pick the expiry closest to the midpoint of [dte_min, dte_max]."""
    mid = (dte_min + dte_max) / 2
    best = None
    for exp in expirations:
        try:
            d = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if d < 1:
            continue
        score = abs(d - mid)
        if best is None or score < best[2]:
            best = (exp, d, score)
    if best is None:
        return None
    return best[0], best[1]


def _rank_key(c):
    return (
        c.get("annual_recovery_ratio") or 0,
        c.get("leap", {}).get("oi") or 0,
    )


def _write_html(report, scan_date):
    out_dir = os.path.join(HERE, "..", "..", "..", "..", "..", "..", "pmcc-scans")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{scan_date}.json")
    html_path = os.path.join(out_dir, f"{scan_date}.html")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    rows = []
    for i, c in enumerate(report["candidates"], 1):
        leap = c["leap"]
        sc = c["short_call"]
        rows.append(
            f"<tr><td>{i}</td><td><b>{c['ticker']}</b></td><td>${c['stock_price']}</td>"
            f"<td>{leap['expiry']}<br><small>{leap['dte']}d</small></td>"
            f"<td>${leap['strike']} &Delta;{leap['delta']}</td>"
            f"<td>${leap['mid']}</td><td>${leap['extrinsic']} ({leap['extrinsic_pct']*100:.1f}%)</td>"
            f"<td>${sc['strike']} &Delta;{sc['delta']}<br><small>{sc['dte']}d</small></td>"
            f"<td>${sc['mid']}</td>"
            f"<td><b>{c['annual_recovery_ratio']}x</b></td>"
            f"<td>${c['net_debit']}</td><td>{c['return_on_debit_pct']}%</td></tr>"
        )
    table = "\n".join(rows) or "<tr><td colspan='12'>No candidates passed the filters.</td></tr>"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>PMCC Weekend Scan — {scan_date}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:2rem;color:#1a1a1a;background:#fafafa}}
h1{{font-size:1.5rem}} .meta{{color:#666;font-size:.85rem;margin-bottom:1rem}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:.85rem}}
th,td{{border:1px solid #e2e2e2;padding:6px 8px;text-align:left}}
th{{background:#1a1a2e;color:#fff;position:sticky;top:0}}
tr:nth-child(even){{background:#f6f6f9}} small{{color:#888}}
.note{{margin-top:1.5rem;font-size:.8rem;color:#777}}
</style></head><body>
<h1>Poor Man's Covered Call — Weekend Scan</h1>
<div class="meta">Generated {scan_date} &middot; {len(report['candidates'])} candidates from
{report['scanned']} tickers &middot; ranked by annualized recovery ratio
(short-call income / LEAP extrinsic). Data: yfinance. Not financial advice.</div>
<table><thead><tr>
<th>#</th><th>Ticker</th><th>Spot</th><th>LEAP exp</th><th>LEAP strike</th><th>LEAP debit</th>
<th>Extrinsic</th><th>Short call</th><th>Credit</th><th>Annual rec.</th><th>Net debit</th><th>Max ROI</th>
</tr></thead><tbody>
{table}
</tbody></table>
<div class="note">Skipped: {len(report['skipped'])} tickers. See {os.path.basename(json_path)} for full data and skip reasons.
Always confirm earnings dates, dividends (early-assignment risk on the short call), and IV rank before entering.</div>
</body></html>"""
    with open(html_path, "w") as f:
        f.write(html)
    return json_path, html_path


def main():
    argv = sys.argv[1:]
    tickers, opts = _parse_args(argv)
    if not tickers or opts["use_universe"]:
        universe = _load_universe()
        tickers = tickers or universe
    if not tickers:
        error_exit("No tickers to scan — pass tickers or populate universe.json")

    today = date.today()
    candidates = []
    skipped = []
    for t in tickers:
        try:
            cand, reason = scan_ticker(t, today, opts)
        except SystemExit:
            raise
        except Exception as e:  # one bad ticker never aborts the sweep
            skipped.append({"ticker": t, "reason": f"error: {type(e).__name__}"})
            continue
        if cand:
            candidates.append(cand)
        else:
            skipped.append({"ticker": t, "reason": reason or "no_candidate"})

    candidates.sort(key=_rank_key, reverse=True)
    candidates = candidates[: opts["top"]]
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    report = {
        "strategy": "pmcc-leap-scanner",
        "scan_date": today.isoformat(),
        "scanned": len(tickers),
        "params": {
            "leap_delta": opts["leap_delta"],
            "leap_dte_min": opts["leap_dte_min"],
            "leap_dte_max": opts["leap_dte_max"],
            "short_delta": opts["short_delta"],
            "short_dte": [opts["short_dte_min"], opts["short_dte_max"]],
            "min_oi": opts["min_oi"],
            "max_extrinsic_pct": opts["max_extrinsic_pct"],
            "max_spread_pct": opts["max_spread_pct"],
        },
        "candidates": candidates,
        "skipped": skipped,
        "data_source": "yfinance",
    }

    if opts["html"]:
        json_path, html_path = _write_html(report, today.isoformat())
        report["html_report"] = html_path
        report["json_report"] = json_path

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
