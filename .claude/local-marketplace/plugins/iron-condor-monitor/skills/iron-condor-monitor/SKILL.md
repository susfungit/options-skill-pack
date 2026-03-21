---
name: iron-condor-monitor
description: >
  Monitors an existing iron condor position and classifies its current health
  into one of five zones: SAFE ZONE, WATCH ZONE, WARNING ZONE, DANGER ZONE, or ACT NOW.
  Use this skill whenever the user wants to check on an open iron condor, asks if their
  condor is safe, wants to know if they should close or roll a position, mentions an iron
  condor they already have on and asks about status/health/risk, or says things like
  "check my iron condor", "how is my condor doing", "is my iron condor safe",
  "should I be worried about my condor", or any variant of monitoring an existing
  four-legged options position. Always use this skill for iron condor check-ins —
  don't attempt zone classification without it.
---

# Iron Condor Monitor

Given an existing iron condor position, fetch current market data and classify
the trade's health into a clear action zone.

---

## Step 1 — Gather position details

You need all of these. Ask for anything missing:

| Input | Example |
|---|---|
| Ticker | AAPL |
| Short put strike (sold put) | 220 |
| Long put strike (bought put) | 200 |
| Short call strike (sold call) | 275 |
| Long call strike (bought call) | 300 |
| Total net credit received (per share, both sides) | 2.86 |
| Expiry date | 2026-05-01 |

---

## Step 2 — Fetch current position data

Run `check_iron_condor.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/check_iron_condor.py TICKER SHORT_PUT LONG_PUT SHORT_CALL LONG_CALL NET_CREDIT EXPIRY
```

Replace with the actual absolute path to `check_iron_condor.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `stock_price`, `dte`, `expiry`
- `buffer_pct_put` — how far (%) the stock is above the short put. Negative = stock below short put.
- `buffer_pct_call` — how far (%) the stock is below the short call. Negative = stock above short call.
- `worst_buffer_pct` — the smaller of the two buffers (determines zone)
- `worst_side` — which side ("put" or "call") is under more pressure
- `current_spread_value` — cost to close all 4 legs now (per share)
- `pnl_per_contract` — current P&L in dollars (positive = profit, negative = loss)
- `loss_pct_of_max` — how much of max possible loss has been incurred (0–100%)
- `breakeven_low`, `breakeven_high` — the profit zone boundaries

If the script errors, note it and work with whatever data you have.

---

## Step 3 — Classify the zone

An iron condor has **two sides** that can be threatened. Use the **worse of the two buffer signals** combined with the loss% signal. The worst signal determines the zone.

| Zone | Worst buffer (put or call side) | OR | Loss % of max loss |
|------|--------------------------------|----|--------------------|
| 🟢 SAFE | > 8% | AND | < 20% |
| 🟡 WATCH | 4 – 8% | OR | 20 – 40% |
| 🟠 WARNING | 2 – 4% | OR | 40 – 65% |
| 🔴 DANGER | 0 – 2% (stock still in range) | OR | 65 – 85% |
| 🚨 ACT NOW | Stock outside short strikes | OR | > 85% of max loss |

**DTE adjustments:**
- DTE ≤ 5: shift all buffer thresholds up by ~1%
- DTE ≥ 30: slightly more lenient — WATCH can start at 3% buffer

When both signals point to different zones, use the **worse one**.

---

## Step 4 — Output the status card

```
╔═══════════════════════════════════════════════════════╗
║  IRON CONDOR MONITOR — [TICKER]                       ║
║  [SHORT_PUT]/[LONG_PUT] · [SHORT_CALL]/[LONG_CALL]    ║
║  Expiry: [DATE]                                        ║
╠═══════════════════════════════════════════════════════╣
║  Status:  [ZONE EMOJI] [ZONE NAME]                    ║
╠═══════════════════════════════════════════════════════╣
║  Stock now:        $[price]                            ║
║  Put buffer:       [N]% above $[short_put]             ║
║  Call buffer:      [N]% below $[short_call]            ║
║  Worst buffer:     [N]% ([put/call] side)              ║
║  DTE remaining:    [N] days                            ║
╠═══════════════════════════════════════════════════════╣
║  Current P&L:      $[N]  per contract                  ║
║  Loss % of max:    [N]%  of $[max_loss]                ║
║  Cost to close:    $[spread_value]  per share          ║
║  Profit zone:      $[low] – $[high]                    ║
╚═══════════════════════════════════════════════════════╝
```

Then write 2–4 sentences explaining:
1. Why this zone was assigned (which side is under pressure, or both are fine)
2. What the position needs to stay profitable (stock stays within the profit zone)
3. A concrete suggested action based on the zone (see below)

---

## Step 5 — Zone-specific guidance

**🟢 SAFE ZONE**
Both sides have comfortable buffers. No action needed — let theta work. Note how much of the original credit has decayed so far and what percentage of max profit has been captured.

**🟡 WATCH ZONE**
One side is getting closer but still manageable. Suggest checking again in a few days or setting price alerts near the threatened short strike. Identify which side (put or call) is under pressure.

**🟠 WARNING ZONE**
One side is under real pressure. Suggest deciding in advance at what price to close. A common rule: close the threatened side (or the whole condor) if the spread reaches 2× the original credit. Consider rolling the tested side further out.

**🔴 DANGER ZONE**
The stock is very close to one of the short strikes. Strongly suggest either closing the entire condor, or closing just the threatened side and keeping the unthreatened side open to collect remaining premium. Explain the cost of waiting.

**🚨 ACT NOW**
The stock has breached or is at a short strike — assignment risk is real on the tested side. Recommend closing immediately. If the user wants to stay in, the only sensible path is to roll the tested side well away from the current price.

---

## Edge cases

- **Script returns no option prices**: Use buffer% from stock price alone to classify provisionally.
- **Expiry has passed**: Report whether the condor expired worthless (max profit) or was assigned on one/both sides.
- **Multiple contracts**: P&L scales linearly.
- **Stock exactly at a short strike**: DANGER ZONE unless DTE ≤ 1, then ACT NOW.
- **One side breached but other side safe**: Focus guidance on the breached side. Note the unthreatened side still has value — closing the breached side alone may be better than closing the entire condor.
- **Stock moves through to long strike**: The position is at or near max loss on the breached side. ACT NOW — little to gain by holding.
