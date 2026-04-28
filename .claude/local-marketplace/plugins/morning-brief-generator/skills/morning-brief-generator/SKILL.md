---
name: morning-brief-generator
description: >
  Produces THE MORNING BRIEF — a daily pre-market options intelligence report (v3.4). Use this skill
  whenever the user asks for: today's morning brief, the daily pre-market brief, "run the morning
  brief", "give me today's options brief", a pre-market options intelligence report, a daily watchlist
  of high-conviction options trades, or anything requesting overnight news + macro + ticker analysis
  + sourced strikes for the trading day. Also trigger when scheduled (e.g. by a cron-like routine
  before market open) or when the user asks to backfill or rerun the brief for a specific date.
  Always use this skill — do not attempt to write the brief manually. The skill enforces v3.4 anti-
  fabrication gates (mandatory sourced live-quote table, Step 6 #12 source citation), produces both
  a JSON record (consumed by downstream tools) and an editorial HTML report, and updates a rolling
  recommendations index used by the evening reviewer and carry-forward logic the next morning.
---

# Morning Brief Generator (v3.4)

Produce **THE MORNING BRIEF**, a daily pre-market options intelligence report. Two outputs every
run:

1. **JSON record** — `morning-briefs/YYYY-MM-DD.json` (machine-readable, schema-enforced)
2. **HTML magazine** — `morning-briefs/YYYY-MM-DD.html` (editorial, printable)

A rolling **`morning-briefs/recommendations.json`** index is updated automatically by the persist
script — it tracks every recommendation across days and is the source of truth for tomorrow's
Section 3 (Open Positions Carry-Forward) and the evening reviewer.

The quality bar is institutional pre-market research, not a generic market summary. Every trade
must cite a sourced live price; every recommendation must survive Step 6 validation; every prior-
day position must get a carry-forward decision.

---

## Inputs

| Input | Default if missing |
|---|---|
| Date (`--date YYYY-MM-DD`) | Today (US/Eastern) |
| Output directory | `morning-briefs/` in CWD |
| Sector / position focus (free-form text) | None |

---

## Step 0 — Bootstrap (run FIRST, before any analysis)

Run the bootstrap helper. It returns today's date in ET, day-of-week, minutes until 9:30 AM open,
brief volume number, **market status** (open/closed_weekend/closed_holiday/early_close),
**last_trading_day**, **quote_freshness_guidance**, and the **carry-forward set** (any open
recommendation from prior briefs that expires on or after today):

```bash
python3 /absolute/path/to/init_brief.py [--date YYYY-MM-DD] [--output-dir morning-briefs]
```

Substitute the actual absolute path to `init_brief.py` (lives alongside this SKILL.md). Parse the
JSON output. Use those values everywhere — do **not** compute date/time or read recommendations.json
yourself.

### Honor `market_status` before doing anything else

| `market_status` | Behavior |
|---|---|
| `open` | Normal flow. Live pre-market quotes required (≤ 30 min old). |
| `closed_weekend` | Markets closed Sat/Sun. Quote table uses **prior session close** (date in `last_trading_day`). Label every timestamp explicitly (e.g. `"2026-04-24 close"`, not `"07:30 ET"`). HTML masthead renders a banner: **"MARKETS CLOSED — Quotes from prior session close. Brief is for planning only."** Futures section: note that futures markets are closed (CME reopens Sunday 6:00 PM ET). The Step 1 Part E gate is **NOT** weakened — every ticker still needs a sourced price; it's just a closing price instead of a pre-market price. |
| `closed_holiday` | Same as weekend, with the holiday name (`market_status_detail`) shown in the masthead banner. Brief is forward-looking for the next trading session. |
| `early_close` | Live pre-market still required. Add an early-close note (`market_status_detail`) to every same-day trade card; management timelines must account for 1:00 PM ET close. |

The bootstrap's `quote_freshness_guidance` field tells you exactly how to label the quote table
sources for today's run — read it and follow it verbatim.

**This is NOT a weakening of the v3.4 anti-fabrication discipline.** The gate exists to prevent
recommending a trade with an invented price. Using yesterday's close on a Saturday is honest and
sourced; inventing a Friday pre-market quote on a Saturday is fabrication. Source what's actually
available, label it accurately, and proceed.

---

## Step 1 — Live price verification (v3.4 mandatory)

### Part A — Macro / futures (timestamped, live)

Search the web for current values of, with timestamp ≤ 30 min old:

- S&P 500 futures (level + %)
- Nasdaq futures (level + %)
- Dow Jones futures (level + %)
- VIX (level + direction)
- WTI crude (price + %)
- Brent crude (price + %)
- Gold futures (price + %)
- 10-Year Treasury yield
- US Dollar Index DXY
- Bitcoin (price + 24h %)
- Ethereum (price + 24h %)

Never substitute prior day's close. If live data cannot be confirmed, flag as unverified.

### Part B — Ticker-level live quotes (with source citation)

For every ticker you intend to recommend, search for current pre-market price (timestamp within
30 min), previous close, pre-market % move, and the source URL or exact search query used.

Strikes are derived **from the live price**, never from a template, never from training-data memory.

### Part C — Index ETF live quotes

Pull live pre-market data for SPY, QQQ, IWM with source citations.

### Part D — Crypto check

Note BTC and ETH 24h % change. Within 1% of ±3% trigger → pre-staging required (Section 8). Above
±3% → full crypto-equity section fires. **If section fires or pre-stages, live quotes for MSTR,
COIN, RIOT, MARA are REQUIRED — same discipline as Part B.**

### Part E — MANDATORY TICKER QUOTE TABLE (v3.4 structural gate)

Before writing any recommendation, build the quote table. It will appear visibly at the top of the
HTML output AND populate the `quote_table` array in the JSON. Format:

| Ticker | Live Price | Timestamp | Source |
|--------|-----------|-----------|--------|
| TSLA   | $X        | HH:MM ET  | search query OR URL |
| ...    | ...       | ...       | ... |

The table MUST include every ticker that appears in:

- Section 3 (Carry-Forward — current prices required for P/L)
- Section 4 (High-Conviction Plays)
- Section 6 (SPY/QQQ/IWM)
- Section 8 (MSTR/COIN/RIOT/MARA when applicable)
- Any ticker in Section 5 where strikes or P/L are claimed

Rules:

1. If any row would be blank → brief fails. Do not proceed to Step 5.
2. If the source column would say "memory" / "estimate" / "approximate" → go back and search.
3. The source must be **verifiable** — a search query that can be re-run or a URL that can be re-opened.
4. If a search returns a stale price (>30 min old during pre-market), note it explicitly.

This table is a structural gate. The brief cannot exist without it.

---

## Step 2 — Overnight news sweep

Search the web (covering the last 18 hours) for:

1. Pre-market movers — biggest % gainers and losers
2. Earnings released after yesterday's close or before today's open
3. M&A deals, buyouts, major corporate announcements overnight
4. FDA decisions, clinical trial results, drug approval news
5. Analyst upgrades / downgrades this morning
6. Geopolitical developments — explicitly:
    - Status of any active conflict zones
    - Naval / military / diplomatic events in the last 18h
    - Confirm whether announced actions actually occurred (arrival, not departure)
7. Executive orders, emergency regulatory actions
8. Federal Reserve speakers, economic data, Treasury actions
9. This week's earnings calendar with confirmed implied moves
10. Sector-specific themes driving pre-market flow
11. Bitcoin and Ethereum overnight news
12. **Overnight executive / political actions** — dedicated queries for items issued between
    yesterday's 4 PM ET close and this morning's pre-market:
    - "Trump Truth Social [last night's date]"
    - "presidential announcement overnight [date]"
    - "executive order [date]" or "executive action [date]"
    - "Federal Reserve statement overnight"
    - "Treasury action [date]"
    - Late-session SCOTUS rulings, congressional votes, SEC/FTC/FDA announcements

Do **not** rely on general market coverage to surface item 12. Run dedicated queries.

---

## Step 3 — Geopolitical & macro cross-check + binary resolution

Verify before any thesis:

- Has any major geopolitical situation REVERSED overnight?
- Is oil moving in the same direction as yesterday — or has it flipped?
- Are risk assets and safe havens moving consistent with the news?
- Has any ceasefire / peace deal / trade truce / sanctions change altered the picture?
- For any reversal narrative (e.g. delegation traveling to peace talks): has the action **occurred**,
  or is it still only announced? Trust arrival, not departure.

If anything reversed direction from yesterday → flag prominently as **REVERSAL ALERT** before any
recommendation.

### Binary Resolution Check (v3.3 — mandatory)

For every binary previously flagged in any recent brief (use the `carry_forward` set from Step 0
plus any binaries mentioned in Section 11 of the most recent brief), explicitly verify:

(a) RESOLVED since yesterday's close?
(b) EXTENDED or DELAYED to a new date?
(c) CANCELED or superseded?
(d) Still LIVE and pending today?

Do **not** assume status is unchanged. Search for explicit resolution. If resolved since last
publication: state the resolution in Section 2/10, remove from Section 11, adjust risk bias
(resolved binaries no longer justify defensive positioning on their own).

---

## Step 4 — Thesis formation per catalyst

For each major mover / catalyst:

- **Catalyst** — what happened, why it matters today
- **Directional bias** — bull / bear / neutral / binary
- **IV environment** — Elevated / Compressed / Unknown — confirmed or estimated
- **Expected move** — what options market is pricing
- **Macro cross-check**: before recommending a directional **bullish** trade, verify:
    - VIX rising?
    - Oil accelerating higher?
    - Broader tape risk-off?
    If YES to any two: downgrade conviction by one notch on bull debit spreads. **Exception:** if a
    previously-flagged binary resolved favorably (per Step 3), do not apply this downgrade based on
    stale fear conditions.

---

## Step 5 — Pick tickers, confirm they're in the quote table

Select 3–5 tickers for High-Conviction Plays.

**Structural gate (v3.4):**

For each ticker:

(a) In Step 1 Part E quote table with sourced live price? → proceed to Step 6.
(b) Not in the table? → search, add with citation, then proceed.
(c) Search failed to return a clean current price? → do not recommend. Replace with a ticker you
    can source.

Same gate applies to Section 3 carry-forward tickers, Section 6 ETFs, Section 8 crypto equities.

---

## Step 6 — Strategy, strike, expiry selection

### A) Minimum DTE rule: default 7 days

Defaults:

| Use case | DTE |
|---|---|
| Post-earnings IV crush (credit) | 14–30 |
| Pre-earnings vega (long) | Earnings + 7 minimum |
| Directional debit | 21–45 |
| Directional credit | 30–45 |
| Long straddle/strangle | ≥ 14 |
| M&A arbitrage | 30–60 |
| Squeeze bear spread | 45–60 |

### B) Short-DTE exception (<5 DTE only if ALL met)

1. Catalyst occurs today or tomorrow
2. Premium-SELLING structure only (not debit)
3. Card flagged "⚠ SHORT-DTE HIGH-GAMMA — SIZE 1/3 NORMAL"
4. Longer-dated alternative (7+ DTE) provided in same card
5. Conviction capped at MEDIUM

In JSON: set `short_dte_exception: true` AND `dte_at_entry < 7` together.

### C) Strike placement (strikes derived from Step 1 Part E live price)

1. **Bull call debit:** both strikes ≥ current price; long ATM/OTM, short further OTM.
2. **Bear put debit:** both strikes ≤ current price; long ATM/OTM, short further OTM.
3. **Put credit (bull put):** short 5–10% BELOW current; long 5–15 points further below.
4. **Call credit (bear call):** short 5–10% ABOVE current; long 5–15 points further above.
5. **Iron condor:** current price BETWEEN both short strikes.
6. **Long straddle:** ATM long call + ATM long put. Expiry after earnings.
7. **M&A arbitrage:** sell cash-secured put 5–15% BELOW deal price.
8. **Bear squeeze spread:** long put 5–15% below; short 30–50% below. Size 10% of normal.

### D) Spread width adjustment

Futures DOWN > 0.5% pre-market → narrow bull spread widths 50%.

---

## Step 7 — Strike & expiry validation checklist (MANDATORY, per trade)

For each trade, answer in writing before publishing:

1. Current pre-market price? (number + timestamp)
2. Exact strategy name?
3. Long-leg strike? Correct side of current price?
4. Short-leg strike? Correct side of current price?
5. Exact expiry date (full format)?
6. DTE from today (must be ≥ 7 OR short-DTE exception met)?
7. Estimated debit or credit?
8. Max profit?
9. Max loss?
10. Break-even?
11. Where is stock now relative to each strike?
12. **v3.4 — SOURCED PRICE CITATION:** "Live price for this ticker came from [search query] OR
    [URL] pulled at [timestamp]. Confirmed in Step 1 Part E quote table."

If item #12 is "my estimate" / "approximately" / "from memory" → **DO NOT PUBLISH.** Return to
Step 1 Part B, pull the live quote, update the table, then return to this trade.

If any answer #1–12 is missing, vague, or illogical → **DO NOT PUBLISH.**

### Common errors to screen

- ❌ DTE < 5 without full short-DTE exception
- ❌ Bull call spread with both strikes below current
- ❌ Bear put spread with both strikes above current
- ❌ Iron condor with current price outside the short strikes
- ❌ Long straddle with expiry before earnings
- ❌ Generic strikes without a specific dollar number
- ❌ v3.4: any trade where #12 cannot cite a sourced price

---

## Step 8 — Build the brief JSON

Construct a single JSON object matching the schema below. This is what gets persisted and what the
evening reviewer reads tomorrow.

```jsonc
{
  "brief_date": "YYYY-MM-DD",            // from Step 0
  "brief_version": "v3.4",
  "brief_volume": 42,                     // from Step 0
  "generated_at_et": "HH:MM ET",
  "minutes_until_market_open": 45,        // null on closed days
  "market_status": "open",                // open | closed_weekend | closed_holiday | early_close
  "market_status_detail": null,           // e.g. "Saturday" or "Memorial Day"
  "last_trading_day": "2026-04-24",       // date string

  "market_snapshot": {                    // Section 1
    "timestamp_et": "HH:MM ET",
    "spx_futures":  {"level": 5234.5, "pct": -0.41},
    "ndx_futures":  {"level": 18234.0, "pct": -0.55},
    "dow_futures":  {"level": 39812.0, "pct": -0.30},
    "vix":          {"level": 16.4, "direction": "rising"},
    "wti_crude":    {"price": 78.20, "pct": 1.1},
    "brent_crude":  {"price": 82.10, "pct": 0.9},
    "gold_futures": {"price": 2345.0, "pct": 0.2},
    "ten_year_yield": 4.36,
    "dxy":          104.21,
    "btc":          {"price": 67200, "pct_24h": -1.2},
    "eth":          {"price": 3415, "pct_24h": -0.8}
  },

  "reversal_alert": null,                 // Section 2 — null OR { "summary": str, "details": str }
  "binary_resolutions": [],               // resolved binaries from Step 3 — { "event": str, "status": "resolved"|"extended"|"canceled", "detail": str }

  "quote_table": [                        // Section "Sourced Live Quotes" + Step 1 Part E
    {
      "ticker": "TSLA",
      "live_price": 376.38,
      "timestamp": "07:30 ET",
      "source": "search: TSLA pre-market 2026-04-25"
    }
  ],

  "carry_forward_reviewed": [             // Section 3 — one entry per open prior recommendation
    {
      "id": "2026-04-23-IBM-01",          // matches id from prior brief in recommendations.json
      "current_stock_price": 240.10,
      "current_pnl_pct": 32,
      "strikes_status": "Stock $240 above $235 short put — both put legs OTM",
      "days_since_entry": 2,
      "dte_remaining": 21,
      "action_today": "HOLD",             // HOLD | CLOSE_HALF | CLOSE_FULL | ROLL | ADJUST_STRIKE
      "trigger_for_close": "Close half at 50% of max profit",
      "notes": ""
    }
  ],

  "recommendations": [                    // Section 4 + 5 + 6 + 8 (any new trade)
    {
      "id": "YYYY-MM-DD-TICKER-NN",       // unique; date + ticker + sequence
      "date_recommended": "YYYY-MM-DD",
      "ticker": "TSLA",
      "section": "high_conviction",       // high_conviction | implied_move | index | crypto_equity | squeeze
      "catalyst": "Q1 deliveries beat",
      "thesis": "...",
      "iv_environment": "Elevated (estimated)",
      "directional_bias": "bullish",
      "strategy": "bull_put_spread",      // snake_case
      "conviction": "HIGH",                // HIGH | MEDIUM | LOW
      "live_price_at_recommendation": 376.38,
      "price_source": "search: TSLA pre-market 2026-04-25",
      "price_timestamp": "07:30 ET",
      "legs": [
        {"action": "sell", "type": "put", "strike": 360, "expiry": "2026-05-16"},
        {"action": "buy",  "type": "put", "strike": 350, "expiry": "2026-05-16"}
      ],
      "expiry_date": "2026-05-16",
      "dte_at_entry": 21,
      "short_dte_exception": false,
      "spread_width": 10,
      "estimated_credit": 1.85,
      "estimated_debit": null,
      "max_profit": 185,                   // per contract, in dollars
      "max_loss": 815,
      "break_even": 358.15,                // number OR [low, high] for condor / straddle
      "stock_vs_strikes": "Stock $376.38 sits $16.38 above $360 short put — full credit at expiry if held above $360",
      "key_risk": "TSLA closes below $360 by 2026-05-16",
      "step6_citation": "Live price $376.38 from search 'TSLA pre-market 2026-04-25' at 07:30 ET, confirmed in quote_table",
      "status": "open"
    }
  ],

  "implied_move_watch": [                 // Section 5 — table rows
    {"ticker": "MSFT", "report_date": "2026-04-29", "report_timing": "AMC", "implied_move_pct": 4.2,
     "thesis": "...", "strategy_idea": "post-earnings put credit spread", "dte": 14, "conviction": "MEDIUM"}
  ],

  "index_read": {                         // Section 6
    "spy": {"price": 711.0, "support": 705, "resistance": 720, "tag": "complacent", "trade_idea": "..."},
    "qqq": {"price": 656.0, "support": 648, "resistance": 670, "tag": "neutral",    "trade_idea": "..."},
    "iwm": {"price": 276.0, "support": 270, "resistance": 285, "tag": "fearful",    "trade_idea": "..."}
  },

  "valuation_screen": [],                 // Section 7 — earnings-week names with P/E > 100, OR empty array
  "valuation_screen_note": "No qualifying names this week.",

  "crypto_equities": {                    // Section 8
    "trigger_state": "no_trigger",        // full_fire | pre_staged | no_trigger
    "btc_pct_24h": -1.2,
    "eth_pct_24h": -0.8,
    "note": "BTC -1.2% / ETH -0.8% — within normal range. No correlated-equity setup triggered."
  },

  "unusual_activity": [],                 // Section 9
  "meta_signal": "Mild risk-off into the open ...",  // Section 10
  "missed_catalyst_watch": []              // Section 11
}
```

---

## Step 9 — Persist the JSON via the helper script

Pipe the JSON into the persist script. It validates, writes the dated brief, and merges new
recommendations + carry-forward updates into `recommendations.json`:

```bash
python3 /absolute/path/to/write_brief.py < /tmp/brief.json
# or
cat /tmp/brief.json | python3 /absolute/path/to/write_brief.py --output-dir morning-briefs
```

The script enforces:

- `quote_table` non-empty
- every recommendation's ticker is in `quote_table` (Step 4 gate)
- every recommendation has a `price_source` (Step 6 #12 gate)
- every recommendation has `dte_at_entry >= 7` unless `short_dte_exception: true`

If validation fails, the brief is **not written**. Fix and re-run. Do not pass
`--allow-validation-errors` unless the user explicitly asks for it.

The script's stdout returns `{ok: true, brief_path, recommendations_path, ...}`. Read this and
include the paths in the final user-facing response.

---

## Step 10 — Render the HTML magazine

Write `morning-briefs/YYYY-MM-DD.html` as a complete standalone document.

### Design spec (unchanged from v3.4 prompt)

**Masthead**

- Black background (`#0f0f0f`)
- "THE MORNING BRIEF" in Bebas Neue
- Subtitle: `Options & Pre-Market Intelligence | [DAY] Edition | [DATE] · Vol. [#]`
- Red ticker bar (`#c41e3a`) below

**Typography (cdn.jsdelivr.net imports)**

- Headlines: Playfair Display
- Body: Source Serif 4
- Labels: Bebas Neue

**Color palette**

- Page: `#faf7f0` · Ink: `#0f0f0f` · Red accent: `#c41e3a`
- Bull green: `#1a7a3a` · Bear red: `#c41e3a` · Amber: `#b8860b`
- Body: `#2a2a2a` · Muted: `#888` · Surface: `#f0ede4`

**Section dividers** — triple rule between sections:

```
3px solid #0f0f0f / 1px solid #c41e3a / 0.5px solid #0f0f0f
```

**v3.4 visible element** — the Step 1 Part E quote table renders as its own visible block at the
top of the brief, just below the market snapshot. Reader must be able to verify every sourced
price before trusting any recommendation.

**Market-closed banner** — when `market_status` is `closed_weekend` or `closed_holiday`, render a
prominent banner immediately under the masthead:

> **MARKETS CLOSED — [Saturday | Memorial Day | …]. Quotes from [last_trading_day] close. Brief is for planning only.**

The banner uses the amber accent color (`#b8860b`) — same family as the carry-forward card so it
reads as "informational, not a tradable signal." When `market_status` is `early_close`, render a
smaller note: **"EARLY CLOSE — 1:00 PM ET. Same-day trades scaled accordingly."**

**Open Positions Carry-Forward block** — amber-accent card (`#b8860b` border) distinguishing it
from new-trade cards. Show ENTRY date, DTE remaining, current status vs strikes, MANAGEMENT ACTION
prominently.

**Stock / strategy card** — section label + ticker tag + move badge + headline + strategy box +
validation line + **v3.4 "Source:" citation line below live price** + conviction line.

**Conviction display**

- HIGH → green dot
- MEDIUM → amber dot
- LOW → red dot

**Footer** — black (`#0f0f0f`) with disclaimer.

### Section order in HTML (11 mandatory + quote table)

0. **Step 1 Part E Quote Table** (visible, at top, just under masthead/market snapshot)
1. Market Snapshot
2. Reversal Alert + Binary Resolution (only if applicable)
3. Open Positions Carry-Forward (always render the section header; if none, render the
   "No open positions carried forward" line)
4. Today's High-Conviction Plays (with sourced live prices)
5. This Week's Implied Move Watch
6. Index Options Read (SPY/QQQ/IWM with sourced prices)
7. Valuation Screen (>100x P/E)
8. Crypto-Correlated Equities (with sourced prices when firing)
9. Unusual Activity Flags
10. Meta Signal
11. Missed Catalyst Watch (no stale binaries)

**HTML file requirements**

- Full DOCTYPE, standalone HTML
- All CSS inline
- Three cdn.jsdelivr.net font imports
- `@media print` styles
- Saved to `morning-briefs/YYYY-MM-DD.html`

---

## Standing rules

**Mandatory**

- ✅ Run Step 0 bootstrap before anything
- ✅ Run Step 1 Parts A/B/C/D
- ✅ v3.4: produce the Step 1 Part E sourced quote table before Step 6
- ✅ Run Step 2 including item #12 (overnight executive actions)
- ✅ Run Step 3 Binary Resolution Check on every prior binary (carry-forward + recent missed-catalyst-watch)
- ✅ Run Step 5 gate (ticker must be in quote table before recommending)
- ✅ Run Step 7 validation including #12 source citation
- ✅ Every trade ≥ 7 DTE unless full short-DTE exception met (and `short_dte_exception: true`)
- ✅ Render all 11 mandatory sections in HTML and populate JSON for each
- ✅ Open Positions Carry-Forward must appear every day — if none open, render the empty-state line
- ✅ Flag IV data as estimated vs confirmed
- ✅ State the one thing that breaks each trade thesis (`key_risk`)
- ✅ Narrow bull spread width 50% when futures down > 0.5%
- ✅ Persist the JSON via `write_brief.py` (Step 9)
- ✅ Produce the HTML file (Step 10)
- ✅ End with standard disclaimer in HTML footer

**Prohibited**

- ❌ Recommend a trade without a sourced live price in `quote_table`
- ❌ Fill in a ticker price from training-data memory, estimate, approximation, or "last I knew"
- ❌ Mark Step 7 ✓ if item #12 cannot be answered
- ❌ Carry forward a binary as "live" without running the Binary Resolution Check
- ❌ Skip Step 2 item #12 (overnight executive actions)
- ❌ Recommend a trade with < 5 DTE unless full exception met
- ❌ Recommend short-DTE at HIGH conviction
- ❌ Recommend short-DTE debit structure
- ❌ Skip any mandatory section
- ❌ Bull call spread with both strikes below current
- ❌ Bear put spread with both strikes above current
- ❌ Iron condor with current price outside short strikes
- ❌ Generic strike placeholders without a specific dollar strike
- ❌ Straddle with expiry before earnings
- ❌ Omit a data timestamp from any price reference
- ❌ Trust a "delegation departing" narrative — wait for arrival
- ❌ Skip the carry-forward section

---

## Final user-facing response

After both files are written, produce a concise summary:

- Brief date and volume number
- Path to the HTML file (so the user can open it)
- Path to the JSON file
- Number of new recommendations
- Number of carry-forward positions reviewed
- Any reversal alert / binary resolution flagged
- Standard disclaimer (one line)

The HTML is the document the user reads. The JSON is the audit trail consumed by the evening
reviewer and the web app's portfolio UI.
