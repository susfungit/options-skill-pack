---
name: evening-brief-reviewer
description: >
  Reviews today's morning brief at end of day. Use this skill whenever the user asks for: an evening
  review, end-of-day brief recap, "score today's brief", "how did the morning brief do", "review my
  trades from this morning", "evening post-mortem", or any variant of scoring the morning brief
  against EOD market data. Also trigger when scheduled (e.g. by a cron-like routine after market
  close) or when the user asks to backfill an evening review for a specific date.
  The skill produces a JSON outcome record + an editorial HTML evening report. It updates the rolling
  recommendations.json with outcome + status changes per position, and accumulates prompt-change
  proposals in prompt_change_proposals.json. Proposals are NEVER auto-applied to the morning prompt —
  they wait for cross-day pattern validation (3+ recurrences in 14 days) and explicit user review.
  Always use this skill — do not attempt to score positions manually. The skill enforces the same
  v3.4 anti-fabrication discipline as the morning brief: every EOD price must be sourced.
---

# Evening Brief Reviewer

Score today's morning brief against end-of-day market data. Two outputs every run:

1. **Evening JSON** — `morning-briefs/YYYY-MM-DD-evening.json`
2. **Evening HTML** — `morning-briefs/YYYY-MM-DD-evening.html`

Side effects on shared state:

- `morning-briefs/recommendations.json` — every scored recommendation gets an `evening_reviews[]`
  entry appended; status updates to `closed`/`rolled`/`expired` are written through.
- `morning-briefs/prompt_change_proposals.json` — any proposed changes to the morning prompt are
  appended with their cross-day recurrence count.

This skill **never modifies the morning prompt directly.** It only proposes changes. You review and
merge them yourself.

---

## Scoring philosophy

Evaluating one day of trades has high noise. The skill is built to **separate signal from noise**:

- **Outcome** describes what happened today, not whether the trade is "right." A range-bound
  iron condor on day 1 of 20 DTE is `working` whether or not it ultimately profits.
- **Diagnosis** is what the skill is actually here to produce. When something failed, *why* did it
  fail? Was it the *data* the prompt told us to gather? The *process* the prompt told us to follow?
  The *judgment* the LLM applied? Or just *bad luck*?
- **Prompt-change proposals only come from data or process errors.** Judgment errors and bad luck
  are logged as lessons but do NOT trigger prompt changes — those would be over-fitting to noise.
- **Cross-day pattern detection.** A single bad day shouldn't rewrite the methodology. Proposals
  accumulate; the skill flags any proposal that has appeared 3+ times in 14 days as "action threshold
  met." You decide whether to actually merge.

---

## Inputs

| Input | Default if missing |
|---|---|
| Date (`--date YYYY-MM-DD`) | Today (US/Eastern) |
| Output directory | `morning-briefs/` in CWD |

---

## Step 0 — Bootstrap (run FIRST)

Run the bootstrap helper:

```bash
python3 /absolute/path/to/load_morning.py [--date YYYY-MM-DD] [--output-dir morning-briefs]
```

It returns:

- `today_date`, `market_status` (matters for partial-review flagging — AMC earnings on
  closed-market days can't be evaluated until the next session)
- `morning_brief_path` and the morning brief's recommendations + carry-forward reviews + quote table
- `open_positions_full_book` — every open position across ALL prior briefs that hasn't expired
  (today's new ones plus carry-forwards). Score the full book, not just today's adds.
- `recent_prompt_proposals` — the last 14 days of accumulated proposals (so you can see whether your
  new proposal recurs prior ones)

**If the morning brief for today doesn't exist**, the bootstrap exits with an error. The evening
review is a function of the morning brief — without one, there's nothing to score.

---

## Step 1 — EOD price verification (v3.4 discipline)

Same anti-fabrication gate as the morning. For every ticker that needs scoring (the union of
`open_positions_full_book` tickers + any ticker the morning brief named in `quote_table`,
`implied_move_watch`, or `index_read`), web-search the **EOD close**:

- Today's 4:00 PM ET close (or last available print)
- Day's % change
- Source URL or exact search query

Build the **`eod_quote_table`** — same structure as the morning brief's quote table, but with
end-of-day prints. This populates the JSON and renders visibly in the HTML.

Rules:

1. Empty `eod_quote_table` → review fails. The persist script will reject.
2. No "memory" / "estimate" / "approximate" sources. Fail back and search.
3. On weekend evenings (`market_status == closed_weekend`): there's no new EOD print. Use the same
   prior-session close the morning brief used; mark every scored recommendation
   `partial_review: true`. The rationale is the same as the morning's "honest sourcing beats invented
   live data" — sourcing yesterday's close on a Saturday is honest; pretending an EOD existed is
   fabrication.
4. On AMC earnings days: source the after-hours print if available (e.g. `AAPL after hours April 30
   2026`). If only RTH close is available, mark that position `partial_review: true` and note that
   tomorrow morning's carry-forward review will close the loop.

---

## Step 2 — Score each open position

For each entry in `open_positions_full_book`, produce a `scored_recommendations[]` block:

### Outcome classification

| Outcome | Meaning |
|---|---|
| `working` | Stock moved with the thesis. Estimated P/L positive OR position structurally on track (e.g. iron condor with stock still inside short strikes, days to expiry shrinking, theta accumulating). |
| `neutral` | Day produced no signal either way. Too early to call OR a sideways tape that doesn't refute the thesis. |
| `not_working` | Stock moved against the thesis but the thesis is still alive. Position is in DANGER/WARNING zone but not blown out. The trade can still recover. |
| `thesis_broken` | The catalyst played out opposite to what the brief predicted, OR the position is at/near max loss with no path to recovery. The trade should be closed regardless of DTE. |

### Required per-position fields

- `eod_price` — from your `eod_quote_table`
- `estimated_pnl_pct` — % of max profit/loss currently realized (estimate; you don't have the option
  chain, so derive from intrinsic value + time decay heuristic). Set `null` if the position is
  too binary to estimate (e.g. long straddle at 1 DTE).
- `estimated_pnl_dollars` — same, in dollars
- `outcome` — one of the four above
- `partial_review: true` if today's catalyst hasn't fully resolved (AMC earnings before tomorrow's
  RTH; weekend; holiday)
- `thesis_check` — one sentence on what the morning brief predicted vs what happened
- `lesson` — null OR one-line takeaway
- `diagnosis_category` — REQUIRED when `outcome` is `not_working` or `thesis_broken`. One of:
    - `data_error` — the morning brief's data was wrong (stale price, missed news, wrong IV)
    - `process_error` — the morning brief skipped a step that would have caught this
    - `judgment_error` — data was right, thesis was wrong (no prompt change warranted)
    - `bad_luck` — correct setup, unforeseeable event (no prompt change warranted)
- `status_update` — null to keep the position open. Set to `closed` / `rolled` / `expired` when
  outcome warrants it (`thesis_broken` → `closed`; an at-expiry position → `expired`).

### Anti-recency-bias guardrail

Do NOT classify a position as `thesis_broken` on a single bad day if the catalyst is still pending.
Example: SPY iron condor opened Monday, market gaps up Tuesday but is still inside short strikes —
`outcome: not_working` (or `neutral`), NOT `thesis_broken`. Reserve `thesis_broken` for positions
that genuinely have no path to recovery.

---

## Step 3 — Diagnose failures + propose prompt changes (sparingly)

For every position scored `not_working` or `thesis_broken`, write a `lesson`. For only those
diagnosed as `data_error` or `process_error`, also draft a `prompt_change_proposals[]` entry.

### Categorization rules (apply strictly)

- **`data_error`** — examples: "Brief used Friday close for ticker X but missed an after-hours print
  that moved the stock 5%." OR "Brief reported IV environment as 'compressed' but actually IV was
  elevated — the data fetch went to the wrong source." This is a fabrication-adjacent issue and
  warrants a prompt change.
- **`process_error`** — examples: "Brief skipped Step 2 #12 (overnight executive actions) and
  missed a Truth Social post that drove the gap." OR "Brief used a 0.20-delta short strike on a
  binary-event week when the rule says 0.15." The process is sound; the prompt didn't enforce it
  hard enough.
- **`judgment_error`** — "Brief correctly noted IV elevated and recommended bull put spread; stock
  fell on macro shock unrelated to the named catalyst. Setup was right; outcome was wrong."
  No prompt change.
- **`bad_luck`** — "Brief identified all known risks, including the binary that broke the trade.
  Position was sized accordingly." No prompt change.

### Proposal format

Each `prompt_change_proposal` entry must include:

- `category` — `data_error` or `process_error` (only these two)
- `summary` — one short, stable line. The persist script uses this to detect recurrence across days
  (case-insensitive, whitespace-normalized). Use the same summary for the same recurring problem.
- `rationale` — what evidence drives this proposal
- `proposed_change` — concrete edit to the v3.4 prompt (e.g. "In Step 2 item #12, add 'Truth Social
  posts after 8 PM ET' to the dedicated query list")
- `triggered_by_recommendation_ids` — the IDs of positions whose failure motivates this proposal

### The 3+ rule

You **propose** every time. The persist script computes `recurrence_count_14d` and
`action_threshold_met` (true when count ≥ 3). The HTML evening report surfaces this — a proposal at
recurrence 1 is "watch", recurrence 3+ is "consider acting."

You do NOT edit the morning SKILL.md. The user reviews proposals and decides.

---

## Step 4 — Build the evening JSON

```jsonc
{
  "review_date": "YYYY-MM-DD",
  "morning_brief_volume": 42,
  "morning_brief_meta_signal_summary": "Markets entered week at record SPX; iron condor + bull puts on relative strength + post-earnings name.",
  "market_status": "open",
  "eod_quote_table": [
    {"ticker": "SPY",  "eod_price": 716.20, "timestamp": "2026-04-27 16:00 ET", "source": "URL: finance.yahoo.com/quote/SPY/"},
    {"ticker": "INTC", "eod_price": 84.10,  "timestamp": "2026-04-27 16:00 ET", "source": "search: INTC close April 27 2026"}
  ],
  "scored_recommendations": [
    {
      "id": "2026-04-25-SPY-01",
      "eod_price": 716.20,
      "estimated_pnl_pct": 8,
      "estimated_pnl_dollars": 24,
      "outcome": "neutral",
      "partial_review": false,
      "thesis_check": "Predicted range-bound; SPY +0.32% intraday — within the iron condor range. No directional signal yet.",
      "lesson": null,
      "diagnosis_category": null,
      "status_update": null
    }
  ],
  "prompt_change_proposals": [],
  "meta_review": "Day 1 of the event-week iron condor + bull-put pair. Tape was quiet ahead of MAG7 earnings. INTC consolidated +1.8% — bull put spread up modestly. SPY drifted; iron condor on track. No diagnosis-worthy failures.",
  "tomorrow_focus": "Tuesday: pre-FOMC positioning. Watch for IV ramp on SPY/QQQ ahead of Wednesday 2:00 PM. Carry-forward review will assess INTC if Tuesday's tape rotates away from semis."
}
```

---

## Step 5 — Persist via write_evening.py

```bash
python3 /absolute/path/to/write_evening.py < /tmp/evening.json
```

Validates:

- `eod_quote_table` non-empty
- every `scored_recommendations[].id` exists in `recommendations.json`
- every `not_working`/`thesis_broken` outcome has a `diagnosis_category`
- proposals only created for `data_error` / `process_error` categories

Writes:

- `morning-briefs/YYYY-MM-DD-evening.json`
- Updates `morning-briefs/recommendations.json` (appends `evening_reviews[]` per position; updates
  `status` if applicable)
- Appends to `morning-briefs/prompt_change_proposals.json` (with `recurrence_count_14d` and
  `action_threshold_met` computed)

The script returns `{ok: true, ...}` and a list of `new_proposals` with their recurrence counts.
Surface those in the HTML — especially any with `action_threshold_met: true`.

---

## Step 6 — Render the HTML evening report

`morning-briefs/YYYY-MM-DD-evening.html` — same magazine design language as the morning brief but
with **outcome cards** instead of trade-recommendation cards.

### Differences from the morning HTML

- **Masthead subtitle** reads `EVENING REVIEW · [DAY] EDITION · [DATE] · Vol. [#]`
- **Ticker bar** color: deeper indigo (`#1a3a6e`) instead of red — visually distinct from the
  morning so a printed stack is easy to sort
- **Outcome cards** (replace trade cards):
    - Top border colored by outcome:
        - `working` → green (`#1a7a3a`)
        - `neutral` → grey (`#888`)
        - `not_working` → amber (`#b8860b`)
        - `thesis_broken` → red (`#c41e3a`)
    - Each card shows: ticker tag, EOD price + day %, outcome badge, P/L estimate, thesis check,
      lesson (if any), diagnosis category (if any), status update (if any), partial-review flag (if
      true)
- **Proposals section** (replaces "implied move watch"):
    - Each proposal renders with `recurrence_count_14d` prominently
    - Proposals where `action_threshold_met: true` get a distinct red "ACT NOW" header
    - Proposals at recurrence 1–2 show as "watch — accumulating"
- **Visible EOD quote table** at top (just like morning's Step 1 Part E table)
- **Meta Review block** (dark bg, indigo accent — analog to morning's Meta Signal)
- **Tomorrow Focus block** (light surface card, summarizing what tomorrow's brief should pay
  attention to)

Otherwise: same fonts (Bebas Neue / Playfair Display / Source Serif 4), same triple-rule dividers,
same `@media print` discipline, same standalone HTML.

---

## Standing rules

**Mandatory**

- ✅ Run Step 0 bootstrap; abort if morning brief for today doesn't exist
- ✅ Build `eod_quote_table` with sourced prices; never fabricate
- ✅ Score the FULL open book, not just today's new recommendations
- ✅ Apply the four-outcome / four-diagnosis taxonomy strictly
- ✅ Mark `partial_review: true` whenever the catalyst hasn't fully resolved
- ✅ Propose prompt changes ONLY for `data_error` / `process_error`
- ✅ Use stable `summary` strings on proposals so recurrence detection works
- ✅ Persist via `write_evening.py` — the script computes recurrence count
- ✅ Surface `action_threshold_met` proposals prominently in the HTML
- ✅ Render the evening HTML with outcome cards + proposals section
- ✅ End with standard disclaimer in HTML footer

**Prohibited**

- ❌ Edit the morning SKILL.md or any `v3.x` prompt directly
- ❌ Classify `thesis_broken` on a single bad day when the catalyst is still pending
- ❌ Generate a prompt-change proposal from a `judgment_error` or `bad_luck` outcome
- ❌ Skip the EOD quote table or use memory-derived prices
- ❌ Run the evening review without a morning brief for the same date
- ❌ Mark `action_threshold_met: true` yourself — that's the script's job

---

## Final user-facing response

After both files are written:

- Review date and morning brief volume number
- Path to the HTML evening report (so the user can open it)
- Path to the JSON
- Counts: positions scored, outcomes by category, new proposals, proposals at action threshold
- Brief one-line summary of the day (the `meta_review` field)
- One-line "tomorrow_focus"
- Standard disclaimer
