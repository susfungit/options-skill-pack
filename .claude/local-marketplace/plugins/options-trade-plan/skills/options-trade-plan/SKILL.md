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
The output is a self-contained HTML page the trader can save and share.

The Python data script does all numeric work and pre-renders most of the HTML. Your job is
narrow: write the qualitative narrative blocks, fill three short prose slots per trade card,
and assemble the final HTML.

---

## Inputs

| Input | Default if missing |
|---|---|
| Ticker | **Required — ask** |
| Expiry / timeframe (`weekly`, `monthly`, `45 DTE`, a date, "end of month") | Nearest weekly Friday |
| Portfolio size | Sizing table always shows $250k / $500k / $1M |
| Directional bias | Treat as neutral |

---

## Step 1 — Run the data script (mandatory, first action)

```bash
python3 /path/to/fetch_trade_plan_data.py TICKER \
  [--expiry YYYY-MM-DD] [--dte N] [--timeframe weekly|monthly|eom]
```

The script returns a single JSON object with two top-level surfaces:

- **`data.*`** (numeric/structured) — `price`, `atm_iv_pct`, `hv_30d_pct`, `iv_hv_ratio`,
  `iv_hv_verdict`, `expected_move`, `pivot`, `expiry`, `dte`, `earnings`, `strike_guidance`,
  `trades.{bull_put, iron_condor, bear_call}`, `chain_summary`, `warnings`. Use this when
  you write narrative — cite specific numbers from here.
- **`html.*`** (pre-rendered HTML fragments) — already-built HTML for every structural
  block of the page. **You do not rebuild these.** Paste them into the template verbatim.

**If the script errors:** still produce a plan. Use web search + estimation. Label every
model value as `(estimated)`. Skip the `html.*` fragments and write minimal HTML by hand.

### Web searches (run in parallel as a single tool-use turn)

Dispatch these in **one** tool-use turn (parallel tool calls), not across multiple turns:

1. `[TICKER] recent earnings report beat miss guidance [CURRENT_YEAR]`
2. `[TICKER] analyst rating change price target [CURRENT_YEAR]`
3. `[TICKER] news catalyst [CURRENT_MONTH] [CURRENT_YEAR]`

If `data.dte > 30`, also dispatch (in the same turn):

4. `[TICKER] ex-dividend date [NEXT_FEW_MONTHS] catalyst event conference`

These feed the Executive Summary and Market Context narrative — they do not recompute
numbers.

---

## Step 2 — Read the script output

Spend most of your reasoning here. Identify:

- The IV/HV verdict (`data.iv_hv_verdict`) — premium selling attractive or thin?
- Whether earnings is in-window (`data.earnings.within_expiry_window`) — flag prominently.
- The DTE bucket (`data.strike_guidance.dte_bucket`) — drives entry/management cadence.
- Any warnings (`data.warnings`) — earnings, low-IV, LEAPS, thin chain.
- For each trade in `data.trades`, the short strike vs. nearest support/resistance:
  - bull put short put vs. `pivot.S1`, `sma_50`, `chain_summary.put_oi_wall`
  - bear call short call vs. `pivot.R1`, `chain_summary.call_oi_wall`, `sma_50/200`
  - iron condor: both sides

You will cite these specific levels in the per-trade prose.

---

## Step 3 — Earnings handling

If `data.earnings.within_expiry_window` is true:
- Flag in the Executive Summary
- In the affected trade cards' **rationale**, state explicitly that you are either
  (a) accepting the risk because shorts are 1.5× the earnings expected move beyond support, or
  (b) recommending the trader avoid this expiry and wait for post-earnings IV crush
- Never silently ignore it

If earnings falls within ~7 days *after* expiry, note in Market Context that pre-earnings
IV is likely inflating premium.

---

## Step 4 — Produce the HTML output

Read `assets/template.html` (lives alongside this SKILL.md). Do **string replacement** for
each `{{TOKEN}}`. Most tokens are pre-rendered in `data.html.*`:

| Token | Source |
|---|---|
| `{{TICKER}}` | `html.ticker` |
| `{{STRATEGY_LABEL}}` | `html.strategy_label` |
| `{{EXPIRY}}` | `html.expiry` |
| `{{DTE}}` | `html.dte` |
| `{{PUB_DATE}}` | `html.pub_date` |
| `{{EXPIRY_RESOLUTION}}` | `html.expiry_resolution` |
| `{{SPOT}}`, `{{CHG_PCT}}`, `{{IV}}`, `{{HV}}`, `{{IV_HV_RATIO}}`, `{{IV_RANK}}`, `{{MAX_PAIN}}`, `{{EARNINGS_LINE}}`, `{{EXPECTED_MOVE}}`, `{{IV_VERDICT}}` | matching `html.*` keys |
| `{{LEVELS_ROWS_HTML}}` | `html.levels_rows_html` |
| `{{TRADE_SUMMARY_ROWS_HTML}}` | `html.trade_summary_rows_html` |
| `{{BULL_PUT_CARD_HTML}}` | `html.bull_put_card_html` (see slot-fill below) |
| `{{CONDOR_CARD_HTML}}` | `html.condor_card_html` (see slot-fill below) |
| `{{BEAR_CALL_CARD_HTML}}` | `html.bear_call_card_html` (see slot-fill below) |
| `{{FLOWCHART_HTML}}` | `html.flowchart_html` |
| `{{VOL_BARS_HTML}}` | `html.vol_bars_html` |
| `{{POSITIONING_HTML}}` | `html.positioning_html` |
| `{{SIZING_ROWS_HTML}}` | `html.sizing_rows_html` |
| `{{CHART_CONFIG_JSON}}` | `JSON.stringify(html.chart_config_json)` (paste as a JS object literal) |

**You write only these four narrative blocks** (each a few short paragraphs of HTML):

| Token | What to write |
|---|---|
| `{{EXEC_SUMMARY_HTML}}` | 2–4 `<p>` paragraphs. State the IV verdict, the directional read, the recommended scenario, earnings status. The first `<p>` should have class `lead` for the drop-cap. |
| `{{CONTEXT_HTML}}` | Catalyst summary from the web searches: recent earnings result, analyst moves, news/events. Bullet list or `<p>` blocks. Cite sources inline as `(source: …)`. |
| `{{EARNINGS_HTML}}` | If clean: a single `<div class="earnings-callout clean">` saying so, with the days-after note if applicable. If in-window: a `<div class="earnings-callout">` with the date, EM widening logic, and your recommended action. |
| `{{SOURCES_HTML}}` | `<li>` items: data script (yfinance, timestamp from `data.as_of`), each web search query + finding, and any other external fact. |

### Per-card prose slots (fill the `<!-- MODEL_SLOT:* -->` markers in each card)

Each pre-rendered card contains three placeholders that look like:

```html
<!-- MODEL_SLOT:bull_put_rationale --><p>[bull put rationale]</p>
```

Replace **both the comment AND the placeholder `<p>` immediately after it** with one short
`<p>` of your own (1–3 sentences). The slots:

| Slot suffix | What to write |
|---|---|
| `*_rationale` | Why this short strike is defensible. Cite the specific support/resistance level (pivot S1/R1, SMA 50/200, OI wall) and how far the short strike sits beyond it. |
| `*_entry_trigger` | A specific, price-action-conditional entry. Example: *"Enter only if AAPL holds above $278.50 (S1) for the first 30 minutes of Monday's session."* Not "enter if bullish." |
| `*_stop_rule` | A specific price OR delta level. Example: *"Close if short-put delta reaches 0.30, or if AAPL closes below $275 (S2)."* |

There are 9 slots total (3 cards × 3 slots). Fill all of them.

### Where to write the file

Write to `trade-plans/trade_plan_[TICKER]_[EXPIRY].html` in the current working directory.
Create the dir if missing (`mkdir -p trade-plans`). Tell the user the path at the end.

---

## Quality checklist (run before finishing)

- [ ] Script ran and JSON parsed before any HTML was written
- [ ] All `{{TOKEN}}` placeholders are replaced (search the output for `{{` — none should remain)
- [ ] All 9 `MODEL_SLOT` markers replaced with prose `<p>` (search the output for `MODEL_SLOT` — none should remain)
- [ ] Executive Summary explicitly states IV/HV verdict, directional read, recommended scenario, earnings status
- [ ] Earnings is addressed (in-window or clean, with days noted)
- [ ] Each card's rationale cites a specific level (pivot/SMA/OI wall) by name and number
- [ ] Each card's entry trigger references a specific price + time-of-day condition
- [ ] Sources section lists data script + every web search with timestamp
- [ ] For DTE > 90, the executive summary flags that standard short-premium is suboptimal

---

## Edge cases

- **Script errors / yfinance offline:** fall back to web-search estimation; label every value `(estimated)`; produce minimal HTML by hand.
- **Very low IV rank (`data.iv_rank_pct_proxy < 25`):** call out in Executive Summary that premium is thin.
- **LEAPS zone (`dte > 90`):** Executive Summary recommends diagonal/calendar; spread cards stay but are labelled suboptimal.
- **Thin option chain / strike not near target delta:** the script returns the nearest available; flag liquidity in the rationale.
- **No directional bias given:** treat as neutral; iron condor is the primary pick.
