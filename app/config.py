"""Constants, paths, and defaults for the Options Skill Pack."""

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(PROJECT_ROOT, "portfolio.json")
PROFILE_PATH = os.path.join(PROJECT_ROOT, "profile.json")
WATCHLIST_PATH = os.path.join(PROJECT_ROOT, "watchlist.json")
TRADE_PLANS_DIR = os.path.join(PROJECT_ROOT, "trade-plans")

CLAUDE_CLI_TIMEOUT_SEC = int(os.environ.get("CLAUDE_CLI_TIMEOUT_SEC", "600"))
TRADE_PLAN_MAX_CONCURRENT = int(os.environ.get("TRADE_PLAN_MAX_CONCURRENT", "5"))

DEFAULT_MODEL = "claude-sonnet-4-6"

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

TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
MODEL_RE = re.compile(r"^claude-[a-z0-9\-]+$")

# ── Rate limiter (shared across routers) ──────────────────────────────────

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
