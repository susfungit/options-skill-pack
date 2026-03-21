---
name: spread-roller
description: >
  Finds roll targets for bull put spreads and iron condors when a position needs
  to be rolled out (later expiry) or diagonally (different strike + later expiry).
  Use this skill whenever the user wants to roll a spread, find roll targets, asks
  "should I roll", "roll my put spread", "roll my condor", "roll down and out",
  "what are my rolling options", "find roll targets for my spread", "roll to a
  later expiry", or any variant of finding new strikes/expiries for an existing
  options position. Also trigger when the user has a spread in WARNING/DANGER/ACT NOW
  and asks what they can do. Always use this skill — don't attempt roll analysis without it.
---

# Spread Roller

Given an existing bull put spread or iron condor position, find roll targets at
future expiries — calendar rolls (same strikes) and diagonal rolls (adjusted strikes).

---

## Step 1 — Gather position details

Ask for anything missing:

**For a bull put spread:**

| Input | Example |
|---|---|
| Ticker | NVDA |
| Short put strike (sold) | 155 |
| Long put strike (bought) | 140 |
| Net credit received (per share) | 1.98 |
| Expiry date | 2026-05-01 |

**For an iron condor (rolling one side):**

| Input | Example |
|---|---|
| Ticker | AAPL |
| Short put strike | 220 |
| Long put strike | 200 |
| Short call strike | 275 |
| Long call strike | 300 |
| Total net credit (per share, both sides) | 2.86 |
| Expiry date | 2026-05-01 |
| Which side to roll | put |

Also accept an optional **target delta** override (default: 0.20 for put spreads, 0.16 for iron condors).

---

## Step 2 — Fetch roll candidates

Run `roll_spread.py` from the same directory as this SKILL.md:

**Bull put spread:**
```bash
python3 /path/to/roll_spread.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY [TARGET_DELTA]
```

**Iron condor (roll one side):**
```bash
python3 /path/to/roll_spread.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY ROLL_SIDE [TARGET_DELTA]
```

Replace with the actual absolute path to `roll_spread.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `close_cost` — current cost to close the existing spread (net debit, per-leg mids)
- `close_cost.realized_pnl` — P&L if you just close now (positive = profit, negative = loss)
- `roll_candidates` — array of roll options, ranked by net roll credit (best first), each with:
  - `type` — `calendar` (same strikes), `defensive_diagonal` (next strike further OTM), or `aggressive_diagonal` (reset to target delta)
  - `new_expiry`, `new_dte`, `new_short_strike`, `new_long_strike`
  - `new_credit` — credit received for opening the new spread
  - `net_roll_credit` — new credit minus close cost (positive = you get paid to roll)
  - `new_breakeven`, `new_max_profit`, `new_max_loss`, `new_return_on_risk_pct`
  - `new_prob_profit_pct`, `new_short_delta`, `new_short_iv_pct`
  - `roll_verdict` — `credit`, `even`, or `debit`

If the script errors, note it and fall back to Step 3.

---

## Step 3 — Fallback estimation (if script fails)

When live data is unavailable:

1. **Close cost estimate**: Use the monitor's `current_spread_value` if you ran the monitor earlier.
2. **New credit estimate**: A calendar roll typically adds 30–60% more credit than the current spread value, depending on IV and DTE extension.
3. **Rule of thumb**: Rolling out 2–4 weeks on a ~20Δ put spread usually yields a net credit if IV hasn't collapsed.

These are rough — flag them clearly as estimates.

---

## Step 4 — Present the roll comparison

Output a comparison card:

```
╔════════════════════════════════════════════════════════════════╗
║  ROLL ANALYSIS — [TICKER] [SIDE] spread                       ║
║  Current: [SHORT]/[LONG] · Expiry [DATE] · [DTE]d remaining   ║
╠════════════════════════════════════════════════════════════════╣
║  Close now:  $[debit] debit  →  P&L: $[realized_pnl]          ║
╠════════════════════════════════════════════════════════════════╣
║  #  Type         Expiry      Strikes    Net Roll   PoP   RoR  ║
║  1  Calendar     [date]      [S]/[L]    +$0.75cr   78%   22%  ║
║  2  Def Diag     [date]      [S]/[L]    +$0.42cr   82%   18%  ║
║  3  Agg Diag     [date]      [S]/[L]    -$0.15db   85%   14%  ║
║  ...                                                           ║
╚════════════════════════════════════════════════════════════════╝
```

Then write 3–5 sentences covering:
1. **Best candidate** — which roll gives the best net credit and why
2. **Trade-off** — calendar preserves your thesis but same risk; diagonal gives more room but less credit
3. **Recommendation** — based on the roll quality (see decision framework below)

---

## Step 5 — Roll quality decision framework

**Net credit roll (verdict = "credit")**
Favorable — you get paid to extend the trade. Highlight how the additional credit improves the breakeven. This is the ideal outcome.

**Net even roll (verdict = "even")**
Acceptable — you're buying more time at no cost. Worth doing if the original thesis is intact and you just need more DTE.

**Net debit roll < 50% of original credit (verdict = "debit", small)**
Cautiously acceptable — you're paying to stay in, but the total invested credit is still reasonable relative to the spread width. Flag that this reduces your effective credit.

**Net debit roll > 50% of original credit (verdict = "debit", large)**
Poor roll economics. Suggest the user consider:
- Just closing the position (take the loss, move on)
- Waiting for a better entry to open a fresh position
- Only roll if they have strong directional conviction

**No viable candidates**
If all rolls are deep debits or no future expiries exist, recommend closing the position.

---

## Step 6 — Iron condor specifics

When rolling one side of an iron condor:
- The untested side stays open and continues to decay (good)
- Only the tested side gets rolled
- The new combined credit = untested side's original credit + new rolled side credit
- Recalculate the full condor's breakevens if the user asks

Remind the user: rolling one side changes the risk profile — the condor becomes asymmetric. If the stock reverses sharply the other way, the untested side (which was left alone) may now be at risk.

---

## Edge cases

- **Expiry already passed**: Cannot roll — report that the position has expired.
- **No future expiries listed**: Some tickers may not have chains far enough out. Report this clearly.
- **All rolls are debits**: Still show them — user may accept a debit roll to avoid max loss. But flag it.
- **Very low DTE (≤ 3 days)**: Urgency is high. Lead with "close now" as the primary option; rolls are secondary.
- **Multiple contracts**: All P&L figures scale linearly. Multiply by the number of contracts.
