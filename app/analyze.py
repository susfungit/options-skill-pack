"""Analyze, compare, expirations, ticker-info, and chain endpoints."""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import TICKER_RE, limiter
from app.tools import execute_tool

logger = logging.getLogger("options_skill_pack")
router = APIRouter()

# ── Analyzer endpoint (no Claude, no tokens) ────────────────────────────────

_STRATEGY_TO_TOOL = {
    "bull-put-spread": "find_bull_put_spread",
    "bear-call-spread": "find_bear_call_spread",
    "iron-condor": "find_iron_condor",
    "covered-call": "find_covered_call",
    "cash-secured-put": "find_cash_secured_put",
}


class StrategyType(str, Enum):
    bull_put_spread = "bull-put-spread"
    bear_call_spread = "bear-call-spread"
    iron_condor = "iron-condor"
    covered_call = "covered-call"
    cash_secured_put = "cash-secured-put"


class AnalyzeRequest(BaseModel):
    ticker: str
    strategy: StrategyType
    target_delta: Optional[float] = Field(None, gt=0, lt=1)
    dte_min: Optional[int] = Field(None, ge=1, le=365)
    dte_max: Optional[int] = Field(None, ge=1, le=365)
    spread_width: Optional[float] = Field(None, gt=0, le=50)
    expiry: Optional[str] = None


@router.post("/api/analyze")
@limiter.limit("30/minute")
async def analyze(request: Request, req: AnalyzeRequest):
    tool_name = _STRATEGY_TO_TOOL.get(req.strategy.value)
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")

    ticker = req.ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    tool_input = {"ticker": ticker}

    # Explicit request values override profile defaults (applied in execute_tool)
    if req.target_delta is not None:
        tool_input["target_delta"] = req.target_delta
    if req.expiry is not None:
        tool_input["expiry"] = req.expiry
    else:
        if req.dte_min is not None:
            tool_input["dte_min"] = req.dte_min
        if req.dte_max is not None:
            tool_input["dte_max"] = req.dte_max
    if req.spread_width is not None:
        tool_input["spread_width"] = req.spread_width

    result_json = execute_tool(tool_name, tool_input)
    return json.loads(result_json)


# ── Compare mode ──────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    ticker: str
    dte_min: Optional[int] = None
    dte_max: Optional[int] = None
    expiry: Optional[str] = None


def _suggest_strategy(trend: str, iv_level: str, percentile_52w: int = 50) -> dict:
    """Rules-based strategy suggestion from trend + IV level + 52-week position."""
    if trend == "bearish":
        if iv_level in ("high", "very_high"):
            return {
                "strategy": "bear-call-spread",
                "label": "Bear Call Spread",
                "reason": "Bearish trend with elevated IV \u2014 sell call spreads above resistance for rich premiums",
            }
        return {
            "strategy": "bear-call-spread",
            "label": "Bear Call Spread",
            "reason": "Bearish trend detected \u2014 sell call spreads above resistance",
        }
    if trend == "bullish":
        if iv_level == "low":
            return {
                "strategy": "covered-call",
                "label": "Covered Call",
                "reason": "Bullish trend with low IV \u2014 sell calls on owned stock for income",
            }
        return {
            "strategy": "bull-put-spread",
            "label": "Bull Put Spread",
            "reason": "Bullish trend with elevated IV \u2014 fat put premiums below support",
        }
    # neutral
    if iv_level == "low":
        return {
            "strategy": "covered-call",
            "label": "Covered Call",
            "reason": "Neutral market with low IV \u2014 covered calls capture what premium exists",
        }
    if percentile_52w <= 35:
        return {
            "strategy": "bull-put-spread",
            "label": "Bull Put Spread",
            "reason": "Near 52-week lows with elevated IV \u2014 sell puts below support for rich premiums",
        }
    return {
        "strategy": "iron-condor",
        "label": "Iron Condor",
        "reason": "Range-bound market with elevated IV \u2014 ideal for iron condor premium",
    }


def _fetch_market_context(ticker: str) -> dict:
    """Fetch trend + IV context for a ticker using yfinance. No Claude tokens."""
    try:
        import yfinance as yf

        tk = yf.Ticker(ticker)

        hist = tk.history(period="1y")
        if hist.empty or len(hist) < 2:
            return {"error": f"No price history for {ticker}"}

        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2])
        change_pct = round((current_price / prev_close - 1) * 100, 2) if prev_close else 0.0
        high_52w = float(hist["Close"].max())
        low_52w = float(hist["Close"].min())
        pct_range = high_52w - low_52w
        percentile_52w = round((current_price - low_52w) / pct_range * 100) if pct_range > 0 else 50

        change_5d = round((current_price / float(hist["Close"].iloc[-6]) - 1) * 100, 1) if len(hist) >= 6 else 0
        change_20d = round((current_price / float(hist["Close"].iloc[-21]) - 1) * 100, 1) if len(hist) >= 21 else 0

        if change_20d > 3:
            classification = "bullish"
        elif change_20d < -3:
            classification = "bearish"
        else:
            classification = "neutral"

        atm_iv_pct = None
        iv_level = "moderate"
        try:
            expirations = tk.options
            if expirations:
                chain = tk.option_chain(expirations[0])
                all_strikes = []
                for df in [chain.puts, chain.calls]:
                    if not df.empty:
                        df = df[df["impliedVolatility"] > 0].copy()
                        if not df.empty:
                            df["dist"] = (df["strike"] - current_price).abs()
                            nearest = df.nsmallest(2, "dist")
                            all_strikes.append(nearest["impliedVolatility"].mean())
                if all_strikes:
                    atm_iv = sum(all_strikes) / len(all_strikes)
                    atm_iv_pct = round(atm_iv * 100, 1)
        except Exception:
            pass

        if atm_iv_pct is not None:
            if atm_iv_pct < 20:
                iv_level = "low"
            elif atm_iv_pct < 40:
                iv_level = "moderate"
            elif atm_iv_pct < 60:
                iv_level = "high"
            else:
                iv_level = "very_high"

        suggestion = _suggest_strategy(classification, iv_level, percentile_52w)

        return {
            "current_price": round(current_price, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": change_pct,
            "trend": {
                "change_5d_pct": change_5d,
                "change_20d_pct": change_20d,
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "percentile_52w": percentile_52w,
                "classification": classification,
            },
            "iv": {
                "atm_iv_pct": atm_iv_pct,
                "level": iv_level,
            },
            "suggestion": suggestion,
        }

    except Exception as e:
        logger.error("Market context fetch failed: %s", e)
        return {"error": "Failed to fetch market context"}


def _pick_best_strategy(bps, bcs, ic, cc, csp) -> dict | None:
    """Rank strategies by actual results (return + probability composite)."""
    candidates = []
    for key, label, d in [
        ("bull-put-spread", "Bull Put Spread", bps),
        ("bear-call-spread", "Bear Call Spread", bcs),
        ("iron-condor", "Iron Condor", ic),
        ("covered-call", "Covered Call", cc),
        ("cash-secured-put", "Cash-Secured Put", csp),
    ]:
        if not d or d.get("error"):
            continue
        ret = d.get("return_on_risk_pct") or d.get("annualized_return_pct") or 0
        prob = d.get("prob_profit_pct")
        if prob is None and "prob_called_pct" in d:
            prob = 100 - d["prob_called_pct"]
        if prob is None:
            prob = 0
        score = ret * 0.4 + prob * 0.6
        candidates.append((score, key, label, ret, prob))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _score, key, label, ret, prob = candidates[0]
    return {
        "strategy": key,
        "label": label,
        "reason": f"Best risk/reward — {ret}% return, {prob}% prob profit",
    }


@router.post("/api/analyze/compare")
@limiter.limit("10/minute")
async def analyze_compare(request: Request, req: CompareRequest):
    """Run all 5 selectors + market context in parallel and return results."""
    ticker = req.ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    def _build_input(strategy_key: str) -> dict:
        # Profile defaults (delta, dte_min, dte_max, spread_width) applied in execute_tool
        inp = {"ticker": ticker}
        if req.expiry is not None:
            inp["expiry"] = req.expiry
        else:
            if req.dte_min is not None:
                inp["dte_min"] = req.dte_min
            if req.dte_max is not None:
                inp["dte_max"] = req.dte_max
        return inp

    async def run_tool(tool_name, strategy_key):
        result_json = await asyncio.to_thread(execute_tool, tool_name, _build_input(strategy_key))
        return json.loads(result_json)

    bps, bcs, ic, cc, csp, market_ctx = await asyncio.gather(
        run_tool("find_bull_put_spread", "bull-put-spread"),
        run_tool("find_bear_call_spread", "bear-call-spread"),
        run_tool("find_iron_condor", "iron-condor"),
        run_tool("find_covered_call", "covered-call"),
        run_tool("find_cash_secured_put", "cash-secured-put"),
        asyncio.to_thread(_fetch_market_context, ticker),
    )

    if market_ctx and not market_ctx.get("error"):
        market_ctx["trend_pick"] = market_ctx.get("suggestion")
        best = _pick_best_strategy(bps, bcs, ic, cc, csp)
        if best:
            market_ctx["suggestion"] = best

    return {
        "ticker": ticker,
        "bull_put_spread": bps,
        "bear_call_spread": bcs,
        "iron_condor": ic,
        "covered_call": cc,
        "cash_secured_put": csp,
        "market_context": market_ctx,
    }


# ── Expirations endpoint ─────────────────────────────────────────────────────

@router.get("/api/expirations/{ticker}")
async def get_expirations(ticker: str):
    """Return available option expiry dates for a ticker."""
    ticker = ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    def _fetch():
        import yfinance as yf
        tk = yf.Ticker(ticker)
        return list(tk.options)

    try:
        expirations = await asyncio.to_thread(_fetch)
        return {"ticker": ticker, "expirations": expirations}
    except Exception as e:
        logger.error("Expirations fetch failed for %s: %s", ticker, e)
        return {"ticker": ticker, "expirations": [], "error": "Failed to fetch expirations"}


# ── Ticker info (company name, cached) ─────────────────────────────────────

_ticker_name_cache: dict[str, str] = {}


@router.get("/api/ticker-info/{ticker}")
async def ticker_info(ticker: str):
    """Return company short name for a ticker, cached in memory."""
    ticker = ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    if ticker in _ticker_name_cache:
        return {"ticker": ticker, "name": _ticker_name_cache[ticker]}

    def _fetch():
        import yfinance as yf
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        return info.get("shortName") or info.get("longName") or ticker

    try:
        name = await asyncio.to_thread(_fetch)
        _ticker_name_cache[ticker] = name
        return {"ticker": ticker, "name": name}
    except Exception:
        return {"ticker": ticker, "name": ticker}


# ── Chain viewer (no Claude, no tokens) ─────────────────────────────────────

class ChainRequest(BaseModel):
    ticker: str
    expiry: str
    side: str = "both"


@router.post("/api/chain")
@limiter.limit("30/minute")
async def get_chain(request: Request, req: ChainRequest):
    """Fetch the full option chain for a ticker + expiry."""
    ticker = req.ticker.upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    try:
        datetime.strptime(req.expiry, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expiry format (YYYY-MM-DD)")
    if req.side not in ("puts", "calls", "both"):
        raise HTTPException(status_code=400, detail="side must be puts, calls, or both")

    script = os.path.join(os.path.dirname(__file__), "fetch_chain_view.py")
    result = await asyncio.to_thread(
        subprocess.run,
        ["python3", script, ticker, req.expiry, req.side],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("Chain fetch failed for %s %s: %s", ticker, req.expiry, result.stderr.strip())
        raise HTTPException(status_code=500, detail="Chain fetch failed")
    return json.loads(result.stdout.strip())
