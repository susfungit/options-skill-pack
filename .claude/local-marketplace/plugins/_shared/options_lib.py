"""Shared options utilities — Black-Scholes, IV solver, market helpers.

All skill scripts import from here to avoid duplication.
"""

import json
import math
import sys
import time
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


def option_mid_ex(row):
    """Like option_mid but also returns the price source.

    Returns (mid_price, source) where source is one of:
      "live"      — computed from bid/ask midpoint
      "lastPrice" — fallback to last traded price
      "none"      — no price data available
    """
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask > bid:
        return round((bid + ask) / 2, 2), "live"
    last = float(row.get("lastPrice", 0) or 0)
    if last > 0:
        return round(last, 2), "lastPrice"
    return 0.0, "none"


def fetch_chain_with_retry(ticker_obj, expiry_str, side="puts", max_retries=2, delay=1.5):
    """Fetch option chain, retrying if bid/ask are mostly zeros.

    Returns the DataFrame (puts or calls) after up to *max_retries* attempts.
    Yahoo's API intermittently returns zeroed-out bid/ask; a short retry
    usually gets real data.
    """
    for attempt in range(max_retries):
        chain = ticker_obj.option_chain(expiry_str)
        df = chain.puts.copy() if side == "puts" else chain.calls.copy()
        if df.empty:
            return df
        # Check if we got real bid/ask on at least some rows
        has_bids = (df["bid"] > 0).sum()
        if has_bids >= max(1, len(df) * 0.2):
            return df
        if attempt < max_retries - 1:
            time.sleep(delay)
    return df


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


# ── Workflow helpers ─────────────────────────────────────────────────────────
# These consolidate boilerplate that was duplicated across all skill scripts.


def error_exit(msg, **extra):
    """Print JSON error and exit. Extra kwargs are merged into the output."""
    payload = {"error": msg}
    payload.update(extra)
    print(json.dumps(payload))
    sys.exit(1)


def get_stock_price(ticker_obj, ticker_sym):
    """Fetch current stock price + prior close from yfinance Ticker.

    Returns (price, prev_close, change_pct). If only one row of history is
    available (e.g. brand new listing), prev_close falls back to price and
    change_pct is 0.0. Calls error_exit on failure.
    """
    hist = ticker_obj.history(period="2d")
    if hist.empty:
        error_exit(f"No price data for {ticker_sym}")
    price = round(float(hist["Close"].iloc[-1]), 2)
    if len(hist) >= 2:
        prev_close = round(float(hist["Close"].iloc[-2]), 2)
        change_pct = round((price / prev_close - 1) * 100, 2) if prev_close else 0.0
    else:
        prev_close = price
        change_pct = 0.0
    return price, prev_close, change_pct


def parse_expiry_flag(argv):
    """Extract --expiry flag from argv list, returning (cleaned_argv, explicit_expiry)."""
    argv = list(argv)
    explicit_expiry = None
    if "--expiry" in argv:
        idx = argv.index("--expiry")
        if idx + 1 < len(argv):
            explicit_expiry = argv[idx + 1]
        argv = argv[:idx] + argv[idx + 2:]
    return argv, explicit_expiry


def resolve_selector_expiry(tk, expirations, dte_min, dte_max, explicit_expiry, ticker_sym):
    """Resolve expiry for selector scripts. Returns (expiry_str, dte) tuple.

    Handles explicit --expiry override and find_best_expiry fallback.
    Calls error_exit on failure.
    """
    if not expirations:
        error_exit(f"No options listed for {ticker_sym}")

    if explicit_expiry:
        if explicit_expiry not in expirations:
            error_exit(f"Expiry {explicit_expiry} not available for {ticker_sym}")
        dte = (datetime.strptime(explicit_expiry, "%Y-%m-%d").date() - date.today()).days
        return explicit_expiry, dte

    result = find_best_expiry(expirations, dte_min, dte_max)
    if result is None:
        error_exit(f"No expiry within {dte_min}\u2013{dte_max} DTE")
    return result


def resolve_monitor_expiry(tk, expiry_str, ticker_sym):
    """Validate and resolve monitor expiry. Returns (use_expiry, expiry_date, dte).

    If exact expiry not in chain, finds nearest within ±3 days.
    Calls error_exit on failure.
    """
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        error_exit(f"Invalid expiry format: {expiry_str} \u2014 use YYYY-MM-DD")

    today = date.today()
    dte = (expiry_date - today).days

    if dte < 0:
        error_exit(f"Expiry {expiry_str} has already passed ({abs(dte)} days ago)")

    available = tk.options
    use_expiry = expiry_str
    if expiry_str not in available:
        nearest = None
        for exp in available:
            exp_d = datetime.strptime(exp, "%Y-%m-%d").date()
            if abs((exp_d - expiry_date).days) <= 3:
                nearest = exp
                break
        if nearest is None:
            error_exit(
                f"Expiry {expiry_str} not found in chain. Available: {list(available[:5])}",
                stock_price=get_stock_price(tk, ticker_sym)[0],
                dte=dte,
            )
        use_expiry = nearest

    return use_expiry, expiry_date, dte


def compute_iv_delta(price, strike, T, mid_price, side="put"):
    """Compute IV and delta for a single option from its mid price.

    Returns (iv, delta) — both None if computation fails.
    iv is raw (not percentage), delta is absolute.
    """
    if not mid_price or mid_price <= 0:
        return None, None
    iv = implied_vol(price, strike, T, mid_price, side)
    if not iv or iv <= 0:
        return None, None
    if side == "put":
        delta = bs_put_delta_abs(price, strike, T, iv)
    else:
        delta = bs_call_delta(price, strike, T, iv)
    return iv, delta


def select_strike_by_delta(df, price, T, target_delta, side="put"):
    """Select the OTM strike closest to target_delta.

    Returns (row_dict, valid_df, otm_df) or (None, valid_df_or_None, otm_df) on failure.
    row_dict includes computed 'calc_iv', 'calc_delta', 'mid_price' columns.
    """
    if side == "put":
        otm = df[df["strike"] < price].copy()
    else:
        otm = df[df["strike"] > price].copy()

    otm["mid_price"] = otm.apply(option_mid, axis=1)
    otm = otm[otm["mid_price"] > 0].copy()

    if otm.empty:
        return None, None, otm

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
        return None, valid, otm

    valid["delta_diff"] = (valid["calc_delta"] - target_delta).abs()
    short_row = valid.loc[valid["delta_diff"].idxmin()]
    return short_row.to_dict(), valid, otm


def find_strike_data(chain_df, target_strike):
    """Find the row for a given strike (or nearest). Returns dict with mid/src/bid/ask/volume/oi."""
    exact = chain_df[chain_df["strike"] == target_strike]
    if not exact.empty:
        row = exact.iloc[0].to_dict()
    else:
        df = chain_df.copy()
        df["_diff"] = (df["strike"] - target_strike).abs()
        row = df.nsmallest(1, "_diff").iloc[0].to_dict()
    mid, src = option_mid_ex(row)
    return {
        "mid": mid,
        "src": src,
        "bid": round(float(row.get("bid", 0) or 0), 2),
        "ask": round(float(row.get("ask", 0) or 0), 2),
        "volume": int(float(row.get("volume", 0) or 0)),
        "open_interest": int(float(row.get("openInterest", 0) or 0)),
    }


def classify_price_source(bid, ask):
    """Classify price source based on bid/ask availability and market hours.

    Returns one of: 'live_bid_ask_mid', 'prev_close_bid_ask_mid', 'last_trade_price'.
    """
    has_bid_ask = bid > 0 and ask > 0
    if has_bid_ask:
        return "live_bid_ask_mid" if is_market_open() else "prev_close_bid_ask_mid"
    return "last_trade_price"


def build_spread_metrics(short_mid, long_mid, short_strike, long_strike,
                         short_delta, side="put"):
    """Compute standard credit spread metrics.

    Args:
        short_mid: mid price of short leg
        long_mid: mid price of long leg
        short_strike, long_strike: strike prices
        short_delta: absolute delta of the short leg
        side: "put" for bull put / iron condor put side, "call" for bear call / iron condor call side

    Returns dict with: net_credit, spread_width, max_profit, max_loss, breakeven, ror, pop.
    """
    net_credit = round(short_mid - long_mid, 2)
    if side == "put":
        spread_width = round(short_strike - long_strike, 2)
        breakeven = round(short_strike - net_credit, 2)
    else:
        spread_width = round(long_strike - short_strike, 2)
        breakeven = round(short_strike + net_credit, 2)

    max_profit = round(net_credit * 100, 2)
    max_loss = round((spread_width - net_credit) * 100, 2)
    ror = round(net_credit / (spread_width - net_credit) * 100, 1) if spread_width > net_credit else 0.0
    pop = round((1 - short_delta) * 100, 1)

    return {
        "net_credit": net_credit,
        "spread_width": spread_width,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakeven": breakeven,
        "return_on_risk_pct": ror,
        "prob_profit_pct": pop,
    }


def compute_spread_pnl(short_mid, long_mid, net_credit, spread_width):
    """Compute current P&L for a credit spread position.

    Args:
        short_mid: current mid of short leg (None if unavailable)
        long_mid: current mid of long leg (None if unavailable)
        net_credit: original credit received per share
        spread_width: distance between strikes

    Returns dict with: current_spread_value, pnl_per_share, pnl_per_contract,
                       max_profit, max_loss, loss_pct_of_max.
    """
    max_loss = round((spread_width - net_credit) * 100, 2)
    max_profit = round(net_credit * 100, 2)

    if short_mid is not None and long_mid is not None:
        current_spread_value = round(short_mid - long_mid, 2)
        pnl_per_share = round(net_credit - current_spread_value, 2)
        pnl_per_contract = round(pnl_per_share * 100, 2)

        if max_loss > 0:
            loss_pct_of_max = round(max(0, -pnl_per_share * 100) / max_loss * 100, 1)
        else:
            loss_pct_of_max = 0.0
    else:
        current_spread_value = None
        pnl_per_share = None
        pnl_per_contract = None
        loss_pct_of_max = None

    return {
        "current_spread_value": current_spread_value,
        "pnl_per_share": pnl_per_share,
        "pnl_per_contract": pnl_per_contract,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "loss_pct_of_max": loss_pct_of_max,
    }
