"""FastAPI app for the Options Skill Pack."""

import os
import json
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic

from app.tools import TOOLS, execute_tool
from app.prompts import SYSTEM_PROMPT, SKILL_GUIDANCE

app = FastAPI(title="Options Skill Pack")

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(PROJECT_ROOT, "portfolio.json")

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


# ── Chat models & endpoint ───────────────────────────────────────────────────

class Message(BaseModel):
    role: str
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

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
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
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
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
    except Exception as e:
        return ChatResponse(response=f"**Error:** {str(e)}")


# ── Portfolio helpers ────────────────────────────────────────────────────────

def _read_portfolio() -> list[dict]:
    if not os.path.exists(PORTFOLIO_PATH):
        return []
    with open(PORTFOLIO_PATH, "r") as f:
        return json.load(f)


def _write_portfolio(data: list[dict]):
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(data, f, indent=2)


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
    return _read_portfolio()


@app.post("/api/portfolio")
async def add_position(position: Position):
    portfolio = _read_portfolio()
    portfolio.append(position.model_dump(exclude_none=True))
    _write_portfolio(portfolio)
    return {"status": "ok", "index": len(portfolio) - 1}


@app.put("/api/portfolio/{index}")
async def update_position(index: int, position: Position):
    portfolio = _read_portfolio()
    if index < 0 or index >= len(portfolio):
        raise HTTPException(status_code=404, detail="Position not found")
    portfolio[index] = position.model_dump(exclude_none=True)
    _write_portfolio(portfolio)
    return {"status": "ok"}


class CloseRequest(BaseModel):
    notes: Optional[str] = None
    close_price: Optional[float] = None


@app.post("/api/portfolio/{index}/close")
async def close_position(index: int, req: CloseRequest = CloseRequest()):
    from datetime import date
    portfolio = _read_portfolio()
    if index < 0 or index >= len(portfolio):
        raise HTTPException(status_code=404, detail="Position not found")

    p = portfolio[index]
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


@app.post("/api/portfolio/{index}/reopen")
async def reopen_position(index: int):
    portfolio = _read_portfolio()
    if index < 0 or index >= len(portfolio):
        raise HTTPException(status_code=404, detail="Position not found")
    portfolio[index]["status"] = "open"
    _write_portfolio(portfolio)
    return {"status": "ok"}


@app.delete("/api/portfolio/{index}")
async def delete_position(index: int):
    portfolio = _read_portfolio()
    if index < 0 or index >= len(portfolio):
        raise HTTPException(status_code=404, detail="Position not found")
    removed = portfolio.pop(index)
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

    if buffer_pct > thresholds[0][0] and loss_pct < thresholds[0][1]:
        return "SAFE"
    if buffer_pct <= 0 or loss_pct > 85:
        return "ACT NOW"
    if buffer_pct <= thresholds[3][0] or loss_pct > thresholds[3][1]:
        return "DANGER"
    if buffer_pct <= thresholds[2][0] or loss_pct > thresholds[2][1]:
        return "WARNING"
    if buffer_pct <= thresholds[1][0] or loss_pct > thresholds[1][1]:
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


def _check_single_position(p: dict) -> dict:
    """Run the monitor script for a single position and return zone data."""
    from datetime import datetime

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
            return {
                "zone": zone,
                "zone_updated": datetime.utcnow().isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
            }

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
            return {
                "zone": zone,
                "zone_updated": datetime.utcnow().isoformat(timespec="seconds"),
                "buffer_pct": data.get("worst_buffer_pct"),
                "worst_side": data.get("worst_side"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
                "loss_pct_of_max": data.get("loss_pct_of_max"),
            }

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
            return {
                "zone": zone,
                "zone_updated": datetime.utcnow().isoformat(timespec="seconds"),
                "buffer_pct": data.get("buffer_pct"),
                "pnl_per_contract": data.get("pnl_per_contract"),
                "stock_price": data.get("stock_price"),
            }

        else:
            return {"zone": "UNKNOWN", "zone_error": f"Unsupported strategy: {strategy}"}

    except Exception as e:
        return {"zone": "UNKNOWN", "zone_error": str(e)}


@app.post("/api/portfolio/check")
async def check_all_positions():
    """Run monitors for all open positions, save zones to portfolio.json."""
    portfolio = _read_portfolio()
    results = []

    for i, p in enumerate(portfolio):
        if p.get("status") != "open":
            results.append({"index": i, "zone": "CLOSED"})
            continue

        zone_data = _check_single_position(p)
        # Save zone data into the position
        portfolio[i].update(zone_data)
        results.append({"index": i, **zone_data})

    _write_portfolio(portfolio)
    return results


@app.post("/api/portfolio/{index}/check")
async def check_single(index: int):
    """Run monitor for a single position, save zone to portfolio.json."""
    portfolio = _read_portfolio()
    if index < 0 or index >= len(portfolio):
        raise HTTPException(status_code=404, detail="Position not found")

    zone_data = _check_single_position(portfolio[index])
    portfolio[index].update(zone_data)
    _write_portfolio(portfolio)
    return {"index": index, **zone_data}


# ── Static files ─────────────────────────────────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(static_dir, "index.html"))
