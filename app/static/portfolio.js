// ── Portfolio ───────────────────────────────────────────────────────────────

let portfolio = [];

async function loadPortfolio() {
  try {
    const res = await fetch('/api/portfolio');
    portfolio = await res.json();
    renderPortfolio();
  } catch (err) {
    console.error('Failed to load portfolio:', err);
  }
}

function renderPortfolio() {
  const grid = document.getElementById('positions-grid');
  const empty = document.getElementById('empty-state');
  const summary = document.getElementById('portfolio-summary');

  const openPositions = portfolio.filter(p => p.status === 'open');

  if (portfolio.length === 0) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    summary.innerHTML = '';
    return;
  }

  empty.style.display = 'none';

  // Summary stats
  const strategies = {};
  openPositions.forEach(p => {
    strategies[p.strategy] = (strategies[p.strategy] || 0) + 1;
  });

  summary.innerHTML = `
    <div class="summary-stat">
      <div class="stat-value">${openPositions.length}</div>
      <div class="stat-label">Open</div>
    </div>
    <div class="summary-stat">
      <div class="stat-value">${portfolio.length - openPositions.length}</div>
      <div class="stat-label">Closed</div>
    </div>
    <div class="summary-stat">
      <div class="stat-value">${Object.keys(strategies).length}</div>
      <div class="stat-label">Strategies</div>
    </div>
  `;

  // Position cards
  grid.innerHTML = portfolio.map((p, i) => {
    const legsStr = formatLegs(p);
    const dteStr = formatDTE(p.expiry);
    const isClosed = p.status === 'closed';
    const zone = p.zone || null;
    const zoneClass = zone ? zone.toLowerCase().replace(' ', '-').replace('act now', 'act') : '';
    const zoneUpdated = p.zone_updated ? formatTimeAgo(p.zone_updated) : null;
    const pnl = p.pnl_per_contract;
    const buffer = p.buffer_pct;
    const suggestion = p.suggestion || null;
    const contracts = p.contracts || 1;
    const maxLoss = computeMaxLoss(p);
    const maxProfit = p.net_credit * 100 * contracts;
    const capturedPct = (pnl != null && maxProfit > 0) ? Math.round((pnl / (maxProfit / contracts)) * 100) : null;

    // Chain data from last check
    const cd = p.chain_data || {};
    const isIC = p.strategy === 'iron-condor';
    const isSingleLeg = (p.strategy === 'covered-call' || p.strategy === 'cash-secured-put');
    let shortLeg, longLeg, costToClose;
    if (isIC) {
      const ws = p.worst_side || 'put';
      const side = ws === 'put' ? (cd.put_side || {}) : (cd.call_side || {});
      shortLeg = side.short_leg || {};
      longLeg = side.long_leg || {};
      costToClose = cd.cost_to_close;
    } else {
      shortLeg = cd.short_leg || {};
      longLeg = cd.long_leg || {};
      costToClose = cd.cost_to_close;
    }
    const hasChainData = shortLeg.iv_pct != null || costToClose != null;

    return `
      <div class="position-card ${isClosed ? 'closed' : ''} ${zone ? 'zone-' + zoneClass : ''}" style="animation-delay: ${i * 0.05}s" id="card-${i}">
        <div class="card-top">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="card-ticker">${esc(p.ticker)}${p.stock_price ? ` <span style="font-weight:400;font-size:0.85em;color:var(--text-muted)">$${p.stock_price.toFixed(2)}</span>` : ''}</div>
              ${zone && !isClosed ? `
                <div class="zone-info">
                  <span class="zone-dot ${zoneClass}"></span>
                  <span class="zone-label ${zoneClass}">${esc(zone)}</span>
                </div>
              ` : ''}
            </div>
            <div class="card-label">${esc(p.label)}</div>
            <div class="card-legs">${esc(legsStr)}</div>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
            <span class="card-strategy">${esc(formatStrategy(p.strategy))}</span>
            ${isClosed ? '<span class="zone-badge" style="color:var(--text-muted);border-color:var(--border);">CLOSED</span>' : ''}
            ${zoneUpdated && !isClosed ? `<span class="zone-updated">${esc(zoneUpdated)}</span>` : ''}
          </div>
        </div>
        <div class="card-metrics">
          <div class="metric">
            <div class="metric-value">$${p.net_credit.toFixed(2)}</div>
            <div class="metric-label">Credit</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="${pnl != null ? (pnl >= 0 ? 'color:var(--pnl-positive)' : 'color:var(--pnl-negative)') : ''}">${pnl != null ? (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(0) : '--'}</div>
            <div class="metric-label">P&L</div>
          </div>
          <div class="metric">
            <div class="metric-value">${buffer != null ? buffer.toFixed(1) + '%' : '--'}</div>
            <div class="metric-label">Buffer</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-negative)">${maxLoss != null ? '$' + maxLoss.toFixed(0) : '--'}</div>
            <div class="metric-label">Max Loss</div>
          </div>
          <div class="metric">
            <div class="metric-value">${contracts}</div>
            <div class="metric-label">Contracts</div>
          </div>
          <div class="metric">
            <div class="metric-value">${dteStr || '--'}</div>
            <div class="metric-label">DTE</div>
          </div>
          <div class="metric">
            <div class="metric-value" style="${capturedPct != null ? (capturedPct >= 50 ? 'color:var(--pnl-positive)' : '') : ''}">${capturedPct != null ? capturedPct + '%' : '--'}</div>
            <div class="metric-label">Captured</div>
          </div>
        </div>
        ${!isClosed && hasChainData ? `
        <div class="card-metrics chain-metrics">
          <div class="metric">
            <div class="metric-value">${costToClose != null ? '$' + costToClose.toFixed(0) : '--'}</div>
            <div class="metric-label">Close Cost</div>
          </div>
          <div class="metric">
            <div class="metric-value">${shortLeg.iv_pct != null ? shortLeg.iv_pct.toFixed(0) + '%' : '--'}</div>
            <div class="metric-label">IV</div>
          </div>
          <div class="metric">
            <div class="metric-value">${shortLeg.delta != null ? shortLeg.delta.toFixed(2) : '--'}</div>
            <div class="metric-label">Delta</div>
          </div>
          <div class="metric">
            <div class="metric-value">${shortLeg.volume != null ? (shortLeg.volume > 999 ? (shortLeg.volume/1000).toFixed(1)+'k' : shortLeg.volume) : '--'}/${shortLeg.open_interest != null ? fmtOI(shortLeg.open_interest) : '--'}</div>
            <div class="metric-label">Vol/OI (short)</div>
          </div>
          ${!isSingleLeg ? `
          <div class="metric">
            <div class="metric-value">${longLeg.volume != null ? (longLeg.volume > 999 ? (longLeg.volume/1000).toFixed(1)+'k' : longLeg.volume) : '--'}/${longLeg.open_interest != null ? fmtOI(longLeg.open_interest) : '--'}</div>
            <div class="metric-label">Vol/OI (long)</div>
          </div>
          ` : ''}
        </div>
        ` : ''}
        ${suggestion && !isClosed ? `<div class="card-suggestion ${zoneClass}">${esc(suggestion)}</div>` : ''}
        <div class="card-actions">
          <button class="card-btn" onclick="editPosition(${i})">Edit</button>
          ${!isClosed ? `<button class="card-btn" onclick="checkPosition(${i})">Check</button>` : ''}
          ${!isClosed ? `<button class="card-btn" onclick="closePosition(${i})">Close</button>` : `<button class="card-btn" onclick="reopenPosition(${i})">Reopen</button>`}
          <button class="card-btn danger" onclick="deletePosition(${i})">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

// ── Check All Positions ─────────────────────────────────────────────────────

async function checkAllPositions() {
  const btn = document.getElementById('btn-check-all');
  btn.disabled = true;
  btn.classList.add('checking');
  btn.innerHTML = '<span>&#8635;</span> Checking...';

  try {
    const res = await fetch('/api/portfolio/check', { method: 'POST' });
    if (!res.ok) throw new Error('Check failed');
    await loadPortfolio();
  } catch (err) {
    alert('Failed to check positions: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove('checking');
    btn.innerHTML = '<span>&#8635;</span> Check All';
  }
}

// ── Check Position (sends to chat) ──────────────────────────────────────────

async function checkPosition(index) {
  const p = portfolio[index];
  const aiEnabled = document.getElementById('ai-toggle').checked;

  // 1. Run monitor script silently → update badge immediately
  const card = document.getElementById('card-' + index);
  if (card) {
    const dot = card.querySelector('.zone-dot');
    if (dot) dot.className = 'zone-dot checking';
  }

  // Always run the script check
  fetch(`/api/portfolio/${p.id}/check`, { method: 'POST' })
    .then(() => loadPortfolio())
    .catch(() => {});

  // 2. Only send to chat if AI is enabled
  if (!aiEnabled) return;

  let prompt = '';

  if (p.strategy === 'bull-put-spread') {
    const short = p.legs.find(l => l.action === 'sell');
    const long = p.legs.find(l => l.action === 'buy');
    prompt = `Check my ${p.ticker} ${short.strike}/${long.strike} bull put spread, credit $${p.net_credit}, expires ${p.expiry}`;
  } else if (p.strategy === 'iron-condor') {
    const sp = p.legs.find(l => l.type === 'put' && l.action === 'sell');
    const lp = p.legs.find(l => l.type === 'put' && l.action === 'buy');
    const sc = p.legs.find(l => l.type === 'call' && l.action === 'sell');
    const lc = p.legs.find(l => l.type === 'call' && l.action === 'buy');
    prompt = `Check my ${p.ticker} iron condor: ${sp.strike}/${lp.strike} puts, ${sc.strike}/${lc.strike} calls, credit $${p.net_credit}, expires ${p.expiry}`;
  } else if (p.strategy === 'covered-call') {
    const call = p.legs.find(l => l.type === 'call');
    prompt = `Check my ${p.ticker} covered call, sold $${call.strike} call for $${p.net_credit}, expires ${p.expiry}` +
      (p.cost_basis ? `, I bought shares at $${p.cost_basis}` : '');
  } else if (p.strategy === 'cash-secured-put') {
    const put = p.legs.find(l => l.type === 'put');
    prompt = `Check my ${p.ticker} cash-secured put, sold $${put.strike} put for $${p.net_credit}, expires ${p.expiry}`;
  }

  inputEl.value = prompt;
  sendMessage();
}

// ── Add/Edit Modal ──────────────────────────────────────────────────────────

function showAddForm() {
  document.getElementById('modal-title').textContent = 'New Position';
  document.getElementById('position-form').reset();
  document.querySelector('[name="edit_index"]').value = '';
  updateLegFields('bull-put-spread');
  document.getElementById('modal-overlay').style.display = 'flex';
}

function editPosition(index) {
  const p = portfolio[index];
  document.getElementById('modal-title').textContent = 'Edit Position';
  const form = document.getElementById('position-form');

  form.querySelector('[name="label"]').value = p.label;
  form.querySelector('[name="strategy"]').value = p.strategy;
  form.querySelector('[name="ticker"]').value = p.ticker;
  form.querySelector('[name="expiry"]').value = p.expiry;
  form.querySelector('[name="contracts"]').value = p.contracts || 1;
  form.querySelector('[name="net_credit"]').value = p.net_credit;
  form.querySelector('[name="status"]').value = p.status;
  form.querySelector('[name="edit_index"]').value = index;

  updateLegFields(p.strategy);

  // Fill leg fields
  if (p.strategy === 'bull-put-spread') {
    const short = p.legs.find(l => l.action === 'sell');
    const long = p.legs.find(l => l.action === 'buy');
    form.querySelector('[name="short_put_strike"]').value = short.strike;
    form.querySelector('[name="short_put_price"]').value = short.price || '';
    form.querySelector('[name="long_put_strike"]').value = long.strike;
    form.querySelector('[name="long_put_price"]').value = long.price || '';
  } else if (p.strategy === 'bear-call-spread') {
    const short = p.legs.find(l => l.action === 'sell');
    const long = p.legs.find(l => l.action === 'buy');
    form.querySelector('[name="short_call_strike"]').value = short.strike;
    form.querySelector('[name="short_call_price"]').value = short.price || '';
    form.querySelector('[name="long_call_strike"]').value = long.strike;
    form.querySelector('[name="long_call_price"]').value = long.price || '';
  } else if (p.strategy === 'iron-condor') {
    const sp = p.legs.find(l => l.type === 'put' && l.action === 'sell');
    const lp = p.legs.find(l => l.type === 'put' && l.action === 'buy');
    const sc = p.legs.find(l => l.type === 'call' && l.action === 'sell');
    const lc = p.legs.find(l => l.type === 'call' && l.action === 'buy');
    form.querySelector('[name="short_put_strike"]').value = sp.strike;
    form.querySelector('[name="short_put_price"]').value = sp.price || '';
    form.querySelector('[name="long_put_strike"]').value = lp.strike;
    form.querySelector('[name="long_put_price"]').value = lp.price || '';
    form.querySelector('[name="short_call_strike"]').value = sc.strike;
    form.querySelector('[name="short_call_price"]').value = sc.price || '';
    form.querySelector('[name="long_call_strike"]').value = lc.strike;
    form.querySelector('[name="long_call_price"]').value = lc.price || '';
  } else if (p.strategy === 'covered-call') {
    const call = p.legs.find(l => l.type === 'call');
    form.querySelector('[name="call_strike"]').value = call.strike;
    form.querySelector('[name="call_price"]').value = call.price || '';
    if (p.cost_basis) form.querySelector('[name="cost_basis"]').value = p.cost_basis;
  } else if (p.strategy === 'cash-secured-put') {
    const put = p.legs.find(l => l.type === 'put');
    form.querySelector('[name="csp_put_strike"]').value = put.strike;
    form.querySelector('[name="csp_put_price"]').value = put.price || '';
  }

  document.getElementById('modal-overlay').style.display = 'flex';
}

function closeModal(event) {
  if (event && event.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').style.display = 'none';
}

function updateLegFields(strategy) {
  const container = document.getElementById('leg-fields');
  const costBasisGroup = document.getElementById('cost-basis-group');

  if (strategy === 'bull-put-spread') {
    costBasisGroup.style.display = 'none';
    container.innerHTML = `
      <div class="form-section-label">Legs</div>
      <div class="form-row">
        <div class="form-group"><label>Short Put Strike</label><input type="number" name="short_put_strike" step="0.5" required></div>
        <div class="form-group"><label>Short Put Price</label><input type="number" name="short_put_price" step="0.01"></div>
        <div class="form-group"><label>Long Put Strike</label><input type="number" name="long_put_strike" step="0.5" required></div>
        <div class="form-group"><label>Long Put Price</label><input type="number" name="long_put_price" step="0.01"></div>
      </div>`;
  } else if (strategy === 'bear-call-spread') {
    costBasisGroup.style.display = 'none';
    container.innerHTML = `
      <div class="form-section-label">Legs</div>
      <div class="form-row">
        <div class="form-group"><label>Short Call Strike</label><input type="number" name="short_call_strike" step="0.5" required></div>
        <div class="form-group"><label>Short Call Price</label><input type="number" name="short_call_price" step="0.01"></div>
        <div class="form-group"><label>Long Call Strike</label><input type="number" name="long_call_strike" step="0.5" required></div>
        <div class="form-group"><label>Long Call Price</label><input type="number" name="long_call_price" step="0.01"></div>
      </div>`;
  } else if (strategy === 'iron-condor') {
    costBasisGroup.style.display = 'none';
    container.innerHTML = `
      <div class="form-section-label">Put Side</div>
      <div class="form-row">
        <div class="form-group"><label>Short Put Strike</label><input type="number" name="short_put_strike" step="0.5" required></div>
        <div class="form-group"><label>Short Put Price</label><input type="number" name="short_put_price" step="0.01"></div>
        <div class="form-group"><label>Long Put Strike</label><input type="number" name="long_put_strike" step="0.5" required></div>
        <div class="form-group"><label>Long Put Price</label><input type="number" name="long_put_price" step="0.01"></div>
      </div>
      <div class="form-section-label">Call Side</div>
      <div class="form-row">
        <div class="form-group"><label>Short Call Strike</label><input type="number" name="short_call_strike" step="0.5" required></div>
        <div class="form-group"><label>Short Call Price</label><input type="number" name="short_call_price" step="0.01"></div>
        <div class="form-group"><label>Long Call Strike</label><input type="number" name="long_call_strike" step="0.5" required></div>
        <div class="form-group"><label>Long Call Price</label><input type="number" name="long_call_price" step="0.01"></div>
      </div>`;
  } else if (strategy === 'covered-call') {
    costBasisGroup.style.display = 'block';
    container.innerHTML = `
      <div class="form-section-label">Leg</div>
      <div class="form-row">
        <div class="form-group"><label>Call Strike</label><input type="number" name="call_strike" step="0.5" required></div>
        <div class="form-group"><label>Call Price</label><input type="number" name="call_price" step="0.01"></div>
      </div>`;
  } else if (strategy === 'cash-secured-put') {
    costBasisGroup.style.display = 'none';
    container.innerHTML = `
      <div class="form-section-label">Leg</div>
      <div class="form-row">
        <div class="form-group"><label>Put Strike</label><input type="number" name="csp_put_strike" step="0.5" required></div>
        <div class="form-group"><label>Put Price</label><input type="number" name="csp_put_price" step="0.01"></div>
      </div>`;
  }
}

async function savePosition(event) {
  event.preventDefault();
  const form = event.target;
  const strategy = form.querySelector('[name="strategy"]').value;
  const editIndex = form.querySelector('[name="edit_index"]').value;

  // Build legs
  let legs = [];
  if (strategy === 'bull-put-spread') {
    legs = [
      { type: 'put', action: 'sell', strike: parseFloat(form.querySelector('[name="short_put_strike"]').value), price: parseFloat(form.querySelector('[name="short_put_price"]').value) || undefined },
      { type: 'put', action: 'buy', strike: parseFloat(form.querySelector('[name="long_put_strike"]').value), price: parseFloat(form.querySelector('[name="long_put_price"]').value) || undefined },
    ];
  } else if (strategy === 'bear-call-spread') {
    legs = [
      { type: 'call', action: 'sell', strike: parseFloat(form.querySelector('[name="short_call_strike"]').value), price: parseFloat(form.querySelector('[name="short_call_price"]').value) || undefined },
      { type: 'call', action: 'buy', strike: parseFloat(form.querySelector('[name="long_call_strike"]').value), price: parseFloat(form.querySelector('[name="long_call_price"]').value) || undefined },
    ];
  } else if (strategy === 'iron-condor') {
    legs = [
      { type: 'put', action: 'sell', strike: parseFloat(form.querySelector('[name="short_put_strike"]').value), price: parseFloat(form.querySelector('[name="short_put_price"]').value) || undefined },
      { type: 'put', action: 'buy', strike: parseFloat(form.querySelector('[name="long_put_strike"]').value), price: parseFloat(form.querySelector('[name="long_put_price"]').value) || undefined },
      { type: 'call', action: 'sell', strike: parseFloat(form.querySelector('[name="short_call_strike"]').value), price: parseFloat(form.querySelector('[name="short_call_price"]').value) || undefined },
      { type: 'call', action: 'buy', strike: parseFloat(form.querySelector('[name="long_call_strike"]').value), price: parseFloat(form.querySelector('[name="long_call_price"]').value) || undefined },
    ];
  } else if (strategy === 'covered-call') {
    legs = [
      { type: 'call', action: 'sell', strike: parseFloat(form.querySelector('[name="call_strike"]').value), price: parseFloat(form.querySelector('[name="call_price"]').value) || undefined },
    ];
  } else if (strategy === 'cash-secured-put') {
    legs = [
      { type: 'put', action: 'sell', strike: parseFloat(form.querySelector('[name="csp_put_strike"]').value), price: parseFloat(form.querySelector('[name="csp_put_price"]').value) || undefined },
    ];
  }

  // Clean undefined prices
  legs = legs.map(l => {
    const clean = { type: l.type, action: l.action, strike: l.strike };
    if (l.price) clean.price = l.price;
    return clean;
  });

  const position = {
    label: form.querySelector('[name="label"]').value,
    strategy,
    ticker: form.querySelector('[name="ticker"]').value.toUpperCase(),
    legs,
    net_credit: parseFloat(form.querySelector('[name="net_credit"]').value),
    expiry: form.querySelector('[name="expiry"]').value,
    contracts: parseInt(form.querySelector('[name="contracts"]').value) || 1,
    opened: new Date().toISOString().split('T')[0],
    status: form.querySelector('[name="status"]').value,
  };

  // Add cost_basis for covered calls
  if (strategy === 'covered-call') {
    const cb = form.querySelector('[name="cost_basis"]').value;
    if (cb) position.cost_basis = parseFloat(cb);
  }

  try {
    if (editIndex !== '') {
      const posId = portfolio[parseInt(editIndex)].id;
      await fetch(`/api/portfolio/${posId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(position),
      });
    } else {
      await fetch('/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(position),
      });
    }
    closeModal();
    loadPortfolio();
  } catch (err) {
    alert('Failed to save: ' + err.message);
  }
}

// ── Close Position ──────────────────────────────────────────────────────────

function closePosition(index) {
  const p = portfolio[index];
  const pnl = p.pnl_per_contract;
  const buffer = p.buffer_pct;

  document.getElementById('close-summary').innerHTML = `
    <div class="close-ticker">${esc(p.ticker)} — ${esc(p.label)}</div>
    <div class="close-detail">${esc(formatLegs(p))} · ${esc(p.expiry)}</div>
  `;

  document.getElementById('close-pnl').innerHTML = `
    <div class="form-row">
      <div class="form-group">
        <label>Close Price (debit per share)</label>
        <input type="number" id="close-price" step="0.01" placeholder="e.g. 0.50" oninput="updateClosePnl(${index})">
      </div>
      <div class="form-group">
        <label>Realized P&L (per contract)</label>
        <div class="close-pnl-item" style="margin-top:4px;">
          <div class="close-pnl-value neutral" id="close-realized-pnl">--</div>
        </div>
      </div>
    </div>
  `;

  document.getElementById('close-notes').value = '';
  document.getElementById('close-index').value = index;
  document.getElementById('close-modal-overlay').style.display = 'flex';
}

function updateClosePnl(index) {
  const p = portfolio[index];
  const closePrice = parseFloat(document.getElementById('close-price').value);
  const el = document.getElementById('close-realized-pnl');

  if (isNaN(closePrice)) {
    el.textContent = '--';
    el.className = 'close-pnl-value neutral';
    return;
  }

  const pnlPerShare = p.net_credit - closePrice;
  const pnlPerContract = pnlPerShare * 100 * (p.contracts || 1);
  const sign = pnlPerContract >= 0 ? '+' : '';
  el.textContent = `${sign}$${pnlPerContract.toFixed(0)}`;
  el.className = `close-pnl-value ${pnlPerContract >= 0 ? 'positive' : 'negative'}`;
}

async function confirmClosePosition() {
  const index = parseInt(document.getElementById('close-index').value);
  const notes = document.getElementById('close-notes').value;
  const closePrice = parseFloat(document.getElementById('close-price').value);
  const posId = portfolio[index].id;

  try {
    await fetch(`/api/portfolio/${posId}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        notes: notes || null,
        close_price: isNaN(closePrice) ? null : closePrice,
      }),
    });
    closeCloseModal();
    loadPortfolio();
  } catch (err) {
    alert('Failed to close: ' + err.message);
  }
}

function closeCloseModal(event) {
  if (event && event.target !== document.getElementById('close-modal-overlay')) return;
  document.getElementById('close-modal-overlay').style.display = 'none';
}

// ── Reopen / Delete ─────────────────────────────────────────────────────────

async function reopenPosition(index) {
  const posId = portfolio[index].id;
  try {
    await fetch(`/api/portfolio/${posId}/reopen`, { method: 'POST' });
    loadPortfolio();
  } catch (err) {
    alert('Failed to reopen: ' + err.message);
  }
}

function deletePosition(index) {
  const p = portfolio[index];
  document.getElementById('delete-summary').innerHTML = `
    <div class="close-ticker">${esc(p.ticker)} — ${esc(p.label)}</div>
    <div class="close-detail">${esc(formatLegs(p))} · ${esc(p.expiry)}</div>
  `;
  document.getElementById('delete-index').value = index;
  document.getElementById('delete-modal-overlay').style.display = 'flex';
}

async function confirmDeletePosition() {
  const index = parseInt(document.getElementById('delete-index').value);
  const posId = portfolio[index].id;
  try {
    await fetch(`/api/portfolio/${posId}`, { method: 'DELETE' });
    closeDeleteModal();
    loadPortfolio();
  } catch (err) {
    alert('Failed to delete: ' + err.message);
  }
}

function closeDeleteModal(event) {
  if (event && event.target !== document.getElementById('delete-modal-overlay')) return;
  document.getElementById('delete-modal-overlay').style.display = 'none';
}
