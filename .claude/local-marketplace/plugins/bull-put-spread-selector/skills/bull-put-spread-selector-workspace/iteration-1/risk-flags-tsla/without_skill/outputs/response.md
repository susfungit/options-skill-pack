# TSLA Bull Put Spread — Setup Report
**Date:** March 19, 2026
**Underlying:** Tesla, Inc. (TSLA)
**Strategy:** Bull Put Spread (Short Put Vertical)
**Methodology:** General knowledge — no specialized skill applied

---

## 1. Market Context

| Parameter | Value |
|---|---|
| Current TSLA Price | ~$392–$398 (most recent: ~$392.78, down ~1.63% on the day) |
| 52-Week Range | $214.25 – $498.83 |
| 30-Day IV (mean) | ~43–50% |
| IV Rank | ~5.88 (low relative to the past year) |
| 50-Day MA | ~$428 |
| 200-Day MA | ~$418 |
| RSI (14-day) | ~41 (neutral, not oversold) |

**Key Technical Levels:**
- **Support:** $380–$385 (200-day MA vicinity, gamma wall at $400)
- **Resistance:** $410–$440 zone (supply area)
- **52-week low buffer:** The stock has rallied ~84% from its $214 low, providing some fundamental cushion.

**Macro Note:** TSLA has been in a broad consolidation/pullback from the $498 high. The RSI at 41 is neutral. The low IV rank (~6) means options are relatively cheap from a premium-selling standpoint, though selling premium remains viable when the spread is sized conservatively.

---

## 2. Target Expiration

**6 weeks from March 19, 2026 = April 30, 2026**

April 30, 2026 is a standard monthly expiration that should exist on the options chain. This gives approximately 42 days to expiration (DTE), which is within the standard 30–60 DTE window preferred for premium-selling strategies.

---

## 3. Recommended Bull Put Spread

### Trade Structure

| Leg | Action | Strike | Role |
|---|---|---|---|
| Short Put | Sell to Open | $355 | Defines max profit zone |
| Long Put | Buy to Open | $335 | Defines max loss / protection |
| Spread Width | — | $20 | Distance between strikes |

**Expiration:** April 30, 2026
**Contracts:** 1 (adjust to risk tolerance)

### Rationale for Strike Selection

- **Short $355 strike:** This is approximately 9–10% below the current price (~$392–$398). At ~9-10% OTM, the delta on the short put should be in the 0.15–0.20 range, providing a reasonable probability of expiring worthless. The $355 level also sits well below the $380–$385 support zone, providing an additional technical buffer — TSLA would need to break two significant support levels to threaten the short strike.
- **Long $335 strike:** $20 below the short strike, defining the max loss. This provides a defined risk structure limiting loss to the spread width minus the net credit.
- **$20-wide spread:** Balances capital efficiency (max loss = $2,000 per contract minus credit) against premium collected.

---

## 4. Estimated Option Premiums

Given TSLA's current IV of approximately 43–50% (30-day mean) and the stock trading ~$393, the following premium estimates are based on Black-Scholes approximation for April 30, 2026 expiry (~42 DTE):

| Parameter | Estimate |
|---|---|
| Short $355 Put premium (bid) | ~$7.50 – $9.50 |
| Long $335 Put premium (ask) | ~$3.50 – $5.00 |
| **Net Credit (midpoint estimate)** | **~$4.50 – $5.00** |

**Using a conservative net credit of $4.50 per share ($450 per contract):**

> Note: These are model-based estimates. Actual market prices will vary based on real-time bid/ask, skew, and liquidity. Always verify with live quotes before entering the trade.

---

## 5. Trade Metrics

| Metric | Value (1 Contract) |
|---|---|
| Net Credit Received | $450 (est.) |
| Max Profit | $450 (if TSLA closes above $355 at expiration) |
| Spread Width | $20.00 per share = $2,000 gross |
| Max Loss | $2,000 − $450 = **$1,550** |
| Breakeven Price | $355 − $4.50 = **$350.50** |
| Return on Risk | $450 / $1,550 = **~29%** |
| Annualized Return on Risk | ~29% × (365/42) ≈ **~252% annualized** |

---

## 6. Probability Analysis

With TSLA at ~$393 and the short put at $355:

| Metric | Estimate |
|---|---|
| Distance to Short Strike | ~$38 (approx. 9.7% below spot) |
| Estimated Short Put Delta | ~0.15–0.20 |
| Probability of Profit (approx.) | **~80–85%** |
| Probability Short Put ITM at expiry | ~15–20% |
| 1-Std-Dev Move (42 DTE, IV ~47%) | ±~$67 (from ~$393 → range ~$326–$460) |
| Short Strike vs. 1-SD Lower Bound | $355 is above the $326 1-SD downside |

> The $355 short strike sits comfortably within the 1-standard-deviation expected range, giving a theoretical probability of profit of ~80–85%. However, TSLA has an elevated historical volatility and news-event risk (earnings, macro), so this probability should be treated with caution.

---

## 7. Risk Flags

| Risk | Severity | Detail |
|---|---|---|
| **Low IV Environment** | Medium | IV Rank ~6 means premiums are relatively compressed; the $4.50 credit estimate may be optimistic — real premiums could be lower. |
| **RSI Neutral / Declining** | Medium | RSI ~41 does not confirm a bullish reversal; stock is in a short-term downtrend from $498 high. |
| **Price Below Key MAs** | High | TSLA is currently trading ~$393, below both the 50-day (~$428) and 200-day (~$418) moving averages. This is a bearish technical signal. |
| **Earnings Risk** | High | Verify whether Tesla has earnings scheduled before April 30. An earnings event within the trade window can cause gap moves that breach strike levels instantly. |
| **Elon Musk / Macro Headline Risk** | High | TSLA has historically experienced sharp moves on news. A 15–20% gap down would push the stock through both strikes. |
| **Breakeven at $350.50** | Medium | Only ~10.8% below current price. A moderate selloff could push the stock toward breakeven. |
| **Liquidity / Bid-Ask Spread** | Medium | At strikes far OTM, bid-ask spreads can be wide; actual fill may result in $3.50–$4.00 credit rather than $4.50 estimate. |

---

## 8. Trade Management Guidelines

| Scenario | Action |
|---|---|
| **Profit target reached (50% of max profit = $225)** | Close spread early; do not hold to expiration |
| **Loss reaches 2x credit ($900 loss)** | Exit spread to avoid full max loss |
| **TSLA breaks below $380 support** | Consider closing early or rolling down/out |
| **At expiration, TSLA > $355** | Allow to expire worthless; collect full credit |
| **At expiration, TSLA between $335–$355** | Close spread; realize partial loss |
| **At expiration, TSLA < $335** | Max loss realized; spread at full loss |

---

## 9. Alternative Strikes (More Conservative)

If the trader wants higher probability of profit and is concerned about the current downtrend:

| Variant | Short Strike | Long Strike | Est. Credit | Breakeven | POP |
|---|---|---|---|---|---|
| **Aggressive** | $370 | $350 | ~$7.00 | ~$363.00 | ~70% |
| **Recommended (Base Case)** | $355 | $335 | ~$4.50 | ~$350.50 | ~82% |
| **Conservative** | $340 | $320 | ~$2.50 | ~$337.50 | ~88% |
| **Ultra-Conservative** | $320 | $300 | ~$1.50 | ~$318.50 | ~93% |

Given the current bearish technical posture (below both major MAs), the **Conservative or Ultra-Conservative** variants may be more appropriate until TSLA re-establishes itself above the 200-day MA (~$418).

---

## 10. Summary Recommendation

| Field | Value |
|---|---|
| **Strategy** | Bull Put Spread |
| **Underlying** | TSLA (Tesla, Inc.) |
| **Sell** | 1x April 30, 2026 $355 Put |
| **Buy** | 1x April 30, 2026 $335 Put |
| **Net Credit** | ~$4.50/share (~$450/contract) |
| **Max Profit** | $450 per contract |
| **Max Loss** | $1,550 per contract |
| **Breakeven** | $350.50 |
| **Return on Risk** | ~29% |
| **Prob. of Profit** | ~80–85% |
| **DTE** | ~42 days |
| **Profit Target (close early)** | 50% of max credit = $225 gain |
| **Stop Loss** | 2x credit = $900 loss |

**Verdict:** The trade is mathematically viable with ~82% POP and a 29% return on risk. However, the bearish technical setup (below 50- and 200-day MAs, declining from $498 peak) introduces meaningful directional risk. The recommended approach is to use the conservative $340/$320 variant or to wait for TSLA to reclaim the 200-day MA (~$418) before entering the base-case $355/$335 spread.

---

## Sources

- [TSLA Stock Price — TradingView](https://www.tradingview.com/symbols/NASDAQ-TSLA/)
- [Tesla, Inc. (TSLA) Stock Price — Nasdaq](https://www.nasdaq.com/market-activity/stocks/tsla)
- [TSLA Options Chain — Nasdaq](https://www.nasdaq.com/market-activity/stocks/tsla/option-chain)
- [TSLA Bull Put Spread — Barchart.com](https://www.barchart.com/stocks/quotes/TSLA/vertical-spreads/bull-put-spread)
- [TSLA Implied Volatility — MarketChameleon](https://marketchameleon.com/Overview/TSLA/IV/)
- [TSLA Technical Analysis — Investing.com](https://www.investing.com/equities/tesla-motors-technical)
- [TSLA Expected Move — Barchart.com](https://www.barchart.com/stocks/quotes/TSLA/expected-move)
- [TSLA Volatility — Unusual Whales](https://unusualwhales.com/stock/TSLA/volatility)
- [Tesla (TSLA) Options — MarketBeat](https://www.marketbeat.com/stocks/NASDAQ/TSLA/options/)

---

*Disclaimer: This is an educational analysis only, not financial advice. Options trading involves substantial risk. Always verify live option prices before placing any trade.*
