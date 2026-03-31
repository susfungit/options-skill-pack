"""Shared options utilities — Black-Scholes, IV solver, market helpers.

All skill scripts import from here to avoid duplication.
"""

import math
from datetime import date, datetime

import pytz


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_int(v):
    """Convert to int, treating None/NaN as 0."""
    if v is None:
        return 0
    try:
        if math.isnan(v):
            return 0
    except TypeError:
        pass
    return int(v)


# ── Black-Scholes ────────────────────────────────────────────────────────────

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
    """Bisection IV solver. Returns None if no solution found."""
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


# ── Market utilities ─────────────────────────────────────────────────────────

def option_mid(row):
    """Best price: bid/ask mid if available, else lastPrice."""
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2)
    last = float(row.get("lastPrice", 0) or 0)
    return round(last, 2) if last > 0 else 0.0


def is_market_open():
    """Check if US equity market is currently open (Mon-Fri 9:30-16:00 ET)."""
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
    """Select expiry closest to midpoint of DTE range, or first available past dte_min."""
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
