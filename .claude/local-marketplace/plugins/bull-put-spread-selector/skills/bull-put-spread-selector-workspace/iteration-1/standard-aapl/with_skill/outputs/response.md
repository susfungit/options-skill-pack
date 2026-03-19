# Bull Put Spread — AAPL

**Date of Analysis:** March 19, 2026
**Skill:** bull-put-spread-selector

---

## Market Data Gathered

| Data Point | Value | Source |
|---|---|---|
| AAPL Current Price | ~$250.00 | Web search (March 19, 2026) |
| Intraday Range | $249.00 – $255.30 | Web search |
| 52-Week Range | $169.21 – $288.62 | Web search |
| Implied Volatility (30-day) | ~39% | OptionCharts / Web search |
| IV Rank (IVR) | ~18.55 | OptionCharts / Web search |
| Target Expiry | May 1, 2026 | 43 DTE from today |
| Next Earnings | April 30, 2026 (after close) | MarketBeat / confirmed |
| Ex-Dividend Date | May 12, 2026 | StockEvents / Web search |

> **Note:** Live option chain with specific strikes and delta values could not be retrieved from web search. All strike prices, premiums, and Greeks below are **estimated** using the Black-Scholes approximation from the skill methodology. Verify on your broker's chain before placing any trade.

---

## Strike Estimation (Black-Scholes Approximation)

**Inputs:**
- Stock price: $250.00
- IV: 39% (0.39)
- DTE: 43
- Delta target: 0.20 (20Δ)

**Short put strike calculation:**
```
otm_pct = 0.85 × IV × sqrt(DTE/365)
        = 0.85 × 0.39 × sqrt(43/365)
        = 0.85 × 0.39 × 0.3432
        = 0.1138  →  11.4% OTM

short_strike = $250.00 × (1 − 0.114) = $221.50  →  rounded to $222.50
```

**Long put strike:**
```
long_strike = $222.50 × 0.90 = $200.25  →  rounded to $200.00
```

**Net credit estimate:**
```
short_put_mid ≈ $250 × 0.0065 × sqrt(43/30) = $250 × 0.0065 × 1.197 = $1.95
long_put_mid  ≈ $1.95 × 0.35 = $0.68
net_credit    = $1.95 − $0.68 = $1.27
```

---

## Trade Card

```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — AAPL                  ║
║  Expiry: May 1, 2026  ·  DTE: 43 days   ║
╠══════════════════════════════════════════╣
║  SELL  $222.50 Put   @ $1.95 (est.)     ║
║  BUY   $200.00 Put   @ $0.68 (est.)     ║
║  Net credit:  $1.27  per share (est.)   ║
╠══════════════════════════════════════════╣
║  Max profit:  $127   per contract       ║
║  Max loss:    $2,123 per contract       ║
║  Breakeven:   $221.23                   ║
║  Prob. profit: ~80%                     ║
║  Return/risk:  6.0%                     ║
╚══════════════════════════════════════════╝
```

*(All values estimated — verify on your broker's chain before trading)*

---

## Trade Rationale

**Why this strike?** The $222.50 short put was selected to target a ~20Δ (approximately 11.4% OTM) based on AAPL's current IV of ~39% and a 43-day expiry window. At this delta, approximately 80% of the time the stock stays above the short strike and the full credit is retained. The long put at $200.00 (10% below the short strike) provides defined downside protection and creates a $22.50-wide spread. The $1.27 net credit (estimated) gives a modest 6% return on risk — thin but consistent with the low-IV environment.

**What needs to happen for max profit:** AAPL must close at or above $222.50 on May 1, 2026. The stock currently trades at $250, which means it can fall as much as $28.77 (roughly 11.5%) and the trade still reaches max profit. The breakeven is $221.23 — the stock can decline roughly 11.5% before the position starts losing money.

**Key risk:** The primary risk is a sharp decline in AAPL below $222.50 before or at expiry. Max loss of $2,123 per contract occurs if AAPL closes at or below $200.00 at expiration. The trade has no ability to profit beyond the initial credit collected.

**Risk flags from checklist:**

---

## Risk Signal Checklist

- [x] **⚠️ EARNINGS WITHIN EXPIRY WINDOW** — Apple is scheduled to report Q2 2026 earnings on **April 30, 2026** (after close), which is the day BEFORE the May 1 expiry. This is a critical risk: IV will be artificially elevated into earnings and will crush immediately after, potentially causing a large gap move in either direction. A negative earnings surprise could easily push AAPL down 5–15% overnight, blowing through the short strike. **This is a significant structural risk for this specific expiry.**

- [x] **⚠️ IV RANK < 25** — AAPL's IVR is approximately 18.55, which is below the 25 caution threshold. Premium is relatively thin despite a 39% IV reading. The low IVR means you're not being well-compensated for the risk you're taking — the credit is not as rich as it would be during a high-IVR period. Consider waiting for IVR to rise above 30–40 before selling premium.

- [ ] **Stock trend** — AAPL at $250 is currently in the lower third of its 52-week range ($169–$289). The stock is below its 52-week high by ~$38. Trend is not clearly bullish — exercise caution.

- [ ] **Ex-dividend date** — The next ex-dividend date is May 12, 2026, which falls AFTER the May 1 expiry. No early assignment risk for this trade.

- [ ] **Spread width** — The $22.50 spread width is well above the $3 minimum threshold. Commissions are not a concern.

---

## Recommendation

> **Proceed with caution.** The two overlapping risk flags — earnings on April 30 and low IVR — make this a less-than-ideal setup. The earnings event is especially problematic: taking a bull put spread through an earnings announcement is a high-risk move because the stock can gap dramatically in either direction. If you still want to trade AAPL puts, consider:
>
> 1. **Using the April 24, 2026 expiry (36 DTE)** to avoid the earnings date entirely. This expiry closes before the April 30 earnings report and avoids the binary event risk.
> 2. **Waiting until after earnings** (first week of May) to sell premium when post-earnings IV crush has settled.
> 3. **Moving the short strike further OTM** (15Δ instead of 20Δ) if proceeding through earnings to give more cushion, at the cost of even thinner credit.

---

## Alternative: April 24 Expiry (Pre-Earnings, 36 DTE)

If you choose to avoid earnings, the April 24, 2026 expiry (36 DTE) is the preferred alternative:

**Estimated strikes for April 24 (36 DTE):**
```
otm_pct = 0.85 × 0.39 × sqrt(36/365) = 0.85 × 0.39 × 0.3141 = 0.1041  →  10.4% OTM
short_strike ≈ $250 × 0.896 = $224.00  →  $224.00
long_strike  = $224.00 × 0.90 = $201.60  →  $200.00

short_put_mid ≈ $250 × 0.0065 × sqrt(36/30) = $250 × 0.0065 × 1.095 = $1.78
long_put_mid  ≈ $1.78 × 0.35 = $0.62
net_credit    = $1.78 − $0.62 = $1.16
```

```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — AAPL (Pre-Earnings)   ║
║  Expiry: Apr 24, 2026  ·  DTE: 36 days  ║
╠══════════════════════════════════════════╣
║  SELL  $224.00 Put   @ $1.78 (est.)     ║
║  BUY   $200.00 Put   @ $0.62 (est.)     ║
║  Net credit:  $1.16  per share (est.)   ║
╠══════════════════════════════════════════╣
║  Max profit:  $116   per contract       ║
║  Max loss:    $2,284 per contract       ║
║  Breakeven:   $222.84                   ║
║  Prob. profit: ~80%                     ║
║  Return/risk:  5.1%                     ║
╚══════════════════════════════════════════╝
```

This pre-earnings version eliminates the binary event risk while maintaining a similar risk/reward structure. Credit is slightly thinner ($1.16 vs $1.27) but the trade doesn't carry earnings gap risk.

---

## P&L Visualization

Want me to plot the full P&L curve for this spread so you can visualize the risk zones?

---

## Sources

- [Apple Inc. (AAPL) Stock Price — Yahoo Finance](https://finance.yahoo.com/quote/AAPL/)
- [AAPL Implied Volatility — OptionCharts](https://optioncharts.io/options/AAPL/volatility-skew)
- [AAPL Implied Volatility IV Rank — Market Chameleon](https://marketchameleon.com/Overview/AAPL/IV/)
- [Apple (AAPL) Earnings Date 2026 — MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/AAPL/earnings/)
- [Apple (AAPL) Options Chain — MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/AAPL/options/)
- [Apple (AAPL) Options Chain — Yahoo Finance](https://finance.yahoo.com/quote/AAPL/options/)
- [AAPL Dividend 2026 — Stock Events](https://stockevents.app/en/stock/AAPL/dividends)
- [Apple (AAPL) Dividend History — MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/AAPL/dividend/)
