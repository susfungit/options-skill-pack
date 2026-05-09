# Evening Brief JSON Schema

This is what `write_evening.py` validates and what gets persisted at `morning-briefs/YYYY-MM-DD-evening.json`. Construct a single JSON object matching this schema exactly.

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
