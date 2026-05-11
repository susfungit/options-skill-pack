"""Render the evening-brief HTML from a persisted evening JSON.

The JSON schema is documented in references/evening_schema.md. This
renderer owns the layout spec (formerly references/evening_html_spec.md);
the LLM no longer generates markup, only narrative content
(thesis_check, lesson, meta_review, tomorrow_focus, optional
highlight_strip_text).

Usage:
    python3 render_evening_html.py --input 2026-05-11-evening.json \\
                                   --output 2026-05-11-evening.html

If --output is omitted, the HTML is written to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path


# ── Strategy display helpers ─────────────────────────────────────────────────

_STRATEGY_LABEL = {
    "bull_put_spread": "Bull Put Spread",
    "bear_call_spread": "Bear Call Spread",
    "cash_secured_put": "Cash-Secured Put",
    "covered_call": "Covered Call",
    "iron_condor": "Iron Condor",
}


def _format_legs(strategy: str, legs: list[dict]) -> str:
    if not legs:
        return "—"
    if strategy in ("cash_secured_put", "covered_call"):
        return f"${legs[0].get('strike')}"
    if strategy == "iron_condor":
        # Try to identify the put spread and call spread by leg type.
        puts = sorted([l for l in legs if l.get("type") == "put"], key=lambda l: -l.get("strike", 0))
        calls = sorted([l for l in legs if l.get("type") == "call"], key=lambda l: l.get("strike", 0))
        if len(puts) >= 2 and len(calls) >= 2:
            return f"${puts[0]['strike']}/${puts[1]['strike']} · ${calls[0]['strike']}/${calls[1]['strike']}"
    # Default vertical spread display: sell_strike / buy_strike
    sell = next((l for l in legs if l.get("action") == "sell"), legs[0])
    buy = next((l for l in legs if l.get("action") == "buy"), None)
    if buy is None:
        return f"${sell.get('strike')}"
    return f"${sell.get('strike')}/${buy.get('strike')}"


def _short_strike(strategy: str, legs: list[dict]) -> float | None:
    """The strike whose buffer matters most for risk display."""
    if strategy in ("bull_put_spread", "cash_secured_put"):
        puts = [l for l in legs if l.get("action") == "sell" and l.get("type") == "put"]
        return max((p.get("strike") for p in puts), default=None)
    if strategy in ("bear_call_spread", "covered_call"):
        calls = [l for l in legs if l.get("action") == "sell" and l.get("type") == "call"]
        return min((c.get("strike") for c in calls), default=None)
    if strategy == "iron_condor":
        # Pick the closer-to-money short — return the put short by convention.
        puts = [l for l in legs if l.get("action") == "sell" and l.get("type") == "put"]
        return max((p.get("strike") for p in puts), default=None)
    return None


def _format_expiry(expiry: str) -> str:
    try:
        d = datetime.strptime(expiry, "%Y-%m-%d").date()
        return d.strftime("%b %-d Expiry")
    except (ValueError, TypeError):
        return expiry or ""


def _days_between(start_iso: str, end_iso: str) -> int | None:
    try:
        a = datetime.strptime(start_iso, "%Y-%m-%d").date()
        b = datetime.strptime(end_iso, "%Y-%m-%d").date()
        return (b - a).days
    except (ValueError, TypeError):
        return None


# ── Sign / change formatting ─────────────────────────────────────────────────


def _chg_class(pct: float | None) -> str:
    if pct is None:
        return "flat"
    if pct > 0.05:
        return "up"
    if pct < -0.05:
        return "down"
    return "flat"


def _chg_glyph(pct: float | None) -> str:
    if pct is None:
        return "▬"
    if pct > 0.05:
        return "▲"
    if pct < -0.05:
        return "▼"
    return "▬"


def _chg_str(pct: float | None) -> str:
    if pct is None:
        return "—"
    return f"{_chg_glyph(pct)} {abs(pct):.2f}%"


def _qt_chg_class(pct: float | None) -> str:
    if pct is None:
        return "chg-flat"
    if pct > 0.05:
        return "chg-up"
    if pct < -0.05:
        return "chg-dn"
    return "chg-flat"


def _money_class(amount: float | None) -> str:
    if amount is None:
        return "flat"
    if amount > 0:
        return "pos"
    if amount < 0:
        return "neg"
    return "flat"


# ── Section renderers ────────────────────────────────────────────────────────


def _masthead(evening: dict) -> str:
    review_date = evening["review_date"]
    d = datetime.strptime(review_date, "%Y-%m-%d").date()
    long_date = d.strftime("%B %-d, %Y")
    day_name = d.strftime("%A")
    vol = evening.get("morning_brief_volume", "—")
    return f"""<div class="masthead">
  <div class="masthead-kicker">Options Intelligence · Evening Edition</div>
  <div class="masthead-title">Evening Review</div>
  <div class="masthead-sub">EVENING REVIEW &nbsp;·&nbsp; {day_name} Edition &nbsp;·&nbsp; {long_date} &nbsp;·&nbsp; Vol. {vol}</div>
</div>"""


def _ticker_bar(evening: dict) -> str:
    rows = evening.get("eod_quote_table", [])
    items = []
    for q in rows:
        sym = escape(q["ticker"])
        price = q["eod_price"]
        pct = q.get("change_pct")
        cls = _chg_class(pct)
        items.append(
            f'  <div class="ticker-item"><span class="ticker-sym">{sym}</span>'
            f'<span class="ticker-price">${price}</span>'
            f'<span class="ticker-chg {cls}">{_chg_str(pct)}</span></div>'
        )
    return '<div class="ticker-bar">\n' + "\n".join(items) + "\n</div>"


def _highlight_strip(evening: dict) -> str:
    text = evening.get("highlight_strip_text")
    if not text:
        return ""
    return f'<div class="highlight-strip">{text}</div>'


def _eod_table(evening: dict) -> str:
    rows = evening.get("eod_quote_table", [])
    body = []
    for q in rows:
        pct = q.get("change_pct")
        body.append(
            f"      <tr>"
            f'<td class="sym">{escape(q["ticker"])}</td>'
            f'<td>${q["eod_price"]}</td>'
            f'<td class="{_qt_chg_class(pct)}">{_chg_str(pct)}</td>'
            f'<td>{escape(q.get("timestamp", ""))}</td>'
            f'<td class="src">{escape(q.get("source", ""))}</td>'
            f"</tr>"
        )
    review_date = evening["review_date"]
    long_date = datetime.strptime(review_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    return f"""<div class="quote-table-wrap">
  <div class="quote-table-title">EOD Quote Table — {long_date} (RTH 16:00 ET)</div>
  <table class="qt">
    <thead>
      <tr><th>Ticker</th><th>EOD Price</th><th>Day Chg</th><th>Timestamp</th><th>Source</th></tr>
    </thead>
    <tbody>
{chr(10).join(body)}
    </tbody>
  </table>
</div>"""


def _scorecard(evening: dict) -> str:
    scored = evening.get("scored_recommendations", [])
    review_date = evening["review_date"]
    counts = {"working": 0, "neutral": 0, "not_working": 0, "thesis_broken": 0}
    new_today = 0
    partial = 0
    for s in scored:
        counts[s["outcome"]] = counts.get(s["outcome"], 0) + 1
        if s["id"].startswith(review_date):
            new_today += 1
        if s.get("partial_review"):
            partial += 1
    n = len(scored)
    return f"""<div class="section-label">Today's Position Scorecard — {n} Positions Scored</div>
<div class="outcome-summary">
  <div class="os-item os-working"><div class="os-count">{counts['working']}</div><div class="os-label">Working</div></div>
  <div class="os-item os-neutral"><div class="os-count">{counts['neutral']}</div><div class="os-label">Neutral</div></div>
  <div class="os-item os-not_working"><div class="os-count">{counts['not_working']}</div><div class="os-label">Not Working</div></div>
  <div class="os-item os-thesis_broken"><div class="os-count">{counts['thesis_broken']}</div><div class="os-label">Thesis Broken</div></div>
  <div class="os-item"><div class="os-count" style="color: var(--indigo-deep);">{new_today}</div><div class="os-label">New Today</div></div>
  <div class="os-item"><div class="os-count" style="color: var(--gold);">{partial}</div><div class="os-label">Partial Review</div></div>
</div>"""


def _outcome_card(scored: dict, position: dict, review_date: str) -> str:
    outcome = scored["outcome"]
    ticker = scored["id"].split("-")[3] if scored["id"].count("-") >= 3 else position.get("ticker", "?")
    strategy_raw = position.get("strategy", "")
    strategy_label = _STRATEGY_LABEL.get(strategy_raw, strategy_raw.replace("_", " ").title())
    legs_str = _format_legs(strategy_raw, position.get("legs") or [])
    expiry = _format_expiry(position.get("expiry_date", ""))
    dte_left = _days_between(review_date, position.get("expiry_date", ""))
    days_held = _days_between(position.get("date_recommended", ""), review_date)
    dte_str = f"{dte_left} DTE" if dte_left is not None else ""
    days_str = f"(Day {days_held})" if days_held is not None else ""

    # Badges
    badges = [f'<span class="badge badge-{outcome}">{outcome.replace("_", " ").title()}</span>']
    if scored["id"].startswith(review_date):
        badges.append('<span class="badge badge-new">New Today</span>')
    if scored.get("partial_review"):
        badges.append('<span class="badge badge-partial">Partial Review</span>')
    status_update = scored.get("status_update")
    if status_update:
        badges.append(f'<span class="badge badge-action">{status_update.title()}</span>')

    # Metrics
    entry = position.get("live_price_at_recommendation")
    eod = scored.get("eod_price")
    pnl_pct = scored.get("estimated_pnl_pct")
    pnl_dollars = scored.get("estimated_pnl_dollars")
    short_strike = _short_strike(strategy_raw, position.get("legs") or [])

    # Day change for the underlying — look up the eod_quote_table entry
    day_chg = None
    eod_table = position.get("_eod_table_ref") or []
    for q in eod_table:
        if q.get("ticker") == ticker:
            day_chg = q.get("change_pct")
            break

    buffer_str = "—"
    buffer_class = "flat"
    if short_strike is not None and eod is not None:
        buf = eod - short_strike
        buf_pct = (buf / eod * 100) if eod else 0.0
        buffer_class = "pos" if buf > 0 else ("warn" if abs(buf_pct) < 2 else "neg")
        buffer_str = f"${buf:.2f} ({buf_pct:.1f}%)"

    entry_eod = (
        f"${entry} → ${eod}" if entry is not None and eod is not None else "—"
    )

    pnl_str = "—"
    if pnl_pct is not None and pnl_dollars is not None:
        sign = "+" if pnl_dollars >= 0 else "−"
        pnl_str = f"{'+' if pnl_pct >= 0 else '−'}{abs(pnl_pct)}% / {sign}${abs(pnl_dollars)}"

    diag = scored.get("diagnosis_category")
    metrics = [
        ('Entry / EOD', entry_eod, 'flat'),
        ('Day Chg', _chg_str(day_chg), _chg_class(day_chg).replace('up', 'pos').replace('down', 'neg')),
        (f'Buffer to ${short_strike}', buffer_str, buffer_class) if short_strike is not None else ('Buffer', '—', 'flat'),
        ('Est. P&amp;L', pnl_str, _money_class(pnl_dollars)),
    ]
    if diag:
        metrics.append(('Diagnosis', diag.replace('_', ' ').title(), 'warn'))

    metrics_html = "".join(
        f'<div class="metric"><span class="metric-label">{label}</span>'
        f'<span class="metric-val {cls}">{val}</span></div>'
        for (label, val, cls) in metrics
    )

    # Body fields
    fields_html = []
    if scored.get("thesis_check"):
        fields_html.append(
            '<div class="card-field">'
            '<div class="card-field-label">Thesis Check</div>'
            f'<div class="card-field-val">{scored["thesis_check"]}</div>'
            '</div>'
        )
    if scored.get("lesson"):
        fields_html.append(
            '<div class="card-field">'
            '<div class="card-field-label">Lesson</div>'
            f'<div class="card-field-val">{scored["lesson"]}</div>'
            '</div>'
        )
    if diag:
        fields_html.append(
            '<div class="card-field">'
            '<div class="card-field-label">Diagnosis Category</div>'
            f'<div class="card-field-val"><strong>{diag.replace("_", " ").title()}</strong></div>'
            '</div>'
        )

    return f"""<div class="outcome-card {outcome}">
  <div class="card-header">
    <div>
      <div class="card-ticker-tag">{escape(ticker)}</div>
      <div class="card-strategy">{strategy_label} · {legs_str} · {expiry} · {dte_str} {days_str}</div>
    </div>
    <div class="badge-row">{''.join(badges)}</div>
  </div>
  <div class="card-body">
    <div class="card-metrics">{metrics_html}</div>
    {''.join(fields_html)}
  </div>
</div>"""


_OUTCOME_SORT = {"thesis_broken": 0, "not_working": 1, "neutral": 2, "working": 3}


def _outcome_cards(evening: dict, positions_by_id: dict) -> str:
    scored = evening.get("scored_recommendations", [])
    eod_table = evening.get("eod_quote_table", [])

    def sort_key(s):
        return (
            _OUTCOME_SORT.get(s["outcome"], 99),
            -(s.get("estimated_pnl_pct") or 0) if s["outcome"] == "working"
            else (s.get("estimated_pnl_pct") or 0),
        )

    cards = []
    review_date = evening["review_date"]
    for s in sorted(scored, key=sort_key):
        pos = dict(positions_by_id.get(s["id"], {}))
        pos["_eod_table_ref"] = eod_table
        cards.append(_outcome_card(s, pos, review_date))
    return (
        '<div class="section-head">Position Outcomes</div>\n'
        '<div class="card-grid">\n' + "\n".join(cards) + "\n</div>"
    )


def _meta_review(evening: dict) -> str:
    text = evening.get("meta_review", "")
    return f"""<div class="meta-block">
  <div class="meta-kicker">Meta Review</div>
  <div class="meta-text">{text}</div>
</div>"""


def _proposals(evening: dict) -> str:
    proposals = evening.get("prompt_change_proposals", [])
    if not proposals:
        return (
            '<div class="section-head">Prompt-Change Proposals</div>\n'
            '<div class="no-proposals"><strong>No new prompt-change proposals today.</strong> '
            'All adverse outcomes today were diagnosed as judgment_error or bad_luck — '
            'no data or process failures to address.</div>'
        )
    rows = []
    for p in proposals:
        threshold = p.get("action_threshold_met")
        count = p.get("recurrence_count_14d", 1)
        header_cls = "danger-header" if threshold else "watch-header"
        header_label = "ACT NOW" if threshold else f"Watch — Accumulating (recurrence {count})"
        rows.append(
            f'<div class="proposal-card"><div class="{header_cls}">{header_label}</div>'
            f'<div><strong>{escape(p.get("summary", ""))}</strong></div>'
            f'<div>{escape(p.get("rationale", ""))}</div>'
            f'<div><em>Proposed change:</em> {escape(p.get("proposed_change", ""))}</div></div>'
        )
    return (
        '<div class="section-head">Prompt-Change Proposals</div>\n'
        + "\n".join(rows)
    )


def _tomorrow(evening: dict) -> str:
    text = evening.get("tomorrow_focus", "")
    review_date = evening["review_date"]
    d = datetime.strptime(review_date, "%Y-%m-%d").date()
    # Best-effort: next business day (skip weekends).
    next_d = d.fromordinal(d.toordinal() + 1)
    while next_d.weekday() >= 5:
        next_d = next_d.fromordinal(next_d.toordinal() + 1)
    next_long = next_d.strftime("%A, %B %-d, %Y")
    return f"""<div class="tomorrow-block">
  <div class="tm-kicker">Tomorrow Focus — {next_long}</div>
  <div class="tm-text">{text}</div>
</div>"""


# ── CSS + page shell ─────────────────────────────────────────────────────────


_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --ink: #1a1a1a; --rule: #2a2a2a; --muted: #555; --pale: #f7f5f1;
    --indigo-deep: #1a3a6e; --indigo-light: #e8edf7;
    --green: #1a7a3a; --grey: #888; --amber: #b8860b; --red: #c41e3a;
    --green-bg: #f0faf3; --amber-bg: #fdf8e8; --red-bg: #fdf0f2; --grey-bg: #f5f5f5;
    --gold: #c9a227;
  }
  html { font-size: 16px; }
  body { font-family: 'Source Serif 4', Georgia, serif; color: var(--ink); background: var(--pale); max-width: 960px; margin: 0 auto; padding: 0 24px 48px; }
  .masthead { border-top: 4px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 24px 0 20px; text-align: center; }
  .masthead-kicker { font-family: 'Source Serif 4', serif; font-size: 0.72rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
  .masthead-title { font-family: 'Bebas Neue', sans-serif; font-size: 3.8rem; letter-spacing: 0.06em; line-height: 1; color: var(--ink); }
  .masthead-sub { font-family: 'Source Serif 4', serif; font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); margin-top: 8px; }
  .ticker-bar { background: var(--indigo-deep); color: #fff; padding: 9px 20px; display: flex; flex-wrap: wrap; gap: 18px 30px; font-family: 'Source Serif 4', serif; font-size: 0.78rem; letter-spacing: 0.04em; }
  .ticker-item { display: flex; align-items: center; gap: 8px; }
  .ticker-sym { font-weight: 600; letter-spacing: 0.08em; }
  .ticker-price { opacity: 0.92; }
  .ticker-chg { font-size: 0.72rem; }
  .up { color: #5ddc8a; } .down { color: #ff7f7f; } .flat { color: #ccc; }
  .triple-rule { border: none; border-top: 4px double var(--rule); margin: 22px 0; }
  .section-head { font-family: 'Bebas Neue', sans-serif; font-size: 1.45rem; letter-spacing: 0.12em; color: var(--ink); border-bottom: 2px solid var(--ink); padding-bottom: 4px; margin-bottom: 16px; text-transform: uppercase; }
  .section-label { font-family: 'Source Serif 4', serif; font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }
  .quote-table-wrap { background: var(--indigo-light); border: 1px solid #c5d0e8; border-radius: 3px; padding: 16px 20px; margin-bottom: 22px; overflow-x: auto; }
  .quote-table-title { font-family: 'Bebas Neue', sans-serif; font-size: 1.1rem; letter-spacing: 0.12em; color: var(--indigo-deep); margin-bottom: 12px; }
  table.qt { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  table.qt th { font-family: 'Source Serif 4', serif; font-weight: 600; text-align: left; font-size: 0.70rem; letter-spacing: 0.10em; text-transform: uppercase; color: var(--indigo-deep); border-bottom: 1px solid #b0bed8; padding: 4px 8px 6px; }
  table.qt td { padding: 6px 8px; border-bottom: 1px solid #dde4f0; vertical-align: top; }
  table.qt tr:last-child td { border-bottom: none; }
  table.qt td.sym { font-weight: 700; font-size: 0.88rem; color: var(--indigo-deep); }
  table.qt td.chg-up { color: var(--green); font-weight: 600; }
  table.qt td.chg-dn { color: var(--red); font-weight: 600; }
  table.qt td.chg-flat { color: var(--muted); font-weight: 600; }
  table.qt td.src { font-size: 0.68rem; color: var(--muted); max-width: 280px; }
  .card-grid { display: grid; gap: 18px; margin-bottom: 8px; }
  .outcome-card { background: #fff; border: 1px solid #ddd; border-radius: 3px; overflow: hidden; }
  .outcome-card.working { border-top: 4px solid var(--green); }
  .outcome-card.neutral { border-top: 4px solid var(--grey); }
  .outcome-card.not_working { border-top: 4px solid var(--amber); }
  .outcome-card.thesis_broken { border-top: 4px solid var(--red); }
  .card-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 12px 16px 8px; flex-wrap: wrap; gap: 8px; }
  .card-ticker-tag { font-family: 'Bebas Neue', sans-serif; font-size: 1.5rem; letter-spacing: 0.08em; color: var(--ink); line-height: 1; }
  .card-strategy { font-size: 0.68rem; letter-spacing: 0.10em; text-transform: uppercase; color: var(--muted); margin-top: 2px; }
  .badge-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .badge { font-family: 'Source Serif 4', serif; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.10em; text-transform: uppercase; padding: 3px 10px; border-radius: 2px; }
  .badge-working { background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }
  .badge-neutral { background: var(--grey-bg); color: var(--grey); border: 1px solid var(--grey); }
  .badge-not_working { background: var(--amber-bg); color: var(--amber); border: 1px solid var(--amber); }
  .badge-thesis_broken { background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }
  .badge-partial { background: #fffbe8; color: #8a6800; border: 1px solid #d8b440; }
  .badge-action { background: #fff8e8; color: #8a6800; border: 1px solid #c8a430; }
  .badge-new { background: #e8edf7; color: var(--indigo-deep); border: 1px solid var(--indigo-deep); }
  .card-body { padding: 0 16px 14px; }
  .card-metrics { display: flex; gap: 20px; flex-wrap: wrap; background: #fafafa; border: 1px solid #eee; border-radius: 2px; padding: 8px 12px; margin-bottom: 10px; font-size: 0.80rem; }
  .metric { display: flex; flex-direction: column; }
  .metric-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.10em; color: var(--muted); }
  .metric-val { font-weight: 700; font-size: 0.95rem; margin-top: 1px; }
  .metric-val.pos { color: var(--green); } .metric-val.neg { color: var(--red); } .metric-val.warn { color: var(--amber); } .metric-val.flat { color: var(--muted); }
  .card-field { margin-bottom: 9px; }
  .card-field-label { font-family: 'Source Serif 4', serif; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); margin-bottom: 2px; }
  .card-field-val { font-size: 0.84rem; line-height: 1.5; }
  .meta-block { background: var(--indigo-deep); color: #fff; padding: 24px 28px; border-radius: 3px; margin: 24px 0; }
  .meta-block .meta-kicker { font-family: 'Bebas Neue', sans-serif; font-size: 0.9rem; letter-spacing: 0.20em; color: #7fa8e0; margin-bottom: 8px; }
  .meta-block .meta-text { font-family: 'Playfair Display', Georgia, serif; font-size: 1.0rem; line-height: 1.7; color: #e8edf7; }
  .tomorrow-block { background: #fff; border: 1px solid #c5d0e8; border-left: 5px solid var(--indigo-deep); border-radius: 3px; padding: 18px 22px; margin-bottom: 24px; }
  .tomorrow-block .tm-kicker { font-family: 'Bebas Neue', sans-serif; font-size: 0.9rem; letter-spacing: 0.20em; color: var(--indigo-deep); margin-bottom: 8px; }
  .tomorrow-block .tm-text { font-size: 0.92rem; line-height: 1.65; color: var(--ink); }
  .no-proposals { background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 3px; padding: 16px 20px; font-size: 0.84rem; color: var(--muted); font-style: italic; }
  .proposal-card { background: #fff; border: 1px solid #ddd; border-left: 4px solid var(--amber); padding: 14px 18px; margin-bottom: 12px; border-radius: 3px; font-size: 0.86rem; line-height: 1.55; }
  .proposal-card .danger-header { color: var(--red); font-family: 'Bebas Neue', sans-serif; letter-spacing: 0.12em; font-size: 1rem; margin-bottom: 6px; }
  .proposal-card .watch-header { color: var(--amber); font-family: 'Bebas Neue', sans-serif; letter-spacing: 0.12em; font-size: 0.92rem; margin-bottom: 6px; }
  .outcome-summary { display: flex; gap: 16px; flex-wrap: wrap; background: #fff; border: 1px solid #ddd; border-radius: 3px; padding: 14px 20px; margin-bottom: 22px; }
  .os-item { display: flex; flex-direction: column; align-items: center; min-width: 70px; }
  .os-count { font-family: 'Bebas Neue', sans-serif; font-size: 2rem; line-height: 1; }
  .os-label { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); margin-top: 2px; text-align: center; }
  .os-working .os-count { color: var(--green); }
  .os-neutral .os-count { color: var(--grey); }
  .os-not_working .os-count { color: var(--amber); }
  .os-thesis_broken .os-count { color: var(--red); }
  .highlight-strip { background: #f0f4ff; border: 1px solid #b0c0e8; border-left: 4px solid var(--indigo-deep); border-radius: 3px; padding: 10px 16px; font-size: 0.82rem; color: var(--indigo-deep); margin-bottom: 20px; }
  .highlight-strip strong { font-weight: 700; }
  .disclaimer { border-top: 1px solid #ccc; padding-top: 16px; margin-top: 32px; font-size: 0.68rem; color: var(--muted); line-height: 1.6; }
  @media print {
    body { background: #fff; padding: 0 12px 32px; }
    .ticker-bar { background: #1a3a6e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .meta-block { background: #1a3a6e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    @page { margin: 0.75in; }
  }
"""


_DISCLAIMER = (
    '<div class="disclaimer"><strong>DISCLAIMER:</strong> '
    'This Evening Review is for informational and educational purposes only and does not constitute investment advice, '
    'a recommendation to buy or sell any security, or a solicitation for any transaction. '
    'Outcomes shown are estimates based on publicly sourced end-of-day prices and heuristic P&amp;L assumptions; '
    'they do not represent actual realized P&amp;L. Options trading involves substantial risk and is not suitable for all investors. '
    'You may lose more than your initial investment. Past performance is not indicative of future results. '
    'Always conduct your own research and consult a licensed financial advisor before making investment decisions. '
    'The author is not a registered investment advisor.</div>'
)


def render(evening: dict, positions_by_id: dict | None = None) -> str:
    if positions_by_id is None:
        positions_by_id = {}
    review_date = evening["review_date"]
    title_date = datetime.strptime(review_date, "%Y-%m-%d").strftime("%B %-d, %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Evening Review — {title_date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;1,300;1,400&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
{_masthead(evening)}
{_ticker_bar(evening)}
<hr class="triple-rule">
{_highlight_strip(evening)}
{_eod_table(evening)}
{_scorecard(evening)}
<hr class="triple-rule">
{_outcome_cards(evening, positions_by_id)}
<hr class="triple-rule">
{_meta_review(evening)}
{_proposals(evening)}
<hr class="triple-rule">
{_tomorrow(evening)}
{_DISCLAIMER}
</body>
</html>
"""


def _load_positions(evening: dict, recs_path: Path | None) -> dict:
    """Build {id: position_record} from recommendations.json for the strategy
    / legs / entry-price details that aren't in the evening JSON itself."""
    if recs_path is None or not recs_path.exists():
        return {}
    try:
        data = json.loads(recs_path.read_text())
    except json.JSONDecodeError:
        return {}
    scored_ids = {s["id"] for s in evening.get("scored_recommendations", [])}
    return {
        r["id"]: r
        for r in data.get("recommendations", [])
        if r.get("id") in scored_ids
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to evening JSON.")
    p.add_argument(
        "--output",
        help="Path to write HTML. If omitted, writes to stdout.",
    )
    p.add_argument(
        "--recommendations",
        help=(
            "Path to recommendations.json (defaults to sibling of --input). "
            "Used to look up legs / entry-price / strategy for each scored id."
        ),
    )
    args = p.parse_args()

    input_path = Path(args.input).resolve()
    evening = json.loads(input_path.read_text())

    if args.recommendations:
        recs_path = Path(args.recommendations).resolve()
    else:
        recs_path = input_path.parent / "recommendations.json"
    positions_by_id = _load_positions(evening, recs_path)

    html_out = render(evening, positions_by_id)

    if args.output:
        Path(args.output).resolve().write_text(html_out)
    else:
        sys.stdout.write(html_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
