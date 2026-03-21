---
name: covered-call-monitor
description: >
  Monitors an existing covered call position and classifies its current health
  into one of five zones: SAFE ZONE, WATCH ZONE, WARNING ZONE, DANGER ZONE, or ACT NOW.
  Use this skill whenever the user wants to check on an open covered call, asks if their
  call is safe, wants to know if their shares will get called away, mentions a covered call
  they have on and asks about status/health/risk, or says things like "check my covered call",
  "how is my call doing", "is my covered call safe", "will I get assigned", "will my shares
  get called away", "covered call status", or any variant of monitoring an existing covered
  call position. Always use this skill for covered call check-ins — don't attempt zone
  classification without it.
---

# Covered Call Monitor

Given an existing covered call position, fetch current market data and classify
the trade's health into a clear action zone.

---

## Step 1 — Gather position details

You need all of these. Ask for anything missing:

| Input | Example |
|---|---|
| Ticker | AAPL |
| Short call strike (sold call) | 260 |
| Premium received (per share) | 3.33 |
| Expiry date | 2026-04-24 |
| Cost basis *(optional)* | 245.00 |

---

## Step 2 — Fetch current position data

Run `check_covered_call.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/check_covered_call.py TICKER SHORT_CALL_STRIKE NET_CREDIT EXPIRY [COST_BASIS]
```

Replace with the actual absolute path to `check_covered_call.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `stock_price`, `dte`, `expiry`
- `buffer_pct` — how far (%) the stock is below the short call. Positive = OTM (safe). Negative = ITM (stock above strike).
- `current_call_value` — cost to buy back the call now
- `pnl_per_contract` — current P&L in dollars (positive = profit, negative = unrealized loss on the call)
- `short_call.current_delta` — current delta of the short call
- `intrinsic_value` — how much the call is in the money (0 if OTM)
- `time_value` — remaining time premium
- If cost basis was provided: `effective_cost_basis`, `called_away_pnl`, `called_away_return_pct`

If the script errors, note it and work with whatever data you have.

---

## Step 3 — Classify the zone

For covered calls, the "threat" is the stock rising above the short call strike, leading to assignment. The buffer measures how far the stock is below the strike.

**Important nuance**: Unlike put spreads where breaching the short strike means losses, being called away on a covered call is often a perfectly acceptable outcome — the user keeps the premium plus any stock gains up to the strike. The zone classification here reflects *assignment risk*, not necessarily *financial risk*.

| Zone | Buffer (strike above stock) | OR | Call value vs credit |
|------|---|---|---|
| 🟢 SAFE | > 8% below strike | AND | Call value < 1.5× credit |
| 🟡 WATCH | 4–8% below strike | OR | Call value 1.5–2× credit |
| 🟠 WARNING | 2–4% below strike | OR | Call value 2–3× credit |
| 🔴 DANGER | 0–2% below strike | OR | Call value 3–5× credit |
| 🚨 ACT NOW | Stock at or above strike (ITM) | OR | Call value > 5× credit |

**DTE adjustments:**
- DTE ≤ 5: shift all buffer thresholds up by ~1%
- DTE ≥ 30: slightly more lenient — WATCH can start at 3% buffer

When both signals point to different zones, use the **worse one**.

---

## Step 4 — Output the status card

```
╔══════════════════════════════════════════════════════╗
║  COVERED CALL MONITOR — [TICKER]                      ║
║  SELL $[strike] Call  ·  [EXPIRY]                     ║
╠══════════════════════════════════════════════════════╣
║  Status:  [ZONE EMOJI] [ZONE NAME]                    ║
╠══════════════════════════════════════════════════════╣
║  Stock now:        $[price]                           ║
║  Call strike:      $[strike]  (buffer: [N]%)          ║
║  Call delta:       [N]                                ║
║  DTE remaining:    [N] days                           ║
╠══════════════════════════════════════════════════════╣
║  Current P&L:      $[N]  per contract (on call)       ║
║  Call value now:   $[N]  (was $[credit] at open)      ║
║  Intrinsic:        $[N]  ·  Time value: $[N]          ║
║  Max profit:       $[N]  (if expires OTM)             ║
╚══════════════════════════════════════════════════════╝
```

If cost basis was provided, add:
```
║  Cost basis:          $[N] → $[effective] (after premium) ║
║  Called-away P&L:     +$[N] per share (+[N]%)             ║
```

Then write 2–4 sentences explaining:
1. Why this zone was assigned (buffer, call value ratio, or both)
2. Whether assignment is likely and whether it would be a good or bad outcome
3. A concrete suggested action based on the zone (see below)

---

## Step 5 — Zone-specific guidance

**🟢 SAFE ZONE**
The call is comfortably out of the money. No action needed — let theta decay work in your favor. Note how much time value remains and how much premium has been captured so far.

**🟡 WATCH ZONE**
The stock is getting closer to the strike but still manageable. Suggest checking again in a few days or setting a price alert near the strike. No action needed yet.

**🟠 WARNING ZONE**
The stock is approaching the strike. Present two paths:
1. **Let it ride**: If the user is comfortable being called away at the strike (especially if they profit on the shares), no need to act.
2. **Roll up and out**: Buy back the current call, sell a higher strike at a later expiry to collect more premium and raise the cap.

**🔴 DANGER ZONE**
Assignment is becoming likely. Key question: does the user *want* to be called away?
- **Yes (or indifferent)**: Do nothing. Being assigned at the strike + keeping the premium is the planned outcome.
- **No (wants to keep shares)**: Buy back the call now (will be at a loss on the call) or roll up and out. The longer they wait, the more expensive the buyback.

**🚨 ACT NOW**
The call is in the money — assignment is very likely, especially near expiration. This is the decision point:
- **Accept assignment**: Keep the premium, sell shares at the strike. If cost basis < strike, this is a profitable outcome. Remind the user of their called-away P&L.
- **Avoid assignment**: Buy back the call immediately (at a loss) or roll to a higher strike/later expiry. This gets expensive the deeper ITM the call goes.
- **Ex-dividend warning**: If there's an upcoming ex-dividend date, early assignment risk is elevated for ITM calls.

---

## Edge cases

- **Script returns no option prices**: Use buffer_pct from stock price alone to classify provisionally.
- **Expiry has passed**: Report whether the call expired worthless (max profit — user keeps shares and premium) or was assigned (shares sold at strike — report final P&L).
- **Multiple contracts**: All P&L figures scale linearly. Multiply by number of contracts.
- **Stock exactly at strike**: DANGER ZONE unless DTE ≤ 1, then ACT NOW.
- **No cost basis provided**: Skip the cost basis section. Focus on call P&L and buffer only.
- **Stock has dropped significantly**: The call is likely cheap to buy back. Note this is a good opportunity to close the call for a profit and potentially sell a new one at a lower strike.
