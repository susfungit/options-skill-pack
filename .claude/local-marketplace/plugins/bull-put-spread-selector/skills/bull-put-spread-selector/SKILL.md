---
name: bull-put-spread-selector
description: >
  Identifies the optimal strikes for a bull put spread (sell put + buy put) for a given stock.
  Use this skill whenever the user wants to: find the right put options to sell and buy for income,
  screen for a specific delta short put, build a credit spread, set up a defined-risk options trade,
  or asks about "which put should I sell/buy", "find me a put spread", "what strikes for my spread",
  "sell a 20-delta put", "bull put spread on [stock]", or any variant of selecting option legs for
  a put credit spread. Also trigger when the user provides a ticker and mentions selling puts with
  downside protection. Always use this skill — don't attempt option strike selection without it.
---

# Bull Put Spread Selector Skill

Given a stock ticker and trade parameters, identify the optimal short put (to sell) and long put
(to buy) for a bull put spread, then present a complete trade summary with risk/reward metrics.

---

## Step 1 — Gather inputs

Collect the following. Ask for anything missing:

| Parameter | Default if omitted |
|---|---|
| Ticker symbol | Required — ask |
| Expiry preference | ~6 weeks out (look for 35–45 DTE) |
| Short put delta target | 0.20 (20Δ) |
| Spread width method | Long put = 10% below short strike |
| Number of contracts | 1 (for display; scales linearly) |

---

## Step 2 — Fetch live option chain data

**Primary method: run the yfinance fetcher script.**

The skill ships with `fetch_chain.py` in the same directory as this SKILL.md file.
Run it via Bash before doing any web searches:

```bash
python3 /path/to/fetch_chain.py [TICKER] [TARGET_DELTA] [DTE_MIN] [DTE_MAX]
```

Substitute the actual absolute path to `fetch_chain.py` — it lives alongside this SKILL.md file.
Example for default parameters:
```bash
python3 "$(dirname "$0")/fetch_chain.py" AAPL 0.20 35 45
```

Or if the path is known (resolve it from the skill directory):
```bash
SKILL_DIR="/Users/sushant/python/options-skill-pack/.claude/local-marketplace/plugins/bull-put-spread-selector/skills/bull-put-spread-selector"
python3 "$SKILL_DIR/fetch_chain.py" [TICKER] [TARGET_DELTA] 35 45
```

The script returns JSON with all fields pre-calculated:
- `price`, `expiry`, `dte`
- `short_put`: `strike`, `mid`, `bid`, `ask`, `delta`, `iv`
- `long_put`: `strike`, `mid`, `bid`, `ask`
- `net_credit`, `spread_width`, `max_profit`, `max_loss`, `breakeven`, `return_on_risk_pct`, `prob_profit_pct`
- `delta_source`: `"live"` | `"estimated_bs"` | `"estimated_otm_pct"` — indicates data quality

**If `delta_source` is `"live"`**: use all values directly — no estimation needed.
**If `delta_source` is `"estimated_bs"` or `"estimated_otm_pct"`**: label prices as `(est.)` in the trade card.
**If the script errors**: fall back to web search + Black-Scholes (Step 3).

### 2b. Supplemental data via web search (always run in parallel)

Even when live chain data succeeds, use web search for context the script cannot provide:

Search 1: `[TICKER] stock price earnings date dividend 2025 2026`
Extract: upcoming earnings date, ex-dividend date, recent price trend, 52-week range

Search 2: `[TICKER] IV rank implied volatility rank options`
Extract: IV Rank (IVR) or IV Percentile — the script gives current IV% from the chain but not IVR.
- IVR > 50 → elevated IV → selling premium is more attractive → POSITIVE signal
- IVR < 30 → low IV → premium is thin → ⚠️ CAUTION

---

## Step 3 — Fallback: estimate strikes when live data unavailable

Use this **only if** the fetch_chain.py script fails or errors.

```
Short put strike  ≈ stock_price × (1 - otm_pct)
  where otm_pct for 20Δ ≈ 0.85 × IV × sqrt(DTE/365)
  (e.g. stock=$100, IV=30%, DTE=42 → otm_pct ≈ 0.085 → strike ≈ $91.50 → round to nearest $0.50)
  Note: this formula breaks down for very high IV (>100%) — use direct Black-Scholes in that case.

Long put strike   = round(short_strike × 0.90, nearest listed strike)
Spread width      = short_strike − long_strike

Net credit estimate (mid):
  short_put_mid ≈ stock_price × 0.0065 × sqrt(DTE/30)   (rough for 20Δ)
  long_put_mid  ≈ short_put_mid × 0.35                   (10% lower strike)
  net_credit    = short_put_mid − long_put_mid
```

Always label estimated values clearly: `(estimated — verify on your broker's chain)`.

---

## Step 4 — Risk / Reward calculations

Once strikes and credit are known:

```
max_profit     = net_credit × 100            (per contract)
max_loss       = (spread_width − net_credit) × 100
breakeven      = short_strike − net_credit
pop            ≈ 1 − short_delta             (probability of profit at expiry ≈ 80% for 20Δ)
return_on_risk = net_credit / (spread_width − net_credit) × 100
```

---

## Step 5 — Risk signal checklist

Run through these and flag any ⚠️:

- [ ] **Earnings within expiry window?** → if YES ⚠️ IV will spike before and crush after; spread risk spikes
- [ ] **IV Rank < 25?** → ⚠️ thin premium; consider waiting or widening the spread
- [ ] **Stock in a downtrend?** → ⚠️ directional risk; consider moving short strike further OTM (15Δ)
- [ ] **Ex-dividend date within expiry?** → note it; early assignment risk on short puts near dividend
- [ ] **Spread width < $3?** → ⚠️ commissions eat into profit; consider widening

---

## Step 6 — Output format

Present a clean, structured trade card followed by a prose rationale. Use this layout:

```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — [TICKER]              ║
║  Expiry: [DATE]  ·  DTE: [N] days        ║
╠══════════════════════════════════════════╣
║  SELL  [SHORT_STRIKE] Put   @ $[price]   ║
║  BUY   [LONG_STRIKE]  Put   @ $[price]   ║
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
2. What needs to happen for max profit (stock stays above short strike)
3. Key risk (what breaks the trade)
4. Any flags from the risk checklist

---

## Step 7 — Interactive P&L widget (optional but recommended)

After the prose summary, offer to render an interactive P&L chart. Say:

> "Want me to plot the full P&L curve for this spread so you can visualize the risk zones?"

If the user says yes (or the context already involves a chart from earlier in the conversation),
build the widget using Chart.js showing the expiry P&L curve with the three key price levels
(long strike, short strike, breakeven) annotated as vertical dashed lines.

---

## Edge cases

- **Can't find option chain**: Use estimation from Step 3 and clearly label all values as estimated.
- **Multiple expiries close to target DTE**: Pick the one closest to 42 DTE; mention the alternative.
- **Strike doesn't land on a round number**: Round to the nearest listed strike (typically $0.50 or $1 increments for most stocks, $5 for high-priced stocks).
- **Very low-priced stock (<$20)**: Spread width of 10% may be only $1–2, making commissions punishing. Flag this and suggest considering a wider spread or different strategy.
- **Very high IV (IVR > 80)**: Premium is rich but often driven by a known event. Explicitly call out the event if one exists.
- **User asks for a different delta**: Respect their preference; adjust OTM% approximation accordingly (10Δ ≈ 12–18% OTM, 30Δ ≈ 5–8% OTM for typical IV/DTE).
