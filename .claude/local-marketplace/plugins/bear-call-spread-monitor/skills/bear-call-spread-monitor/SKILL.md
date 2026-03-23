---
name: bear-call-spread-monitor
description: >
  Monitors an existing bear call spread position and classifies its current health
  into one of five zones: SAFE ZONE, WATCH ZONE, WARNING ZONE, DANGER ZONE, or ACT NOW.
  Use this skill whenever the user wants to check on an open bear call spread, asks if
  their call spread is safe, wants to know if they should close or roll a position, mentions
  a bear call spread they already have on and asks about status/health/risk, or says things like
  "check my bear call spread", "how is my call spread doing", "is my bear call spread safe",
  "should I be worried about my call spread", or any variant of monitoring an existing
  bear call spread position. Always use this skill for position check-ins — don't attempt
  zone classification without it.
---

# Bear Call Spread Monitor

Given an existing bear call spread position, fetch current market data and classify
the trade's health into a clear action zone.

---

## Step 1 — Gather position details

You need all of these. Ask for anything missing:

| Input | Example |
|---|---|
| Ticker | AAPL |
| Short call strike (the one you sold) | 260 |
| Long call strike (the one you bought) | 270 |
| Original net credit received (per share) | 1.50 |
| Expiry date | 2026-05-01 |

---

## Step 2 — Fetch current position data

Run `check_bear_call.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/check_bear_call.py TICKER SHORT_STRIKE LONG_STRIKE NET_CREDIT EXPIRY
```

The script returns JSON with:
- `stock_price`, `dte`, `expiry`
- `buffer_pct` — how far (%) the stock is below the short strike. Negative = stock is ABOVE the short strike.
- `be_buffer_pct` — how far (%) the stock is below the breakeven
- `current_spread_value` — what it costs to close the spread now (per share)
- `pnl_per_contract` — current P&L in dollars per contract
- `loss_pct_of_max` — how much of the maximum possible loss has been incurred (0–100%)

---

## Step 3 — Classify the zone

| Zone | Stock buffer below short strike | OR | Loss % of max loss |
|------|--------------------------------|----|--------------------|
| 🟢 SAFE | > 8% | AND | < 20% |
| 🟡 WATCH | 4 – 8% | OR | 20 – 40% |
| 🟠 WARNING | 2 – 4% | OR | 40 – 65% |
| 🔴 DANGER | 0 – 2% (stock still below) | OR | 65 – 85% |
| 🚨 ACT NOW | Stock at or above short strike | OR | > 85% of max loss |

**DTE adjustments:**
- DTE ≤ 5: shift all buffer thresholds up by ~1%
- DTE ≥ 30: slightly more lenient

When both signals point to different zones, use the **worse one**.

---

## Step 4 — Output the status card

```
╔══════════════════════════════════════════════╗
║  SPREAD MONITOR — [TICKER]                   ║
║  [SHORT_STRIKE]/[LONG_STRIKE] Call · [EXPIRY] ║
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

---

## Step 5 — Zone-specific guidance

**🟢 SAFE ZONE** — No action needed. Let theta work.

**🟡 WATCH ZONE** — Monitor more actively. Set a price alert near the short strike.

**🟠 WARNING ZONE** — Trade is under pressure. Suggest deciding exit level in advance.

**🔴 DANGER ZONE** — Strongly suggest closing or rolling the short call up and out.

**🚨 ACT NOW** — Stock is at or above the short strike. Close immediately or roll.
