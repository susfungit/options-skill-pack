---
name: bear-call-spread-selector
description: >
  Identifies the optimal strikes for a bear call spread (sell call + buy call) for a given stock.
  Use this skill whenever the user wants to: find the right call options to sell and buy for bearish income,
  screen for a specific delta short call, build a bearish credit spread, set up a defined-risk bearish trade,
  or asks about "which call should I sell/buy", "find me a call spread", "bear call spread on [stock]",
  "sell a 20-delta call", or any variant of selecting option legs for a call credit spread. Also trigger
  when the user provides a ticker and mentions selling calls with upside protection or a bearish outlook.
  Always use this skill — don't attempt option strike selection without it.
---

# Bear Call Spread Selector Skill

Given a stock ticker and trade parameters, identify the optimal short call (to sell) and long call
(to buy) for a bear call spread, then present a complete trade summary with risk/reward metrics.

---

## Step 1 — Gather inputs

Collect the following. Ask for anything missing:

| Parameter | Default if omitted |
|---|---|
| Ticker symbol | Required — ask |
| Expiry preference | ~6 weeks out (look for 35–45 DTE) |
| Short call delta target | 0.20 (20Δ) |
| Spread width % | 10 (long call placed 10% above short strike) |
| Number of contracts | 1 (for display; scales linearly) |

---

## Step 2 — Fetch live option chain data

**Primary method: run the yfinance fetcher script.**

The skill ships with `fetch_bear_call.py` in the same directory as this SKILL.md file.
Run it via Bash before doing any web searches:

```bash
python3 /path/to/fetch_bear_call.py [TICKER] [TARGET_DELTA] [DTE_MIN] [DTE_MAX] [SPREAD_WIDTH]
```

Substitute the actual absolute path to `fetch_bear_call.py` — it lives alongside this SKILL.md file.

The script returns JSON with all fields pre-calculated:
- `price`, `expiry`, `dte`
- `short_call`: `strike`, `mid`, `bid`, `ask`, `delta`, `iv`
- `long_call`: `strike`, `mid`, `bid`, `ask`
- `net_credit`, `spread_width`, `max_profit`, `max_loss`, `breakeven`, `return_on_risk_pct`, `prob_profit_pct`

**If the script errors**: fall back to web search + Black-Scholes (Step 3).

### 2b. Supplemental data via web search (always run in parallel)

Search 1: `[TICKER] stock price earnings date dividend 2025 2026`
Extract: upcoming earnings date, ex-dividend date, recent price trend, 52-week range

Search 2: `[TICKER] IV rank implied volatility rank options`
Extract: IV Rank (IVR) or IV Percentile
- IVR > 50 → elevated IV → selling premium is more attractive → POSITIVE signal
- IVR < 30 → low IV → premium is thin → CAUTION

---

## Step 3 — Fallback: estimate strikes when live data unavailable

Use this **only if** the fetch_bear_call.py script fails or errors.

```
Short call strike ≈ stock_price × (1 + otm_pct)
  where otm_pct for 20Δ ≈ 0.85 × IV × sqrt(DTE/365)

Long call strike  = round(short_strike × (1 + spread_width_pct/100), nearest listed strike)
Spread width      = long_strike − short_strike

Net credit estimate (mid):
  short_call_mid ≈ stock_price × 0.0065 × sqrt(DTE/30)
  long_call_mid  ≈ short_call_mid × 0.35
  net_credit     = short_call_mid − long_call_mid
```

Always label estimated values clearly: `(estimated — verify on your broker's chain)`.

---

## Step 4 — Risk / Reward calculations

```
max_profit     = net_credit × 100            (per contract)
max_loss       = (spread_width − net_credit) × 100
breakeven      = short_strike + net_credit
pop            ≈ 1 − short_delta             (probability of profit at expiry)
return_on_risk = net_credit / (spread_width − net_credit) × 100
```

---

## Step 5 — Risk signal checklist

- [ ] **Earnings within expiry window?** → ⚠️ IV spike/crush risk
- [ ] **IV Rank < 25?** → ⚠️ thin premium; consider waiting
- [ ] **Stock in an uptrend?** → ⚠️ directional risk; consider moving short strike further OTM (15Δ)
- [ ] **Ex-dividend date within expiry?** → note it; early assignment risk on short ITM calls
- [ ] **Spread width < $3?** → ⚠️ commissions eat into profit

---

## Step 6 — Output format

```
╔══════════════════════════════════════════╗
║  BEAR CALL SPREAD — [TICKER]             ║
║  Expiry: [DATE]  ·  DTE: [N] days        ║
╠══════════════════════════════════════════╣
║  SELL  [SHORT_STRIKE] Call  @ $[price]   ║
║  BUY   [LONG_STRIKE]  Call  @ $[price]   ║
║  Net credit:  $[credit]  per share       ║
╠══════════════════════════════════════════╣
║  Max profit:  $[N]  per contract         ║
║  Max loss:    $[N]  per contract         ║
║  Breakeven:   $[price]                   ║
║  Prob. profit: ~[N]%                     ║
║  Return/risk:  [N]%                      ║
╚══════════════════════════════════════════╝
```

After the trade card, write 3–5 sentences covering:
1. Why this strike was chosen (delta, OTM%, IV context)
2. What needs to happen for max profit (stock stays below short strike)
3. Key risk (what breaks the trade — strong rally)
4. Any flags from the risk checklist

---

## Step 7 — Interactive P&L widget (optional)

After the prose summary, offer to render an interactive P&L chart.

---

## Edge cases

- **Can't find option chain**: Use estimation from Step 3 and clearly label.
- **Multiple expiries close to target DTE**: Pick the one closest to 42 DTE.
- **Very low-priced stock (<$20)**: Flag thin spread and commissions risk.
- **Very high IV (IVR > 80)**: Premium is rich but often event-driven. Call it out.
- **User asks for a different delta**: Respect their preference.
