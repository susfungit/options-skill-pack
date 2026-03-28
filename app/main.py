"""FastAPI app for the Options Skill Pack."""

import copy
import os
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import anthropic

from app.tools import TOOLS, execute_tool
from app.prompts import SYSTEM_PROMPT, SKILL_GUIDANCE

app = FastAPI(title="Options Skill Pack")

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(PROJECT_ROOT, "portfolio.json")
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")

DEFAULT_MODEL = "claude-sonnet-4-20250514"

DEFAULT_PROFILE = {
    "name": "",
    "model": DEFAULT_MODEL,
    "strategy_defaults": {
        "bull-put-spread": {"delta": 0.20, "dte_min": 35, "dte_max": 45, "spread_width": 10},
        "bear-call-spread": {"delta": 0.20, "dte_min": 35, "dte_max": 45, "spread_width": 10},
        "iron-condor": {"delta": 0.16, "dte_min": 35, "dte_max": 45},
        "covered-call": {"delta": 0.30, "dte_min": 30, "dte_max": 45},
        "cash-secured-put": {"delta": 0.25, "dte_min": 30, "dte_max": 45},
    },
    "profit_rules": {
        "close_pct": 75,
        "consider_pct": 50,
        "near_expiry_pct": 25,
        "near_expiry_dte": 14,
    },
    "chat_history_limit": 4,
}

# ── Claude API client ────────────────────────────────────────────────────────

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="CLAUDE_API_KEY or ANTHROPIC_API_KEY environment variable not set",
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


@app.get("/api/models")
async def list_models():
    try:
        client = get_client()
        models = client.models.list()
        cutoff = datetime.now(tz=models.data[0].created_at.tzinfo) if models.data else datetime.now()
        cutoff = cutoff.replace(year=cutoff.year - 1)
        result = [
            {"id": m.id, "display_name": m.display_name}
            for m in models.data
            if m.created_at >= cutoff
        ]
        result.sort(key=lambda m: m["id"])
        return {"models": result}
    except HTTPException:
        return {"models": [{"id": DEFAULT_MODEL, "display_name": "Claude Sonnet 4"}]}


# ── Chat models & endpoint ───────────────────────────────────────────────────

class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Message] = []


class ChatResponse(BaseModel):
    response: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        client = get_client()
    except HTTPException as e:
        return ChatResponse(response=f"**Configuration error:** {e.detail}")

    messages = [{"role": m.role, "content": m.content} for m in req.history]
    messages.append({"role": "user", "content": req.message})

    model = _read_profile().get("model", DEFAULT_MODEL)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        while response.stop_reason == "tool_use":
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            tool_results = []

            for tool_use in tool_uses:
                result_json = execute_tool(tool_use.name, tool_use.input)
                guidance = SKILL_GUIDANCE.get(tool_use.name, "")
                if guidance:
                    tool_result_content = (
                        f"Tool output:\n{result_json}\n\n"
                        f"---\n{guidance}"
                    )
                else:
                    tool_result_content = result_json

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": tool_result_content,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

        text_parts = [block.text for block in response.content if hasattr(block, "text")]
        return ChatResponse(response="\n".join(text_parts))

    except anthropic.BadRequestError as e:
        return ChatResponse(response=f"**API error:** {e.message}")
    except anthropic.AuthenticationError as e:
        return ChatResponse(response="**Authentication failed.** Check your ANTHROPIC_API_KEY.")
    except Exception:
        return ChatResponse(response="**Error:** An unexpected error occurred. Check server logs.")


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


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    tool_name = _STRATEGY_TO_TOOL.get(req.strategy.value)
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")

    tool_input = {"ticker": req.ticker.upper()}

    # Apply profile defaults, then override with explicit request values
    profile = _read_profile()
    defaults = profile["strategy_defaults"].get(req.strategy.value, {})
    if req.target_delta is not None:
        tool_input["target_delta"] = req.target_delta
    elif "delta" in defaults:
        tool_input["target_delta"] = defaults["delta"]
    if req.expiry is not None:
        tool_input["expiry"] = req.expiry
    else:
        if req.dte_min is not None:
            tool_input["dte_min"] = req.dte_min
        elif "dte_min" in defaults:
            tool_input["dte_min"] = defaults["dte_min"]
        if req.dte_max is not None:
            tool_input["dte_max"] = req.dte_max
        elif "dte_max" in defaults:
            tool_input["dte_max"] = defaults["dte_max"]
    if req.spread_width is not None:
        tool_input["spread_width"] = req.spread_width
    elif "spread_width" in defaults:
        tool_input["spread_width"] = defaults["spread_width"]

    result_json = execute_tool(tool_name, tool_input)
    return json.loads(result_json)


class CompareRequest(BaseModel):
    ticker: str
    dte_min: Optional[int] = None
    dte_max: Optional[int] = None
    expiry: Optional[str] = None


# ── Market context for compare mode ──────────────────────────────────────────

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
    # Neutral + elevated IV: consider 52-week position
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
        from datetime import datetime

        tk = yf.Ticker(ticker)

        # --- Price trend ---
        hist = tk.history(period="1y")
        if hist.empty or len(hist) < 2:
            return {"error": f"No price history for {ticker}"}

        current_price = float(hist["Close"].iloc[-1])
        high_52w = float(hist["Close"].max())
        low_52w = float(hist["Close"].min())
        pct_range = high_52w - low_52w
        percentile_52w = round((current_price - low_52w) / pct_range * 100) if pct_range > 0 else 50

        # 5-day and 20-day changes
        change_5d = round((current_price / float(hist["Close"].iloc[-6]) - 1) * 100, 1) if len(hist) >= 6 else 0
        change_20d = round((current_price / float(hist["Close"].iloc[-21]) - 1) * 100, 1) if len(hist) >= 21 else 0

        if change_20d > 3:
            classification = "bullish"
        elif change_20d < -3:
            classification = "bearish"
        else:
            classification = "neutral"

        # --- ATM IV from nearest expiry ---
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
            pass  # IV is optional — suggestion still works with trend alone

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
        return {"error": str(e)}


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


@app.post("/api/analyze/compare")
async def analyze_compare(req: CompareRequest):
    """Run all 4 selectors + market context in parallel and return results."""
    import asyncio

    ticker = req.ticker.upper()
    profile = _read_profile()
    strategy_defaults = profile["strategy_defaults"]

    def _build_input(strategy_key: str) -> dict:
        defaults = strategy_defaults.get(strategy_key, {})
        inp = {"ticker": ticker}
        if req.expiry is not None:
            inp["expiry"] = req.expiry
        else:
            if req.dte_min is not None:
                inp["dte_min"] = req.dte_min
            elif "dte_min" in defaults:
                inp["dte_min"] = defaults["dte_min"]
            if req.dte_max is not None:
                inp["dte_max"] = req.dte_max
            elif "dte_max" in defaults:
                inp["dte_max"] = defaults["dte_max"]
        if "delta" in defaults:
            inp["target_delta"] = defaults["delta"]
        if "spread_width" in defaults:
            inp["spread_width"] = defaults["spread_width"]
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

    # Add data-driven pick alongside rules-based trend pick
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

@app.get("/api/expirations/{ticker}")
async def get_expirations(ticker: str):
    """Return available option expiry dates for a ticker."""
    import asyncio
    ticker = ticker.upper()
    def _fetch():
        import yfinance as yf
        tk = yf.Ticker(ticker)
        return list(tk.options)
    try:
        expirations = await asyncio.to_thread(_fetch)
        return {"ticker": ticker, "expirations": expirations}
    except Exception as e:
        return {"ticker": ticker, "expirations": [], "error": str(e)}


# ── Chain viewer (no Claude, no tokens) ─────────────────────────────────────

import re
import subprocess

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


class ChainRequest(BaseModel):
    ticker: str
    expiry: str
    side: str = "both"


@app.post("/api/chain")
async def get_chain(req: ChainRequest):
    """Fetch the full option chain for a ticker + expiry."""
    import asyncio

    ticker = req.ticker.upper()
    if not _TICKER_RE.match(ticker):
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
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Chain fetch failed")
    return json.loads(result.stdout.strip())


# ── Portfolio helpers ────────────────────────────────────────────────────────

def _read_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_PATH):
        return []
    with open(PORTFOLIO_PATH, "r") as f:
        return json.load(f)


def _write_portfolio(data: list[dict]):
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Profile helpers ──────────────────────────────────────────────────────────


def _read_profile() -> dict:
    """Return saved profile merged over defaults (so new fields always exist)."""
    profile = copy.deepcopy(DEFAULT_PROFILE)
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r") as f:
            saved = json.load(f)
        for key in profile:
            if key in saved and isinstance(profile[key], dict):
                profile[key].update(saved[key])
            elif key in saved:
                profile[key] = saved[key]
    return profile


def _write_profile(data: dict):
    with open(PROFILE_PATH, "w") as f:
        json.dump(data, f, indent=2)


@app.get("/api/profile")
async def get_profile():
    return _read_profile()


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    strategy_defaults: Optional[dict] = None
    profit_rules: Optional[dict] = None
    chat_history_limit: Optional[int] = None


@app.put("/api/profile")
async def update_profile(req: ProfileUpdate):
    profile = _read_profile()
    if req.name is not None:
        profile["name"] = req.name
    if req.model is not None:
        profile["model"] = req.model
    if req.strategy_defaults is not None:
        profile["strategy_defaults"] = req.strategy_defaults
    if req.profit_rules is not None:
        profile["profit_rules"] = req.profit_rules
    if req.chat_history_limit is not None:
        profile["chat_history_limit"] = max(2, req.chat_history_limit)
    _write_profile(profile)
    return profile


def _find_position(portfolio: list[dict], pos_id: str) -> tuple[int, dict]:
    """Find position by ID, return (index, position) or raise 404."""
    for i, p in enumerate(portfolio):
        if p.get("id") == pos_id:
            return i, p
    raise HTTPException(status_code=404, detail="Position not found")


# ── Portfolio models ─────────────────────────────────────────────────────────

class Leg(BaseModel):
    type: str
    action: str
    strike: float
    price: Optional[float] = None


class Position(BaseModel):
    label: str
    strategy: str
    ticker: str
    legs: list[Leg]
    net_credit: float
    expiry: str
    contracts: int = 1
    opened: Optional[str] = None
    status: str = "open"
    cost_basis: Optional[float] = None


# ── Portfolio endpoints ──────────────────────────────────────────────────────

@app.get("/api/portfolio")
async def list_portfolio():
    portfolio = _read_portfolio()
    # Backfill IDs for legacy positions
    changed = False
    for p in portfolio:
        if "id" not in p:
            p["id"] = uuid.uuid4().hex[:8]
            changed = True
    if changed:
        _write_portfolio(portfolio)
    return portfolio


@app.post("/api/portfolio")
async def add_position(position: Position):
    portfolio = _read_portfolio()
    entry = position.model_dump(exclude_none=True)
    entry["id"] = uuid.uuid4().hex[:8]
    portfolio.append(entry)
    _write_portfolio(portfolio)
    return {"status": "ok", "id": entry["id"]}


@app.post("/api/portfolio/check")
async def check_all_positions():
    """Run monitors for all open positions, save zones to portfolio.json."""
    portfolio = _read_portfolio()
    results = []

    for i, p in enumerate(portfolio):
        if p.get("status") != "open":
            results.append({"id": p.get("id"), "zone": "CLOSED"})
            continue

        zone_data = _check_single_position(p)
        portfolio[i].update(zone_data)
        results.append({"id": p.get("id"), **zone_data})

    _write_portfolio(portfolio)
    return results


@app.put("/api/portfolio/{pos_id}")
async def update_position(pos_id: str, position: Position):
    portfolio = _read_portfolio()
    idx, existing = _find_position(portfolio, pos_id)
    updated = position.model_dump(exclude_none=True)
    updated["id"] = pos_id
    portfolio[idx] = updated
    _write_portfolio(portfolio)
    return {"status": "ok"}


class CloseRequest(BaseModel):
    notes: Optional[str] = None
    close_price: Optional[float] = None


@app.post("/api/portfolio/{pos_id}/close")
async def close_position(pos_id: str, req: CloseRequest = CloseRequest()):
    from datetime import date
    portfolio = _read_portfolio()
    idx, p = _find_position(portfolio, pos_id)
    p["status"] = "closed"
    p["closed_date"] = date.today().isoformat()

    if req.close_price is not None:
        p["close_price"] = req.close_price
        pnl_per_share = p["net_credit"] - req.close_price
        contracts = p.get("contracts", 1)
        p["closed_pnl"] = round(pnl_per_share * 100 * contracts, 2)

    if req.notes:
        p["close_notes"] = req.notes

    _write_portfolio(portfolio)
    return {"status": "ok"}


@app.post("/api/portfolio/{pos_id}/reopen")
async def reopen_position(pos_id: str):
    portfolio = _read_portfolio()
    idx, p = _find_position(portfolio, pos_id)
    p["status"] = "open"
    _write_portfolio(portfolio)
    return {"status": "ok"}


@app.delete("/api/portfolio/{pos_id}")
async def delete_position(pos_id: str):
    portfolio = _read_portfolio()
    idx, removed = _find_position(portfolio, pos_id)
    portfolio.pop(idx)
    _write_portfolio(portfolio)
    return {"status": "ok", "removed": removed}


# ── Zone classification (no Claude, no tokens) ──────────────────────────

def _classify_zone_spread(buffer_pct: float, loss_pct: float, dte: int) -> str:
    """Classify zone for put spreads and iron condors."""
    # DTE adjustments
    if dte <= 5:
        thresholds = [(9, 20), (5, 40), (3, 65), (1, 85)]
    elif dte >= 30:
        thresholds = [(7, 20), (3, 40), (2, 65), (0, 85)]
    else:
        thresholds = [(8, 20), (4, 40), (2, 65), (0, 85)]

    if buffer_pct <= 0 or loss_pct > 85:
        return "ACT NOW"
    if buffer_pct <= thresholds[3][0] or loss_pct > thresholds[3][1]:
        return "DANGER"
    if buffer_pct <= thresholds[2][0] or loss_pct > thresholds[2][1]:
        return "WARNING"
    if buffer_pct <= thresholds[1][0] or loss_pct > thresholds[1][1]:
        return "WATCH"
    if buffer_pct > thresholds[0][0] and loss_pct < thresholds[0][1]:
        return "SAFE"
    return "WATCH"


def _classify_zone_covered_call(buffer_pct: float, call_value: float, credit: float, dte: int) -> str:
    """Classify zone for covered calls."""
    ratio = call_value / credit if credit > 0 else 0

    if buffer_pct <= 0 or ratio > 5:
        return "ACT NOW"
    if buffer_pct <= 2 or ratio > 3:
        return "DANGER"
    if buffer_pct <= 4 or ratio > 2:
        return "WARNING"
    if buffer_pct <= 8 or ratio > 1.5:
        return "WATCH"
    return "SAFE"


def _position_suggestion(zone: str, strategy: str, pnl: float, net_credit: float,
                         contracts: int, dte: int, buffer_pct: float) -> str | None:
    """Rules-based suggestion for an open position. Returns a short action hint."""
    profile = _read_profile()
    rules = profile["profit_rules"]
    close_pct = rules.get("close_pct", 75)
    consider_pct = rules.get("consider_pct", 50)
    near_expiry_pct = rules.get("near_expiry_pct", 25)
    near_expiry_dte = rules.get("near_expiry_dte", 14)

    max_profit = net_credit * 100 * contracts
    profit_pct = (pnl / max_profit * 100) if max_profit > 0 else 0

    # Profit-taking (only when position is profitable)
    if pnl > 0:
        if profit_pct >= close_pct:
            return f"Close candidate \u2014 captured {close_pct}%+ of max profit"
        if profit_pct >= consider_pct:
            return f"Consider closing \u2014 captured {consider_pct}%+ of max profit"
        if dte <= near_expiry_dte and profit_pct >= near_expiry_pct:
            return "Near expiry with profit \u2014 close to avoid gamma risk"

    # Covered call specific
    if strategy == "covered-call" and buffer_pct is not None and buffer_pct <= 2:
        return "Shares may be called away \u2014 close call to keep shares or let assign"

    # Zone-based defensive suggestions
    if zone == "ACT NOW":
        return "Close immediately or roll defensively"
    if zone == "DANGER":
        return "Roll or close to limit further loss"
    if zone == "WARNING":
        return "Consider rolling or reducing position size"
    if zone == "WATCH":
        if dte <= 7:
            return "Expiry imminent \u2014 decide: close, roll, or let expire"
        return "Monitor closely \u2014 prepare roll if it deteriorates"

    # Safe with low DTE
    if zone == "SAFE" and dte <= 7 and pnl >= 0:
        return "Expiring soon in profit \u2014 let expire or close to lock in"

    return None


def _check_single_position(p: dict) -> dict:
    """Run the monitor script for a single position and return zone data."""
    from datetime import datetime, timezone

    strategy = p.get("strategy", "")
    ticker = p.get("ticker", "")
    expiry = p.get("expiry", "")
    net_credit = p.get("net_credit", 0)

    try:
        if strategy == "bull-put-spread":
            short = next(l for l in p["legs"] if l["action"] == "sell")
            long = next(l for l in p["legs"] if l["action"] == "buy")
            result_json = execute_tool("check_bull_put_spread", {
                "ticker": ticker,
                "short_strike": short["strike"],
                "long_strike": long["strike"],
                "net_credit": net_credit,
                "expiry": expiry,
            })
            data = json.loads(result_json)
            if "error" in data:
                return {"zone": "UNKNOWN", "zone_error": data["error"]}

            zone = _classify_zone_spread(
                data.get("buffer_pct", 0),
                data.get("loss_pct_of_max", 0),
                data.get("dte", 30),
            )
            suggestion = _position_suggestion(
                zone, strategy, data.get("pnl_per_contract", 0),
                net_credit, p.get("contracts", 1), data.get("dte", 30),
                data.get("buffer_pct", 0),
            )
            result = {
                "zone": zone,
                "zone_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
                "chain_data": {
                    "short_leg": {
                        "bid": data.get("short_put", {}).get("bid"),
                        "ask": data.get("short_put", {}).get("ask"),
                        "iv_pct": data.get("short_put", {}).get("current_iv_pct"),
                        "delta": data.get("short_put", {}).get("current_delta"),
                        "volume": data.get("short_put", {}).get("volume"),
                        "open_interest": data.get("short_put", {}).get("open_interest"),
                    },
                    "long_leg": {
                        "bid": data.get("long_put", {}).get("bid"),
                        "ask": data.get("long_put", {}).get("ask"),
                        "volume": data.get("long_put", {}).get("volume"),
                        "open_interest": data.get("long_put", {}).get("open_interest"),
                    },
                    "cost_to_close": data.get("cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            return result

        elif strategy == "bear-call-spread":
            short = next(l for l in p["legs"] if l["action"] == "sell")
            long = next(l for l in p["legs"] if l["action"] == "buy")
            result_json = execute_tool("check_bear_call_spread", {
                "ticker": ticker,
                "short_strike": short["strike"],
                "long_strike": long["strike"],
                "net_credit": net_credit,
                "expiry": expiry,
            })
            data = json.loads(result_json)
            if "error" in data:
                return {"zone": "UNKNOWN", "zone_error": data["error"]}

            zone = _classify_zone_spread(
                data.get("buffer_pct", 0),
                data.get("loss_pct_of_max", 0),
                data.get("dte", 30),
            )
            suggestion = _position_suggestion(
                zone, strategy, data.get("pnl_per_contract", 0),
                net_credit, p.get("contracts", 1), data.get("dte", 30),
                data.get("buffer_pct", 0),
            )
            result = {
                "zone": zone,
                "zone_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
                "chain_data": {
                    "short_leg": {
                        "bid": data.get("short_call", {}).get("bid"),
                        "ask": data.get("short_call", {}).get("ask"),
                        "iv_pct": data.get("short_call", {}).get("current_iv_pct"),
                        "delta": data.get("short_call", {}).get("current_delta"),
                        "volume": data.get("short_call", {}).get("volume"),
                        "open_interest": data.get("short_call", {}).get("open_interest"),
                    },
                    "long_leg": {
                        "bid": data.get("long_call", {}).get("bid"),
                        "ask": data.get("long_call", {}).get("ask"),
                        "volume": data.get("long_call", {}).get("volume"),
                        "open_interest": data.get("long_call", {}).get("open_interest"),
                    },
                    "cost_to_close": data.get("cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            return result

        elif strategy == "iron-condor":
            sp = next(l for l in p["legs"] if l["type"] == "put" and l["action"] == "sell")
            lp = next(l for l in p["legs"] if l["type"] == "put" and l["action"] == "buy")
            sc = next(l for l in p["legs"] if l["type"] == "call" and l["action"] == "sell")
            lc = next(l for l in p["legs"] if l["type"] == "call" and l["action"] == "buy")
            result_json = execute_tool("check_iron_condor", {
                "ticker": ticker,
                "short_put": sp["strike"],
                "long_put": lp["strike"],
                "short_call": sc["strike"],
                "long_call": lc["strike"],
                "net_credit": net_credit,
                "expiry": expiry,
            })
            data = json.loads(result_json)
            if "error" in data:
                return {"zone": "UNKNOWN", "zone_error": data["error"]}

            zone = _classify_zone_spread(
                data.get("worst_buffer_pct", 0),
                data.get("loss_pct_of_max", 0),
                data.get("dte", 30),
            )
            suggestion = _position_suggestion(
                zone, strategy, data.get("pnl_per_contract", 0),
                net_credit, p.get("contracts", 1), data.get("dte", 30),
                data.get("worst_buffer_pct", 0),
            )
            result = {
                "zone": zone,
                "zone_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "buffer_pct": data.get("worst_buffer_pct"),
                "worst_side": data.get("worst_side"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
                "chain_data": {
                    "put_side": {
                        "short_leg": {
                            "bid": data.get("short_put", {}).get("bid"),
                            "ask": data.get("short_put", {}).get("ask"),
                            "iv_pct": data.get("short_put", {}).get("current_iv_pct"),
                            "delta": data.get("short_put", {}).get("current_delta"),
                            "volume": data.get("short_put", {}).get("volume"),
                            "open_interest": data.get("short_put", {}).get("open_interest"),
                        },
                        "long_leg": {
                            "bid": data.get("long_put", {}).get("bid"),
                            "ask": data.get("long_put", {}).get("ask"),
                            "volume": data.get("long_put", {}).get("volume"),
                            "open_interest": data.get("long_put", {}).get("open_interest"),
                        },
                    },
                    "call_side": {
                        "short_leg": {
                            "bid": data.get("short_call", {}).get("bid"),
                            "ask": data.get("short_call", {}).get("ask"),
                            "iv_pct": data.get("short_call", {}).get("current_iv_pct"),
                            "delta": data.get("short_call", {}).get("current_delta"),
                            "volume": data.get("short_call", {}).get("volume"),
                            "open_interest": data.get("short_call", {}).get("open_interest"),
                        },
                        "long_leg": {
                            "bid": data.get("long_call", {}).get("bid"),
                            "ask": data.get("long_call", {}).get("ask"),
                            "volume": data.get("long_call", {}).get("volume"),
                            "open_interest": data.get("long_call", {}).get("open_interest"),
                        },
                    },
                    "cost_to_close": data.get("cost_to_close"),
                    "put_cost_to_close": data.get("put_cost_to_close"),
                    "call_cost_to_close": data.get("call_cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            return result

        elif strategy == "covered-call":
            call = next(l for l in p["legs"] if l["type"] == "call")
            tool_input = {
                "ticker": ticker,
                "short_call_strike": call["strike"],
                "net_credit": net_credit,
                "expiry": expiry,
            }
            if p.get("cost_basis"):
                tool_input["cost_basis"] = p["cost_basis"]

            result_json = execute_tool("check_covered_call", tool_input)
            data = json.loads(result_json)
            if "error" in data:
                return {"zone": "UNKNOWN", "zone_error": data["error"]}

            zone = _classify_zone_covered_call(
                data.get("buffer_pct", 0),
                data.get("current_call_value", 0) or 0,
                net_credit,
                data.get("dte", 30),
            )
            suggestion = _position_suggestion(
                zone, strategy, data.get("pnl_per_contract", 0),
                net_credit, p.get("contracts", 1), data.get("dte", 30),
                data.get("buffer_pct", 0),
            )
            result = {
                "zone": zone,
                "zone_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "chain_data": {
                    "short_leg": {
                        "bid": data.get("short_call", {}).get("bid"),
                        "ask": data.get("short_call", {}).get("ask"),
                        "iv_pct": data.get("short_call", {}).get("current_iv_pct"),
                        "delta": data.get("short_call", {}).get("current_delta"),
                        "volume": data.get("short_call", {}).get("volume"),
                        "open_interest": data.get("short_call", {}).get("open_interest"),
                    },
                    "cost_to_close": data.get("cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            return result

        elif strategy == "cash-secured-put":
            put = next(l for l in p["legs"] if l["type"] == "put")
            result_json = execute_tool("check_cash_secured_put", {
                "ticker": ticker,
                "short_put_strike": put["strike"],
                "net_credit": net_credit,
                "expiry": expiry,
            })
            data = json.loads(result_json)
            if "error" in data:
                return {"zone": "UNKNOWN", "zone_error": data["error"]}

            zone = _classify_zone_spread(
                data.get("buffer_pct", 0),
                data.get("loss_pct_of_max", 0),
                data.get("dte", 30),
            )
            suggestion = _position_suggestion(
                zone, strategy, data.get("pnl_per_contract", 0),
                net_credit, p.get("contracts", 1), data.get("dte", 30),
                data.get("buffer_pct", 0),
            )
            result = {
                "zone": zone,
                "zone_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
                "chain_data": {
                    "short_leg": {
                        "bid": data.get("short_put", {}).get("bid"),
                        "ask": data.get("short_put", {}).get("ask"),
                        "iv_pct": data.get("short_put", {}).get("current_iv_pct"),
                        "delta": data.get("short_put", {}).get("current_delta"),
                        "volume": data.get("short_put", {}).get("volume"),
                        "open_interest": data.get("short_put", {}).get("open_interest"),
                    },
                    "cost_to_close": data.get("cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            return result

        else:
            return {"zone": "UNKNOWN", "zone_error": f"Unsupported strategy: {strategy}"}

    except Exception as e:
        return {"zone": "UNKNOWN", "zone_error": str(e)}


@app.post("/api/portfolio/{pos_id}/check")
async def check_single(pos_id: str):
    """Run monitor for a single position, save zone to portfolio.json."""
    portfolio = _read_portfolio()
    idx, p = _find_position(portfolio, pos_id)

    zone_data = _check_single_position(p)
    portfolio[idx].update(zone_data)
    _write_portfolio(portfolio)
    return {"id": pos_id, **zone_data}


# ── Static files ─────────────────────────────────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(static_dir, "index.html"))
