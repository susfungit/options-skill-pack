The `check_position.py` script ran successfully and returned live data via yfinance.

**Raw data from script:**
- Stock price: $247.99
- Short put ($185) mid: $0.71 | Long put ($170) mid: $0.14
- Current spread value: $0.57 (cost to close)
- P&L per contract: +$153.00
- Buffer above short strike: 25.4%
- Buffer above breakeven ($182.90): 26.25%
- DTE: 41 days
- Loss % of max: 0.0%

**Zone classification:** Both signals (buffer = 25.4%, loss% = 0.0%) place this firmly in SAFE ZONE.

---

```
╔══════════════════════════════════════════════╗
║  SPREAD MONITOR — AAPL                       ║
║  185/170 Put  ·  2026-05-01                  ║
╠══════════════════════════════════════════════╣
║  Status:  🟢 SAFE ZONE                       ║
╠══════════════════════════════════════════════╣
║  Stock now:     $247.99                      ║
║  Short strike:  $185.00  (buffer: 25.4%)     ║
║  Breakeven:     $182.90  (buffer: 26.25%)    ║
║  DTE remaining: 41 days                      ║
╠══════════════════════════════════════════════╣
║  Current P&L:   +$153.00  per contract       ║
║  Loss % of max: 0.0%  of $1,290.00           ║
║  Cost to close: $0.57  per share             ║
╚══════════════════════════════════════════════╝
```

**Zone assigned: SAFE ZONE** — Both signals are firmly in safe territory. AAPL is trading at $247.99, sitting 25.4% above your $185 short strike and 26.25% above your $182.90 breakeven. The spread has decayed from your original $2.10 credit down to $0.57, meaning you've already locked in $1.53 per share ($153 per contract) — roughly 72.9% of your maximum possible profit of $210 per contract — with 41 days still remaining.

**What the position needs to stay on track:** AAPL would need to fall roughly $63 (about 25%) before your short strike comes into play. With 41 DTE and the stock this far out of range, the main risk is a sharp, unexpected gap down — not gradual drift.

**Suggested action:** No action needed — let theta continue working for you. At $0.57 to close, you could take profits early and eliminate all risk for a cost of $57 per contract (keeping $153 of the original $210 credit). A reasonable rule of thumb: consider closing early if the spread decays to 10–15 cents (capturing 90%+ of max profit), or set a mental stop if AAPL were to drop below $210 and re-evaluate at that point.
