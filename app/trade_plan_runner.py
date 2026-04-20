"""Background job runner for the `options-trade-plan` skill via the `claude` CLI."""

import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from app import config

logger = logging.getLogger("options_skill_pack")

_CLAUDE_BIN: Optional[str] = shutil.which("claude")

_JOBS: dict[str, "Job"] = {}
_JOBS_LOCK = asyncio.Lock()
_SEMAPHORE: Optional[asyncio.Semaphore] = None

_PRUNE_AFTER_SEC = 15 * 60  # Drop finished jobs from the in-memory list after 15 min


@dataclass
class Job:
    job_id: str
    ticker: str
    timeframe: Optional[str]
    status: str  # "running" | "done" | "error"
    started_at: float
    finished_at: Optional[float] = None
    output_filename: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def claude_bin() -> Optional[str]:
    return _CLAUDE_BIN


def _semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(config.TRADE_PLAN_MAX_CONCURRENT)
    return _SEMAPHORE


def _build_prompt(ticker: str, timeframe: Optional[str], expiry: Optional[str],
                  portfolio_size: Optional[str], bias: Optional[str]) -> str:
    lead = f"Generate an options trade plan for {ticker}"
    if expiry:
        lead += f" for expiry {expiry}"
    elif timeframe:
        lead += f" ({timeframe})"
    lead += "."

    extras = []
    if portfolio_size:
        extras.append(f"Portfolio size: {portfolio_size}.")
    if bias:
        extras.append(f"Directional bias: {bias}.")

    tail = "Use the options-trade-plan skill. Write the output HTML to ./trade-plans/ in the current working directory."
    return " ".join([lead, *extras, tail])


async def submit_job(ticker: str, timeframe: Optional[str] = None,
                     expiry: Optional[str] = None,
                     portfolio_size: Optional[str] = None,
                     bias: Optional[str] = None) -> str:
    """Register a new job and spawn its background task. Returns the job_id."""
    job_id = uuid.uuid4().hex[:12]
    job = Job(
        job_id=job_id,
        ticker=ticker,
        timeframe=timeframe,
        status="running",
        started_at=time.time(),
    )
    async with _JOBS_LOCK:
        _JOBS[job_id] = job

    asyncio.create_task(_run_job(job_id, ticker, timeframe, expiry, portfolio_size, bias))
    return job_id


async def _run_job(job_id: str, ticker: str, timeframe: Optional[str],
                   expiry: Optional[str], portfolio_size: Optional[str],
                   bias: Optional[str]) -> None:
    if not _CLAUDE_BIN:
        await _finish(job_id, error="claude CLI not found on server PATH. Install it to generate trade plans.")
        return

    trade_plans_dir = Path(config.TRADE_PLANS_DIR)
    trade_plans_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(trade_plans_dir)

    prompt = _build_prompt(ticker, timeframe, expiry, portfolio_size, bias)
    cmd = [_CLAUDE_BIN, "-p", "--permission-mode", "bypassPermissions", prompt]

    async with _semaphore():
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=config.PROJECT_ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=config.CLAUDE_CLI_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                await _finish(job_id, error=f"Timed out after {config.CLAUDE_CLI_TIMEOUT_SEC}s.")
                return
        except Exception as e:
            logger.exception("trade-plan subprocess failed")
            await _finish(job_id, error=f"Subprocess failed: {e}")
            return

    if proc.returncode != 0:
        stderr = (stderr_b or b"").decode("utf-8", errors="replace").strip()
        tail = stderr[-2000:] if stderr else f"Exit code {proc.returncode}."
        await _finish(job_id, error=tail or f"Exit code {proc.returncode}.")
        return

    after = _snapshot(trade_plans_dir)
    new_files = sorted(after - before, key=lambda n: (trade_plans_dir / n).stat().st_mtime, reverse=True)
    match = next((n for n in new_files if ticker in n), new_files[0] if new_files else None)

    if not match:
        stdout = (stdout_b or b"").decode("utf-8", errors="replace").strip()
        await _finish(job_id, error="No HTML file produced. " + (stdout[-500:] if stdout else ""))
        return

    await _finish(job_id, output_filename=match)


async def _finish(job_id: str, output_filename: Optional[str] = None, error: Optional[str] = None) -> None:
    async with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job.finished_at = time.time()
        if error:
            job.status = "error"
            job.error = error
        else:
            job.status = "done"
            job.output_filename = output_filename


def _snapshot(d: Path) -> set[str]:
    return {p.name for p in d.glob("*.html")} if d.exists() else set()


async def list_jobs() -> list[dict]:
    """Return a snapshot of jobs, pruning finished ones older than the TTL."""
    now = time.time()
    async with _JOBS_LOCK:
        stale = [
            jid for jid, j in _JOBS.items()
            if j.status in ("done", "error") and j.finished_at and (now - j.finished_at) > _PRUNE_AFTER_SEC
        ]
        for jid in stale:
            _JOBS.pop(jid, None)
        return [j.to_dict() for j in sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)]
