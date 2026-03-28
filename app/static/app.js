// ── Theme Toggle ─────────────────────────────────────────────────────────────

(function initTheme() {
  const saved = localStorage.getItem('theme') || 'light';
  if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  updateThemeIcon(saved);
})();

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  if (next === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.innerHTML = theme === 'dark' ? '&#9788;' : '&#9789;';
}

// ── HTML escaping ────────────────────────────────────────────────────────────

function esc(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function fmtOI(v) { return (v || 0).toLocaleString(); }

// ── Panel Navigation (right side tabs) ──────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'portfolio') loadPortfolio();
    if (tab.dataset.tab === 'profile') { loadProfile(); loadModels(); }
  });
});

// Load portfolio on startup
document.addEventListener('DOMContentLoaded', () => loadPortfolio());

// ── AI Toggle ────────────────────────────────────────────────────────────────

document.getElementById('ai-toggle').addEventListener('change', (e) => {
  const chatArea = document.getElementById('input-area');
  chatArea.classList.toggle('disabled', !e.target.checked);
});


// ── Chat ────────────────────────────────────────────────────────────────────

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
let history = [];

inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (role === 'assistant') {
    div.innerHTML = DOMPurify.sanitize(marked.parse(content));
  } else {
    div.textContent = content;
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!document.getElementById('ai-toggle').checked) return;

  addMessage('user', text);
  inputEl.value = '';
  inputEl.style.height = 'auto';

  sendBtn.disabled = true;
  const loadingEl = addMessage('assistant', 'Thinking');
  loadingEl.classList.add('loading');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Server error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    loadingEl.classList.remove('loading');
    loadingEl.innerHTML = DOMPurify.sanitize(marked.parse(data.response));

    history.push({ role: 'user', content: text });
    history.push({ role: 'assistant', content: data.response });
    const histLimit = cachedProfile?.chat_history_limit ?? 4;
    if (history.length > histLimit) history = history.slice(-histLimit);
  } catch (err) {
    loadingEl.classList.remove('loading');
    loadingEl.textContent = 'Error: ' + err.message;
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

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

function formatLegs(p) {
  return p.legs.map(l => {
    const action = l.action === 'sell' ? 'S' : 'B';
    const type = l.type.charAt(0).toUpperCase();
    return `${action} $${l.strike}${type}`;
  }).join(' / ');
}

function formatStrategy(s) {
  return s.replace(/-/g, ' ');
}

function formatTimeAgo(isoString) {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return diffMins + 'm ago';
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return diffHrs + 'h ago';
  const diffDays = Math.floor(diffHrs / 24);
  return diffDays + 'd ago';
}

// ── Check All Positions (no Claude, no tokens) ─────────────────────────────

async function checkAllPositions() {
  const btn = document.getElementById('btn-check-all');
  btn.disabled = true;
  btn.classList.add('checking');
  btn.innerHTML = '<span>&#8635;</span> Checking...';

  try {
    const res = await fetch('/api/portfolio/check', { method: 'POST' });
    if (!res.ok) throw new Error('Check failed');
    // Reload portfolio to show updated zones
    await loadPortfolio();
  } catch (err) {
    alert('Failed to check positions: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove('checking');
    btn.innerHTML = '<span>&#8635;</span> Check All';
  }
}

// (checkSinglePosition merged into checkPosition below)

function computeMaxLoss(p) {
  const legs = p.legs || [];
  const credit = p.net_credit || 0;
  const contracts = p.contracts || 1;
  const strikes = legs.map(l => l.strike).filter(Boolean);
  if (strikes.length < 2 && !['covered-call', 'cash-secured-put'].includes(p.strategy)) return null;
  if (p.strategy === 'bull-put-spread' || p.strategy === 'bear-call-spread') {
    const width = Math.abs(strikes[0] - strikes[1]);
    return (width - credit) * 100 * contracts;
  }
  if (p.strategy === 'iron-condor') {
    const puts = legs.filter(l => l.type === 'put').map(l => l.strike);
    const calls = legs.filter(l => l.type === 'call').map(l => l.strike);
    const putWidth = puts.length === 2 ? Math.abs(puts[0] - puts[1]) : 0;
    const callWidth = calls.length === 2 ? Math.abs(calls[0] - calls[1]) : 0;
    const maxWidth = Math.max(putWidth, callWidth);
    return (maxWidth - credit) * 100 * contracts;
  }
  if (p.strategy === 'cash-secured-put') {
    const strike = strikes[0] || 0;
    return (strike - credit) * 100 * contracts;
  }
  if (p.strategy === 'covered-call') return null; // unlimited downside on shares
  return null;
}

function formatDTE(expiry) {
  const exp = new Date(expiry + 'T00:00:00');
  const now = new Date();
  const diff = Math.ceil((exp - now) / (1000 * 60 * 60 * 24));
  if (diff < 0) return 'EXP';
  return diff + 'd';
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

// ── Analyzer ─────────────────────────────────────────────────────────────────

document.getElementById('az-ticker').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runAnalysis();
});

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
  _lastExpTicker = '';  // reset so next loadExpirations fetches fresh
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

let lastAnalysis = null;

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
      <span class="az-ticker">${esc(ticker)}</span>
      <span class="az-price">$${price.toFixed(2)}</span>
      <span class="az-strategy-label" style="margin-left:12px;margin-bottom:0;">STRATEGY COMPARISON</span>
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
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${bps.net_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Bull Put Spread' ? 'az-best' : ''}">${bps.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Bull Put Spread' ? 'az-best' : ''}">${bps.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${bps.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">$${bps.breakeven.toFixed(2)}</span><span class="az-cm-lbl">Breakeven</span></div>
          <div class="az-cm"><span class="az-cm-val">${bps.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('bull-put-spread', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['bull-put-spread'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('bull-put-spread')">Add to Portfolio</button>
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
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${bcs.net_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Bear Call Spread' ? 'az-best' : ''}">${bcs.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Bear Call Spread' ? 'az-best' : ''}">${bcs.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${bcs.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">$${bcs.breakeven.toFixed(2)}</span><span class="az-cm-lbl">Breakeven</span></div>
          <div class="az-cm"><span class="az-cm-val">${bcs.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('bear-call-spread', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['bear-call-spread'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('bear-call-spread')">Add to Portfolio</button>
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
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${ic.total_credit.toFixed(2)}</span><span class="az-cm-lbl">Credit</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Iron Condor' ? 'az-best' : ''}">${ic.return_on_risk_pct}%</span><span class="az-cm-lbl">Return/Risk</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Iron Condor' ? 'az-best' : ''}">${ic.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-negative)">$${ic.max_loss.toFixed(0)}</span><span class="az-cm-lbl">Max Loss</span></div>
          <div class="az-cm"><span class="az-cm-val">${esc(ic.profit_zone)}</span><span class="az-cm-lbl">Profit Zone</span></div>
          <div class="az-cm"><span class="az-cm-val">${ic.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('iron-condor', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['iron-condor'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('iron-condor')">Add to Portfolio</button>
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
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${cc.premium_per_share.toFixed(2)}</span><span class="az-cm-lbl">Premium</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Covered Call' ? 'az-best' : ''}">${cc.annualized_return_pct}%</span><span class="az-cm-lbl">Annualized</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Covered Call' ? 'az-best' : ''}">${(100 - cc.prob_called_pct).toFixed(1)}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.downside_protection_pct}%</span><span class="az-cm-lbl">Downside Prot.</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.called_away_return_pct}%</span><span class="az-cm-lbl">Called Away</span></div>
          <div class="az-cm"><span class="az-cm-val">${cc.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('covered-call', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['covered-call'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('covered-call')">Add to Portfolio</button>
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
          <div class="az-cm"><span class="az-cm-val" style="color:var(--pnl-positive)">$${csp.premium_per_share.toFixed(2)}</span><span class="az-cm-lbl">Premium</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestReturn === 'Cash-Secured Put' ? 'az-best' : ''}">${csp.annualized_return_pct}%</span><span class="az-cm-lbl">Annualized</span></div>
          <div class="az-cm"><span class="az-cm-val ${bestProb === 'Cash-Secured Put' ? 'az-best' : ''}">${csp.prob_profit_pct}%</span><span class="az-cm-lbl">Prob Profit</span></div>
          <div class="az-cm"><span class="az-cm-val">$${csp.effective_buy_price.toFixed(2)}</span><span class="az-cm-lbl">Eff. Buy Price</span></div>
          <div class="az-cm"><span class="az-cm-val">${csp.discount_pct}%</span><span class="az-cm-lbl">Discount</span></div>
          <div class="az-cm"><span class="az-cm-val">${csp.dte}d</span><span class="az-cm-lbl">DTE</span></div>
        </div>
        <div class="az-compare-actions">
          <button class="btn-view-chain" onclick="viewChain('cash-secured-put', lastAnalysis && lastAnalysis.data ? lastAnalysis.data['cash-secured-put'] : null)">View Chain</button>
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('cash-secured-put')">Add to Portfolio</button>
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
  lastAnalysis = { strategy, data };
  addAnalysisToPortfolio();
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
            <span class="az-ticker">${esc(d.ticker)}</span>
            <span class="az-price">$${d.price.toFixed(2)}</span>
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
            <div class="metric-label">Net Credit</div>
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
        </div>
      </div>`;
  } else if (strategy === 'bear-call-spread') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}</span>
            <span class="az-price">$${d.price.toFixed(2)}</span>
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
            <div class="metric-label">Net Credit</div>
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
        </div>
      </div>`;
  } else if (strategy === 'iron-condor') {
    const ps = d.put_side, cs = d.call_side;
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}</span>
            <span class="az-price">$${d.price.toFixed(2)}</span>
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
            <div class="metric-label">Total Credit</div>
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
        </div>
      </div>`;
  } else if (strategy === 'covered-call') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}</span>
            <span class="az-price">$${d.stock_price.toFixed(2)}</span>
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
            <div class="metric-label">Premium</div>
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
        </div>
      </div>`;
  } else if (strategy === 'cash-secured-put') {
    results.innerHTML = `
      <div class="az-result-card">
        <div class="az-header">
          <div>
            <span class="az-ticker">${esc(d.ticker)}</span>
            <span class="az-price">$${d.stock_price.toFixed(2)}</span>
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
            <div class="metric-label">Premium</div>
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
        </div>
      </div>`;
  }
}

function addAnalysisToPortfolio() {
  if (!lastAnalysis) return;
  const { strategy, data } = lastAnalysis;

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
    for (const r of rows) {
      const hl = highlights.has(r.strike) ? ' class="az-chain-highlight"' : '';
      html += `<tr${hl}>
        <td class="chain-strike">${r.strike.toFixed(1)}</td>
        <td>${r.bid.toFixed(2)}</td><td>${r.ask.toFixed(2)}</td>
        <td>${r.mid.toFixed(2)}</td>
        <td>${r.volume}</td><td>${r.open_interest.toLocaleString()}</td>
        <td>${r.iv_pct.toFixed(1)}</td><td>${r.delta.toFixed(3)}</td>
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
      <span>Option Chain &mdash; ${esc(chain.ticker)} ${esc(chain.expiry)} &middot; ${chain.dte} DTE</span>
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
    'covered-call': 'calls',
    'iron-condor': 'both',
  };
  const side = sideMap[strategy] || 'both';
  const ticker = data.ticker;
  const expiry = data.expiry;
  const highlights = extractHighlightStrikes(strategy, data);

  // Toggle off if already showing
  const existing = document.getElementById('az-chain-container');
  if (existing) { existing.remove(); return; }

  // Show loading
  const resultsEl = document.getElementById('az-results');
  const loadingDiv = document.createElement('div');
  loadingDiv.id = 'az-chain-container';
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


// ── Profile ─────────────────────────────────────────────────────────────────

let cachedProfile = null;

async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const data = await res.json();
    const sel = document.getElementById('pf-model');
    const current = sel.value;
    sel.innerHTML = data.models.map(m => `<option value="${m.id}">${m.display_name} — ${m.id}</option>`).join('');
    if (current) sel.value = current;
  } catch (err) {
    console.error('Failed to load models:', err);
  }
}

async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    const profile = await res.json();
    cachedProfile = profile;

    // Personal
    document.getElementById('pf-name').value = profile.name || '';
    if (profile.model) document.getElementById('pf-model').value = profile.model;
    const nameEl = document.getElementById('user-name');
    nameEl.textContent = profile.name || '';

    const sd = profile.strategy_defaults || {};
    const bps = sd['bull-put-spread'] || {};
    const ic = sd['iron-condor'] || {};
    const cc = sd['covered-call'] || {};

    document.getElementById('pf-bps-delta').value = bps.delta ?? '';
    document.getElementById('pf-bps-dte-min').value = bps.dte_min ?? '';
    document.getElementById('pf-bps-dte-max').value = bps.dte_max ?? '';
    document.getElementById('pf-bps-width').value = bps.spread_width ?? '';
    document.getElementById('pf-ic-delta').value = ic.delta ?? '';
    document.getElementById('pf-ic-dte-min').value = ic.dte_min ?? '';
    document.getElementById('pf-ic-dte-max').value = ic.dte_max ?? '';
    document.getElementById('pf-cc-delta').value = cc.delta ?? '';
    document.getElementById('pf-cc-dte-min').value = cc.dte_min ?? '';
    document.getElementById('pf-cc-dte-max').value = cc.dte_max ?? '';

    const csp = sd['cash-secured-put'] || {};
    document.getElementById('pf-csp-delta').value = csp.delta ?? '';
    document.getElementById('pf-csp-dte-min').value = csp.dte_min ?? '';
    document.getElementById('pf-csp-dte-max').value = csp.dte_max ?? '';

    const pr = profile.profit_rules || {};
    document.getElementById('pf-close-pct').value = pr.close_pct ?? '';
    document.getElementById('pf-consider-pct').value = pr.consider_pct ?? '';
    document.getElementById('pf-near-pct').value = pr.near_expiry_pct ?? '';
    document.getElementById('pf-near-dte').value = pr.near_expiry_dte ?? '';

    document.getElementById('pf-chat-history').value = profile.chat_history_limit ?? 4;

    updateAnalyzerPlaceholders();
  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

async function saveProfile() {
  const btn = document.querySelector('.btn-save-profile');
  const statusEl = document.getElementById('profile-status');
  btn.disabled = true;
  statusEl.textContent = '';

  const body = {
    name: document.getElementById('pf-name').value.trim(),
    model: document.getElementById('pf-model').value,
    strategy_defaults: {
      'bull-put-spread': {
        delta: parseFloat(document.getElementById('pf-bps-delta').value) || 0.20,
        dte_min: parseInt(document.getElementById('pf-bps-dte-min').value) || 35,
        dte_max: parseInt(document.getElementById('pf-bps-dte-max').value) || 45,
        spread_width: parseFloat(document.getElementById('pf-bps-width').value) || 10,
      },
      'iron-condor': {
        delta: parseFloat(document.getElementById('pf-ic-delta').value) || 0.16,
        dte_min: parseInt(document.getElementById('pf-ic-dte-min').value) || 35,
        dte_max: parseInt(document.getElementById('pf-ic-dte-max').value) || 45,
      },
      'covered-call': {
        delta: parseFloat(document.getElementById('pf-cc-delta').value) || 0.30,
        dte_min: parseInt(document.getElementById('pf-cc-dte-min').value) || 30,
        dte_max: parseInt(document.getElementById('pf-cc-dte-max').value) || 45,
      },
      'cash-secured-put': {
        delta: parseFloat(document.getElementById('pf-csp-delta').value) || 0.25,
        dte_min: parseInt(document.getElementById('pf-csp-dte-min').value) || 30,
        dte_max: parseInt(document.getElementById('pf-csp-dte-max').value) || 45,
      },
    },
    profit_rules: {
      close_pct: parseInt(document.getElementById('pf-close-pct').value) || 75,
      consider_pct: parseInt(document.getElementById('pf-consider-pct').value) || 50,
      near_expiry_pct: parseInt(document.getElementById('pf-near-pct').value) || 25,
      near_expiry_dte: parseInt(document.getElementById('pf-near-dte').value) || 14,
    },
    chat_history_limit: parseInt(document.getElementById('pf-chat-history').value) || 4,
  };

  try {
    const res = await fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    cachedProfile = await res.json();
    document.getElementById('user-name').textContent = cachedProfile.name || '';
    statusEl.textContent = 'Saved';
    statusEl.className = 'profile-status success';
    updateAnalyzerPlaceholders();
    setTimeout(() => { statusEl.textContent = ''; }, 2000);
  } catch (err) {
    statusEl.textContent = 'Save failed';
    statusEl.className = 'profile-status error';
  }
  btn.disabled = false;
}

function updateAnalyzerPlaceholders() {
  if (!cachedProfile) return;
  const strategy = document.getElementById('az-strategy').value;
  const sd = cachedProfile.strategy_defaults || {};

  const strategyKey = strategy === 'compare' ? 'bull-put-spread' : strategy;
  const defaults = sd[strategyKey] || {};

  document.getElementById('az-dte-min').placeholder = defaults.dte_min ?? '35';
  document.getElementById('az-dte-max').placeholder = defaults.dte_max ?? '45';
  document.getElementById('az-delta').placeholder = defaults.delta ?? 'auto';
}

// Clamp delta input to 0.00–0.99
document.getElementById('az-delta').addEventListener('blur', function() {
  const v = parseFloat(this.value);
  if (this.value === '' || isNaN(v)) { this.value = ''; return; }
  this.value = Math.min(0.99, Math.max(0, v)).toFixed(2);
});

// Load profile on startup and update placeholders when strategy changes
document.addEventListener('DOMContentLoaded', () => loadProfile());

function onStrategyChange(value) {
  document.getElementById('az-delta-group').style.display = value === 'compare' ? 'none' : 'block';
  updateAnalyzerPlaceholders();
}
