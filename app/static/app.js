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
    div.innerHTML = marked.parse(content);
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
    loadingEl.innerHTML = marked.parse(data.response);

    history.push({ role: 'user', content: text });
    history.push({ role: 'assistant', content: data.response });
    if (history.length > 20) history = history.slice(-20);
  } catch (err) {
    loadingEl.classList.remove('loading');
    loadingEl.innerHTML = `<strong>Error:</strong> ${err.message}`;
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

    return `
      <div class="position-card ${isClosed ? 'closed' : ''} ${zone ? 'zone-' + zoneClass : ''}" style="animation-delay: ${i * 0.05}s" id="card-${i}">
        <div class="card-top">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="card-ticker">${p.ticker}</div>
              ${zone && !isClosed ? `
                <div class="zone-info">
                  <span class="zone-dot ${zoneClass}"></span>
                  <span class="zone-label ${zoneClass}">${zone}</span>
                </div>
              ` : ''}
            </div>
            <div class="card-label">${p.label}</div>
            <div class="card-legs">${legsStr}</div>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
            <span class="card-strategy">${formatStrategy(p.strategy)}</span>
            ${isClosed ? '<span class="zone-badge" style="color:var(--text-muted);border-color:var(--border);">CLOSED</span>' : ''}
            ${zoneUpdated && !isClosed ? `<span class="zone-updated">${zoneUpdated}</span>` : ''}
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
  const date = new Date(isoString + 'Z');
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

  // 1. Run monitor script silently → update badge immediately
  const card = document.getElementById('card-' + index);
  if (card) {
    const dot = card.querySelector('.zone-dot');
    if (dot) dot.className = 'zone-dot checking';
  }

  // Fire script check (don't await — let it run in parallel with chat)
  fetch(`/api/portfolio/${index}/check`, { method: 'POST' })
    .then(() => loadPortfolio())
    .catch(() => {});

  // 2. Send to chat sidebar for AI analysis
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
      await fetch(`/api/portfolio/${editIndex}`, {
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
    <div class="close-ticker">${p.ticker} — ${p.label}</div>
    <div class="close-detail">${formatLegs(p)} · ${p.expiry}</div>
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
  const index = document.getElementById('close-index').value;
  const notes = document.getElementById('close-notes').value;
  const closePrice = parseFloat(document.getElementById('close-price').value);

  try {
    await fetch(`/api/portfolio/${index}/close`, {
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
  try {
    await fetch(`/api/portfolio/${index}/reopen`, { method: 'POST' });
    loadPortfolio();
  } catch (err) {
    alert('Failed to reopen: ' + err.message);
  }
}

function deletePosition(index) {
  const p = portfolio[index];
  document.getElementById('delete-summary').innerHTML = `
    <div class="close-ticker">${p.ticker} — ${p.label}</div>
    <div class="close-detail">${formatLegs(p)} · ${p.expiry}</div>
  `;
  document.getElementById('delete-index').value = index;
  document.getElementById('delete-modal-overlay').style.display = 'flex';
}

async function confirmDeletePosition() {
  const index = document.getElementById('delete-index').value;
  try {
    await fetch(`/api/portfolio/${index}`, { method: 'DELETE' });
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
