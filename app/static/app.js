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

// ── Panel Navigation (right side tabs) ──────────────────────────────────────

document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'portfolio') loadPortfolio();
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
    if (history.length > 20) history = history.slice(-20);
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

    return `
      <div class="position-card ${isClosed ? 'closed' : ''} ${zone ? 'zone-' + zoneClass : ''}" style="animation-delay: ${i * 0.05}s" id="card-${i}">
        <div class="card-top">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="card-ticker">${esc(p.ticker)}</div>
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
            <div class="metric-value">${dteStr}</div>
            <div class="metric-label">DTE</div>
          </div>
        </div>
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

function onStrategyChange(value) {
  document.getElementById('az-delta-group').style.display = value === 'compare' ? 'none' : 'block';
}

async function runAnalysis() {
  const ticker = document.getElementById('az-ticker').value.trim().toUpperCase();
  const strategy = document.getElementById('az-strategy').value;

  if (!ticker) return;

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.textContent = 'Analyzing...';
  document.getElementById('az-empty').style.display = 'none';
  document.getElementById('az-results').innerHTML = '<div class="az-loading">Fetching live option chain data...</div>';

  if (strategy === 'compare') {
    await runCompareAnalysis(ticker, btn);
  } else {
    await runSingleAnalysis(ticker, strategy, btn);
  }

  btn.disabled = false;
  btn.textContent = 'Analyze';
}

async function runSingleAnalysis(ticker, strategy, btn) {
  const deltaVal = document.getElementById('az-delta').value;
  const dteMinVal = document.getElementById('az-dte-min').value;
  const dteMaxVal = document.getElementById('az-dte-max').value;

  const body = { ticker, strategy };
  if (deltaVal) body.target_delta = parseFloat(deltaVal);
  if (dteMinVal) body.dte_min = parseInt(dteMinVal);
  if (dteMaxVal) body.dte_max = parseInt(dteMaxVal);

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
  if (dteMinVal) body.dte_min = parseInt(dteMinVal);
  if (dteMaxVal) body.dte_max = parseInt(dteMaxVal);

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
  if (strategy === 'bull-put-spread') {
    return `Assess this bull put spread on ${d.ticker} ($${d.price}): sell $${d.short_put.strike}P (Δ${d.short_put.delta}, IV ${d.short_put.iv_pct}%) / buy $${d.long_put.strike}P, credit $${d.net_credit}, max loss $${d.max_loss}, breakeven $${d.breakeven}, ${d.return_on_risk_pct}% return, ${d.prob_profit_pct}% prob profit, ${d.dte} DTE. Is this a good trade?`;
  }
  if (strategy === 'iron-condor') {
    const ps = d.put_side, cs = d.call_side;
    return `Assess this iron condor on ${d.ticker} ($${d.price}): puts ${ps.short_put.strike}/${ps.long_put.strike} (Δ${ps.short_put.delta}, IV ${ps.short_put.iv_pct}%), calls ${cs.short_call.strike}/${cs.long_call.strike} (Δ${cs.short_call.delta}, IV ${cs.short_call.iv_pct}%), total credit $${d.total_credit}, max loss $${d.max_loss}, profit zone ${d.profit_zone}, ${d.return_on_risk_pct}% return, ${d.prob_profit_pct}% prob profit, ${d.dte} DTE. Is this a good trade?`;
  }
  if (strategy === 'covered-call') {
    return `Assess this covered call on ${d.ticker} ($${d.stock_price}): sell $${d.short_call.strike}C (Δ${d.short_call.delta}, IV ${d.short_call.iv_pct}%), premium $${d.premium_per_share}, static ${d.static_return_pct}%, annualized ${d.annualized_return_pct}%, downside protection ${d.downside_protection_pct}%, called away return ${d.called_away_return_pct}%, ${d.prob_called_pct}% prob called, ${d.dte} DTE. Is this a good trade?`;
  }
  return `Assess this ${formatStrategy(strategy)} result: ${JSON.stringify(d)}`;
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
  const bps = data.bull_put_spread;
  const ic = data.iron_condor;
  const cc = data.covered_call;
  const mc = data.market_context;
  const ticker = data.ticker;
  const price = bps.price || ic.price || cc.stock_price || 0;

  // Find best values for highlighting
  const returns = [
    { strategy: 'Bull Put Spread', val: bps.return_on_risk_pct || 0 },
    { strategy: 'Iron Condor', val: ic.return_on_risk_pct || 0 },
    { strategy: 'Covered Call', val: cc.annualized_return_pct || 0 },
  ];
  const probs = [
    { strategy: 'Bull Put Spread', val: bps.prob_profit_pct || 0 },
    { strategy: 'Iron Condor', val: ic.prob_profit_pct || 0 },
    { strategy: 'Covered Call', val: 100 - (cc.prob_called_pct || 0) },
  ];
  const bestReturn = returns.reduce((a, b) => a.val > b.val ? a : b).strategy;
  const bestProb = probs.reduce((a, b) => a.val > b.val ? a : b).strategy;

  // Suggestion strategy key (e.g. "bull-put-spread") or null
  const suggested = mc && !mc.error && mc.suggestion ? mc.suggestion.strategy : null;
  const strategyToKey = { 'Bull Put Spread': 'bull-put-spread', 'Iron Condor': 'iron-condor', 'Covered Call': 'covered-call' };

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
          ? `<span class="az-suggestion-badge">\u2605 ${esc(mc.suggestion.label)}</span>`
          : `<span class="az-mc-badge az-trend-bearish">\u26A0 ${esc(mc.suggestion.label)}</span>`
        }
        <span class="az-mc-reason">${esc(mc.suggestion.reason)}</span>
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
      <div class="az-compare-card ${suggested === 'bull-put-spread' ? 'az-suggested' : ''}">
        <div class="az-compare-title">Bull Put Spread${suggested === 'bull-put-spread' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}</div>
        ${bps.error ? `<div class="az-error">${esc(bps.error)}</div>` : `
        <div class="az-compare-legs">
          <span class="leg-action sell">SELL</span> $${bps.short_put.strike}P
          <span class="leg-action buy">BUY</span> $${bps.long_put.strike}P
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
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('bull-put-spread')">Add to Portfolio</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'iron-condor' ? 'az-suggested' : ''}">
        <div class="az-compare-title">Iron Condor${suggested === 'iron-condor' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}</div>
        ${ic.error ? `<div class="az-error">${esc(ic.error)}</div>` : `
        <div class="az-compare-legs">
          <span class="leg-action sell">SELL</span> $${ic.put_side.short_put.strike}P / $${ic.call_side.short_call.strike}C
          <span class="leg-action buy">BUY</span> $${ic.put_side.long_put.strike}P / $${ic.call_side.long_call.strike}C
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
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('iron-condor')">Add to Portfolio</button>
        </div>
        `}
      </div>
      <div class="az-compare-card ${suggested === 'covered-call' ? 'az-suggested' : ''}">
        <div class="az-compare-title">Covered Call${suggested === 'covered-call' ? '<span class="az-suggested-tag">SUGGESTED</span>' : ''}</div>
        ${cc.error ? `<div class="az-error">${esc(cc.error)}</div>` : `
        <div class="az-compare-legs">
          <span class="leg-action sell">SELL</span> $${cc.short_call.strike}C @ $${cc.premium_per_share.toFixed(2)}
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
          <button class="btn-add-to-portfolio" onclick="addCompareToPortfolio('covered-call')">Add to Portfolio</button>
        </div>
        `}
      </div>
    </div>`;

  // Store all results for "Add to Portfolio"
  lastAnalysis = {
    strategy: 'compare',
    data: { 'bull-put-spread': bps, 'iron-condor': ic, 'covered-call': cc },
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
  const bps = data.bull_put_spread;
  const ic = data.iron_condor;
  const cc = data.covered_call;
  const ticker = data.ticker;

  let prompt = `Compare these 3 strategies for ${ticker} and recommend which is best right now:\n\n`;
  if (!bps.error) {
    prompt += `Bull Put Spread: sell $${bps.short_put.strike}P / buy $${bps.long_put.strike}P, credit $${bps.net_credit}, ${bps.return_on_risk_pct}% return, ${bps.prob_profit_pct}% prob profit, ${bps.dte} DTE\n`;
  }
  if (!ic.error) {
    prompt += `Iron Condor: puts ${ic.put_side.short_put.strike}/${ic.put_side.long_put.strike}, calls ${ic.call_side.short_call.strike}/${ic.call_side.long_call.strike}, credit $${ic.total_credit}, ${ic.return_on_risk_pct}% return, ${ic.prob_profit_pct}% prob profit, ${ic.dte} DTE\n`;
  }
  if (!cc.error) {
    prompt += `Covered Call: sell $${cc.short_call.strike}C, premium $${cc.premium_per_share}, ${cc.annualized_return_pct}% annualized, ${cc.prob_called_pct}% prob called, ${cc.dte} DTE\n`;
  }
  if (data.market_context && !data.market_context.error) {
    const mc = data.market_context;
    const t = mc.trend;
    const sign5d = t.change_5d_pct >= 0 ? '+' : '';
    const sign20d = t.change_20d_pct >= 0 ? '+' : '';
    prompt += `\nMarket Context:\n`;
    prompt += `- Trend: ${t.classification} (5d: ${sign5d}${t.change_5d_pct}%, 20d: ${sign20d}${t.change_20d_pct}%, 52w percentile: ${t.percentile_52w}%)\n`;
    prompt += `- ATM IV: ${mc.iv.atm_iv_pct}% (${mc.iv.level})\n`;
    prompt += `- Auto-suggestion: ${mc.suggestion.label} \u2014 ${mc.suggestion.reason}\n`;
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
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${d.long_put.strike} P</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${d.long_put.bid.toFixed(2)} / ${d.long_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${d.long_put.mid.toFixed(2)}</td>
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
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${ps.long_put.strike} P</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${ps.long_put.bid.toFixed(2)} / ${ps.long_put.ask.toFixed(2)}</td>
            <td class="leg-mid">$${ps.long_put.mid.toFixed(2)}</td>
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
          </tr>
          <tr>
            <td class="leg-action buy">BUY</td>
            <td class="leg-strike">$${cs.long_call.strike} C</td>
            <td class="leg-delta"></td>
            <td class="leg-iv"></td>
            <td class="leg-bid-ask">${cs.long_call.bid.toFixed(2)} / ${cs.long_call.ask.toFixed(2)}</td>
            <td class="leg-mid">$${cs.long_call.mid.toFixed(2)}</td>
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
  }

  document.getElementById('modal-overlay').style.display = 'flex';
}
