---
name: pmcc-leap-scanner
description: >
  Scans the options chains of many tickers and returns a ranked list of poor man's
  covered call (PMCC) candidates — deep-ITM, long-dated LEAP calls that act as a stock
  substitute, with a modeled short call to sell against them. Use this skill whenever
  the user wants to: run a weekend scanner for PMCC ideas, screen for poor man's covered
  call setups, find deep-ITM LEAP calls to buy as a stock replacement, build a diagonal
  call income strategy, or asks about "scan for PMCC candidates", "poor man's covered
  call scanner", "weekend LEAP scan", "find LEAP calls for a poor man's covered call",
  "which stocks are good for a PMCC", "deep ITM LEAP candidates", "diagonal call scanner",
  or any variant of screening multiple tickers for long LEAP call / PMCC opportunities.
  Also trigger when the user mentions a watchlist or "my list" together with PMCC, LEAP,
  or poor man's covered call. Always use this skill for multi-ticker PMCC screening —
  don't attempt to scan chains manually.
---

# PMCC LEAP Scanner

A weekend scanner that screens a universe of tickers for **Poor Man's Covered Call**
(PMCC) candidates. A PMCC buys a deep-ITM, long-dated **LEAP call** (the cheap stock
substitute) and sells shorter-dated OTM calls against it like a covered call. This skill
finds the stocks where that setup looks attractive right now.

## Step 1 — Gather inputs (all optional; sensible defaults)

| Input | Default | Notes |
|-------|---------|-------|
| tickers | built-in `universe.json` | Pass a custom list to override (e.g. the user's watchlist) |
| leap_delta | 0.80 | Target delta for the LEAP long leg (stock-substitute threshold) |
| leap_dte_min / max | 330 / 730 | LEAP must be this far out (≈ 12–24 months) |
| short_delta | 0.30 | Delta of the modeled short call income leg |
| short_dte_min / max | 30 / 45 | DTE window for the modeled short call |
| min_oi | 100 | Liquidity floor on the LEAP open interest |
| max_extrinsic_pct | 0.15 | Reject LEAPs whose time value exceeds 15% of strike |
| max_spread_pct | 0.15 | Reject LEAPs with a bid-ask spread wider than 15% of mid |

If the user gives a watchlist ("scan my list: AAPL, NVDA, MSFT"), pass those tickers.
Otherwise scan the built-in universe.

## Step 2 — Run the scanner

```bash
python3 scan_pmcc.py [TICKERS...] [--leap-delta 0.80] [--short-delta 0.30] [--html]
```

Examples:
- `python3 scan_pmcc.py` — scan the full built-in universe
- `python3 scan_pmcc.py AAPL NVDA MSFT` — scan just these
- `python3 scan_pmcc.py --html` — also write an HTML report to `pmcc-scans/`

The script outputs a single JSON object: `candidates` (ranked) and `skipped` (with
reasons). It never makes a trade — it screens.

## Step 3 — Fallback if the script fails

If the chain fetch fails (market closed, yfinance hiccup), say so plainly and offer to
retry during market hours. Do not fabricate strikes, premiums, or deltas. A PMCC needs a
real deep-ITM LEAP quote — if you can't source it, don't recommend it.

## Step 4 — Risk checklist (apply per candidate before recommending)

- **Earnings** before the LEAP expiry — expected, but flag near-term earnings that could
  gap the underlying.
- **Dividends / ex-div dates** — the short call carries early-assignment risk around
  ex-div, especially if ITM. Note upcoming ex-div dates.
- **Directional bias** — PMCC is a *bullish-to-neutral* strategy. Only suitable if the
  user is constructive on the name; flag clear downtrends.
- **IV rank** — high IV makes the short calls richer (good) but the LEAP pricier (bad).
  Mention IV context where relevant.
- **Liquidity** — the scanner already gates on OI and spread, but call out anything thin.

## Step 5 — Present the ranked candidate table

Show a compact table ranked by **annualized recovery ratio** (how fast selling short
calls recovers the extrinsic time value paid for the LEAP). For each candidate include:
ticker, spot, LEAP (expiry / strike / delta / debit / extrinsic %), modeled short call
(strike / delta / credit), net debit, max ROI on debit, breakeven, and recovery ratio.

Then highlight the top 3–5 with a one-line rationale each, and note how many tickers were
skipped and the most common skip reasons (transparency — no silent drops).

## Step 6 — Edge cases

- **No LEAP chain** / illiquid LEAP → ticker is skipped with a reason; don't force it.
- **Short strike ≤ LEAP strike** → not a valid PMCC; skipped.
- **Extrinsic too high** → the LEAP is overpaying for time value; skipped (raise
  `--max-extrinsic-pct` only if the user insists).
- **User wants more leverage** → lower `--leap-delta` / `--leap-dte-min` (aggressive,
  cheaper, decays faster). **More conservative** → raise them.
