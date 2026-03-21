## Bull Put Spread Monitor — Position Check

**Position:** NVDA 155/140 Bull Put Spread
**Original credit:** $1.98/share
**Expiry:** 2026-05-01
**Data source:** yfinance (live market data)
**Checked on:** 2026-03-21

---

```
╔══════════════════════════════════════════════╗
║  SPREAD MONITOR — NVDA                       ║
║  155/140 Put  ·  2026-05-01                  ║
╠══════════════════════════════════════════════╣
║  Status:  🟢 SAFE ZONE                       ║
╠══════════════════════════════════════════════╣
║  Stock now:     $172.70                      ║
║  Short strike:  $155.00  (buffer: 10.25%)    ║
║  Breakeven:     $153.02  (buffer: 11.40%)    ║
║  DTE remaining: 41 days                      ║
╠══════════════════════════════════════════════╣
║  Current P&L:   $0.00  per contract          ║
║  Loss % of max: 0.0%  of $1,302.00           ║
║  Cost to close: $1.98  per share             ║
╚══════════════════════════════════════════════╝
```

### Assessment

This position is firmly in the **Safe Zone** on both signals: NVDA is trading at $172.70, sitting **10.25% above the $155 short strike** — well beyond the 8% threshold required for SAFE, and the DTE-adjusted leniency at 41 days only further supports that classification. The loss percentage is 0.0% of the $1,302 max loss, meaning the spread has not deteriorated in value at all since entry (the current spread value of $1.98 exactly matches the original credit received).

The position needs NVDA to stay above $153.02 (the breakeven) through May 1 to keep any profit, and above $155 to avoid the short put moving into the money. With 41 days remaining and a 10.25% cushion to the short strike, theta decay is working in your favor.

**Suggested action:** No action needed — let theta work. The spread currently has $0.00 of realized P&L, meaning all $198 of max profit per contract is still available to be captured through time decay. Monitor again in 1–2 weeks or if NVDA drops toward the $165–$160 range. Consider setting a price alert at $160 to prompt a reassessment.
