"""Analysis tab router — async analyst skill runs via the `claude` CLI.

Backed by `trade_plan_runner.SKILL_REGISTRY`. Defaults to `options-trade-plan`
for backward compatibility with the original Trade Plans flow.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import config
from app.config import TICKER_RE, limiter
from app import trade_plan_runner
from app.trade_plan_runner import SKILL_REGISTRY, DEFAULT_SKILL

logger = logging.getLogger("options_skill_pack")
router = APIRouter()

_ALLOWED_PREFIXES = tuple(s["filename_prefix"] for s in SKILL_REGISTRY.values())
_PREFIX_TO_SKILL = {s["filename_prefix"]: name for name, s in SKILL_REGISTRY.items()}
_FILENAME_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in _ALLOWED_PREFIXES) +
    r")[A-Z0-9\.\-]{1,12}_\d{4}-\d{2}-\d{2}\.html$"
)
_PARSE_RE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _ALLOWED_PREFIXES) +
    r")([A-Z0-9\.\-]+)_(\d{4}-\d{2}-\d{2})\.html$"
)
_TIMEFRAME_RE = re.compile(r"^(weekly|monthly|eom|\d{1,3}\s*dte)$", re.IGNORECASE)
_BIAS_VALUES = {"neutral", "bullish", "bearish"}


class TradePlanRequest(BaseModel):
    ticker: str
    skill_name: str = DEFAULT_SKILL
    timeframe: Optional[str] = None
    expiry: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    portfolio_size: Optional[str] = Field(None, max_length=32)
    bias: Optional[str] = None
    force: bool = False


@router.post("/api/trade-plans")
@limiter.limit("10/minute")
async def create_trade_plan(request: Request, req: TradePlanRequest):
    ticker = req.ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    skill_name = req.skill_name.strip() if req.skill_name else DEFAULT_SKILL
    if skill_name not in SKILL_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown skill: {skill_name}. Choose one of: {sorted(SKILL_REGISTRY)}",
        )
    supports = SKILL_REGISTRY[skill_name]["supports"]

    # Drop fields the chosen skill doesn't use rather than rejecting — the
    # frontend may send a uniform payload regardless of which skill is selected.
    timeframe = req.timeframe.strip() if (req.timeframe and "timeframe" in supports) else None
    if timeframe and not _TIMEFRAME_RE.match(timeframe):
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    bias = req.bias.strip().lower() if (req.bias and "bias" in supports) else None
    if bias and bias not in _BIAS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid bias")

    portfolio_size = req.portfolio_size.strip() if (req.portfolio_size and "portfolio_size" in supports) else None
    if portfolio_size and not re.match(r"^[\$\d,\.kKmM\s]{1,32}$", portfolio_size):
        raise HTTPException(status_code=400, detail="Invalid portfolio_size")

    expiry = req.expiry if "expiry" in supports else None

    if not trade_plan_runner.claude_bin():
        raise HTTPException(
            status_code=503,
            detail="claude CLI not installed on server. Run `which claude` to verify.",
        )

    running = sum(1 for j in await trade_plan_runner.list_jobs() if j["status"] == "running")
    if running >= config.TRADE_PLAN_MAX_CONCURRENT:
        raise HTTPException(
            status_code=409,
            detail=f"{running} plans already in progress (max {config.TRADE_PLAN_MAX_CONCURRENT}). Wait for one to finish.",
        )

    job_id = await trade_plan_runner.submit_job(
        ticker=ticker,
        timeframe=timeframe,
        expiry=expiry,
        portfolio_size=portfolio_size,
        bias=bias,
        skill_name=skill_name,
        force=req.force,
    )
    return {"job_id": job_id}


@router.get("/api/trade-plans/jobs")
async def list_jobs(request: Request):
    return {
        "jobs": await trade_plan_runner.list_jobs(),
        "claude_available": bool(trade_plan_runner.claude_bin()),
    }


@router.get("/api/trade-plans/files")
async def list_files(request: Request):
    plans_dir = Path(config.TRADE_PLANS_DIR)
    if not plans_dir.exists():
        return {"files": []}

    items = []
    for p in plans_dir.glob("*.html"):
        if not _FILENAME_RE.match(p.name):
            continue
        stat = p.stat()
        skill_name, ticker, expiry = _parse_filename(p.name)
        item = {
            "filename": p.name,
            "skill_name": skill_name,
            "ticker": ticker,
            "expiry": expiry,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "size": stat.st_size,
        }
        # Merge in sidecar metrics if present (cost, tokens, duration).
        sidecar = p.with_suffix(p.suffix + ".meta.json")
        if sidecar.exists():
            try:
                item["metrics"] = json.loads(sidecar.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        items.append(item)

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": items}


@router.get("/api/trade-plans/files/{name}")
async def get_file(request: Request, name: str):
    path = _resolve_plan_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    # These reports are self-generated HTML, but serve them with a strict CSP so
    # that even an injected <script> in a report can't execute or call out.
    headers = {"Content-Security-Policy": "script-src 'none'; sandbox"}
    return FileResponse(path, media_type="text/html", headers=headers)


@router.delete("/api/trade-plans/files/{name}")
async def delete_file(request: Request, name: str):
    path = _resolve_plan_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(path)
    # Also remove the sidecar if it exists. Best-effort — don't fail the delete
    # if cleanup hits a race or a stale sidecar.
    sidecar = path + ".meta.json"
    if os.path.exists(sidecar):
        try:
            os.remove(sidecar)
        except OSError:
            pass
    return {"deleted": name}


def _resolve_plan_path(name: str) -> str:
    if not _FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    plans_dir = os.path.realpath(config.TRADE_PLANS_DIR)
    path = os.path.realpath(os.path.join(plans_dir, name))
    if os.path.commonpath([path, plans_dir]) != plans_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def _parse_filename(name: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    m = _PARSE_RE.match(name)
    if not m:
        return (None, None, None)
    return (_PREFIX_TO_SKILL.get(m.group(1)), m.group(2), m.group(3))
