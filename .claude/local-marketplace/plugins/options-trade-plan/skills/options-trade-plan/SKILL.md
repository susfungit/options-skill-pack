---
name: options-trade-plan
description: >
  Generates a professional, data-driven options spread trade plan for any ticker and any timeframe,
  delivered as a self-contained editorial-style HTML page. Use this skill whenever the user asks for:
  a weekly or monthly options trade plan on a ticker; a spread strategy analysis (iron condor, bull put,
  bear call, diagonal, calendar) for any expiry; an options income strategy for a specific stock and
  timeframe; anything like "analyze [TICKER] for [expiry] options"; "give me a trade plan for [TICKER]
  [weeklies/monthlies/45 DTE]"; "what spread should I sell on [TICKER] this week/month"; or "options
  strategy for [TICKER]" — even when the timeframe is vague or missing. Trigger aggressively on any
  request that combines a ticker with options, spreads, credit, premium selling, or income — even if
  the user does not explicitly ask for a "plan" or "HTML" output. This skill should not be skipped in
  favour of ad-hoc analysis; the output is a full research document, not a text answer.
---

# Options Trade Plan Skill

Produce a **professional, data-driven options spread trade plan** for any ticker and timeframe.
The output is a self-contained HTML page the trader can save and share. The quality bar is
"sell-side research note," not a generic explainer.

This skill is designed for experienced options traders. Skip the introductions. Get straight
to data-backed, specific setups.

---

## Inputs

| Input | Default if missing |
|---|---|
| Ticker | **Required — ask** |
| Expiry / timeframe (`weekly`, `monthly`, `45 DTE`, a date, "end of month") | Nearest weekly Friday; state the assumption |
| Portfolio size | Show $250k / $500k / $1M in the sizing table |
| Directional bias | Treat as neutral |
| Risk tolerance | Conservative defaults (see Step 5) |

---

## Step 0 — Resolve the expiry before anything else

Convert the user's timeframe into a concrete expiry date and a DTE number *before* doing any
analysis. The resolver script (Step 1) handles this, but know the rules so you can explain them:

- "Weekly" or "next Friday" → nearest listed Friday ≥ tomorrow
- "Monthly" → 3rd Friday of the nearest upcoming month
- "N DTE" → nearest listed expiry at or beyond N days
- "End of month" → last trading day of the current month
- Explicit date → use it; if not listed, pick the nearest listed expiry
- No timeframe → default to nearest weekly Friday and say so at the top of the output

State the resolved expiry and DTE explicitly at the top of the output.

---

## Step 1 — Run the data script

Before writing any output, run `fetch_trade_plan_data.py` (lives alongside this SKILL.md):

```bash
python3 /path/to/fetch_trade_plan_data.py TICKER \
  [--expiry YYYY-MM-DD] [--dte N] [--timeframe weekly|monthly|eom]
```

Substitute the actual absolute path. The script returns a single JSON object with **everything
Step 2 would otherwise have you calculate by hand**:

- `price`, `prev_close`, `change_pct`, `ohlc_last_session`, `ohlc_prev_session`
- `sma_50`, `sma_200`
- `atm_iv_pct`, `hv_30d_pct`, `iv_hv_ratio`, `iv_hv_verdict`
- `iv_rank_pct_proxy`, `iv_percentile_pct_proxy` (HV-history proxy — label as *proxy* in the output)
- `expected_move` (`dollar`, `pct`, `low`, `high`) using the formula `price × IV × sqrt(DTE/365)`
- `pivot` (`P`, `R1`, `R2`, `S1`, `S2`) derived from the last **completed** session's OHLC
- `expiry`, `dte`, `expiry_resolution` (the human-readable explanation of how it was chosen)
- `earnings` (`date`, `timing`, `within_expiry_window`, `days_from_expiry`) or `null`
- `strike_guidance` — bucket, target short delta, recommended width, LEAPS warning
- `trades.bull_put`, `trades.bear_call`, `trades.iron_condor` — each with strikes, mids,
  deltas, credit, max P/L, breakeven, prob_profit_pct
- `chain_summary` — `max_pain`, `put_oi_wall`, `call_oi_wall`, `put_call_oi_ratio`
- `warnings` — any earnings-in-window, low-IV, LEAPS, or thin-chain flags

**If the script errors:** still produce a plan. Use web search + estimation (Step 3) and
clearly label all model-derived values as `(estimated)`.

### Parallel web searches (always run while the script executes)

Dispatch these searches in parallel — they fill in the qualitative and catalyst context the
script cannot provide:

1. `[TICKER] recent earnings report beat miss guidance [CURRENT_YEAR]`
2. `[TICKER] analyst rating change price target [CURRENT_YEAR]`
3. `[TICKER] news catalyst [CURRENT_MONTH] [CURRENT_YEAR]`
4. VIX level and sector/industry ETF move — e.g. `VIX today` and `XLK today` for a tech name
5. For DTE > 30 days: `[TICKER] ex-dividend date [NEXT_FEW_MONTHS]` and any product event, conference, or FDA/reg catalyst within the window

The goal of these searches is atmospheric context for the executive summary and the "Market
Context & Catalysts" section — not to recompute the numerical data.

---

## Step 2 — Verdict on the volatility regime

Using `iv_hv_ratio`:

| Ratio | Verdict | Implication |
|---|---|---|
| > 1.20 | IV rich vs. realized | Selling premium is attractive |
| 0.85 – 1.20 | Fair | Neutral stance; no edge from IV |
| < 0.85 | IV cheap vs. realized | Thin premium — avoid selling vol |

State the verdict explicitly in the Executive Summary.

---

## Step 3 — DTE → strategy eligibility

The script's `strike_guidance.dte_bucket` already classifies this; mirror it in the output:

| DTE | Short-strike delta | Width | What's eligible |
|---|---|---|---|
| 0 – 7 (weekly) | ~0.15 | $5 | Defined-risk spreads only; gamma risk too high for naked |
| 8 – 21 (bi-weekly) | ~0.18 | $5 – $10 | Defined-risk spreads only |
| 22 – 45 (monthly) | 0.20 – 0.25 | $10 | Spreads; naked strangle if IV rank > 50 and account approved |
| 46 – 90 (extended) | 0.25 – 0.30 | $10 – $15 | Spreads + diagonals + calendars |
| > 90 (LEAPS zone) | — | — | **Flag that standard short-premium is suboptimal** — recommend diagonal/calendar and explain why |

**Weekly management cutoff:** close Thursday if the short strike is threatened, regardless of
profit.

---

## Step 4 — Earnings check (mandatory)

Read `earnings.within_expiry_window` and `earnings.days_from_expiry`. If earnings falls inside
the window:

- Flag prominently in the Executive Summary
- Either widen the short strikes by **1.5 × the earnings expected move** OR recommend avoiding
  outright premium selling and suggest an alternative (long strangle, calendar, iron fly around
  the event) — state explicitly which you're doing
- Never silently ignore earnings inside the window

If earnings falls within ~7 days *after* expiry, note that pre-earnings IV is likely inflating
premium and briefly call it out.

---

## Step 5 — Three conditional trade structures

The three trades are **scenario-conditional**, not a buffet. The decision flowchart in
Step 6 picks the one to use.

### Scenario A — Bullish / stable tape → bull put spread
Use `trades.bull_put` from the script. **Justification must cite the specific support level**
that makes the short strike defensible — pivot S1, 50-day SMA, prior close volume node, or
put-OI wall. If the short strike is not near any of these, say so and note it's a weaker setup.

### Scenario B — Neutral / range-bound tape → iron condor
Use `trades.iron_condor`. Justify both the put side (support) and call side (resistance)
levels, citing specific pivots / SMAs / OI walls.

### Scenario C — Bearish / rejection tape → bear call spread
Use `trades.bear_call`. Justify the short strike with a resistance level — pivot R1, call-OI
wall, swing high, or declining SMA.

### For each trade, produce every one of the following:

1. Exact strikes and expiry date
2. Each leg: BUY / SELL, strike, estimated premium — **labelled "model estimate (Black-Scholes from mid)"**
3. Net credit (from script); include both mid and natural where available
4. Max profit per contract (dollars *and* per share)
5. Max loss per contract
6. Breakeven price(s)
7. Short-strike delta at entry
8. Estimated probability of profit
9. **Specific, price-action-conditional entry trigger.** Not "enter if bullish." Good examples:
   - *"Enter only if [TICKER] holds above [$S1] after the first 30 minutes of Monday's session."*
   - *"Enter only on a confirmed rejection at [$R1] — a failed breakout candle or re-break below the daily pivot."*
10. Stop/adjustment rule — specific price OR delta level:
    - *"Close if short-put delta reaches 0.30."*
    - *"Close if [TICKER] closes below [$S2]."*
11. Management timeline scaled to DTE:
    - **DTE ≤ 7:** take 50% profit by day 3; close Thursday if near short strike
    - **DTE 8 – 21:** take 50% profit at 50% of time elapsed; close at 7 DTE remaining
    - **DTE 22 – 45:** take 50% profit or close at 21 DTE remaining, whichever first
    - **DTE 46 – 90:** take 50% profit; close at 30 DTE remaining
    - **All:** hard stop at 2× credit received

---

## Step 6 — Decision flowchart

Build the flowchart using the **actual calculated levels** — do not use placeholders like "$X."

```
Start: [TICKER] opens on [first trading day]
  │
  ├─ Is [TICKER] above [$S1] after the first 30–60 minutes?
  │    ├─ YES → Is there a rejection below [$R1 / $R2]?
  │    │         ├─ NO  → Scenario A — bull put spread
  │    │         └─ YES → Scenario C — bear call spread
  │    └─ NO  → Is price inside [$S1]–[$R1] and non-trending?
  │              ├─ YES → Scenario B — iron condor
  │              └─ NO  → No trade. Wait for next session/week.
```

Render this as HTML/CSS in the sidebar — never as an image.

---

## Step 7 — Position sizing

```
contracts = floor( (portfolio × risk_budget%) / max_loss_per_contract )
```

Conservative risk budgets:

| Structure | Budget |
|---|---|
| One-sided spread (bull put or bear call) | 0.35% of portfolio |
| Iron condor | 0.25% |
| Naked strangle (only when eligible) | 0.20% |

Always produce a sizing table with at least three portfolio sizes — default to
$250k, $500k, $1M. If the user gave a number, anchor it to that and keep one or two others for
comparison. Under the table, add:

> Run ONE core trade at a time at full size. Do not layer all three simultaneously.

---

## Step 8 — Produce the HTML output

**Use the template.** Read `assets/template.html` (ships alongside this SKILL.md). It is a
self-contained, Chart.js-powered, editorial-style document designed to the exact specification
below. Fill in the placeholder tokens with real data and write the result to a new file.

### Placeholder tokens in the template

The template contains `{{TOKEN}}` placeholders. Do a straightforward string-replace to populate
them — no templating engine needed. Key tokens include:

`{{TICKER}}`, `{{EXPIRY}}`, `{{DTE}}`, `{{PUB_DATE}}`, `{{SPOT}}`, `{{CHG_PCT}}`, `{{IV}}`,
`{{HV}}`, `{{IV_HV_RATIO}}`, `{{MAX_PAIN}}`, `{{EARNINGS_LINE}}`, `{{EXEC_SUMMARY_HTML}}`,
`{{CONTEXT_HTML}}`, `{{LEVELS_ROWS_HTML}}`, `{{EARNINGS_HTML}}`,
`{{TRADE_SUMMARY_ROWS_HTML}}`, `{{BULL_PUT_CARD_HTML}}`, `{{CONDOR_CARD_HTML}}`,
`{{BEAR_CALL_CARD_HTML}}`, `{{FLOWCHART_HTML}}`, `{{IV_VERDICT}}`, `{{POSITIONING_HTML}}`,
`{{SIZING_ROWS_HTML}}`, `{{SOURCES_HTML}}`, `{{CHART_CONFIG_JSON}}`.

The template has detailed comments indicating what each section expects.

### Required design traits (already baked into the template — do not override)

- Light cream background (`#faf9f6`)
- Serif headlines (Playfair Display), sans-serif body (IBM Plex Sans), mono for numbers (IBM Plex Mono)
- Two-column layout: main analysis left (~65%), sidebar right (~35%)
- Color-coded trade cards: green (bull put), blue (iron condor), red (bear call)
- Chart.js P&L diagram with all three strategies overlaid and a legend matching the card colors

### Chart.js P&L data

Produce `CHART_CONFIG_JSON` as an object with three datasets. The X-axis runs from ~15% below
spot to ~15% above spot in 0.5-dollar increments; at each x, compute P&L at expiry:

- **Bull put spread:** `pnl(x) = credit` if `x ≥ short_put_strike`; linearly declines to `credit - width` at/below `long_put_strike`. Multiply all values by 100 for per-contract dollars.
- **Iron condor:** sum of bull put P&L and bear call P&L using the IC credit.
- **Bear call spread:** `pnl(x) = credit` if `x ≤ short_call_strike`; linearly declines to `credit - width` at/above `long_call_strike`.

Datasets have `borderColor` set to `#2d8a4b` (bull), `#1e5fa8` (condor, dashed via `borderDash`), `#b2342c` (bear, dotted via `borderDash`).

### Required section order

1. Masthead (ticker, strategy type, expiry, DTE, publication date)
2. Data band (spot, IV, HV, IV/HV ratio, max pain, DTE, earnings)
3. Executive Summary
4. Market Context & Catalysts
5. Technical Structure & Positioning (levels table)
6. Earnings & Catalyst Check (always present, even if clean)
7. Trade Setups (summary table + three detailed cards)
8. P&L Comparison Chart
9. Risk Management & Sizing (sizing table + one-core-trade note)
10. Data Sources & Caveats (list every data point with source + timestamp)
11. Footer disclaimer

### Where to write the file

Unless the user asks otherwise, write to a `trade-plans/` subdirectory of the current working
directory as `trade-plans/trade_plan_[TICKER]_[EXPIRY].html`. Create the directory if it does
not already exist (`mkdir -p trade-plans`). Tell the user the full path at the end.

---

## Quality checklist — run through before finishing

- [ ] Script was executed and the JSON parsed before any HTML was written
- [ ] Expiry date and DTE are explicitly stated at the top
- [ ] IV/HV ratio is shown with a one-line verdict
- [ ] Expected move is shown as ±$ and ±%, derived from the formula
- [ ] Pivot levels come from the last completed session's OHLC (shown in a table)
- [ ] Earnings timing vs. expiry is addressed explicitly (in-window OR clean, with days noted)
- [ ] Each trade has a specific, price-action-conditional entry trigger
- [ ] Each trade has a specific stop level (price or delta)
- [ ] Management timeline matches the DTE bucket
- [ ] All option premiums are labelled as model estimates
- [ ] Data sources section lists every external fact with its timestamp
- [ ] Output is a complete, self-contained HTML file — opens in a browser with no missing assets
- [ ] Chart.js P&L overlay has all three strategies, color-matched to cards
- [ ] Sizing table covers at least three portfolio sizes
- [ ] Decision flowchart uses the actual calculated price levels, not placeholders
- [ ] For DTE > 90, the plan explicitly flags that standard short-premium is suboptimal and recommends a diagonal or calendar

---

## Edge cases

- **Script errors or yfinance is offline:** Fall back to web-search estimation. Label every
  model value as `(estimated)`. Still produce the full HTML. Never refuse.
- **Earnings in window:** Widen shorts 1.5× earnings EM OR recommend long vol / iron fly. State
  which choice you made and why.
- **Very low IV rank (< 25):** Warn that premium is thin. Still produce the plan, but note the
  user may want to wait for IV expansion.
- **LEAPS zone (> 90 DTE):** Recommend diagonal/calendar. Still include the spread variants in
  the output, but clearly label them as suboptimal for the DTE.
- **Thin option chain / no strikes near target delta:** Use the nearest available strike. Note
  in the risk section that liquidity is poor.
- **No directional bias given:** Treat as neutral. The iron condor card gets the primary
  recommendation slot; the decision flowchart still shows the three scenarios.
