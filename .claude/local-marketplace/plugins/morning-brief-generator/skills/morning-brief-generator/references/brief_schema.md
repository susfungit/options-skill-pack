# Morning Brief JSON Schema (v3.4)

This schema is what `write_brief.py` validates and what the evening reviewer reads tomorrow. Every field, every type, every comment-as-rule is mandatory. Construct a single JSON object matching this schema exactly.

```jsonc
{
  "brief_date": "YYYY-MM-DD",            // from Step 0
  "brief_version": "v3.4",
  "brief_volume": 42,                     // from Step 0
  "generated_at_et": "HH:MM ET",
  "minutes_until_market_open": 45,        // null on closed days
  "market_status": "open",                // open | closed_weekend | closed_holiday | early_close
  "market_status_detail": null,           // e.g. "Saturday" or "Memorial Day"
  "last_trading_day": "2026-04-24",       // date string

  "market_snapshot": {                    // Section 1
    "timestamp_et": "HH:MM ET",
    "spx_futures":  {"level": 5234.5, "pct": -0.41},
    "ndx_futures":  {"level": 18234.0, "pct": -0.55},
    "dow_futures":  {"level": 39812.0, "pct": -0.30},
    "vix":          {"level": 16.4, "direction": "rising"},
    "wti_crude":    {"price": 78.20, "pct": 1.1},
    "brent_crude":  {"price": 82.10, "pct": 0.9},
    "gold_futures": {"price": 2345.0, "pct": 0.2},
    "ten_year_yield": 4.36,
    "dxy":          104.21,
    "btc":          {"price": 67200, "pct_24h": -1.2},
    "eth":          {"price": 3415, "pct_24h": -0.8}
  },

  "reversal_alert": null,                 // Section 2 — null OR { "summary": str, "details": str }
  "binary_resolutions": [],               // resolved binaries from Step 3 — { "event": str, "status": "resolved"|"extended"|"canceled", "detail": str }

  "quote_table": [                        // Section "Sourced Live Quotes" + Step 1 Part E
    {
      "ticker": "TSLA",
      "live_price": 376.38,
      "timestamp": "07:30 ET",
      "source": "search: TSLA pre-market 2026-04-25"
    }
  ],

  "carry_forward_reviewed": [             // Section 3 — one entry per open prior recommendation
    {
      "id": "2026-04-23-IBM-01",          // matches id from prior brief in recommendations.json
      "current_stock_price": 240.10,
      "current_pnl_pct": 32,
      "strikes_status": "Stock $240 above $235 short put — both put legs OTM",
      "days_since_entry": 2,
      "dte_remaining": 21,
      "action_today": "HOLD",             // HOLD | CLOSE_HALF | CLOSE_FULL | ROLL | ADJUST_STRIKE
      "trigger_for_close": "Close half at 50% of max profit",
      "notes": ""
    }
  ],

  "recommendations": [                    // Section 4 + 5 + 6 + 8 (any new trade)
    {
      "id": "YYYY-MM-DD-TICKER-NN",       // unique; date + ticker + sequence
      "date_recommended": "YYYY-MM-DD",
      "ticker": "TSLA",
      "section": "high_conviction",       // high_conviction | implied_move | index | crypto_equity | squeeze
      "catalyst": "Q1 deliveries beat",
      "thesis": "...",
      "iv_environment": "Elevated (estimated)",
      "directional_bias": "bullish",
      "strategy": "bull_put_spread",      // snake_case
      "conviction": "HIGH",                // HIGH | MEDIUM | LOW
      "live_price_at_recommendation": 376.38,
      "price_source": "search: TSLA pre-market 2026-04-25",
      "price_timestamp": "07:30 ET",
      "legs": [
        {"action": "sell", "type": "put", "strike": 360, "expiry": "2026-05-16"},
        {"action": "buy",  "type": "put", "strike": 350, "expiry": "2026-05-16"}
      ],
      "expiry_date": "2026-05-16",
      "dte_at_entry": 21,
      "short_dte_exception": false,
      "spread_width": 10,
      "estimated_credit": 1.85,
      "estimated_debit": null,
      "max_profit": 185,                   // per contract, in dollars
      "max_loss": 815,
      "break_even": 358.15,                // number OR [low, high] for condor / straddle
      "stock_vs_strikes": "Stock $376.38 sits $16.38 above $360 short put — full credit at expiry if held above $360",
      "key_risk": "TSLA closes below $360 by 2026-05-16",
      "step6_citation": "Live price $376.38 from search 'TSLA pre-market 2026-04-25' at 07:30 ET, confirmed in quote_table",
      "status": "open"
    }
  ],

  "implied_move_watch": [                 // Section 5 — table rows
    {"ticker": "MSFT", "report_date": "2026-04-29", "report_timing": "AMC", "implied_move_pct": 4.2,
     "thesis": "...", "strategy_idea": "post-earnings put credit spread", "dte": 14, "conviction": "MEDIUM"}
  ],

  "index_read": {                         // Section 6
    "spy": {"price": 711.0, "support": 705, "resistance": 720, "tag": "complacent", "trade_idea": "..."},
    "qqq": {"price": 656.0, "support": 648, "resistance": 670, "tag": "neutral",    "trade_idea": "..."},
    "iwm": {"price": 276.0, "support": 270, "resistance": 285, "tag": "fearful",    "trade_idea": "..."}
  },

  "valuation_screen": [],                 // Section 7 — earnings-week names with P/E > 100, OR empty array
  "valuation_screen_note": "No qualifying names this week.",

  "crypto_equities": {                    // Section 8
    "trigger_state": "no_trigger",        // full_fire | pre_staged | no_trigger
    "btc_pct_24h": -1.2,
    "eth_pct_24h": -0.8,
    "note": "BTC -1.2% / ETH -0.8% — within normal range. No correlated-equity setup triggered."
  },

  "unusual_activity": [],                 // Section 9
  "meta_signal": "Mild risk-off into the open ...",  // Section 10
  "missed_catalyst_watch": []              // Section 11
}
```
