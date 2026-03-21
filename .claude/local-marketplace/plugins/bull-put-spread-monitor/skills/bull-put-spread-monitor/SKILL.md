---
name: bull-put-spread-monitor
description: >
  Monitors an existing bull put spread position and classifies its current health
  into one of five zones: SAFE ZONE, WATCH ZONE, WARNING ZONE, DANGER ZONE, or ACT NOW.
  Use this skill whenever the user wants to check on an open bull put spread, asks if
  their spread is safe, wants to know if they should close or roll a position, mentions
  a spread they already have on and asks about status/health/risk, or says things like
  "check my spread", "how is my put spread doing", "should I be worried about my spread",
  "is my position safe", or any variant of monitoring or reviewing an existing options position.
  Always use this skill for position check-ins — don't attempt zone classification without it.
---

# Bull Put Spread Monitor

Given an existing bull put spread position, fetch current market data and classify
the trade's health into a clear action zone.

---

## Step 1 — Gather position details

You need all of these. Ask for anything missing:

| Input | Example |
|---|---|
| Ticker | NVDA |
| Short put strike (the one you sold) | 155 |
| Long put strike (the one you bought) | 140 |
| Original net credit received (per share) | 1.98 |
| Expiry date | 2026-05-01 |

---

## Step 2 — Fetch current position data

Run `check_position.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/check_position.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY
```

Replace with the actual absolute path to `check_position.py`. It lives alongside this SKILL.md.

Example:
```bash
python3 "$(git rev-parse --show-toplevel)/.claude/local-marketplace/plugins/bull-put-spread-monitor/skills/bull-put-spread-monitor/check_position.py" NVDA 155 140 1.98 2026-05-01
```

The script returns JSON with:
- `stock_price`, `dte`, `expiry`
- `buffer_pct` — how far (%) the stock is above the short strike. Negative = stock is BELOW the short strike.
- `be_buffer_pct` — how far (%) the stock is above the breakeven
- `current_spread_value` — what it costs to close the spread now (per share)
- `pnl_per_contract` — current P&L in dollars per contract (positive = profit, negative = loss)
- `loss_pct_of_max` — how much of the maximum possible loss has already been incurred (0–100%)

If the script errors, note it and work with whatever data you have, using web search to get the current stock price as a fallback.

---

## Step 3 — Classify the zone

Use the table below. **The worse of the two signals (buffer OR loss%) determines the zone** — a position can look fine on price but be deteriorating on P&L, or vice versa.

| Zone | Stock buffer above short strike | OR | Loss % of max loss |
|------|--------------------------------|----|--------------------|
| 🟢 SAFE | > 8% | AND | < 20% |
| 🟡 WATCH | 4 – 8% | OR | 20 – 40% |
| 🟠 WARNING | 2 – 4% | OR | 40 – 65% |
| 🔴 DANGER | 0 – 2% (stock still above) | OR | 65 – 85% |
| 🚨 ACT NOW | Stock at or below short strike | OR | > 85% of max loss |

**DTE adjustments** — as expiry approaches, gamma risk accelerates near the short strike, so tighten:
- DTE ≤ 5: shift all buffer thresholds up by ~1% (WATCH starts at 5%, WARNING at 3%)
- DTE ≥ 30: slightly more lenient — WATCH can start at 3% buffer

When both signals point to different zones, use the **worse one**.

---

## Step 4 — Output the status card

Use this layout:

```
╔══════════════════════════════════════════════╗
║  SPREAD MONITOR — [TICKER]                   ║
║  [SHORT_STRIKE]/[LONG_STRIKE] Put  ·  [EXPIRY] ║
╠══════════════════════════════════════════════╣
║  Status:  [ZONE EMOJI] [ZONE NAME]           ║
╠══════════════════════════════════════════════╣
║  Stock now:     $[price]                     ║
║  Short strike:  $[strike]  (buffer: [N]%)    ║
║  Breakeven:     $[be]      (buffer: [N]%)    ║
║  DTE remaining: [N] days                     ║
╠══════════════════════════════════════════════╣
║  Current P&L:   $[N]  per contract           ║
║  Loss % of max: [N]%  of $[max_loss]         ║
║  Cost to close: $[spread_value]  per share   ║
╚══════════════════════════════════════════════╝
```

Then write 2–4 sentences explaining:
1. Why this zone was assigned (which signal drove it — buffer, loss%, or both)
2. What the position needs to recover or stay on track
3. A concrete suggested action based on the zone (see below)

---

## Step 5 — Zone-specific guidance

Tailor your action suggestion to the zone:

**🟢 SAFE ZONE**
The trade is progressing well. No action needed — let theta work. Mention how much of the original credit has been locked in so far.

**🟡 WATCH ZONE**
Position is healthy but monitor more actively. Suggest checking again in a few days or setting a price alert near the short strike. No action yet.

**🟠 WARNING ZONE**
The trade is under pressure. Suggest the user decide in advance at what level they'd close — having a plan removes emotion. A common rule: close if the spread reaches 2× the original credit (i.e., you're losing the equivalent of what you made twice over).

**🔴 DANGER ZONE**
The position is at serious risk. Strongly suggest either closing now to limit loss, or rolling the short strike down and out to a further expiry for a credit/small debit. Explain the cost of waiting.

**🚨 ACT NOW**
The stock is at or below the short strike — assignment risk is real and the spread is approaching max loss. Recommend closing immediately. If the user wants to stay in the trade, the only sensible path is to roll well before expiry.

---

## Edge cases

- **Script returns no option prices**: The market may be closed or the strike no longer has liquidity. Use `buffer_pct` from the stock price alone to classify the zone, note that P&L data is unavailable, and label the zone as provisional.
- **Expiry has passed**: Tell the user the trade has expired and whether it expired worthless (profit) or was assigned (loss) based on the stock price vs. short strike at the time.
- **Multiple contracts**: All P&L figures scale linearly — multiply per-contract numbers by the number of contracts.
- **Stock exactly at short strike**: Classify as DANGER ZONE unless DTE ≤ 1, in which case ACT NOW (assignment is imminent).
