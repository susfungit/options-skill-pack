# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An options trading toolkit with two interfaces:
1. **Claude Code skills** (11 skills in `.claude/local-marketplace/plugins/`) that trigger on natural language
2. **A FastAPI web app** (`app/`) with chat, portfolio management, analyzer, and profile tabs

Strategies supported: bull put spread, bear call spread, iron condor, covered call, cash-secured put. Each has a selector (find trades) and monitor (check health). The spread-roller handles rolling any spread.

## Commands

```bash
# Run the web app
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m uvicorn app.main:app

# Run tests (all external calls mocked, no API key needed)
pytest
pytest tests/test_app.py::test_validate_negative_strike   # single test

# Run a selector script standalone
python3 .claude/local-marketplace/plugins/bull-put-spread-selector/skills/bull-put-spread-selector/fetch_chain.py AAPL
python3 .claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py AAPL 220 200 1.50 2026-05-16

# Docker
docker compose up --build

# Setup (first time only)
pip install -r app/requirements.txt
bash setup.sh   # generates .claude/settings.json
```

## Architecture

### Web app (`app/`)

FastAPI app split into routers:
- **`main.py`** — app setup, middleware (auth, CORS, rate limiting, security headers), static files
- **`chat.py`** — Claude API client, `/api/chat` streaming endpoint with tool-use loop
- **`analyze.py`** — `/api/analyze` (runs selector scripts without AI tokens), `/api/analyze/compare` (parallel all-strategy comparison), `/api/expirations`, `/api/chain-view`
- **`portfolio.py`** — CRUD for positions, profile endpoints, zone classification (`_classify_zone_spread`, `_classify_zone_covered_call`), `/api/portfolio/{id}/check`
- **`trade_plans.py` / `trade_plan_runner.py`** — Trade Plans tab endpoints; runs the `options-trade-plan` skill by shelling out to the `claude` CLI as an async background job. Requires `claude` on the server PATH (authenticated against the host's Claude subscription). Output written to `trade-plans/`.
- **`tools.py`** — `TOOL_REGISTRY` dict is the single source of truth for all tools. `TOOLS[]`, `SCRIPT_MAP`, `SKILL_GUIDANCE`, and `_build_args()` are derived from it automatically
- **`prompts.py`** — system prompt and per-skill guidance
- **`config.py`** — constants, paths, default profile, rate limiter
- **`storage.py`** — JSON file I/O with locking for portfolio.json and profile.json
- **`auth.py`** — optional API key auth via `APP_API_KEY` env var, session cookies

### Tool registry pattern (`app/tools.py`)

All tools are defined in `TOOL_REGISTRY`. Each entry contains the tool's schema, script path, arg spec, and guidance text. Adding a tool means adding one dict entry — everything else derives automatically. Exception: `roll_spread` uses a custom `_roll_spread_args()` builder for branching iron-condor vs bull-put logic.

### Skills (`.claude/local-marketplace/plugins/`)

Each plugin follows the same structure:
```
{strategy}-{selector|monitor}/
├── .claude-plugin/plugin.json
└── skills/{strategy}-{selector|monitor}/
    ├── SKILL.md          # Claude Code skill prompt
    ├── fetch_*.py / check_*.py   # standalone Python script
    └── evals/evals.json
```

Scripts accept CLI args, use yfinance for market data, output a single JSON object to stdout. Shared utilities live in `plugins/_shared/options_lib.py`.

### Frontend (`app/static/`)

Single-page app: `index.html` + `style.css` + `app.js`. Four tabs: Chat, Portfolio, Analyzer, Profile. The analyzer runs scripts server-side without using Claude API tokens.

## Adding a new strategy

Use the `/add-strategy` command (defined in `.claude/commands/add-strategy.md`). It walks through all 9 steps: create selector plugin, monitor plugin, register in `TOOL_REGISTRY`, update `analyze.py` (StrategyType enum + `_STRATEGY_TO_TOOL`), update `portfolio.py` (zone classification + check endpoint), update UI dropdowns and JS rendering, install plugins, update examples and README.

## Key conventions

- **Zone system**: All monitors classify positions into SAFE / WATCH / WARNING / DANGER / ACT NOW based on buffer_pct and loss metrics
- **Subprocess security**: All scripts run with `shell=False`. Tickers validated against `^[A-Z]{1,5}$` before execution
- **Data files**: `portfolio.json`, `profile.json`, `monitor_config.json` are gitignored. Example templates have `.example.json` suffix
- **No auth by default**: The web app is for local use. Set `APP_API_KEY` env var to enable token-based auth
- **Notifications**: `notify.py` handles email/pushover/macOS notifications. It reads `monitor_config.json` directly — credentials never pass through Claude
