"""Portfolio CRUD, profile endpoints, zone classification, and position monitoring."""

import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import config
from app.config import MODEL_RE, TICKER_RE, limiter
from app.storage import (
    read_portfolio, write_portfolio, read_profile, write_profile,
    read_watchlist, write_watchlist,
    _portfolio_lock, _atomic_write_json,
)
from app.tools import execute_tool

logger = logging.getLogger("options_skill_pack")
router = APIRouter()


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
    close_price: Optional[float] = None
    closed_pnl: Optional[float] = None
    closed_date: Optional[str] = None
    close_notes: Optional[str] = None


class CloseRequest(BaseModel):
    notes: Optional[str] = None
    close_price: Optional[float] = None


class WatchlistLeg(BaseModel):
    type: str
    action: str
    strike: float
    original_mid: Optional[float] = None


class WatchlistTrade(BaseModel):
    ticker: str
    strategy: str
    expiry: str
    legs: list[WatchlistLeg]
    original_credit: float
    original_return_pct: Optional[float] = None
    stock_price_at_save: Optional[float] = None
    note: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    strategy_defaults: Optional[dict] = None
    profit_rules: Optional[dict] = None
    chat_history_limit: Optional[int] = None


# ── Profile endpoints ────────────────────────────────────────────────────────

@router.get("/api/profile")
async def get_profile():
    return read_profile()


@router.put("/api/profile")
async def update_profile(req: ProfileUpdate):
    profile = read_profile()
    if req.name is not None:
        profile["name"] = req.name
    if req.model is not None:
        if not MODEL_RE.match(req.model):
            raise HTTPException(status_code=400, detail="Invalid model ID format")
        profile["model"] = req.model
    if req.strategy_defaults is not None:
        profile["strategy_defaults"] = req.strategy_defaults
    if req.profit_rules is not None:
        profile["profit_rules"] = req.profit_rules
    if req.chat_history_limit is not None:
        profile["chat_history_limit"] = max(2, req.chat_history_limit)
    write_profile(profile)
    return profile


# ── Portfolio helpers ────────────────────────────────────────────────────────

def _find_position(portfolio: list[dict], pos_id: str) -> tuple[int, dict]:
    """Find position by ID, return (index, position) or raise 404."""
    for i, p in enumerate(portfolio):
        if p.get("id") == pos_id:
            return i, p
    raise HTTPException(status_code=404, detail="Position not found")


# ── Portfolio CRUD endpoints ─────────────────────────────────────────────────

@router.get("/api/portfolio")
async def list_portfolio():
    portfolio = read_portfolio()
    changed = False
    for p in portfolio:
        if "id" not in p:
            p["id"] = uuid.uuid4().hex[:8]
            changed = True
    if changed:
        write_portfolio(portfolio)
    return portfolio


@router.post("/api/portfolio")
async def add_position(position: Position):
    portfolio = read_portfolio()
    entry = position.model_dump(exclude_none=True)
    entry["id"] = uuid.uuid4().hex[:8]
    portfolio.append(entry)
    write_portfolio(portfolio)
    return {"status": "ok", "id": entry["id"]}


@router.put("/api/portfolio/{pos_id}")
async def update_position(pos_id: str, position: Position):
    portfolio = read_portfolio()
    idx, existing = _find_position(portfolio, pos_id)
    updated = position.model_dump(exclude_none=True)
    updated["id"] = pos_id
    portfolio[idx] = updated
    write_portfolio(portfolio)
    return {"status": "ok"}


@router.post("/api/portfolio/{pos_id}/close")
async def close_position(pos_id: str, req: CloseRequest = CloseRequest()):
    portfolio = read_portfolio()
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

    write_portfolio(portfolio)
    return {"status": "ok"}


@router.post("/api/portfolio/{pos_id}/reopen")
async def reopen_position(pos_id: str):
    portfolio = read_portfolio()
    idx, p = _find_position(portfolio, pos_id)
    p["status"] = "open"
    write_portfolio(portfolio)
    return {"status": "ok"}


@router.delete("/api/portfolio/{pos_id}")
async def delete_position(pos_id: str):
    portfolio = read_portfolio()
    idx, removed = _find_position(portfolio, pos_id)
    portfolio.pop(idx)
    write_portfolio(portfolio)
    return {"status": "ok", "removed": removed}


# ── Zone classification (no Claude, no tokens) ──────────────────────────

def _classify_zone_spread(buffer_pct: float, loss_pct: float, dte: int) -> str:
    """Classify zone for put spreads and iron condors."""
    # DTE adjustment: ~1% tighter at short DTE, ~1% looser at long DTE
    buf_adj = 1 if dte <= 5 else (-1 if dte >= 30 else 0)

    if buffer_pct <= 0 or loss_pct > 85:
        return "ACT NOW"
    if buffer_pct <= 2 + buf_adj or loss_pct > 65:
        return "DANGER"
    if buffer_pct <= 4 + buf_adj or loss_pct > 40:
        return "WARNING"
    if buffer_pct <= 8 + buf_adj or loss_pct > 20:
        return "WATCH"
    return "SAFE"


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
    rules = read_profile()["profit_rules"]
    close_pct = rules.get("close_pct", 75)
    consider_pct = rules.get("consider_pct", 50)
    near_expiry_pct = rules.get("near_expiry_pct", 25)
    near_expiry_dte = rules.get("near_expiry_dte", 14)

    max_profit = net_credit * 100 * contracts
    profit_pct = (pnl / max_profit * 100) if max_profit > 0 else 0

    if pnl > 0:
        if profit_pct >= close_pct:
            return f"Close candidate \u2014 captured {close_pct}%+ of max profit"
        if profit_pct >= consider_pct:
            return f"Consider closing \u2014 captured {consider_pct}%+ of max profit"
        if dte <= near_expiry_dte and profit_pct >= near_expiry_pct:
            return "Near expiry with profit \u2014 close to avoid gamma risk"

    if strategy == "covered-call" and buffer_pct is not None and buffer_pct <= 2:
        return "Shares may be called away \u2014 close call to keep shares or let assign"

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

    if zone == "SAFE" and dte <= 7 and pnl >= 0:
        return "Expiring soon in profit \u2014 let expire or close to lock in"

    return None


def _check_single_position(p: dict) -> dict:
    """Run the monitor script for a single position and return zone data."""
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
                "prev_close": data.get("prev_close"),
                "change_pct": data.get("change_pct"),
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
                    "cost_to_close_mid": data.get("cost_to_close_mid"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            result["price_source"] = data.get("price_source", "unknown")
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
                "prev_close": data.get("prev_close"),
                "change_pct": data.get("change_pct"),
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
                    "cost_to_close_mid": data.get("cost_to_close_mid"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            result["price_source"] = data.get("price_source", "unknown")
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
                "prev_close": data.get("prev_close"),
                "change_pct": data.get("change_pct"),
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
                    "cost_to_close_mid": data.get("cost_to_close_mid"),
                    "put_cost_to_close": data.get("put_cost_to_close"),
                    "call_cost_to_close": data.get("call_cost_to_close"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            result["price_source"] = data.get("price_source", "unknown")
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
                "prev_close": data.get("prev_close"),
                "change_pct": data.get("change_pct"),
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
                    "cost_to_close_mid": data.get("cost_to_close_mid"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            result["price_source"] = data.get("price_source", "unknown")
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
                "prev_close": data.get("prev_close"),
                "change_pct": data.get("change_pct"),
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
                    "cost_to_close_mid": data.get("cost_to_close_mid"),
                },
            }
            if suggestion:
                result["suggestion"] = suggestion
            result["price_source"] = data.get("price_source", "unknown")
            return result

        else:
            return {"zone": "UNKNOWN", "zone_error": f"Unsupported strategy: {strategy}"}

    except Exception as e:
        logger.error("Position check failed for %s: %s", p.get("id"), e)
        return {"zone": "UNKNOWN", "zone_error": "Monitor check failed"}


# ── Position check endpoints ─────────────────────────────────────────────────

@router.post("/api/portfolio/check")
@limiter.limit("5/minute")
async def check_all_positions(request: Request):
    """Run monitors for all open positions, save zones to portfolio.json."""
    portfolio = read_portfolio()
    zone_updates: dict[str, dict] = {}
    results = []

    for p in portfolio:
        pid = p.get("id")
        if p.get("status") != "open":
            results.append({"id": pid, "zone": "CLOSED"})
            continue
        zone_data = _check_single_position(p)
        zone_updates[pid] = zone_data
        results.append({"id": pid, **zone_data})

    with _portfolio_lock:
        if os.path.exists(config.PORTFOLIO_PATH):
            with open(config.PORTFOLIO_PATH, "r") as f:
                fresh = json.load(f)
        else:
            fresh = []
        for fp in fresh:
            zd = zone_updates.get(fp.get("id"))
            if zd:
                fp.update(zd)
        _atomic_write_json(config.PORTFOLIO_PATH, fresh)
    return results


# ── Watchlist endpoints ──────────────────────────────────────────────────────

@router.get("/api/watchlist")
async def list_watchlist():
    return read_watchlist()


@router.post("/api/watchlist")
async def add_watchlist(item: WatchlistTrade):
    ticker = item.ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    watchlist = read_watchlist()
    entry = item.model_dump(exclude_none=True)
    entry["ticker"] = ticker
    entry["id"] = uuid.uuid4().hex[:8]
    entry["saved_at"] = date.today().isoformat()
    watchlist.append(entry)
    write_watchlist(watchlist)
    return {"status": "ok", "id": entry["id"]}


@router.delete("/api/watchlist/{item_id}")
async def delete_watchlist(item_id: str):
    watchlist = read_watchlist()
    new_list = [w for w in watchlist if w.get("id") != item_id]
    if len(new_list) == len(watchlist):
        raise HTTPException(status_code=404, detail="Item not found")
    write_watchlist(new_list)
    return {"status": "ok"}


def _refresh_watchlist_item(item: dict) -> dict:
    """Fetch current prices for a watchlist trade's strikes."""
    fake_position = {
        "id": item["id"],
        "strategy": item["strategy"],
        "ticker": item["ticker"],
        "expiry": item["expiry"],
        "legs": item["legs"],
        "net_credit": item["original_credit"],
        "contracts": 1,
        "status": "open",
    }
    try:
        result = _check_single_position(fake_position)
        return {
            "stock_price": result.get("stock_price"),
            "prev_close": result.get("prev_close"),
            "change_pct": result.get("change_pct"),
            "pnl_per_contract": result.get("pnl_per_contract"),
            "buffer_pct": result.get("buffer_pct"),
            "chain_data": result.get("chain_data"),
            "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    except Exception as e:
        logger.error("Watchlist refresh failed for %s: %s", item.get("id"), e)
        return {"error": "Refresh failed"}


@router.post("/api/watchlist/{item_id}/refresh")
async def refresh_watchlist_item(item_id: str):
    watchlist = read_watchlist()
    item = next((w for w in watchlist if w.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    current = _refresh_watchlist_item(item)
    item["current"] = current
    write_watchlist(watchlist)
    return {"id": item_id, **current}


@router.post("/api/watchlist/refresh")
@limiter.limit("5/minute")
async def refresh_all_watchlist(request: Request):
    watchlist = read_watchlist()
    results = []
    for item in watchlist:
        current = _refresh_watchlist_item(item)
        item["current"] = current
        results.append({"id": item["id"], **current})
    write_watchlist(watchlist)
    return results


@router.post("/api/portfolio/{pos_id}/check")
async def check_single(pos_id: str):
    """Run monitor for a single position, save zone to portfolio.json."""
    portfolio = read_portfolio()
    _idx, p = _find_position(portfolio, pos_id)

    zone_data = _check_single_position(p)

    with _portfolio_lock:
        if os.path.exists(config.PORTFOLIO_PATH):
            with open(config.PORTFOLIO_PATH, "r") as f:
                fresh = json.load(f)
        else:
            fresh = []
        for fp in fresh:
            if fp.get("id") == pos_id:
                fp.update(zone_data)
                break
        _atomic_write_json(config.PORTFOLIO_PATH, fresh)
    return {"id": pos_id, **zone_data}
