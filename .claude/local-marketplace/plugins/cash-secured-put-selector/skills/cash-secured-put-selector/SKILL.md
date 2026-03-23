---
name: cash-secured-put-selector
description: >
  Identifies the optimal put strike to sell for a cash-secured put on a given stock.
  Use this skill whenever the user wants to: sell a cash-secured put, sell a put backed by cash,
  buy a stock at a discount using options, generate income by selling puts, find the right put to sell,
  or asks about "cash-secured put on [stock]", "sell a put on [stock]", "CSP on [stock]",
  "what put should I sell", "buy [stock] at a discount", "sell a 20-delta put on [stock]",
  "wheel strategy put side", or any variant of selecting a put option to sell backed by cash.
  Also trigger when the user mentions wanting to acquire shares at a lower price using options.
  Always use this skill — don't attempt cash-secured put strike selection without it.
---

# Cash-Secured Put Selector

Given a stock ticker and trade parameters, find the optimal OTM put to sell backed by cash —
balancing premium income against the probability of assignment and the effective purchase price
if assigned.

---

## Step 1 — Gather inputs

You need the ticker. Ask for it if missing. Everything else has sensible defaults:

| Input | Default | Example override |
|---|---|---|
| Ticker | *(required)* | AAPL |
| Target delta | 0.25 (~25% chance of assignment) | "15-delta put", "conservative" |
| DTE range | 30–45 days | "60 days out", "May expiry" |
| Contracts | 1 (= 100 shares) | "3 contracts" |

**Delta guidance for the user:**
- 0.30Δ — aggressive: more premium, ~30% chance of being assigned
- 0.25Δ (default) — balanced: decent premium, ~25% chance of assignment
- 0.15–0.20Δ — conservative: less premium, lower chance of buying shares
- 0.40–0.50Δ — acquisition mode: user *wants* to buy shares at a discount

---

## Step 2 — Fetch live option chain data

Run `fetch_csp.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/fetch_csp.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]
```

Replace with the actual absolute path to `fetch_csp.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `stock_price` — current stock price
- `short_put.strike`, `short_put.mid`, `short_put.delta`, `short_put.iv_pct`
- `premium_per_share`, `premium_per_contract`
- `cash_required` — cash needed to secure the put (strike × 100)
- `return_on_capital_pct` — premium / cash required
- `annualized_return_pct` — return on capital annualized
- `effective_buy_price` — strike minus premium (your cost if assigned)
- `discount_pct` — how far below current price you'd buy if assigned
- `breakeven` — same as effective buy price
- `prob_assigned_pct` — probability of assignment (≈ delta × 100)

If the script errors, note it and use Step 3.

### 2b. Supplemental data via web search (always run in parallel)

Even when live chain data succeeds, use web search for context:

Search 1: `[TICKER] stock price earnings date dividend 2025 2026`
Extract: upcoming earnings date, ex-dividend date, recent price trend, 52-week range

Search 2: `[TICKER] IV rank implied volatility rank options`
Extract: IV Rank (IVR) or IV Percentile
- IVR > 50 → elevated IV → selling premium is more attractive → POSITIVE signal
- IVR < 30 → low IV → premium is thin → CAUTION

---

## Step 3 — Fallback estimation (if script fails)

When live data is unavailable:

1. **OTM% approximation**: `otm_pct ≈ 0.85 × IV × sqrt(DTE/365)` for a ~25Δ put
2. **Strike estimate**: `strike = stock_price × (1 - otm_pct)`
3. **Premium estimate**: Use BS model or estimate as ~1.5% of stock price for 25Δ, 30-45 DTE

Flag clearly that these are estimates without live data.

---

## Step 4 — Risk / Reward calculations

Once strike and premium are known:

```
premium_per_contract = premium × 100
cash_required        = strike × 100
max_profit           = premium × 100                   (keep the premium if stock stays above)
max_loss             = (strike - premium) × 100        (assigned at strike, stock goes to 0)
breakeven            = strike - premium
return_on_capital    = premium / strike × 100
annualized_return    = return_on_capital × (365 / DTE)
effective_buy_price  = strike - premium
discount_pct         = (stock_price - effective_buy_price) / stock_price × 100
prob_profit          ≈ 1 - delta                       (~75% for 25Δ)
```

---

## Step 5 — Risk signal checklist

Run through these and flag any:

- [ ] **Earnings within expiry window?** → IV will spike before and crush after; put price may gap
- [ ] **IV Rank < 25?** → thin premium; consider waiting for higher IV
- [ ] **Stock in a downtrend?** → directional risk; consider lower delta or waiting
- [ ] **Ex-dividend date within expiry?** → note it; early assignment possible on deep ITM puts
- [ ] **Cash requirement vs. portfolio size?** → CSPs tie up capital; flag if cash required is large relative to account

---

## Step 6 — Output the trade card

```
╔══════════════════════════════════════════════════════╗
║  CASH-SECURED PUT — [TICKER]                          ║
║  Expiry: [DATE]  ·  DTE: [N] days                    ║
╠══════════════════════════════════════════════════════╣
║  SELL  $[strike] Put   @ $[mid]                       ║
║  Cash required:  $[N]  per contract                  ║
╠══════════════════════════════════════════════════════╣
║  Premium income:         $[N] per contract            ║
║  Return on capital:      [N]%                         ║
║  Annualized return:      [N]%                         ║
║  Effective buy price:    $[N]  ([N]% below current)   ║
║  Breakeven:              $[N]                         ║
║  Prob. of profit:        ~[N]%                        ║
║  Prob. of assignment:    ~[N]%                        ║
╚══════════════════════════════════════════════════════╝
```

Then write 3–5 sentences covering:
1. Why this strike was chosen (delta, OTM%, IV context)
2. The two outcomes: keep premium if stock stays above strike, or buy shares at effective price if assigned
3. Why assignment isn't necessarily bad — you're buying at a discount with premium cushion
4. Any flags from the risk checklist

---

## Step 7 — Interactive P&L widget (optional but recommended)

After the prose summary, offer to render an interactive P&L chart. Say:

> "Want me to plot the P&L curve for this cash-secured put?"

If yes, build the widget using Chart.js showing the expiry P&L curve with the strike
and breakeven annotated as vertical dashed lines.

---

## Edge cases

- **User wants to be assigned**: Some users sell ATM or ITM puts intentionally to acquire shares. Adjust delta target accordingly and emphasize the effective purchase price.
- **Very low-priced stock (<$20)**: Cash requirement is low but premium may be pennies. Flag if premium < $0.50 per share.
- **Very high-priced stock (>$500)**: Cash requirement is very large ($50,000+ per contract). Flag the capital commitment.
- **High IV (IVR > 80)**: Premium is rich but often driven by a known event. Call out the event and note that assignment risk is also higher.
- **User asks about "the wheel"**: CSP is the first leg of the wheel strategy. If assigned, the next step is to sell a covered call on the acquired shares. Mention this connection.
- **Multiple contracts**: All figures scale linearly. Multiply by number of contracts.
