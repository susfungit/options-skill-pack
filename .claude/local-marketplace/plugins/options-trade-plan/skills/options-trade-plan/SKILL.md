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

Produce a professional, data-driven options spread trade plan for any ticker and timeframe.
Output is a self-contained HTML page assembled by `render_trade_plan.py`.

**Your job is narrow:** write 13 short prose blocks as JSON. Python pre-renders all numeric
HTML (cards, tables, charts, sizing rows) and stitches the final page. You never read or
write the HTML template.

---

## Inputs

| Input | Default if missing |
|---|---|
| Ticker | **Required — ask** |
| Expiry / timeframe (`weekly`, `monthly`, `45 DTE`, a date, "end of month") | Nearest weekly Friday |
| Portfolio size | Sizing table always shows $250k / $500k / $1M |
| Directional bias | Treat as neutral |

---

## Step 1 — Run the data script

```bash
mkdir -p trade-plans/.tmp
python3 /path/to/fetch_trade_plan_data.py TICKER \
  [--expiry YYYY-MM-DD] [--dte N] [--timeframe weekly|monthly|eom] \
  --fragments-out trade-plans/.tmp/TICKER_fragments.json \
  > trade-plans/.tmp/TICKER_data.json
```

The redirected stdout file is a single JSON object with `data.*` fields you'll cite in prose:
`price`, `atm_iv_pct`, `hv_30d_pct`, `iv_hv_ratio`, `iv_hv_verdict`, `expected_move`,
`pivot`, `expiry`, `dte`, `earnings`, `strike_guidance`, `trades.{bull_put, iron_condor,
bear_call}`, `chain_summary`, `warnings`, `skip_dividend_search`.

Bulky pre-rendered HTML fragments are written to the `--fragments-out` file — do not read
that file; the renderer consumes it directly.

**If the script errors:** still produce a plan. Use web search + estimation, label every
model value `(estimated)`, and skip the renderer step (write minimal HTML by hand into
`trade-plans/trade_plan_TICKER_EXPIRY.html`).

### Web searches (run in parallel as a single tool-use turn)

Before searching, check `trade-plans/.tmp/search_cache/TICKER_TODAY.json` (where
`TODAY` is `YYYY-MM-DD` UTC). If the file exists, read it and skip the searches.
Otherwise dispatch these in **one** tool-use turn:

1. `[TICKER] recent earnings report beat miss guidance [CURRENT_YEAR]`
2. `[TICKER] analyst rating change price target [CURRENT_YEAR]`
3. `[TICKER] news catalyst [CURRENT_MONTH] [CURRENT_YEAR]`

If `data.skip_dividend_search` is **false**, also dispatch (in the same turn):

4. `[TICKER] ex-dividend date [NEXT_FEW_MONTHS] catalyst event conference`

After the searches return, write a short JSON summary of the findings to
`trade-plans/.tmp/search_cache/TICKER_TODAY.json` so future runs the same day skip the
searches. Use the file path the cache check would have read.

These results feed your `context_html` and `sources_html` prose — they do not recompute
numbers.

---

## Step 2 — Read the data and identify the angle

Spend most of your reasoning here. Identify:

- IV/HV verdict (`data.iv_hv_verdict`) — premium selling attractive or thin?
- Earnings within window (`data.earnings.within_expiry_window`) — flag prominently.
- DTE bucket (`data.strike_guidance.dte_bucket`) — drives entry/management cadence.
- Warnings (`data.warnings`) — earnings, low IV, LEAPS, thin chain.
- Each short strike vs. the relevant level:
  - bull put short put vs. `pivot.S1`, `sma_50`, `chain_summary.put_oi_wall`
  - bear call short call vs. `pivot.R1`, `chain_summary.call_oi_wall`, `sma_50/200`
  - iron condor: both sides

Cite these specific levels by name and number in the per-trade prose.

---

## Step 3 — Earnings handling

If `data.earnings.within_expiry_window` is true:
- Flag in `exec_summary_html` and the affected card's rationale prose
- State explicitly that you are either (a) accepting the risk because shorts are 1.5× the
  earnings expected move beyond support, or (b) recommending the trader avoid this expiry
  and wait for post-earnings IV crush
- Never silently ignore it

If earnings falls within ~7 days *after* expiry, note in `context_html` that pre-earnings
IV is likely inflating premium.

---

## Step 4 — Write the prose JSON and render

Write a single file `trade-plans/.tmp/TICKER_prose.json` with these 13 keys (all string
values, all valid HTML fragments):

| Key | What to write |
|---|---|
| `exec_summary_html` | 2–4 `<p>` paragraphs. State IV verdict, directional read, recommended scenario, earnings status. First `<p>` should have class `lead` for the drop-cap. |
| `context_html` | Catalyst summary from web searches: recent earnings result, analyst moves, news/events. `<p>` blocks or `<ul><li>` bullets. Cite sources inline as `(source: …)`. |
| `earnings_html` | If clean: a single `<div class="earnings-callout clean">` saying so, with the days-after note if applicable. If in-window: a `<div class="earnings-callout">` with the date, EM widening logic, and your recommended action. |
| `sources_html` | `<li>` items: data script (yfinance, timestamp from `data.as_of`), each web search query + finding, and any other external fact. |
| `bull_put_rationale` | One `<p>`, 1–3 sentences. Why this short strike is defensible — cite the specific level (pivot S1, SMA 50, OI wall) and how far the short sits beyond it. |
| `bull_put_entry_trigger` | One `<p>`. Specific, price-action-conditional. *"Enter only if AAPL holds above $278.50 (S1) for the first 30 minutes of Monday's session."* Not "enter if bullish." |
| `bull_put_stop_rule` | One `<p>`. Specific price OR delta level. *"Close if short-put delta reaches 0.30, or if AAPL closes below $275 (S2)."* |
| `iron_condor_rationale` | Same shape as bull_put_rationale, citing both sides. |
| `iron_condor_entry_trigger` | Same shape. |
| `iron_condor_stop_rule` | Same shape. |
| `bear_call_rationale` | Same shape as bull_put_rationale, for the call side. |
| `bear_call_entry_trigger` | Same shape. |
| `bear_call_stop_rule` | Same shape. |

Then call the renderer:

```bash
python3 /path/to/render_trade_plan.py \
  --data trade-plans/.tmp/TICKER_data.json \
  --fragments trade-plans/.tmp/TICKER_fragments.json \
  --prose trade-plans/.tmp/TICKER_prose.json \
  --out trade-plans
```

The renderer prints the output path. Tell the user that path. It validates that every
`{{TOKEN}}` and `MODEL_SLOT` is replaced; if a prose key is missing or malformed, the
renderer fails loudly and the user sees the error.

---

## Quality checklist

- [ ] Data script ran and the JSON parsed before any prose was written
- [ ] Executive summary explicitly states IV/HV verdict, directional read, recommended scenario, earnings status
- [ ] Earnings is addressed (in-window or clean, with days noted)
- [ ] Each rationale cites a specific level (pivot/SMA/OI wall) by name and number
- [ ] Each entry trigger references a specific price + time-of-day condition
- [ ] Sources lists data script + every web search with timestamp
- [ ] For DTE > 90, executive summary flags that standard short-premium is suboptimal
- [ ] Renderer exited 0 and printed the output HTML path

---

## Edge cases

- **Script errors / yfinance offline:** skip the renderer; produce minimal HTML by hand and label every value `(estimated)`.
- **Very low IV rank (`data.iv_rank_pct_proxy < 25`):** call out in `exec_summary_html` that premium is thin.
- **LEAPS zone (`dte > 90`):** `exec_summary_html` recommends diagonal/calendar; spread cards stay but are labelled suboptimal.
- **Thin chain / strike not near target delta:** the script returns the nearest available; flag liquidity in the rationale.
- **No directional bias given:** treat as neutral; iron condor is the primary pick.
