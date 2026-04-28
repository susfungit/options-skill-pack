"""Persist helper for evening-brief-reviewer.

Reads an evening review JSON object from stdin and writes:
  1. morning-briefs/YYYY-MM-DD-evening.json  (full review)
  2. Updates each scored recommendation in morning-briefs/recommendations.json
     with an evening_review block (and updates status if outcome warrants it)
  3. Appends new prompt-change proposals to morning-briefs/prompt_change_proposals.json
     and computes recurrence count (how many times the same proposal has appeared
     across briefs in the last 14 days) — useful for the 3+ threshold rule

Schema (minimum required):
{
  "review_date": "YYYY-MM-DD",
  "morning_brief_volume": int,
  "eod_quote_table": [                  # REQUIRED, non-empty
    {"ticker": str, "eod_price": float, "timestamp": str, "source": str}
  ],
  "scored_recommendations": [           # one per recommendation reviewed
    {
      "id": "YYYY-MM-DD-TICKER-NN",
      "eod_price": float,
      "estimated_pnl_pct": float | null,
      "estimated_pnl_dollars": float | null,
      "outcome": "working" | "neutral" | "not_working" | "thesis_broken",
      "partial_review": bool,            # true when catalyst not yet resolved (e.g. AMC earnings)
      "thesis_check": str,
      "lesson": str | null,
      "diagnosis_category": "data_error" | "process_error" | "judgment_error" | "bad_luck" | null,
      "status_update": "open" | "closed" | "rolled" | "expired" | null
    }
  ],
  "prompt_change_proposals": [          # zero or more
    {
      "category": "data_error" | "process_error",
      "summary": str,                    # one-line proposal title (used for recurrence matching)
      "rationale": str,
      "proposed_change": str,            # concrete change to v3.4 prompt
      "triggered_by_recommendation_ids": [str]
    }
  ],
  "meta_review": str,                    # one paragraph summary of the day
  "tomorrow_focus": str                  # one paragraph — what tomorrow's brief should pay attention to
}

Rules enforced:
  • eod_quote_table non-empty (same anti-fabrication discipline as morning)
  • every scored_recommendation's id must exist in recommendations.json
  • diagnosis_category required when outcome is not_working or thesis_broken
  • prompt_change_proposals only created from data_error or process_error categories

Usage:
    python3 write_evening.py < evening.json
    cat evening.json | python3 write_evening.py --output-dir morning-briefs
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


REQUIRED_TOP = {"review_date", "eod_quote_table", "scored_recommendations"}
REQUIRED_SCORE = {"id", "eod_price", "outcome"}


def _validate(review: dict, existing_recs: list[dict]) -> list[str]:
    errs: list[str] = []
    missing = REQUIRED_TOP - set(review)
    if missing:
        errs.append(f"review missing keys: {sorted(missing)}")

    qt = review.get("eod_quote_table") or []
    if not qt:
        errs.append("eod_quote_table empty — anti-fabrication gate failed")

    existing_ids = {r.get("id") for r in existing_recs if r.get("id")}
    for i, s in enumerate(review.get("scored_recommendations") or []):
        smissing = REQUIRED_SCORE - set(s)
        if smissing:
            errs.append(f"scored_recommendations[{i}] missing keys: {sorted(smissing)}")
            continue
        if s["id"] not in existing_ids:
            errs.append(
                f"scored_recommendations[{i}] id {s['id']!r} not found in recommendations.json"
            )
        if s["outcome"] in {"not_working", "thesis_broken"} and not s.get("diagnosis_category"):
            errs.append(
                f"scored_recommendations[{i}] outcome={s['outcome']!r} but diagnosis_category missing"
            )

    for i, p in enumerate(review.get("prompt_change_proposals") or []):
        if p.get("category") not in {"data_error", "process_error"}:
            errs.append(
                f"prompt_change_proposals[{i}] category {p.get('category')!r} — only "
                "data_error or process_error may produce a proposal"
            )
        if not p.get("summary") or not p.get("proposed_change"):
            errs.append(f"prompt_change_proposals[{i}] missing summary or proposed_change")
    return errs


def _merge_into_recommendations(
    existing: list[dict], scored: list[dict], review_date: str
) -> list[dict]:
    by_id = {r["id"]: r for r in existing if "id" in r}
    for s in scored:
        rid = s.get("id")
        if rid not in by_id:
            sys.stderr.write(f"warning: scored id {rid!r} not in index — skipping\n")
            continue
        rec = by_id[rid]
        rec.setdefault("evening_reviews", []).append(
            {
                "review_date": review_date,
                "eod_price": s.get("eod_price"),
                "estimated_pnl_pct": s.get("estimated_pnl_pct"),
                "estimated_pnl_dollars": s.get("estimated_pnl_dollars"),
                "outcome": s.get("outcome"),
                "partial_review": s.get("partial_review", False),
                "thesis_check": s.get("thesis_check"),
                "lesson": s.get("lesson"),
                "diagnosis_category": s.get("diagnosis_category"),
            }
        )
        new_status = s.get("status_update")
        if new_status and new_status in {"closed", "rolled", "expired"}:
            rec["status"] = new_status
    return list(by_id.values())


def _append_proposals(
    existing_proposals: list[dict], new_proposals: list[dict], review_date: str
) -> tuple[list[dict], list[dict]]:
    """Returns (updated_index, proposals_with_recurrence_counts).

    Recurrence count = number of times a proposal with the same `summary`
    (case-insensitive, whitespace-trimmed) has appeared in the last 14 days
    INCLUDING the new one being added.
    """
    cutoff = (datetime.fromisoformat(review_date) - timedelta(days=14)).date().isoformat()

    def _norm(s: str) -> str:
        return " ".join(s.lower().split())

    enriched: list[dict] = []
    for p in new_proposals:
        entry = dict(p)
        entry["date"] = review_date
        existing_proposals.append(entry)
        norm_summary = _norm(p.get("summary", ""))
        recurrence = sum(
            1
            for q in existing_proposals
            if q.get("date", "") >= cutoff and _norm(q.get("summary", "")) == norm_summary
        )
        entry["recurrence_count_14d"] = recurrence
        entry["action_threshold_met"] = recurrence >= 3
        enriched.append(entry)
    return existing_proposals, enriched


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="morning-briefs")
    p.add_argument(
        "--allow-validation-errors",
        action="store_true",
        help="Write even if validation fails. Default: refuse.",
    )
    args = p.parse_args()

    raw = sys.stdin.read()
    try:
        review = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"invalid JSON on stdin: {e}\n")
        return 2

    out_dir = Path(args.output_dir).resolve()
    if not out_dir.exists():
        sys.stderr.write(f"output dir {out_dir} does not exist\n")
        return 4

    recs_path = out_dir / "recommendations.json"
    if not recs_path.exists():
        sys.stderr.write(
            f"recommendations.json not found at {recs_path} — morning brief never ran\n"
        )
        return 5

    existing_recs = json.loads(recs_path.read_text()).get("recommendations", [])
    errs = _validate(review, existing_recs)
    if errs and not args.allow_validation_errors:
        sys.stderr.write("validation failed:\n  - " + "\n  - ".join(errs) + "\n")
        sys.stderr.write("review NOT written.\n")
        return 3

    review_date = review["review_date"]

    evening_path = out_dir / f"{review_date}-evening.json"
    evening_path.write_text(json.dumps(review, indent=2))

    merged_recs = _merge_into_recommendations(
        existing_recs, review.get("scored_recommendations", []) or [], review_date
    )
    recs_path.write_text(json.dumps({"recommendations": merged_recs}, indent=2))

    proposals_path = out_dir / "prompt_change_proposals.json"
    if proposals_path.exists():
        existing_proposals = json.loads(proposals_path.read_text()).get("proposals", [])
    else:
        existing_proposals = []

    updated_proposals, enriched_new = _append_proposals(
        existing_proposals, review.get("prompt_change_proposals", []) or [], review_date
    )
    proposals_path.write_text(json.dumps({"proposals": updated_proposals}, indent=2))

    print(
        json.dumps(
            {
                "ok": True,
                "evening_path": str(evening_path),
                "recommendations_path": str(recs_path),
                "proposals_path": str(proposals_path),
                "scored_count": len(review.get("scored_recommendations", []) or []),
                "new_proposals": enriched_new,
                "validation_warnings": errs if args.allow_validation_errors else [],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
