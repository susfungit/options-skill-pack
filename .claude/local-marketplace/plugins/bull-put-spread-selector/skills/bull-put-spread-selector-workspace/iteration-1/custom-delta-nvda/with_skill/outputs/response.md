# Bull Put Spread — NVDA (15-Delta Short Put)

**Date:** March 19, 2026
**Skill:** bull-put-spread-selector

---

## Market Data Summary

| Item | Value |
|---|---|
| Ticker | NVDA (NVIDIA Corporation) |
| Current Price | ~$183.22 |
| 52-Week Range | ~$174.64 – $197.63 (recent month) |
| Recent Trend | Down ~2.1% over past month; pulled back from ~$197 to ~$183 |
| 30-Day IV | ~40.6% |
| IV Rank (IVR) | ~20% (low end of 52-week range) |
| IV Percentile | ~44% |
| Next Earnings | May 27, 2026 (after close) — outside the target expiry window |
| Target Expiry | April 30, 2026 (42 DTE) |

---

## Trade Setup

```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — NVDA                  ║
║  Expiry: April 30, 2026  ·  DTE: 42     ║
╠══════════════════════════════════════════╣
║  SELL  $157.50 Put   @ $1.13 (est.)     ║
║  BUY   $140.00 Put   @ $0.40 (est.)     ║
║  Net credit:  $0.73  per share          ║
╠══════════════════════════════════════════╣
║  Max profit:   $73   per contract       ║
║  Max loss:   $1,677  per contract       ║
║  Breakeven:   $156.77                   ║
║  Prob. profit: ~85%                     ║
║  Return/risk:  ~4.4%                    ║
╚══════════════════════════════════════════╝
```

> **All prices are estimated — verify on your broker's option chain before trading.**

---

## Strike Selection Rationale

**Why these strikes?**

The user requested a 15-delta short put, which is further out-of-the-money than the skill's default 20-delta target. At 42 DTE and with NVDA's 30-day IV of ~40.6%, a 15-delta put lands approximately 14% below the current price (vs. ~12% for a 20-delta put). Applying the OTM% formula:

```
otm_pct (15Δ) ≈ 0.85 × 0.406 × sqrt(42/365) × 1.20 ≈ 14.0%
Short strike    = $183.22 × (1 – 0.140) = $157.57 → rounded to $157.50
Long strike     = $157.50 × 0.90 = $141.75 → rounded to $140.00
Spread width    = $157.50 – $140.00 = $17.50
```

The $157.50 short strike is approximately 14.0% below the current price of $183.22, providing a substantial buffer — NVDA would need to fall more than $26 from current levels before the trade is at risk of max loss.

---

## Risk Signal Checklist

| Check | Status | Note |
|---|---|---|
| Earnings within expiry window? | CLEAR | Next earnings May 27, 2026 — after April 30 expiry |
| IV Rank < 25? | ⚠️ CAUTION | IVR ~20% — premium is on the thin side; consider if reward justifies the risk |
| Stock in a downtrend? | ⚠️ NOTE | NVDA down ~2.1% over past month; moving further OTM (15Δ) is appropriate here |
| Ex-dividend date within expiry? | CHECK BROKER | NVIDIA pays a small dividend; verify no ex-div date falls within the window |
| Spread width < $3? | CLEAR | $17.50 spread width is well above the $3 threshold |

---

## Trade Rationale (Prose)

**Strike selection:** The $157.50 short put was chosen to target approximately 15 delta — placing it ~14% out-of-the-money given NVDA's current IV of ~40.6% and 42 days to expiration. The wider OTM% vs. a standard 20-delta setup reflects both the user's preference for a lower-delta short and NVDA's recent mild downtrend over the past month. The $140 long put provides defined downside protection, capping max loss at $1,677 per contract.

**For max profit:** NVDA must close above $157.50 at expiration on April 30. Given that the stock is currently at $183.22, this requires the stock to hold at or above that level — a buffer of more than $25.72 (14%) from today's price. The ~85% probability of profit reflects this wide buffer.

**Key risk:** The primary risk is a significant, sustained decline in NVDA. A drop to the $157.50 level would put the spread at breakeven ($156.77); a fall below $140 would produce the maximum loss of $1,677 per contract. Given the recent pullback from $197 and the broader semiconductor sector volatility, a sharp downward move is the main threat.

**Flags:** The IVR of ~20% is the primary caution here. With IV in the lower fifth of its 52-week range, the collected premium ($0.73/share, or $73/contract) is relatively modest for a $17.50-wide spread. The return on risk of ~4.4% reflects the thin premium environment. Traders who are comfortable with the directional thesis (NVDA holds above ~$157 through late April) may still find this worthwhile, but those expecting richer premium should consider waiting for an IV expansion or tightening the spread width to improve the credit-to-width ratio. The good news: NVDA's next earnings (May 27) fall outside this expiry window, eliminating the earnings-event risk that often makes NVDA spreads difficult to manage.

---

## Interactive P&L Chart

Want me to plot the full P&L curve for this spread so you can visualize the risk zones? I can render a chart showing the expiry P&L from the $140 long strike through to above the $157.50 short strike, with vertical dashed lines marking the breakeven ($156.77), short strike ($157.50), and long strike ($140.00).

---

## Sources

- [CNBC NVDA Quote](https://www.cnbc.com/quotes/NVDA) — current price data
- [NVDA Implied Volatility | IV Rank & Percentile | projectoption](https://projectoption.com/stocks/nvda/implied-volatility) — IV and IVR data
- [NVIDIA Announces Financial Results for Fourth Quarter and Fiscal 2026 | NVIDIA Newsroom](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026) — Q4 FY2026 earnings
- [NVIDIA (NVDA) Earnings Date and Reports 2026 | MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/NVDA/earnings/) — next earnings date (May 27, 2026)
- [NVDA Options Prices for Nvidia Corp Stock — Barchart.com](https://www.barchart.com/stocks/quotes/nvda/options) — options chain reference
- [NVIDIA Corporation (NVDA) Options Chain — Yahoo Finance](https://finance.yahoo.com/quote/NVDA/options/) — options chain reference
