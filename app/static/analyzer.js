// ── Analyzer ─────────────────────────────────────────────────────────────────

let lastAnalysis = null;

async function runAnalysis() {
  const ticker = document.getElementById('az-ticker').value.trim().toUpperCase();
  const strategy = document.getElementById('az-strategy').value;

  if (!ticker) return;

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.textContent = 'Searching...';
  document.getElementById('az-empty').style.display = 'none';
  document.getElementById('az-results').innerHTML = '<div class="az-loading">Fetching live option chain data...</div>';

  if (strategy === 'compare') {
    await runCompareAnalysis(ticker, btn);
  } else {
    await runSingleAnalysis(ticker, strategy, btn);
  }

  btn.disabled = false;
  btn.textContent = 'Find Trade';
}

function toggleExpMode() {
  const mode = document.querySelector('input[name="az-exp-mode"]:checked').value;
  document.getElementById('az-dte-inputs').style.display = mode === 'dte' ? 'flex' : 'none';
  document.getElementById('az-expiry-input').style.display = mode === 'expiry' ? 'block' : 'none';
  if (mode === 'expiry') loadExpirations();
}

let _lastExpTicker = '';
async function loadExpirations() {
  const ticker = document.getElementById('az-ticker').value.trim().toUpperCase();
  if (!ticker || ticker === _lastExpTicker) return;
  _lastExpTicker = ticker;
  const sel = document.getElementById('az-expiry');
  sel.innerHTML = '<option value="">Select expiry...</option>';
  try {
    const res = await fetch(`/api/expirations/${ticker}`);
    const data = await res.json();
    for (const exp of data.expirations || []) {
      const opt = document.createElement('option');
      opt.value = exp;
      opt.textContent = exp;
      sel.appendChild(opt);
    }
  } catch (e) { /* silent */ }
}

function onTickerChange() {
  _lastExpTicker = '';
  const mode = document.querySelector('input[name="az-exp-mode"]:checked').value;
  if (mode === 'expiry') loadExpirations();
}

async function runSingleAnalysis(ticker, strategy, btn) {
  const deltaVal = document.getElementById('az-delta').value;
  const dteMinVal = document.getElementById('az-dte-min').value;
  const dteMaxVal = document.getElementById('az-dte-max').value;

  const body = { ticker, strategy };
  if (deltaVal) body.target_delta = parseFloat(deltaVal);
  const expMode = document.querySelector('input[name="az-exp-mode"]:checked').value;
  if (expMode === 'expiry') {
    const expVal = document.getElementById('az-expiry').value;
    if (expVal) body.expiry = expVal;
  } else {
    if (dteMinVal) body.dte_min = parseInt(dteMinVal);
    if (dteMaxVal) body.dte_max = parseInt(dteMaxVal);
  }

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.error) {
      document.getElementById('az-results').innerHTML = `<div class="az-error">${esc(data.error)}</div>`;
      return;
    }

    // Resolve company name then render
    await resolveTickerName(ticker);
    renderAnalysisResult(strategy, data);
    document.getElementById('btn-clear').style.display = 'inline-block';

    if (document.getElementById('ai-toggle').checked) {
      inputEl.value = buildAnalysisChatPrompt(strategy, data);
      sendMessage();
    }
  } catch (err) {
    document.getElementById('az-results').innerHTML = `<div class="az-error">${esc(err.message)}</div>`;
    document.getElementById('btn-clear').style.display = 'inline-block';
  }
}

async function runCompareAnalysis(ticker, btn) {
  const dteMinVal = document.getElementById('az-dte-min').value;
  const dteMaxVal = document.getElementById('az-dte-max').value;

  const body = { ticker };
  const expMode = document.querySelector('input[name="az-exp-mode"]:checked').value;
  if (expMode === 'expiry') {
    const expVal = document.getElementById('az-expiry').value;
    if (expVal) body.expiry = expVal;
  } else {
    if (dteMinVal) body.dte_min = parseInt(dteMinVal);
    if (dteMaxVal) body.dte_max = parseInt(dteMaxVal);
  }

  try {
    const res = await fetch('/api/analyze/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    await resolveTickerName(ticker);
    renderCompareResult(data);
    document.getElementById('btn-clear').style.display = 'inline-block';

    if (document.getElementById('ai-toggle').checked) {
      inputEl.value = buildCompareChatPrompt(data);
      sendMessage();
    }
  } catch (err) {
    document.getElementById('az-results').innerHTML = `<div class="az-error">${esc(err.message)}</div>`;
    document.getElementById('btn-clear').style.display = 'inline-block';
  }
}

function buildAnalysisChatPrompt(strategy, d) {
  const prefix = ``;
  if (strategy === 'bull-put-spread') {
    return `${prefix}Assess this bull put spread on ${d.ticker} ($${d.price}): sell $${d.short_put.strike}P (Δ${d.short_put.delta}, IV ${d.short_put.iv_pct}%) / buy $${d.long_put.strike}P, credit $${d.net_credit}, max loss $${d.max_loss}, breakeven $${d.breakeven}, ${d.return_on_risk_pct}% return, ${d.prob_profit_pct}% prob profit, expiry ${d.expiry} (${d.dte} DTE). Is this a good trade?`;
  }
  if (strategy === 'bear-call-spread') {
    return `${prefix}Assess this bear call spread on ${d.ticker} ($${d.price}): sell $${d.short_call.strike}C (Δ${d.short_call.delta}, IV ${d.short_call.iv_pct}%) / buy $${d.long_call.strike}C, credit $${d.net_credit}, max loss $${d.max_loss}, breakeven $${d.breakeven}, ${d.return_on_risk_pct}% return, ${d.prob_profit_pct}% prob profit, expiry ${d.expiry} (${d.dte} DTE). Is this a good trade?`;
  }
  if (strategy === 'iron-condor') {
    const ps = d.put_side, cs = d.call_side;
    return `${prefix}Assess this iron condor on ${d.ticker} ($${d.price}): puts ${ps.short_put.strike}/${ps.long_put.strike} (Δ${ps.short_put.delta}, IV ${ps.short_put.iv_pct}%), calls ${cs.short_call.strike}/${cs.long_call.strike} (Δ${cs.short_call.delta}, IV ${cs.short_call.iv_pct}%), total credit $${d.total_credit}, max loss $${d.max_loss}, profit zone ${d.profit_zone}, ${d.return_on_risk_pct}% return, ${d.prob_profit_pct}% prob profit, expiry ${d.expiry} (${d.dte} DTE). Is this a good trade?`;
  }
  if (strategy === 'covered-call') {
    return `${prefix}Assess this covered call on ${d.ticker} ($${d.stock_price}): sell $${d.short_call.strike}C (Δ${d.short_call.delta}, IV ${d.short_call.iv_pct}%), premium $${d.premium_per_share}, static ${d.static_return_pct}%, annualized ${d.annualized_return_pct}%, downside protection ${d.downside_protection_pct}%, called away return ${d.called_away_return_pct}%, ${d.prob_called_pct}% prob called, expiry ${d.expiry} (${d.dte} DTE). Is this a good trade?`;
  }
  if (strategy === 'cash-secured-put') {
    return `${prefix}Assess this cash-secured put on ${d.ticker} ($${d.stock_price}): sell $${d.short_put.strike}P (Δ${d.short_put.delta}, IV ${d.short_put.iv_pct}%), premium $${d.premium_per_share}, return on capital ${d.return_on_capital_pct}%, annualized ${d.annualized_return_pct}%, effective buy price $${d.effective_buy_price} (${d.discount_pct}% discount), ${d.prob_profit_pct}% prob profit, cash required $${d.cash_required}, expiry ${d.expiry} (${d.dte} DTE). Is this a good trade?`;
  }
  return `${prefix}Assess this ${formatStrategy(strategy)} result: ${JSON.stringify(d)}`;
}

function clearAnalysis() {
  document.getElementById('az-results').innerHTML = '';
  document.getElementById('az-empty').style.display = 'block';
  document.getElementById('btn-clear').style.display = 'none';
  lastAnalysis = null;
}

function renderCompareResult(data) {
  lastAnalysis = null;
  const results = document.getElementById('az-results');
  const bps = data.bull_put_spread || {};
  const bcs = data.bear_call_spread || {};
  const ic = data.iron_condor || {};
  const cc = data.covered_call || {};
  const csp = data.cash_secured_put || {};
  const mc = data.market_context;
  const ticker = data.ticker;
  const price = bps.price || bcs.price || ic.price || cc.stock_price || csp.stock_price || 0;
  const src = [bps, bcs, ic, cc, csp].find(s => s && (s.price || s.stock_price)) || {};
  const prevClose = src.prev_close;
  const changePct = src.change_pct;

  // Find best values for highlighting (skip strategies with errors)
  const returns = [
    !bps.error && { strategy: 'Bull Put Spread', val: bps.return_on_risk_pct || 0 },
    !bcs.error && { strategy: 'Bear Call Spread', val: bcs.return_on_risk_pct || 0 },
    !ic.error && { strategy: 'Iron Condor', val: ic.return_on_risk_pct || 0 },
    !cc.error && { strategy: 'Covered Call', val: cc.annualized_return_pct || 0 },
    !csp.error && { strategy: 'Cash-Secured Put', val: csp.annualized_return_pct || 0 },
  ].filter(Boolean);
  const probs = [
    !bps.error && { strategy: 'Bull Put Spread', val: bps.prob_profit_pct || 0 },
    !bcs.error && { strategy: 'Bear Call Spread', val: bcs.prob_profit_pct || 0 },
    !ic.error && { strategy: 'Iron Condor', val: ic.prob_profit_pct || 0 },
    !cc.error && { strategy: 'Covered Call', val: 100 - (cc.prob_called_pct || 0) },
    !csp.error && { strategy: 'Cash-Secured Put', val: csp.prob_profit_pct || 0 },
  ].filter(Boolean);
  const bestReturn = returns.length ? returns.reduce((a, b) => a.val > b.val ? a : b).strategy : '';
  const bestProb = probs.length ? probs.reduce((a, b) => a.val > b.val ? a : b).strategy : '';

  // Data-driven best pick and rules-based trend pick
  const suggested = mc && !mc.error && mc.suggestion ? mc.suggestion.strategy : null;
  const trendPick = mc && !mc.error && mc.trend_pick ? mc.trend_pick.strategy : null;

  // Market context bar
  let contextHtml = '';
  if (mc && !mc.error) {
    const t = mc.trend;
    const trendIcon = t.classification === 'bullish' ? '\u2197' : t.classification === 'bearish' ? '\u2198' : '\u2192';
    const sign5d = t.change_5d_pct >= 0 ? '+' : '';
    const sign20d = t.change_20d_pct >= 0 ? '+' : '';
    contextHtml = `
      <div class="az-market-context">
        <span class="az-mc-badge az-trend-${t.classification}">${trendIcon} ${t.classification.toUpperCase()}</span>
        <span class="az-mc-detail">5d: ${sign5d}${t.change_5d_pct}% &middot; 20d: ${sign20d}${t.change_20d_pct}% &middot; 52w: ${t.percentile_52w}%ile</span>
        <span class="az-mc-sep"></span>
        <span class="az-iv-badge">IV: ${mc.iv.atm_iv_pct != null ? mc.iv.atm_iv_pct + '%' : 'N/A'} ${mc.iv.level.toUpperCase()}</span>
        <span class="az-mc-sep"></span>
        ${suggested
          ? `<span class="az-suggestion-badge">\u2605 ${esc(mc.suggestion.label)}</span>
             <span class="az-mc-reason">${esc(mc.suggestion.reason)}</span>`
          : ''}
        ${trendPick
          ? `<span class="az-mc-sep"></span>
             <span class="az-trend-pick-badge">${trendIcon} TREND: ${esc(mc.trend_pick.label)}</span>`
          : ''}
      </div>`;
  }

  results.innerHTML = `
    <div class="az-compare-header">
      <span class="az-ticker">${esc(ticker)}${getTickerName(ticker) ? `<span class="ticker-name">${esc(getTickerName(ticker))}</span>` : ''}</span>
      <span class="az-price">$${price.toFixed(2)}${formatPriceChange(price, prevClose, changePct)}</span>
      <span class="az-strategy-label" style="margin-left:12px;margin-bottom:0;">STRATEGY COMPARISON</span>
      <button class="btn-add-watchlist" onclick="addCompareToWatchlist()" title="Save best trade to Watchlist">&#9734; Save to Watchlist</button>
    </div>
    ${contextHtml}
    <div class="az-compare-grid">
      <div class="az-compare-card ${suggested === 'bull-put-spread' ? 'az-suggested' : ''} ${trendPick === 'bull-put-spread' ? 'az-trend-picked' : ''}">
        <div class="az-compare-title">Bull Put Spread${suggested === 'bull-put-spread' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}${trendPick === 'bull-put-spread' ? '<span class="az-trend-pick-tag">TREND PICK</span>' : ''}</div>
        ${bps.error ? `<div class="az-error">${esc(bps.error)}</div>` : `
        <div class="az-compare-legs">
          <div><span class="leg-action sell">SELL</span> $${bps.short_put.strike}P <span class="leg-oi">OI:${fmtOI(bps.short_put.oi)}</span> <span class="leg-vol">Vol:${fmtOI(bps.short_put.volume)}</span></div>
          <div><span class="leg-action buy">BUY</span> $${bps.long_put.strike}P <span class="leg-oi">OI:${fmtOI(bps.long_put.oi)}</span> <span class="leg-vol">Vol:${fmtOI(bps.long_put.volume)}</span></div>
        </div>
        <div class="az-compare-metrics">
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${bps.net_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit (mid)${bps.natural_credit != null ? ` <span class="natural-price">nat $${bps.natural_credit.toFixed(2)}</span>` : ''}</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Bull Put Spread' ? 'az-best' : ''}">${bps.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Bull Put Spread' ? 'az-best' : ''}">${bps.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${bps.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">$${bps.breakeven.toFixed(2)}</span><span class="az-cm-lbl">Breakeven</span></div>
          <div class="az-cm"><span class="az-cm-val">${bps.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('bull-put-spread', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['bull-put-spread'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('bull-put-spread')">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addCompareToWatchlist('bull-put-spread')" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'bear-call-spread' ? 'az-suggested' : ''} ${trendPick === 'bear-call-spread' ? 'az-trend-picked' : ''}">
        <div class="az-compare-title">Bear Call Spread${suggested === 'bear-call-spread' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}${trendPick === 'bear-call-spread' ? '<span class="az-trend-pick-tag">TREND PICK</span>' : ''}</div>
        ${bcs.error ? `<div class="az-error">${esc(bcs.error)}</div>` : `
        <div class="az-compare-legs">
          <div><span class="leg-action sell">SELL</span> $${bcs.short_call.strike}C <span class="leg-oi">OI:${fmtOI(bcs.short_call.oi)}</span> <span class="leg-vol">Vol:${fmtOI(bcs.short_call.volume)}</span></div>
          <div><span class="leg-action buy">BUY</span> $${bcs.long_call.strike}C <span class="leg-oi">OI:${fmtOI(bcs.long_call.oi)}</span> <span class="leg-vol">Vol:${fmtOI(bcs.long_call.volume)}</span></div>
        </div>
        <div class="az-compare-metrics">
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${bcs.net_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit (mid)${bcs.natural_credit != null ? ` <span class="natural-price">nat $${bcs.natural_credit.toFixed(2)}</span>` : ''}</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Bear Call Spread' ? 'az-best' : ''}">${bcs.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Bear Call Spread' ? 'az-best' : ''}">${bcs.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${bcs.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">$${bcs.breakeven.toFixed(2)}</span><span class="az-cm-lbl">Breakeven</span></div>
          <div class="az-cm"><span class="az-cm-val">${bcs.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('bear-call-spread', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['bear-call-spread'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('bear-call-spread')">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addCompareToWatchlist('bear-call-spread')" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'iron-condor' ? 'az-suggested' : ''} ${trendPick === 'iron-condor' ? 'az-trend-picked' : ''}">
        <div class="az-compare-title">Iron Condor${suggested === 'iron-condor' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}${trendPick === 'iron-condor' ? '<span class="az-trend-pick-tag">TREND PICK</span>' : ''}</div>
        ${ic.error ? `<div class="az-error">${esc(ic.error)}</div>` : `
        <div class="az-compare-legs">
          <div><span class="leg-action sell">SELL</span> $${ic.put_side.short_put.strike}P / $${ic.call_side.short_call.strike}C <span class="leg-oi">OI:${fmtOI(ic.put_side.short_put.oi + ic.call_side.short_call.oi)}</span></div>
          <div><span class="leg-action buy">BUY</span> $${ic.put_side.long_put.strike}P / $${ic.call_side.long_call.strike}C <span class="leg-oi">OI:${fmtOI(ic.put_side.long_put.oi + ic.call_side.long_call.oi)}</span></div>
        </div>
        <div class="az-compare-metrics">
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${ic.total_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit (mid)${ic.total_natural_credit != null ? ` <span class="natural-price">nat $${ic.total_natural_credit.toFixed(2)}</span>` : ''}</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Iron Condor' ? 'az-best' : ''}">${ic.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Iron Condor' ? 'az-best' : ''}">${ic.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${ic.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">${esc(ic.profit_zone)}</span><span class="az-cm-lbl">Profit Zone</span></div>
          <div class="az-cm"><span class="az-cm-val">${ic.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('iron-condor', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['iron-condor'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('iron-condor')">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addCompareToWatchlist('iron-condor')" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'covered-call' ? 'az-suggested' : ''} ${trendPick === 'covered-call' ? 'az-trend-picked' : ''}">
        <div class="az-compare-title">Covered Call${suggested === 'covered-call' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}${trendPick === 'covered-call' ? '<span class="az-trend-pick-tag">TREND PICK</span>' : ''}</div>
        ${cc.error ? `<div class="az-error">${esc(cc.error)}</div>` : `
        <div class="az-compare-legs">
          <div><span class="leg-action sell">SELL</span> $${cc.short_call.strike}C @ $${cc.premium_per_share.toFixed(2)} <span class="leg-oi">OI:${fmtOI(cc.short_call.oi)}</span> <span class="leg-vol">Vol:${fmtOI(cc.short_call.volume)}</span></div>
        </div>
        <div class="az-compare-metrics">
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${cc.premium_per_share.toFixed(2)}</span><span class="az-cm-lbl">Premium (mid)${cc.natural_premium != null ? ` <span class="natural-price">nat $${cc.natural_premium.toFixed(2)}</span>` : ''}</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Covered Call' ? 'az-best' : ''}">${cc.annualized_return_pct}%</span><span class="az-cm-lbl">Annualized</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Covered Call' ? 'az-best' : ''}">${(100 - cc.prob_called_pct).toFixed(1)}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.downside_protection_pct}%</span><span class="az-cm-lbl">Downside Prot.</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.called_away_return_pct}%</span><span class="az-cm-lbl">Called Away</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('covered-call', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['covered-call'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('covered-call')">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addCompareToWatchlist('covered-call')" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'cash-secured-put' ? 'az-suggested' : ''} ${trendPick === 'cash-secured-put' ? 'az-trend-picked' : ''}">
        <div class="az-compare-title">Cash-Secured Put${suggested === 'cash-secured-put' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}${trendPick === 'cash-secured-put' ? '<span class="az-trend-pick-tag">TREND PICK</span>' : ''}</div>
        ${csp.error || !csp.short_put ? `<div class="az-error">${esc(csp.error || 'No data')}</div>` : `
        <div class="az-compare-legs">
          <div><span class="leg-action sell">SELL</span> $${csp.short_put.strike}P @ $${csp.premium_per_share.toFixed(2)} <span class="leg-oi">OI:${fmtOI(csp.short_put.oi)}</span> <span class="leg-vol">Vol:${fmtOI(csp.short_put.volume)}</span></div>
        </div>
        <div class="az-compare-metrics">
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${csp.premium_per_share.toFixed(2)}</span><span class="az-cm-lbl">Premium (mid)${csp.natural_premium != null ? ` <span class="natural-price">nat $${csp.natural_premium.toFixed(2)}</span>` : ''}</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Cash-Secured Put' ? 'az-best' : ''}">${csp.annualized_return_pct}%</span><span class="az-cm-lbl">Annualized</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Cash-Secured Put' ? 'az-best' : ''}">${csp.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val">$${csp.effective_buy_price.toFixed(2)}</span><span class="az-cm-lbl">Eff. Buy Price</span></div>
          <div class="az-cm"><span class="az-cm-val">${csp.discount_pct}%</span><span class="az-cm-lbl">Discount</span></div>
          <div class="az-cm"><span class="az-cm-val">${csp.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('cash-secured-put', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['cash-secured-put'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('cash-secured-put')">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addCompareToWatchlist('cash-secured-put')" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
        `}
      </div>
    </div>`;

  // Store all results for "Add to Portfolio"
  lastAnalysis = {
    strategy: 'compare',
    data: { 'bull-put-spread': bps, 'bear-call-spread': bcs, 'iron-condor': ic, 'covered-call': cc, 'cash-secured-put': csp },
  };
}

function addCompareToPortfolio(strategy) {
  if (!lastAnalysis || lastAnalysis.strategy !== 'compare') return;
  const data = lastAnalysis.data[strategy];
  if (!data || data.error) return;
  addAnalysisToPortfolio(strategy, data);
}

function addCompareToWatchlist(strategy) {
  if (!lastAnalysis || lastAnalysis.strategy !== 'compare') return;
  if (strategy) {
    const data = lastAnalysis.data[strategy];
    if (!data || data.error) return;
    addToWatchlist(strategy, data);
  } else {
    const strategies = ['bull-put-spread', 'bear-call-spread', 'iron-condor', 'covered-call', 'cash-secured-put'];
    const first = strategies.find(s => lastAnalysis.data[s] && !lastAnalysis.data[s].error);
    if (first) addToWatchlist(first, lastAnalysis.data[first]);
  }
}

function addSingleToWatchlist() {
  if (!lastAnalysis || !lastAnalysis.strategy || lastAnalysis.strategy === 'compare') return;
  addToWatchlist(lastAnalysis.strategy, lastAnalysis.data);
}

function buildCompareChatPrompt(data) {
  const bps = data.bull_put_spread || {};
  const bcs = data.bear_call_spread || {};
  const ic = data.iron_condor || {};
  const cc = data.covered_call || {};
  const csp = data.cash_secured_put || {};
  const ticker = data.ticker;

  const expiry = bps.expiry || bcs.expiry || ic.expiry || cc.expiry || csp.expiry || '';
  const count = [bps, bcs, ic, cc, csp].filter(s => s.short_put || s.short_call || s.put_side).length;
  let prompt = `Compare these ${count} strategies for ${ticker}${expiry ? ` with expiry ${expiry}` : ''} and recommend which is best right now:\n\n`;
  if (bps.short_put && !bps.error) {
    prompt += `Bull Put Spread: sell $${bps.short_put.strike}P / buy $${bps.long_put.strike}P, credit $${bps.net_credit}, ${bps.return_on_risk_pct}% return, ${bps.prob_profit_pct}% prob profit, expiry ${bps.expiry} (${bps.dte} DTE)\n`;
  }
  if (bcs.short_call && !bcs.error) {
    prompt += `Bear Call Spread: sell $${bcs.short_call.strike}C / buy $${bcs.long_call.strike}C, credit $${bcs.net_credit}, ${bcs.return_on_risk_pct}% return, ${bcs.prob_profit_pct}% prob profit, expiry ${bcs.expiry} (${bcs.dte} DTE)\n`;
  }
  if (ic.put_side && !ic.error) {
    prompt += `Iron Condor: puts ${ic.put_side.short_put.strike}/${ic.put_side.long_put.strike}, calls ${ic.call_side.short_call.strike}/${ic.call_side.long_call.strike}, credit $${ic.total_credit}, ${ic.return_on_risk_pct}% return, ${ic.prob_profit_pct}% prob profit, expiry ${ic.expiry} (${ic.dte} DTE)\n`;
  }
  if (cc.short_call && !cc.error) {
    prompt += `Covered Call: sell $${cc.short_call.strike}C, premium $${cc.premium_per_share}, ${cc.annualized_return_pct}% annualized, ${cc.prob_called_pct}% prob called, expiry ${cc.expiry} (${cc.dte} DTE)\n`;
  }
  if (csp.short_put && !csp.error) {
    prompt += `Cash-Secured Put: sell $${csp.short_put.strike}P, premium $${csp.premium_per_share}, ${csp.return_on_capital_pct}% return on capital, ${csp.annualized_return_pct}% annualized, ${csp.prob_profit_pct}% prob profit, eff. buy $${csp.effective_buy_price}, expiry ${csp.expiry} (${csp.dte} DTE)\n`;
  }
  if (data.market_context && !data.market_context.error) {
    const mc = data.market_context;
    const t = mc.trend;
    const sign5d = t.change_5d_pct >= 0 ? '+' : '';
    const sign20d = t.change_20d_pct >= 0 ? '+' : '';
    prompt += `\nMarket Context:\n`;
    prompt += `- Trend: ${t.classification} (5d: ${sign5d}${t.change_5d_pct}%, 20d: ${sign20d}${t.change_20d_pct}%, 52w percentile: ${t.percentile_52w}%)\n`;
    prompt += `- ATM IV: ${mc.iv.atm_iv_pct}% (${mc.iv.level})\n`;
    prompt += `- Best by numbers: ${mc.suggestion.label} \u2014 ${mc.suggestion.reason}\n`;
    if (mc.trend_pick && mc.trend_pick.strategy !== mc.suggestion.strategy) {
      prompt += `- Trend pick: ${mc.trend_pick.label} \u2014 ${mc.trend_pick.reason}\n`;
    }
  }
  prompt += `\nWhich strategy fits best for ${ticker} given current conditions? Consider risk/reward, probability, and market outlook.`;
  return prompt;
}

function renderAnalysisResult(strategy, d) {
  lastAnalysis = { strategy, data: d };
  const results = document.getElementById('az-results');

  if (strategy === 'bull-put-spread') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}${getTickerName(d.ticker) ? `<span class="ticker-name">${esc(getTickerName(d.ticker))}</span>` : ''}</span>
            <span class="az-price">$${d.price.toFixed(2)}${formatPriceChange(d.price, d.prev_close, d.change_pct)}</span>
          </div>
          <div class="az-expiry">${esc(d.expiry)} · ${d.dte} DTE</div>
        </div>
        <div class="az-strategy-label">Bull Put Spread</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${d.short_put.strike} P</td>
            <td class="leg-delta">Δ ${d.short_put.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${d.short_put.iv_pct}%</td>
            <td class="leg-bid-ask">${d.short_put.bid.toFixed(2)} / ${d.short_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.short_put.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.short_put.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.short_put.volume)}</td>
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${d.long_put.strike} P</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${d.long_put.bid.toFixed(2)} / ${d.long_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.long_put.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.long_put.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.long_put.volume)}</td>
          </tr>
        </table>
        <div class="az-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${d.net_credit.toFixed(2)}</div>
            <div class="metric-label">Net Credit (mid)${d.natural_credit != null ? `<br><span class="natural-price">nat $${d.natural_credit.toFixed(2)}</span>` : ''}</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.max_profit.toFixed(0)}</div>
            <div class="metric-label">Max Profit</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-negative)">$${d.max_loss.toFixed(0)}</div>
            <div class="metric-label">Max Loss</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.breakeven.toFixed(2)}</div>
            <div class="metric-label">Breakeven</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.return_on_risk_pct}%</div>
            <div class="metric-label">Return/Risk</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.prob_profit_pct}%</div>
            <div class="metric-label">Prob Profit</div>
          </div>
        </div>
        <div class="az-actions">
          <button class="btn-view-chain" onclick="viewChain()">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addAnalysisToPortfolio()">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addSingleToWatchlist()" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
      </div>`;
  } else if (strategy === 'bear-call-spread') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}${getTickerName(d.ticker) ? `<span class="ticker-name">${esc(getTickerName(d.ticker))}</span>` : ''}</span>
            <span class="az-price">$${d.price.toFixed(2)}${formatPriceChange(d.price, d.prev_close, d.change_pct)}</span>
          </div>
          <div class="az-expiry">${esc(d.expiry)} · ${d.dte} DTE</div>
        </div>
        <div class="az-strategy-label">Bear Call Spread</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${d.short_call.strike} C</td>
            <td class="leg-delta">Δ ${d.short_call.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${d.short_call.iv_pct}%</td>
            <td class="leg-bid-ask">${d.short_call.bid.toFixed(2)} / ${d.short_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.short_call.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.short_call.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.short_call.volume)}</td>
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${d.long_call.strike} C</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${d.long_call.bid.toFixed(2)} / ${d.long_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.long_call.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.long_call.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.long_call.volume)}</td>
          </tr>
        </table>
        <div class="az-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${d.net_credit.toFixed(2)}</div>
            <div class="metric-label">Net Credit (mid)${d.natural_credit != null ? `<br><span class="natural-price">nat $${d.natural_credit.toFixed(2)}</span>` : ''}</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.max_profit.toFixed(0)}</div>
            <div class="metric-label">Max Profit</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-negative)">$${d.max_loss.toFixed(0)}</div>
            <div class="metric-label">Max Loss</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.breakeven.toFixed(2)}</div>
            <div class="metric-label">Breakeven</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.return_on_risk_pct}%</div>
            <div class="metric-label">Return/Risk</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.prob_profit_pct}%</div>
            <div class="metric-label">Prob Profit</div>
          </div>
        </div>
        <div class="az-actions">
          <button class="btn-view-chain" onclick="viewChain()">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addAnalysisToPortfolio()">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addSingleToWatchlist()" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
      </div>`;
  } else if (strategy === 'iron-condor') {
    const ps = d.put_side, cs = d.call_side;
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}${getTickerName(d.ticker) ? `<span class="ticker-name">${esc(getTickerName(d.ticker))}</span>` : ''}</span>
            <span class="az-price">$${d.price.toFixed(2)}${formatPriceChange(d.price, d.prev_close, d.change_pct)}</span>
          </div>
          <div class="az-expiry">${esc(d.expiry)} · ${d.dte} DTE</div>
        </div>
        <div class="az-strategy-label">Iron Condor</div>
        <div class="az-side-label">Put Side · $${ps.credit.toFixed(2)} credit</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${ps.short_put.strike} P</td>
            <td class="leg-delta">Δ ${ps.short_put.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${ps.short_put.iv_pct}%</td>
            <td class="leg-bid-ask">${ps.short_put.bid.toFixed(2)} / ${ps.short_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${ps.short_put.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(ps.short_put.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(ps.short_put.volume)}</td>
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${ps.long_put.strike} P</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${ps.long_put.bid.toFixed(2)} / ${ps.long_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${ps.long_put.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(ps.long_put.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(ps.long_put.volume)}</td>
          </tr>
        </table>
        <div class="az-side-label">Call Side · $${cs.credit.toFixed(2)} credit</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${cs.short_call.strike} C</td>
            <td class="leg-delta">Δ ${cs.short_call.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${cs.short_call.iv_pct}%</td>
            <td class="leg-bid-ask">${cs.short_call.bid.toFixed(2)} / ${cs.short_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${cs.short_call.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(cs.short_call.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(cs.short_call.volume)}</td>
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${cs.long_call.strike} C</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${cs.long_call.bid.toFixed(2)} / ${cs.long_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${cs.long_call.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(cs.long_call.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(cs.long_call.volume)}</td>
          </tr>
        </table>
        <div class="az-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${d.total_credit.toFixed(2)}</div>
            <div class="metric-label">Total Credit (mid)${d.total_natural_credit != null ? `<br><span class="natural-price">nat $${d.total_natural_credit.toFixed(2)}</span>` : ''}</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.max_profit.toFixed(0)}</div>
            <div class="metric-label">Max Profit</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-negative)">$${d.max_loss.toFixed(0)}</div>
            <div class="metric-label">Max Loss</div>
          </div>
          <div class="metric">
            <div class="metric-value">${esc(d.profit_zone)}</div>
            <div class="metric-label">Profit Zone</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.return_on_risk_pct}%</div>
            <div class="metric-label">Return/Risk</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.prob_profit_pct}%</div>
            <div class="metric-label">Prob Profit</div>
          </div>
        </div>
        <div class="az-actions">
          <button class="btn-view-chain" onclick="viewChain()">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addAnalysisToPortfolio()">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addSingleToWatchlist()" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
      </div>`;
  } else if (strategy === 'covered-call') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}${getTickerName(d.ticker) ? `<span class="ticker-name">${esc(getTickerName(d.ticker))}</span>` : ''}</span>
            <span class="az-price">$${d.stock_price.toFixed(2)}${formatPriceChange(d.stock_price, d.prev_close, d.change_pct)}</span>
          </div>
          <div class="az-expiry">${esc(d.expiry)} · ${d.dte} DTE</div>
        </div>
        <div class="az-strategy-label">Covered Call</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${d.short_call.strike} C</td>
            <td class="leg-delta">Δ ${d.short_call.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${d.short_call.iv_pct}%</td>
            <td class="leg-bid-ask">${d.short_call.bid.toFixed(2)} / ${d.short_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.short_call.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.short_call.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.short_call.volume)}</td>
          </tr>
        </table>
        <div class="az-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${d.premium_per_share.toFixed(2)}</div>
            <div class="metric-label">Premium (mid)${d.natural_premium != null ? `<br><span class="natural-price">nat $${d.natural_premium.toFixed(2)}</span>` : ''}</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.static_return_pct}%</div>
            <div class="metric-label">Static Return</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.annualized_return_pct}%</div>
            <div class="metric-label">Annualized</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.downside_protection_pct}%</div>
            <div class="metric-label">Downside Prot.</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.called_away_return_pct}%</div>
            <div class="metric-label">Called Away</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.prob_called_pct}%</div>
            <div class="metric-label">Prob Called</div>
          </div>
        </div>
        <div class="az-actions">
          <button class="btn-view-chain" onclick="viewChain()">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addAnalysisToPortfolio()">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addSingleToWatchlist()" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
      </div>`;
  } else if (strategy === 'cash-secured-put') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}${getTickerName(d.ticker) ? `<span class="ticker-name">${esc(getTickerName(d.ticker))}</span>` : ''}</span>
            <span class="az-price">$${d.stock_price.toFixed(2)}${formatPriceChange(d.stock_price, d.prev_close, d.change_pct)}</span>
          </div>
          <div class="az-expiry">${esc(d.expiry)} · ${d.dte} DTE</div>
        </div>
        <div class="az-strategy-label">Cash-Secured Put</div>
        <table class="az-legs-table">
          <tr>
            <td class="leg-action sell">SELL</td>
            <td class="leg-strike">$${d.short_put.strike} P</td>
            <td class="leg-delta">Δ ${d.short_put.delta.toFixed(2)}</td>
            <td class="leg-iv">IV ${d.short_put.iv_pct}%</td>
            <td class="leg-bid-ask">${d.short_put.bid.toFixed(2)} / ${d.short_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.short_put.mid.toFixed(2)}</td>
            <td class="leg-oi">OI ${fmtOI(d.short_put.oi)}</td>
            <td class="leg-vol">Vol ${fmtOI(d.short_put.volume)}</td>
          </tr>
        </table>
        <div class="az-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${d.premium_per_share.toFixed(2)}</div>
            <div class="metric-label">Premium (mid)${d.natural_premium != null ? `<br><span class="natural-price">nat $${d.natural_premium.toFixed(2)}</span>` : ''}</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.return_on_capital_pct}%</div>
            <div class="metric-label">Return/Capital</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.annualized_return_pct}%</div>
            <div class="metric-label">Annualized</div>
          </div>
          <div class="metric">
            <div class="metric-value">$${d.effective_buy_price.toFixed(2)}</div>
            <div class="metric-label">Eff. Buy Price</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.discount_pct}%</div>
            <div class="metric-label">Discount</div>
          </div>
          <div class="metric">
            <div class="metric-value">${d.prob_profit_pct}%</div>
            <div class="metric-label">Prob Profit</div>
          </div>
        </div>
        <div class="az-cash-required">Cash Required: $${d.cash_required.toFixed(0)} per contract</div>
        <div class="az-actions">
          <button class="btn-view-chain" onclick="viewChain()">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addAnalysisToPortfolio()">Add to Portfolio</button>
          <button class="btn-add-watchlist" onclick="addSingleToWatchlist()" title="Save to Watchlist">&#9734; Save to Watchlist</button>
        </div>
      </div>`;
  }
}

function addAnalysisToPortfolio(strategyOverride, dataOverride) {
  const strategy = strategyOverride || (lastAnalysis && lastAnalysis.strategy);
  const data = dataOverride || (lastAnalysis && lastAnalysis.data);
  if (!strategy || !data) return;

  // Pre-fill the add position form
  const form = document.getElementById('position-form');
  document.getElementById('modal-title').textContent = 'New Position';
  form.reset();
  form.querySelector('[name="edit_index"]').value = '';
  form.querySelector('[name="strategy"]').value = strategy;
  form.querySelector('[name="ticker"]').value = data.ticker;
  form.querySelector('[name="expiry"]').value = data.expiry;
  const expMonth = new Date(data.expiry + 'T00:00:00').toLocaleString('en', { month: 'short' });
  form.querySelector('[name="label"]').value = `${data.ticker} ${expMonth} ${formatStrategy(strategy)}`;

  updateLegFields(strategy);

  if (strategy === 'bull-put-spread') {
    form.querySelector('[name="short_put_strike"]').value = data.short_put.strike;
    form.querySelector('[name="short_put_price"]').value = data.short_put.mid;
    form.querySelector('[name="long_put_strike"]').value = data.long_put.strike;
    form.querySelector('[name="long_put_price"]').value = data.long_put.mid;
    form.querySelector('[name="net_credit"]').value = data.net_credit;
  } else if (strategy === 'bear-call-spread') {
    form.querySelector('[name="short_call_strike"]').value = data.short_call.strike;
    form.querySelector('[name="short_call_price"]').value = data.short_call.mid;
    form.querySelector('[name="long_call_strike"]').value = data.long_call.strike;
    form.querySelector('[name="long_call_price"]').value = data.long_call.mid;
    form.querySelector('[name="net_credit"]').value = data.net_credit;
  } else if (strategy === 'iron-condor') {
    form.querySelector('[name="short_put_strike"]').value = data.put_side.short_put.strike;
    form.querySelector('[name="short_put_price"]').value = data.put_side.short_put.mid;
    form.querySelector('[name="long_put_strike"]').value = data.put_side.long_put.strike;
    form.querySelector('[name="long_put_price"]').value = data.put_side.long_put.mid;
    form.querySelector('[name="short_call_strike"]').value = data.call_side.short_call.strike;
    form.querySelector('[name="short_call_price"]').value = data.call_side.short_call.mid;
    form.querySelector('[name="long_call_strike"]').value = data.call_side.long_call.strike;
    form.querySelector('[name="long_call_price"]').value = data.call_side.long_call.mid;
    form.querySelector('[name="net_credit"]').value = data.total_credit;
  } else if (strategy === 'covered-call') {
    form.querySelector('[name="call_strike"]').value = data.short_call.strike;
    form.querySelector('[name="call_price"]').value = data.short_call.mid;
    form.querySelector('[name="net_credit"]').value = data.premium_per_share;
  } else if (strategy === 'cash-secured-put') {
    form.querySelector('[name="csp_put_strike"]').value = data.short_put.strike;
    form.querySelector('[name="csp_put_price"]').value = data.short_put.mid;
    form.querySelector('[name="net_credit"]').value = data.premium_per_share;
  }

  document.getElementById('modal-overlay').style.display = 'flex';
}


// ── Chain Viewer ────────────────────────────────────────────────────────────

function extractHighlightStrikes(strategy, data) {
  const strikes = new Set();
  if (strategy === 'bull-put-spread') {
    strikes.add(data.short_put.strike);
    strikes.add(data.long_put.strike);
  } else if (strategy === 'iron-condor') {
    strikes.add(data.put_side.short_put.strike);
    strikes.add(data.put_side.long_put.strike);
    strikes.add(data.call_side.short_call.strike);
    strikes.add(data.call_side.long_call.strike);
  } else if (strategy === 'covered-call') {
    strikes.add(data.short_call.strike);
  } else if (strategy === 'cash-secured-put') {
    strikes.add(data.short_put.strike);
  }
  return strikes;
}

function renderChainTable(chain, side, highlights) {
  const container = document.getElementById('az-chain-container');

  function buildTable(rows, label) {
    if (!rows || rows.length === 0) return `<div class="az-chain-empty">No ${esc(label)} data available</div>`;
    let html = `<div class="az-chain-section">
      <div class="az-chain-section-label">${esc(label)}</div>
      <div class="az-chain-scroll">
      <table class="az-chain-table">
        <thead><tr>
          <th>Strike</th><th>Bid</th><th>Ask</th><th>Mid</th>
          <th>Vol</th><th>OI</th><th>IV%</th><th>Delta</th>
        </tr></thead><tbody>`;
    const fx = (v, d) => v == null ? '--' : v.toFixed(d);
    for (const r of rows) {
      const hl = highlights.has(r.strike) ? ' class="az-chain-highlight"' : '';
      html += `<tr${hl}>
        <td class="chain-strike">${fx(r.strike, 1)}</td>
        <td>${fx(r.bid, 2)}</td><td>${fx(r.ask, 2)}</td>
        <td>${fx(r.mid, 2)}</td>
        <td>${r.volume ?? '--'}</td><td>${r.open_interest != null ? r.open_interest.toLocaleString() : '--'}</td>
        <td>${fx(r.iv_pct, 1)}</td><td>${fx(r.delta, 3)}</td>
      </tr>`;
    }
    html += '</tbody></table></div></div>';
    return html;
  }

  let body = '';
  if (side === 'puts' || side === 'both') body += buildTable(chain.puts, 'PUTS');
  if (side === 'calls' || side === 'both') body += buildTable(chain.calls, 'CALLS');

  container.innerHTML = `
    <div class="az-chain-header">
      <span>Option Chain &mdash; ${esc(chain.ticker)} $${(chain.price || 0).toFixed(2)}${formatPriceChange(chain.price, chain.prev_close, chain.change_pct)} &middot; ${esc(chain.expiry)} &middot; ${chain.dte} DTE</span>
      <button class="az-chain-close" onclick="document.getElementById('az-chain-container').remove()">&times;</button>
    </div>
    ${body}`;
}

async function viewChain(strategyOverride, dataOverride) {
  const strategy = strategyOverride || (lastAnalysis && lastAnalysis.strategy);
  const data = dataOverride || (lastAnalysis && lastAnalysis.data);
  if (!strategy || !data || data.error) return;

  const sideMap = {
    'bull-put-spread': 'puts',
    'bear-call-spread': 'calls',
    'cash-secured-put': 'puts',
    'covered-call': 'calls',
    'iron-condor': 'both',
  };
  const side = sideMap[strategy] || 'both';
  const ticker = data.ticker;
  const expiry = data.expiry;
  const highlights = extractHighlightStrikes(strategy, data);

  // Remove any existing chain display before loading new one
  const existing = document.getElementById('az-chain-container');
  if (existing) existing.remove();

  // Show loading
  const resultsEl = document.getElementById('az-results');
  const loadingDiv = document.createElement('div');
  loadingDiv.id = 'az-chain-container';
  loadingDiv.dataset.strategy = strategy;
  loadingDiv.innerHTML = '<div class="az-chain-loading">Loading option chain...</div>';
  resultsEl.appendChild(loadingDiv);

  try {
    const resp = await fetch('/api/chain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, expiry, side }),
    });
    const chain = await resp.json();
    if (chain.error) throw new Error(chain.error);
    if (chain.detail) throw new Error(chain.detail);
    renderChainTable(chain, side, highlights);
  } catch (err) {
    loadingDiv.innerHTML = `<div class="az-chain-error">${esc(err.message)}</div>`;
  }
}
