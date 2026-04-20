"""Trade Plans router — async `/options-trade-plan` skill runs via the `claude` CLI."""

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

logger = logging.getLogger("options_skill_pack")
router = APIRouter()

_FILENAME_RE = re.compile(r"^trade_plan_[A-Z0-9\.\-]{1,12}_\d{4}-\d{2}-\d{2}\.html$")
_TIMEFRAME_RE = re.compile(r"^(weekly|monthly|eom|\d{1,3}\s*dte)$", re.IGNORECASE)
_BIAS_VALUES = {"neutral", "bullish", "bearish"}


class TradePlanRequest(BaseModel):
    ticker: str
    timeframe: Optional[str] = None
    expiry: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    portfolio_size: Optional[str] = Field(None, max_length=32)
    bias: Optional[str] = None


@router.post("/api/trade-plans")
@limiter.limit("10/minute")
async def create_trade_plan(request: Request, req: TradePlanRequest):
    ticker = req.ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    timeframe = req.timeframe.strip() if req.timeframe else None
    if timeframe and not _TIMEFRAME_RE.match(timeframe):
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    bias = req.bias.strip().lower() if req.bias else None
    if bias and bias not in _BIAS_VALUES:
        raise HTTPException(status_code=400, detail="Invalid bias")

    portfolio_size = req.portfolio_size.strip() if req.portfolio_size else None
    if portfolio_size and not re.match(r"^[\$\d,\.kKmM\s]{1,32}$", portfolio_size):
        raise HTTPException(status_code=400, detail="Invalid portfolio_size")

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
        expiry=req.expiry,
        portfolio_size=portfolio_size,
        bias=bias,
    )
    return {"job_id": job_id}


@router.get("/api/trade-plans/jobs")
async def list_jobs(request: Request):
    return {"jobs": await trade_plan_runner.list_jobs()}


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
        ticker, expiry = _parse_filename(p.name)
        items.append({
            "filename": p.name,
            "ticker": ticker,
            "expiry": expiry,
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "size": stat.st_size,
        })

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": items}


@router.get("/api/trade-plans/files/{name}")
async def get_file(request: Request, name: str):
    path = _resolve_plan_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="text/html")


@router.delete("/api/trade-plans/files/{name}")
async def delete_file(request: Request, name: str):
    path = _resolve_plan_path(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(path)
    return {"deleted": name}


def _resolve_plan_path(name: str) -> str:
    if not _FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid filename")
    plans_dir = os.path.realpath(config.TRADE_PLANS_DIR)
    path = os.path.realpath(os.path.join(plans_dir, name))
    if os.path.commonpath([path, plans_dir]) != plans_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return path


def _parse_filename(name: str) -> tuple[Optional[str], Optional[str]]:
    m = re.match(r"^trade_plan_([A-Z0-9\.\-]+)_(\d{4}-\d{2}-\d{2})\.html$", name)
    return (m.group(1), m.group(2)) if m else (None, None)
