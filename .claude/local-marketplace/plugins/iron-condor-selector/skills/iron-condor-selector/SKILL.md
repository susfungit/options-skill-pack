---
name: iron-condor-selector
description: >
  Identifies the optimal strikes for an iron condor (sell put + buy put + sell call + buy call) for a given stock.
  Use this skill whenever the user wants to: set up an iron condor, find strikes for a neutral options trade,
  build a range-bound strategy, sell premium on both sides, or asks about "iron condor on [stock]",
  "sell strangles with protection", "neutral options trade", "range-bound strategy on [stock]",
  "set up an iron condor", or any variant of selecting option legs for a four-legged credit spread.
  Also trigger when the user mentions a ticker and wants to profit from a stock staying in a range.
  Always use this skill — don't attempt iron condor strike selection without it.
---

# Iron Condor Selector Skill

Given a stock ticker and trade parameters, identify the optimal short put, long put, short call,
and long call for an iron condor, then present a complete trade summary with risk/reward metrics.

---

## Step 1 — Gather inputs

Collect the following. Ask for anything missing:

| Parameter | Default if omitted |
|---|---|
| Ticker symbol | Required — ask |
| Expiry preference | ~6 weeks out (look for 35–45 DTE) |
| Short strike delta target | 0.16 (16Δ) each side |
| Wing width method | Long strikes = 10% beyond short strikes |
| Number of contracts | 1 (for display; scales linearly) |

---

## Step 2 — Fetch live option chain data

**Primary method: run the fetch_iron_condor.py script.**

The skill ships with `fetch_iron_condor.py` in the same directory as this SKILL.md file.
Run it via Bash before doing any web searches:

```bash
python3 /path/to/fetch_iron_condor.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]
```

Substitute the actual absolute path to `fetch_iron_condor.py` — it lives alongside this SKILL.md.

The script returns JSON with all fields pre-calculated:
- `price`, `expiry`, `dte`
- `put_side`: `short_put` (strike, mid, delta, iv), `long_put` (strike, mid), `credit`, `width`
- `call_side`: `short_call` (strike, mid, delta, iv), `long_call` (strike, mid), `credit`, `width`
- `total_credit`, `max_profit`, `max_loss`, `breakeven_low`, `breakeven_high`, `profit_zone`
- `return_on_risk_pct`, `prob_profit_pct`
- `delta_source`: indicates data quality

**If `delta_source` is not `"live"`**: label prices as `(est.)` in the trade card.
**If the script errors**: fall back to web search + estimation (Step 3).

### 2b. Supplemental data via web search (always run in parallel)

Even when live chain data succeeds, use web search for context:

Search 1: `[TICKER] stock price earnings date dividend 2025 2026`
Extract: upcoming earnings date, ex-dividend date, recent price trend, 52-week range

Search 2: `[TICKER] IV rank implied volatility rank options`
Extract: IV Rank (IVR) or IV Percentile
- IVR > 50 → elevated IV → selling premium is attractive → POSITIVE for iron condors
- IVR < 30 → low IV → premium is thin → ⚠️ CAUTION — iron condor less attractive

---

## Step 3 — Fallback: estimate strikes when live data unavailable

Use this **only if** fetch_iron_condor.py fails.

```
Put side:
  Short put strike  ≈ stock_price × (1 - otm_pct)
    where otm_pct for 16Δ ≈ 1.0 × IV × sqrt(DTE/365)
  Long put strike   = round(short_put × 0.90, nearest listed strike)

Call side:
  Short call strike ≈ stock_price × (1 + otm_pct)
  Long call strike  = round(short_call × 1.10, nearest listed strike)

Total credit ≈ put_credit + call_credit
```

Always label estimated values clearly: `(estimated — verify on your broker's chain)`.

---

## Step 4 — Risk / Reward calculations

Once all four strikes and credits are known:

```
total_credit    = put_credit + call_credit
wider_width     = max(put_spread_width, call_spread_width)
max_profit      = total_credit × 100                          (per contract)
max_loss        = (wider_width − total_credit) × 100
breakeven_low   = short_put_strike − total_credit
breakeven_high  = short_call_strike + total_credit
profit_zone     = breakeven_low to breakeven_high
pop             ≈ 1 − put_delta − call_delta                  (prob stock stays between short strikes)
return_on_risk  = total_credit / (wider_width − total_credit) × 100
```

---

## Step 5 — Risk signal checklist

Run through these and flag any ⚠️:

- [ ] **Earnings within expiry window?** → ⚠️ IV will spike before and crush after; iron condor risk spikes on directional move
- [ ] **IV Rank < 25?** → ⚠️ thin premium; iron condors thrive on elevated IV — consider waiting
- [ ] **Stock in a strong trend?** → ⚠️ iron condors are range-bound strategies; trending stocks are dangerous — consider widening or skipping
- [ ] **Ex-dividend date within expiry?** → note it; early assignment risk on short call
- [ ] **Put/call skew significant?** → note if put side credit is much larger than call side (common) — this is normal, not a red flag
- [ ] **Spread widths unequal?** → if one side is much wider, max loss is determined by the wider side

---

## Step 6 — Output format

Present a clean, structured trade card followed by prose rationale:

```
╔══════════════════════════════════════════════════════╗
║  IRON CONDOR — [TICKER]                              ║
║  Expiry: [DATE]  ·  DTE: [N] days                    ║
╠══════════════════════════════════════════════════════╣
║  PUT SIDE (bull put spread):                         ║
║    SELL  [SHORT_PUT]  Put   @ $[price]               ║
║    BUY   [LONG_PUT]   Put   @ $[price]               ║
║    Credit: $[put_credit]  ·  Width: $[put_width]     ║
╠══════════════════════════════════════════════════════╣
║  CALL SIDE (bear call spread):                       ║
║    SELL  [SHORT_CALL] Call  @ $[price]                ║
║    BUY   [LONG_CALL]  Call  @ $[price]               ║
║    Credit: $[call_credit]  ·  Width: $[call_width]   ║
╠══════════════════════════════════════════════════════╣
║  Total credit:   $[total]  per share                 ║
║  Max profit:     $[N]  per contract                  ║
║  Max loss:       $[N]  per contract                  ║
║  Profit zone:    $[low] – $[high]                    ║
║  Prob. profit:   ~[N]%                               ║
║  Return/risk:    [N]%                                ║
╚══════════════════════════════════════════════════════╝
```

After the trade card, write 3–5 sentences covering:
1. Why these strikes were chosen (delta, OTM%, IV context)
2. The profit zone — stock needs to stay between $[low] and $[high]
3. Key risk (what breaks the trade — a large directional move in either direction)
4. Any flags from the risk checklist
5. Whether the put/call credit split is typical or skewed

---

## Edge cases

- **Can't find option chain**: Use estimation from Step 3 and clearly label all values as estimated.
- **Multiple expiries close to target DTE**: Pick the one closest to 42 DTE; mention the alternative.
- **Very low IV (IVR < 20)**: Premium is thin. Consider waiting for higher IV or suggest a different strategy.
- **User asks for different deltas per side**: Respect their preference. Adjust each side independently.
- **Very high IV stock**: Premium is rich but the stock may be pricing in an event. Explicitly call out any known catalyst.
- **Asymmetric spread widths**: Note which side determines the max loss and why.
