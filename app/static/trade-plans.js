// ── Analysis tab (skill picker + job runner) ────────────────────────────────

let _tpPollTimer = null;
let _tpErrorDismissTimer = null;
let _tpErrorCapSnapshot = null;

// Mirror of trade_plan_runner.SKILL_REGISTRY's `supports` set. Drives which
// extra inputs are visible per selected skill. Keep in sync with the backend.
const SKILL_FIELDS = {
  'options-trade-plan': new Set(['timeframe', 'portfolio_size', 'bias']),
  'trade-analyze':     new Set(),
  'trade-thesis':      new Set(['portfolio_size']),
  'trade-risk':        new Set(['portfolio_size']),
  'trade-fundamental': new Set(),
  'trade-technical':   new Set(),
  'trade-sentiment':   new Set(),
  'trade-earnings':    new Set(),
  'trade-options':     new Set(['timeframe', 'bias']),
};

const SKILL_LABELS = {
  'options-trade-plan': 'Spread Plan',
  'trade-options':     'Market Read',
  'trade-analyze':     'Full Analysis',
  'trade-thesis':      'Thesis',
  'trade-risk':        'Risk',
  'trade-fundamental': 'Fundamental',
  'trade-technical':   'Technical',
  'trade-sentiment':   'Sentiment',
  'trade-earnings':    'Earnings',
};

function _currentSkill() {
  const el = document.getElementById('tp-skill');
  return el ? el.value : 'options-trade-plan';
}

function formatTokens(n) {
  if (n == null) return '';
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k';
  return String(n);
}

function formatCost(usd) {
  if (usd == null) return '';
  if (usd < 0.01) return '<$0.01';
  return '$' + usd.toFixed(2);
}

function formatApiMs(ms) {
  if (ms == null) return '';
  const s = ms / 1000;
  if (s < 60) return s.toFixed(1) + 's';
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m + 'm ' + r.toString().padStart(2, '0') + 's';
}

function renderMetricsSubtitle(m) {
  if (!m) return '';
  const parts = [];
  if (m.cost_usd != null) parts.push(formatCost(m.cost_usd));
  const inTok = m.input_tokens || 0;
  const outTok = m.output_tokens || 0;
  const cache = m.cache_read_tokens || 0;
  if (inTok || outTok) {
    let tokenStr = `${formatTokens(inTok)} in / ${formatTokens(outTok)} out`;
    if (cache) tokenStr += ` (+${formatTokens(cache)} cached)`;
    parts.push(tokenStr);
  }
  if (m.duration_ms != null) parts.push(formatApiMs(m.duration_ms));
  if (m.num_turns != null && m.num_turns > 1) parts.push(`${m.num_turns} turns`);
  return parts.join(' · ');
}

function applySkillFieldVisibility() {
  const supports = SKILL_FIELDS[_currentSkill()] || new Set();
  const toggle = (id, on) => {
    const el = document.getElementById(id);
    if (el) el.style.display = on ? '' : 'none';
  };
  toggle('tp-timeframe-group', supports.has('timeframe'));
  toggle('tp-portfolio-size-group', supports.has('portfolio_size'));
  toggle('tp-bias-group', supports.has('bias'));
}

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
  const skill_name = _currentSkill();
  const supports = SKILL_FIELDS[skill_name] || new Set();
  const ticker = document.getElementById('tp-ticker').value.trim().toUpperCase();
  const timeframe = supports.has('timeframe') ? (document.getElementById('tp-timeframe').value || null) : null;
  const portfolio_size = supports.has('portfolio_size') ? (document.getElementById('tp-portfolio-size').value.trim() || null) : null;
  const bias = supports.has('bias') ? (document.getElementById('tp-bias').value || null) : null;
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
      body: JSON.stringify({ skill_name, ticker, timeframe, portfolio_size, bias }),
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
    const skillLabel = SKILL_LABELS[j.skill_name] || j.skill_name || '';
    const skillBadge = skillLabel ? `<span class="tp-skill-badge">${esc(skillLabel)}</span>` : '';
    if (j.status === 'running') {
      return `
        <div class="tp-row tp-row-running">
          <div class="tp-row-left">
            <span class="tp-spinner"></span>
            <span class="tp-ticker">${esc(j.ticker)}</span>
            ${skillBadge}
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
            <div><span class="tp-ticker">${esc(j.ticker)}</span> ${skillBadge} <span class="tp-error-label">Failed</span></div>
            <div class="tp-error-msg">${esc((j.error || '').slice(0, 240))}</div>
          </div>
        </div>
        <div class="tp-row-right">
          <button class="tp-btn" onclick="retryTradePlan('${esc(j.ticker)}', '${esc(j.timeframe || '')}', '${esc(j.skill_name || '')}')">Retry</button>
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
    const skillLabel = SKILL_LABELS[f.skill_name] || f.skill_name || '';
    const skillBadge = skillLabel ? `<span class="tp-skill-badge">${esc(skillLabel)}</span>` : '';
    const dateLabel = f.skill_name === 'options-trade-plan' ? `expiry ${esc(f.expiry || '?')}` : esc(f.expiry || '?');
    const metricsStr = renderMetricsSubtitle(f.metrics);
    const metricsLine = metricsStr ? `<div class="tp-metrics">${esc(metricsStr)}</div>` : '';
    return `
      <div class="tp-row tp-row-file">
        <div class="tp-row-left">
          <span class="tp-status-dot tp-dot-done"></span>
          <div>
            <div><span class="tp-ticker">${esc(f.ticker || '?')}</span>
              ${skillBadge}
              <span class="tp-meta">${dateLabel}</span></div>
            <div class="tp-file-sub">${esc(relTime)} · ${sizeKb} KB</div>
            ${metricsLine}
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

function retryTradePlan(ticker, timeframe, skill_name) {
  document.getElementById('tp-ticker').value = ticker;
  if (skill_name) {
    const skillEl = document.getElementById('tp-skill');
    if (skillEl) {
      skillEl.value = skill_name;
      applySkillFieldVisibility();
    }
  }
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
  const skillEl = document.getElementById('tp-skill');
  if (skillEl && !skillEl._fieldVisHookInstalled) {
    skillEl.addEventListener('change', applySkillFieldVisibility);
    skillEl._fieldVisHookInstalled = true;
  }
  applySkillFieldVisibility();
  refreshTradePlans();
  _tpPollTimer = setInterval(refreshTradePlans, 3000);
}

function stopTradePlansPolling() {
  if (_tpPollTimer) {
    clearInterval(_tpPollTimer);
    _tpPollTimer = null;
  }
}
