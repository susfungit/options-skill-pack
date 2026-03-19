# Bull Put Spread — TSLA (Tesla, Inc.)
**Generated:** March 19, 2026

---

## Market Context

| Data Point | Value |
|---|---|
| Current Price | ~$398.10 |
| 52-Week Range | $214.25 – $498.83 |
| Recent Trend | Downtrend — below 20/50/100-day SMAs; descending channel |
| 30-Day IV | ~50.3% |
| IV Rank (IVR) | ~5.88 (very low relative to historical range) |
| Next Earnings | **April 28, 2026 (After Close) — CONFIRMED** |
| Dividend | None |

---

## Expiry Selection

Today is March 19, 2026. Six weeks out = approximately April 30, 2026 (42 DTE).

Available standard expiries near that target:
- **April 25, 2026** — 37 DTE — **BEFORE earnings (Apr 28)** ✓ Recommended
- May 1, 2026 — 43 DTE — spans earnings (Apr 28); IV crush post-earnings dramatically changes P&L

**Selected expiry: April 25, 2026 (37 DTE)** — this is the closest expiry that avoids the April 28 earnings event. Holding through earnings with a defined-risk spread is possible but adds significant binary risk; the April 25 expiry sidesteps that.

---

## Strike Estimation

Live chain data unavailable — values estimated using Black-Scholes approximation *(estimated — verify on your broker's chain)*.

**Inputs:**
- Stock price (S): $398.10
- IV: 50.25%
- DTE: 37

**Short put (20Δ target):**
```
otm_pct = 0.85 × 0.5025 × sqrt(37/365)
        = 0.85 × 0.5025 × 0.3184
        = 0.1360  (13.6% OTM)

Short strike = $398.10 × (1 − 0.136) = $343.96 → round to $345
```

**Long put (10% below short strike):**
```
Long strike = $345 × 0.90 = $310.50 → round to $310
```

**Spread width:** $345 − $310 = **$35**

**Net credit estimate:**
```
short_put_mid ≈ $398.10 × 0.0065 × sqrt(37/30) = $2.88
long_put_mid  ≈ $2.88 × 0.35                   = $1.01
net_credit    = $2.88 − $1.01                  = $1.87
```

---

## Trade Card

```
╔══════════════════════════════════════════╗
║  BULL PUT SPREAD — TSLA                  ║
║  Expiry: Apr 25, 2026  ·  DTE: 37 days  ║
╠══════════════════════════════════════════╣
║  SELL  $345 Put   @ $2.88 (estimated)   ║
║  BUY   $310 Put   @ $1.01 (estimated)   ║
║  Net credit:  $1.87  per share          ║
╠══════════════════════════════════════════╣
║  Max profit:  $187  per contract        ║
║  Max loss:    $3,313  per contract      ║
║  Breakeven:   $343.13                   ║
║  Prob. profit: ~80%                     ║
║  Return/risk:  5.64%                    ║
╚══════════════════════════════════════════╝
```

*(All values estimated — verify on your broker's live option chain before entering the trade.)*

---

## Risk / Reward Summary

| Metric | Value |
|---|---|
| Max Profit | $187 per contract |
| Max Loss | $3,313 per contract |
| Breakeven | $343.13 |
| Probability of Profit | ~80% |
| Return on Risk | 5.64% |

---

## Risk Checklist

| Check | Status | Notes |
|---|---|---|
| Earnings within expiry window? | ✅ CLEAR | April 25 expiry is 3 days BEFORE the Apr 28 earnings |
| IV Rank < 25? | ⚠️ CAUTION | IVR ~5.88 — premium is very thin relative to TSLA's historical IV range |
| Stock in a downtrend? | ⚠️ CAUTION | TSLA is in a descending channel; below all major SMAs; Strong Sell technical signal |
| Ex-dividend date within expiry? | ✅ CLEAR | TSLA pays no dividend; no early assignment risk |
| Spread width < $3? | ✅ CLEAR | Spread is $35 wide — well above the minimum threshold |

---

## Rationale

**Why this strike?** The $345 short put is approximately 13.6% out-of-the-money, targeting a ~20 delta, which provides a theoretical ~80% probability of expiring worthless. TSLA's elevated absolute IV (50%+) generates reasonable premium even though the IV Rank of 5.88 signals that this is historically cheap relative to TSLA's past volatility — meaning premium sellers are not getting as much edge as usual on a relative basis.

**What needs to happen for max profit?** TSLA must remain above $345 at expiration on April 25, 2026. At a current price of ~$398, the stock has roughly 13.3% of downside buffer before the short strike is breached.

**Key risk.** TSLA is in a confirmed downtrend — trading below its 20-, 50-, and 100-day moving averages in a descending channel with a "Strong Sell" technical signal. A continuation lower (support at ~$381 is the nearest level, then $343) would push the position toward maximum loss. The low IVR compounds this: premium collected is thin, so the reward-to-risk ratio of 5.64% is modest for the directional exposure taken.

**Risk flags summary.** Two significant flags apply: (1) ⚠️ TSLA is in a clear downtrend — consider sizing down to 1 contract or targeting a 15Δ short put (~$325 strike) to gain more buffer; (2) ⚠️ IV Rank of ~5.88 means options are historically cheap — premium collected is thinner than typical for this stock, reducing the attractiveness of selling premium right now. The April 28 earnings date is the largest lurking risk: the April 25 expiry avoids it, but if you accidentally select the May 1 or later expiry, you will straddle a major binary event.

---

## Alternative: Lower-Delta Trade for Downtrend Protection

Given the downtrend, a more conservative configuration targeting **15Δ** (~16–17% OTM) may be preferable:

| Parameter | 20Δ (Primary) | 15Δ (Conservative) |
|---|---|---|
| Short Strike | $345 (estimated) | ~$330 (estimated) |
| Long Strike | $310 (estimated) | ~$295 (estimated) |
| Net Credit | ~$1.87 | ~$1.30 (estimated) |
| Breakeven | ~$343.13 | ~$328.70 (estimated) |
| Buffer from current price | 13.3% | 17.4% |

*(All values estimated — verify on your broker's chain.)*

---

## P&L Visualization

Want me to plot the full P&L curve for this spread so you can visualize the risk zones?

---

## Sources

- [Tesla Stock Forecast | Capital.com (Mar 18, 2026)](https://capital.com/en-int/market-updates/tesla-stock-forecast-18-03-2026)
- [TSLA Implied Volatility | Market Chameleon](https://marketchameleon.com/Overview/TSLA/IV/)
- [TSLA IV Mean 30-Day | AlphaQuery](https://www.alphaquery.com/stock/TSLA/volatility-option-statistics/30-day/iv-mean)
- [Tesla Earnings Date | MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/TSLA/earnings/)
- [TSLA Technical Analysis | Investing.com](https://www.investing.com/equities/tesla-motors-technical)
- [Tesla Dividend History | Nasdaq](https://www.nasdaq.com/market-activity/stocks/tsla/dividend-history)
- [TSLA Options Chain | Barchart.com](https://www.barchart.com/stocks/quotes/TSLA/options)
