"""Tool definitions and executors for Claude API tool use."""

import json
import math
import os
import re
import subprocess

from app.config import PROJECT_ROOT

PLUGINS_DIR = os.path.join(PROJECT_ROOT, ".claude", "local-marketplace", "plugins")


def _skill_path(plugin: str, skill: str, script: str) -> str:
    return os.path.join(PLUGINS_DIR, plugin, "skills", skill, script)


# ── roll_spread arg builder (callable escape hatch for branching logic) ─────

def _roll_spread_args(tool_input: dict) -> list[str]:
    """Build CLI args for roll_spread — branches on bull-put vs iron-condor."""
    if "short_call" in tool_input and "long_call" in tool_input:
        # Iron condor mode
        args = [
            tool_input["ticker"],
            str(tool_input["short_strike"]),
            str(tool_input["long_strike"]),
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


# ── Unified Tool Registry ──────────────────────────────────────────────────────

TOOL_REGISTRY = {
    "find_bull_put_spread": {
        "description": "Fetch live option chain data and find optimal bull put spread strikes (sell put + buy put) for a given stock. Returns strikes, credit, max profit/loss, breakeven, probability of profit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, NVDA)"},
                "target_delta": {"type": "number", "description": "Target delta for short put (default 0.20 = 20 delta)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 35)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
                "spread_width": {"type": "number", "description": "Spread width as % below short strike for long put (default 10)"},
            },
            "required": ["ticker"],
        },
        "plugin": "bull-put-spread-selector",
        "skill": "bull-put-spread-selector",
        "script": "fetch_chain.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "target_delta", "kind": "positional"},
            {"field": "dte_min", "kind": "positional"},
            {"field": "dte_max", "kind": "positional"},
            {"field": "spread_width", "kind": "positional"},
            {"field": "expiry", "kind": "named", "flag": "--expiry"},
        ],
        "guidance": """Interpretation guidance for the bull put spread data:

**Strike selection context:**
- The short put was selected near the target delta (default 20\u0394 = ~80% probability of profit)
- The long put is placed below the short strike at the configured spread width % (default 10%) for defined risk
- If delta_source is "estimated", label prices as estimates

**Risk checklist \u2014 flag these in your response:**
- Earnings within expiry window? \u2192 IV spike/crush risk
- IV Rank < 25? \u2192 premium is thin, may not be worth selling
- Stock in a downtrend? \u2192 directional risk, consider lower delta
- Ex-dividend date within expiry? \u2192 early assignment risk
- Spread width < $3? \u2192 commissions eat into profit

**Key formulas (already computed in the data):**
- max_profit = net_credit \u00d7 100
- max_loss = (spread_width - net_credit) \u00d7 100
- breakeven = short_strike - net_credit
- prob_profit \u2248 1 - short_delta
- return_on_risk = net_credit / (spread_width - net_credit) \u00d7 100

Present a clear trade summary with the strikes, all metrics, risk flags, and a brief rationale.""",
    },

    "find_bear_call_spread": {
        "description": "Fetch live option chain data and find optimal bear call spread strikes (sell call + buy call) for a given stock. Returns strikes, credit, max profit/loss, breakeven, probability of profit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL, NVDA)"},
                "target_delta": {"type": "number", "description": "Target delta for short call (default 0.20 = 20 delta)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 35)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
                "spread_width": {"type": "number", "description": "Spread width as % above short strike for long call (default 10)"},
            },
            "required": ["ticker"],
        },
        "plugin": "bear-call-spread-selector",
        "skill": "bear-call-spread-selector",
        "script": "fetch_bear_call.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "target_delta", "kind": "positional"},
            {"field": "dte_min", "kind": "positional"},
            {"field": "dte_max", "kind": "positional"},
            {"field": "spread_width", "kind": "positional"},
            {"field": "expiry", "kind": "named", "flag": "--expiry"},
        ],
        "guidance": """Interpretation guidance for the bear call spread data:

**Strike selection context:**
- The short call was selected near the target delta (default 20\u0394 = ~80% probability of profit)
- The long call is placed above the short strike at the configured spread width % (default 10%) for defined risk
- If delta_source is "estimated", label prices as estimates

**Risk checklist \u2014 flag these in your response:**
- Earnings within expiry window? \u2192 IV spike/crush risk
- IV Rank < 25? \u2192 premium is thin, may not be worth selling
- Stock in an uptrend? \u2192 directional risk, consider lower delta
- Ex-dividend date within expiry? \u2192 early assignment risk on ITM calls
- Spread width < $3? \u2192 commissions eat into profit

**Key formulas (already computed in the data):**
- max_profit = net_credit \u00d7 100
- max_loss = (spread_width - net_credit) \u00d7 100
- breakeven = short_strike + net_credit
- prob_profit \u2248 1 - short_delta
- return_on_risk = net_credit / (spread_width - net_credit) \u00d7 100

Present a clear trade summary with the strikes, all metrics, risk flags, and a brief rationale.""",
    },

    "check_bear_call_spread": {
        "description": "Check the current status of an existing bear call spread position. Returns current stock price, option prices, P&L, buffer to short strike, and loss percentage of max loss.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_strike": {"type": "number", "description": "Short (sold) call strike price"},
                "long_strike": {"type": "number", "description": "Long (bought) call strike price"},
                "net_credit": {"type": "number", "description": "Original net credit received per share"},
                "expiry": {"type": "string", "description": "Expiry date as YYYY-MM-DD"},
            },
            "required": ["ticker", "short_strike", "long_strike", "net_credit", "expiry"],
        },
        "plugin": "bear-call-spread-monitor",
        "skill": "bear-call-spread-monitor",
        "script": "check_bear_call.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "short_strike", "kind": "positional", "required": True},
            {"field": "long_strike", "kind": "positional", "required": True},
            {"field": "net_credit", "kind": "positional", "required": True},
            {"field": "expiry", "kind": "positional", "required": True},
        ],
        "guidance": """Interpretation guidance for bear call spread position data:

**Zone classification \u2014 use the WORSE of these two signals:**

| Zone | Buffer (stock below short strike) | OR | Loss % of max loss |
|------|---|---|---|
| \U0001f7e2 SAFE | > 8% | AND | < 20% |
| \U0001f7e1 WATCH | 4\u20138% | OR | 20\u201340% |
| \U0001f7e0 WARNING | 2\u20134% | OR | 40\u201365% |
| \U0001f534 DANGER | 0\u20132% | OR | 65\u201385% |
| \U0001f6a8 ACT NOW | Stock at/above short strike | OR | > 85% |

**DTE adjustments:**
- DTE \u2264 5: tighten thresholds by ~1%
- DTE \u2265 30: slightly more lenient

**Zone-specific guidance:**
- SAFE: No action, let theta work. Note profit captured so far.
- WATCH: Monitor, set price alerts near short strike.
- WARNING: Decide exit level in advance. Consider rolling.
- DANGER: Strongly suggest closing or rolling up and out.
- ACT NOW: Close immediately or roll. Assignment risk is real.""",
    },

    "find_iron_condor": {
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
        "plugin": "iron-condor-selector",
        "skill": "iron-condor-selector",
        "script": "fetch_iron_condor.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "target_delta", "kind": "positional"},
            {"field": "dte_min", "kind": "positional"},
            {"field": "dte_max", "kind": "positional"},
            {"field": "expiry", "kind": "named", "flag": "--expiry"},
        ],
        "guidance": """Interpretation guidance for the iron condor data:

**Strike selection context:**
- Both short strikes selected near target delta (default 16\u0394 each side)
- Wings are ~10% beyond short strikes
- The profit zone is between the two short strikes

**Risk checklist \u2014 flag these:**
- Earnings within expiry? \u2192 gap risk through either side
- IV Rank < 25? \u2192 thin premium
- Strong directional trend? \u2192 one side at higher risk
- Put/call skew? \u2192 note if one side has significantly higher IV

**Key metrics (already computed):**
- total_credit = put_credit + call_credit
- max_loss based on wider side: (wider_width - total_credit) \u00d7 100
- profit_zone: between breakeven_low and breakeven_high
- prob_profit \u2248 1 - put_delta - call_delta

Present both sides clearly, the profit zone, and flag any skew between sides.""",
    },

    "find_covered_call": {
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
        "plugin": "covered-call-selector",
        "skill": "covered-call-selector",
        "script": "fetch_covered_call.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "target_delta", "kind": "positional"},
            {"field": "dte_min", "kind": "positional"},
            {"field": "dte_max", "kind": "positional"},
            {"field": "expiry", "kind": "named", "flag": "--expiry"},
        ],
        "guidance": """Interpretation guidance for the covered call data:

**Strike selection context:**
- Call selected near target delta (default 30\u0394 = ~30% chance of assignment)
- Higher delta = more premium but more likely to be called away
- Lower delta = less premium but keeps shares more often

**Key metrics to highlight:**
- static_return_pct: yield if stock stays flat
- annualized_return_pct: static return annualized
- downside_protection_pct: how much stock can drop before net loss
- called_away_return_pct: max return if assigned (stock gains + premium)
- prob_called_pct \u2248 delta \u00d7 100

**Risk checklist:**
- Earnings within expiry? \u2192 gap risk, IV crush
- IV Rank < 25? \u2192 premium is thin
- Ex-dividend before expiry? \u2192 early assignment risk on ITM calls
- Strong uptrend? \u2192 risk of missing significant upside

If the user provided a cost basis, calculate and show:
- Effective cost basis = cost_basis - premium
- Called-away P&L = strike - cost_basis + premium""",
    },

    "check_bull_put_spread": {
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
        "plugin": "bull-put-spread-monitor",
        "skill": "bull-put-spread-monitor",
        "script": "check_position.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "short_strike", "kind": "positional", "required": True},
            {"field": "long_strike", "kind": "positional", "required": True},
            {"field": "net_credit", "kind": "positional", "required": True},
            {"field": "expiry", "kind": "positional", "required": True},
        ],
        "guidance": """Interpretation guidance for bull put spread position data:

**Zone classification \u2014 use the WORSE of these two signals:**

| Zone | Buffer (stock above short strike) | OR | Loss % of max loss |
|------|---|---|---|
| \U0001f7e2 SAFE | > 8% | AND | < 20% |
| \U0001f7e1 WATCH | 4\u20138% | OR | 20\u201340% |
| \U0001f7e0 WARNING | 2\u20134% | OR | 40\u201365% |
| \U0001f534 DANGER | 0\u20132% | OR | 65\u201385% |
| \U0001f6a8 ACT NOW | Stock at/below short strike | OR | > 85% |

**DTE adjustments:**
- DTE \u2264 5: tighten thresholds by ~1%
- DTE \u2265 30: slightly more lenient

**Zone-specific guidance:**
- SAFE: No action, let theta work. Note profit captured so far.
- WATCH: Monitor, set price alerts near short strike.
- WARNING: Decide exit level in advance. Consider rolling.
- DANGER: Strongly suggest closing or rolling down and out.
- ACT NOW: Close immediately or roll. Assignment risk is real.""",
    },

    "check_iron_condor": {
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
        "plugin": "iron-condor-monitor",
        "skill": "iron-condor-monitor",
        "script": "check_iron_condor.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "short_put", "kind": "positional", "required": True},
            {"field": "long_put", "kind": "positional", "required": True},
            {"field": "short_call", "kind": "positional", "required": True},
            {"field": "long_call", "kind": "positional", "required": True},
            {"field": "net_credit", "kind": "positional", "required": True},
            {"field": "expiry", "kind": "positional", "required": True},
        ],
        "guidance": """Interpretation guidance for iron condor position data:

**Zone classification \u2014 use the WORSE buffer (put or call side):**

| Zone | Worst buffer | OR | Loss % of max |
|------|---|---|---|
| \U0001f7e2 SAFE | > 8% | AND | < 20% |
| \U0001f7e1 WATCH | 4\u20138% | OR | 20\u201340% |
| \U0001f7e0 WARNING | 2\u20134% | OR | 40\u201365% |
| \U0001f534 DANGER | 0\u20132% | OR | 65\u201385% |
| \U0001f6a8 ACT NOW | Outside short strikes | OR | > 85% |

Identify which side (put or call) is under more pressure using worst_side.

**Zone guidance:**
- SAFE: Both sides comfortable. Let theta work.
- WATCH: Identify threatened side. Set alerts.
- WARNING: Consider closing threatened side or rolling it.
- DANGER: Close the threatened side or entire condor.
- ACT NOW: Close immediately. Consider keeping unthreatened side.""",
    },

    "check_covered_call": {
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
        "plugin": "covered-call-monitor",
        "skill": "covered-call-monitor",
        "script": "check_covered_call.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "short_call_strike", "kind": "positional", "required": True},
            {"field": "net_credit", "kind": "positional", "required": True},
            {"field": "expiry", "kind": "positional", "required": True},
            {"field": "cost_basis", "kind": "positional"},
        ],
        "guidance": """Interpretation guidance for covered call position data:

**Zone classification:**

| Zone | Buffer (strike above stock) | OR | Call value vs credit |
|------|---|---|---|
| \U0001f7e2 SAFE | > 8% | AND | < 1.5\u00d7 credit |
| \U0001f7e1 WATCH | 4\u20138% | OR | 1.5\u20132\u00d7 credit |
| \U0001f7e0 WARNING | 2\u20134% | OR | 2\u20133\u00d7 credit |
| \U0001f534 DANGER | 0\u20132% | OR | 3\u20135\u00d7 credit |
| \U0001f6a8 ACT NOW | Stock at/above strike | OR | > 5\u00d7 credit |

**Important nuance:** Unlike put spreads, being called away is often fine \u2014 user keeps premium + stock gains up to strike.

**Zone guidance:**
- SAFE: Let theta decay. Note time value remaining.
- WATCH: Monitor, set alert near strike.
- WARNING: Two paths \u2014 let ride (if OK being called) or roll up and out.
- DANGER: Ask if user wants to keep shares. If yes, buy back or roll.
- ACT NOW: Assignment likely. Accept it (profitable if cost_basis < strike) or buy back.

If cost_basis provided, show effective cost basis and called-away P&L.""",
    },

    "find_cash_secured_put": {
        "description": "Fetch live option chain data and find the optimal put to sell for a cash-secured put. Returns strike, premium, return on capital, effective buy price, and probability of assignment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "target_delta": {"type": "number", "description": "Target delta for short put (default 0.25)"},
                "dte_min": {"type": "integer", "description": "Minimum days to expiration (default 30)"},
                "dte_max": {"type": "integer", "description": "Maximum days to expiration (default 45)"},
            },
            "required": ["ticker"],
        },
        "plugin": "cash-secured-put-selector",
        "skill": "cash-secured-put-selector",
        "script": "fetch_csp.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "target_delta", "kind": "positional", "default_if": {"when_present": ["dte_min", "dte_max"], "value": 0.25}},
            {"field": "dte_min", "kind": "positional"},
            {"field": "dte_max", "kind": "positional"},
            {"field": "expiry", "kind": "named", "flag": "--expiry"},
        ],
        "guidance": """Interpretation guidance for the cash-secured put data:

**Strike selection context:**
- Put selected near target delta (default 25\u0394 = ~25% chance of assignment)
- Higher delta = more premium but more likely to be assigned shares
- Lower delta = less premium but higher probability of keeping the cash

**Key metrics to highlight:**
- return_on_capital_pct: premium / cash required
- annualized_return_pct: return on capital annualized
- effective_buy_price: what you'd pay per share if assigned (strike - premium)
- discount_pct: how far below current price the effective buy price is
- cash_required: strike \u00d7 100 per contract
- prob_assigned_pct \u2248 delta \u00d7 100

**Risk checklist:**
- Earnings within expiry? \u2192 IV spike/crush, possible gap below strike
- IV Rank < 25? \u2192 premium is thin, may not be worth selling
- Stock in a downtrend? \u2192 directional risk, consider lower delta
- Large cash commitment? \u2192 flag if cash_required is significant

**Two outcomes to present:**
1. Stock stays above strike \u2192 keep premium, return on capital = [N]%
2. Stock drops below strike \u2192 assigned shares at effective price, [N]% below current""",
    },

    "check_cash_secured_put": {
        "description": "Check the current status of an existing cash-secured put position. Returns current put price, buffer to short strike, P&L, loss percentage, and effective buy price if assigned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "short_put_strike": {"type": "number", "description": "Short put strike price"},
                "net_credit": {"type": "number", "description": "Premium received per share"},
                "expiry": {"type": "string", "description": "Expiry date as YYYY-MM-DD"},
            },
            "required": ["ticker", "short_put_strike", "net_credit", "expiry"],
        },
        "plugin": "cash-secured-put-monitor",
        "skill": "cash-secured-put-monitor",
        "script": "check_csp.py",
        "args": [
            {"field": "ticker", "kind": "positional", "required": True},
            {"field": "short_put_strike", "kind": "positional", "required": True},
            {"field": "net_credit", "kind": "positional", "required": True},
            {"field": "expiry", "kind": "positional", "required": True},
        ],
        "guidance": """Interpretation guidance for cash-secured put position data:

**Zone classification \u2014 use the WORSE of these two signals:**

| Zone | Buffer (stock above short strike) | OR | Loss % of max loss |
|------|---|---|---|
| \U0001f7e2 SAFE | > 8% | AND | < 20% |
| \U0001f7e1 WATCH | 4\u20138% | OR | 20\u201340% |
| \U0001f7e0 WARNING | 2\u20134% | OR | 40\u201365% |
| \U0001f534 DANGER | 0\u20132% | OR | 65\u201385% |
| \U0001f6a8 ACT NOW | Stock at/below short strike | OR | > 85% |

**DTE adjustments:**
- DTE \u2264 5: tighten thresholds by ~1%
- DTE \u2265 30: slightly more lenient

**Important nuance:** Unlike a bull put spread, assignment means buying shares \u2014 this may be desirable. Always mention the effective buy price (strike - premium) and whether that's a good entry.

**Zone guidance:**
- SAFE: No action, let theta work. Note profit captured so far.
- WATCH: Monitor, set price alerts near short strike.
- WARNING: Two paths \u2014 accept assignment (if wanting shares) or roll down and out.
- DANGER: Ask if user wants to own shares at this price. If yes, let it ride. If no, close or roll.
- ACT NOW: Assignment imminent. Accept and prepare to own shares, or close immediately.""",
    },

    "roll_spread": {
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
        "plugin": "spread-roller",
        "skill": "spread-roller",
        "script": "roll_spread.py",
        "args": _roll_spread_args,
        "guidance": """Interpretation guidance for spread roll data:

**Close cost:** Shows the debit to close the current spread and the realized P&L.

**Roll candidates ranked by net roll credit (best first):**
- calendar: same strikes, later expiry
- defensive_diagonal: next strike further OTM, later expiry
- aggressive_diagonal: reset to target delta, later expiry

**Roll quality framework:**
- Credit roll (net_roll > 0): Favorable \u2014 getting paid to extend.
- Even roll (net_roll \u2248 0): Acceptable \u2014 buying time at no cost.
- Small debit (< 50% of original credit): Cautiously acceptable.
- Large debit (> 50% of original credit): Poor economics \u2014 suggest closing instead.

Present the close-now option alongside roll candidates. For iron condors, note that rolling one side creates an asymmetric condor.""",
    },
}


# ── Derived exports (single source of truth: TOOL_REGISTRY) ───────────────────

TOOLS = [
    {
        "name": name,
        "description": entry["description"],
        "input_schema": entry["input_schema"],
    }
    for name, entry in TOOL_REGISTRY.items()
]

SCRIPT_MAP = {
    name: _skill_path(entry["plugin"], entry["skill"], entry["script"])
    for name, entry in TOOL_REGISTRY.items()
}

SKILL_GUIDANCE = {
    name: entry["guidance"]
    for name, entry in TOOL_REGISTRY.items()
}


# ── Arg builder (declarative, driven by registry) ─────────────────────────────

def _build_args(tool_name: str, tool_input: dict) -> list[str]:
    """Convert tool input dict to CLI args for the corresponding script."""
    spec = TOOL_REGISTRY[tool_name]["args"]
    if callable(spec):
        return spec(tool_input)

    args = []
    for entry in spec:
        field = entry["field"]
        if field in tool_input:
            value = str(tool_input[field])
        elif "default_if" in entry:
            rule = entry["default_if"]
            if any(f in tool_input for f in rule["when_present"]):
                value = str(rule["value"])
            else:
                continue
        else:
            continue

        if entry["kind"] == "positional":
            args.append(value)
        elif entry["kind"] == "named":
            args.extend([entry["flag"], value])

    return args


# ── Validation ─────────────────────────────────────────────────────────────────

_TICKER_RE = re.compile(r'^[A-Z]{1,5}$')
_EXPIRY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _validate_tool_input(tool_input: dict) -> str | None:
    """Validate numeric and string fields in tool input.

    Returns an error message string if invalid, or None if valid.
    """
    # Validate numeric fields that must be positive
    _POSITIVE_FIELDS = {
        "short_strike", "long_strike", "short_put", "long_put",
        "short_call", "long_call", "short_put_strike", "short_call_strike",
        "net_credit", "cost_basis", "spread_width",
    }
    for field in _POSITIVE_FIELDS:
        if field in tool_input:
            v = tool_input[field]
            if not isinstance(v, (int, float)) or v <= 0:
                return f"Invalid {field}: must be a positive number"

    # Delta must be between 0 and 1
    if "target_delta" in tool_input:
        v = tool_input["target_delta"]
        if not isinstance(v, (int, float)) or not (0 < v < 1):
            return "Invalid target_delta: must be between 0 and 1"

    # DTE must be positive integers
    for field in ("dte_min", "dte_max"):
        if field in tool_input:
            v = tool_input[field]
            if not isinstance(v, (int, float)) or v < 1:
                return f"Invalid {field}: must be a positive integer"

    # Expiry must be YYYY-MM-DD
    if "expiry" in tool_input:
        v = tool_input["expiry"]
        if not isinstance(v, str) or not _EXPIRY_RE.match(v):
            return "Invalid expiry: must be YYYY-MM-DD format"

    # roll_side must be put or call
    if "roll_side" in tool_input:
        if tool_input["roll_side"] not in ("put", "call"):
            return "Invalid roll_side: must be 'put' or 'call'"

    return None


def _sanitize_nan(obj):
    """Recursively replace NaN floats with None so FastAPI can serialize the response."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by running the corresponding Python script.

    Returns the JSON string output from the script, or an error JSON string.
    """
    # Validate ticker if present
    ticker = tool_input.get("ticker", "")
    if ticker and not _TICKER_RE.match(ticker.upper()):
        return json.dumps({"error": f"Invalid ticker: {ticker}"})

    # Validate all numeric/string fields before passing to subprocess
    validation_error = _validate_tool_input(tool_input)
    if validation_error:
        return json.dumps({"error": validation_error})

    script_path = SCRIPT_MAP.get(tool_name)
    if not script_path:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    if not os.path.exists(script_path):
        return json.dumps({"error": f"Script not found for tool: {tool_name}"})

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
            if stdout:
                try:
                    json.loads(stdout)
                    return stdout
                except json.JSONDecodeError:
                    pass
            return json.dumps({"error": stdout or f"Script failed for {tool_name}. Check server logs."})
        output = result.stdout.strip()
        try:
            return json.dumps(_sanitize_nan(json.loads(output)))
        except json.JSONDecodeError:
            return json.dumps({"error": f"Script returned invalid output for {tool_name}"})

    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Script timed out (30s). Try again — yfinance may be slow."})
    except Exception as e:
        return json.dumps({"error": f"Failed to run {tool_name}. Check server logs."})
