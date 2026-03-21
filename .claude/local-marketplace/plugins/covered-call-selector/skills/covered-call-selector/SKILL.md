---
name: covered-call-selector
description: >
  Identifies the optimal call strike to sell for a covered call on a given stock.
  Use this skill whenever the user wants to: sell a covered call, write a call against
  shares they own, generate income from a stock position, find the right call to sell,
  or asks about "covered call on [stock]", "sell calls against my shares", "what call
  should I sell on [stock]", "write a call on [stock]", "yield on my [stock] shares",
  "income from my shares", "sell premium on [stock] I own", or any variant of selecting
  a call option to sell against an existing stock position. Also trigger when the user
  mentions owning shares and wanting to generate income or reduce cost basis.
  Always use this skill — don't attempt covered call strike selection without it.
---

# Covered Call Selector

Given a stock the user owns (or plans to own), find the optimal OTM call to sell
for income — balancing premium yield against the probability of being called away.

---

## Step 1 — Gather inputs

You need the ticker. Ask for it if missing. Everything else has sensible defaults:

| Input | Default | Example override |
|---|---|---|
| Ticker | *(required)* | AAPL |
| Target delta | 0.30 (~30% chance of assignment) | "15-delta call", "very conservative" |
| DTE range | 30–45 days | "60 days out", "May expiry" |
| Contracts | 1 (= 100 shares) | "3 contracts" |
| Cost basis | *(optional)* | "I bought at $150" |

**Delta guidance for the user:**
- 0.30Δ (default) — balanced: decent premium, ~30% chance of assignment
- 0.20Δ — moderate: less premium, ~20% chance of being called
- 0.10–0.15Δ — conservative: small premium, unlikely to be called, mostly for downside buffer

---

## Step 2 — Fetch live option chain data

Run `fetch_covered_call.py` from the same directory as this SKILL.md:

```bash
python3 /path/to/fetch_covered_call.py TICKER [TARGET_DELTA] [DTE_MIN] [DTE_MAX]
```

Replace with the actual absolute path to `fetch_covered_call.py`. It lives alongside this SKILL.md.

The script returns JSON with:
- `stock_price` — current stock price
- `short_call.strike`, `short_call.mid`, `short_call.delta`, `short_call.iv_pct`
- `premium_per_share`, `premium_per_contract`
- `static_return_pct` — yield if stock stays flat (premium / stock price)
- `annualized_return_pct` — static return annualized
- `downside_protection_pct` — how much stock can drop before net loss
- `called_away_return_pct` — max return if stock rises above strike and shares are called
- `breakeven` — stock price minus premium
- `prob_called_pct` — probability of assignment (≈ delta × 100)

If the script errors, note it and use Step 3.

---

## Step 3 — Fallback estimation (if script fails)

When live data is unavailable:

1. **OTM% approximation**: `otm_pct ≈ 0.85 × IV × sqrt(DTE/365)` — use the same formula as put spreads but for calls
2. **Strike estimate**: `strike = stock_price × (1 + otm_pct)`
3. **Premium estimate**: Use BS model or estimate as ~1–2% of stock price for 30Δ, 30-45 DTE

Flag clearly that these are estimates without live data.

---

## Step 4 — Risk checklist

Before presenting the trade, check and flag these risks. Use a web search for earnings and dividend dates if needed.

| Risk Signal | What to check | Flag if |
|---|---|---|
| Earnings | Does the company report within the expiry window? | Earnings before expiry — IV crush risk, possible gap |
| IV Rank | Is IV high or low relative to the past year? | IV rank < 25 — premium is thin, may not be worth selling |
| Ex-dividend | Is there an ex-dividend date before expiry? | Ex-div before expiry — early assignment risk on ITM calls |
| Trend | Is the stock in a strong uptrend? | Strong uptrend — risk of missing significant upside |

---

## Step 5 — Output the trade card

```
╔══════════════════════════════════════════════════════╗
║  COVERED CALL — [TICKER]                              ║
║  Expiry: [DATE]  ·  DTE: [N] days                    ║
╠══════════════════════════════════════════════════════╣
║  SELL  $[strike] Call   @ $[mid]                      ║
║  per 100 shares owned                                ║
╠══════════════════════════════════════════════════════╣
║  Premium:              $[N] per share ($[N] total)    ║
║  Static return:        [N]%                           ║
║  Annualized return:    [N]%                           ║
║  Downside protection:  [N]%                           ║
║  Called-away return:   [N]%                           ║
║  Breakeven:            $[N]                           ║
║  Prob. of assignment:  ~[N]%                          ║
╚══════════════════════════════════════════════════════╝
```

If the user provided a cost basis, add below the card:

```
Cost basis adjustment:
  Original cost basis:   $[N]
  Effective cost basis:  $[N] (after premium)
  Called-away P&L:       +$[N] per share (+[N]%)
```

Then write 2–4 sentences:
1. Why this strike (delta proximity, premium quality)
2. The trade-off: premium income vs capping upside at the strike
3. Any risk flags from the checklist
4. When this call should be re-evaluated (e.g., "if stock moves above $X, consider buying back the call")

---

## Edge cases

- **Stock is very volatile (IV > 60%)**: Premium is juicy but assignment risk is higher. Note this and suggest the user may want a lower delta (0.15–0.20) to reduce prob of being called.
- **Stock pays a dividend soon**: If the ex-dividend date is before expiry and the call goes ITM, early assignment is possible. Flag this clearly — the user may want to sell the call after the ex-div date.
- **User wants to be called**: Some users sell ATM or slightly ITM covered calls intentionally (to exit the position at a target price + premium). This is fine — adjust the delta target accordingly and note the high assignment probability.
- **User doesn't own the stock yet**: A covered call requires owning shares. If the user is asking hypothetically, note that selling a naked call without shares is a very different (and much riskier) strategy.
- **Multiple contracts**: All per-share and per-contract figures scale linearly. Multiply premium by number of contracts.
