// ── Trade Plans ──────────────────────────────────────────────────────────────

let _tpPollTimer = null;
let _tpErrorDismissTimer = null;
let _tpErrorCapSnapshot = null;

function hideTradePlanError() {
  const errEl = document.getElementById('tp-form-error');
  if (errEl) {
    errEl.style.display = 'none';
    errEl.textContent = '';
  }
  if (_tpErrorDismissTimer) {
    clearTimeout(_tpErrorDismissTimer);
    _tpErrorDismissTimer = null;
  }
  _tpErrorCapSnapshot = null;
}

function showTradePlanError(msg, runningAtErrorTime) {
  const errEl = document.getElementById('tp-form-error');
  if (!errEl) return;
  errEl.textContent = msg;
  errEl.style.display = 'block';
  _tpErrorCapSnapshot = (typeof runningAtErrorTime === 'number') ? runningAtErrorTime : null;
  if (_tpErrorDismissTimer) clearTimeout(_tpErrorDismissTimer);
  _tpErrorDismissTimer = setTimeout(hideTradePlanError, 8000);
}

async function submitTradePlan() {
  const ticker = document.getElementById('tp-ticker').value.trim().toUpperCase();
  const timeframe = document.getElementById('tp-timeframe').value || null;
  const portfolio_size = document.getElementById('tp-portfolio-size').value.trim() || null;
  const bias = document.getElementById('tp-bias').value || null;
  hideTradePlanError();
  if (!ticker || !/^[A-Z]{1,5}$/.test(ticker)) {
    showTradePlanError('Enter a valid ticker (1–5 uppercase letters).');
    return;
  }

  const btn = document.getElementById('tp-generate');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  try {
    const res = await fetch('/api/trade-plans', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, timeframe, portfolio_size, bias }),
    });
    const data = await res.json();
    if (!res.ok) {
      const runningNow = await _getRunningCount();
      showTradePlanError(data.detail || data.error || `Failed (${res.status}).`, runningNow);
      return;
    }
    document.getElementById('tp-ticker').value = '';
    document.getElementById('tp-portfolio-size').value = '';
    await refreshTradePlans();
  } catch (e) {
    showTradePlanError('Network error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate';
  }
}

async function refreshTradePlans() {
  try {
    const [jobsRes, filesRes] = await Promise.all([
      fetch('/api/trade-plans/jobs'),
      fetch('/api/trade-plans/files'),
    ]);
    const jobsData = jobsRes.ok ? await jobsRes.json() : { jobs: [] };
    const filesData = filesRes.ok ? await filesRes.json() : { files: [] };
    const jobs = jobsData.jobs || [];
    applyClaudeAvailability(jobsData.claude_available !== false);
    renderInflight(jobs);
    renderGeneratedPlans(filesData.files || []);

    if (_tpErrorCapSnapshot !== null) {
      const running = jobs.filter(j => j.status === 'running').length;
      if (running < _tpErrorCapSnapshot) hideTradePlanError();
    }
  } catch (e) {
    console.error('trade-plans refresh failed', e);
  }
}

async function _getRunningCount() {
  try {
    const res = await fetch('/api/trade-plans/jobs');
    if (!res.ok) return null;
    const data = await res.json();
    return (data.jobs || []).filter(j => j.status === 'running').length;
  } catch {
    return null;
  }
}

function applyClaudeAvailability(available) {
  const banner = document.getElementById('tp-unavailable-banner');
  const btn = document.getElementById('tp-generate');
  if (banner) banner.style.display = available ? 'none' : 'block';
  if (btn) {
    btn.disabled = !available;
    btn.title = available ? '' : 'claude CLI not installed on server';
  }
}

function renderInflight(jobs) {
  const list = document.getElementById('tp-inflight-list');
  const empty = document.getElementById('tp-inflight-empty');
  const count = document.getElementById('tp-inflight-count');

  const visible = jobs.filter(j => j.status === 'running' || j.status === 'error');
  count.textContent = jobs.filter(j => j.status === 'running').length;

  if (!visible.length) {
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = visible.map(j => {
    const elapsed = formatElapsed(j.started_at, j.finished_at);
    if (j.status === 'running') {
      return `
        <div class="tp-row tp-row-running">
          <div class="tp-row-left">
            <span class="tp-spinner"></span>
            <span class="tp-ticker">${esc(j.ticker)}</span>
            ${j.timeframe ? `<span class="tp-meta">${esc(j.timeframe)}</span>` : ''}
          </div>
          <div class="tp-row-right">
            <span class="tp-elapsed">${elapsed}</span>
          </div>
        </div>`;
    }
    return `
      <div class="tp-row tp-row-error">
        <div class="tp-row-left">
          <span class="tp-status-dot tp-dot-error"></span>
          <div>
            <div><span class="tp-ticker">${esc(j.ticker)}</span> <span class="tp-error-label">Failed</span></div>
            <div class="tp-error-msg">${esc((j.error || '').slice(0, 240))}</div>
          </div>
        </div>
        <div class="tp-row-right">
          <button class="tp-btn" onclick="retryTradePlan('${esc(j.ticker)}', '${esc(j.timeframe || '')}')">Retry</button>
        </div>
      </div>`;
  }).join('');
}

function renderGeneratedPlans(files) {
  const list = document.getElementById('tp-files-list');
  const empty = document.getElementById('tp-files-empty');
  const count = document.getElementById('tp-files-count');
  count.textContent = files.length;

  if (!files.length) {
    list.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  list.innerHTML = files.map(f => {
    const relTime = formatTimeAgo(f.mtime);
    const sizeKb = (f.size / 1024).toFixed(0);
    const href = `/api/trade-plans/files/${encodeURIComponent(f.filename)}`;
    return `
      <div class="tp-row tp-row-file">
        <div class="tp-row-left">
          <span class="tp-status-dot tp-dot-done"></span>
          <div>
            <div><span class="tp-ticker">${esc(f.ticker || '?')}</span>
              <span class="tp-meta">expiry ${esc(f.expiry || '?')}</span></div>
            <div class="tp-file-sub">${esc(relTime)} · ${sizeKb} KB</div>
          </div>
        </div>
        <div class="tp-row-right">
          <a class="tp-btn tp-btn-primary" href="${href}" target="_blank" rel="noopener">Open</a>
          <button class="tp-btn tp-btn-danger" onclick="deleteTradePlan('${esc(f.filename)}')">Delete</button>
        </div>
      </div>`;
  }).join('');
}

async function deleteTradePlan(filename) {
  if (!confirm(`Delete ${filename}?`)) return;
  try {
    const res = await fetch(`/api/trade-plans/files/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.detail || `Delete failed (${res.status}).`);
      return;
    }
    await refreshTradePlans();
  } catch (e) {
    alert('Network error: ' + e.message);
  }
}

function retryTradePlan(ticker, timeframe) {
  document.getElementById('tp-ticker').value = ticker;
  if (timeframe) document.getElementById('tp-timeframe').value = timeframe;
  submitTradePlan();
}

function formatElapsed(startEpoch, endEpoch) {
  const now = endEpoch || (Date.now() / 1000);
  const secs = Math.max(0, Math.floor(now - startEpoch));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

function startTradePlansPolling() {
  if (_tpPollTimer) return;
  refreshTradePlans();
  _tpPollTimer = setInterval(refreshTradePlans, 3000);
}

function stopTradePlansPolling() {
  if (_tpPollTimer) {
    clearInterval(_tpPollTimer);
    _tpPollTimer = null;
  }
}
