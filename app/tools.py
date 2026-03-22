"""Tool definitions and executors for Claude API tool use."""

import json
import os
import re
import subprocess

# Project root — one level up from app/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS_DIR = os.path.join(PROJECT_ROOT, ".claude", "local-marketplace", "plugins")

# ── Tool definitions (Claude API format) ─────────────────────────────────────

TOOLS = [
    {
        "name": "find_bull_put_spread",
        "description": "Fetch live option chain data and find optimal bull put spread strikes (sell put + buy put) for a given stock. Returns strikes, credit, max profit/loss, breakeven, probability of profit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, NVDA)"},
                "target_delta": {"type": "number", "description": "Target delta for short put (default 0.20 = 20 delta)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 35)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "find_iron_condor",
        "description": "Fetch live option chain data and find optimal iron condor strikes (sell put + buy put + sell call + buy call) for a given stock. Returns all 4 legs, total credit, profit zone, and probability of profit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "target_delta": {"type": "number", "description": "Target delta for both short strikes (default 0.16)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 35)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "find_covered_call",
        "description": "Fetch live option chain data and find the optimal call to sell for a covered call on a stock the user owns. Returns strike, premium, static/annualized yield, downside protection, and probability of assignment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "target_delta": {"type": "number", "description": "Target delta for short call (default 0.30)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 30)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "check_bull_put_spread",
        "description": "Check the current status of an existing bull put spread position. Returns current stock price, option prices, P&L, buffer to short strike, and loss percentage of max loss.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_strike": {"type": "number", "description": "Short (sold) put strike price"},
                "long_strike": {"type": "number", "description": "Long (bought) put strike price"},
                "net_credit": {"type": "number", "description": "Original net credit received per share"},
                "expiry": {"type": "string", "description": "Expiry date as YYYY-MM-DD"},
            },
            "required": ["ticker", "short_strike", "long_strike", "net_credit", "expiry"],
        },
    },
    {
        "name": "check_iron_condor",
        "description": "Check the current status of an existing iron condor position. Returns current prices for all 4 legs, P&L, buffer on both sides, and which side is under more pressure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_put": {"type": "number", "description": "Short put strike"},
                "long_put": {"type": "number", "description": "Long put strike"},
                "short_call": {"type": "number", "description": "Short call strike"},
                "long_call": {"type": "number", "description": "Long call strike"},
                "net_credit": {"type": "number", "description": "Total net credit received per share"},
                "expiry": {"type": "string", "description": "Expiry date as YYYY-MM-DD"},
            },
            "required": ["ticker", "short_put", "long_put", "short_call", "long_call", "net_credit", "expiry"],
        },
    },
    {
        "name": "check_covered_call",
        "description": "Check the current status of an existing covered call position. Returns current call price, buffer to strike, P&L on the call, and optionally effective cost basis and called-away P&L.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_call_strike": {"type": "number", "description": "Short call strike price"},
                "net_credit": {"type": "number", "description": "Premium received per share"},
                "expiry": {"type": "string", "description": "Expiry date as YYYY-MM-DD"},
                "cost_basis": {"type": "number", "description": "Stock purchase price per share (optional)"},
            },
            "required": ["ticker", "short_call_strike", "net_credit", "expiry"],
        },
    },
    {
        "name": "roll_spread",
        "description": "Find roll targets for a bull put spread or one side of an iron condor. Shows close cost, then ranks calendar and diagonal roll candidates by net roll credit. For iron condors, specify which side to roll.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_strike": {"type": "number", "description": "Short strike to roll (put or call)"},
                "long_strike": {"type": "number", "description": "Long strike to roll"},
                "net_credit": {"type": "number", "description": "Original net credit per share"},
                "expiry": {"type": "string", "description": "Current expiry as YYYY-MM-DD"},
                "short_call": {"type": "number", "description": "Short call strike (iron condor only)"},
                "long_call": {"type": "number", "description": "Long call strike (iron condor only)"},
                "roll_side": {"type": "string", "description": "Which side to roll: 'put' or 'call' (iron condor only)"},
                "target_delta": {"type": "number", "description": "Delta target for aggressive diagonal (default 0.20 put, 0.16 condor)"},
            },
            "required": ["ticker", "short_strike", "long_strike", "net_credit", "expiry"],
        },
    },
]

# ── Script mapping — points to original skill directories ────────────────────

def _skill_path(plugin: str, skill: str, script: str) -> str:
    return os.path.join(PLUGINS_DIR, plugin, "skills", skill, script)

SCRIPT_MAP = {
    "find_bull_put_spread": _skill_path("bull-put-spread-selector", "bull-put-spread-selector", "fetch_chain.py"),
    "find_iron_condor": _skill_path("iron-condor-selector", "iron-condor-selector", "fetch_iron_condor.py"),
    "find_covered_call": _skill_path("covered-call-selector", "covered-call-selector", "fetch_covered_call.py"),
    "check_bull_put_spread": _skill_path("bull-put-spread-monitor", "bull-put-spread-monitor", "check_position.py"),
    "check_iron_condor": _skill_path("iron-condor-monitor", "iron-condor-monitor", "check_iron_condor.py"),
    "check_covered_call": _skill_path("covered-call-monitor", "covered-call-monitor", "check_covered_call.py"),
    "roll_spread": _skill_path("spread-roller", "spread-roller", "roll_spread.py"),
}


def _build_args(tool_name: str, tool_input: dict) -> list[str]:
    """Convert tool input dict to CLI args for the corresponding script."""

    if tool_name == "find_bull_put_spread":
        args = [tool_input["ticker"]]
        if "target_delta" in tool_input:
            args.append(str(tool_input["target_delta"]))
        if "dte_min" in tool_input:
            args.append(str(tool_input["dte_min"]))
        if "dte_max" in tool_input:
            args.append(str(tool_input["dte_max"]))
        return args

    if tool_name == "find_iron_condor":
        args = [tool_input["ticker"]]
        if "target_delta" in tool_input:
            args.append(str(tool_input["target_delta"]))
        if "dte_min" in tool_input:
            args.append(str(tool_input["dte_min"]))
        if "dte_max" in tool_input:
            args.append(str(tool_input["dte_max"]))
        return args

    if tool_name == "find_covered_call":
        args = [tool_input["ticker"]]
        if "target_delta" in tool_input:
            args.append(str(tool_input["target_delta"]))
        if "dte_min" in tool_input:
            args.append(str(tool_input["dte_min"]))
        if "dte_max" in tool_input:
            args.append(str(tool_input["dte_max"]))
        return args

    if tool_name == "check_bull_put_spread":
        return [
            tool_input["ticker"],
            str(tool_input["short_strike"]),
            str(tool_input["long_strike"]),
            str(tool_input["net_credit"]),
            tool_input["expiry"],
        ]

    if tool_name == "check_iron_condor":
        return [
            tool_input["ticker"],
            str(tool_input["short_put"]),
            str(tool_input["long_put"]),
            str(tool_input["short_call"]),
            str(tool_input["long_call"]),
            str(tool_input["net_credit"]),
            tool_input["expiry"],
        ]

    if tool_name == "check_covered_call":
        args = [
            tool_input["ticker"],
            str(tool_input["short_call_strike"]),
            str(tool_input["net_credit"]),
            tool_input["expiry"],
        ]
        if "cost_basis" in tool_input:
            args.append(str(tool_input["cost_basis"]))
        return args

    if tool_name == "roll_spread":
        # Detect bull put vs iron condor from presence of short_call
        if "short_call" in tool_input and "long_call" in tool_input:
            # Iron condor mode
            args = [
                tool_input["ticker"],
                str(tool_input["short_strike"]),  # short_put
                str(tool_input["long_strike"]),    # long_put
                str(tool_input["short_call"]),
                str(tool_input["long_call"]),
                str(tool_input["net_credit"]),
                tool_input["expiry"],
                tool_input.get("roll_side", "put"),
            ]
            if "target_delta" in tool_input:
                args.append(str(tool_input["target_delta"]))
        else:
            # Bull put spread mode
            args = [
                tool_input["ticker"],
                str(tool_input["short_strike"]),
                str(tool_input["long_strike"]),
                str(tool_input["net_credit"]),
                tool_input["expiry"],
            ]
            if "target_delta" in tool_input:
                args.append(str(tool_input["target_delta"]))
        return args

    return []


_TICKER_RE = re.compile(r'^[A-Z]{1,5}$')


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by running the corresponding Python script.

    Returns the JSON string output from the script, or an error JSON string.
    """
    # Validate ticker if present
    ticker = tool_input.get("ticker", "")
    if ticker and not _TICKER_RE.match(ticker.upper()):
        return json.dumps({"error": f"Invalid ticker: {ticker}"})

    script_path = SCRIPT_MAP.get(tool_name)
    if not script_path:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    if not os.path.exists(script_path):
        return json.dumps({"error": f"Script not found: {script_path}"})

    args = _build_args(tool_name, tool_input)
    cmd = ["python3", script_path] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            return stdout if stdout else json.dumps({"error": f"Script failed: {stderr}"})
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Script timed out (30s). Try again — yfinance may be slow."})
    except Exception as e:
        return json.dumps({"error": f"Failed to run script: {str(e)}"})
