#!/usr/bin/env python3
"""Generate a self-contained HTML trade report from /tmp/trade_report_data.json.

Reads JSON payload, writes TRADE-REPORT.html in the current working directory.
Stdlib only — no external dependencies.
"""
from __future__ import annotations

import json
import html
import os
from datetime import datetime
from pathlib import Path

JSON_PATH = Path("/tmp/trade_report_data.json")
OUT_PATH = Path(os.environ.get("TRADE_HTML_OUT", "TRADE-REPORT.html"))

CSS = """
:root {
  --primary: #1a365d;
  --strong-buy: #22763d;
  --buy: #48bb78;
  --hold: #d69e2e;
  --caution: #dd6b20;
  --avoid: #c53030;
  --bg: #ffffff;
  --text: #2d3748;
  --border: #e2e8f0;
  --disclaimer-bg: #fffff0;
  --muted: #718096;
  --panel: #f7fafc;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--text);
  background: var(--bg);
  line-height: 1.55;
}
.container { max-width: 1100px; margin: 0 auto; padding: 32px 28px 80px; }
header.cover {
  border-bottom: 4px solid var(--primary);
  padding-bottom: 20px;
  margin-bottom: 28px;
}
header.cover h1 {
  margin: 0 0 6px;
  color: var(--primary);
  font-size: 32px;
  letter-spacing: -0.5px;
}
header.cover .subtitle { color: var(--muted); font-size: 15px; }
.disclaimer-banner {
  background: var(--disclaimer-bg);
  border: 1px solid var(--hold);
  border-left: 4px solid var(--hold);
  padding: 12px 16px;
  border-radius: 4px;
  margin: 18px 0;
  font-size: 13px;
}
nav.toc {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 14px 18px;
  border-radius: 6px;
  margin-bottom: 32px;
}
nav.toc h2 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--primary);
  text-transform: uppercase;
  letter-spacing: 1px;
}
nav.toc ul { margin: 0; padding-left: 20px; columns: 2; }
nav.toc a { color: var(--primary); text-decoration: none; font-size: 14px; }
nav.toc a:hover { text-decoration: underline; }
section { margin: 36px 0; }
h2.section-title {
  color: var(--primary);
  border-bottom: 2px solid var(--border);
  padding-bottom: 6px;
  font-size: 22px;
  margin-bottom: 16px;
}
h3 { color: var(--primary); font-size: 18px; margin-top: 22px; }
.pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.pill-strong-buy { background: var(--strong-buy); }
.pill-buy { background: var(--buy); color: #1a3d2a; }
.pill-hold { background: var(--hold); }
.pill-caution { background: var(--caution); }
.pill-avoid { background: var(--avoid); }
.pill-neutral { background: var(--muted); }
.stock-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px 22px;
  margin-bottom: 22px;
  background: var(--bg);
}
.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}
.stock-header h3 { margin: 0; font-size: 22px; }
.stock-meta { color: var(--muted); font-size: 13px; }
.score-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  background: var(--primary);
  color: #fff;
  padding: 8px 14px;
  border-radius: 6px;
  min-width: 72px;
}
.score-badge .num { font-size: 22px; font-weight: 700; line-height: 1; }
.score-badge .label { font-size: 10px; letter-spacing: 1px; text-transform: uppercase; opacity: 0.85; }
.score-bars { margin: 14px 0; }
.bar-row {
  display: grid;
  grid-template-columns: 130px 1fr 50px;
  align-items: center;
  gap: 10px;
  margin: 6px 0;
  font-size: 13px;
}
.bar-track {
  background: var(--border);
  border-radius: 3px;
  height: 10px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--buy), var(--primary));
  border-radius: 3px;
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  margin: 14px 0;
}
.case-box {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 13px;
}
.case-bull { background: #f0fff4; border-color: var(--buy); }
.case-bear { background: #fff5f5; border-color: var(--avoid); }
.case-box h4 { margin: 0 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
.case-bull h4 { color: var(--strong-buy); }
.case-bear h4 { color: var(--avoid); }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
th { background: var(--panel); color: var(--primary); font-weight: 600; }
.kv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin: 12px 0;
}
.kv {
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
}
.kv .k { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
.kv .v { font-weight: 600; color: var(--primary); }
.callout {
  background: var(--disclaimer-bg);
  border-left: 4px solid var(--caution);
  padding: 12px 16px;
  margin: 14px 0;
  font-size: 13px;
  border-radius: 4px;
}
.exec-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.es-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px 14px;
}
.es-card .es-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.es-card .es-value { font-size: 16px; font-weight: 600; color: var(--primary); margin-top: 4px; }
ol.timeline { padding-left: 20px; }
ol.timeline li { margin: 4px 0; font-size: 13px; }
footer.report-footer {
  margin-top: 60px;
  padding: 18px 0;
  border-top: 2px solid var(--primary);
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}
@media print {
  .container { padding: 12px; max-width: none; }
  section { page-break-inside: avoid; }
  .stock-card { page-break-inside: avoid; }
  nav.toc { page-break-after: always; }
  a { color: var(--text); text-decoration: none; }
}
@media (max-width: 700px) {
  nav.toc ul { columns: 1; }
  .two-col { grid-template-columns: 1fr; }
  .bar-row { grid-template-columns: 110px 1fr 40px; font-size: 12px; }
}
"""


def signal_pill_class(signal: str) -> str:
    s = (signal or "").strip().lower()
    if "strong buy" in s:
        return "pill-strong-buy"
    if s == "buy" or "accumulate" in s:
        return "pill-buy"
    if "hold" in s:
        return "pill-hold"
    if "caution" in s:
        return "pill-caution"
    if "avoid" in s:
        return "pill-avoid"
    return "pill-neutral"


def esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def render_score_bars(rows):
    out = ['<div class="score-bars">']
    for label, score, max_score in rows:
        try:
            pct = max(0, min(100, (float(score) / float(max_score)) * 100))
        except (TypeError, ValueError, ZeroDivisionError):
            pct = 0
        out.append(
            f'<div class="bar-row"><span>{esc(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<span>{esc(score)}/{esc(max_score)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def render_stock(analysis: dict) -> str:
    ticker = esc(analysis.get("ticker", "?"))
    company = esc(analysis.get("company_name", ""))
    score = analysis.get("trade_score", 0)
    grade = esc(analysis.get("trade_grade", ""))
    signal = analysis.get("trade_signal", "")
    date = esc(analysis.get("analysis_date", ""))
    price = analysis.get("price_at_analysis")
    target = analysis.get("price_target")
    stop = analysis.get("stop_loss")
    rr = esc(analysis.get("risk_reward_ratio", ""))
    bull = esc(analysis.get("bull_case", ""))
    bear = esc(analysis.get("bear_case", ""))
    catalyst = esc(analysis.get("catalyst", ""))
    pos_size = analysis.get("position_size_pct")
    levels = analysis.get("key_levels", {}) or {}

    sub = analysis.get("sub_scores", {}) or {}
    bars = render_score_bars([
        ("Technical", sub.get("technical", analysis.get("technical_score", 0)), 100),
        ("Fundamental", sub.get("fundamental", analysis.get("fundamental_score", 0)), 100),
        ("Sentiment", sub.get("sentiment", analysis.get("sentiment_score", 0)), 100),
        ("Risk", sub.get("risk", analysis.get("risk_score", 0)), 100),
        ("Thesis", sub.get("thesis", analysis.get("thesis_score", 0)), 100),
    ])

    kv_items = []
    if price is not None:
        kv_items.append(("Price", f"${esc(price)}"))
    if target is not None:
        kv_items.append(("Target", f"${esc(target)}"))
    if stop is not None:
        kv_items.append(("Stop", f"${esc(stop)}"))
    if rr:
        kv_items.append(("Risk/Reward", rr))
    if pos_size is not None:
        kv_items.append(("Position Size", f"{esc(pos_size)}%"))
    if "support" in levels:
        kv_items.append(("Support", f"${esc(levels['support'])}"))
    if "resistance" in levels:
        kv_items.append(("Resistance", f"${esc(levels['resistance'])}"))
    kv_html = "".join(
        f'<div class="kv"><div class="k">{esc(k)}</div><div class="v">{v}</div></div>'
        for k, v in kv_items
    )

    return f"""
    <article class="stock-card" id="stock-{ticker}">
      <div class="stock-header">
        <div>
          <h3>{ticker} <span class="stock-meta">— {company}</span></h3>
          <div class="stock-meta">Analysis date: {date}</div>
          <div style="margin-top:6px"><span class="pill {signal_pill_class(signal)}">{esc(signal)}</span> <strong>Grade {grade}</strong></div>
        </div>
        <div class="score-badge"><span class="num">{esc(score)}</span><span class="label">Trade Score</span></div>
      </div>
      {bars}
      <div class="kv-grid">{kv_html}</div>
      <div class="two-col">
        <div class="case-box case-bull"><h4>Bull Case</h4>{bull}</div>
        <div class="case-box case-bear"><h4>Bear Case</h4>{bear}</div>
      </div>
      {('<div class="callout"><strong>Catalyst:</strong> ' + catalyst + '</div>') if catalyst else ''}
    </article>
    """


def render_executive_summary(es: dict) -> str:
    if not es:
        return ""
    cards = []
    if "total_stocks_analyzed" in es:
        cards.append(("Stocks Analyzed", es["total_stocks_analyzed"]))
    if es.get("top_conviction_pick"):
        cards.append(("Top Conviction", es["top_conviction_pick"]))
    if es.get("biggest_risk_flag"):
        cards.append(("Biggest Risk Flag", es["biggest_risk_flag"]))
    if es.get("portfolio_action_needed"):
        cards.append(("Portfolio Action", es["portfolio_action_needed"]))
    cards_html = "".join(
        f'<div class="es-card"><div class="es-label">{esc(k)}</div><div class="es-value">{esc(v)}</div></div>'
        for k, v in cards
    )

    def pill_list(items, cls):
        if not items:
            return ""
        return " ".join(f'<span class="pill {cls}">{esc(t)}</span>' for t in items)

    signal_groups = []
    if es.get("strong_buys"):
        signal_groups.append(("Strong Buys", pill_list(es["strong_buys"], "pill-strong-buy")))
    if es.get("buys"):
        signal_groups.append(("Buys", pill_list(es["buys"], "pill-buy")))
    if es.get("holds"):
        signal_groups.append(("Holds", pill_list(es["holds"], "pill-hold")))
    if es.get("avoids"):
        signal_groups.append(("Avoids", pill_list(es["avoids"], "pill-avoid")))
    signal_html = "".join(
        f'<p><strong>{esc(label)}:</strong> {pills}</p>'
        for label, pills in signal_groups
    )

    catalysts = es.get("upcoming_catalysts") or []
    cat_html = ""
    if catalysts:
        items = "".join(f"<li>{esc(c)}</li>" for c in catalysts)
        cat_html = f'<h3>Upcoming Catalysts</h3><ol class="timeline">{items}</ol>'

    return f"""
    <section id="executive-summary">
      <h2 class="section-title">Executive Summary</h2>
      <div class="exec-summary-grid">{cards_html}</div>
      <div style="margin-top:14px">{signal_html}</div>
      {cat_html}
    </section>
    """


def render_toc(analyses, has_portfolio, has_watchlist, has_screens, has_earnings) -> str:
    items = ['<li><a href="#executive-summary">Executive Summary</a></li>']
    for a in analyses:
        t = esc(a.get("ticker", "?"))
        items.append(f'<li><a href="#stock-{t}">{t} — {esc(a.get("company_name",""))}</a></li>')
    if has_portfolio:
        items.append('<li><a href="#portfolio">Portfolio Analysis</a></li>')
    if has_watchlist:
        items.append('<li><a href="#watchlist">Watchlist</a></li>')
    if has_screens:
        items.append('<li><a href="#screens">Screen Results</a></li>')
    if has_earnings:
        items.append('<li><a href="#earnings">Earnings Calendar</a></li>')
    return f'<nav class="toc"><h2>Contents</h2><ul>{"".join(items)}</ul></nav>'


def render_portfolio(p: dict) -> str:
    if not p:
        return ""
    rows = "".join(
        f"<tr><td>{esc(k.replace('_',' ').title())}</td><td>{esc(v)}</td></tr>"
        for k, v in p.items()
    )
    return f"""
    <section id="portfolio">
      <h2 class="section-title">Portfolio Analysis</h2>
      <table><tbody>{rows}</tbody></table>
    </section>
    """


def render_watchlist(w: dict) -> str:
    if not w:
        return ""
    alerts = w.get("alert_details") or []
    alerts_html = "".join(f"<li>{esc(a)}</li>" for a in alerts)
    return f"""
    <section id="watchlist">
      <h2 class="section-title">Watchlist</h2>
      <div class="kv-grid">
        <div class="kv"><div class="k">Stocks</div><div class="v">{esc(w.get('watchlist_count',''))}</div></div>
        <div class="kv"><div class="k">Avg Score</div><div class="v">{esc(w.get('average_score',''))}</div></div>
        <div class="kv"><div class="k">Top Stock</div><div class="v">{esc(w.get('top_stock',''))}</div></div>
        <div class="kv"><div class="k">Active Alerts</div><div class="v">{esc(w.get('active_alerts',''))}</div></div>
      </div>
      {('<h3>Alerts</h3><ul>'+alerts_html+'</ul>') if alerts_html else ''}
    </section>
    """


def render_screens(screens: list) -> str:
    if not screens:
        return ""
    rows = []
    for s in screens:
        top3 = ", ".join(s.get("top_3", []))
        rows.append(
            f"<tr><td>{esc(s.get('screen_name',''))}</td>"
            f"<td>{esc(s.get('matches_count',''))}</td>"
            f"<td>{esc(top3)}</td>"
            f"<td>{esc(s.get('screen_date',''))}</td></tr>"
        )
    return f"""
    <section id="screens">
      <h2 class="section-title">Screen Results</h2>
      <table><thead><tr><th>Screen</th><th>Matches</th><th>Top 3</th><th>Date</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>
    """


def render_earnings(earnings: list) -> str:
    if not earnings:
        return ""
    rows = []
    for e in earnings:
        rows.append(
            f"<tr><td>{esc(e.get('ticker',''))}</td>"
            f"<td>{esc(e.get('earnings_date',''))}</td>"
            f"<td>{esc(e.get('days_until',''))}</td>"
            f"<td>{esc(e.get('eps_estimate',''))}</td>"
            f"<td>{esc(e.get('implied_move',''))}</td>"
            f"<td>{esc(e.get('conviction',''))}</td>"
            f"<td>{esc(e.get('setup_recommendation',''))}</td></tr>"
        )
    return f"""
    <section id="earnings">
      <h2 class="section-title">Earnings Calendar</h2>
      <table><thead><tr><th>Ticker</th><th>Date</th><th>Days</th><th>EPS Est</th><th>Implied Move</th><th>Conviction</th><th>Setup</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table>
    </section>
    """


def main() -> int:
    if not JSON_PATH.exists():
        print(f"ERROR: {JSON_PATH} not found. Skill must write JSON payload first.")
        return 1
    data = json.loads(JSON_PATH.read_text())

    meta = data.get("report_metadata", {}) or {}
    analyses = data.get("analyses", []) or []
    portfolio = data.get("portfolio") or {}
    watchlist = data.get("watchlist") or {}
    screens = data.get("screens") or []
    earnings = data.get("earnings") or []
    exec_summary = data.get("executive_summary") or {}

    gen_date = meta.get("generated_date") or datetime.now().strftime("%Y-%m-%d")
    gen_time = meta.get("generated_time") or datetime.now().strftime("%H:%M:%S")
    disclaimer = meta.get("disclaimer", "For educational/research purposes only. Not financial advice.")

    toc = render_toc(analyses, bool(portfolio), bool(watchlist), bool(screens), bool(earnings))
    es_html = render_executive_summary(exec_summary)

    stocks_html = ""
    if analyses:
        stocks_html = (
            '<section id="analyses"><h2 class="section-title">Individual Stock Analyses</h2>'
            + "".join(render_stock(a) for a in analyses)
            + "</section>"
        )

    portfolio_html = render_portfolio(portfolio)
    watchlist_html = render_watchlist(watchlist)
    screens_html = render_screens(screens)
    earnings_html = render_earnings(earnings)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Trading Research Report — {esc(gen_date)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <header class="cover">
    <h1>AI Trading Research Report</h1>
    <div class="subtitle">Generated by AI Trading Analyst · {esc(gen_date)} {esc(gen_time)}</div>
    <div class="disclaimer-banner"><strong>DISCLAIMER:</strong> {esc(disclaimer)}</div>
  </header>
  {toc}
  {es_html}
  {stocks_html}
  {portfolio_html}
  {watchlist_html}
  {screens_html}
  {earnings_html}
  <footer class="report-footer">
    <div><strong>DISCLAIMER:</strong> {esc(disclaimer)}</div>
    <div>Generated {esc(gen_date)} {esc(gen_time)} · Print to PDF via Cmd/Ctrl+P</div>
  </footer>
</div>
</body>
</html>
"""
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {OUT_PATH.resolve()} ({OUT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
