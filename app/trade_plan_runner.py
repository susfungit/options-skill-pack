"""Background job runner for analyst skills (`options-trade-plan`, `trade-*`) via the `claude` CLI."""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app import config

logger = logging.getLogger("options_skill_pack")

_CLAUDE_BIN: Optional[str] = shutil.which("claude")

# Tools the trade-plan / trade-* skills are permitted to use in `-p` mode.
# Replaces a blanket `--permission-mode bypassPermissions`. Bash is needed to
# run the bundled Python selector/renderer scripts; Read/Write/Edit for report
# files; Glob/Grep for locating skill assets; WebSearch/WebFetch for live market
# news and quotes; Task to fan out to analyst subagents; TodoWrite for the
# skills that track multi-step progress. Override with the ALLOWED_TOOLS env var.
_ALLOWED_TOOLS: str = os.environ.get(
    "TRADE_PLAN_ALLOWED_TOOLS",
    "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,Task,TodoWrite",
)

_JOBS: dict[str, "Job"] = {}
_JOBS_LOCK = asyncio.Lock()
_SEMAPHORE: Optional[asyncio.Semaphore] = None

_PRUNE_AFTER_SEC = 15 * 60  # Drop finished jobs from the in-memory list after 15 min

# (skill_name, ticker, expiry-or-timeframe, bias) → (output_filename, completed_at_epoch)
_PLAN_CACHE: dict[tuple, tuple[str, float]] = {}
_PLAN_CACHE_TTL_SEC = 30 * 60


# Each skill entry has:
#   filename_prefix — appears in both the prompt instruction and the file regex.
#   supports        — which optional inputs (timeframe / expiry / portfolio_size /
#                     bias) are meaningful. Unsupported inputs are silently dropped
#                     so the frontend can post a uniform payload.
#   lead            — the opening sentence of the wrapper prompt.
#   rendering       — how this skill should produce HTML. See _build_prompt.
#                       "inline_html"  → skill writes HTML directly (default).
#                       "force_inline_html" → SKILL.md says markdown; wrapper
#                                             overrides it to inline HTML.
#                       "vendored_script_html" → skill writes JSON to /tmp then
#                                                runs our vendored renderer.
#
# `trade-quick` is intentionally excluded — its SKILL.md is terminal-only.
SKILL_REGISTRY: dict[str, dict] = {
    "options-trade-plan": {
        "filename_prefix": "trade_plan_",
        "supports": {"timeframe", "expiry", "portfolio_size", "bias"},
        "lead": "Generate an options trade plan for {ticker}",
        "rendering": "inline_html",
    },
    "trade-analyze": {
        "filename_prefix": "trade_analysis_",
        "supports": set(),
        "lead": "Run a full multi-dimensional stock analysis for {ticker}",
        "rendering": "vendored_script_html",
    },
    "trade-thesis": {
        "filename_prefix": "trade_thesis_",
        "supports": {"portfolio_size"},
        "lead": "Generate a complete investment thesis for {ticker}",
        "rendering": "force_inline_html",
    },
    "trade-risk": {
        "filename_prefix": "trade_risk_",
        "supports": {"portfolio_size"},
        "lead": "Run a risk assessment and position-sizing analysis for {ticker}",
        "rendering": "force_inline_html",
    },
    "trade-fundamental": {
        "filename_prefix": "trade_fundamental_",
        "supports": set(),
        "lead": "Run a fundamental analysis of {ticker}",
        "rendering": "inline_html",
    },
    "trade-technical": {
        "filename_prefix": "trade_technical_",
        "supports": set(),
        "lead": "Run a technical analysis of {ticker}",
        "rendering": "force_inline_html",
    },
    "trade-sentiment": {
        "filename_prefix": "trade_sentiment_",
        "supports": set(),
        "lead": "Run a sentiment and momentum analysis of {ticker}",
        "rendering": "force_inline_html",
    },
    "trade-earnings": {
        "filename_prefix": "trade_earnings_",
        "supports": set(),
        "lead": "Run a pre-earnings analysis of {ticker}",
        "rendering": "force_inline_html",
    },
    "trade-options": {
        "filename_prefix": "trade_options_",
        "supports": {"timeframe", "expiry", "bias"},
        "lead": "Run an options strategy analysis of {ticker}",
        "rendering": "inline_html",
    },
}

DEFAULT_SKILL = "options-trade-plan"

# Resolved at import: path to the vendored HTML renderer used by trade-analyze.
_VENDORED_RENDERER = str(
    Path(config.PROJECT_ROOT)
    / ".claude" / "local-marketplace" / "plugins" / "ai-trading-analyst"
    / "scripts" / "generate_trade_html.py"
)


@dataclass
class Job:
    job_id: str
    ticker: str
    timeframe: Optional[str]
    status: str  # "running" | "done" | "error"
    started_at: float
    skill_name: str = DEFAULT_SKILL
    finished_at: Optional[float] = None
    output_filename: Optional[str] = None
    error: Optional[str] = None
    # Usage metrics parsed from `claude -p --output-format json` envelope.
    # All optional — older Claude Code versions or stderr-only failures may
    # leave them unset, and the rest of the system should still function.
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    num_turns: Optional[int] = None
    duration_ms: Optional[int] = None  # API-side duration reported by claude
    model: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_usage(stdout_bytes: bytes) -> dict:
    """Parse `claude -p --output-format json` stdout into a metrics dict.

    Returns {} if parsing fails or fields are missing — never raises. The job
    flow tolerates absent metrics; only the UI display degrades.
    """
    try:
        envelope = json.loads(stdout_bytes.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(envelope, dict):
        return {}
    usage = envelope.get("usage") or {}
    return {
        "cost_usd": envelope.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
        "num_turns": envelope.get("num_turns"),
        "duration_ms": envelope.get("duration_api_ms") or envelope.get("duration_ms"),
    }


def claude_bin() -> Optional[str]:
    return _CLAUDE_BIN


def _semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(config.TRADE_PLAN_MAX_CONCURRENT)
    return _SEMAPHORE


def _expected_filename(skill_name: str, ticker: str, expiry: Optional[str]) -> str:
    prefix = SKILL_REGISTRY[skill_name]["filename_prefix"]
    date_part = expiry or date.today().isoformat()
    return f"{prefix}{ticker}_{date_part}.html"


def _build_prompt(skill_name: str, ticker: str, timeframe: Optional[str],
                  expiry: Optional[str], portfolio_size: Optional[str],
                  bias: Optional[str]) -> str:
    spec = SKILL_REGISTRY[skill_name]
    supports = spec["supports"]
    lead = spec["lead"].format(ticker=ticker)

    if "expiry" in supports and expiry:
        lead += f" for expiry {expiry}"
    elif "timeframe" in supports and timeframe:
        lead += f" ({timeframe})"
    lead += "."

    extras = []
    if "portfolio_size" in supports and portfolio_size:
        extras.append(f"Portfolio size: {portfolio_size}.")
    if "bias" in supports and bias:
        extras.append(f"Directional bias: {bias}.")

    filename = _expected_filename(skill_name, ticker, expiry)
    out_path = f"./trade-plans/{filename}"
    rendering = spec["rendering"]

    common_header = (
        f"Use the {skill_name} skill. The ONLY deliverable is a single "
        f"self-contained HTML file at '{out_path}' (path relative to the "
        f"current working directory). Do not produce any other files. "
        f"OUTPUT PATH OVERRIDE: the skill's own instructions may name a different "
        f"output file (e.g. an UPPERCASE name like TRADE-FUNDAMENTAL-<TICKER>.html "
        f"in the project root) — IGNORE that. Write ONLY to '{out_path}' and "
        f"nowhere else."
    )

    if rendering == "inline_html":
        tail = (
            f"{common_header} Render the report as inline HTML with embedded "
            f"CSS and no external assets, following the editorial style used "
            f"by the skill itself. Do NOT call any helper scripts under "
            f"~/.claude/skills/trade/scripts/ — those are intentionally not "
            f"available in this environment."
        )
    elif rendering == "force_inline_html":
        tail = (
            f"{common_header} IMPORTANT OUTPUT OVERRIDE: ignore any "
            f"instruction in the skill prompt that tells you to produce a "
            f"`.md` (Markdown) file. Do NOT write any `.md` files. Instead, "
            f"render the entire analysis as inline HTML with embedded CSS "
            f"and no external assets, matching the self-contained editorial "
            f"style of the trade-fundamental and trade-options skills. "
            f"Do NOT call any helper scripts."
        )
    elif rendering == "vendored_script_html":
        tail = (
            f"{common_header} OUTPUT OVERRIDE: this environment does NOT "
            f"include `~/.claude/skills/trade/scripts/`. When the skill "
            f"reaches the HTML rendering step, do NOT call "
            f"`~/.claude/skills/trade/scripts/generate_trade_html.py`. "
            f"Use this vendored copy instead, with the absolute output path: "
            f"`TRADE_HTML_OUT='{out_path}' python3 {_VENDORED_RENDERER}`. "
            f"You may still write the intermediate JSON payload to "
            f"/tmp/trade_report_data.json as the script expects. Do NOT leave "
            f"any `.md` file behind as a separate deliverable — only the HTML."
        )
    else:
        # Defensive default — should never be reached for registered skills.
        tail = (
            f"{common_header} Render the report as inline HTML with embedded "
            f"CSS and no external assets."
        )

    return " ".join([lead, *extras, tail])


def _cache_key(skill_name: str, ticker: str, timeframe: Optional[str],
               expiry: Optional[str], bias: Optional[str]) -> tuple:
    return (skill_name, ticker, expiry or timeframe or "", bias or "")


async def submit_job(ticker: str, timeframe: Optional[str] = None,
                     expiry: Optional[str] = None,
                     portfolio_size: Optional[str] = None,
                     bias: Optional[str] = None,
                     skill_name: str = DEFAULT_SKILL,
                     force: bool = False) -> str:
    """Register a new job and spawn its background task. Returns the job_id.

    If a recent identical plan exists in the cache (and the file is still on disk),
    short-circuits with a job marked done immediately. Pass force=True to bypass.
    """
    if skill_name not in SKILL_REGISTRY:
        raise ValueError(f"Unknown skill: {skill_name}")

    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job = Job(
        job_id=job_id,
        ticker=ticker,
        timeframe=timeframe,
        skill_name=skill_name,
        status="running",
        started_at=now,
    )
    async with _JOBS_LOCK:
        _JOBS[job_id] = job

    if not force:
        key = _cache_key(skill_name, ticker, timeframe, expiry, bias)
        cached = _PLAN_CACHE.get(key)
        if cached:
            filename, finished_at = cached
            file_path = Path(config.TRADE_PLANS_DIR) / filename
            if (now - finished_at) < _PLAN_CACHE_TTL_SEC and file_path.exists():
                async with _JOBS_LOCK:
                    job.status = "done"
                    job.output_filename = filename
                    job.finished_at = now
                return job_id
            _PLAN_CACHE.pop(key, None)

    asyncio.create_task(_run_job(job_id, skill_name, ticker, timeframe, expiry, portfolio_size, bias))
    return job_id


async def _run_job(job_id: str, skill_name: str, ticker: str, timeframe: Optional[str],
                   expiry: Optional[str], portfolio_size: Optional[str],
                   bias: Optional[str]) -> None:
    if not _CLAUDE_BIN:
        await _finish(job_id, error="claude CLI not found on server PATH. Install it to generate trade plans.")
        return

    trade_plans_dir = Path(config.TRADE_PLANS_DIR)
    trade_plans_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot(trade_plans_dir)

    prompt = _build_prompt(skill_name, ticker, timeframe, expiry, portfolio_size, bias)
    model = os.environ.get("TRADE_PLAN_MODEL", "claude-haiku-4-5-20251001")
    # `--output-format json` makes the CLI emit a single envelope on stdout with
    # usage/cost/duration fields. The HTML still gets written to disk by the skill
    # itself, so file detection (snapshot diff below) is unaffected.
    #
    # Instead of `--permission-mode bypassPermissions` (which auto-approves every
    # tool, so a prompt-injected run could do anything), we pass an explicit
    # allowlist of exactly what the trade-plan / trade-* skills need: run the
    # bundled Python selector scripts, read/write the report files, fetch market
    # data over the web, and fan out to subagents. Tools outside this list are
    # denied (there is no interactive approver in `-p` mode).
    #
    # The prompt goes in via stdin, NOT as a trailing positional: `--allowed-tools`
    # is variadic and would otherwise swallow the prompt as another tool name.
    cmd = [
        _CLAUDE_BIN, "-p",
        "--model", model,
        "--output-format", "json",
        "--allowed-tools", _ALLOWED_TOOLS,
    ]

    # Strip ANTHROPIC_API_KEY so the subprocess falls back to the host's
    # claude.ai subscription auth instead of billing the API. The env var
    # otherwise takes precedence even when the user is logged in.
    sub_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    run_start = time.time()
    async with _semaphore():
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=config.PROJECT_ROOT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=sub_env,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode()), timeout=config.CLAUDE_CLI_TIMEOUT_SEC
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
    # Detect files added OR modified during this run. The renderer writes a
    # deterministic filename ({prefix}{ticker}_{date}.html), so a re-run of the same
    # plan overwrites in place — set-difference would miss it.
    candidates = sorted(
        (n for n in after if n not in before or (trade_plans_dir / n).stat().st_mtime >= run_start),
        key=lambda n: (trade_plans_dir / n).stat().st_mtime,
        reverse=True,
    )
    prefix = SKILL_REGISTRY[skill_name]["filename_prefix"]
    match = (
        next((n for n in candidates if n.startswith(prefix) and ticker in n), None)
        or next((n for n in candidates if ticker in n), None)
        or (candidates[0] if candidates else None)
    )

    if not match:
        # The skill may have written to the project root under its own hardcoded
        # filename instead of trade-plans/. Recover it before declaring failure.
        match = _recover_stray_html(skill_name, ticker, expiry, run_start)

    if not match:
        stdout = (stdout_b or b"").decode("utf-8", errors="replace").strip()
        await _finish(job_id, error="No HTML file produced. " + (stdout[-500:] if stdout else ""))
        return

    metrics = _extract_usage(stdout_b or b"")
    wall_ms = int((time.time() - run_start) * 1000)
    _write_sidecar(trade_plans_dir / match, skill_name, ticker, model, metrics, wall_ms)
    if metrics:
        logger.info(
            "analysis-job done skill=%s ticker=%s cost_usd=%s input=%s output=%s "
            "cache_read=%s turns=%s api_ms=%s wall_ms=%s",
            skill_name, ticker,
            metrics.get("cost_usd"), metrics.get("input_tokens"),
            metrics.get("output_tokens"), metrics.get("cache_read_tokens"),
            metrics.get("num_turns"), metrics.get("duration_ms"), wall_ms,
        )

    _PLAN_CACHE[_cache_key(skill_name, ticker, timeframe, expiry, bias)] = (match, time.time())
    await _finish(job_id, output_filename=match, model=model, **metrics)


def _write_sidecar(html_path: Path, skill_name: str, ticker: str, model: str,
                   metrics: dict, wall_ms: int) -> None:
    """Persist usage metrics next to the HTML so the UI can show them past the
    in-memory job TTL. Best-effort — failures are logged but don't break the job."""
    try:
        sidecar = html_path.with_suffix(html_path.suffix + ".meta.json")
        payload = {
            "skill_name": skill_name,
            "ticker": ticker,
            "model": model,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "wall_ms": wall_ms,
            **{k: v for k, v in metrics.items() if v is not None},
        }
        sidecar.write_text(json.dumps(payload, indent=2))
    except OSError as e:
        logger.warning("Failed to write sidecar for %s: %s", html_path.name, e)


async def _finish(job_id: str, output_filename: Optional[str] = None,
                  error: Optional[str] = None, model: Optional[str] = None,
                  cost_usd: Optional[float] = None,
                  input_tokens: Optional[int] = None,
                  output_tokens: Optional[int] = None,
                  cache_read_tokens: Optional[int] = None,
                  cache_creation_tokens: Optional[int] = None,
                  num_turns: Optional[int] = None,
                  duration_ms: Optional[int] = None) -> None:
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
            job.model = model
            job.cost_usd = cost_usd
            job.input_tokens = input_tokens
            job.output_tokens = output_tokens
            job.cache_read_tokens = cache_read_tokens
            job.cache_creation_tokens = cache_creation_tokens
            job.num_turns = num_turns
            job.duration_ms = duration_ms


def _snapshot(d: Path) -> set[str]:
    return {p.name for p in d.glob("*.html")} if d.exists() else set()


def _recover_stray_html(skill_name: str, ticker: str, expiry: Optional[str],
                        run_start: float) -> Optional[str]:
    """Recover an analyst HTML that the skill wrote to the project root instead
    of trade-plans/.

    Some analyst SKILL.md files hardcode an UPPERCASE output filename in the CWD
    (e.g. TRADE-FUNDAMENTAL-<TICKER>.html). The wrapper prompt overrides that, but
    the model occasionally follows the skill anyway, leaving the file in the
    project root where the normal snapshot diff misses it. If that happened, move
    the stray file into trade-plans/ under the canonical name and return it.
    Returns None if nothing recoverable is found. Best-effort — never raises.
    """
    root = Path(config.PROJECT_ROOT)
    trade_plans_dir = Path(config.TRADE_PLANS_DIR)
    try:
        strays = [
            p for p in root.glob("*.html")
            if ticker in p.name.upper() and p.stat().st_mtime >= run_start
        ]
    except OSError:
        return None
    if not strays:
        return None
    src = max(strays, key=lambda p: p.stat().st_mtime)
    dest = trade_plans_dir / _expected_filename(skill_name, ticker, expiry)
    try:
        src.replace(dest)  # atomic on the same filesystem; overwrites a stale dest
    except OSError as e:
        logger.warning("Failed to relocate stray %s -> %s: %s", src.name, dest.name, e)
        return None
    logger.warning(
        "Recovered stray analyst HTML written to project root: %s -> trade-plans/%s "
        "(skill=%s ignored the output-path override)",
        src.name, dest.name, skill_name,
    )
    return dest.name


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
