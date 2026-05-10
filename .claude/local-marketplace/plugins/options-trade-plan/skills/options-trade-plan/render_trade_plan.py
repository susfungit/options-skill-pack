#!/usr/bin/env python3
"""Stitch the final options-trade-plan HTML from three inputs:

  --data       JSON from `fetch_trade_plan_data.py` (stdout, slim mode)
  --fragments  JSON written by `fetch_trade_plan_data.py --fragments-out`
  --prose      JSON authored by the model with the 13 narrative keys
  --out        directory to write the final HTML into (e.g. trade-plans/)

Performs `{{TOKEN}}` substitution and `<!-- MODEL_SLOT:* --><p>[...]</p>`
replacement using assets/template.html (loaded from beside this script
unless overridden with --template). Validates that no template tokens or
slot markers remain. Writes `trade_plan_{TICKER}_{EXPIRY}.html` and prints
its path to stdout.

This script exists to keep finished HTML out of the model's output stream:
the model only writes the small prose JSON; this renderer does the bulky
substitution deterministically.
"""

import argparse
import json
import re
import sys
from pathlib import Path


_FRAGMENT_TOKENS = {
    "TICKER": "ticker",
    "STRATEGY_LABEL": "strategy_label",
    "EXPIRY": "expiry",
    "DTE": "dte",
    "PUB_DATE": "pub_date",
    "EXPIRY_RESOLUTION": "expiry_resolution",
    "SPOT": "spot",
    "CHG_PCT": "chg_pct",
    "IV": "iv",
    "HV": "hv",
    "IV_HV_RATIO": "iv_hv_ratio",
    "IV_RANK": "iv_rank",
    "MAX_PAIN": "max_pain",
    "EARNINGS_LINE": "earnings_line",
    "EXPECTED_MOVE": "expected_move",
    "IV_VERDICT": "iv_verdict",
    "LEVELS_ROWS_HTML": "levels_rows_html",
    "TRADE_SUMMARY_ROWS_HTML": "trade_summary_rows_html",
    "BULL_PUT_CARD_HTML": "bull_put_card_html",
    "CONDOR_CARD_HTML": "condor_card_html",
    "BEAR_CALL_CARD_HTML": "bear_call_card_html",
    "FLOWCHART_HTML": "flowchart_html",
    "VOL_BARS_HTML": "vol_bars_html",
    "POSITIONING_HTML": "positioning_html",
    "SIZING_ROWS_HTML": "sizing_rows_html",
}

_PROSE_TOKENS = {
    "EXEC_SUMMARY_HTML": "exec_summary_html",
    "CONTEXT_HTML": "context_html",
    "EARNINGS_HTML": "earnings_html",
    "SOURCES_HTML": "sources_html",
}

_PROSE_SLOTS = (
    "bull_put_rationale", "bull_put_entry_trigger", "bull_put_stop_rule",
    "iron_condor_rationale", "iron_condor_entry_trigger", "iron_condor_stop_rule",
    "bear_call_rationale", "bear_call_entry_trigger", "bear_call_stop_rule",
)

_SLOT_RE = re.compile(r"<!-- MODEL_SLOT:(\w+) --><p>\[[^\]]*\]</p>")
_TOKEN_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def render(fragments: dict, prose: dict, template: str) -> str:
    html = template

    for token, key in _FRAGMENT_TOKENS.items():
        if key not in fragments:
            raise KeyError(f"fragments missing key {key!r} (for {{{{{token}}}}})")
        html = html.replace("{{" + token + "}}", str(fragments[key]))

    if "chart_config_json" not in fragments:
        raise KeyError("fragments missing key 'chart_config_json'")
    html = html.replace(
        "{{CHART_CONFIG_JSON}}",
        json.dumps(fragments["chart_config_json"]),
    )

    for token, key in _PROSE_TOKENS.items():
        if key not in prose:
            raise KeyError(f"prose missing key {key!r} (for {{{{{token}}}}})")
        html = html.replace("{{" + token + "}}", str(prose[key]))

    def _slot_sub(match):
        name = match.group(1)
        if name not in prose:
            raise KeyError(f"prose missing slot {name!r}")
        return str(prose[name])

    html = _SLOT_RE.sub(_slot_sub, html)

    leftover = sorted(set(_TOKEN_RE.findall(html)))
    if leftover:
        raise ValueError(f"unsubstituted template tokens: {leftover}")
    if "MODEL_SLOT" in html:
        raise ValueError("MODEL_SLOT markers remain after substitution")

    return html


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--fragments", required=True)
    ap.add_argument("--prose", required=True)
    ap.add_argument("--out", required=True, help="output directory (e.g. trade-plans/)")
    ap.add_argument("--template", default=None,
                    help="path to template.html (default: assets/template.html beside this script)")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text())
    fragments = json.loads(Path(args.fragments).read_text())
    prose = json.loads(Path(args.prose).read_text())

    missing = [k for k in list(_PROSE_TOKENS.values()) + list(_PROSE_SLOTS) if k not in prose]
    if missing:
        sys.exit(f"prose JSON missing keys: {missing}")

    template_path = Path(args.template) if args.template else Path(__file__).parent / "assets" / "template.html"
    template = template_path.read_text()

    html = render(fragments, prose, template)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"trade_plan_{_safe(data.get('ticker', 'UNKNOWN'))}_{_safe(data.get('expiry', 'unknown'))}.html"
    out_path.write_text(html)
    print(str(out_path))


if __name__ == "__main__":
    main()
