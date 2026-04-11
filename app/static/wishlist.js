// ── Trade Watchlist ──────────────────────────────────────────────────────────

let _watchlist = [];
let _pendingWatchlistRemoveId = null;

async function loadWishlist() {
  try {
    const res = await fetch('/api/wishlist');
    if (!res.ok) throw new Error('Failed to load watchlist');
    _watchlist = await res.json();
    renderWatchlist();
  } catch (err) {
    console.error('Failed to load watchlist:', err);
  }
}

function renderWatchlist() {
  const grid = document.getElementById('wishlist-grid');
  const empty = document.getElementById('wishlist-empty');
  const summary = document.getElementById('wishlist-summary');

  if (!_watchlist.length) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    summary.innerHTML = '';
    return;
  }

  empty.style.display = 'none';
  summary.innerHTML = `<span style="color:var(--text-muted);font-size:13px;">${_watchlist.length} saved trade${_watchlist.length === 1 ? '' : 's'}</span>`;

  grid.innerHTML = _watchlist.map((item, i) => {
    const legsStr = item.legs.map(l => {
      const action = l.action === 'sell' ? 'S' : 'B';
      const type = l.type.charAt(0).toUpperCase();
      return `${action} $${l.strike}${type}`;
    }).join(' / ');

    const dteStr = formatDTE(item.expiry);
    const cur = item.current || {};
    const hasRefresh = cur.stock_price != null;
    const refreshedAt = cur.refreshed_at ? formatTimeAgo(cur.refreshed_at) : null;

    // Compute current credit from chain data
    let currentCredit = null;
    if (cur.chain_data) {
      currentCredit = computeCurrentCredit(item, cur.chain_data);
    }

    const creditChange = (currentCredit != null && item.original_credit)
      ? currentCredit - item.original_credit
      : null;

    const creditChangeStr = creditChange != null
      ? (creditChange >= 0 ? '+' : '') + '$' + creditChange.toFixed(2)
      : null;

    const creditChangeClass = creditChange != null
      ? (creditChange > 0 ? 'wl-credit-up' : creditChange < 0 ? 'wl-credit-down' : '')
      : '';

    return `
      <div class="watchlist-card" style="animation-delay: ${i * 0.05}s">
        <div class="card-top">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="card-ticker">${esc(item.ticker)}${getTickerName(item.ticker) ? `<span class="ticker-name">${esc(getTickerName(item.ticker))}</span>` : ''}${hasRefresh ? `<span class="ticker-price">$${cur.stock_price.toFixed(2)}</span>` : (item.stock_price_at_save ? `<span class="ticker-price">$${item.stock_price_at_save.toFixed(2)}</span>` : '')}</div>
            </div>
            <div class="card-label">${esc(legsStr)}</div>
          </div>
          <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
            <span class="card-strategy">${esc(formatStrategy(item.strategy))}</span>
            <span class="zone-updated">saved ${esc(item.saved_at || '')}</span>
            ${refreshedAt ? `<span class="zone-updated">${esc(refreshedAt)}</span>` : ''}
          </div>
        </div>
        <div class="card-metrics">
          <div class="metric">
            <div class="metric-value" style="color:var(--pnl-positive)">$${item.original_credit.toFixed(2)}</div>
            <div class="metric-label">Saved Credit</div>
          </div>
          <div class="metric">
            <div class="metric-value ${creditChangeClass}">${currentCredit != null ? '$' + currentCredit.toFixed(2) : '--'}${creditChangeStr ? ` <span class="wl-change-badge ${creditChangeClass}">${creditChangeStr}</span>` : ''}</div>
            <div class="metric-label">Current Credit</div>
          </div>
          <div class="metric">
            <div class="metric-value">${item.original_return_pct != null ? item.original_return_pct + '%' : '--'}</div>
            <div class="metric-label">Return/Risk</div>
          </div>
          <div class="metric">
            <div class="metric-value">${hasRefresh && cur.buffer_pct != null ? cur.buffer_pct.toFixed(1) + '%' : '--'}</div>
            <div class="metric-label">Buffer</div>
          </div>
          <div class="metric">
            <div class="metric-value">${esc(item.expiry)}</div>
            <div class="metric-label">${dteStr || '--'} DTE</div>
          </div>
        </div>
        <div class="card-actions">
          <button class="card-btn" onclick="refreshWatchlistItem('${esc(item.id)}', this)">Refresh</button>
          <button class="card-btn" onclick="watchlistToPortfolio(${i})">Add to Portfolio</button>
          <button class="card-btn danger" onclick="removeWatchlistItem('${esc(item.id)}')">Remove</button>
        </div>
      </div>
    `;
  }).join('');
}

function computeCurrentCredit(item, chainData) {
  const strategy = item.strategy;
  if (strategy === 'bull-put-spread' || strategy === 'bear-call-spread') {
    const sl = chainData.short_leg || {};
    const ll = chainData.long_leg || {};
    if (sl.bid != null && ll.ask != null) {
      return Math.round((sl.bid - ll.ask) * 100) / 100;
    }
  } else if (strategy === 'iron-condor') {
    const ps = chainData.put_side || {};
    const cs = chainData.call_side || {};
    const psl = (ps.short_leg || {}).bid;
    const pll = (ps.long_leg || {}).ask;
    const csl = (cs.short_leg || {}).bid;
    const cll = (cs.long_leg || {}).ask;
    if (psl != null && pll != null && csl != null && cll != null) {
      return Math.round(((psl - pll) + (csl - cll)) * 100) / 100;
    }
  } else if (strategy === 'covered-call' || strategy === 'cash-secured-put') {
    const sl = chainData.short_leg || {};
    if (sl.bid != null) return Math.round(sl.bid * 100) / 100;
  }
  return null;
}

async function addToWishlist(strategy, data) {
  if (!strategy || !data) return false;

  const legs = [];
  let credit = 0;
  let returnPct = null;
  let stockPrice = null;

  if (strategy === 'bull-put-spread') {
    legs.push({ type: 'put', action: 'sell', strike: data.short_put.strike, original_mid: data.short_put.mid });
    legs.push({ type: 'put', action: 'buy', strike: data.long_put.strike, original_mid: data.long_put.mid });
    credit = data.net_credit;
    returnPct = data.return_on_risk_pct;
    stockPrice = data.price;
  } else if (strategy === 'bear-call-spread') {
    legs.push({ type: 'call', action: 'sell', strike: data.short_call.strike, original_mid: data.short_call.mid });
    legs.push({ type: 'call', action: 'buy', strike: data.long_call.strike, original_mid: data.long_call.mid });
    credit = data.net_credit;
    returnPct = data.return_on_risk_pct;
    stockPrice = data.price;
  } else if (strategy === 'iron-condor') {
    const ps = data.put_side || data;
    const cs = data.call_side || data;
    legs.push({ type: 'put', action: 'sell', strike: ps.short_put.strike, original_mid: ps.short_put.mid });
    legs.push({ type: 'put', action: 'buy', strike: ps.long_put.strike, original_mid: ps.long_put.mid });
    legs.push({ type: 'call', action: 'sell', strike: cs.short_call.strike, original_mid: cs.short_call.mid });
    legs.push({ type: 'call', action: 'buy', strike: cs.long_call.strike, original_mid: cs.long_call.mid });
    credit = data.total_credit || data.net_credit;
    returnPct = data.return_on_risk_pct;
    stockPrice = data.price || data.stock_price;
  } else if (strategy === 'covered-call') {
    legs.push({ type: 'call', action: 'sell', strike: data.short_call.strike, original_mid: data.short_call.mid });
    credit = data.premium_per_share;
    returnPct = data.return_on_risk_pct || data.annualized_return_pct;
    stockPrice = data.stock_price;
  } else if (strategy === 'cash-secured-put') {
    legs.push({ type: 'put', action: 'sell', strike: data.short_put.strike, original_mid: data.short_put.mid });
    credit = data.premium_per_share;
    returnPct = data.return_on_risk_pct || data.annualized_return_pct;
    stockPrice = data.stock_price;
  }

  const payload = {
    ticker: data.ticker,
    strategy,
    expiry: data.expiry,
    legs,
    original_credit: credit,
    original_return_pct: returnPct,
    stock_price_at_save: stockPrice,
  };

  try {
    const res = await fetch('/api/wishlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to add');
    }
    await loadWishlist();
    return true;
  } catch (err) {
    alert('Failed to save trade: ' + err.message);
    return false;
  }
}

async function refreshWatchlistItem(id, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '...'; }
  try {
    const res = await fetch(`/api/wishlist/${id}/refresh`, { method: 'POST' });
    if (!res.ok) throw new Error('Refresh failed');
    await loadWishlist();
  } catch (err) {
    alert('Refresh failed: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Refresh'; }
  }
}

async function refreshAllWatchlist() {
  const btn = document.getElementById('btn-refresh-wishlist');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span>&#8635;</span> Refreshing...'; }
  try {
    const res = await fetch('/api/wishlist/refresh', { method: 'POST' });
    if (!res.ok) throw new Error('Refresh failed');
    await loadWishlist();
  } catch (err) {
    alert('Refresh failed: ' + err.message);
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '<span>&#8635;</span> Refresh All'; }
  }
}

function watchlistToPortfolio(index) {
  const item = _watchlist[index];
  if (!item) return;

  const form = document.getElementById('position-form');
  document.getElementById('modal-title').textContent = 'New Position';
  form.reset();
  form.querySelector('[name="edit_index"]').value = '';
  form.querySelector('[name="strategy"]').value = item.strategy;
  form.querySelector('[name="ticker"]').value = item.ticker;
  form.querySelector('[name="expiry"]').value = item.expiry;
  form.querySelector('[name="net_credit"]').value = item.original_credit;

  const expMonth = new Date(item.expiry + 'T00:00:00').toLocaleString('en', { month: 'short' });
  form.querySelector('[name="label"]').value = `${item.ticker} ${expMonth} ${formatStrategy(item.strategy)}`;

  updateLegFields(item.strategy);

  if (item.strategy === 'bull-put-spread') {
    const short = item.legs.find(l => l.action === 'sell');
    const long = item.legs.find(l => l.action === 'buy');
    form.querySelector('[name="short_put_strike"]').value = short.strike;
    form.querySelector('[name="short_put_price"]').value = short.original_mid || '';
    form.querySelector('[name="long_put_strike"]').value = long.strike;
    form.querySelector('[name="long_put_price"]').value = long.original_mid || '';
  } else if (item.strategy === 'bear-call-spread') {
    const short = item.legs.find(l => l.action === 'sell');
    const long = item.legs.find(l => l.action === 'buy');
    form.querySelector('[name="short_call_strike"]').value = short.strike;
    form.querySelector('[name="short_call_price"]').value = short.original_mid || '';
    form.querySelector('[name="long_call_strike"]').value = long.strike;
    form.querySelector('[name="long_call_price"]').value = long.original_mid || '';
  } else if (item.strategy === 'iron-condor') {
    const sp = item.legs.find(l => l.type === 'put' && l.action === 'sell');
    const lp = item.legs.find(l => l.type === 'put' && l.action === 'buy');
    const sc = item.legs.find(l => l.type === 'call' && l.action === 'sell');
    const lc = item.legs.find(l => l.type === 'call' && l.action === 'buy');
    form.querySelector('[name="short_put_strike"]').value = sp.strike;
    form.querySelector('[name="short_put_price"]').value = sp.original_mid || '';
    form.querySelector('[name="long_put_strike"]').value = lp.strike;
    form.querySelector('[name="long_put_price"]').value = lp.original_mid || '';
    form.querySelector('[name="short_call_strike"]').value = sc.strike;
    form.querySelector('[name="short_call_price"]').value = sc.original_mid || '';
    form.querySelector('[name="long_call_strike"]').value = lc.strike;
    form.querySelector('[name="long_call_price"]').value = lc.original_mid || '';
  } else if (item.strategy === 'covered-call') {
    const call = item.legs.find(l => l.type === 'call');
    form.querySelector('[name="call_strike"]').value = call.strike;
    form.querySelector('[name="call_price"]').value = call.original_mid || '';
  } else if (item.strategy === 'cash-secured-put') {
    const put = item.legs.find(l => l.type === 'put');
    form.querySelector('[name="csp_put_strike"]').value = put.strike;
    form.querySelector('[name="csp_put_price"]').value = put.original_mid || '';
  }

  _pendingWatchlistRemoveId = item.id;
  document.getElementById('closed-fields-group').style.display = 'none';
  document.getElementById('modal-overlay').style.display = 'flex';
}

async function removeWatchlistItem(id) {
  if (!confirm('Remove this trade from watchlist?')) return;
  try {
    const res = await fetch(`/api/wishlist/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to remove');
    await loadWishlist();
  } catch (err) {
    alert('Failed to remove: ' + err.message);
  }
}
