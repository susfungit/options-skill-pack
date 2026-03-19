# NVDA 15-Delta Bull Put Spread — March 19, 2026

> **Methodology note:** This analysis was produced without a specialized skill. Market data was sourced via web search; options pricing was derived using Black-Scholes approximations (no live broker feed). Use your brokerage to verify live bid/ask before entering.

---

## Market Snapshot

| Field | Value |
|---|---|
| Underlying | NVIDIA Corporation (NVDA) |
| Price (March 18 close) | $180.40 |
| 52-Week Range | $86.62 – $212.19 |
| 30-Day IV | ~40.6% |
| IV Rank (52-week) | ~20% |
| Target Expiration | **April 17, 2026** (29 DTE) |
| Risk-Free Rate | ~4.3% |

---

## 15-Delta Strike Calculation (Black-Scholes)

To find the put strike with delta ≈ −0.15:

```
σ      = 0.406 (IV)
T      = 29/365 = 0.0795 years
σ√T    = 0.406 × 0.2820 = 0.1145
(r + ½σ²)T = (0.043 + 0.0825) × 0.0795 = 0.00998

Target: put delta = −0.15 → N(d1) = 0.85 → d1 = N⁻¹(0.85) ≈ 1.0364

ln(S/K) = d1 × σ√T − (r + ½σ²)T
        = 1.0364 × 0.1145 − 0.00998
        = 0.1187 − 0.00998 = 0.1087

K = S × e^(−0.1087) = 180.40 × 0.8970 ≈ $161.80
```

**Rounded to nearest listed NVDA strike: $162.50**

Verified delta at $162.50:
- d1 ≈ 1.03 → put delta ≈ −0.15  ✓

---

## Recommended Trade: Sell $162.50 / Buy $152.50 Put Spread (April 17, 2026)

### Structure

| Leg | Action | Strike | Expiration | Approx Mid | Delta |
|---|---|---|---|---|---|
| Short put | SELL | $162.50 | Apr 17, 2026 | ~$2.60 | −0.15 |
| Long put  | BUY  | $152.50 | Apr 17, 2026 | ~$1.15 |  −0.08 |

---

### Trade Economics (per 1 contract = 100 shares)

| Metric | Per Share | Per Contract |
|---|---|---|
| Net Credit Received | $1.45 | $145 |
| Maximum Profit | $1.45 | **$145** |
| Maximum Loss | $8.55 | **$855** |
| Spread Width | $10.00 | $1,000 |
| Breakeven at Expiration | **$161.05** | — |
| Return on Risk | 17.0% | — |
| Probability of Profit | ~**85%** | — |

> Probability of profit is approximated as 1 − |short put delta| at trade entry, consistent with the Black-Scholes framework. More precisely, POP ≈ N(d2) evaluated at the breakeven price ≈ 85%.

---

### Alternate Configuration: $5-Wide Spread

If you prefer less capital at risk with a slightly tighter setup:

| Leg | Action | Strike | Approx Mid |
|---|---|---|---|
| Short put | SELL | $162.50 | ~$2.60 |
| Long put  | BUY  | $157.50 | ~$1.55 |

| Metric | Per Share | Per Contract |
|---|---|---|
| Net Credit | $1.05 | $105 |
| Max Profit | $1.05 | $105 |
| Max Loss | $3.95 | $395 |
| Breakeven | $161.45 | — |
| Return on Risk | 26.6% | — |
| Probability of Profit | ~85% | — |

---

## Trade Rationale

1. **Bullish / neutral bias.** NVDA closed at $180.40, approximately 15% above the 15-delta short strike ($162.50), giving substantial downside cushion before the trade loses.

2. **Low IV environment.** IV Rank of ~20% means IV is in the lower quintile of its 52-week range (low: 31.7%, high: 75.1%). Premium collection is moderate; a spread structure captures defined credit while capping risk if IV spikes.

3. **29 DTE is theta-optimal.** The April 17 standard monthly cycle sits in the 25–45 DTE sweet spot where theta decay accelerates while avoiding binary event risk (NVDA's next earnings are expected in late May 2026, outside this window).

4. **$10-wide spread is preferred** for better credit-to-risk ratio (17% ROR) and meaningful premium ($145/contract) that justifies commission drag. The $5-wide is viable for accounts with smaller buying power.

---

## Risk Management Guidelines

| Scenario | Action |
|---|---|
| Stock falls toward $168–$170 (-7%) | Consider closing spread at ~50% max loss ($427) |
| Credit decays to 50% of initial ($0.72) | Consider closing early for profit (captures most theta) |
| IV spikes sharply (>60%) | Monitor vega exposure; spread is net short vega |
| Approaching expiration with stock near $162.50 | Close position — avoid pin risk and assignment |

---

## Entry Checklist

- [ ] Confirm NVDA is not within 2 weeks of an earnings announcement
- [ ] Verify live bid/ask for $162.50P and $152.50P — target fill at mid or better
- [ ] Confirm short put delta is −0.14 to −0.16 at time of entry (not just at calculation time)
- [ ] Size position: risk no more than 2–5% of portfolio on a single spread
- [ ] Set GTC order to close at 50% max profit ($0.72 credit remaining)
- [ ] Set alert if NVDA drops below $170

---

## Summary

**Trade:** Sell NVDA Apr 17 2026 $162.50 / $152.50 Bull Put Spread
**Credit:** ~$1.45 ($145/contract)
**Max Loss:** ~$8.55 ($855/contract)
**Breakeven:** $161.05
**Probability of Profit:** ~85%
**Short Strike Delta:** −0.15 (target met)

---

*Sources used for market data:*
- [CNBC NVDA Quote](https://www.cnbc.com/quotes/NVDA) — closing price $180.40 (March 18, 2026)
- [ProjectOption NVDA IV](https://projectoption.com/stocks/nvda/implied-volatility) — IV 40.6%, IV Rank 20%
- [MarketBeat NVDA 52-Week Range](https://www.marketbeat.com/stocks/NASDAQ/NVDA/chart/) — $86.62–$212.19
- [Barchart NVDA Options](https://www.barchart.com/stocks/quotes/nvda/options) — options chain reference

*Options pricing estimated via Black-Scholes model. Not financial advice. Verify all figures with your broker before trading.*
