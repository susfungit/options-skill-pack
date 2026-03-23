---
name: cash-secured-put-monitor
description: >
  Monitors an existing cash-secured put position and classifies its current health
  into one of five zones: SAFE ZONE, WATCH ZONE, WARNING ZONE, DANGER ZONE, or ACT NOW.
  Use this skill whenever the user wants to check on an open cash-secured put, asks if
  their CSP is safe, wants to know if they'll be assigned, mentions a cash-secured put
  they have on and asks about status/health/risk, or says things like "check my CSP",
  "how is my put doing", "is my cash-secured put safe", "will I get assigned on my put",
  "CSP status", or any variant of monitoring an existing cash-secured put position.
  Always use this skill for CSP check-ins — don't attempt zone classification without it.
---

# Cash-Secured Put Monitor

Given an existing cash-secured put position, fetch current market data and classify
the trade's health into a clear action zone.

---

## Step 1 — Gather position details

You need all of these. Ask for anything missing:

| Input | Example |
|---|---|
| Ticker | AAPL |
| Short put strike (sold put) | 200 |
| Premium received (per share) | 3.50 |
| Expiry date | 2026-05-01 |

---

## Step 2 — Fetch current position data

Run `check_csp.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/check_csp.py TICKER SHORT_PUT_STRIKE NET_CREDIT EXPIRY
```

Replace with the actual absolute path to `check_csp.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `stock_price`, `dte`, `expiry`
- `buffer_pct` — how far (%) the stock is above the short put. Positive = OTM (safe). Negative = stock is BELOW the strike (ITM).
- `current_put_value` — cost to buy back the put now
- `pnl_per_contract` — current P&L in dollars (positive = profit, negative = unrealized loss)
- `loss_pct_of_max` — how much of the maximum loss has been incurred (0–100%)
- `short_put.current_delta` — current delta of the short put
- `breakeven` — strike minus premium
- `be_buffer_pct` — buffer above breakeven

If the script errors, note it and work with whatever data you have.

---

## Step 3 — Classify the zone

For cash-secured puts, the "threat" is the stock dropping below the short put strike, leading to assignment. The buffer measures how far the stock is above the strike.

**Important nuance**: Unlike a bull put spread where max loss is capped by the long put, a CSP's max loss is the full strike price minus premium (stock goes to zero). However, assignment is often an acceptable outcome — the user is buying shares they want at a discount. The zone classification reflects *assignment risk and P&L health*.

| Zone | Stock buffer above short strike | OR | Loss % of max loss |
|------|---|---|---|
| 🟢 SAFE | > 8% | AND | < 20% |
| 🟡 WATCH | 4–8% | OR | 20–40% |
| 🟠 WARNING | 2–4% | OR | 40–65% |
| 🔴 DANGER | 0–2% (stock still above) | OR | 65–85% |
| 🚨 ACT NOW | Stock at or below short strike | OR | > 85% of max loss |

**DTE adjustments:**
- DTE ≤ 5: shift all buffer thresholds up by ~1% (more urgent)
- DTE ≥ 30: slightly more lenient — WATCH can start at 3% buffer

When both signals point to different zones, use the **worse one**.

---

## Step 4 — Output the status card

```
╔══════════════════════════════════════════════════════╗
║  CSP MONITOR — [TICKER]                               ║
║  SELL $[strike] Put  ·  [EXPIRY]                      ║
╠══════════════════════════════════════════════════════╣
║  Status:  [ZONE EMOJI] [ZONE NAME]                    ║
╠══════════════════════════════════════════════════════╣
║  Stock now:        $[price]                           ║
║  Put strike:       $[strike]  (buffer: [N]%)          ║
║  Breakeven:        $[breakeven] (buffer: [N]%)        ║
║  DTE remaining:    [N] days                           ║
╠══════════════════════════════════════════════════════╣
║  Current P&L:      $[N]  per contract                 ║
║  Put value now:    $[N]  (was $[credit] at open)      ║
║  Loss % of max:    [N]%                               ║
║  Cost to close:    $[N]  per share                    ║
║  Cash committed:   $[N]  per contract                 ║
╚══════════════════════════════════════════════════════╝
```

Then write 2–4 sentences explaining:
1. Why this zone was assigned (buffer, loss%, or both)
2. Whether assignment is likely and what the effective purchase price would be
3. A concrete suggested action based on the zone (see below)

---

## Step 5 — Zone-specific guidance

**🟢 SAFE ZONE**
The put is comfortably out of the money. No action needed — let theta decay work. Note how much premium has been captured so far and how much time remains.

**🟡 WATCH ZONE**
Stock is drifting toward the strike but still manageable. Suggest checking again in a few days or setting a price alert. No action needed yet.

**🟠 WARNING ZONE**
The stock is approaching the strike. Present two paths:
1. **Happy to own shares**: No action needed — assignment means buying at the effective price (strike minus premium), which is what the user planned.
2. **Want to avoid assignment**: Roll the put down and out — buy back the current put, sell a lower strike at a later expiry.

**🔴 DANGER ZONE**
Assignment is becoming likely. Key question: does the user *want* to own the shares?
- **Yes**: Do nothing. Being assigned at the effective price was the plan.
- **No**: Buy back the put now (at a loss) or roll down and out. The deeper ITM, the more expensive.

**🚨 ACT NOW**
The stock is at or below the short strike — assignment is very likely. Decision point:
- **Accept assignment**: Take delivery of shares at the strike. Effective cost = strike - premium. If the user still likes the stock, this is the planned outcome.
- **Avoid assignment**: Buy back the put immediately (significant loss on the put). Consider whether the loss is better than owning shares at this price.
- **Roll**: If there's time, roll down to a lower strike at a later expiry to collect more premium and lower the effective buy price.

---

## Edge cases

- **Script returns no option prices**: Use buffer_pct from stock price alone to classify provisionally.
- **Expiry has passed**: Report whether the put expired worthless (max profit) or was assigned (shares acquired at effective price).
- **Multiple contracts**: All P&L figures scale linearly. Multiply by number of contracts. Also multiply cash required.
- **Stock exactly at short strike**: DANGER ZONE unless DTE ≤ 1, then ACT NOW.
- **Stock has risen significantly**: The put is likely cheap to buy back. Note this is a good opportunity to close for a profit and potentially sell a new put at a higher strike.
