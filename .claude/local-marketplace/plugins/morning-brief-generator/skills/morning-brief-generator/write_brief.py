"""Persist helper for morning-brief-generator.

Reads a brief JSON object from stdin, validates it against the schema,
and writes:
  1. morning-briefs/YYYY-MM-DD.json  (full brief output)
  2. morning-briefs/recommendations.json  (rolling index — appends new
     recommendations and merges carry-forward review status updates)

Schema (minimum required fields):
{
  "brief_date": "YYYY-MM-DD",
  "brief_version": "v3.4",
  "brief_volume": int,
  "market_snapshot": {...},          # free-form, but must include timestamp
  "quote_table": [                    # Step 0 Part E — REQUIRED, non-empty
    {"ticker": str, "live_price": float, "timestamp": str, "source": str}
  ],
  "recommendations": [                # zero or more new trades
    {
      "id": "YYYY-MM-DD-TICKER-NN",
      "date_recommended": "YYYY-MM-DD",
      "ticker": str,
      "strategy": str,
      "conviction": "HIGH" | "MEDIUM" | "LOW",
      "live_price_at_recommendation": float,
      "price_source": str,
      "price_timestamp": str,
      "legs": [
        {"action": "buy"|"sell", "type": "put"|"call", "strike": float, "expiry": "YYYY-MM-DD"}
      ],
      "expiry_date": "YYYY-MM-DD",
      "dte_at_entry": int,
      "estimated_credit": float | null,
      "estimated_debit": float | null,
      "max_profit": float,
      "max_loss": float,
      "break_even": float | list[float],
      "thesis": str,
      "key_risk": str,
      "catalyst": str,
      "section": str,                  # "high_conviction"|"implied_move"|"index"|"crypto_equity"|"squeeze"
      "status": "open"
    }
  ],
  "carry_forward_reviewed": [        # zero or more updates to existing recs
    {
      "id": "YYYY-MM-DD-TICKER-NN",
      "action_today": "HOLD"|"CLOSE_HALF"|"CLOSE_FULL"|"ROLL"|"ADJUST_STRIKE",
      "current_stock_price": float,
      "current_pnl_pct": float | null,
      "notes": str
    }
  ]
}

Rules enforced:
  • quote_table must be non-empty
  • every recommendation's ticker must appear in quote_table (Step 4 gate)
  • every recommendation must have a price_source (Step 6 #12 gate)
  • every recommendation must have dte_at_entry >= 7 (or be flagged
    short_dte_exception=true)

Usage:
    python3 write_brief.py < brief.json
    cat brief.json | python3 write_brief.py --output-dir morning-briefs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_BRIEF_KEYS = {"brief_date", "brief_version", "quote_table", "recommendations"}
REQUIRED_REC_KEYS = {
    "id",
    "date_recommended",
    "ticker",
    "strategy",
    "conviction",
    "live_price_at_recommendation",
    "price_source",
    "expiry_date",
    "dte_at_entry",
    "max_profit",
    "max_loss",
    "break_even",
    "thesis",
    "status",
}


def _validate(brief: dict) -> list[str]:
    errs: list[str] = []
    missing = REQUIRED_BRIEF_KEYS - set(brief)
    if missing:
        errs.append(f"brief missing keys: {sorted(missing)}")

    qt = brief.get("quote_table") or []
    if not qt:
        errs.append("quote_table is empty — Step 0 Part E gate failed")
    quote_tickers = {row.get("ticker") for row in qt if isinstance(row, dict)}

    for i, rec in enumerate(brief.get("recommendations", []) or []):
        rmissing = REQUIRED_REC_KEYS - set(rec)
        if rmissing:
            errs.append(f"rec[{i}] missing keys: {sorted(rmissing)}")
            continue
        if rec["ticker"] not in quote_tickers:
            errs.append(
                f"rec[{i}] ticker {rec['ticker']!r} not in quote_table — Step 4 gate failed"
            )
        if not rec.get("price_source"):
            errs.append(f"rec[{i}] missing price_source — Step 6 #12 gate failed")
        dte = rec.get("dte_at_entry", 0)
        if dte < 7 and not rec.get("short_dte_exception"):
            errs.append(
                f"rec[{i}] dte_at_entry={dte} < 7 and short_dte_exception not set"
            )
    return errs


def _merge_recommendations(
    existing: list[dict], new: list[dict], updates: list[dict]
) -> list[dict]:
    by_id = {r["id"]: r for r in existing if "id" in r}

    for rec in new:
        if rec["id"] in by_id:
            sys.stderr.write(f"warning: rec id {rec['id']} already exists — skipping insert\n")
            continue
        by_id[rec["id"]] = rec

    for upd in updates:
        rid = upd.get("id")
        if not rid or rid not in by_id:
            sys.stderr.write(f"warning: carry_forward review for unknown id {rid!r} — skipping\n")
            continue
        existing_rec = by_id[rid]
        existing_rec.setdefault("reviews", []).append(
            {
                "review_date": upd.get("review_date"),
                "action_today": upd.get("action_today"),
                "current_stock_price": upd.get("current_stock_price"),
                "current_pnl_pct": upd.get("current_pnl_pct"),
                "notes": upd.get("notes"),
            }
        )
        if upd.get("action_today") in {"CLOSE_FULL", "ROLL"}:
            existing_rec["status"] = "closed" if upd["action_today"] == "CLOSE_FULL" else "rolled"

    return list(by_id.values())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="morning-briefs")
    p.add_argument(
        "--allow-validation-errors",
        action="store_true",
        help="Write even if validation fails. Default: refuse (Step 0 Part E gate).",
    )
    args = p.parse_args()

    raw = sys.stdin.read()
    try:
        brief = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"invalid JSON on stdin: {e}\n")
        return 2

    errs = _validate(brief)
    if errs and not args.allow_validation_errors:
        sys.stderr.write("validation failed:\n  - " + "\n  - ".join(errs) + "\n")
        sys.stderr.write("brief NOT written. Fix the issues or pass --allow-validation-errors.\n")
        return 3

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    brief_path = out_dir / f"{brief['brief_date']}.json"
    brief_path.write_text(json.dumps(brief, indent=2))

    recs_path = out_dir / "recommendations.json"
    if recs_path.exists():
        try:
            existing = json.loads(recs_path.read_text()).get("recommendations", [])
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []

    review_date = brief["brief_date"]
    updates = []
    for upd in brief.get("carry_forward_reviewed", []) or []:
        upd = dict(upd)
        upd.setdefault("review_date", review_date)
        updates.append(upd)

    merged = _merge_recommendations(
        existing, brief.get("recommendations", []) or [], updates
    )
    recs_path.write_text(
        json.dumps({"recommendations": merged}, indent=2)
    )

    print(
        json.dumps(
            {
                "ok": True,
                "brief_path": str(brief_path),
                "recommendations_path": str(recs_path),
                "new_recommendations": len(brief.get("recommendations", []) or []),
                "carry_forward_reviewed": len(updates),
                "validation_warnings": errs if args.allow_validation_errors else [],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
