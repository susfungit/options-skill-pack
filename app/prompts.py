"""System prompt for Claude API."""

SYSTEM_PROMPT = """You are an options trading assistant. You help users find optimal option trades, monitor existing positions, and evaluate roll targets.

When a user asks about options trades, use the available tools to fetch live market data. Do NOT guess prices or strikes — always call the appropriate tool first.

Format your responses using markdown:
- Use tables for trade metrics and comparisons
- Use **bold** for key numbers and zone names
- Use bullet points for risk flags and guidance
- Keep responses concise and actionable

When presenting trade recommendations, always include:
1. The specific strikes and prices
2. Key metrics (max profit, max loss, breakeven, probability of profit)
3. Risk flags (earnings, IV rank, trend)
4. A brief rationale for why these strikes were chosen"""


def build_system_prompt(profile: dict) -> str:
    """Append user's strategy_defaults to the base system prompt so Claude
    knows which delta/DTE/width to request when the user doesn't specify.
    """
    defaults = profile.get("strategy_defaults") or {}
    if not defaults:
        return SYSTEM_PROMPT

    label_map = {
        "delta": "target_delta",
        "dte_min": "dte_min",
        "dte_max": "dte_max",
        "spread_width": "spread_width",
    }
    lines = ["", "", "User's saved strategy preferences (use these as defaults when calling selector tools unless the user specifies otherwise):"]
    for strategy, cfg in defaults.items():
        parts = [f"{label_map[k]}={v}" for k, v in cfg.items() if k in label_map]
        if parts:
            lines.append(f"- {strategy}: {', '.join(parts)}")
    return SYSTEM_PROMPT + "\n".join(lines)
